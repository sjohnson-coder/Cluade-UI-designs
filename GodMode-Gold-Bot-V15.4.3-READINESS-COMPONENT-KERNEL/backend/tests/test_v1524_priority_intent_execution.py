from pathlib import Path
import copy


def _candidate():
    return {
        "ok": True,
        "action": "TAKE_TRADE",
        "source": "early_intent",
        "side": "BUY",
        "confidence": 69.0,
        "latencyMs": 18.0,
        "features": {
            "anticipatoryEntry": True,
            "earlyIntent": True,
            "progressiveStage": "INTENT",
            "sourceTickAgeMs": 42,
            "intentPrediction": {"displacement_atr": 0.08},
        },
        "tradePlan": {"entry": 4000.12, "sl": 3993.0, "tp1": 4007.2},
    }


def test_priority_lane_reports_exact_execution_blocker(monkeypatch):
    import app as backend_app

    backend_app.PRIORITY_INTENT_STATE.clear()
    backend_app.PRIORITY_INTENT_STATE.update({"runtimeStatus": "STARTING", "lastCandidate": {}})
    monkeypatch.setattr(backend_app.mt5_bridge, "status", lambda: {"connected": True})
    monkeypatch.setattr(backend_app, "_market_state", lambda: {"open": True})
    monkeypatch.setattr(backend_app, "_live_market", lambda: {"symbol": "XAUUSD", "price": 4000.1})
    monkeypatch.setattr(backend_app, "_fast_sniper_decision", lambda market: _candidate())
    monkeypatch.setattr(backend_app.kill_switch, "status", lambda: {"active": False})
    monkeypatch.setattr(backend_app, "_execution_mode", lambda: "auto")
    settings = copy.deepcopy(backend_app.SETTINGS_STATE)
    settings["execution"] = {
        "liveTradingEnabled": False,
        "dryRun": True,
        "autoTradingEnabled": False,
        "mode": "auto",
    }
    monkeypatch.setattr(backend_app, "SETTINGS_STATE", settings)

    result = backend_app._priority_intent_tick()
    assert result["blocked"] is True
    assert "Live Trading is OFF or Dry Run is ON" in result["message"]
    assert "Auto Trading switch is OFF" in result["message"]
    assert backend_app.PRIORITY_INTENT_STATE["runtimeStatus"] == "QUALIFIED_BLOCKED"
    assert backend_app.PRIORITY_INTENT_STATE["lastCandidate"]["moveAtr"] == 0.08


def test_priority_lane_dispatches_qualified_candidate_immediately(monkeypatch):
    import app as backend_app

    backend_app.PRIORITY_INTENT_STATE.clear()
    backend_app.PRIORITY_INTENT_STATE.update({"runtimeStatus": "STARTING", "lastCandidate": {}})
    monkeypatch.setattr(backend_app.mt5_bridge, "status", lambda: {"connected": True})
    monkeypatch.setattr(backend_app, "_market_state", lambda: {"open": True})
    monkeypatch.setattr(backend_app, "_live_market", lambda: {"symbol": "XAUUSD", "price": 4000.1})
    monkeypatch.setattr(backend_app, "_fast_sniper_decision", lambda market: _candidate())
    monkeypatch.setattr(backend_app.kill_switch, "status", lambda: {"active": False})
    monkeypatch.setattr(backend_app, "_execution_mode", lambda: "auto")
    settings = copy.deepcopy(backend_app.SETTINGS_STATE)
    settings["execution"] = {
        "liveTradingEnabled": True,
        "dryRun": False,
        "autoTradingEnabled": True,
        "mode": "auto",
    }
    settings.setdefault("automation", {})["earlyIntentCandidateRetrySeconds"] = 2.0
    monkeypatch.setattr(backend_app, "SETTINGS_STATE", settings)
    calls = []
    def execute(reason="", precomputed_decision=None, precomputed_market=None):
        calls.append((reason, precomputed_decision, precomputed_market))
        return {"ok": True, "blocked": False, "message": "order sent"}
    monkeypatch.setattr(backend_app, "_auto_trade_tick", execute)

    result = backend_app._priority_intent_tick()
    assert result["ok"] is True
    assert calls[0][0] == "priority_intent_loop"
    assert calls[0][1]["source"] == "early_intent"
    assert calls[0][2]["symbol"] == "XAUUSD"
    assert backend_app.PRIORITY_INTENT_STATE["runtimeStatus"] == "ORDER_SENT"
    assert backend_app.PRIORITY_INTENT_STATE["lastExecution"]["dispatchLatencyMs"] >= 0


def test_priority_lane_is_started_and_uses_250ms_default():
    app_text = Path("backend/app.py").read_text(encoding="utf-8")
    settings = Path("backend/data/settings.json").read_text(encoding="utf-8")
    assert "godmode-priority-intent-loop" in app_text
    assert '"earlyIntentPriorityLoopSeconds": 0.25' in app_text
    assert '"earlyIntentPriorityLoopSeconds": 0.25' in settings
    assert '"earlyIntentDecisionTtlSeconds": 0.2' in settings


def test_anticipatory_entries_bypass_synchronous_ai_audit_latency():
    app_text = Path("backend/app.py").read_text(encoding="utf-8")
    assert '_anticipatory_entry = bool((decision.get("features") or {}).get("anticipatoryEntry"))' in app_text
    assert "_shock_flag or _anticipatory_entry or" in app_text


def test_uncalibrated_v15_veto_is_shadow_only_for_anticipatory_entries():
    app_text = Path("backend/app.py").read_text(encoding="utf-8")
    assert "anticipatoryUncalibratedV15VetoDisabled" in app_text
    assert '"shadowOnly": _shadow_only' in app_text
    assert "if not _shadow_only:" in app_text


def test_incremental_tick_fetch_prevents_full_window_ipc_reloads(monkeypatch):
    import app as backend_app

    backend_app.PREDICTOR_TICK_BUFFERS.clear()
    backend_app.PREDICTOR_TICK_LAST_FETCH_MSC.clear()
    now = 1_700_000_010.0
    calls = []

    monkeypatch.setattr(backend_app.mt5_bridge, "status", lambda: {"connected": True})

    def fetch(symbol, start, end):
        calls.append((start, end))
        base = 1_700_000_009_000 if len(calls) == 1 else 1_700_000_009_800
        return [
            {"time_msc": base, "bid": 100.0, "ask": 100.1},
            {"time_msc": base + 100, "bid": 100.1, "ask": 100.2},
        ]

    monkeypatch.setattr(backend_app.mt5_bridge, "copy_ticks_range", fetch)
    market = {"tickTimeMsc": 1_700_000_009_900, "bid": 100.2, "ask": 100.3, "price": 100.25}
    _, first_meta = backend_app._predictor_tick_window("XAUUSD", 12.0, now, market)
    _, second_meta = backend_app._predictor_tick_window("XAUUSD", 12.0, now + 0.25, market)
    first_span = calls[0][1] - calls[0][0]
    assert first_span > 12.0
    assert len(calls) == 1
    assert first_meta["historyBackfill"] is True
    assert second_meta["historyBackfill"] is False


def test_telegram_alerts_prove_active_build_and_no_longer_masquerade_as_early_entries():
    app_text = Path("backend/app.py").read_text(encoding="utf-8")
    assert '`Build: {BUILD_ID}`' in app_text
    assert "POST-MOVE DIAGNOSTIC — EARLY ORDER NOT SENT" in app_text
    assert "MOMENTUM SPIKE DETECTED — WATCH RETEST" not in app_text
    assert "This is not an early-entry signal" in app_text


def test_status_endpoint_exposes_priority_latency_and_build(monkeypatch):
    import app as backend_app

    now = __import__("time").time()
    backend_app.FAST_SNIPER_STATE["earlyIntent"] = {"updatedAt": now, "runtimeStatus": "WATCH"}
    backend_app.FAST_SNIPER_STATE["earlyImpulse"] = {"updatedAt": now, "runtimeStatus": "WATCH"}
    backend_app.PRIORITY_INTENT_STATE.update({"runtimeStatus": "WATCH", "scanLatencyMs": 12.5})
    monkeypatch.setattr(backend_app, "_live_market", lambda: {"symbol": "XAUUSD"})
    monkeypatch.setattr(backend_app, "_fast_sniper_decision", lambda market: {"ok": False, "reason": "watch"})
    monkeypatch.setattr(backend_app.mt5_bridge, "status", lambda: {"connected": True, "symbol": "XAUUSD"})
    result = backend_app.fast_sniper_status()
    assert result["buildId"] == backend_app.BUILD_ID
    assert result["priorityIntent"]["scanLatencyMs"] == 12.5


def test_launcher_rejects_stale_backend_and_ui_exposes_priority_latency():
    launcher = Path("START_GODMODE.bat").read_text(encoding="utf-8")
    ui = Path("frontend/dist/early-impulse-settings.js").read_text(encoding="utf-8")
    assert "service -eq 'godmode-backend'" in launcher
    assert "/api/fast-sniper/status" in launcher
    assert "priorityIntent" in ui
    assert "eip-tick-age" in ui
    assert "eip-fetch-latency" in ui
    assert "eip-priority-state" in ui


def test_priority_dispatch_reuses_exact_detected_decision_and_market():
    text = Path("backend/app.py").read_text(encoding="utf-8")
    assert "precomputed_decision: dict[str, Any] | None = None" in text
    assert "precomputed_market: dict[str, Any] | None = None" in text
    assert "precomputed_decision=decision, precomputed_market=market" in text


def test_priority_candle_context_is_cached_and_forming_m5_is_live(monkeypatch):
    import app as backend_app

    backend_app.PREDICTOR_CANDLE_CACHE.clear()
    calls = []
    monkeypatch.setattr(backend_app.mt5_bridge, "status", lambda: {"connected": True})

    def rates(symbol, timeframe, count):
        calls.append((symbol, timeframe, count))
        return [
            {"time": 1, "open": 99.0, "high": 100.0, "low": 98.0, "close": 99.5},
            {"time": 2, "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.1},
        ]

    monkeypatch.setattr(backend_app.mt5_bridge, "copy_rates", rates)
    first, first_meta = backend_app._predictor_candle_series(
        "XAUUSD", "M5", 90, 0.5, {"price": 100.4}, 1000.0
    )
    second, second_meta = backend_app._predictor_candle_series(
        "XAUUSD", "M5", 90, 0.5, {"price": 101.2}, 1000.25
    )
    assert len(calls) == 1
    assert first_meta["cacheHit"] is False
    assert second_meta["cacheHit"] is True
    assert second[-1]["close"] == 101.2
    assert second[-1]["high"] == 101.2


def test_tick_range_is_inside_mt5_ipc_guard_and_latency_controls_are_packaged():
    bridge = Path("backend/services/mt5_bridge.py").read_text(encoding="utf-8")
    settings = Path("backend/data/settings.json").read_text(encoding="utf-8")
    ui = Path("frontend/dist/early-impulse-settings.js").read_text(encoding="utf-8")
    assert '"copy_rates", "copy_ticks_range", "open_positions"' in bridge
    for key in (
        "earlyIntentPriorityLoopSeconds",
        "earlyIntentTriggerCandleCacheSeconds",
        "earlyIntentContextCandleCacheSeconds",
    ):
        assert f'"{key}"' in settings
        assert key in ui
