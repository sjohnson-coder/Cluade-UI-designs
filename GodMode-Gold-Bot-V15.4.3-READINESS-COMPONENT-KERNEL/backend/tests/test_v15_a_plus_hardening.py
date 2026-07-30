import math

from services.v15.contracts import clamp
from services.v15.probability_engine import ProbabilityEngine


def _forecast(engine: ProbabilityEngine, trend: float):
    return engine.forecast(
        {"trend": trend, "momentum": trend, "structure": trend, "extension": 0.2},
        {"primary": "strong_trend", "confidence": 0.9},
        {"quality": 0.9, "uncertainty": 0.1},
        {"risk_bias": 0.0, "uncertainty": 0.1},
    )


def test_nonfinite_signals_fail_neutral_not_maximum_confidence():
    assert clamp(float("nan")) == 0.5
    assert clamp(float("inf")) == 0.5
    assert clamp("bad") == 0.5
    assert math.isfinite(clamp(float("nan")))


def test_decisive_model_score_reduces_not_increases_uncertainty():
    engine = ProbabilityEngine()
    decisive = _forecast(engine, 1.0)
    ambiguous = _forecast(engine, 0.15)
    assert decisive["probabilities"]["continuation"] > ambiguous["probabilities"]["continuation"]
    assert decisive["uncertainty"] < ambiguous["uncertainty"]


def test_calibration_requires_200_target_outcomes_not_aggregate_labels():
    engine = ProbabilityEngine()
    report = {
        "decision_id": "d",
        "forecast": {"probabilities": {
            "continuation": 0.7, "tp_before_sl": 0.7, "be_first": 0.6,
            "fast_fail": 0.2, "invalidation": 0.2,
        }},
    }
    for _ in range(40):
        engine.record_trade_outcome(report, True)
    result = _forecast(engine, 0.8)
    assert result["calibration_label_events"] == 200
    assert result["calibration_samples"] == 40
    assert result["is_calibrated"] is False
    assert result["score_type"] == "heuristic_shadow_score"
