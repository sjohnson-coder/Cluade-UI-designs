from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app


def _market():
    rows=[]
    price=100.0
    for i in range(40):
        price -= 0.25
        rows.append({'open':price+0.10,'high':price+0.18,'low':price-0.15,'close':price})
    return {'symbol':'XAUUSD','timeframe':'M5','price':price,'candles':rows}


def test_completed_retest_resets_stale_ema_late_entry_origin(monkeypatch):
    decision={
        'side':'SELL','confidence':84.0,'quality':'SCOUT','strategy':'Fast Sniper Retest Continuation',
        'tradePlan':{'entry':90.0},
        'features':{'fastSniper':True,'retestContinuation':True,'retestCompleted':True,
                    'lateEntryOriginReset':True,'retestEntryPrice':90.0,
                    'retestTriggerLow':89.8,'mtfScore':0.62}
    }
    monkeypatch.setattr(app, '_entry_quality_metrics', lambda *a, **k: {
        'ok':True,'late':True,'extensionAtr':2.9,'atr':1.0,'chop':False,
        'pullbackReclaim':False,'recentLegEfficiency':0.7,'recentFlips':1,
        'directionalMoveAtr':1.2
    })
    monkeypatch.setattr(app, '_recent_session_edge_stats', lambda: {'total':0})
    result=app._entry_quality_governor(decision,_market())
    assert result['ok'] is True
    assert result['entryQuality']['metrics']['lateEntryOriginReset'] is True
    assert result['entryQuality']['metrics']['retestLocalExtensionAtr'] == 0.2


def test_retest_still_blocks_when_new_continuation_leg_itself_is_late(monkeypatch):
    decision={
        'side':'SELL','confidence':84.0,'quality':'SCOUT','strategy':'Fast Sniper Retest Continuation',
        'tradePlan':{'entry':90.0},
        'features':{'fastSniper':True,'retestContinuation':True,'retestCompleted':True,
                    'lateEntryOriginReset':True,'retestEntryPrice':90.0,
                    'retestTriggerLow':88.5,'mtfScore':0.62}
    }
    monkeypatch.setattr(app, '_entry_quality_metrics', lambda *a, **k: {
        'ok':True,'late':True,'extensionAtr':2.9,'atr':1.0,'chop':False,
        'pullbackReclaim':False,'recentLegEfficiency':0.7,'recentFlips':1,
        'directionalMoveAtr':1.2
    })
    monkeypatch.setattr(app, '_recent_session_edge_stats', lambda: {'total':0})
    result=app._entry_quality_governor(decision,_market())
    assert result['blocked'] is True
    assert 'validated retest origin' in result['message']


def test_retest_confidence_formula_is_not_hard_clamped_to_82():
    source=Path(app.__file__).read_text(encoding='utf-8')
    assert 'body_strength * 7.0' in source
    assert 'retrace_quality * 5.0' in source
    assert '"confidence": round(confidence, 1)' in source


def test_packaged_settings_enable_continuous_edge_state():
    import json
    cfg=json.loads((ROOT/'data'/'settings.json').read_text())
    tm=cfg['trading']['tradeManagement']
    assert tm['continuousEdgeStateEnabled'] is True
    assert tm['liveProbabilityRunnerScore'] == 70.0
    assert cfg['buildId'] == 'V15.4.3-READINESS-COMPONENT-KERNEL'
