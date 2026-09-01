"""
The XAUUSD study suite. Each function prints one exhibit from the report.

Run `python analysis.py` to reproduce every number in FINDINGS.md from the
parquet files written by data_pipeline.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

SPREAD_SCENARIOS = [
    (0.10, "CME GC futures (1 tick + commission)"),
    (0.20, "GC futures, wider fill"),
    (0.30, "tight ECN CFD"),
    (0.50, "typical retail CFD"),
    (1.00, "wide retail CFD"),
]


def load():
    m1 = pd.read_parquet("m1.parquet")
    daily = pd.read_parquet("daily.parquet")
    daily.index = pd.to_datetime(daily.index)
    m1 = m1[m1["tday"].isin(set(daily.index.date))]
    return m1, daily


def _closes(m1: pd.DataFrame) -> pd.DataFrame:
    minute = m1.index.hour * 60 + m1.index.minute
    piv = m1.pivot_table(index="tday", columns=minute, values="close", aggfunc="last")
    piv.index = pd.to_datetime(piv.index)
    return piv


def at(piv: pd.DataFrame, hour: int, minute: int) -> pd.Series:
    key = hour * 60 + minute
    return piv[key] if key in piv.columns else pd.Series(np.nan, index=piv.index)


# --------------------------------------------------------------------------
def volatility_clock(m1):
    """Where in the 24h cycle the day's range is actually made."""
    t = m1.assign(rng=m1["high"] - m1["low"], hr=m1.index.hour)
    p = t.groupby("hr").agg(bars=("rng", "size"), avg=("rng", "mean"))
    share = p["avg"] * p["bars"]
    p["pct_of_range"] = (share / share.sum() * 100).round(2)
    return p[["avg", "pct_of_range"]].rename(columns={"avg": "avg_m1_range_usd"})


def extreme_timing(m1):
    """The hour that prints the session high and the session low."""
    def hl(x):
        return pd.Series({"hi": x["high"].idxmax().hour, "lo": x["low"].idxmin().hour})
    z = m1.groupby("tday").apply(hl, include_groups=False)
    return pd.DataFrame({
        "high_pct": (z["hi"].value_counts(normalize=True) * 100).round(2),
        "low_pct": (z["lo"].value_counts(normalize=True) * 100).round(2),
    }).sort_index().fillna(0)


def reopen_artifact(m1):
    """The 18:00 NY session reopen: how much of that hour's 'edge' is one print.

    This is the single most important diagnostic in the study. The reopen bar
    carries a stale quote, so open->close on it manufactures a return that no
    order could ever have captured.
    """
    h18 = m1[m1.index.hour == 18].copy()
    h18["r"] = h18["close"] - h18["open"]
    by_minute = h18.groupby(h18.index.minute)["r"].sum()
    total = by_minute.sum()
    return {
        "hour_total_usd": round(total, 1),
        "minute_00_usd": round(by_minute.loc[0], 1),
        "share_from_first_print_pct": round(by_minute.loc[0] / total * 100, 1),
        "minutes_00_04_share_pct": round(by_minute.loc[0:4].sum() / total * 100, 1),
    }


def session_drift(piv):
    """Drift by session, measured from 18:05 so the reopen print is excluded."""
    windows = {
        "Asia 18:05-02:00": ((18, 5), (2, 0)),
        "London 02:00-08:00": ((2, 0), (8, 0)),
        "NY AM 08:00-12:00": ((8, 0), (12, 0)),
        "NY PM 12:00-16:58": ((12, 0), (16, 58)),
    }
    rows = []
    for name, ((h1, m1_), (h2, m2)) in windows.items():
        bp = ((at(piv, h2, m2) / at(piv, h1, m1_) - 1) * 1e4).dropna()
        t = stats.ttest_1samp(bp, 0)
        rows.append({"window": name, "n": len(bp), "mean_bp": round(bp.mean(), 2),
                     "up_pct": round((bp > 0).mean() * 100, 1),
                     "t": round(t.statistic, 2), "p": round(t.pvalue, 4),
                     "sharpe_ann": round(bp.mean() / bp.std() * np.sqrt(252), 2)})
    return pd.DataFrame(rows)


def session_exposure(piv, daily):
    """What a dollar earns holding gold in one session only, versus all day."""
    parts = pd.DataFrame({
        "asia": at(piv, 2, 0) / at(piv, 18, 5) - 1,
        "london": at(piv, 8, 0) / at(piv, 2, 0) - 1,
        "ny": at(piv, 16, 58) / at(piv, 8, 0) - 1,
    }).dropna()

    rows = []
    for name, weights, hours in [
        ("Buy & hold (all sessions)", (1, 1, 1), 23),
        ("Asia only", (1, 0, 0), 8),
        ("London only", (0, 1, 0), 6),
        ("New York only", (0, 0, 1), 9),
        ("Overlay 1.5 / 0.5 / 0.0", (1.5, 0.5, 0.0), 14),
    ]:
        r = (parts["asia"] * weights[0] + parts["london"] * weights[1]
             + parts["ny"] * weights[2])
        eq = (1 + r).cumprod()
        rows.append({
            "exposure": name,
            "CAGR_pct": round((eq.iloc[-1] ** (252 / len(r)) - 1) * 100, 2),
            "vol_pct": round(r.std() * np.sqrt(252) * 100, 1),
            "sharpe": round(r.mean() / r.std() * np.sqrt(252), 2),
            "maxDD_pct": round(((eq / eq.cummax()) - 1).min() * 100, 1),
            "market_hours": hours,
        })
    return pd.DataFrame(rows), parts


def cost_sensitivity(piv):
    """The Asia drift against realistic execution costs. This is the whole game."""
    entry, exit_ = at(piv, 18, 5), at(piv, 2, 0)
    df = pd.DataFrame({"entry": entry, "exit": exit_}).dropna()
    df["usd"] = df["exit"] - df["entry"]

    rows = []
    for cost, label in SPREAD_SCENARIOS:
        net_bp = (df["usd"] - cost) / df["entry"] * 1e4
        rows.append({"venue": label, "cost_usd_oz": cost,
                     "net_bp_per_night": round(net_bp.mean(), 2),
                     "annualised_pct": round(net_bp.mean() * 252 / 100, 2),
                     "verdict": "viable" if net_bp.mean() > 0 else "dead"})
    return pd.DataFrame(rows)


def predictability(daily):
    """Direction versus volatility: which one is actually forecastable."""
    d = daily.copy()
    prev_close = d["close"].shift()
    d["tr"] = np.maximum(d["high"] - d["low"],
                         np.maximum((d["high"] - prev_close).abs(),
                                    (d["low"] - prev_close).abs()))
    d["atr"] = d["tr"].rolling(14).mean()
    d["lr"] = np.log(d["close"] / prev_close)

    ok = d["atr"].shift().notna() & d["tr"].notna()
    vol_r2 = np.corrcoef(d["atr"].shift()[ok], d["tr"][ok])[0, 1] ** 2
    ok2 = d["lr"].shift().notna() & d["lr"].notna()
    dir_r2 = np.corrcoef(d["lr"].shift()[ok2], d["lr"][ok2])[0, 1] ** 2
    return {"volatility_R2": round(vol_r2, 4), "direction_R2": round(dir_r2, 6),
            "ratio": round(vol_r2 / dir_r2)}


def win_rate_dial(sweep_fn):
    """Same setup, only the target changes. Win rate moves; expectancy does not."""
    rows = []
    for rr in [0.25, 0.5, 1.0, 2.0, 3.0, 5.0]:
        t = sweep_fn(rr)
        r = t["R"]
        rows.append({"target_R": rr, "win_pct": round((r > 0).mean() * 100, 1),
                     "expectancy_R": round(r.mean(), 4),
                     "total_R": round(r.sum(), 1)})
    return pd.DataFrame(rows)


def news_windows(m1, piv, daily):
    """NFP and the 08:30 release window."""
    minute = m1.index.hour * 60 + m1.index.minute
    highs = m1.pivot_table(index="tday", columns=minute, values="high", aggfunc="max")
    lows = m1.pivot_table(index="tday", columns=minute, values="low", aggfunc="min")
    highs.index = pd.to_datetime(highs.index)
    lows.index = pd.to_datetime(lows.index)

    def rng(a, b):
        cols = [c for c in highs.columns if a <= c < b]
        return highs[cols].max(axis=1) - lows[cols].min(axis=1)

    idx = highs.index
    nfp = (idx.dayofweek == 4) & (idx.day <= 7)
    release, quiet = rng(8 * 60 + 30, 8 * 60 + 35), rng(7 * 60, 7 * 60 + 5)
    day_range = (daily["high"] - daily["low"]).reindex(idx)

    # does the first move survive? measure the 5-minute impulse, then ask whether
    # price is still on that side of it at the close.
    before, after = at(piv, 8, 29), at(piv, 8, 35)
    direction = np.sign(after - before)
    to_close = ((at(piv, 16, 58) - after) * direction).dropna()
    nfp_days = pd.Series(nfp, index=idx).reindex(to_close.index).fillna(False)

    return {
        "median_release_range_usd": round(release.median(), 2),
        "median_quiet_range_usd": round(quiet.median(), 2),
        "nfp_release_range_usd": round(release[nfp].median(), 2),
        "nfp_pct_of_day_range": round((release[nfp] / day_range[nfp]).median() * 100, 1),
        "nfp_spike_holds_to_close_pct":
            round((to_close[nfp_days] > 0).mean() * 100, 1),
        "other_days_spike_holds_to_close_pct":
            round((to_close[~nfp_days] > 0).mean() * 100, 1),
    }


if __name__ == "__main__":
    m1, daily = load()
    piv = _closes(m1)

    print("\n-- volatility clock (NY hour) --")
    print(volatility_clock(m1).to_string())
    print("\n-- reopen artifact --")
    print(reopen_artifact(m1))
    print("\n-- session drift, reopen print excluded --")
    print(session_drift(piv).to_string(index=False))
    print("\n-- exposure by session --")
    table, _ = session_exposure(piv, daily)
    print(table.to_string(index=False))
    print("\n-- cost sensitivity of the Asia drift --")
    print(cost_sensitivity(piv).to_string(index=False))
    print("\n-- what is forecastable --")
    print(predictability(daily))
    print("\n-- news --")
    print(news_windows(m1, piv, daily))
