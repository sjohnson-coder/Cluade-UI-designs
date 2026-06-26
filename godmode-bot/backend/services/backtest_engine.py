"""Cost-aware backtest + walk-forward harness, and factor-weight optimizer.

This replays the REAL GodMode decision engine bar-by-bar over historical M15 candles
(resampling H1/H4/D1 on the fly, lookahead-free), simulates each taken trade forward
with the engine's own TP1-TP4 + break-even plan, and charges spread + commission on
every trade. It produces honest per-strategy edge metrics (expectancy in R, profit
factor, win rate, max drawdown, sample size) plus walk-forward out-of-sample folds,
and a KEEP / MARGINAL / DISABLE verdict per strategy.

The weight optimizer measures how predictive each confidence FACTOR actually is of
realised, cost-adjusted R (Pearson correlation on in-sample trades), turns that into
per-factor weights, and validates the result on a held-out out-of-sample slice — so
the engine's confidence stops relying on hand-set numbers and starts reflecting what
actually worked. Pure standard library; no numpy/scipy required.

Honest assumptions (documented):
  • Entry at the signal bar's close; SL-before-TP within a bar (conservative).
  • Historical news is not modeled — the news gate is bypassed in backtest.
  • Spread/commission are user-supplied constants (set them to your broker's real
    XAUUSD costs for a faithful result).
"""
from __future__ import annotations

import bisect
import math
from datetime import datetime, timezone
from typing import Any


# ── candle math ───────────────────────────────────────────────────────────────
def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1 - alpha) * out[-1])
    return out


def _attach_emas(candles: list[dict[str, Any]]) -> None:
    closes = [float(c["close"]) for c in candles]
    e20, e50 = _ema(closes, 20), _ema(closes, 50)
    e200 = _ema(closes, min(200, max(2, len(closes))))
    for i, c in enumerate(candles):
        c["ema20"] = round(e20[i], 5)
        c["ema50"] = round(e50[i], 5)
        c["ema200"] = round(e200[i], 5)


def _resample(candles: list[dict[str, Any]], tf_sec: int) -> tuple[list[dict[str, Any]], list[int]]:
    """Resample ascending M15 candles into closed higher-timeframe buckets."""
    buckets: dict[int, dict[str, Any]] = {}
    order: list[int] = []
    for c in candles:
        b = (int(c["time"]) // tf_sec) * tf_sec
        if b not in buckets:
            buckets[b] = {"time": b, "open": float(c["open"]), "high": float(c["high"]),
                          "low": float(c["low"]), "close": float(c["close"]), "tickVolume": float(c.get("tickVolume", 0))}
            order.append(b)
        else:
            bk = buckets[b]
            bk["high"] = max(bk["high"], float(c["high"]))
            bk["low"] = min(bk["low"], float(c["low"]))
            bk["close"] = float(c["close"])
            bk["tickVolume"] += float(c.get("tickVolume", 0))
    out = [buckets[b] for b in order]
    _attach_emas(out)
    close_times = [bk["time"] + tf_sec for bk in out]  # a bucket is usable once closed
    return out, close_times


def _session_label(epoch: float) -> str:
    h = datetime.fromtimestamp(int(epoch), timezone.utc).hour
    if 7 <= h < 12:
        return "London"
    if 12 <= h < 17:
        return "London / New York"
    if 17 <= h < 22:
        return "New York"
    return "Asia"


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


# ── trade simulation ────────────────────────────────────────────────────────--
def _simulate(candles: list[dict[str, Any]], entry_i: int, dec: dict[str, Any],
              spread: float, commission: float, max_hold: int) -> dict[str, Any] | None:
    plan = dec.get("tradePlan", {})
    side = str(dec.get("side", "")).upper()
    entry = float(candles[entry_i]["close"])
    sl = float(plan.get("sl") or 0)
    tps = [float(plan.get(k) or 0) for k in ("tp1", "tp2", "tp3", "tp4")]
    risk = abs(entry - sl)
    if risk <= 0 or side not in ("BUY", "SELL"):
        return None
    cost_R = (spread + commission) / risk  # round-trip cost expressed in R
    portion = 0.25
    realized = 0.0
    remaining = 1.0
    filled = 0
    sl_cur = sl
    n = len(candles)
    exit_i = min(entry_i + max_hold, n - 1)
    for j in range(entry_i + 1, min(entry_i + 1 + max_hold, n)):
        hi, lo = float(candles[j]["high"]), float(candles[j]["low"])
        if side == "BUY":
            if lo <= sl_cur:  # conservative: stop before any TP in the same bar
                realized += remaining * ((sl_cur - entry) / risk)
                remaining = 0.0; exit_i = j; break
            while filled < 4 and hi >= tps[filled] and tps[filled] > 0:
                realized += portion * ((tps[filled] - entry) / risk)
                remaining -= portion; filled += 1
                if filled >= 1:
                    sl_cur = max(sl_cur, entry)  # break-even after TP1
        else:
            if hi >= sl_cur:
                realized += remaining * ((entry - sl_cur) / risk)
                remaining = 0.0; exit_i = j; break
            while filled < 4 and lo <= tps[filled] and tps[filled] > 0:
                realized += portion * ((entry - tps[filled]) / risk)
                remaining -= portion; filled += 1
                if filled >= 1:
                    sl_cur = min(sl_cur, entry)
        if remaining <= 1e-9:
            exit_i = j; break
    else:
        exit_i = min(entry_i + max_hold, n - 1)
    if remaining > 1e-9:  # mark remainder to market at exit close
        last = float(candles[exit_i]["close"])
        realized += remaining * (((last - entry) if side == "BUY" else (entry - last)) / risk)
    return {"netR": round(realized - cost_R, 4), "grossR": round(realized, 4),
            "exitIndex": exit_i, "holdBars": exit_i - entry_i, "filledTPs": filled}


# ── metrics ────────────────────────────────────────────────────────────────--
def _metrics(rs: list[float]) -> dict[str, Any]:
    n = len(rs)
    if n == 0:
        return {"trades": 0, "winRate": 0.0, "expectancyR": 0.0, "totalR": 0.0,
                "profitFactor": 0.0, "maxDrawdownR": 0.0, "sharpe": 0.0}
    wins = [r for r in rs if r > 0]
    gross_w = sum(wins)
    gross_l = abs(sum(r for r in rs if r < 0))
    mean = sum(rs) / n
    var = sum((r - mean) ** 2 for r in rs) / n
    std = math.sqrt(var)
    equity = 0.0; peak = 0.0; max_dd = 0.0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {
        "trades": n,
        "winRate": round(len(wins) / n * 100, 1),
        "expectancyR": round(mean, 3),
        "totalR": round(sum(rs), 2),
        "profitFactor": round(gross_w / gross_l, 2) if gross_l else (999.0 if gross_w else 0.0),
        "maxDrawdownR": round(max_dd, 2),
        "sharpe": round(mean / std, 2) if std else 0.0,
    }


def _verdict(m: dict[str, Any], min_sample: int) -> str:
    if m["trades"] < min_sample:
        return "FLAG_LOW_SAMPLE"
    if m["expectancyR"] >= 0.05 and m["profitFactor"] >= 1.10:
        return "KEEP"
    if m["expectancyR"] >= -0.02:
        return "MARGINAL"
    return "DISABLE"


class CostAwareBacktester:
    def _collect(self, candles: list[dict[str, Any]], engine: Any, strategies: list[dict[str, Any]],
                 p: dict[str, Any], progress: Any = None) -> list[dict[str, Any]]:
        candles = sorted(candles, key=lambda c: int(c["time"]))
        for c in candles:  # normalise types
            for k in ("open", "high", "low", "close"):
                c[k] = float(c[k])
        if progress:
            progress(0.02, f"Preparing {len(candles)} candles (EMAs + H1/H4/D1 resample)…")
        _attach_emas(candles)
        h1, h1ct = _resample(candles, 3600)
        h4, h4ct = _resample(candles, 14400)
        d1, d1ct = _resample(candles, 86400)
        n = len(candles)
        warmup = int(p.get("warmup", 250))
        lookback = int(p.get("lookback", 400))
        htf_lb = int(p.get("htfLookback", 200))
        max_hold = int(p.get("maxHoldBars", 96))
        spread = float(p.get("spread", 0.20))
        commission = float(p.get("commission", 0.0))
        allowed = p.get("allowedSessions") or ["Asia", "London", "London / New York", "New York"]
        trades: list[dict[str, Any]] = []
        i = warmup
        span = max(1, n - 1 - warmup)
        step = max(1, span // 100)   # ~100 progress ticks across the replay
        while i < n - 1:
            if progress and (i - warmup) % step == 0:
                frac = 0.05 + 0.9 * (i - warmup) / span   # 5%..95% during the replay
                progress(frac, f"Replaying bar {i - warmup:,} / {span:,} · {len(trades)} trades so far")
            t = int(candles[i]["time"])
            k1 = bisect.bisect_right(h1ct, t)
            k4 = bisect.bisect_right(h4ct, t)
            kd = bisect.bisect_right(d1ct, t)
            market = {
                "symbol": p.get("symbol", "XAUUSD"), "timeframe": "M15",
                "price": candles[i]["close"], "spread": spread, "side": "WAIT",
                "candles": candles[max(0, i - lookback + 1): i + 1],
                "h1Candles": h1[max(0, k1 - htf_lb): k1],
                "h4Candles": h4[max(0, k4 - htf_lb): k4],
                "d1Candles": d1[max(0, kd - htf_lb): kd],
                "asOfTime": t, "session": _session_label(t), "backtest": True,
                "allowedSessions": allowed, "respectAllowedSessions": True,
            }
            try:
                dec = engine.evaluate(market, strategies, {})
            except Exception:
                i += 1; continue
            if dec.get("action") == "TAKE_TRADE" and str(dec.get("side")) in ("BUY", "SELL"):
                sim = _simulate(candles, i, dec, spread, commission, max_hold)
                if sim:
                    trades.append({
                        "strategy": (dec.get("selectedStrategy", {}) or {}).get("name", "GodMode Bot"),
                        "side": dec["side"], "confidence": float(dec.get("confidence", 0) or 0),
                        "entryTime": t, "entryIndex": i, "exitIndex": sim["exitIndex"],
                        "netR": sim["netR"], "win": sim["netR"] > 0,
                        "factors": {f["name"]: float(f["score"]) for f in dec.get("factors", [])},
                    })
                    i = max(sim["exitIndex"], i + 1)  # single position at a time
                    continue
            i += 1
        return trades

    def run(self, candles: list[dict[str, Any]], engine: Any, strategies: list[dict[str, Any]],
            params: dict[str, Any] | None = None, progress: Any = None) -> dict[str, Any]:
        p = params or {}
        if not candles or len(candles) < int(p.get("warmup", 250)) + 50:
            return {"ok": False, "message": "Not enough candles to backtest.", "candles": len(candles or [])}
        prior = dict(engine.factor_weights)  # don't let live learned weights leak into the test
        engine.reset_factor_weights()
        try:
            trades = self._collect(candles, engine, strategies, p, progress=progress)
        finally:
            engine.set_factor_weights(prior)
        if progress:
            progress(0.97, "Computing metrics, walk-forward folds & verdict…")
        min_sample = int(p.get("minSample", 20))
        folds = int(p.get("folds", 4))
        by_strat: dict[str, list[float]] = {}
        for tr in trades:
            by_strat.setdefault(tr["strategy"], []).append(tr["netR"])
        strat_rows = []
        for name, rs in sorted(by_strat.items(), key=lambda kv: sum(kv[1]), reverse=True):
            m = _metrics(rs)
            m["strategy"] = name
            m["verdict"] = _verdict(m, min_sample)
            strat_rows.append(m)
        overall = _metrics([tr["netR"] for tr in trades])
        # walk-forward folds (chronological)
        wf = []
        if trades:
            size = max(1, len(trades) // max(folds, 1))
            for f in range(folds):
                seg = trades[f * size: (f + 1) * size] if f < folds - 1 else trades[f * size:]
                if seg:
                    fm = _metrics([t["netR"] for t in seg])
                    fm["fold"] = f + 1
                    wf.append(fm)
        oos_consistency = round(sum(1 for f in wf if f["expectancyR"] > 0) / len(wf) * 100, 0) if wf else 0
        # Plain-English verdict: is this edge worth trading / optimizing?
        exp = overall["expectancyR"]; pf = overall["profitFactor"]; tn = overall["trades"]
        if tn < 30:
            assessment = {"edge": "insufficient", "worthLive": False,
                          "message": f"Only {tn} trades — not enough to judge. Backtest more bars."}
        elif pf >= 1.30 and exp >= 0.10 and oos_consistency >= 70:
            assessment = {"edge": "strong", "worthLive": True,
                          "message": f"Real edge after costs (PF {pf}, {exp:+.3f}R/trade, {oos_consistency:.0f}% folds positive). Worth trading live; optimizing weights may sharpen it."}
        elif pf >= 1.10 and exp >= 0.03 and oos_consistency >= 50:
            assessment = {"edge": "marginal", "worthLive": False,
                          "message": f"Marginal edge (PF {pf}, {exp:+.3f}R/trade). Barely above costs and folds are inconsistent — refine (disable weak strategies, tighten filters) before sizing up. Optimizing may help but verify out-of-sample."}
        else:
            assessment = {"edge": "none", "worthLive": False,
                          "message": f"No reliable edge after costs (PF {pf}, {exp:+.3f}R/trade). Do NOT trade live as-is. Disable the DISABLE-verdict strategies and re-test; the issue is strategy quality, not weights."}
        candle_span = ""
        if candles:
            a = datetime.fromtimestamp(int(candles[0]["time"]), timezone.utc).strftime("%Y-%m-%d")
            b = datetime.fromtimestamp(int(candles[-1]["time"]), timezone.utc).strftime("%Y-%m-%d")
            candle_span = f"{a} → {b}"
        return {
            "ok": True,
            "method": "cost-aware walk-forward replay",
            "candles": len(candles),
            "span": candle_span,
            "costs": {"spreadPrice": float(p.get("spread", 0.20)), "commissionPrice": float(p.get("commission", 0.0))},
            "totalTrades": len(trades),
            "overall": overall,
            "assessment": assessment,
            "strategies": strat_rows,
            "walkForward": wf,
            "oosConsistencyPct": oos_consistency,
            "assumptions": ["Entry at signal-bar close", "SL-before-TP within a bar (conservative)",
                            "Historical news not modeled", "TP1-TP4 25% partials + break-even after TP1"],
        }

    def optimize_weights(self, candles: list[dict[str, Any]], engine: Any, strategies: list[dict[str, Any]],
                         params: dict[str, Any] | None = None) -> dict[str, Any]:
        p = params or {}
        prior = dict(engine.factor_weights)
        engine.reset_factor_weights()
        try:
            trades = self._collect(candles, engine, strategies, p)
        finally:
            engine.set_factor_weights(prior)
        if len(trades) < int(p.get("minSampleForFit", 40)):
            return {"ok": False, "message": f"Need >= {int(p.get('minSampleForFit', 40))} backtested trades to fit weights; got {len(trades)}.",
                    "trades": len(trades)}
        # default weights captured from the engine's factor list
        default_w: dict[str, float] = {}
        for tr in trades:
            for name in tr["factors"]:
                default_w.setdefault(name, 1.0)
        # use the engine's real defaults if exposed via a sample evaluation
        names = list(default_w.keys())
        split = int(len(trades) * 0.7)
        ins, oos = trades[:split], trades[split:]

        # Anti-overfit shrinkage: a learned weight is blended TOWARD neutral (1.0) by
        # ``learningRate`` (0.5 default) — so even an OOS-approved fit only moves a weight
        # halfway to its in-sample optimum. This stops a noisy correlation on a small sample
        # from swinging a factor's influence too hard (Bayesian shrinkage toward the prior).
        shrink = max(0.0, min(1.0, float(p.get("learningRate", 0.5))))
        learned: dict[str, float] = {}
        contributions = []
        for name in names:
            xs = [t["factors"].get(name, 50.0) for t in ins]
            ys = [t["netR"] for t in ins]
            corr = _pearson(xs, ys)
            w_full = 1.0 + 2.0 * corr                       # raw in-sample fit
            w = max(0.3, min(1.8, round(1.0 + shrink * (w_full - 1.0), 3)))  # shrink toward neutral
            learned[name] = w
            contributions.append({"factor": name, "correlation": round(corr, 3), "weight": w, "rawWeight": round(max(0.3, min(1.8, w_full)), 3)})
        contributions.sort(key=lambda x: x["correlation"], reverse=True)

        def score(trade, weights):
            num = sum(weights.get(k, 1.0) * v for k, v in trade["factors"].items())
            den = sum(weights.get(k, 1.0) for k in trade["factors"]) or 1.0
            return num / den

        def oos_quality(weights):
            scored = sorted(oos, key=lambda t: score(t, weights), reverse=True)
            top = scored[: max(1, len(scored) // 4)]
            top_r = sum(t["netR"] for t in top) / len(top)
            corr = _pearson([score(t, weights) for t in oos], [t["netR"] for t in oos])
            return {"topQuartileMeanR": round(top_r, 3), "scoreOutcomeCorr": round(corr, 3)}

        before = oos_quality(default_w)
        after = oos_quality(learned)
        improved = after["scoreOutcomeCorr"] >= before["scoreOutcomeCorr"] and after["topQuartileMeanR"] >= before["topQuartileMeanR"] - 0.01
        return {
            "ok": True,
            "trainedOn": len(ins), "validatedOn": len(oos),
            "factorContributions": contributions,
            "learnedWeights": learned,
            "outOfSample": {"before": before, "after": after, "improved": improved},
            "recommendation": "apply" if improved else "hold — out-of-sample did not improve; collect more trades",
        }
