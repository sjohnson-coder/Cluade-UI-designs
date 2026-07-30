from pathlib import Path
import json, re

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / 'backend' / 'app.py'
BUILD = 'V15.4.3-READINESS-COMPONENT-KERNEL'
VERSION = '15.4.3'


def test_release_identity_is_consistent_across_runtime_components():
    app = APP.read_text(encoding='utf-8')
    assert f'APP_VERSION = "{VERSION}"' in app
    assert f'BUILD_ID = "{BUILD}"' in app
    assert BUILD in (ROOT / 'frontend/src/lib/api.ts').read_text(encoding='utf-8')
    assert BUILD in (ROOT / 'mt5_ea/GodModeTickGuard.mq5').read_text(encoding='utf-8')
    bundle = ''.join(p.read_text(encoding='utf-8') for p in (ROOT / 'frontend/dist/assets').glob('*.js'))
    assert BUILD in bundle
    assert 'V13.55.5-PRODUCTION-DYNAMIC-SL-AUDITED' not in bundle


def test_no_pass_only_exception_handlers_remain_in_backend_app():
    lines = APP.read_text(encoding='utf-8').splitlines()
    for i, line in enumerate(lines):
        if re.match(r'^\s*except Exception(?: as \w+)?:\s*$', line):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            assert j >= len(lines) or lines[j].strip() != 'pass', f'silent pass at line {i+1}'


def test_health_reporting_helper_is_non_throwing_and_throttled():
    src = APP.read_text(encoding='utf-8')
    assert 'def _report_suppressed_exception' in src
    assert '_SUPPRESSED_EXCEPTION_LAST' in src
    assert 'RUNTIME_HEALTH.fail(component, detail)' in src
    assert 'LOGGER.warning("Recoverable subsystem failure' in src


def test_ui_theme_and_all_mobile_navigation_remain_available():
    css = (ROOT / 'frontend/src/styles/theme.css').read_text(encoding='utf-8')
    assert '--gold:' in css
    assert '.nav-item.active' in css
    assert 'repeat(10,minmax(64px,1fr))' in css
    assert '.nav-item:nth-child(n+6){display:none}' not in css


def test_tick_guard_is_explicitly_source_only_in_manifest():
    manifest = json.loads((ROOT / 'RELEASE_MANIFEST.json').read_text(encoding='utf-8'))
    tg = manifest['tickGuard']
    assert tg['sourceIncluded'] is True
    assert tg['compiledEx5Included'] is False
    assert tg['protectionStatus'].startswith('INCOMPLETE')
