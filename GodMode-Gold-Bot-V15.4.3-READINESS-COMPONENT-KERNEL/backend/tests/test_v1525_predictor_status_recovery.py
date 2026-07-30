from pathlib import Path
import time


def test_fast_sniper_status_is_cached_read_only_and_never_runs_decision(monkeypatch):
    import app as backend_app

    now = time.time()
    backend_app.FAST_SNIPER_STATE["last"] = {"ok": True, "action": "WAIT", "reason": "cached"}
    backend_app.FAST_SNIPER_STATE["lastAt"] = now
    backend_app.FAST_SNIPER_STATE["earlyIntent"] = {
        "updatedAt": now,
        "runtimeStatus": "WATCH",
        "probability": 0.31,
    }
    backend_app.FAST_SNIPER_STATE["earlyImpulse"] = {
        "updatedAt": now,
        "runtimeStatus": "WATCH",
        "probability": 0.22,
    }
    backend_app.PRIORITY_INTENT_STATE.update({
        "runtimeStatus": "WATCH",
        "lastScanAt": now,
        "buildId": backend_app.BUILD_ID,
    })
    monkeypatch.setattr(
        backend_app,
        "_fast_sniper_decision",
        lambda market: (_ for _ in ()).throw(AssertionError("status endpoint must not evaluate a trade decision")),
    )
    monkeypatch.setattr(backend_app.mt5_bridge, "status", lambda: {"connected": True, "symbol": "XAUUSD"})

    started = time.perf_counter()
    result = backend_app.fast_sniper_status()
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    assert result["ok"] is True
    assert result["last"]["reason"] == "cached"
    assert result["earlyIntent"]["runtimeStatus"] == "WATCH"
    assert result["priorityIntent"]["runtimeStatus"] == "WATCH"
    assert result["endpointStatus"] == "LIVE"
    assert elapsed_ms < 100.0


def test_priority_intent_health_distinguishes_starting_stale_and_live(monkeypatch):
    import app as backend_app

    now = 1_700_000_000.0
    monkeypatch.setattr(backend_app.time, "time", lambda: now)

    backend_app.PRIORITY_INTENT_STATE.clear()
    backend_app.PRIORITY_INTENT_STATE.update({"runtimeStatus": "STARTING", "lastScanAt": 0.0})
    starting = backend_app._priority_intent_health()
    assert starting["status"] == "starting"
    assert starting["ok"] is False

    backend_app.PRIORITY_INTENT_STATE.update({"runtimeStatus": "WATCH", "lastScanAt": now - 10.0})
    stale = backend_app._priority_intent_health()
    assert stale["status"] == "stale"
    assert stale["ok"] is False

    backend_app.PRIORITY_INTENT_STATE.update({"runtimeStatus": "WATCH", "lastScanAt": now - 0.2})
    live = backend_app._priority_intent_health()
    assert live["status"] == "live"
    assert live["ok"] is True
    assert live["lastScanAgeSeconds"] == 0.2


def test_health_full_exposes_priority_intent_component():
    text = Path("backend/app.py").read_text(encoding="utf-8")
    assert '"id": "priorityIntent"' in text
    assert '"label": "Priority Intent Execution"' in text
    assert '_priority_intent_health()' in text


def test_priority_intent_has_its_own_supervisor_and_task_handle():
    text = Path("backend/app.py").read_text(encoding="utf-8")
    assert "_PRIORITY_INTENT_TASK" in text
    assert "async def _priority_intent_supervisor" in text
    assert "godmode-priority-intent-supervisor" in text


def test_frontend_uses_versioned_predictor_assets_and_removes_duplicate_overlay():
    index = Path("frontend/dist/index.html").read_text(encoding="utf-8")
    assert "early-impulse-settings-v1529.js" in index
    assert "early-impulse-settings-v1529.css" in index
    assert "early-intent-ui.js" not in index
    assert 'src="/early-impulse-settings.js"' not in index


def test_predictor_ui_error_copy_does_not_call_whole_backend_offline():
    source = Path("frontend/src/pages/Settings.tsx").read_text(encoding="utf-8")
    assert "Predictor status endpoint unavailable" in source
    assert "Backend unavailable." not in source[source.find("fastSniperStatus"):source.find("fastSniperStatus") + 1000]
