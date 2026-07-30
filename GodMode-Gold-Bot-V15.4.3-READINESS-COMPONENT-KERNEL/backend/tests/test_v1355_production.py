"""V13.55 production-remediation acceptance tests.

These tests target the safety boundaries added during the V13.52/V13.54 merge:
stable execution identity, protected manual/UI entries, authenticated Telegram
controls, Tick Guard restart safety, and coherent production artifacts.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import app
from services.runtime_safety import ExecutionLedger


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
EA = ROOT / "mt5_ea" / "GodModeTickGuard.mq5"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def test_v1355_build_attestation_is_exact_across_all_components():
    assert app.APP_VERSION == "15.4.3"
    expected = "V15.4.3-READINESS-COMPONENT-KERNEL"
    assert app.BUILD_ID == expected
    frontend = _read(FRONTEND / "src" / "lib" / "api.ts")
    frontend_id = re.search(r"FRONTEND_BUILD_ID\s*=\s*'([^']+)'", frontend)
    assert frontend_id and frontend_id.group(1) == expected
    ea = _read(EA)
    ea_id = re.search(r'ExpectedEngineBuild\s*=\s*"([^"]+)"', ea)
    assert ea_id and ea_id.group(1) == expected
    assert re.search(r'#property\s+version\s+"15\.043"', ea)


def test_frontend_production_bundle_exists_and_is_not_source_placeholder():
    index = FRONTEND / "dist" / "index.html"
    assert index.exists()
    html = _read(index)
    assets = re.findall(r"/assets/[^\"']+", html)
    assert assets, "production index does not reference a built asset"
    assert all((FRONTEND / "dist" / asset.lstrip("/")).exists() for asset in assets)


def test_explicit_retry_is_deduped_across_entry_channels(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.sqlite")
    payload = {
        "operation": "OPEN",
        "executionId": "shared-command-001",
        "symbol": "XAUUSD",
        "side": "BUY",
        "volume": 0.01,
    }
    accepted, key, _ = ledger.begin(payload, "telegram")
    assert accepted
    ledger.finish(key, {"ok": True, "ticket": 12})
    retry, retry_key, prior = ledger.begin(payload, "ui-manual")
    assert not retry
    assert retry_key == key
    assert prior["result"]["ticket"] == 12


def test_identical_payloads_with_distinct_explicit_ids_are_both_legitimate(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.sqlite")
    base = {"operation": "OPEN", "symbol": "XAUUSD", "side": "SELL", "volume": 0.01}
    first, first_key, _ = ledger.begin({**base, "executionId": "decision-001"}, "auto")
    second, second_key, _ = ledger.begin({**base, "executionId": "decision-002"}, "auto")
    assert first and second
    assert first_key != second_key


def test_gateway_fails_closed_when_execution_identity_is_missing():
    result = app._execute_mt5_serialized(
        {"operation": "OPEN", "symbol": "XAUUSD", "side": "BUY", "volume": 0.01},
        "test",
    )
    assert result["ok"] is False
    assert result["blocked"] is True
    assert "executionid" in result["message"].lower()


def test_protected_manual_entry_requires_directional_stop(monkeypatch):
    monkeypatch.setattr(app, "_live_market", lambda: {"symbol": "XAUUSD", "price": 2400.0, "side": "BUY"})
    bad, error = app._protected_entry_payload(
        {"side": "BUY", "price": 2400.0, "sl": 2401.0, "tp": 2410.0, "volume": 5.0},
        "test",
    )
    assert bad is None
    assert error and error["blocked"] is True


def test_protected_manual_entry_applies_shared_risk_cap(monkeypatch):
    monkeypatch.setattr(app, "_live_market", lambda: {"symbol": "XAUUSD", "price": 2400.0, "side": "BUY"})
    monkeypatch.setattr(app, "_live_account", lambda: {"equity": 10_000.0, "balance": 10_000.0})
    monkeypatch.setattr(
        app.mt5_bridge,
        "symbol_specs",
        lambda _symbol: {
            "volumeMin": 0.01,
            "volumeStep": 0.01,
            "volumeMax": 100.0,
            "tradeTickValue": 1.0,
            "tradeTickSize": 0.01,
            "source": "test",
        },
    )
    protected, error = app._protected_entry_payload(
        {
            "executionId": "manual-risk-test",
            "side": "BUY",
            "price": 2400.0,
            "sl": 2390.0,
            "tp": 2420.0,
            "volume": 5.0,
        },
        "test",
    )
    assert error is None
    assert protected is not None
    assert protected["volume"] <= protected["sizingGuard"]["capLot"]
    assert protected["sizingGuard"]["capped"] is True


def test_protected_entry_blocks_when_broker_minimum_exceeds_risk_budget(monkeypatch):
    monkeypatch.setattr(app, "_live_market", lambda: {"symbol": "XAUUSD", "price": 2400.0, "side": "BUY"})
    monkeypatch.setattr(app, "_live_account", lambda: {"equity": 100.0, "balance": 100.0})
    monkeypatch.setattr(
        app.mt5_bridge,
        "symbol_specs",
        lambda _symbol: {
            "volumeMin": 0.01,
            "volumeStep": 0.01,
            "volumeMax": 100.0,
            "tradeTickValue": 1.0,
            "tradeTickSize": 0.01,
            "source": "test",
        },
    )
    protected, error = app._protected_entry_payload(
        {
            "executionId": "manual-too-risky-at-minimum",
            "side": "BUY",
            "price": 2400.0,
            "sl": 2300.0,
            "tp": 2600.0,
            "volume": 0.01,
        },
        "test",
    )
    assert protected is None
    assert error and error["blocked"] is True
    assert error["sizingGuard"]["untradeableAtBrokerMinimum"] is True


def test_telegram_chat_authorization_covers_messages_and_callbacks():
    configured = "123456"
    assert app._telegram_update_is_authorized({"message": {"chat": {"id": 123456}}}, configured)
    assert app._telegram_update_is_authorized(
        {"callback_query": {"message": {"chat": {"id": 123456}}}},
        configured,
    )
    assert not app._telegram_update_is_authorized({"message": {"chat": {"id": 999}}}, configured)
    assert not app._telegram_update_is_authorized({}, configured)


def test_manual_telegram_and_position_controls_are_exposed():
    source = _read(BACKEND / "app.py")
    for command in ('startswith("/buy ")', 'startswith("/sell ")', 'startswith("/be ")', 'startswith("/trail ")'):
        assert command in source
    assert "CONFIRM MANUAL TRADE" in source
    routes = {route.path for route in app.app.routes}
    assert "/api/trades/break-even" in routes
    assert "/api/trades/modify-trailing-stop" in routes


def test_tick_guard_resets_sequence_before_restart_validation():
    source = _read(EA)
    assert "void ResetSequenceGlobals()" in source
    engine_transition = source.index('if(g_activeEngine=="" || g_activeEngine!=engine)')
    reset = source.index("ResetSequenceGlobals();", engine_transition)
    sequence_comparison = source.index("if(seq<lastSeq)", engine_transition)
    assert reset < sequence_comparison, "restart ownership must reset sequence state before sequence comparison"
    quantize = source.index("target=QuantizePrice(sym,target);")
    final_safety = source.index("bool correctCurrentSide", quantize)
    final_profit = source.index("bool profitable", final_safety)
    final_tighten = source.index("bool improves", final_profit)
    modify = source.index("trade.PositionModify", final_tighten)
    assert quantize < final_safety < final_profit < final_tighten < modify
    assert re.search(r"void\s+OnDeinit\s*\([^)]*\)\s*\{", source), "EA deinit handler must have a function body"


def test_readiness_client_parses_degraded_503_payload_before_transport_failure():
    source = _read(FRONTEND / "src" / "lib" / "api.ts")
    request = source[source.index("async function request"):source.index("function offline")]
    assert "await res.json()" in request
    assert request.index("await res.json()") < request.index("if (!res.ok")
    assert "AUTH_REQUIRED" in request
    assert "path !== '/api/readiness'" in request


def test_packaged_breathing_settings_are_consistent():
    settings = json.loads(_read(BACKEND / "data" / "settings.json"))
    management = settings["trading"]["tradeManagement"]
    assert management["profitLockFraction"] == 0.62
    assert management["aiDynamicMaxGivebackFraction"] == 0.45
    assert management["aiDynamicRecoveryScoreToBreathe"] == 70
    assert max(management["aiDynamicMinLockFraction"], 1.0 - management["aiDynamicMaxGivebackFraction"]) == 0.55
