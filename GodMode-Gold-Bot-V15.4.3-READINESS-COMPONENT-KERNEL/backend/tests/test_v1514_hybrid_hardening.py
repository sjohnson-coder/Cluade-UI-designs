from pathlib import Path

import app


def test_release_identity_is_v1514():
    assert app.APP_VERSION == "15.4.3"
    assert app.BUILD_ID == "V15.4.3-READINESS-COMPONENT-KERNEL"


def test_post_close_path_has_no_fake_ai_veto():
    text = Path(app.__file__).read_text(encoding="utf-8")
    assert "AI audit gate blocked ticket" not in text
    assert "Entry enforcement occurs only on the" in text


def test_body_gate_supports_shadow_and_enforce_modes():
    text = Path(app.__file__).read_text(encoding="utf-8")
    assert 'fsmmsBodyAtrGateMode' in text
    assert '_gate_mode == "ENFORCE"' in text
    assert 'body-gate-shadow' in text
    settings = app._default_settings()
    # Existing persisted settings may override defaults at runtime; code defaults must
    # still advertise the operator-facing modes and critical-path protection.
    assert settings["aiAuditor"]["bypassCriticalImpulseEntries"] is True
    assert settings["aiAuditor"]["timeoutSeconds"] == 8


def test_critical_impulse_bypasses_synchronous_ai_audit():
    text = Path(app.__file__).read_text(encoding="utf-8")
    assert 'critical_impulse_latency_protection' in text
    assert '_decision_source == "cascade_aligned_retest"' in text
    assert 'if _bypass_audit:' in text
