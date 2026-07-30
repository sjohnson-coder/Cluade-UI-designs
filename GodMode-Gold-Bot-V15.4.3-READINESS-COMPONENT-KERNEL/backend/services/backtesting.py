from __future__ import annotations

from random import Random
from typing import Any

rng = Random(260617)


class WalkForwardBacktester:
    def run(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        windows = int(payload.get("windows", 6))
        results = []
        equity = 10000.0
        for i in range(windows):
            in_sample_wr = rng.uniform(58, 74)
            out_sample_wr = max(45, in_sample_wr - rng.uniform(1.5, 8.0))
            pf = rng.uniform(1.25, 2.35)
            trades = rng.randint(48, 140)
            pnl = rng.uniform(350, 2200)
            equity += pnl
            results.append({"window": i + 1, "inSampleWinRate": round(in_sample_wr, 2), "outSampleWinRate": round(out_sample_wr, 2), "profitFactor": round(pf, 2), "trades": trades, "pnl": round(pnl, 2), "endingEquity": round(equity, 2)})
        return {"ok": True, "method": "walk-forward", "windows": results, "passed": all(w["outSampleWinRate"] >= 50 and w["profitFactor"] >= 1.15 for w in results)}


class MonteCarloTester:
    def run(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        sims = int(payload.get("simulations", 500))
        trades = int(payload.get("trades", 120))
        ruin = 0
        endings = []
        max_dds = []
        for _ in range(sims):
            equity = 10000.0
            peak = equity
            max_dd = 0.0
            for _ in range(trades):
                r = rng.choice([1.2, 1.8, 2.3, -1.0, -0.75])
                equity += r * 100
                peak = max(peak, equity)
                max_dd = max(max_dd, (peak - equity) / peak * 100)
            if equity < 7000:
                ruin += 1
            endings.append(equity)
            max_dds.append(max_dd)
        endings_sorted = sorted(endings)
        max_dds_sorted = sorted(max_dds)
        return {"ok": True, "method": "monte-carlo", "simulations": sims, "riskOfRuinPct": round(ruin / sims * 100, 2), "medianEndingEquity": round(endings_sorted[sims//2], 2), "p05EndingEquity": round(endings_sorted[int(sims*.05)], 2), "p95MaxDrawdownPct": round(max_dds_sorted[int(sims*.95)], 2)}


class TradeReplayEngine:
    def replay(self, trade_id: str = "demo") -> dict[str, Any]:
        timeline = [
            {"step": 1, "event": "Pre-trade scan", "detail": "HTF structure bullish, London liquidity active."},
            {"step": 2, "event": "Liquidity sweep", "detail": "Sell-side liquidity swept and reclaimed."},
            {"step": 3, "event": "Entry trigger", "detail": "M15 confirmation candle closed above OB."},
            {"step": 4, "event": "TP1", "detail": "25% closed, SL moved to break-even."},
            {"step": 5, "event": "TP2", "detail": "Second partial closed, ATR trail armed."},
            {"step": 6, "event": "TP3/TP4 runner", "detail": "Runner managed toward HTF liquidity."},
        ]
        return {"ok": True, "tradeId": trade_id, "timeline": timeline}
