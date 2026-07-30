from services.impulse_prediction import predict_impulse


def _ticks(start=100.0, step=0.08, count=20, spread=0.10):
    rows=[]
    for i in range(count):
        mid=start+step*i
        rows.append({'time_msc':(1_000_000+i*500),'bid':mid-spread/2,'ask':mid+spread/2})
    return rows


def _candles(live_close=101.5):
    rows=[]
    for i in range(11):
        base=100.0+(i%2)*0.05
        rows.append({'open':base,'high':base+0.20,'low':base-0.20,'close':base+0.02})
    rows.append({'open':100.1,'high':live_close+0.05,'low':100.0,'close':live_close})
    return rows


def test_early_buy_impulse_detects_before_full_atr():
    result=predict_impulse(ticks=_ticks(step=0.025),candles=_candles(100.45),atr=2.0,current_spread=0.10,max_spread=0.40,
                           config={'probeProbability':0.55,'confirmProbability':0.75,'minProbeDisplacementAtr':0.12})
    assert result.side=='BUY'
    assert result.stage in {'PROBE','CONFIRMED'}
    assert result.displacement_atr < 1.0


def test_liquidity_sweep_is_penalised():
    candles=_candles(100.05)
    candles[-1]={'open':100.0,'high':101.0,'low':99.95,'close':100.05}
    result=predict_impulse(ticks=_ticks(step=0.012),candles=candles,atr=2.0,current_spread=0.10,max_spread=0.40,
                           config={'probeProbability':0.55,'minProbeDisplacementAtr':0.05})
    assert result.sweep_penalty >= 0.8
    assert result.stage == 'WATCH'


def test_spread_expansion_reduces_probability():
    normal=predict_impulse(ticks=_ticks(spread=0.10),candles=_candles(),atr=2.0,current_spread=0.10,max_spread=0.50)
    wide=predict_impulse(ticks=_ticks(spread=0.10),candles=_candles(),atr=2.0,current_spread=0.48,max_spread=0.50)
    assert normal.probability > wide.probability


def test_source_integrates_anticipatory_progressive_lane():
    from pathlib import Path
    source=(Path(__file__).parents[1]/'app.py').read_text()
    assert 'Early Impulse Predictor' in source
    assert 'anticipatoryEntry' in source
    assert 'progressiveStage' in source
    assert 'copy_ticks_range' in source
