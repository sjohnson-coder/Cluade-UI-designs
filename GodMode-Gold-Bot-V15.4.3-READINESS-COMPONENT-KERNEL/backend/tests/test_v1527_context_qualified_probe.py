from __future__ import annotations

import copy

import pytest


def _candles(start: float, steps: list[float]) -> list[dict]:
    rows = []
    price = start
    for i, step in enumerate(steps):
        open_ = price
        close = price + step
        high = max(open_, close) + 0.18
        low = min(open_, close) - 0.18
        rows.append({"time": 1_700_000_000 + i * 300, "open": open_, "high": high, "low": low, "close": close})
        price = close
    return rows


def test_context_gate_allows_first_expansion_with_m5_and_m15_support():
    from services.intent_context import qualify_intent_context

    m5 = _candles(4000.0, [0.05, -0.03, 0.04, -0.02, 0.03, 0.02, -0.01, 0.04, -0.02, 0.03, 0.02, -0.01, 0.04, 0.03, -0.02, 0.05, -0.01, 0.04, -0.02, 0.03, 0.10, 0.18, 0.26, 0.34, 0.42])
    m15 = _candles(3990.0, [0.2] * 28)
    result = qualify_intent_context(
        side="BUY",
        m5_candles=m5,
        m15_candles=m15,
        atr=4.0,
        intent={"structure_score": 0.85, "reversal_penalty": 0.05, "acceleration_score": 0.80},
        config={"minScore": 0.55, "maxLegMoveAtr": 1.45, "maxExtensionAtr": 0.70},
    )
    assert result.allowed is True
    assert result.terminal_acceleration is False
    assert result.score >= 0.55


def test_context_gate_blocks_terminal_sell_acceleration_at_exhaustion_low():
    from services.intent_context import qualify_intent_context

    # Long one-way sell leg, already at the bottom of its recent range with an
    # oversold oscillator profile. A local tick burst here is terminal, not fresh.
    m5 = _candles(4050.0, [-0.4, -0.6, -0.7, -0.8, -0.9, -1.1, -1.2, -1.4, -1.6, -1.8, -2.0, -2.2, -2.4, -2.6, -2.8, -3.0, -3.2, -3.4, -3.6, -3.8, -4.0, -4.2, -4.4, -4.6, -4.8])
    m15 = _candles(4070.0, [-0.5] * 28)
    result = qualify_intent_context(
        side="SELL",
        m5_candles=m5,
        m15_candles=m15,
        atr=4.0,
        intent={"structure_score": 0.90, "reversal_penalty": 0.02, "acceleration_score": 0.95},
        config={"minScore": 0.50, "maxLegMoveAtr": 1.10, "terminalSwingPosition": 0.15, "maxRunBars": 6},
    )
    assert result.allowed is False
    assert result.terminal_acceleration is True
    assert any("terminal" in reason.lower() or "exhaust" in reason.lower() for reason in result.reasons)


def test_probe_stop_blocks_when_structure_requires_more_than_maximum_stop():
    from services.anticipatory_trade import build_probe_stop

    candles = [
        {"open": 4018.0, "high": 4019.0, "low": 4014.0, "close": 4018.5},
        {"open": 4018.5, "high": 4019.2, "low": 4013.0, "close": 4018.8},
        {"open": 4018.8, "high": 4019.4, "low": 4012.5, "close": 4019.0},
    ]
    result = build_probe_stop(
        side="BUY",
        entry=4019.1,
        atr=4.0,
        recent_candles=candles,
        config={"maxStopPoints": 3.5, "minStopPoints": 1.5, "stopAtr": 0.45},
    )
    assert result.allowed is False
    assert result.reason.startswith("structure_requires")


def test_probe_stop_is_tight_and_directionally_valid():
    from services.anticipatory_trade import build_probe_stop

    candles = [
        {"open": 4018.0, "high": 4019.0, "low": 4017.2, "close": 4018.6},
        {"open": 4018.6, "high": 4019.4, "low": 4017.8, "close": 4019.1},
        {"open": 4019.1, "high": 4020.0, "low": 4018.2, "close": 4019.8},
    ]
    result = build_probe_stop(
        side="BUY",
        entry=4020.0,
        atr=4.0,
        recent_candles=candles,
        config={"maxStopPoints": 3.5, "minStopPoints": 1.5, "stopAtr": 0.45},
    )
    assert result.allowed is True
    assert 0 < 4020.0 - result.sl <= 3.5
    assert result.tp1 > 4020.0


def test_broker_minimum_lot_blocks_probe_that_exceeds_probe_risk_budget(monkeypatch):
    import app as backend_app

    monkeypatch.setattr(backend_app, "_live_account", lambda: {"equity": 1000.0, "balance": 1000.0})
    monkeypatch.setattr(
        backend_app.mt5_bridge,
        "symbol_specs",
        lambda symbol: {
            "volumeMin": 0.01,
            "volumeStep": 0.01,
            "volumeMax": 100.0,
            "tradeTickValue": 1.0,
            "tradeTickSize": 0.01,
            "source": "test",
        },
    )
    original = copy.deepcopy(backend_app.SETTINGS_STATE)
    try:
        backend_app.SETTINGS_STATE.setdefault("pyramiding", {}).update({"baseLot": 0.01, "lotStep": 0.01, "maxLot": 0.01, "maxTotalLots": 0.01})
        result = backend_app._safe_entry_lot("XAUUSD", 0.01, 4000.0, 3996.5, "early_intent_probe", risk_pct=0.12)
    finally:
        backend_app.SETTINGS_STATE.clear()
        backend_app.SETTINGS_STATE.update(original)
    assert result["untradeableAtBrokerMinimum"] is True
    assert result["riskCeiling"]["riskPct"] == pytest.approx(0.12)


def test_probe_lifecycle_promotes_only_after_confirmation():
    from services.anticipatory_trade import classify_probe_lifecycle

    probe = classify_probe_lifecycle(
        side="SELL",
        profit_r=0.10,
        intent_state={"side": "SELL", "stage": "INTENT", "probability": 0.75},
        impulse_state={"side": "SELL", "stage": "PROBE", "probability": 0.78},
        config={"confirmProbability": 0.84, "promotionProfitR": 0.35},
    )
    confirmed = classify_probe_lifecycle(
        side="SELL",
        profit_r=0.38,
        intent_state={"side": "SELL", "stage": "INTENT", "probability": 0.76},
        impulse_state={"side": "SELL", "stage": "CONFIRMED", "probability": 0.86},
        config={"confirmProbability": 0.84, "promotionProfitR": 0.35},
    )
    assert probe.stage == "PROBE"
    assert confirmed.stage == "CONFIRMED"


def test_probe_management_cuts_stalled_or_opposite_probe_and_never_widens():
    from services.anticipatory_trade import probe_management_decision

    stalled = probe_management_decision(
        side="BUY",
        stage="PROBE",
        profit_r=-0.05,
        peak_r=0.04,
        age_seconds=50,
        intent_state={"side": "BUY", "stage": "WATCH", "probability": 0.40, "acceleration_score": 0.10},
        impulse_state={"side": None, "stage": "WATCH", "probability": 0.20},
        config={"stallSeconds": 45, "minProgressR": 0.12, "fastFailR": -0.25},
    )
    opposite = probe_management_decision(
        side="SELL",
        stage="PROBE",
        profit_r=-0.08,
        peak_r=0.02,
        age_seconds=12,
        intent_state={"side": "BUY", "stage": "INTENT", "probability": 0.75, "acceleration_score": 0.70},
        impulse_state={"side": "BUY", "stage": "PROBE", "probability": 0.80},
        config={"oppositeProbability": 0.70},
    )
    assert stalled.action == "CUT"
    assert opposite.action == "CUT"
    assert stalled.allow_widen is False
    assert opposite.allow_breathe is False


def test_context_gate_handles_edge_run_without_unbound_extension_threshold():
    from services.intent_context import qualify_intent_context

    # At the range edge and oscillator-exhausted, but not beyond max leg distance.
    # This exercises the run/extension terminal branch and must never raise.
    m5 = _candles(4000.0, [0.02] * 18 + [0.08, 0.10, 0.12, 0.14, 0.16, 0.18, 0.20])
    m15 = _candles(3995.0, [0.10] * 28)
    result = qualify_intent_context(
        side="BUY",
        m5_candles=m5,
        m15_candles=m15,
        atr=4.0,
        intent={"structure_score": 0.90, "reversal_penalty": 0.02, "acceleration_score": 0.90},
        config={"maxLegMoveAtr": 3.0, "maxRunBars": 4, "maxExtensionAtr": 0.20},
    )
    assert isinstance(result.allowed, bool)


def test_probe_runtime_state_clears_legacy_widen_and_breathe_directives():
    from services.anticipatory_trade import sanitize_probe_runtime_state

    state = {
        "pendingDirective": {"command": "RECOVER", "requestedSl": 3990.0},
        "pendingBreath": {"until": 123.0},
        "breathingUntil": 456.0,
        "dynamicRecoveryMode": True,
        "widenCount": 2,
    }
    removed = sanitize_probe_runtime_state(state)
    assert set(removed) >= {"pendingDirective", "pendingBreath", "breathingUntil", "dynamicRecoveryMode"}
    assert "pendingDirective" not in state
    assert "pendingBreath" not in state
    assert state["breathingUntil"] == 0.0
    assert state["dynamicRecoveryMode"] is False
