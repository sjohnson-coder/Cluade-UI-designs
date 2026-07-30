from __future__ import annotations
import ast
import json
from pathlib import Path
import services.audited_defaults as D

ROOT = Path(__file__).resolve().parents[2]

def test_audited_defaults_are_coherent_and_runner_aware():
    D.assert_coherent()
    assert D.PROFIT_LOCK_FRACTION == 0.62
    assert D.FAST_FAIL_MIN_SECONDS >= 180
    assert D.TRAIL_START_ATR >= D.PROTECT_START_ATR

def test_packaged_settings_match_audited_defaults():
    cfg=json.loads((ROOT/'backend/data/settings.json').read_text(encoding='utf-8'))
    tm=cfg['trading']['tradeManagement']
    assert tm['profitLockFraction'] == D.PROFIT_LOCK_FRACTION
    assert tm['trailAtrMult'] == D.TRAIL_ATR_MULT
    assert tm['fastFailMinSeconds'] == D.FAST_FAIL_MIN_SECONDS
    assert tm['fastFailNoProgressMinutes'] == D.FAST_FAIL_NO_PROGRESS_MINUTES
    assert tm['trailStartAtr'] == D.TRAIL_START_ATR
    assert tm['recoveryRoomAtr'] == D.RECOVERY_ROOM_ATR
    assert tm['breakEvenBufferPoints'] == D.BREAK_EVEN_BUFFER_POINTS

def test_no_value_matching_v1415_migration_exists():
    src=(ROOT/'backend/app.py').read_text(encoding='utf-8')
    assert 'v14.1.5-structural-defaults-migration' not in src
    assert 'float(_cur or 0) == float(_legacy)' not in src

# Directories that are not part of the shipped release. The virtual environment matters most:
# every start script creates it *inside* the project root, so without this exclusion the scan walks
# site-packages and reports ~780 third-party offenders. The assertion could only ever pass on a
# machine where the bot had not been started yet.
_NON_RELEASE_DIRS = {'__pycache__', '.pytest_cache', 'node_modules', '.git', 'venv', 'env'}


def _is_release_source(path: Path) -> bool:
    for part in path.parts:
        if part in _NON_RELEASE_DIRS:
            return False
        # Matches .venv, .venv-test, .venv311 and anything else the operator names their env.
        if part.startswith('.venv'):
            return False
    return True


def test_no_pass_only_exception_handlers_in_python_release():
    offenders=[]
    for path in ROOT.rglob('*.py'):
        if not _is_release_source(path): continue
        tree=ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and len(node.body)==1 and isinstance(node.body[0], ast.Pass):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []

def test_release_identity_is_coherent():
    """V14.1.17: assert BUILD_ID and APP_VERSION exist and agree on the version prefix,
    instead of asserting a fixed string. This test's original literal was already stale
    across two consecutive releases — the exact drift pattern that made the cert flow
    unshippable. Coherence is the invariant, not a specific string."""
    app=(ROOT/'backend/app.py').read_text(encoding='utf-8')
    build_id = None
    app_version = None
    for line in app.splitlines():
        s = line.strip()
        if s.startswith('BUILD_ID') and build_id is None:
            _, _, rhs = s.partition('=')
            build_id = rhs.strip().strip('"').strip("'")
        elif s.startswith('APP_VERSION') and app_version is None:
            _, _, rhs = s.partition('=')
            app_version = rhs.strip().strip('"').strip("'")
    assert build_id, 'BUILD_ID missing from backend/app.py'
    assert app_version, 'APP_VERSION missing from backend/app.py'
    # BUILD_ID looks like "V15.4.3-READINESS-COMPONENT-KERNEL"; APP_VERSION like "15.4.3".
    assert build_id.upper().startswith(f'V{app_version}-'), (
        f'BUILD_ID {build_id!r} does not match APP_VERSION {app_version!r}'
    )
