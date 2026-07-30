from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = 'V15.4.3-READINESS-COMPONENT-KERNEL'
VERSION = '15.4.3'


def test_active_launcher_uses_exact_v1502_identity():
    text = (ROOT / 'START_GODMODE.bat').read_text(encoding='utf-8')
    assert f'set "GODMODE_BUILD={BUILD}"' in text
    assert 'GodMode Gold Bot V15.4.3' in text
    assert 'V15.4.3 did not become ready' in text
    assert 'build=V1543-READINESS-COMPONENT-KERNEL' in text
    assert 'V14.1.23' not in text
    assert 'V15.0.0' not in text


def test_deployed_html_uses_exact_v1502_identity():
    text = (ROOT / 'frontend' / 'dist' / 'index.html').read_text(encoding='utf-8')
    assert f'content="{BUILD}"' in text
    assert 'v15-enterprise.js' in text
    assert 'V15.0.0' not in text


def test_release_verifier_covers_launcher_and_html_identity():
    text = (ROOT / 'VERIFY_RELEASE.py').read_text(encoding='utf-8')
    for token in ('START_GODMODE.bat', 'frontend/dist/index.html', 'DASHBOARD_URL', 'godmode-build'):
        assert token in text


def test_react_source_does_not_duplicate_runtime_panel():
    text = (ROOT / 'frontend' / 'src' / 'pages' / 'AIAgent.tsx').read_text(encoding='utf-8')
    assert 'V15Intelligence' not in text
