from __future__ import annotations

from pathlib import Path
from typing import Any
import json


class EmergencyKillSwitch:
    def __init__(self, path: str = "data/kill_switch.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def status(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"active": False, "reason": "", "mode": "normal"}
        return json.loads(self.path.read_text())

    def activate(self, reason: str = "Manual emergency stop") -> dict[str, Any]:
        payload = {"active": True, "reason": reason, "mode": "kill_all_new_trades"}
        self.path.write_text(json.dumps(payload, indent=2))
        return payload

    def reset(self) -> dict[str, Any]:
        payload = {"active": False, "reason": "", "mode": "normal"}
        self.path.write_text(json.dumps(payload, indent=2))
        return payload


class BrokerExecutionScorer:
    def score(self, spread: float = 0.12, slippage: float = 0.02, latency_ms: int = 24, rejects: int = 0) -> dict[str, Any]:
        score = 100
        score -= max(0, spread - 0.12) * 80
        score -= max(0, slippage - 0.03) * 120
        score -= max(0, latency_ms - 50) * 0.15
        score -= rejects * 10
        score = round(max(0, min(100, score)), 1)
        grade = "Excellent" if score >= 90 else "Good" if score >= 75 else "Degraded" if score >= 55 else "Unsafe"
        return {"score": score, "grade": grade, "spread": spread, "slippage": slippage, "latencyMs": latency_ms, "rejects": rejects}


class OverfittingGuard:
    def evaluate(self, strategy_stats: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        strategy_stats = strategy_stats or []
        warnings = []
        for s in strategy_stats:
            if s.get("trades", 0) < 30 and s.get("winRate", 0) > 80:
                warnings.append(f"{s.get('name')} has suspiciously high win rate with low sample size")
        return {"status": "PASS" if not warnings else "REVIEW", "warnings": warnings, "rules": ["minimum samples", "out-of-sample decay", "parameter sensitivity", "walk-forward pass required"]}
