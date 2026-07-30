from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app.py"
EA = ROOT / "mt5_ea" / "GodModeTickGuard.mq5"


def _function_source(name: str) -> str:
    source = APP.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    return "\n".join(source.splitlines()[node.lineno - 1:node.end_lineno])


def test_management_uses_broker_trade_age_and_live_atr_without_eight_dollar_fallback():
    source = _function_source("_auto_manage_open_trades")
    assert "broker_open_epoch(pos)" in source
    assert "valid_live_atr(market)" in source
    assert 'market.get("atr14") or 8' not in source


def test_v14_wrapper_requires_protection_threshold_activation():
    source = _function_source("_auto_manage_open_trades")
    assert "v14_activation = threshold_activated" in source
    assert "if ai_dynamic_stop and v14_activation and prof_dist > 0:" in source


def test_breathing_requires_broker_confirmed_profitable_stop():
    source = _function_source("_auto_manage_open_trades")
    assert "broker_profit_stop_confirmed(direction, entry, sl, current_price)" in source
    assert "brokerProfitStopConfirmed" in source


def test_peak_and_sl_readback_are_persisted_immediately():
    source = _function_source("_auto_manage_open_trades")
    assert '_persist_protection_event("peak"' in source
    assert '_persist_protection_event("broker_sl_confirmed"' in source


def test_management_no_longer_uses_check_count_timers():
    source = _function_source("_auto_manage_open_trades")
    for name in (
        "dynamicSlRecoverConfirmations",
        "dynamicSlCutConfirmations",
        "dynamicSlCooldownChecks",
        "dynamicSlGraceChecks",
        "dynamicSlMaxHoldChecks",
    ):
        assert name not in source


def test_tick_guard_is_single_actuator_for_fresh_python_policy():
    source = EA.read_text(encoding="utf-8")
    for directive in ('"PROTECT"', '"RECOVER"', '"BREATH"'):
        assert directive in source
    assert "freshOwner" in source
    assert "if(!freshOwner" in source
    assert "brokerConfirmedProfit" in source


def test_default_settings_use_elapsed_seconds_and_require_tick_guard():
    source = _function_source("_default_settings")
    for name in (
        "dynamicSlCooldownSeconds",
        "dynamicSlGraceSeconds",
        "dynamicSlMaxHoldSeconds",
        "dynamicSlRecoverConfirmSeconds",
        "dynamicSlCutConfirmSeconds",
        "dynamicSlDecisionMaxAgeSeconds",
    ):
        assert name in source
    for legacy in ("dynamicSlCooldownChecks", "dynamicSlGraceChecks", "dynamicSlMaxHoldChecks"):
        assert legacy not in source
    assert '"requireTickGuardForLive": True' in source


def test_settings_normalisation_cannot_disable_authoritative_tick_guard():
    source = _function_source("_normalise_settings_candidate")
    assert 'automation["requireTickGuardForLive"] = True' in source


def test_settings_ui_writes_elapsed_seconds_not_loop_counts():
    source = (ROOT / "frontend" / "src" / "pages" / "Settings.tsx").read_text(encoding="utf-8")
    assert "automation.dynamicSlCooldownSeconds" in source
    assert "automation.dynamicSlRecoverConfirmSeconds" in source
    assert "automation.dynamicSlCutConfirmSeconds" in source
    assert "automation.dynamicSlGraceSeconds" in source
    assert "automation.dynamicSlMaxHoldSeconds" in source
    assert "dynamicSlCooldownChecks" not in source


def test_pyramiding_risk_changes_fail_closed_without_live_atr():
    profit_source = _function_source("_position_profit_r")
    pyramid_source = _function_source("_maybe_execute_staged_pyramid_add")
    assert "valid_live_atr(market)" in profit_source
    assert "or 8" not in profit_source
    assert "atr = valid_live_atr(market)" in pyramid_source
    assert "if atr is None:" in pyramid_source


def test_missed_move_route_is_registered_once():
    source = APP.read_text(encoding="utf-8")
    assert source.count('@app.get("/api/journal/missed-pumps")') == 1


def test_all_atr_dependent_risk_increases_fail_closed_without_live_atr():
    burst_source = _function_source("_maybe_execute_protected_burst_add")
    loss_source = _function_source("_loss_feedback_governor")
    auto_source = _function_source("_auto_trade_tick")
    for source in (burst_source, loss_source, auto_source):
        assert "valid_live_atr(market)" in source
        assert 'market.get("atr14") or 8' not in source
        assert 'market.get("atr14") or market.get("atr") or 8.0' not in source
    assert "Live ATR unavailable; Protected Burst blocked" in burst_source
    assert "live_atr_unavailable" in loss_source
    assert "Repeat-setup guard blocked: valid live ATR unavailable" in auto_source


def test_ai_monitor_reports_missing_live_atr_instead_of_inventing_eight_points():
    source = _function_source("ai_monitor_status")
    assert "valid_live_atr(market)" in source
    assert 'market.get("atr14") or 8' not in source
    assert '"reason": "live_atr_unavailable"' in source


def test_missed_move_route_converts_tick_replay_to_broker_native_pnl():
    source = _function_source("journal_missed_pumps")
    assert "mt5_bridge.order_calc_profit" in source
    assert '"replayVolume": 0.01' in source
    assert '"pnlSource"' in source
