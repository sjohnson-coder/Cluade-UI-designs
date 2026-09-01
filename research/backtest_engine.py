"""
Event-driven intraday backtest engine for XAUUSD.

Two entry models, both walked bar-by-bar on M1 so that stop and target order
inside a bar is never assumed away:

    sweep_reclaim()  -- the SMC/ICT liquidity-grab model. Price trades through
                        a reference level (Asian high/low, previous day high/low),
                        then closes back inside it. Fade the failed break.
    breakout()       -- the inverse. Trade the break in its own direction.

Every trade is charged an explicit spread. That single line is the difference
between the published version of these strategies and the one below.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SESSION_END_MIN = 17 * 60          # flat by 17:00 New York


def load(m1_path: str = "m1.parquet", daily_path: str = "daily.parquet"):
    m1 = pd.read_parquet(m1_path)
    daily = pd.read_parquet(daily_path)
    daily.index = pd.to_datetime(daily.index)
    m1 = m1[m1["tday"].isin(set(daily.index.date))].sort_index()
    return m1, daily


def reference_levels(m1: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Asian range and previous-day extremes, plus ATR14 for stop scaling.

    Everything here is lagged: a level used on day D is built only from data
    available before day D's trading window opens.
    """
    hour = m1.index.hour
    asian = m1[(hour >= 18) | (hour < 2)]
    a = asian.groupby("tday").agg(asia_high=("high", "max"),
                                  asia_low=("low", "min"),
                                  n=("close", "size"))
    a = a[a["n"] > 300]
    a.index = pd.to_datetime(a.index)

    lv = pd.DataFrame(index=daily.index)
    lv["pdh"] = daily["high"].shift()
    lv["pdl"] = daily["low"].shift()
    lv["atr"] = (daily["high"] - daily["low"]).rolling(14).mean().shift()
    return lv.join(a[["asia_high", "asia_low"]]).dropna()


def _day_arrays(m1: pd.DataFrame) -> dict:
    """Pre-slice to numpy per session; the inner loop runs millions of times."""
    out = {}
    for day, g in m1.groupby("tday"):
        out[pd.Timestamp(day)] = (
            g.index.hour.values * 60 + g.index.minute.values,
            g["high"].values, g["low"].values, g["close"].values,
        )
    return out


def _resolve(side, entry, stop, target, rr, minutes, high, low, close, from_min):
    """Walk forward to the first of stop / target / session end."""
    fwd = np.where((minutes > from_min) & (minutes <= SESSION_END_MIN))[0]
    for j in fwd:
        if side == "long":
            if low[j] <= stop:
                return -1.0, "stop"
            if high[j] >= target:
                return rr, "target"
        else:
            if high[j] >= stop:
                return -1.0, "stop"
            if low[j] <= target:
                return rr, "target"
    if len(fwd):
        last = close[fwd[-1]]
        risk = abs(entry - stop)
        return ((last - entry) if side == "long" else (entry - last)) / risk, "timed"
    return 0.0, "no-data"


def sweep_reclaim(m1, levels, days, level, side, win_start, win_end,
                  reclaim_max=60, rr=2.0, stop_buffer_atr=0.10, spread=0.35):
    """side='short' fades a sweep ABOVE `level`; 'long' fades a sweep BELOW it."""
    trades = []
    for day in levels.index:
        if day not in days:
            continue
        minutes, high, low, close = days[day]
        atr, ref = levels.at[day, "atr"], levels.at[day, level]
        if not (np.isfinite(atr) and np.isfinite(ref)) or atr <= 0:
            continue

        window = np.where((minutes >= win_start) & (minutes < win_end))[0]
        swept, extreme, swept_at = False, np.nan, -1

        for i in window:
            if not swept:
                if side == "short" and high[i] > ref:
                    swept, extreme, swept_at = True, high[i], i
                elif side == "long" and low[i] < ref:
                    swept, extreme, swept_at = True, low[i], i
                continue

            extreme = max(extreme, high[i]) if side == "short" else min(extreme, low[i])
            if minutes[i] - minutes[swept_at] > reclaim_max:
                break                                   # sweep never reclaimed

            reclaimed = close[i] < ref if side == "short" else close[i] > ref
            if not reclaimed:
                continue

            entry = close[i]
            stop = (extreme + stop_buffer_atr * atr) if side == "short" \
                else (extreme - stop_buffer_atr * atr)
            risk = abs(stop - entry)
            if risk <= 0:
                break
            target = entry - rr * risk if side == "short" else entry + rr * risk

            r, how = _resolve(side, entry, stop, target, rr,
                              minutes, high, low, close, minutes[i])
            trades.append({"day": day, "side": side, "entry": entry, "risk": risk,
                           "R": r - spread / risk, "exit": how,
                           "risk_atr": risk / atr})
            break
    return pd.DataFrame(trades)


def breakout(m1, levels, days, level, side, win_start, win_end,
             rr=2.0, stop_buffer_atr=0.5, spread=0.35, min_displacement_atr=0.05,
             trend=None):
    """Trade the break in its own direction. `trend` is an optional dict of
    day -> signed trend strength; a trade is skipped when it disagrees."""
    trades = []
    for day in levels.index:
        if day not in days:
            continue
        minutes, high, low, close = days[day]
        atr, ref = levels.at[day, "atr"], levels.at[day, level]
        if not (np.isfinite(atr) and np.isfinite(ref)) or atr <= 0:
            continue
        if trend is not None:
            t = trend.get(day, np.nan)
            if not np.isfinite(t) or (side == "long" and t <= 0) or (side == "short" and t >= 0):
                continue

        for i in np.where((minutes >= win_start) & (minutes < win_end))[0]:
            broke = (close[i] > ref + min_displacement_atr * atr) if side == "long" \
                else (close[i] < ref - min_displacement_atr * atr)
            if not broke:
                continue

            entry = close[i]
            stop = ref - stop_buffer_atr * atr if side == "long" else ref + stop_buffer_atr * atr
            risk = abs(entry - stop)
            if risk <= 0:
                break
            target = entry + rr * risk if side == "long" else entry - rr * risk

            r, how = _resolve(side, entry, stop, target, rr,
                              minutes, high, low, close, minutes[i])
            trades.append({"day": day, "side": side, "entry": entry, "risk": risk,
                           "R": r - spread / risk, "exit": how})
            break
    return pd.DataFrame(trades)


def summarise(trades: pd.DataFrame, label: str, years: float = 11.66) -> dict:
    if trades.empty:
        return {"strategy": label, "n": 0}
    r = trades["R"]
    equity = r.cumsum()
    losses = abs(r[r < 0].sum())
    is_r = r[trades["day"].dt.year <= 2021]
    oos_r = r[trades["day"].dt.year >= 2022]
    return {
        "strategy": label,
        "n": len(r),
        "win%": round((r > 0).mean() * 100, 1),
        "expectancy_R": round(r.mean(), 4),
        "total_R": round(r.sum(), 1),
        "PF": round(r[r > 0].sum() / losses, 2) if losses else np.nan,
        "maxDD_R": round((equity - equity.cummax()).min(), 1),
        "trades_yr": round(len(r) / years, 1),
        "IS_exp": round(is_r.mean(), 4) if len(is_r) else np.nan,
        "OOS_exp": round(oos_r.mean(), 4) if len(oos_r) else np.nan,
    }


if __name__ == "__main__":
    m1, daily = load()
    levels = reference_levels(m1, daily)
    days = _day_arrays(m1)

    windows = {
        "London killzone 02:00-05:00": (120, 300),
        "NY killzone 07:00-10:00": (420, 600),
        "Silver bullet 10:00-11:00": (600, 660),
    }
    rows = []
    for name, (a, b) in windows.items():
        for level, side in [("asia_high", "short"), ("asia_low", "long"),
                            ("pdh", "short"), ("pdl", "long")]:
            t = sweep_reclaim(m1, levels, days, level, side, a, b)
            rows.append(summarise(t, f"{name} | fade {level}"))

    print(pd.DataFrame(rows).sort_values("expectancy_R", ascending=False).to_string(index=False))
