"""GodMode demo-data engine.

Generates realistic, internally-consistent XAUUSD trading data that mirrors the
exact response shapes produced by ``MT5Bridge`` so the entire UI is populated and
fully functional when a live MetaTrader 5 terminal is not attached.

Everything is deterministic per UTC-day (seeded) but evolves minute-to-minute so
charts, prices and confidence rings animate naturally on the 5s/10s polling the
frontend already does. This is clearly marked ``source: "demo"`` on every payload
so the UI can badge it, and it never sends real broker orders.
"""
from __future__ import annotations

import math
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any

CURRENCY = "USD"
SYMBOL = "XAUUSD"
BASE_PRICE = 2385.0
START_BALANCE = 10000.0

SESSIONS = ["London", "London / New York", "New York", "Asia"]
STRATEGY_POOL = [
    ("trend_continuation", "Trend Continuation"),
    ("liquidity_sweep", "Liquidity Sweep"),
    ("london_breakout", "London Breakout"),
    ("mean_reversion", "Mean Reversion"),
    ("news_scalper", "News Scalper"),
    ("reversal", "Reversal"),
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _day_seed(offset: int = 0) -> int:
    d = _now().date()
    return int(d.strftime("%Y%m%d")) + offset


def current_session() -> str:
    hour = _now().hour
    if 7 <= hour < 12:
        return "London"
    if 12 <= hour < 17:
        return "London / New York"
    if 17 <= hour < 22:
        return "New York"
    return "Asia"


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1 - alpha) * out[-1])
    return out


def _candles(count: int = 120, timeframe: str = "M15") -> list[dict[str, Any]]:
    """Deterministic-per-day random walk with intraday drift, EMAs attached."""
    rng = random.Random(_day_seed())
    minutes = {"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240, "D1": 1440}.get(timeframe.upper(), 15)
    now = _now()
    # advance the walk by how far into the day we are so prices move over time
    elapsed_steps = int((now.hour * 60 + now.minute) / max(1, minutes))
    total = count + elapsed_steps
    price = BASE_PRICE + rng.uniform(-12, 12)
    closes: list[float] = []
    drift = math.sin(_day_seed() % 7) * 0.6
    for i in range(total):
        wave = math.sin(i / 9.0) * 1.4 + math.sin(i / 23.0) * 2.2
        step = rng.uniform(-1.7, 1.7) + drift * 0.15 + wave * 0.12
        price = max(2200.0, price + step)
        closes.append(round(price, 3))
    closes = closes[-count:]
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, min(200, max(2, len(closes))))
    out: list[dict[str, Any]] = []
    start_time = now - timedelta(minutes=minutes * (count - 1))
    for i, close in enumerate(closes):
        o = closes[i - 1] if i else close - rng.uniform(-1.0, 1.0)
        hi = max(o, close) + abs(rng.uniform(0.3, 1.8))
        lo = min(o, close) - abs(rng.uniform(0.3, 1.8))
        t = start_time + timedelta(minutes=minutes * i)
        out.append({
            "time": int(t.timestamp()),
            "timeLabel": t.strftime("%H:%M"),
            "open": round(o, 3),
            "high": round(hi, 3),
            "low": round(lo, 3),
            "close": round(close, 3),
            "tickVolume": rng.randint(420, 2600),
            "ema20": round(ema20[i], 3),
            "ema50": round(ema50[i], 3),
            "ema200": round(ema200[i], 3),
        })
    return out


def _atr(candles: list[dict[str, Any]], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    trs = []
    prev = candles[0]["close"]
    for c in candles[1:]:
        trs.append(max(c["high"] - c["low"], abs(c["high"] - prev), abs(c["low"] - prev)))
        prev = c["close"]
    return round(sum(trs[-period:]) / max(1, min(period, len(trs))), 3)


def _trend(candles: list[dict[str, Any]]) -> str:
    last = candles[-1]
    c, e20, e50, e200 = last["close"], last["ema20"], last["ema50"], last["ema200"]
    if c > e20 > e50 > e200:
        return "Strong Bullish Trend"
    if c < e20 < e50 < e200:
        return "Strong Bearish Trend"
    if c > e50:
        return "Weak Bullish Trend"
    if c < e50:
        return "Weak Bearish Trend"
    return "Range"


# --------------------------------------------------------------------------- #
#  Public snapshot builders (mirror MT5Bridge output shapes)
# --------------------------------------------------------------------------- #
def market_snapshot(symbol: str | None = None, timeframe: str = "M15") -> dict[str, Any]:
    symbol = symbol or SYMBOL
    candles = _candles(120, timeframe)
    last = candles[-1]
    prev = candles[-2]
    atr = _atr(candles)
    trend = _trend(candles)
    price = last["close"]
    change = round(price - prev["close"], 3)
    bull = "Bull" in trend
    side = "BUY" if bull else "SELL" if "Bear" in trend else "WAIT"
    confidence = 87 if "Strong" in trend else 72 if side != "WAIT" else 58
    return {
        "source": "demo",
        "connected": True,
        "demo": True,
        "symbol": symbol,
        "price": price,
        "bid": round(price - 0.12, 3),
        "ask": round(price + 0.12, 3),
        "change": change,
        "changePct": round((change / prev["close"]) * 100, 3) if prev["close"] else 0.0,
        "timeframe": timeframe,
        "session": current_session(),
        "volatility": "High" if atr > 20 else "Normal",
        "spread": round(0.12 + abs(math.sin(time.time() / 30)) * 0.18, 2),
        "atr14": atr,
        "regime": trend,
        "activeStrategy": "Liquidity Sweep + Order Block Retest" if bull else "Mean Reversion",
        "confidence": confidence,
        "side": side,
        "candles": candles,
        "sparkline": [{"x": i, "value": c["close"]} for i, c in enumerate(candles[-40:])],
        "timestamp": _now().isoformat(),
    }


def _open_positions(market: dict[str, Any]) -> list[dict[str, Any]]:
    rng = random.Random(_day_seed(3))
    price = market["price"]
    specs = [
        ("XAUUSD", "BUY", 2.00, price - 16.6, 0.66, "TP2", "Adaptive Strategy Engine"),
        ("GBPUSD", "BUY", 1.50, 1.27345, 0.33, "TP1", "London Breakout"),
        ("USDCAD", "SELL", 1.00, 1.36210, 0.50, "TP1", "Mean Reversion"),
    ]
    out = []
    for i, (sym, direction, lots, entry, prog, tp_label, strat) in enumerate(specs):
        cur = price if sym == "XAUUSD" else round(entry + rng.uniform(-0.004, 0.006), 5)
        diff = (cur - entry) if direction == "BUY" else (entry - cur)
        pip_val = 100 if sym == "XAUUSD" else 100000
        pnl = round(diff * lots * (10 if sym == "XAUUSD" else 0.1) * (pip_val / 100), 2)
        out.append({
            "ticket": 128456789 + i,
            "symbol": sym,
            "name": f"{sym[:3]} / {sym[3:]}",
            "direction": direction,
            "lots": lots,
            "entryPrice": round(entry, 5 if sym != "XAUUSD" else 3),
            "currentPrice": round(cur, 5 if sym != "XAUUSD" else 3),
            "sl": round(entry - 25 if direction == "BUY" else entry + 25, 3) if sym == "XAUUSD" else round(entry - 0.004, 5),
            "tp": round(entry + 45 if direction == "BUY" else entry - 45, 3) if sym == "XAUUSD" else round(entry + 0.006, 5),
            "tp1": round(entry + 13, 3) if sym == "XAUUSD" else None,
            "tp2": round(entry + 25, 3) if sym == "XAUUSD" else None,
            "tp3": round(entry + 45, 3) if sym == "XAUUSD" else None,
            "pnlUsd": pnl,
            "pnlPct": round(diff / entry * 100, 2),
            "tpProgress": int(prog * 100),
            "tpLabel": tp_label,
            "rr": "1 : 2.52" if sym == "XAUUSD" else "1 : 1.8",
            "trailingStop": sym == "XAUUSD",
            "beMoved": sym == "XAUUSD",
            "executionQuality": "Excellent",
            "openTime": (_now() - timedelta(hours=i + 1, minutes=12)).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "strategy": strat,
            "magicNumber": 20250524,
            "comment": "GODMODE_demo",
            "source": "demo",
        })
    return out


def _pending_orders(market: dict[str, Any]) -> list[dict[str, Any]]:
    price = market["price"]
    return [
        {"ticket": 128460001, "symbol": "XAUUSD", "type": "Buy Limit", "direction": "BUY", "lots": 1.5,
         "price": round(price - 13, 3), "trigger": f"<= {round(price - 13, 2)}", "expiry": "GTC",
         "status": "Active", "magicNumber": 20250524, "comment": "GODMODE_demo", "source": "demo"},
        {"ticket": 128460002, "symbol": "EURUSD", "type": "Sell Stop", "direction": "SELL", "lots": 1.0,
         "price": 1.07850, "trigger": "<= 1.07850", "expiry": "GTC",
         "status": "Active", "magicNumber": 20250524, "comment": "GODMODE_demo", "source": "demo"},
    ]


def _closed_trades(days: int = 90) -> list[dict[str, Any]]:
    rng = random.Random(_day_seed(11))
    syms = ["XAUUSD", "XAUUSD", "XAUUSD", "GBPUSD", "EURUSD", "US30", "EURJPY", "AUDUSD", "NAS100"]
    strategies = [s[1] for s in STRATEGY_POOL]
    regimes = ["Strong Bullish Trend", "Range", "Weak Bullish Trend", "Strong Bearish Trend", "Volatile"]
    out: list[dict[str, Any]] = []
    n = 124
    balance = START_BALANCE
    for i in range(n):
        sym = rng.choice(syms)
        direction = rng.choice(["BUY", "SELL"])
        win = rng.random() < 0.70  # ~68-70% win rate (matches mockup)
        strat = rng.choice(strategies)
        entry = BASE_PRICE + rng.uniform(-30, 30) if sym == "XAUUSD" else round(rng.uniform(0.9, 1.4), 5)
        # Wins average ~1.3R, losses ~ -1.0R -> profit factor lands near 2.3
        r_mult = round(rng.uniform(0.7, 2.0), 2) if win else round(-rng.uniform(0.9, 1.6), 2)
        risk = rng.choice([120, 150, 180, 210, 250])
        pnl = round(r_mult * risk, 2)
        balance += pnl
        close_dt = _now() - timedelta(hours=int((n - i) * 7.3))
        out.append({
            "ticket": f"JRN-{close_dt.strftime('%Y%m%d')}-{i:03d}",
            "symbol": sym,
            "name": sym,
            "direction": direction,
            "side": direction,
            "lots": rng.choice([0.5, 1.0, 1.25, 1.5, 2.0]),
            "entryPrice": round(entry, 3 if sym == "XAUUSD" else 5),
            "exitPrice": round(entry + (r_mult * 8 if direction == "BUY" else -r_mult * 8), 3) if sym == "XAUUSD" else round(entry + rng.uniform(-0.01, 0.01), 5),
            "sl": round(entry - 25 if direction == "BUY" else entry + 25, 3) if sym == "XAUUSD" else None,
            "tp": round(entry + 45 if direction == "BUY" else entry - 45, 3) if sym == "XAUUSD" else None,
            "pnlUsd": pnl,
            "pnlPct": round(pnl / balance * 100, 2),
            "rMultiple": r_mult,
            "rr": f"{abs(r_mult):.2f}R",
            "holdTime": f"{rng.randint(1, 8)}h {rng.randint(0, 59)}m",
            "duration": f"{rng.randint(1, 8)}h {rng.randint(0, 59)}m",
            "closeTime": close_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "date": close_dt.strftime("%Y-%m-%d"),
            "time": close_dt.strftime("%H:%M:%S"),
            "reason": rng.choice(["TP1 Hit", "TP2 Hit", "TP3 Hit", "SL Hit", "Manual", "Trailing Stop"]) if not win else rng.choice(["TP1 Hit", "TP2 Hit", "TP3 Hit"]),
            "strategy": strat,
            "marketRegime": rng.choice(regimes),
            "session": rng.choice(SESSIONS),
            "confidence": rng.randint(58, 93),
            "outcome": "WIN" if pnl > 0 else "LOSS",
            "htfTrend": rng.choice(["Bullish", "Bearish", "Neutral"]),
            "newsImpact": rng.choice(["Low", "Medium", "High"]),
            "structure": rng.choice(["BOS", "CHoCH", "Range"]),
            "tags": rng.sample(["Breakout", "London Session", "liquidity sweep", "High Volatility", "OTE", "Order Block"], k=3),
            "lessons": "Price swept liquidity below the prior low and broke structure with strong displacement; patience waiting for confirmation paid off.",
            "improvement": "Could have taken partial profit at 1.5R and let the rest run.",
            "aiNotes": "Strong execution. Entry aligned with strategy rules and market structure. High-probability setup with institutional confirmation.",
            "aiScore": round(rng.uniform(7.5, 9.5), 1),
            "candles": _trade_thumbnail(rng, direction, win),
            "magicNumber": 20250524,
            "comment": "GODMODE_demo",
            "currency": CURRENCY,
            "source": "demo",
        })
    out.reverse()  # newest first
    return out


def _trade_thumbnail(rng: random.Random, direction: str, win: bool) -> list[dict[str, Any]]:
    """Small candle series for journal/trade thumbnails."""
    price = BASE_PRICE + rng.uniform(-20, 20)
    bias = (1 if direction == "BUY" else -1) * (1 if win else -0.6)
    rows = []
    for i in range(24):
        o = price
        price = price + rng.uniform(-1.2, 1.2) + bias * 0.25
        rows.append({"time": i, "open": round(o, 2), "high": round(max(o, price) + rng.uniform(0.1, 0.8), 2),
                     "low": round(min(o, price) - rng.uniform(0.1, 0.8), 2), "close": round(price, 2)})
    return rows


def account_snapshot() -> dict[str, Any]:
    history = _closed_trades()
    today = _now().strftime("%Y-%m-%d")
    net = sum(t["pnlUsd"] for t in history)
    daily = sum(t["pnlUsd"] for t in history if t["date"] == today) or 456.78
    balance = round(START_BALANCE + net, 2)
    open_risk = 562.50
    equity = round(balance + 455.0, 2)
    return {
        "source": "demo",
        "connected": True,
        "demo": True,
        "balance": balance,
        "equity": equity,
        "dailyPnl": round(daily, 2),
        "dailyPnlPct": round(daily / balance * 100, 2),
        "openRisk": open_risk,
        "openRiskPct": round(open_risk / equity * 100, 2),
        "freeMargin": 7842.11,
        "margin": round(equity - 7842.11, 2),
        "marginHealth": 72,
        "dailyLossUsedPct": 26.5,
        "drawdownPct": 24.5,
        "currency": CURRENCY,
        "login": 51234567,
        "server": "ICMarketsSC-Live05",
        "broker": "IC Markets (SC) MT5 — Demo Mode",
        "leverage": 500,
    }


def trades() -> dict[str, Any]:
    market = market_snapshot()
    return {
        "active": _open_positions(market),
        "pending": _pending_orders(market),
        "history": _closed_trades(),
        "memoryScope": "demo",
        "source": "demo",
        "message": "Demo data — connect MetaTrader 5 for live bot-only trades.",
    }


def signals() -> list[dict[str, Any]]:
    rng = random.Random(_day_seed(7) + int(time.time() / 15))
    market = market_snapshot()
    base = market["price"]
    rows = []
    setups = [
        ("BUY", "Trend Continuation", 87, "Active"),
        ("SELL", "Mean Reversion", 82, "Active"),
        ("HOLD", "Liquidity Sweep", 58, "Active"),
        ("BUY", "Order Block Break", 76, "Completed"),
        ("SELL", "Break of Structure", 71, "Completed"),
    ]
    for i, (side, strat, conf, status) in enumerate(setups):
        entry = round(base + rng.uniform(-8, 8), 2)
        sl = round(entry - 7.6 if side == "BUY" else entry + 7.6, 2)
        tp1 = round(entry + 7.2 if side == "BUY" else entry - 7.2, 2)
        tp2 = round(entry + 15.8 if side == "BUY" else entry - 15.8, 2)
        t = _now() - timedelta(minutes=i * 5 + 1)
        result = "—"
        if status == "Completed":
            result = f"+{rng.uniform(0.3, 0.9):.2f}%" if side == "BUY" else f"-{rng.uniform(0.1, 0.5):.2f}%"
        rows.append({
            "id": f"demo-{i}-{int(time.time())}",
            "time": t.strftime("%H:%M:%S"),
            "date": t.strftime("%Y-%m-%d"),
            "pair": SYMBOL, "symbol": SYMBOL,
            "side": side,
            "strategy": strat,
            "timeframe": "M15",
            "entry": entry, "entryPrice": entry,
            "sl": sl, "tp1": tp1, "tp2": tp2,
            "tp3": round(entry + 24 if side == "BUY" else entry - 24, 2),
            "rr": "1 : 2.07",
            "risk": "0.32%", "reward1": "0.30%", "reward2": "0.66%",
            "confidence": conf,
            "status": status,
            "result": result,
            "price": entry,
            "change": f"{market['changePct']:.2f}%",
            "session": current_session(),
            "lots": "1.25",
            "reason": "Price is trending above the 50 EMA with strong bullish momentum. Break and retest of previous resistance turned support. RSI above 50 and MACD bullish crossover confirm continuation." if side == "BUY" else "Price reached an extreme into a key supply zone with RSI divergence; expecting a controlled mean reversion back to value.",
            "source": "demo",
        })
    return rows


def analytics(date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
    history = _closed_trades()
    if date_from or date_to:
        def _in_range(t):
            d = str(t.get("date") or t.get("closeTime", ""))[:10]
            if date_from and d < date_from:
                return False
            if date_to and d > date_to:
                return False
            return True
        history = [t for t in history if _in_range(t)]

    total = len(history)
    wins = [t for t in history if t["pnlUsd"] > 0]
    losses = [t for t in history if t["pnlUsd"] < 0]
    gross_profit = sum(t["pnlUsd"] for t in wins)
    gross_loss = abs(sum(t["pnlUsd"] for t in losses))
    net = round(gross_profit - gross_loss, 2)

    # equity curve
    equity = START_BALANCE
    bench = START_BALANCE
    curve = []
    for t in sorted(history, key=lambda x: x["closeTime"]):
        equity += t["pnlUsd"]
        bench += t["pnlUsd"] * 0.45
        curve.append({"date": t["date"], "equity": round(equity, 2), "benchmark": round(bench, 2)})
    # drawdown
    peak = START_BALANCE
    drawdown = []
    for p in curve:
        peak = max(peak, p["equity"])
        dd = round((p["equity"] - peak) / peak * 100, 2)
        drawdown.append({"date": p["date"], "value": dd})
    max_dd = abs(min((d["value"] for d in drawdown), default=0.0))

    # strategy aggregation
    strat_map: dict[str, dict[str, Any]] = {}
    for t in history:
        s = strat_map.setdefault(t["strategy"], {"Strategy": t["strategy"], "net": 0.0, "wins": 0, "Trades": 0})
        s["net"] += t["pnlUsd"]
        s["Trades"] += 1
        if t["pnlUsd"] > 0:
            s["wins"] += 1
    top = sorted(strat_map.values(), key=lambda x: x["net"], reverse=True)
    top_strategies = [{"Strategy": s["Strategy"], "name": s["Strategy"], "Net PnL": f"+${s['net']:,.2f}",
                       "netPnl": round(s["net"], 2), "Win Rate": f"{round(s['wins'] / s['Trades'] * 100)}%" if s["Trades"] else "0%",
                       "winRate": round(s["wins"] / s["Trades"] * 100) if s["Trades"] else 0, "Trades": s["Trades"]} for s in top]

    # sessions
    sess_map: dict[str, dict[str, Any]] = {}
    for t in history:
        s = sess_map.setdefault(t["session"], {"Session": t["session"], "net": 0.0, "wins": 0, "n": 0})
        s["net"] += t["pnlUsd"]; s["n"] += 1
        if t["pnlUsd"] > 0:
            s["wins"] += 1
    sessions = [{"Session": s["Session"], "Net PnL": f"${s['net']:,.2f}", "Win Rate": f"{round(s['wins'] / s['n'] * 100)}%" if s["n"] else "0%",
                 "Trades": s["n"], "Expectancy": f"${round(s['net'] / s['n'], 2)}" if s["n"] else "$0"} for s in sorted(sess_map.values(), key=lambda x: x["net"], reverse=True)]

    # returns heatmap (weeks x days)
    rng = random.Random(_day_seed(5))
    returns = [{"week": f"Week {w}", "Mon": round(rng.uniform(-0.5, 2.0), 2), "Tue": round(rng.uniform(-0.5, 2.0), 2),
                "Wed": round(rng.uniform(-0.5, 2.0), 2), "Thu": round(rng.uniform(-0.5, 1.5), 2),
                "Fri": round(rng.uniform(-0.3, 1.5), 2)} for w in range(1, 6)]

    heatmap = [{"x": s, "v": round(rng.uniform(-100, 6700), 2)} for s in ["M5", "M15", "H1", "H4", "D1"]]
    exec_quality = [{"x": b, "v": round(rng.uniform(2, 80), 1)} for b in ["<0", "0-0.5", "0.5-1", "1-2", "2-3", ">3"]]
    scatter = [{"confidence": rng.randint(50, 95), "result": round(rng.uniform(-2, 4), 2)} for _ in range(40)]

    buy_n = [t for t in history if t["direction"] == "BUY"]
    sell_n = [t for t in history if t["direction"] == "SELL"]

    return {
        "source": "demo",
        "demo": True,
        "kpis": {
            "netProfit": net,
            "returnPct": round(net / START_BALANCE * 100, 2),
            "totalTrades": total,
            "winRate": round(len(wins) / total * 100, 1) if total else 0.0,
            "profitFactor": round(gross_profit / gross_loss, 2) if gross_loss else 0.0,
            "expectancy": round(net / total, 2) if total else 0.0,
            "maxDrawdown": round(max_dd, 2),
        },
        "startingBalance": START_BALANCE,
        "endingBalance": round(START_BALANCE + net, 2),
        "equityCurve": curve,
        "drawdown": drawdown,
        "returns": returns,
        "topStrategies": top_strategies,
        "sessions": sessions,
        "marketHeatmap": heatmap,
        "executionQuality": exec_quality,
        "expectancyScatter": scatter,
        "confidenceResult": scatter,
        "buyWinRate": round(len([t for t in buy_n if t["pnlUsd"] > 0]) / len(buy_n) * 100, 1) if buy_n else 0,
        "sellWinRate": round(len([t for t in sell_n if t["pnlUsd"] > 0]) / len(sell_n) * 100, 1) if sell_n else 0,
        "breakEvenRate": 4.5,
        "lossRate": round(len(losses) / total * 100, 1) if total else 0,
        "avgSlippage": 0.21,
        "fillQuality": "Excellent",
        "history": history,
        "currency": CURRENCY,
        "account": account_snapshot(),
    }


def journal(date_from: str | None = None, date_to: str | None = None) -> list[dict[str, Any]]:
    history = _closed_trades()
    if date_from or date_to:
        history = [t for t in history if (not date_from or t["date"] >= date_from) and (not date_to or t["date"] <= date_to)]
    return history


def dashboard(decision_fn=None) -> dict[str, Any]:
    market = market_snapshot()
    account = account_snapshot()
    t = trades()
    a = analytics()
    bull = "Bull" in market["regime"]
    why = [
        "HTF alignment (H1, H4, D1 bullish)" if bull else "HTF showing bearish displacement",
        "Price in premium zone after OTE",
        "Liquidity sweep below lows detected",
        "London session + Kill Zone confluence",
        "Volume confirmation above average",
        "Clean pullback into 15m order block",
    ]
    decision = {
        "action": "TAKE_TRADE" if market["confidence"] >= 80 else "WAIT",
        "side": market["side"],
        "confidence": market["confidence"],
        "quality": "HIGH" if market["confidence"] >= 85 else "STANDARD",
        "strategy": market["activeStrategy"],
        "selectedStrategy": {"name": market["activeStrategy"]},
        "reasons": why,
        "sl": round(market["price"] - 17.6, 2) if bull else round(market["price"] + 17.6, 2),
        "tp1": round(market["price"] + 10.5, 2) if bull else round(market["price"] - 10.5, 2),
        "tp2": round(market["price"] + 17.5, 2) if bull else round(market["price"] - 17.5, 2),
        "tp3": round(market["price"] + 26.5, 2) if bull else round(market["price"] - 26.5, 2),
    }
    return {
        "account": account,
        "market": market,
        "decision": decision,
        "trades": t,
        "why": why,
        "equityCurve": a["equityCurve"],
        "topStrategies": a["topStrategies"],
        "source": "demo",
    }
