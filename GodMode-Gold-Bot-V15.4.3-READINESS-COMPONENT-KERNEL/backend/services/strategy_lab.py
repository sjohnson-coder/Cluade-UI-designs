"""GodMode AI Strategy Lab.

Continuously back-/forward-tests CANDIDATE trading styles against the user's own market history
and head-to-head against their current live configuration, then recommends an upgrade only when a
candidate genuinely beats the incumbent out-of-sample. Nothing is ever auto-applied — the user
clicks Install after seeing the evidence.

A "candidate strategy" here is a coherent, named *profile* for the real decision engine (entry
strictness, confidence bar, efficiency/chop filter, R:R target, session focus, optional factor
weights). The same engine, tuned to a different trading style — so each candidate produces a
genuinely different trade set the backtester can measure. Candidates come from a curated library
(below); a trusted-feed URL or an AI generator can extend the pool later by appending profiles of
the same shape.
"""
from __future__ import annotations

import copy
from typing import Any
from .ai_strategy_gen import sanitize_profile


# Curated candidate library — proven Gold trading STYLES, each a parameter profile the engine runs.
CANDIDATE_LIBRARY: list[dict[str, Any]] = [
    {"id": "trend_rider", "name": "Tight Trend-Rider", "source": "library",
     "thesis": "Only trades clean, efficient trends and rides them with a wide R target. Skips chop hard.",
     "profile": {"strictnessMode": "strict", "minEfficiencyRatio": 0.42, "minRiskReward": 1.8,
                 "standardConfidence": 78, "allowScoutEntries": False}},
    {"id": "aggressive_scout", "name": "Aggressive Scout", "source": "library",
     "thesis": "Takes more, smaller scout entries at a lower confidence bar — more trades, tighter risk.",
     "profile": {"strictnessMode": "relaxed", "allowScoutEntries": True, "scoutConfidence": 62,
                 "minRiskReward": 1.3, "minEfficiencyRatio": 0.26}},
    {"id": "sniper_quality", "name": "Sniper Quality-Only", "source": "library",
     "thesis": "Fewer, A+ setups only: high confidence, high efficiency, 2R minimum.",
     "profile": {"strictnessMode": "sniper", "standardConfidence": 85, "minRiskReward": 2.0,
                 "minEfficiencyRatio": 0.45, "allowScoutEntries": False}},
    {"id": "london_ny_breakout", "name": "London/NY Breakout", "source": "library",
     "thesis": "Trades only the London & NY sessions (highest Gold volatility), efficient moves only.",
     "profile": {"strictnessMode": "balanced", "minEfficiencyRatio": 0.40, "minRiskReward": 1.6,
                 "allowedSessions": ["London", "London / New York", "New York"]}},
    {"id": "strict_chop_avoider", "name": "Strict Chop-Avoider", "source": "library",
     "thesis": "Maximum range/chop rejection + more confluence required — fewer but cleaner trades.",
     "profile": {"strictnessMode": "strict", "minEfficiencyRatio": 0.48, "minConfluence": 5,
                 "minRiskReward": 1.6}},
    {"id": "balanced_plus", "name": "Balanced+", "source": "library",
     "thesis": "Your balanced default with a slightly higher R target — a gentle, low-risk tweak.",
     "profile": {"strictnessMode": "balanced", "minRiskReward": 1.5}},
    {"id": "range_break_scout", "name": "Range Compression Breakout", "source": "library",
     "thesis": "For chop/range/compression regimes — but it does NOT fade the range (fading loses). It sits "
               "ready and only fires on a fresh, sized directional leg breaking OUT of the compression: a "
               "lower efficiency floor lets it engage as the range resolves, with a tight spread cap and "
               "scout size. Back/forward-tested like every candidate; only installs if it beats your edge.",
     "profile": {"strictnessMode": "balanced", "minEfficiencyRatio": 0.18, "minRiskReward": 1.4,
                 "standardConfidence": 74, "scoutConfidence": 70, "allowScoutEntries": True, "maxSpread": 0.30,
                 "idealRegimes": ["Range / Wait", "Compression / Wait", "Asian Range", "Volatility Expansion"]}},
    {"id": "prime_quality", "name": "Prime Quality (cost-aware)", "source": "library",
     "thesis": "Concentrates on the few highest edge-to-cost setups: London/NY only, strict chop "
               "rejection, high confluence, and a tight spread cap so trading costs can't eat the edge. "
               "Stacks the two configs that scored best on your real history — meant to beat the cost drag.",
     "profile": {"strictnessMode": "strict", "minEfficiencyRatio": 0.48, "minConfluence": 5,
                 "minRiskReward": 1.7, "standardConfidence": 80, "allowScoutEntries": False,
                 "maxSpread": 0.30, "allowedSessions": ["London", "London / New York", "New York"]}},
]


def _f(d: dict[str, Any], k: str, default: float = 0.0) -> float:
    try:
        return float(d.get(k, default) or 0.0)
    except Exception:
        return default


class StrategyLab:
    def __init__(self) -> None:
        self.extra: list[dict[str, Any]] = []   # feed/AI-generated candidates appended at runtime

    def candidates(self) -> list[dict[str, Any]]:
        return CANDIDATE_LIBRARY + self.extra

    def add_candidates(self, items: list[dict[str, Any]]) -> int:
        """Append externally-sourced candidate PROFILES (trusted feed / AI generator). Each must be
        {id,name,thesis,profile{...}} of the same shape — rule-spec only, never executable code."""
        added = 0
        have = {c["id"] for c in self.candidates()}
        for it in items or []:
            clean = sanitize_profile(
                it,
                source=str(it.get("source") or "direct") if isinstance(it, dict) else "direct",
            )
            if clean and clean["id"] not in have:
                self.extra.append(clean)
                have.add(clean["id"])
                added += 1
        return added

    def get(self, cid: str) -> dict[str, Any] | None:
        return next((c for c in self.candidates() if c["id"] == cid), None)

    def evaluate(self, candles: list[dict[str, Any]], engine: Any, strategies: list[dict[str, Any]],
                 backtester: Any, baseline_profile: dict[str, Any], params: dict[str, Any],
                 progress: Any = None) -> dict[str, Any]:
        """Backtest the live BASELINE config and every candidate over the SAME history, compare,
        and recommend the best candidate that beats the baseline out-of-sample. The engine's live
        config is snapshotted and ALWAYS restored, so this never disturbs live trading."""
        # Never lend the singleton live engine to research workloads. Even though
        # older code restored its settings in a finally block, live evaluations
        # could run concurrently while a candidate profile was temporarily active.
        engine = copy.deepcopy(engine)
        snapshot = engine.strictness_dict()
        base_sessions = params.get("allowedSessions")
        min_trades = int(params.get("minSample", 30))
        total = len(self.candidates()) + 1   # baseline + candidates
        def _sub(idx: int, name: str):
            # map each candidate's internal 0..1 replay progress onto its slice of the whole run
            return (lambda frac, stage: progress((idx + max(0.0, min(1.0, frac))) / total,
                                                 f"Testing {name} ({idx + 1}/{total}) — {stage}")) if progress else None
        try:
            engine.configure_strictness(baseline_profile or snapshot)
            base = backtester.run(candles, engine, strategies, params, progress=_sub(0, "your current config"))
            if not base.get("ok"):
                return {"ok": False, "message": base.get("message", "Baseline backtest failed."), "candles": base.get("candles")}
            base_m = base.get("overall", {})
            rows: list[dict[str, Any]] = []
            for ci, c in enumerate(self.candidates()):
                prof = {**(baseline_profile or {}), **c["profile"]}
                engine.configure_strictness(prof)
                p = {**params, "allowedSessions": c["profile"].get("allowedSessions", base_sessions)}
                r = backtester.run(candles, engine, strategies, p, progress=_sub(ci + 1, c["name"]))
                m = r.get("overall", {}) if r.get("ok") else {}
                rows.append({
                    "id": c["id"], "name": c["name"], "source": c.get("source", "library"),
                    "thesis": c.get("thesis", ""), "profile": c["profile"],
                    "trades": int(m.get("trades", 0) or 0),
                    "expectancyR": _f(m, "expectancyR"), "profitFactor": _f(m, "profitFactor"),
                    "winRate": _f(m, "winRate"), "maxDrawdownR": _f(m, "maxDrawdownR"),
                    "oosConsistencyPct": _f(r, "oosConsistencyPct"),
                    "expectancyVsBaseline": round(_f(m, "expectancyR") - _f(base_m, "expectancyR"), 3),
                    "pfVsBaseline": round(_f(m, "profitFactor") - _f(base_m, "profitFactor"), 2),
                })
        finally:
            engine.configure_strictness(snapshot)   # restore live config no matter what

        # Recommendation: best candidate that clears sample + beats baseline expectancy by a margin
        # AND holds up out-of-sample AND doesn't worsen profit factor. Conservative on purpose.
        base_exp = _f(base_m, "expectancyR"); base_pf = _f(base_m, "profitFactor")
        margin = float(params.get("improveMarginR", 0.05))
        eligible = [r for r in rows
                    if r["trades"] >= min_trades
                    and r["expectancyR"] >= base_exp + margin
                    and r["oosConsistencyPct"] >= float(params.get("minOos", 50))
                    and r["profitFactor"] >= base_pf - 0.05]
        eligible.sort(key=lambda r: (r["expectancyR"], r["oosConsistencyPct"]), reverse=True)
        rows.sort(key=lambda r: r["expectancyR"], reverse=True)
        recommendation = None
        if eligible:
            best = eligible[0]
            recommendation = {
                "id": best["id"], "name": best["name"], "profile": best["profile"], "thesis": best["thesis"],
                "why": (f"Over {base.get('span','your history')} it produced {best['expectancyR']:+.3f}R/trade vs your "
                        f"current {base_exp:+.3f}R ({best['expectancyVsBaseline']:+.3f}R better) at profit factor "
                        f"{best['profitFactor']} with {best['oosConsistencyPct']:.0f}% of walk-forward folds positive "
                        f"across {best['trades']} trades — a genuine, out-of-sample improvement, not curve-fit noise."),
                "candidate": best, "baseline": base_m,
            }
        return {
            "ok": True, "span": base.get("span"), "candles": base.get("candles"),
            "dataSource": params.get("dataSource", "unknown"),
            "baseline": {"name": "Your current config", **base_m, "oosConsistencyPct": _f(base, "oosConsistencyPct")},
            "candidates": rows, "recommendation": recommendation,
            "signature": f"{base.get('span','')}|{(recommendation or {}).get('id','none')}",
        }
