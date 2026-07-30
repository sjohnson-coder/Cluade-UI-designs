import json
import pytest
import app
from services.live_market_feeds import EconomicCalendarAPI, TickDataBacktester

def test_health_endpoint_and_identity():
    paths={r.path for r in app.app.routes}
    assert '/api/health' in paths and '/api/liveness' in paths and '/api/readiness' in paths
    assert app.APP_VERSION=='15.4.3'
    assert app.BUILD_ID=='V15.4.3-READINESS-COMPONENT-KERNEL'

def test_news_window_validation_is_explicit():
    cal=EconomicCalendarAPI()
    with pytest.raises(ValueError): cal.configure(before='thirty')
    with pytest.raises(ValueError): cal.configure(after=241)

def test_tick_backtest_requires_explicit_synthetic_mode(monkeypatch):
    b=TickDataBacktester()
    sample=b.load_ticks(source='synthetic',limit=10)
    assert sample['syntheticFallback'] is True and sample['sourceRequested']=='synthetic'
    with pytest.raises(ValueError): b.load_ticks(source='unknown')

def test_manifest_discloses_tick_guard_limitation():
    manifest=json.loads((app.Path(__file__).resolve().parents[2]/'RELEASE_MANIFEST.json').read_text())
    assert manifest['tickGuard']['compiledEx5Included'] is False
    assert manifest['tickGuard']['protectionStatus'].startswith('INCOMPLETE')
