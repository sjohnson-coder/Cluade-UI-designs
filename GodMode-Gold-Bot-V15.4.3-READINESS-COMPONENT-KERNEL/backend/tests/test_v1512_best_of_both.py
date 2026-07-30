from pathlib import Path

from backend.services.v15.orchestrator import GodModeV15Orchestrator
from backend.services.v15.probability_engine import ProbabilityEngine


def test_unattributed_outcome_is_rejected_and_persisted(tmp_path: Path):
    engine = GodModeV15Orchestrator(tmp_path)
    assert engine.record_trade_outcome(True) is False
    assert engine.unattributed_outcomes == 1

    restarted = GodModeV15Orchestrator(tmp_path)
    assert restarted.unattributed_outcomes == 1
    assert restarted.overview()["calibrationProgress"]["unattributedOutcomes"] == 1


def test_decision_attribution_survives_restart(tmp_path: Path):
    engine = GodModeV15Orchestrator(tmp_path)
    report = {
        "decision_id": "decision-1",
        "generated_at": __import__("time").time(),
        "forecast": {"probabilities": {"tp_before_sl": 0.7}},
    }
    engine._reports["decision-1"] = report
    engine.state.update("calibration_attribution", {
        "reports": engine._reports,
        "unattributed_outcomes": 0,
    })

    restarted = GodModeV15Orchestrator(tmp_path)
    assert restarted.record_trade_outcome(True, decision_id="decision-1") is True
    progress = restarted.probability.calibration_progress()
    assert progress["samples"] == 1


def test_calibration_progress_uses_primary_trade_horizon(tmp_path: Path):
    engine = ProbabilityEngine(tmp_path / "calibration.json")
    engine.calibration = {
        "tp_before_sl": {"samples": 40, "brier": 0.20},
        "continuation": {"samples": 200, "brier": 0.10},
    }
    progress = engine.calibration_progress(target=200)
    assert progress["samples"] == 40
    assert progress["remaining"] == 160
    assert progress["isCalibrated"] is False
