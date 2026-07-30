from services.ai_monitor import assess_continuation, compute_protected_profit_breathing_stop


def decision(side='SELL', er=0.55, hist=-1.0, rsi=42, swing_high=4128):
    return {'side': side, 'features': {'computedSide': side, 'htfDailyBias': side, 'efficiencyRatio': er, 'macd': {'histogram': hist}, 'rsi14': rsi, 'swingHigh': swing_high, 'swingLow': 4095}}


def test_sell_continuation_score_is_open_trade_specific():
    pos = {'direction': 'SELL', 'entryPrice': 4120.61, 'currentPrice': 4111.0, 'riskBasis': 8.0, 'peakDist': 12.0}
    result = assess_continuation(pos, decision(), {'spread': 0.2}, 6.0)
    assert result['continuationScore'] >= 70
    assert result['invalidated'] is False


def test_sell_breathing_stop_remains_profitable_and_widens_only():
    pos = {'direction': 'SELL', 'entryPrice': 4120.61, 'currentPrice': 4111.0, 'sl': 4112.0, 'riskBasis': 8.0, 'peakDist': 12.0}
    stop = compute_protected_profit_breathing_stop(pos, decision(swing_high=4114), {'spread': 0.2, 'slippage': 0.05}, 6.0, 0.05, 0.65)
    assert stop is not None
    assert stop > pos['sl']            # more breathing room for a SELL
    assert stop < pos['entryPrice']    # still guaranteed gross profit
    assert stop > pos['currentPrice']  # legal side of market for SELL stop


def test_invalidated_sell_does_not_score_as_continuation():
    pos = {'direction': 'SELL', 'entryPrice': 4120.61, 'currentPrice': 4131.0, 'riskBasis': 8.0, 'peakDist': 12.0}
    result = assess_continuation(pos, decision(swing_high=4128), {'spread': 0.2}, 6.0)
    assert result['invalidated'] is True
    assert result['continuationScore'] < 50


def test_breathing_stop_never_crosses_entry_to_loss_side():
    pos = {'direction': 'BUY', 'entryPrice': 100.0, 'currentPrice': 101.0, 'sl': 100.8, 'riskBasis': 2.0, 'peakDist': 1.2}
    d = {'features': {'computedSide': 'BUY', 'htfDailyBias': 'BUY', 'efficiencyRatio': 0.5, 'macd': {'histogram': 1}, 'rsi14': 55, 'swingLow': 99}}
    stop = compute_protected_profit_breathing_stop(pos, d, {'spread': 0.05}, 1.0, 0.05, 0.8)
    assert stop is None or stop > 100.0
