import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as app_module
from services.v15.broker_engine import BrokerIntelligence
from services.v15.external_context import FreeExternalContext
from services.v15.governance import ModelGovernance
from services.v15.missed_opportunity import MissedOpportunityTracker
from services.v15.probability_engine import ProbabilityEngine
from services.v15.runtime_state import RuntimeStateManager


def test_missing_broker_telemetry_is_unknown_not_perfect():
    broker = BrokerIntelligence()
    profile = broker.update({})
    assert profile["samples"] == 0
    assert profile["quality"] == pytest.approx(0.5)
    assert profile["uncertainty"] == pytest.approx(1.0)
    assert profile["telemetry_available"] is False


def test_runtime_command_and_update_share_one_serialisation_lock(tmp_path: Path):
    manager = RuntimeStateManager(tmp_path / "state.json")
    threads = []
    for i in range(50):
        threads.append(threading.Thread(target=manager.update, args=("n", {str(i): i})))
        threads.append(threading.Thread(target=manager.publish_command, args=("test", {"i": i})))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    snap = manager.snapshot(public=False)
    assert snap["revision"] == 100
    assert snap["state"]["command_sequence"] == 50
    assert len(snap["state"]["n"]) == 50
    on_disk = json.loads((tmp_path / "state.json").read_text())
    assert on_disk["revision"] == 100


def test_missed_opportunity_uses_first_hit_and_validates_inputs(tmp_path: Path):
    tracker = MissedOpportunityTracker(tmp_path / "missed.jsonl")
    tracker.register("tp-first", "BUY", 100, 95, 110, ["spread"], 1)
    assert tracker.resolve("tp-first", [100, 111, 94], 2)["classification"] == "profitable_miss"
    tracker.register("sl-first", "BUY", 100, 95, 110, ["spread"], 3)
    assert tracker.resolve("sl-first", [100, 94, 111], 4)["classification"] == "correct_reject"
    with pytest.raises(ValueError):
        tracker.register("bad", "BAD", 100, 95, 110, [], 1)
    with pytest.raises(ValueError):
        tracker.resolve("tp-first", [], 3)
    with pytest.raises(KeyError):
        tracker.resolve("missing", [100], 3)


def test_probability_calibration_persists_and_records_outcome(tmp_path: Path):
    path = tmp_path / "calibration.json"
    engine = ProbabilityEngine(path)
    engine.record("continuation", 0.8, True, decision_id="d1")
    engine.record("continuation", 0.2, False, decision_id="d2")
    restored = ProbabilityEngine(path)
    snap = restored.snapshot()
    assert snap["horizons"]["continuation"]["samples"] == 2
    assert snap["horizons"]["continuation"]["wins"] == 1
    assert len(snap["events"]) == 2


def test_governance_requires_verified_artifact_and_rolls_back_payload(tmp_path: Path):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    candidate = artifacts / "candidate.json"
    candidate.write_text(json.dumps({"coefficients": {"trend": 1.2}}))
    gov = ModelGovernance(tmp_path / "governance.json", artifacts_dir=artifacts)
    record = gov.submit(
        "cal-1",
        "calibration",
        {"brier": .14, "drawdown": .08, "sortino": 1.8, "samples": 500, "shadow_passed": True},
        artifact_path=candidate,
        feature_schema=["trend"],
    )
    assert record["status"] == "promoted"
    assert record["artifact_sha256"]
    assert gov.active_artifact()["coefficients"]["trend"] == 1.2
    rolled = gov.rollback()
    assert rolled["status"] == "rolled_back"
    assert gov.active_artifact() is None
    with pytest.raises(ValueError):
        gov.submit("fake", "calibration", {"brier": 0, "drawdown": 0, "sortino": 9, "samples": 999, "shadow_passed": True})


def test_external_context_computes_nonzero_risk_and_is_bounded(tmp_path: Path):
    context = FreeExternalContext(tmp_path / "cache.json")
    payloads = {
        "https://example.test/rss": b"<rss><channel><item><title>Federal Reserve emergency rate decision shocks markets</title><pubDate>today</pubDate></item></channel></rss>",
    }
    context.sources = [("rss", "https://example.test/rss", "test")]
    result = context.refresh(fetcher=lambda url, timeout=4: payloads[url])
    assert result["available"] is True
    assert result["risk_bias"] > 0
    assert 0 <= result["uncertainty"] <= 1


def test_v15_api_returns_404_or_422_not_500():
    client = TestClient(app_module.app)
    headers = {'Origin': 'http://127.0.0.1:8000', 'Sec-Fetch-Site': 'same-origin'}
    missing = client.post('/api/v15/missed-opportunities/resolve', json={'signal_id': 'missing', 'prices': [1, 2]}, headers=headers)
    assert missing.status_code == 404
    bad = client.post('/api/v15/missed-opportunities/register', json={'side': 'BAD', 'entry': 1, 'sl': 0, 'tp': 2, 'gates': 'abc'}, headers=headers)
    assert bad.status_code == 422
    gov = client.post('/api/v15/governance/approve', json={'candidate_id': 'missing'}, headers=headers)
    assert gov.status_code == 404


def test_overview_is_degraded_until_a_fresh_shadow_evaluation(tmp_path: Path):
    from services.v15.orchestrator import GodModeV15Orchestrator
    orchestrator = GodModeV15Orchestrator(tmp_path)
    overview = orchestrator.overview()
    assert overview["health"]["ok"] is False
    assert overview["health"]["score"] < 100
    assert overview["status"] in {"warming", "stale", "degraded"}


def test_runtime_state_survives_restart_and_windows_replace_lock(tmp_path: Path, monkeypatch):
    import services.v15.runtime_state as module
    path = tmp_path / "state.json"
    manager = RuntimeStateManager(path)
    original_replace = module.os.replace
    attempts = {"count": 0}

    def locked_replace(src, dst):
        attempts["count"] += 1
        if attempts["count"] <= 5:
            raise PermissionError("simulated Windows scanner lock")
        return original_replace(src, dst)

    monkeypatch.setattr(module.os, "replace", locked_replace)
    manager.update("health", {"ok": True})
    restored = RuntimeStateManager(path)
    assert restored.snapshot(public=False)["state"]["health"]["ok"] is True
    assert attempts["count"] >= 5


def test_orchestrator_marks_old_shadow_report_stale_across_restart(tmp_path: Path):
    from services.v15.orchestrator import GodModeV15Orchestrator
    orchestrator = GodModeV15Orchestrator(tmp_path)
    report = orchestrator.evaluate({
        "market": {"returns": [0.001], "atr": 1.0, "atr_baseline": 1.0, "adx": 20, "liquidity": 0.8},
        "features": {"trend": 0.6, "momentum": 0.6, "structure": 0.6, "extension": 0.2},
        "broker": {"spread_points": 20, "slippage_points": 1, "latency_ms": 50, "filled": True, "session": "london"},
        "position": {}, "burst": {},
    })
    report["generated_at"] -= 2 * 24 * 3600
    orchestrator.state.update("intelligence", report)
    restored = GodModeV15Orchestrator(tmp_path)
    overview = restored.overview()
    assert overview["status"] == "stale"
    assert overview["health"]["ok"] is False

def test_shadow_health_uses_runtime_beat(monkeypatch):
    import app

    monkeypatch.setattr(app.V15_ORCHESTRATOR, "evaluate", lambda payload, source="api": {
        "decision_id": "decision-1", "health": {"score": 82.0}
    })
    calls = []
    monkeypatch.setattr(app.RUNTIME_HEALTH, "beat", lambda component, detail=None, **kwargs: calls.append((component, detail)))
    result = app._v15_shadow_evaluate({"symbol": "XAUUSD"}, {"side": "BUY"}, source="test")
    assert result["decision_id"] == "decision-1"
    assert calls == [("v15_shadow", "decision-1 82%")]


def test_outcome_can_be_bound_to_exact_shadow_decision(tmp_path):
    from services.v15.orchestrator import GodModeV15Orchestrator

    engine = GodModeV15Orchestrator(tmp_path)
    report_a = engine.evaluate({
        "market": {"returns": [0.1, 0.2], "atr_ratio": 1.0, "adx": 25},
        "features": {"trend": 0.7},
        "broker": {"spread": 0.2, "slippage": 0.01, "latency_ms": 20, "filled": True},
    })
    report_b = engine.evaluate({
        "market": {"returns": [-0.1, -0.2], "atr_ratio": 1.0, "adx": 25},
        "features": {"trend": -0.7},
        "broker": {"spread": 0.2, "slippage": 0.01, "latency_ms": 20, "filled": True},
    })
    assert engine.record_trade_outcome(True, decision_id=report_a["decision_id"])
    snap = engine.probability.snapshot()
    assert len(snap["events"]) > 0
    assert report_a["decision_id"] != report_b["decision_id"]
