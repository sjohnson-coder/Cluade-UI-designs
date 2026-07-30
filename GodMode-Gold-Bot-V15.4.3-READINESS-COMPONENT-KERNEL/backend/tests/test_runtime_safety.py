from pathlib import Path
from services.runtime_safety import ExecutionLedger, RuntimeHealth


def test_execution_ledger_blocks_duplicate(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.sqlite")
    payload = {"executionId": "sig-1", "symbol": "XAUUSD", "side": "BUY", "volume": 0.01}
    accepted, key, _ = ledger.begin(payload, "auto")
    assert accepted
    ledger.finish(key, {"ok": True, "dryRun": True})
    accepted2, key2, prior = ledger.begin(payload, "auto")
    assert not accepted2
    assert key2 == key
    assert prior and prior["status"] == "DRY_RUN"


def test_runtime_health_marks_stale():
    health = RuntimeHealth()
    health.beat("engine")
    snap = health.snapshot({"engine": 60})
    assert snap["engine"]["ok"] is True
    assert snap["engine"]["stale"] is False
