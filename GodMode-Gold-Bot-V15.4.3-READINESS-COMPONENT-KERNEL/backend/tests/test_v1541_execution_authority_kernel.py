from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / 'backend' / 'app.py'
API = ROOT / 'frontend' / 'src' / 'lib' / 'api.ts'
MAIN = ROOT / 'frontend' / 'src' / 'main.tsx'
APP_TSX = ROOT / 'frontend' / 'src' / 'App.tsx'


def test_backend_readiness_separates_app_health_from_execution_authority():
    src = APP.read_text(encoding='utf-8')
    assert '"executionAuthority"' in src
    assert 'app_ready =' in src
    assert 'trading_ready = bool(' in src
    assert 'ready = not reasons' not in src[src.index('def _authoritative_readiness'):src.index('@app.get("/api/liveness")')]


def test_execution_blockers_do_not_mark_ui_backend_degraded():
    src = API.read_text(encoding='utf-8')
    assert "payload?.appReady === true" in src
    assert "payload?.tradingReady" in src
    assert "payload?.ready === true && buildMatch" not in src


def test_noncritical_api_failures_do_not_set_global_offline():
    src = API.read_text(encoding='utf-8')
    assert "if(criticalLivePath && safetyState !== 'AUTH_REQUIRED')" in src
    assert "if (safetyState !== 'AUTH_REQUIRED') safetyState='OFFLINE';" not in src


def test_ui_render_errors_are_advisory_not_execution_degrading():
    src = MAIN.read_text(encoding='utf-8')
    assert "godmode:ui-error" in src
    assert "state:'DEGRADED'" not in src


def test_app_shows_execution_authority_as_amber_not_backend_degraded():
    src = APP_TSX.read_text(encoding='utf-8')
    assert 'EXECUTION AUTHORITY NOT ARMED' in src
    assert 'executionAuthority' in src
