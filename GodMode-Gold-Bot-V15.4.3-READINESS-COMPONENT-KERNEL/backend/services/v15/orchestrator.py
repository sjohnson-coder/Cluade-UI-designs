from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from .broker_engine import BrokerIntelligence
from .burst_engine import BurstIntelligence
from .exit_engine import AdaptiveExitEngine
from .explainability import ExplainabilityEngine
from .external_context import FreeExternalContext
from .governance import ModelGovernance
from .missed_opportunity import MissedOpportunityTracker
from .probability_engine import ProbabilityEngine
from .regime_engine import RegimeEngine
from .runtime_state import RuntimeStateManager

VERSION = "15.4.3"
BUILD_ID = "V15.4.3-READINESS-COMPONENT-KERNEL"


class GodModeV15Orchestrator:
    def __init__(self, data_dir: Path):
        data_dir = Path(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        self.state = RuntimeStateManager(data_dir / "v15_runtime_state.json")
        self.regime = RegimeEngine()
        self.broker = BrokerIntelligence()
        self.probability = ProbabilityEngine(data_dir / "v15_probability_calibration.json")
        self.missed = MissedOpportunityTracker(data_dir / "v15_missed_opportunities.jsonl")
        self.exit = AdaptiveExitEngine()
        self.burst = BurstIntelligence()
        self.external = FreeExternalContext(data_dir / "v15_external_context.json")
        self.governance = ModelGovernance(data_dir / "v15_governance.json", data_dir / "model_artifacts")
        self.explainability = ExplainabilityEngine()
        self.last_report: dict[str, Any] | None = None
        self._reports: dict[str, dict[str, Any]] = {}
        attribution = self.state.snapshot(public=False)["state"].get("calibration_attribution") or {}
        self.unattributed_outcomes = int(attribution.get("unattributed_outcomes", 0))
        persisted_reports = attribution.get("reports") or {}
        if isinstance(persisted_reports, dict):
            self._reports = {str(k): dict(v) for k, v in persisted_reports.items() if isinstance(v, dict)}
        snap = self.state.snapshot(public=False)["state"].get("intelligence")
        if isinstance(snap, dict) and snap.get("decision_id"):
            self.last_report = snap

    def evaluate(self, payload: dict[str, Any], source: str = "api") -> dict[str, Any]:
        errors: list[str] = []
        external_context = self.external.cached()
        market = dict(payload.get("market") or {})
        market["news_risk"] = max(float(market.get("news_risk", 0) or 0), float(external_context.get("risk_bias", 0) or 0))
        try:
            regime = self.regime.assess(market)
        except Exception as exc:
            regime = {"primary": "unknown", "confidence": 0.0, "scores": {}}
            errors.append(f"regime:{exc}")
        try:
            broker = self.broker.update(payload.get("broker") or {})
        except Exception as exc:
            broker = {"quality": 0.5, "samples": 0, "uncertainty": 1.0, "telemetry_available": False}
            errors.append(f"broker:{exc}")
        try:
            forecast = self.probability.forecast(payload.get("features") or {}, regime, broker, external_context)
        except Exception as exc:
            forecast = {"probabilities": {}, "confidence": 0.0, "uncertainty": 1.0, "contributions": [], "score_type": "unavailable"}
            errors.append(f"forecast:{exc}")
        probs = forecast.get("probabilities", {})
        position = dict(payload.get("position") or {})
        position.setdefault("recovery_probability", probs.get("recovery", 0.5))
        position.setdefault("continuation_probability", probs.get("continuation", 0.5))
        position.setdefault("invalidation_probability", probs.get("invalidation", 0.5))
        exit_decision = self.exit.decide(position)
        burst_input = dict(payload.get("burst") or {})
        burst_input.setdefault("continuation_probability", probs.get("continuation", 0))
        burst_input.setdefault("burst_success_probability", probs.get("burst_success", 0))
        burst_input.setdefault("broker_quality", broker.get("quality", 0.5))
        burst_input.setdefault("news_risk", external_context.get("risk_bias", 0))
        burst_decision = self.burst.evaluate(burst_input)
        explanation = self.explainability.build(regime, forecast, exit_decision, burst_decision)
        required_missing = []
        if not market:
            required_missing.append("market")
        if not payload.get("features"):
            required_missing.append("features")
        if not broker.get("telemetry_available"):
            required_missing.append("broker_telemetry")
        errors.extend(f"missing:{x}" for x in required_missing)
        health_score = max(0.0, min(100.0, 100 - 12 * len(errors) - 22 * float(forecast.get("uncertainty", 1)) - 12 * float(broker.get("uncertainty", 1)) - 8 * float(external_context.get("uncertainty", 1))))
        report = {
            "version": VERSION, "build_id": BUILD_ID, "status": "shadow", "source": source,
            "decision_id": uuid.uuid4().hex, "generated_at": time.time(), "regime": regime,
            "broker": broker, "forecast": forecast, "exit": exit_decision, "burst": burst_decision,
            "external_context": external_context, "missed_opportunities": self.missed.summary(),
            "governance": self.governance.snapshot(), "calibration": self.probability.snapshot(),
            "calibrationProgress": {**self.probability.calibration_progress(), "unattributedOutcomes": self.unattributed_outcomes},
            "explanation": explanation, "health": {"score": health_score, "ok": health_score >= 60 and not required_missing, "errors": errors},
        }
        self.last_report = report
        self._reports[report["decision_id"]] = report
        if len(self._reports) > 500:
            oldest = sorted(self._reports.values(), key=lambda item: float(item.get("generated_at", 0)))[:-500]
            for item in oldest:
                self._reports.pop(str(item.get("decision_id") or ""), None)
        self.state.update("intelligence", report)
        # V15.2.7: _reports is NOT persisted here (removed). Writing up to 547KB of
        # _reports on every evaluate() call (~20/min = ~5GB/hr disk writes + deepcopy
        # on the hot entry path) was a measured write-amplification bug. _reports is
        # now persisted only in record_trade_outcome where it actually changes in a
        # way that needs to survive a restart.
        return report

    def record_trade_outcome(self, won: bool, decision_id: str | None = None, probabilities: dict[str, Any] | None = None) -> bool:
        report = self._reports.get(str(decision_id or "")) if decision_id else None
        if report is None and probabilities:
            report = {
                "decision_id": str(decision_id or "historical"),
                "generated_at": time.time(),
                "forecast": {"probabilities": dict(probabilities)},
            }
        if report is None:
            self.unattributed_outcomes += 1
            # Persist the counter only (not _reports - that stays hot-path-free).
            self.state.update("calibration_attribution", {
                "unattributed_outcomes": self.unattributed_outcomes,
            })
            return False
        if not report or time.time() - float(report.get("generated_at", 0)) > 6 * 3600:
            return False
        self.probability.record_trade_outcome(report, bool(won))
        self.state.update("calibration", self.probability.snapshot())
        if decision_id:
            self._reports.pop(str(decision_id), None)
        self.state.update("calibration_attribution", {
            "reports": self._reports,
            "unattributed_outcomes": self.unattributed_outcomes,
        })
        return True

    def overview(self) -> dict[str, Any]:
        if not self.last_report:
            return {"version": VERSION, "build_id": BUILD_ID, "status": "warming", "health": {"score": 25.0, "ok": False, "errors": ["No shadow evaluation has completed"]}, "missed_opportunities": self.missed.summary(), "governance": self.governance.snapshot(), "calibration": self.probability.snapshot(), "calibrationProgress": {**self.probability.calibration_progress(), "unattributedOutcomes": self.unattributed_outcomes}, "external_context": self.external.cached()}
        age = time.time() - float(self.last_report.get("generated_at", 0))
        report = dict(self.last_report)
        # Persisted shadow state can survive an upgrade. Never advertise the old
        # package identity from that cached report; runtime identity is authoritative.
        report["version"] = VERSION
        report["build_id"] = BUILD_ID
        if age > 90:
            report["status"] = "stale"
            report["health"] = dict(report.get("health") or {})
            report["health"]["ok"] = False
            report["health"]["score"] = min(float(report["health"].get("score", 0)), 45.0)
            report["health"].setdefault("errors", []).append(f"Shadow evaluation stale: {age:.0f}s")
        return report
