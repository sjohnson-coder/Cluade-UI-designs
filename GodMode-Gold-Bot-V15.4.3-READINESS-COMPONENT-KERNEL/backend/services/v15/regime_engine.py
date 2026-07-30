from __future__ import annotations

import statistics
from typing import Any

from .contracts import clamp


class RegimeEngine:
    def assess(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        returns = [float(x) for x in snapshot.get("returns") or []]
        mean = statistics.fmean(returns) if returns else 0.0
        stdev = statistics.pstdev(returns) if len(returns) > 1 else 0.0
        atr = max(0.0, float(snapshot.get("atr", 0.0)))
        baseline = max(1e-9, float(snapshot.get("atr_baseline", atr or 1.0)))
        vol_ratio = atr / baseline
        adx = float(snapshot.get("adx", 0.0))
        news = clamp(snapshot.get("news_risk", 0.0))
        liquidity = clamp(snapshot.get("liquidity", 0.5))
        directional = min(1.0, abs(mean) / max(stdev, 1e-6))

        scores = {
            "news_driven": news,
            "strong_trend": clamp((adx - 20) / 25) * clamp(directional) * clamp(liquidity + 0.1),
            "weak_trend": clamp((adx - 12) / 20) * clamp(0.7 - directional / 3),
            "expansion": clamp((vol_ratio - 1.0) / 1.2),
            "compression": clamp((1.0 - vol_ratio) / 0.55),
            "mean_reversion": clamp((22 - adx) / 22) * clamp(1.0 - directional),
            "low_liquidity": clamp(1.0 - liquidity),
        }
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        primary, top_score = ordered[0]
        runner_up = ordered[1][1] if len(ordered) > 1 else 0.0
        # V15.0.8 — regime confidence was previously just the winning regime's RAW SCORE.
        # That is not a confidence. With scores {strong_trend: 0.90, mean_reversion: 0.88}
        # the old code reported 90% confident while the classifier was, in reality, nearly
        # coin-flipping between a trend read and its exact opposite. Because this value is
        # weighted 40% into the forecast's uncertainty term, an inflated regime confidence
        # propagated straight through to an inflated headline confidence.
        # Confidence is now the MARGIN over the runner-up: decisive only when the winner
        # genuinely separates from the alternatives.
        margin = clamp((top_score - runner_up) / max(top_score, 1e-6)) if top_score > 0 else 0.0
        confidence = clamp(top_score * (0.35 + 0.65 * margin))
        contested = margin < 0.20 and top_score > 0.0
        if top_score < 0.25 or contested:
            primary, confidence = "transition", min(confidence, 0.35)
        suitability = {
            "trend_continuation": clamp(scores["strong_trend"] + 0.4 * scores["expansion"] - news * 0.3),
            "breakout": clamp(scores["compression"] * 0.45 + scores["expansion"] * 0.55 - news * 0.2),
            "mean_reversion": clamp(scores["mean_reversion"] - scores["strong_trend"] * 0.4),
            "no_trade": clamp(max(news, scores["low_liquidity"], 1.0 - confidence) * 0.8),
        }
        return {"primary": primary, "confidence": clamp(confidence), "top_score": clamp(top_score), "margin": clamp(margin), "contested": bool(contested), "scores": scores, "strategy_suitability": suitability, "volatility_ratio": vol_ratio, "directional_strength": directional}
