from __future__ import annotations

import copy
import inspect
import time
from types import SimpleNamespace

import pytest

import app
from services import ai_reviewer, ai_strategy_gen, chart_render, decision_engine, trade_context
from services.live_execution import ExposureValidator
from services.pyramiding import AIPyramidingEngine
from services.trade_management import MultiTargetTradeManager
from services.mt5_bridge import MT5Bridge
from services.runtime_safety import ExecutionLedger, RuntimeHealth


@pytest.fixture
def manager_harness(monkeypatch):
    settings = copy.deepcopy(app._default_settings())
    settings["trading"]["tradeManagement"].update(
        {
            "conditionalTimeStopEnabled": True,
            "partialTakeProfit": False,
            "tpPushEnabled": False,
            "autoBreakEven": True,
            "autoTrailing": True,
        }
    )
    settings["automation"].update(
        {
            "recoveryMonitorEnabled": False,
            "dynamicSlEnabled": True,
            "mql5ControlFilePath": "",
        }
    )
    positions: list[dict] = []
    market = {"symbol": "XAUUSD", "price": 4041.50, "atr14": 8.0, "spread": 0.20}
    mutations: list[tuple[str, dict, str]] = []
    notifications: list[tuple] = []
    controls: list[str] = []

    monkeypatch.setattr(app, "SETTINGS_STATE", settings)
    monkeypatch.setattr(app, "POSITION_PROTECTION_STATE", {})
    # Keep each management test independent from predictor/candle state produced by
    # earlier tests. Production caches are time bounded, but test cases run inside the
    # same sub-second TTL and otherwise contaminate each other's management context.
    monkeypatch.setattr(app, "PREDICTOR_CANDLE_CACHE", {})
    monkeypatch.setattr(app, "PREDICTOR_TICK_BUFFERS", {})
    monkeypatch.setattr(app, "PREDICTOR_TICK_LAST_FETCH_MSC", {})
    monkeypatch.setattr(app, "PREDICTOR_TICK_LAST_BACKFILL_AT", {})
    monkeypatch.setattr(app, "FAST_SNIPER_STATE", {"earlyIntent": {}, "earlyImpulse": {}})
    monkeypatch.setattr(
        app,
        "RECAP_STATE",
        {"lastCloseReconcile": time.time(), "lastProtSave": time.time()},
    )
    monkeypatch.setattr(app, "AUTO_TRADE_STATE", {"protectedBurstActiveCampaign": {}})
    monkeypatch.setattr(app, "RUNTIME_HEALTH", RuntimeHealth())
    monkeypatch.setattr(app.mt5_bridge, "open_positions", lambda bot_only=True: positions)
    monkeypatch.setattr(app.mt5_bridge, "closed_bot_trades", lambda days=1: [])
    monkeypatch.setattr(
        app.mt5_bridge,
        "symbol_specs",
        lambda symbol: {
            "tickSize": 0.01,
            "tradeTickSize": 0.01,
            "point": 0.01,
            "digits": 2,
            "minStopDistance": 0.10,
            "volumeMin": 0.01,
            "volumeStep": 0.01,
        },
    )
    monkeypatch.setattr(app, "_live_market", lambda: dict(market))
    monkeypatch.setattr(app, "_live_account", lambda: {"equity": 1000.0, "balance": 1000.0})
    monkeypatch.setattr(
        app.trade_manager,
        "live_management_decision",
        lambda ctx: {"action": "HOLD", "reason": "test"},
    )
    monkeypatch.setattr(app.trade_context, "get", lambda *args, **kwargs: {})
    monkeypatch.setattr(app, "_decision", lambda: {"reason": "test"})
    monkeypatch.setattr(app, "_cached_decision", lambda: {})
    monkeypatch.setattr(app, "_push_notification", lambda *args, **kwargs: notifications.append(args))
    monkeypatch.setattr(app, "_telegram_rich_trade_alert", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_management_alert", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_write_mql5_control", lambda lines: controls.__setitem__(slice(None), list(lines)))
    monkeypatch.setattr(app, "_save_protection_state", lambda: None)

    def execute(operation: str, payload: dict, source: str) -> dict:
        mutations.append((operation, dict(payload), source))
        confirmed = {"ticket": payload.get("ticket")}
        if payload.get("sl") is not None:
            confirmed["sl"] = payload["sl"]
        if payload.get("tp") is not None:
            confirmed["tp"] = payload["tp"]
        return {"ok": True, "readbackConfirmed": True, "confirmedPosition": confirmed}

    monkeypatch.setattr(app, "_execute_mt5_mutation_serialized", execute)
    return {
        "settings": settings,
        "positions": positions,
        "market": market,
        "mutations": mutations,
        "notifications": notifications,
        "controls": controls,
    }


def _screenshot_sell(ticket: int = 777001) -> dict:
    return {
        "ticket": ticket,
        "symbol": "XAUUSD",
        "direction": "SELL",
        "entryPrice": 4050.55,
        "currentPrice": 4041.50,
        "sl": 4053.65,
        "tp": 0.0,
        "lots": 0.01,
        "comment": "GODMODE_manual",
        "openTime": time.time() - 60,
    }


def test_full_manager_locks_the_screenshot_sell_without_crashing(manager_harness):
    manager_harness["positions"].append(_screenshot_sell())

    app._auto_manage_open_trades()

    assert not [m for m in manager_harness["mutations"] if m[0] == "MODIFY_SL"]
    directives = [line.split(",") for line in manager_harness["controls"]]
    protect = next(parts for parts in directives if parts[0] == "777001" and parts[1] == "PROTECT")
    assert float(protect[2]) == pytest.approx(4045.1)
    state = app.POSITION_PROTECTION_STATE["777001"]
    assert state["beMoved"] is False  # becomes true only after broker readback confirms the EA mutation
    assert state["pendingDirective"]["command"] == "PROTECT"
    assert state["protectionArmed"] is True
    assert state["peakDist"] == pytest.approx(9.05)
    assert app.RUNTIME_HEALTH.snapshot()["trade_protection"]["ok"] is True
    assert not any(note and note[0] == "Protection loop error" for note in manager_harness["notifications"])


def test_recorded_peak_is_reprotected_after_retrace(manager_harness):
    position = _screenshot_sell(777002)
    position["currentPrice"] = 4048.50
    manager_harness["market"]["price"] = 4048.50
    manager_harness["positions"].append(position)
    app.POSITION_PROTECTION_STATE["777002"] = {
        "beMoved": False,
        "trailLevel": 0.0,
        "alertedOpen": True,
        "counterTrend": False,
        "contextLabel": "",
        "riskBasis": 3.10,
        "peakR": 2.91,
        "peakDist": 9.05,
        "protectionArmed": True,
        "firstSeenTs": time.time() - 120,
    }

    app._auto_manage_open_trades()

    assert not [m for m in manager_harness["mutations"] if m[0] == "MODIFY_SL"]
    directives = [line.split(",") for line in manager_harness["controls"]]
    protect = next(parts for parts in directives if parts[0] == "777002" and parts[1] == "PROTECT")
    target = float(protect[2])
    # The old 4044.94 peak floor is no longer on the legal side of market.
    # Python emits the nearest legal profitable policy target; Tick Guard alone mutates MT5.
    assert target == pytest.approx(4048.60)
    assert target < position["entryPrice"]
    assert target > manager_harness["market"]["price"]


def test_one_bad_position_does_not_abort_protection_for_the_rest(manager_harness):
    manager_harness["positions"].extend(
        [
            {**_screenshot_sell(1), "entryPrice": "not-a-number"},
            _screenshot_sell(2),
        ]
    )

    app._auto_manage_open_trades()

    directives = [line.split(",") for line in manager_harness["controls"]]
    assert any(parts[0] == "2" and parts[1] == "PROTECT" for parts in directives)
    assert not any(operation == "MODIFY_SL" for operation, _payload, _source in manager_harness["mutations"])
    health = app.RUNTIME_HEALTH.snapshot()["trade_protection"]
    assert health["ok"] is False
    assert "1" in health["detail"]


def test_rejected_known_outcome_can_retry_same_protective_command(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.sqlite")
    command = {"operation": "MODIFY_SL", "ticket": 7, "sl": 4044.94}
    accepted, key, _ = ledger.begin(command, "management_trailing")
    assert accepted
    ledger.finish(key, {"ok": False, "message": "Invalid stops", "request": command})

    retry, retry_key, prior = ledger.begin(command, "management_trailing")

    assert retry is True
    assert retry_key == key
    assert prior and prior["recovered"] is True


def test_mutation_readback_verifies_preflight_adjusted_stop(monkeypatch, tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.sqlite")
    position = {"ticket": 88, "symbol": "XAUUSD", "sl": 4045.00, "tp": 0.0, "lots": 0.01}
    monkeypatch.setattr(app, "EXECUTION_LEDGER", ledger)
    monkeypatch.setattr(app.mt5_bridge, "open_positions", lambda bot_only=False: [position])
    monkeypatch.setattr(
        app.mt5_bridge,
        "modify_position",
        lambda payload: {
            "ok": True,
            "mt5Request": {"position": 88, "sl": 4045.00, "tp": 0.0},
            "result": {"retcode": 10009},
        },
    )
    monkeypatch.setattr(app.mt5_bridge, "symbol_specs", lambda symbol: {"tickSize": 0.01})

    result = app._execute_mt5_mutation_serialized(
        "MODIFY_SL",
        {"ticket": 88, "sl": 4044.94},
        "test_adjusted_stop",
    )

    assert result["ok"] is True
    assert result["readbackConfirmed"] is True
    assert result["confirmedPosition"]["sl"] == 4045.00


def test_stale_stop_decision_is_rejected_before_broker_submission(monkeypatch, tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.sqlite")
    position = {"ticket": 89, "symbol": "XAUUSD", "sl": 4045.00, "tp": 0.0, "lots": 0.01}
    monkeypatch.setattr(app, "EXECUTION_LEDGER", ledger)
    monkeypatch.setattr(app.mt5_bridge, "open_positions", lambda bot_only=False: [position])
    monkeypatch.setattr(
        app.mt5_bridge,
        "modify_position",
        lambda payload: pytest.fail("stale decision reached broker submission"),
    )
    monkeypatch.setattr(app.mt5_bridge, "symbol_specs", lambda symbol: {"tickSize": 0.01})

    result = app._execute_mt5_mutation_serialized(
        "MODIFY_SL",
        {"ticket": 89, "sl": 4044.50, "expectedCurrentSl": 4044.00},
        "test_stale_stop",
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["staleDecision"] is True
    assert ledger.unresolved() == []


def test_reconciliation_uses_retained_preflight_adjusted_stop(monkeypatch, tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.sqlite")
    command = {"operation": "MODIFY_SL", "ticket": 88, "sl": 4044.94}
    accepted, key, _ = ledger.begin(command, "management_trailing")
    assert accepted
    ledger.mark_submitting(key)
    ledger.fail(
        key,
        "broker response lost",
        unknown=True,
        result={"mt5Request": {"position": 88, "sl": 4045.00, "tp": 0.0}},
    )
    row = ledger.get(key)
    assert row and row["status"] == "UNKNOWN"

    monkeypatch.setattr(app, "EXECUTION_LEDGER", ledger)
    monkeypatch.setattr(
        app.mt5_bridge,
        "open_positions",
        lambda bot_only=False: [
            {"ticket": 88, "symbol": "XAUUSD", "sl": 4045.00, "tp": 0.0, "lots": 0.01}
        ],
    )
    monkeypatch.setattr(app.mt5_bridge, "symbol_specs", lambda symbol: {"tickSize": 0.01})

    reconciled = app._reconcile_execution_row(row)

    assert reconciled["ok"] is True
    assert reconciled["status"] == "RECONCILED"
    assert reconciled["evidence"]["submittedRequest"]["sl"] == 4045.00


def test_manual_trail_is_persistently_armed_after_confirmation(manager_harness, monkeypatch):
    position = _screenshot_sell(55)
    manager_harness["positions"].append(position)
    monkeypatch.setattr(app.mt5_bridge, "status", lambda: {"connected": True})
    monkeypatch.setattr(
        app.mt5_bridge,
        "market_snapshot",
        lambda symbol, timeframe: {"atr14": 8.0},
    )

    result = app._manual_position_control(55, "TRAIL")

    assert result["ok"] is True
    assert result["requestedSl"] == 4046.70
    assert app.POSITION_PROTECTION_STATE["55"]["manualTrailArmed"] is True
    assert app.POSITION_PROTECTION_STATE["55"]["beMoved"] is True


def test_valid_armed_retest_returns_a_decision_and_consumes_arm(monkeypatch):
    now = time.time()
    app.FAST_SNIPER_RETEST_STATE.clear()
    app.FAST_SNIPER_RETEST_STATE.update(
        {
            "active": True,
            "side": "SELL",
            "extreme": 4050.0,
            "legStart": 4060.0,
            "atr5": 5.0,
            "armedAt": now - 600,
            "armedReason": "test impulse",
            "barsObserved": 1,
            "expiresAt": now + 600,
        }
    )
    settings = copy.deepcopy(app.SETTINGS_STATE)
    settings.setdefault("automation", {}).update(
        {
            "fastSniperRetestTrackerEnabled": True,
            "fastSniperRetestFibMin": 0.12,
            "fastSniperRetestFibMax": 0.58,
            "fastSniperRetestMinBodyAtr": 0.12,
            "fastSniperRetestMaxOvershoot": 0.08,
            "fastSniperRetestMaxTriggerBodyAtr": 1.10,
            "fastSniperRetestMinBarsAfterArm": 2,
            "fastSniperRetestRequireCounterPullback": True,
        }
    )
    monkeypatch.setattr(app, "SETTINGS_STATE", settings)
    monkeypatch.setattr(
        app,
        "_fast_sniper_mtf_matrix",
        lambda *args, **kwargs: {"score": 0.5, "summary": "aligned"},
    )
    monkeypatch.setattr(app, "_journal_record", lambda *args, **kwargs: None)
    candles = [
        {"open": 4052, "high": 4053, "low": 4051, "close": 4052.2},
        {"open": 4052, "high": 4054, "low": 4051, "close": 4053.5},
        {"open": 4054, "high": 4054.5, "low": 4052.5, "close": 4053.0},
        {"open": 4053, "high": 4053.2, "low": 4052.8, "close": 4053.0},
    ]

    result = app._check_armed_retest(
        candles,
        candles,
        {"price": 4053},
        "XAUUSD",
        5.0,
        50.0,
        time.perf_counter(),
        now,
    )

    assert result and result["action"] == "TAKE_TRADE"
    assert result["contextLabel"] == "retest-continuation"
    assert result["counterTrend"] is False
    assert app.FAST_SNIPER_RETEST_STATE["active"] is False


def test_tick_guard_heartbeat_requires_exact_fresh_attestation(monkeypatch, tmp_path):
    settings = copy.deepcopy(app.SETTINGS_STATE)
    settings.setdefault("automation", {}).update(
        {
            "mql5ControlFilePath": str(tmp_path),
            "requireTickGuardForLive": True,
            "tickGuardHeartbeatFileName": "godmode_tickguard_heartbeat.csv",
        }
    )
    monkeypatch.setattr(app, "SETTINGS_STATE", settings)
    monkeypatch.setattr(app, "RUNTIME_HEALTH", RuntimeHealth())
    heartbeat = tmp_path / "godmode_tickguard_heartbeat.csv"
    heartbeat.write_text(
        f"{int(time.time())},{app.BUILD_ID},{app.mt5_bridge.magic},{app.mt5_bridge.comment_prefix},XAUUSD\n",
        encoding="ascii",
    )

    fresh = app._tick_guard_heartbeat_status()
    assert fresh["ok"] is True

    heartbeat.write_text(
        f"{int(time.time())},{app.BUILD_ID},{app.mt5_bridge.magic},{app.mt5_bridge.comment_prefix},GBPUSD\n",
        encoding="ascii",
    )
    wrong_symbol = app._tick_guard_heartbeat_status()
    assert wrong_symbol["ok"] is False
    assert "symbol" in wrong_symbol["message"]

    heartbeat.write_text(
        f"{int(time.time()) - 60},{app.BUILD_ID},{app.mt5_bridge.magic},{app.mt5_bridge.comment_prefix},XAUUSD\n",
        encoding="ascii",
    )
    stale = app._tick_guard_heartbeat_status()
    assert stale["ok"] is False
    assert "age" in stale["message"]


def test_live_execution_gate_blocks_unattested_tick_guard(monkeypatch):
    settings = copy.deepcopy(app.SETTINGS_STATE)
    settings.setdefault("execution", {}).update({"dryRun": False, "liveTradingEnabled": True})
    monkeypatch.setattr(app, "SETTINGS_STATE", settings)
    monkeypatch.setattr(app.mt5_bridge, "live_enabled", True)
    monkeypatch.setattr(app.EXECUTION_LEDGER, "stale", lambda older_than_seconds=0: [])
    health = RuntimeHealth()
    health.beat("trade_protection")
    health.beat("event_loop")
    monkeypatch.setattr(app, "RUNTIME_HEALTH", health)
    monkeypatch.setattr(app, "_tick_guard_heartbeat_status", lambda: {"ok": False, "required": True})
    monkeypatch.setattr(app, "_validation_status", lambda: {"passed": True})

    result = app._execution_validation_check("test")

    assert result["ok"] is False
    assert result["blocked"] is True
    assert "Tick Guard" in result["message"]


def test_protection_is_scheduled_before_new_entries():
    source = inspect.getsource(app._auto_trading_loop)
    assert source.index("auto_manage_open_trades") < source.index('auto_trade_tick')


def test_sltp_preflight_contains_tick_and_freeze_adjustment():
    source = inspect.getsource(MT5Bridge._preflight)
    assert "is_sltp" in source
    assert "trade_freeze_level" in source
    assert 'adjustments["sl"]' in source


def test_winner_recovery_verdict_is_isolated_per_ticket(manager_harness, monkeypatch):
    # This regression exercises the legacy compatibility path explicitly. V15.2.8
    # deterministic intelligence is authoritative by default and intentionally ignores
    # the legacy assessor when enabled.
    manager_harness["settings"]["trading"]["tradeManagement"]["deterministicExitIntelligenceEnabled"] = False
    first = {**_screenshot_sell(9101), "sl": 4043.00}
    second = {**_screenshot_sell(9102), "sl": 4053.65}
    manager_harness["positions"].extend([first, second])
    monkeypatch.setattr(
        app,
        "assess_continuation",
        lambda *args, **kwargs: {
            "continuationScore": 1.0,
            "invalidated": True,
            "reasons": ["first ticket invalidated"],
        },
    )
    verdicts: list[tuple[int, float, bool]] = []

    def capture_v14(**kwargs):
        verdicts.append(
            (
                int(kwargs["pos"]["ticket"]),
                float(kwargs["recovery_score"]),
                bool(kwargs["invalidated"]),
            )
        )
        return SimpleNamespace(
            blocked=False,
            error=None,
            proposed_sl=kwargs["desired_sl"],
            to_dict=lambda: {},
        )

    monkeypatch.setattr(app, "_v14_dynamic_sl_decision", capture_v14)

    app._auto_manage_open_trades()

    assert verdicts[0] == (9101, 1.0, True)
    assert verdicts[1] == (9102, 50.0, False)


def test_management_partial_closes_use_distinct_durable_execution_ids(manager_harness):
    manager_harness["settings"]["trading"]["tradeManagement"]["partialTakeProfit"] = True
    position = {
        **_screenshot_sell(9201),
        "lots": 0.04,
        "currentPrice": 4047.40,
    }
    manager_harness["positions"].append(position)
    manager_harness["market"]["price"] = 4047.40

    app._auto_manage_open_trades()
    position["lots"] = 0.03
    position["currentPrice"] = 4044.90
    manager_harness["market"]["price"] = 4044.90
    app._auto_manage_open_trades()

    partial_payloads = [
        payload
        for operation, payload, source in manager_harness["mutations"]
        if operation == "PARTIAL_CLOSE" and source == "management_partial_close"
    ]
    assert len(partial_payloads) == 2
    assert partial_payloads[0]["executionId"]
    assert partial_payloads[1]["executionId"]
    assert partial_payloads[0]["executionId"] != partial_payloads[1]["executionId"]


def test_public_settings_redact_every_known_secret():
    settings = copy.deepcopy(app._default_settings())
    for dotted in app.SETTINGS_SECRET_PATHS:
        node = settings
        parts = dotted.split(".")
        for key in parts[:-1]:
            node = node.setdefault(key, {})
        node[parts[-1]] = f"secret-{dotted}"

    public = app._safe_public_settings(settings)

    for dotted in app.SETTINGS_SECRET_PATHS:
        node = public
        parts = dotted.split(".")
        for key in parts[:-1]:
            node = node[key]
        assert node[parts[-1]] == ""


def test_disconnected_dry_run_readiness_does_not_require_reconciliation(monkeypatch):
    monkeypatch.setattr(
        app.mt5_bridge,
        "status",
        lambda: {"connected": False, "liveTradingEnabled": False},
    )
    monkeypatch.setattr(app, "_market_state", lambda: {"open": True})
    monkeypatch.setattr(app.EXECUTION_LEDGER, "unresolved", lambda: [])
    monkeypatch.setattr(
        app.RUNTIME_HEALTH,
        "snapshot",
        lambda *args, **kwargs: {
            "reconciliation": {"ok": False, "stale": False, "detail": "MT5 disconnected"}
        },
    )
    monkeypatch.setattr(app, "_validation_status", lambda: {"enabled": False, "passed": False})
    monkeypatch.setattr(app.kill_switch, "status", lambda: {"active": False})

    readiness = app._authoritative_readiness()

    assert readiness["ready"] is True
    assert readiness["tradingReady"] is False
    assert "MT5 not connected" in readiness["warnings"]


def test_cold_decision_refresh_acquires_and_releases_its_lock(monkeypatch):
    reports: list[tuple] = []
    monkeypatch.setattr(app, "_DECISION_CACHE", {})
    monkeypatch.setattr(app, "_DECISION_CACHE_TS", 0.0)
    monkeypatch.setattr(app, "_live_market", lambda: {"connected": False})
    monkeypatch.setattr(app, "_market_state", lambda: {"open": True, "reason": "Open"})
    monkeypatch.setattr(app, "_report_suppressed_exception", lambda *args: reports.append(args))

    result = app._cached_decision()

    assert result["action"] == "WAIT"
    assert app._DECISION_REFRESH_LOCK.locked() is False
    assert reports == []


def test_missing_spread_is_an_expected_noop(monkeypatch):
    reports: list[tuple] = []
    monkeypatch.setattr(app, "_report_suppressed_exception", lambda *args: reports.append(args))

    app._note_spread(None)

    assert reports == []


def test_multi_target_execution_runs_shared_entry_risk_gate(monkeypatch):
    payload = {
        "executionId": "multi-target-risk-gate-test",
        "symbol": "XAUUSD",
        "side": "BUY",
        "price": 4050.0,
        "sl": 4040.0,
        "volume": 0.04,
    }
    calls: list[tuple[dict, str]] = []
    monkeypatch.setattr(
        app,
        "_protected_entry_payload",
        lambda candidate, source: (
            calls.append((dict(candidate), source)) or {},
            {"ok": False, "blocked": True, "message": "risk ceiling unavailable"},
        ),
    )
    monkeypatch.setattr(
        app,
        "_execute_mt5_multi_serialized",
        lambda *args, **kwargs: pytest.fail("broker path bypassed shared entry gate"),
    )

    result = app.execute_multi_target(payload)

    assert calls and calls[0][1] == "multi_target"
    assert result["blocked"] is True


def test_multi_target_plan_rejects_missing_or_invalid_geometry():
    manager = MultiTargetTradeManager()

    missing = manager.build_child_orders({"volume": 0.04})
    invalid_side = manager.build_child_orders(
        {"side": "WAIT", "entry": 4050.0, "sl": 4040.0, "volume": 0.04}
    )
    invalid_stop = manager.build_child_orders(
        {"side": "BUY", "entry": 4050.0, "sl": 4060.0, "volume": 0.04}
    )

    assert missing["ok"] is False
    assert invalid_side["ok"] is False
    assert invalid_stop["ok"] is False


def test_exposure_validator_fails_closed_without_live_evidence():
    result = ExposureValidator().validate_pyramid({})

    assert result["allowed"] is False
    assert result["blocks"]


def test_pyramiding_engine_fails_closed_when_confirmation_evidence_is_missing():
    engine = AIPyramidingEngine()
    result = engine.evaluate(
        {"action": "TAKE_TRADE", "quality": "SNIPER", "confidence": 100},
        position={
            "profitR": 3.0,
            "beMoved": True,
            "winsSinceLastLoss": 5,
            "currentLots": 0.01,
            "marginLevelPct": 1000,
        },
        market={"spread": 0.01},
        broker_quality={"score": 100},
        kill_switch={"active": False},
    )

    assert result["allowed"] is False
    assert any("structure" in reason.lower() or "retest" in reason.lower() for reason in result["blocks"])


def test_pyramid_execution_uses_real_broker_position_not_forged_payload(monkeypatch):
    calls: list[bool] = []
    monkeypatch.setattr(
        app.mt5_bridge,
        "open_positions",
        lambda bot_only=True: calls.append(bot_only) or [],
    )

    result = app.pyramiding_execute(
        {
            "executionId": "forged-pyramid-context",
            "position": {
                "direction": "BUY",
                "profitR": 99,
                "beMoved": True,
                "winsSinceLastLoss": 99,
            },
            "market": {
                "price": 4050,
                "cleanlinessScore": 100,
                "trendAlignmentScore": 100,
                "liquidityRoomScore": 100,
            },
            "decision": {"action": "TAKE_TRADE", "side": "BUY", "quality": "SNIPER", "confidence": 100},
        }
    )

    assert calls
    assert result["blocked"] is True
    assert "active" in result["message"].lower()


def test_legacy_real_pyramid_endpoint_delegates_to_protected_path(monkeypatch):
    monkeypatch.setattr(
        app,
        "pyramiding_execute",
        lambda payload: {"ok": False, "blocked": True, "marker": payload["executionId"]},
    )

    result = app.pyramid_execute_real({"executionId": "legacy-safe-delegation"})

    assert result == {"ok": False, "blocked": True, "marker": "legacy-safe-delegation"}


def test_live_entry_blocks_when_risk_sizing_has_no_authoritative_inputs(monkeypatch):
    monkeypatch.setattr(app.mt5_bridge, "live_enabled", True)
    monkeypatch.setattr(
        app,
        "_safe_entry_lot",
        lambda *args, **kwargs: {
            "lot": 0.01,
            "untradeableAtBrokerMinimum": False,
            "riskCeiling": {"source": "fallback_no_inputs"},
        },
    )

    order, error = app._protected_entry_payload(
        {
            "executionId": "risk-evidence-required",
            "symbol": "XAUUSD",
            "side": "BUY",
            "price": 4050,
            "sl": 4040,
            "tp": 4070,
            "volume": 0.01,
        },
        "test",
    )

    assert order is None
    assert error and error["blocked"] is True
    assert "risk" in error["message"].lower()


@pytest.mark.parametrize(
    "module",
    [ai_strategy_gen, decision_engine, ai_reviewer, chart_render, trade_context],
)
def test_service_exception_paths_have_a_real_logging_import(module):
    assert hasattr(module, "logging")


def _runner_rows(start: float, step: float, count: int = 40) -> list[dict]:
    rows = []
    price = start
    for idx in range(count):
        close = price + step
        rows.append({
            "open": price,
            "high": max(price, close) + 0.25,
            "low": min(price, close) - 0.25,
            "close": close,
            "time": idx,
        })
        price = close
    return rows


def test_full_manager_preemptively_breathes_a_clean_confirmed_runner(manager_harness, monkeypatch):
    position = _screenshot_sell(777008)
    position.update({"currentPrice": 4041.50, "sl": 4042.00, "openTime": time.time() - 240})
    manager_harness["positions"].append(position)
    app.POSITION_PROTECTION_STATE["777008"] = {
        "beMoved": True,
        "trailLevel": 4042.0,
        "alertedOpen": True,
        "counterTrend": False,
        "contextLabel": "",
        "riskBasis": 3.10,
        "peakR": 3.87,
        "peakDist": 12.0,
        "protectionArmed": True,
        "firstSeenTs": time.time() - 240,
        "lastBrokerSl": 4042.0,
        "brokerProfitStopConfirmed": True,
        "anticipatoryStage": "CONFIRMED",
    }
    m5 = _runner_rows(4058.0, -0.42)
    m15 = _runner_rows(4070.0, -0.62, 30)

    def predictor_rows(_symbol, timeframe, _count, _ttl, _market, _now):
        return (m5 if timeframe == "M5" else m15), {"cacheHit": True}

    monkeypatch.setattr(app, "_predictor_candle_series", predictor_rows)
    monkeypatch.setattr(app, "FAST_SNIPER_STATE", {
        "earlyIntent": {"side": "SELL", "stage": "INTENT", "probability": 0.80},
        "earlyImpulse": {"side": "SELL", "stage": "CONFIRMED", "probability": 0.88},
    })
    monkeypatch.setattr(app, "_cached_decision", lambda: {
        "side": "SELL", "symbol": "XAUUSD", "_generatedAt": time.time(),
        "features": {"computedSide": "SELL", "htfDailyBias": "SELL"},
    })

    app._auto_manage_open_trades()

    directives = [line.split(",") for line in manager_harness["controls"]]
    breathe = next(parts for parts in directives if parts[0] == "777008" and parts[1] == "BREATH")
    target = float(breathe[2])
    assert position["sl"] < target < position["entryPrice"]
    state = app.POSITION_PROTECTION_STATE["777008"]
    assert state["exitIntelligence"]["phase"] == "RUNNER"
    assert state["pendingBreath"]["reason"] == "preemptive runner room"


def test_deterministic_exit_intelligence_cannot_be_overridden_by_legacy_recovery(manager_harness, monkeypatch):
    position = {**_screenshot_sell(9301), "sl": 4042.00}
    manager_harness["positions"].append(position)

    deterministic = SimpleNamespace(
        phase="DEFENSIVE",
        action="HOLD",
        continuation_score=20.0,
        invalidated=False,
        protection_armed=True,
        allow_widen=False,
        recommended_sl=None,
        max_giveback_fraction=0.28,
        trail_atr=0.28,
        reason_codes=("RECENT_M5_STRUCTURE_INVALIDATED",),
        as_dict=lambda: {
            "phase": "DEFENSIVE",
            "action": "HOLD",
            "continuation_score": 20.0,
            "invalidated": False,
            "reason_codes": ["RECENT_M5_STRUCTURE_INVALIDATED"],
        },
    )
    monkeypatch.setattr(app, "evaluate_exit_intelligence", lambda **kwargs: deterministic)
    monkeypatch.setattr(
        app,
        "assess_continuation",
        lambda *args, **kwargs: {
            "continuationScore": 99.0,
            "invalidated": False,
            "reasons": ["legacy optimistic"],
        },
    )
    verdicts = []

    def capture_v14(**kwargs):
        verdicts.append((kwargs["recovery_score"], kwargs["invalidated"]))
        return SimpleNamespace(blocked=False, error=None, proposed_sl=kwargs["desired_sl"], to_dict=lambda: {})

    monkeypatch.setattr(app, "_v14_dynamic_sl_decision", capture_v14)
    app._auto_manage_open_trades()

    assert verdicts
    assert verdicts[0] == (20.0, False)


def test_high_score_alone_cannot_widen_without_runner_breathe_action(manager_harness, monkeypatch):
    position = {**_screenshot_sell(9302), "sl": 4042.00}
    manager_harness["positions"].append(position)

    deterministic = SimpleNamespace(
        phase="DEVELOPING",
        action="HOLD",
        continuation_score=90.0,
        invalidated=False,
        protection_armed=True,
        allow_widen=False,
        recommended_sl=None,
        max_giveback_fraction=0.45,
        trail_atr=0.65,
        reason_codes=("PHASE_DEVELOPING",),
        as_dict=lambda: {
            "phase": "DEVELOPING",
            "action": "HOLD",
            "continuation_score": 90.0,
            "invalidated": False,
            "reason_codes": ["PHASE_DEVELOPING"],
        },
    )
    monkeypatch.setattr(app, "evaluate_exit_intelligence", lambda **kwargs: deterministic)
    app._auto_manage_open_trades()

    directives = [line.split(",") for line in manager_harness["controls"]]
    assert not any(parts[0] == "9302" and parts[1] in {"BREATH", "RECOVER"} for parts in directives)
