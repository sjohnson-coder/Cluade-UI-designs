import json
import math
import threading
from pathlib import Path

from services.v15.runtime_state import RuntimeStateManager
from services.v15.regime_engine import RegimeEngine
from services.v15.broker_engine import BrokerIntelligence
from services.v15.probability_engine import ProbabilityEngine
from services.v15.missed_opportunity import MissedOpportunityTracker
from services.v15.exit_engine import AdaptiveExitEngine
from services.v15.burst_engine import BurstIntelligence
from services.v15.external_context import FreeExternalContext
from services.v15.governance import ModelGovernance
from services.v15.orchestrator import GodModeV15Orchestrator


def test_runtime_state_is_monotonic_thread_safe_and_redacts_secrets(tmp_path: Path):
    manager = RuntimeStateManager(tmp_path / "state.json")
    revisions = []

    def worker(i: int):
        snap = manager.update("telegram", {"botToken": f"secret-{i}", "enabled": True})
        revisions.append(snap["revision"])

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert sorted(revisions) == list(range(1, 9))
    public = manager.snapshot(public=True)
    assert public["state"]["telegram"]["botToken"] == "***configured***"
    assert json.loads((tmp_path / "state.json").read_text())["revision"] == 8


def test_regime_and_broker_profiles_are_deterministic_and_bounded():
    regime = RegimeEngine().assess({
        "returns": [0.001, 0.0012, 0.0009, 0.0011, 0.0013],
        "atr": 2.4, "atr_baseline": 1.2, "adx": 35, "range_position": 0.82,
        "news_risk": 0.1, "liquidity": 0.9,
    })
    assert regime["primary"] in {"strong_trend", "expansion"}
    assert 0 <= regime["confidence"] <= 1

    broker = BrokerIntelligence(window=10)
    for _ in range(5):
        broker.update({"spread_points": 25, "slippage_points": 3, "latency_ms": 80, "filled": True, "session": "london"})
    profile = broker.profile("london")
    assert profile["quality"] > 0.5
    assert profile["samples"] == 5


def test_probability_engine_emits_all_horizons_calibrated_and_finite():
    engine = ProbabilityEngine()
    forecast = engine.forecast(
        {"trend": 0.8, "momentum": 0.7, "structure": 0.75, "extension": 0.3, "spread_quality": 0.9, "recovery_evidence": 0.55},
        {"primary": "strong_trend", "confidence": 0.8},
        {"quality": 0.85},
    )
    required = {"continuation", "reversal", "recovery", "tp_before_sl", "be_first", "fast_fail", "burst_success", "invalidation"}
    assert required.issubset(forecast["probabilities"])
    assert all(0 <= v <= 1 and math.isfinite(v) for v in forecast["probabilities"].values())
    assert forecast["expected_mfe_r"] >= 0
    assert forecast["expected_mae_r"] >= 0
    assert forecast["uncertainty"] <= 1


def test_missed_opportunity_tracker_replays_rejected_signals(tmp_path: Path):
    tracker = MissedOpportunityTracker(tmp_path / "missed.jsonl")
    tracker.register("sig-1", "BUY", 2300.0, 2295.0, 2310.0, ["spread_gate"], 100)
    result = tracker.resolve("sig-1", [2300, 2302, 2306, 2311], 104)
    assert result["classification"] == "profitable_miss"
    assert tracker.summary()["profitable_misses"] == 1


def test_exit_engine_hard_invalidation_overrides_recovery_and_preserves_profit_floor():
    engine = AdaptiveExitEngine()
    decision = engine.decide({
        "current_r": 0.9, "peak_r": 1.4, "age_seconds": 500, "recovery_probability": 0.95,
        "continuation_probability": 0.12, "invalidation_probability": 0.94,
        "hard_invalidation": True, "atr_r": 0.4, "current_stop_r": 0.2,
    })
    assert decision["action"] == "close"
    assert decision["priority"] == "hard_invalidation"

    protected = engine.decide({
        "current_r": 0.8, "peak_r": 1.5, "age_seconds": 200, "recovery_probability": 0.4,
        "continuation_probability": 0.55, "invalidation_probability": 0.2,
        "hard_invalidation": False, "atr_r": 0.35, "current_stop_r": 0.4,
    })
    assert protected["recommended_stop_r"] >= 0.4


def test_burst_engine_always_returns_complete_gate_trace():
    result = BurstIntelligence().evaluate({
        "base_protected": True, "base_profit_r": 1.0, "continuation_probability": 0.76,
        "burst_success_probability": 0.68, "broker_quality": 0.9, "bridge_ready": True,
        "exposure_r": 0.3, "max_exposure_r": 0.8, "cooldown_active": False,
        "extension": 0.35, "max_extension": 0.8, "risk_reward": 1.8,
    })
    assert result["allowed"] is True
    assert len(result["gates"]) >= 7
    assert all("name" in gate and "passed" in gate for gate in result["gates"])


def test_external_context_provider_failure_is_neutral_and_nonfatal(tmp_path: Path):
    context = FreeExternalContext(tmp_path / "external_cache.json")
    result = context.refresh(fetcher=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")))
    assert result["available"] is False
    assert result["risk_bias"] == 0.0
    assert result["uncertainty"] >= 0.8
    assert result["errors"]


def test_governance_auto_promotes_calibration_but_requires_approval_for_material_change(tmp_path: Path):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    cal_artifact = artifacts / "cal-1.json"
    cal_artifact.write_text(json.dumps({"calibration": {"continuation": 0.7}}))
    risk_artifact = artifacts / "risk-2.json"
    risk_artifact.write_text(json.dumps({"risk_threshold": 0.8}))
    gov = ModelGovernance(tmp_path / "governance.json", artifacts_dir=artifacts)
    calibration = gov.submit("cal-1", "calibration", {"brier": 0.14, "drawdown": 0.08, "sortino": 1.8, "samples": 500, "shadow_passed": True}, artifact_path=cal_artifact, feature_schema=["trend"])
    assert calibration["status"] == "promoted"
    material = gov.submit("risk-2", "risk_threshold", {"brier": 0.12, "drawdown": 0.07, "sortino": 2.0, "samples": 700, "shadow_passed": True}, artifact_path=risk_artifact, feature_schema=["trend"])
    assert material["status"] == "approval_required"
    assert gov.approve("risk-2")["status"] == "promoted"
    assert gov.rollback()["status"] == "rolled_back"


def test_orchestrator_composes_all_engines_and_survives_partial_external_failure(tmp_path: Path):
    orchestrator = GodModeV15Orchestrator(tmp_path)
    report = orchestrator.evaluate({
        "market": {"returns": [0.001, 0.001, 0.0012], "atr": 2.0, "atr_baseline": 1.2, "adx": 30, "range_position": 0.75, "news_risk": 0.1, "liquidity": 0.8},
        "features": {"trend": 0.8, "momentum": 0.7, "structure": 0.7, "extension": 0.2, "spread_quality": 0.9, "recovery_evidence": 0.4},
        "broker": {"spread_points": 20, "slippage_points": 2, "latency_ms": 70, "filled": True, "session": "london"},
        "position": {"current_r": 0.4, "peak_r": 0.8, "age_seconds": 120, "current_stop_r": -0.2, "hard_invalidation": False, "atr_r": 0.35},
        "burst": {"base_protected": False, "base_profit_r": 0.4, "bridge_ready": True, "exposure_r": 0.1, "max_exposure_r": 0.8, "cooldown_active": False, "extension": 0.2, "max_extension": 0.8, "risk_reward": 1.5},
    })
    for key in ["regime", "broker", "forecast", "exit", "burst", "external_context", "explanation", "health"]:
        assert key in report
    assert report["decision_id"]
    assert 0 <= report["health"]["score"] <= 100
