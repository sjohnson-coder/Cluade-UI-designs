from pathlib import Path

from services.early_intent import predict_early_intent


def _ticks(prices, spread=0.10):
    return [
        {"time_msc": 1_000_000 + i * 300, "bid": price, "ask": price + spread}
        for i, price in enumerate(prices)
    ]


def _candles(side="BUY", sweep=False):
    candles = []
    for i in range(13):
        base = 99.0 + i * 0.05
        candles.append({"open": base, "high": base + 0.40, "low": base - 0.40, "close": base + 0.05})
    if side == "BUY":
        candles[-1] = {"open": 100.0, "high": 101.08, "low": 99.90, "close": 100.98 if not sweep else 99.90}
    else:
        candles[-1] = {"open": 100.0, "high": 100.10, "low": 98.92, "close": 99.02 if not sweep else 100.10}
    return candles


def test_buy_intent_qualifies_before_point_one_atr():
    prices = [100,100.02,100.05,100.09,100.14,100.20,100.28,100.38,100.50,100.64,100.80,100.98]
    result = predict_early_intent(
        ticks=_ticks(prices), candles=_candles("BUY"), atr=10.0,
        current_spread=0.10, max_spread=0.40,
    )
    assert result.side == "BUY"
    assert result.stage == "INTENT"
    assert 0.07 <= result.displacement_atr < 0.10
    assert result.probability >= 0.68


def test_sell_intent_is_symmetric():
    prices = [100,99.98,99.95,99.91,99.86,99.80,99.72,99.62,99.50,99.36,99.20,99.02]
    result = predict_early_intent(
        ticks=_ticks(prices), candles=_candles("SELL"), atr=10.0,
        current_spread=0.10, max_spread=0.40,
    )
    assert result.side == "SELL"
    assert result.stage == "INTENT"


def test_spread_blowout_and_reversal_do_not_qualify():
    prices = [100,100.02,100.05,100.09,100.14,100.20,100.28,100.38,100.50,100.64,100.80,100.98]
    result = predict_early_intent(
        ticks=_ticks(prices, spread=0.70), candles=_candles("BUY", sweep=True), atr=10.0,
        current_spread=0.70, max_spread=0.40,
    )
    assert result.stage != "INTENT"
    assert result.reversal_penalty >= 0.85


def test_runtime_wires_real_probe_multiplier_and_ui():
    app = Path('backend/app.py').read_text(encoding='utf-8')
    assert 'predict_early_intent' in app
    assert '"source": "early_intent"' in app
    assert 'probeLotMultiplier' in app
    assert 'effectiveLotMultiplier' in app
    ui = Path('frontend/src/pages/Settings.tsx').read_text(encoding='utf-8')
    assert 'Enable Early Intent' in ui
    assert 'earlyIntentProbability' in ui
    dist = Path('frontend/dist/predictor-live-v1529.js').read_text(encoding='utf-8')
    assert 'V15.4.3-READINESS-COMPONENT-KERNEL' in dist
    assert 'godmode-predictor-dashboard' in dist
