import asyncio
import time
from pathlib import Path

import app
from services.readiness_monitor import ReadinessComponentMonitor

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app.py"


def test_timed_out_component_is_not_resubmitted_until_original_finishes():
    calls = {"count": 0}

    def slow_probe():
        calls["count"] += 1
        time.sleep(0.08)
        return {"ok": True, "value": 7}

    async def scenario():
        monitor = ReadinessComponentMonitor(max_workers=2)
        monitor.register("slow", slow_probe, interval_seconds=1.0, timeout_seconds=0.01, critical=True, max_age_seconds=2.0)
        try:
            first = await monitor.refresh("slow")
            second = await monitor.refresh("slow")
            assert first["timedOut"] is True
            assert second["skipped"] is True
            assert calls["count"] == 1
            await asyncio.sleep(0.12)
            snap = monitor.snapshot("slow")
            assert snap["inFlight"] is False
            assert snap["payload"] == {"ok": True, "value": 7}
            assert snap["successes"] == 1
        finally:
            monitor.shutdown()

    asyncio.run(scenario())


def test_component_failure_retains_last_success_and_reports_age():
    sequence = iter(({"ok": True, "value": "good"}, RuntimeError("boom")))

    def probe():
        value = next(sequence)
        if isinstance(value, Exception):
            raise value
        return value

    async def scenario():
        monitor = ReadinessComponentMonitor(max_workers=1)
        monitor.register("probe", probe, interval_seconds=1.0, timeout_seconds=0.2, critical=True, max_age_seconds=5.0)
        try:
            await monitor.refresh("probe")
            await monitor.refresh("probe", force=True)
            snap = monitor.snapshot("probe")
            assert snap["payload"] == {"ok": True, "value": "good"}
            assert snap["lastError"] == "RuntimeError: boom"
            assert snap["lastSuccessAgeSeconds"] is not None
            assert snap["fresh"] is True
        finally:
            monitor.shutdown()

    asyncio.run(scenario())


def test_readiness_background_loop_uses_component_cache_not_monolithic_lane():
    src = APP.read_text(encoding="utf-8")
    assert "READINESS_COMPONENT_MONITOR" in src
    assert "_compose_cached_readiness" in src
    assert "Readiness lane deadline exceeded; rotating dedicated executor" not in src
    loop_chunk = src[src.index("async def _readiness_snapshot_loop"):src.index("def _cached_readiness_snapshot")]
    assert "_authoritative_readiness()" not in loop_chunk
    assert "READINESS_LANE.run" not in loop_chunk


def test_order_admission_and_runtime_health_use_cached_readiness():
    src = APP.read_text(encoding="utf-8")
    prelive_start = src.index("def _prelive_admission") if "def _prelive_admission" in src else src.index("def _prelive")
    prelive_end = src.index("def _execute_mt5_serialized", prelive_start)
    prelive = src[prelive_start:prelive_end]
    assert "_cached_readiness_snapshot()" in prelive
    assert "_authoritative_readiness()" not in prelive
    runtime_start = src.index('def runtime_health()')
    runtime_end = src.index('@app.get("/api/live-certification/status")', runtime_start)
    assert "_cached_readiness_snapshot()" in src[runtime_start:runtime_end]


def test_missed_move_autopsy_fast_sniper_has_no_undefined_regime_reference():
    src = APP.read_text(encoding="utf-8")
    start = src.index("def _fast_sniper_decision")
    end = src.index("def _effective_auto_loop_sleep", start)
    chunk = src[start:end]
    assert "(regime or {})" not in chunk
    assert "_regime_info" in chunk


def test_cached_readiness_exposes_per_component_diagnostics_and_fails_closed_when_critical_stale(monkeypatch):
    monkeypatch.setattr(app, "_readiness_component_snapshots", lambda: {
        "mt5Status": {"payload": {"connected": True, "liveTradingEnabled": True}, "fresh": True, "critical": True, "lastSuccessAgeSeconds": 0.1},
        "market": {"payload": {"open": True, "reason": "open"}, "fresh": True, "critical": True, "lastSuccessAgeSeconds": 0.1},
        "validation": {"payload": {"enabled": False, "passed": True}, "fresh": True, "critical": True, "lastSuccessAgeSeconds": 0.1},
        "tickGuard": {"payload": {"required": False, "ok": True}, "fresh": True, "critical": True, "lastSuccessAgeSeconds": 0.1},
        "certification": {"payload": {"approved": True}, "fresh": False, "critical": True, "lastSuccessAgeSeconds": 20.0, "lastError": "timeout"},
        "unresolved": {"payload": [], "fresh": True, "critical": True, "lastSuccessAgeSeconds": 0.1},
    })
    monkeypatch.setattr(app.mt5_bridge, "status", lambda: {"connected": True, "liveTradingEnabled": True})
    monkeypatch.setattr(app, "_market_state", lambda: {"open": True, "reason": "open"})
    monkeypatch.setattr(app.RUNTIME_HEALTH, "snapshot", lambda *_a, **_k: {
        "reconciliation": {"ok": True, "stale": False},
        "auto_loop": {"ok": True, "stale": False},
        "trade_protection": {"ok": True, "stale": False},
        "event_loop": {"ok": True, "stale": False},
    })
    monkeypatch.setattr(app, "_priority_intent_health", lambda: {"taskPresent": True, "ok": True})
    monkeypatch.setattr(app.kill_switch, "status", lambda: {"active": False})
    monkeypatch.setattr(app.os, "access", lambda *_a, **_k: True)
    monkeypatch.setitem(app.SETTINGS_STATE, "execution", {"autoTradingEnabled": True, "dryRun": False, "requireLiveCertification": True})
    monkeypatch.setitem(app.SETTINGS_STATE, "automation", {"earlyIntentEnabled": True})

    payload = app._compose_cached_readiness()
    assert payload["appReady"] is True
    assert payload["tradingReady"] is False
    assert "certification" in payload["readinessComponents"]
    assert any("Certification readiness data stale" in x for x in payload["executionBlockers"])



def test_cached_readiness_does_not_call_mt5_or_market_probes(monkeypatch):
    snapshots = {
        "mt5Status": {"payload": {"connected": True, "liveTradingEnabled": True}, "fresh": True, "critical": True, "lastSuccessAgeSeconds": 0.1},
        "market": {"payload": {"open": True, "reason": "open"}, "fresh": True, "critical": True, "lastSuccessAgeSeconds": 0.1},
        "validation": {"payload": {"enabled": False, "passed": True}, "fresh": True, "critical": True, "lastSuccessAgeSeconds": 0.1},
        "tickGuard": {"payload": {"required": False, "ok": True}, "fresh": True, "critical": True, "lastSuccessAgeSeconds": 0.1},
        "certification": {"payload": {"approved": True}, "fresh": True, "critical": True, "lastSuccessAgeSeconds": 0.1},
        "unresolved": {"payload": [], "fresh": True, "critical": True, "lastSuccessAgeSeconds": 0.1},
    }
    monkeypatch.setattr(app, "_readiness_component_snapshots", lambda: snapshots)
    monkeypatch.setattr(app.mt5_bridge, "status", lambda: (_ for _ in ()).throw(AssertionError("must use component cache")))
    monkeypatch.setattr(app, "_market_state", lambda: (_ for _ in ()).throw(AssertionError("must use component cache")))
    monkeypatch.setattr(app.RUNTIME_HEALTH, "snapshot", lambda *_a, **_k: {})
    monkeypatch.setattr(app, "_priority_intent_health", lambda: {"taskPresent": False, "ok": True})
    monkeypatch.setattr(app.kill_switch, "status", lambda: {"active": False})
    monkeypatch.setattr(app.os, "access", lambda *_a, **_k: True)
    monkeypatch.setitem(app.SETTINGS_STATE, "execution", {"autoTradingEnabled": False, "dryRun": False, "requireLiveCertification": False})
    payload = app._compose_cached_readiness()
    assert payload["mt5Connected"] is True
    assert payload["marketOpen"] is True



def test_manual_refresh_result_is_not_overwritten_by_cached_app_ok(monkeypatch):
    async def scenario():
        monkeypatch.setattr(app.READINESS_COMPONENT_MONITOR, "refresh_all", lambda force=False: None)
    # Source-level contract: explicit refresh outcome must be applied after cached payload expansion.
    src = APP.read_text(encoding="utf-8")
    start = src.index('async def readiness_refresh()')
    end = src.index('@app.get("/api/runtime/lanes")', start)
    chunk = src[start:end]
    assert 'return {**cached, "ok": not timed_out and not failed' in chunk


def test_release_identity_v1543():
    assert app.BUILD_ID == "V15.4.3-READINESS-COMPONENT-KERNEL"
