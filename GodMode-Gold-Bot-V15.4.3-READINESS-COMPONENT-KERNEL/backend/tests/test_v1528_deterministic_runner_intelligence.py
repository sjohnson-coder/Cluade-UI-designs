from __future__ import annotations

from services.deterministic_exit_intelligence import evaluate_exit_intelligence
from services.anticipatory_trade import classify_probe_lifecycle


def _trend_rows(*, start: float, step: float, count: int = 36, wick: float = 0.35):
    rows = []
    price = start
    for i in range(count):
        close = price + step
        rows.append({
            "open": price,
            "high": max(price, close) + wick,
            "low": min(price, close) - wick,
            "close": close,
            "time": i,
        })
        price = close
    return rows


def _sell_position(**overrides):
    base = {
        "direction": "SELL",
        "entryPrice": 4015.49,
        "currentPrice": 4013.20,
        "sl": 4013.67,
        "riskBasis": 2.86,
        "peakDist": 3.50,
        "profitR": (4015.49 - 4013.20) / 2.86,
        "stage": "CONFIRMED",
        "ageSeconds": 220,
    }
    base.update(overrides)
    return base


def _same_side_predictors(side: str = "SELL"):
    return (
        {"side": side, "stage": "INTENT", "probability": 0.78, "persistence_score": 0.82, "acceleration_score": 0.68},
        {"side": side, "stage": "CONFIRMED", "probability": 0.87, "persistence_score": 0.84, "acceleration_score": 0.61},
    )


def test_clean_confirmed_sell_runner_gets_wider_profitable_breathing_room():
    m5 = _trend_rows(start=4030.0, step=-0.42)
    # Preserve a realistic pullback near the end without destroying the clean broader leg.
    m5[-4:] = [
        {"open": 4015.8, "high": 4016.2, "low": 4014.2, "close": 4014.7, "time": 40},
        {"open": 4014.7, "high": 4015.1, "low": 4012.9, "close": 4013.4, "time": 41},
        {"open": 4013.4, "high": 4014.1, "low": 4012.6, "close": 4013.0, "time": 42},
        {"open": 4013.0, "high": 4013.6, "low": 4012.8, "close": 4013.2, "time": 43},
    ]
    m15 = _trend_rows(start=4045.0, step=-0.65, count=28)
    intent, impulse = _same_side_predictors()
    result = evaluate_exit_intelligence(
        position=_sell_position(),
        market={"price": 4013.20, "bid": 4013.15, "ask": 4013.25, "spread": 0.10, "normalSpread": 0.20},
        atr=4.2,
        m5_candles=m5,
        m15_candles=m15,
        decision={"side": "SELL", "features": {"computedSide": "SELL", "htfDailyBias": "SELL"}},
        intent_state=intent,
        impulse_state=impulse,
        config={},
    )
    assert result.phase == "RUNNER"
    assert result.continuation_score >= 70
    assert result.max_giveback_fraction >= 0.60
    assert result.trail_atr >= 0.75
    assert result.action == "BREATHE"
    assert result.recommended_sl is not None
    assert 4013.67 < result.recommended_sl < 4015.49
    assert not result.invalidated


def test_strong_runner_does_not_tighten_more_as_profit_expands():
    m5 = _trend_rows(start=4040.0, step=-0.55)
    m15 = _trend_rows(start=4060.0, step=-0.75, count=28)
    intent, impulse = _same_side_predictors()
    first = evaluate_exit_intelligence(
        position=_sell_position(currentPrice=4012.8, peakDist=3.7, sl=4013.7),
        market={"price": 4012.8, "spread": 0.12, "normalSpread": 0.20},
        atr=4.0, m5_candles=m5, m15_candles=m15,
        decision={"side": "SELL", "features": {"computedSide": "SELL", "htfDailyBias": "SELL"}},
        intent_state=intent, impulse_state=impulse, config={},
    )
    second = evaluate_exit_intelligence(
        position=_sell_position(currentPrice=4009.8, peakDist=6.0, sl=4011.2),
        market={"price": 4009.8, "spread": 0.12, "normalSpread": 0.20},
        atr=4.0, m5_candles=m5, m15_candles=m15,
        decision={"side": "SELL", "features": {"computedSide": "SELL", "htfDailyBias": "SELL"}},
        intent_state=intent, impulse_state=impulse, config={},
    )
    assert first.phase == second.phase == "RUNNER"
    assert second.trail_atr >= first.trail_atr
    assert second.max_giveback_fraction >= first.max_giveback_fraction


def test_opposite_confirmed_reversal_invalidates_and_cuts_red_trade():
    m5 = _trend_rows(start=4000.0, step=0.50)
    m15 = _trend_rows(start=3990.0, step=0.70, count=28)
    result = evaluate_exit_intelligence(
        position=_sell_position(currentPrice=4017.2, peakDist=0.6, sl=4018.1, profitR=-0.60),
        market={"price": 4017.2, "spread": 0.18, "normalSpread": 0.20},
        atr=4.0, m5_candles=m5, m15_candles=m15,
        decision={"side": "BUY", "features": {"computedSide": "BUY", "htfDailyBias": "BUY"}},
        intent_state={"side": "BUY", "stage": "CONFIRMED", "probability": 0.84},
        impulse_state={"side": "BUY", "stage": "CONFIRMED", "probability": 0.88},
        config={},
    )
    assert result.invalidated
    assert result.phase == "DEFENSIVE"
    assert result.action == "CUT"


def test_small_unproven_peak_is_not_micro_locked():
    m5 = _trend_rows(start=4020.0, step=-0.20)
    m15 = _trend_rows(start=4030.0, step=-0.30, count=28)
    intent, impulse = _same_side_predictors()
    result = evaluate_exit_intelligence(
        position=_sell_position(currentPrice=4014.95, peakDist=0.70, sl=4018.35, profitR=0.19),
        market={"price": 4014.95, "spread": 0.12, "normalSpread": 0.20},
        atr=4.0, m5_candles=m5, m15_candles=m15,
        decision={"side": "SELL", "features": {"computedSide": "SELL", "htfDailyBias": "SELL"}},
        intent_state=intent, impulse_state=impulse, config={},
    )
    assert result.phase in {"DEVELOPING", "PROBE"}
    assert not result.protection_armed
    assert result.action == "HOLD"
    assert result.recommended_sl is None


def test_stale_or_missing_context_never_adds_risk():
    result = evaluate_exit_intelligence(
        position=_sell_position(),
        market={"price": 4013.2, "spread": 0.15},
        atr=4.0,
        m5_candles=[],
        m15_candles=[],
        decision={"stale": True},
        intent_state={},
        impulse_state={},
        config={},
    )
    assert result.phase == "SAFE_HOLD"
    assert result.action == "HOLD"
    assert result.recommended_sl is None
    assert not result.allow_widen


def test_probe_can_promote_from_peak_and_context_even_when_live_window_turns_watch():
    lifecycle = classify_probe_lifecycle(
        side="SELL",
        profit_r=0.28,
        peak_r=0.62,
        context_score=0.76,
        intent_state={"side": "SELL", "stage": "WATCH", "probability": 0.42},
        impulse_state={"side": "SELL", "stage": "WATCH", "probability": 0.45},
        config={"promotionPeakR": 0.55, "promotionContextScore": 0.68},
    )
    assert lifecycle.stage == "CONFIRMED"
    assert "peak" in lifecycle.reason.lower()


def test_v14_tp_extension_is_always_ahead_of_the_live_market():
    from services.dynamic_sl_v14 import BrokerRules, DynamicSLState, PositionSnapshot, decide
    import time

    rules = BrokerRules(tick_size=0.01, stops_level_points=0, freeze_level_points=0, point=0.01)
    sell = PositionSnapshot(
        ticket=99, symbol="XAUUSD", side="SELL", entry=4050.55,
        bid=4041.40, ask=4041.50, sl=4042.00, tp=None, volume=0.01,
        initial_risk_price=3.10, peak_profit_r=3.87, current_profit_r=2.92,
        timestamp=time.time(), sequence=1,
    )
    result = decide(
        sell, rules, state=DynamicSLState.PROFIT_LOCK,
        recovery_score=100, invalidated=False, max_giveback_fraction=0.72,
        desired_sl=4047.19, desired_tp=None,
    )
    assert not result.blocked
    assert result.proposed_tp is None or result.proposed_tp < sell.ask
