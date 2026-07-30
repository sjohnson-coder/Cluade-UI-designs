from __future__ import annotations

from typing import Any


class ExplainabilityEngine:
    def build(self, regime: dict[str, Any], forecast: dict[str, Any], exit_decision: dict[str, Any], burst: dict[str, Any]) -> dict[str, Any]:
        probs = forecast.get("probabilities", {})
        reasons = sorted(forecast.get("contributions", []), key=lambda x: abs(float(x.get("impact", 0))), reverse=True)
        summary = f"Regime {regime.get('primary')} ({regime.get('confidence', 0):.0%}); continuation {probs.get('continuation', 0):.0%}; exit policy {exit_decision.get('action')}; burst {'allowed' if burst.get('allowed') else 'blocked'}."
        return {"summary": summary, "reasons": reasons[:8], "confidence": forecast.get("confidence", 0), "uncertainty": forecast.get("uncertainty", 1), "exit_reason": exit_decision.get("reason"), "burst_blockers": burst.get("blocked_by", [])}
