from pathlib import Path
import gc
import app

def test_enterprise_identity():
    assert app.APP_VERSION == "15.4.3"
    assert app.BUILD_ID == "V15.4.3-READINESS-COMPONENT-KERNEL"

def test_ticket_lock_registry_does_not_leak():
    for i in range(1000):
        lock = app._v14_ticket_lock(i)
        with lock:
            pass
    del lock
    gc.collect()
    assert len(app._V14_TICKET_LOCKS) < 10

def test_release_verifier_forbids_mutable_artifacts():
    root=Path(__file__).resolve().parents[2]
    verifier=(root/"VERIFY_RELEASE.py").read_text()
    for suffix in (".pyc", ".sqlite", ".sqlite3", ".db", ".log"):
        assert repr(suffix) in verifier
    assert "settings_save_audit.jsonl" in verifier


def test_v1414_mac_mobile_launcher_requires_strong_key():
    root = Path(__file__).resolve().parents[2]
    text = (root / "start_backend_mobile_mac.command").read_text(encoding="utf-8")
    assert "minimum 16 characters" in text
    assert "blank = none" not in text
    assert "No access key" not in text


def test_v1414_tick_guard_has_independent_protection_defaults():
    root = Path(__file__).resolve().parents[2]
    text = (root / "mt5_ea" / "GodModeTickGuard.mq5").read_text(encoding="utf-8")
    assert "EnableBreakEven      = true" in text
    assert "EnableTrailing       = true" in text
    assert 'ExpectedEngineBuild  = "V15.4.3-READINESS-COMPONENT-KERNEL"' in text


def test_v1414_compile_helper_identity_is_current():
    root = Path(__file__).resolve().parents[2]
    helper = root / "COMPILE_TICK_GUARD_V14_1_18.bat"
    assert helper.exists()
    text = helper.read_text(encoding="utf-8")
    assert "V15.1.2" in text
    assert "V13.55.1" not in text
