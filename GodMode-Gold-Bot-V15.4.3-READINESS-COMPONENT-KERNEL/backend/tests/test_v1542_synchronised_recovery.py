
import ast
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app.py"

def _source(): return APP.read_text(encoding="utf-8")

def test_telegram_watcher_initialises_dependencies_and_reuses_decision():
    src=_source()
    assert 'auto_cfg = SETTINGS_STATE.get("automation", {})' in src
    assert 'regime = "—"' in src
    assert '_auto_trade_tick("fast_sniper_watch", precomputed_decision=fast, precomputed_market=market)' in src

def test_priority_overlap_is_busy_not_down():
    src=_source()
    assert 'runtimeStatus": "BUSY"' in src
    assert 'previous cycle completing' in src
    assert 'transient_overlap = bool(payload.get("skipped"))' in src

def test_priority_cycle_has_bounded_deadline_and_inflight_state():
    src=_source()
    assert 'PRIORITY_INTENT_STATE["inFlight"] = True' in src
    assert '_priority_intent_tick, timeout=2.0' in src
    assert '"inFlight": False' in src

def test_blocked_decisions_record_first_and_final_blocker():
    src=_source()
    assert 'firstBlocker' in src and 'finalBlocker' in src and 'decisionTrace' in src

def test_no_undefined_local_names_in_app_ast():
    ast.parse(_source())

def test_release_identity_is_v1542():
    assert 'V15.4.3-READINESS-COMPONENT-KERNEL' in _source()
