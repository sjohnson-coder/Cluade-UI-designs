from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import time
from pathlib import Path

import pytest

import app
from services import live_certification, runtime_safety
from services.live_certification import REQUIRED_GATES


def _live_settings(*, telegram_override: bool = False) -> dict:
    settings = copy.deepcopy(app.SETTINGS_STATE)
    settings.setdefault("execution", {}).update(
        {
            "dryRun": False,
            "liveTradingEnabled": True,
            "requireLiveCertification": True,
        }
    )
    settings.setdefault("validation", {}).update(
        {
            "enabled": True,
            "allowTelegramManualOverride": telegram_override,
        }
    )
    settings.setdefault("automation", {}).update(
        {
            "mql5ControlFilePath": "",
            "requireTickGuardForLive": False,
        }
    )
    return settings


def _install_healthy_live_gate(
    monkeypatch: pytest.MonkeyPatch,
    *,
    event_loop: dict | None = None,
) -> None:
    monkeypatch.setattr(app, "SETTINGS_STATE", _live_settings())
    monkeypatch.setattr(app.mt5_bridge, "live_enabled", True)
    monkeypatch.setattr(app.EXECUTION_LEDGER, "stale", lambda older_than_seconds=0: [])
    health = {
        "trade_protection": {"ok": True, "stale": False},
    }
    if event_loop is not None:
        health["event_loop"] = event_loop
    monkeypatch.setattr(app.RUNTIME_HEALTH, "snapshot", lambda _thresholds: health)
    monkeypatch.setattr(
        app,
        "_tick_guard_heartbeat_status",
        lambda: {"ok": True, "required": True, "configured": True},
    )
    monkeypatch.setattr(
        app,
        "_live_certification_status",
        lambda: {"approved": True, "grade": "A+"},
    )


def test_telegram_validation_override_cannot_bypass_unresolved_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app, "SETTINGS_STATE", _live_settings(telegram_override=True))
    monkeypatch.setattr(app.mt5_bridge, "live_enabled", True)
    monkeypatch.setattr(
        app.EXECUTION_LEDGER,
        "stale",
        lambda older_than_seconds=0: [
            {"executionId": "uncertain-1", "status": "UNKNOWN"}
        ],
    )
    monkeypatch.setattr(
        app,
        "TELEGRAM_PENDING_TRADES",
        {
            "approval-1": {
                "status": "pending",
                "expiresAt": time.time() + 60,
                "payload": {"side": "WAIT"},
            }
        },
    )
    monkeypatch.setattr(app, "_save_pending_trades", lambda: None)

    result = app._telegram_execute_pending_trade("approval-1")

    assert result["ok"] is False
    assert result["blocked"] is True
    assert "unresolved broker outcome" in result["message"]


def test_validation_override_bypasses_only_strategy_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_healthy_live_gate(
        monkeypatch,
        event_loop={"ok": True, "stale": False},
    )
    monkeypatch.setattr(
        app,
        "_validation_status",
        lambda: {"enabled": True, "passed": False},
    )

    blocked = app._execution_validation_check("test")
    overridden = app._execution_validation_check(
        "telegram_take",
        allow_validation_override=True,
    )

    assert blocked["ok"] is False
    assert overridden["ok"] is True
    assert overridden["validationOverride"] is True


def test_certified_live_mode_requires_tick_guard_even_without_configured_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app, "SETTINGS_STATE", _live_settings())
    monkeypatch.setattr(app.mt5_bridge, "live_enabled", True)

    status = app._tick_guard_heartbeat_status()

    assert status["required"] is True
    assert status["configured"] is False
    assert status["ok"] is False


def test_live_execution_fails_closed_before_first_event_loop_sample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_healthy_live_gate(monkeypatch, event_loop=None)
    monkeypatch.setattr(app, "_validation_status", lambda: {"passed": True})

    result = app._execution_validation_check("test")

    assert result["ok"] is False
    assert result["blocked"] is True
    assert "event-loop" in result["message"]


def test_health_center_never_labels_dry_run_as_live_trading_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _live_settings()
    settings["execution"]["dryRun"] = True
    monkeypatch.setattr(app, "SETTINGS_STATE", settings)
    monkeypatch.setattr(
        app.mt5_bridge,
        "status",
        lambda: {
            "connected": True,
            "liveTradingEnabled": True,
            "source": "live_mt5",
        },
    )
    monkeypatch.setattr(app.mt5_bridge, "live_enabled", True)
    monkeypatch.setattr(app, "_market_state", lambda: {"open": True, "reason": "Open"})
    monkeypatch.setattr(app.kill_switch, "status", lambda: {"active": False})
    monkeypatch.setattr(
        app.RUNTIME_HEALTH,
        "snapshot",
        lambda _thresholds: {
            "event_loop": {"ok": True, "stale": False, "detail": "healthy"}
        },
    )

    payload = app.health_full()
    trading = {row["id"]: row for row in payload["components"]}["trading"]

    assert payload["tradingAllowed"] is False
    assert payload["executionMode"] == "DRY_RUN"
    assert "Dry-run" in trading["detail"]


def test_atomic_json_directory_sync_failure_does_not_report_commit_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "state.json"
    target.write_text('{"generation":1}\n', encoding="utf-8")

    def directory_sync_unavailable(_path: str, _flags: int) -> int:
        raise PermissionError("directory fsync unsupported")

    monkeypatch.setattr(runtime_safety.os, "open", directory_sync_unavailable)

    runtime_safety.atomic_write_json(target, {"generation": 2})

    assert json.loads(target.read_text(encoding="utf-8")) == {"generation": 2}


def _evidence_backed_payload(root: Path, now: float, signing_key: str) -> dict:
    evidence_dir = root / "evidence"
    evidence_dir.mkdir()
    gates: dict[str, dict] = {}
    for gate in REQUIRED_GATES:
        artifact = evidence_dir / f"{gate}.json"
        artifact.write_text(
            json.dumps({"gate": gate, "buildId": app.BUILD_ID}) + "\n",
            encoding="utf-8",
        )
        gates[gate] = {
            "passed": True,
            "observedAt": now - 60,
            "evidence": f"evidence/{gate}.json",
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        }
    payload = {
        "schemaVersion": 2,
        "buildId": app.BUILD_ID,
        "issuer": "release-officer",
        "signatureAlgorithm": "hmac-sha256",
        "issuedAt": now - 60,
        "expiresAt": now + 3600,
        "gates": gates,
    }
    payload["signature"] = live_certification.sign_certification_payload(
        payload,
        signing_key=signing_key,
    )
    return payload


def test_live_certification_verifies_signature_and_evidence_hashes(
    tmp_path: Path,
) -> None:
    now = 1_800_000_000.0
    key = "test-only-certification-key-with-32-bytes"
    payload = _evidence_backed_payload(tmp_path, now, key)

    valid = live_certification.evaluate_live_certification(
        payload,
        build_id=app.BUILD_ID,
        now=now,
        evidence_root=tmp_path,
        signing_key=key,
        trusted_issuers={"release-officer"},
    )
    assert valid["approved"] is True

    (tmp_path / "evidence" / f"{REQUIRED_GATES[0]}.json").write_text(
        '{"tampered":true}\n',
        encoding="utf-8",
    )
    tampered = live_certification.evaluate_live_certification(
        payload,
        build_id=app.BUILD_ID,
        now=now,
        evidence_root=tmp_path,
        signing_key=key,
        trusted_issuers={"release-officer"},
    )
    assert tampered["approved"] is False
    assert f"EVIDENCE_HASH_MISMATCH:{REQUIRED_GATES[0]}" in tampered["failures"]


def test_live_certification_rejects_excessive_lifetime_and_stale_observations(
    tmp_path: Path,
) -> None:
    now = 1_800_000_000.0
    key = "test-only-certification-key-with-32-bytes"
    payload = _evidence_backed_payload(tmp_path, now, key)
    payload["expiresAt"] = now + live_certification.MAX_CERTIFICATION_TTL_SECONDS + 1
    payload["gates"][REQUIRED_GATES[0]]["observedAt"] = (
        now - live_certification.MAX_EVIDENCE_AGE_SECONDS - 1
    )
    payload["signature"] = live_certification.sign_certification_payload(
        payload,
        signing_key=key,
    )

    status = live_certification.evaluate_live_certification(
        payload,
        build_id=app.BUILD_ID,
        now=now,
        evidence_root=tmp_path,
        signing_key=key,
        trusted_issuers={"release-officer"},
    )

    assert status["approved"] is False
    assert "CERTIFICATION_TTL_EXCEEDED" in status["failures"]
    assert f"EVIDENCE_STALE:{REQUIRED_GATES[0]}" in status["failures"]


def test_certification_signing_tool_hashes_artifacts_without_persisting_key(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[2]
    tool_path = root / "SIGN_LIVE_CERTIFICATION.py"
    spec = importlib.util.spec_from_file_location("certification_signer", tool_path)
    assert spec and spec.loader
    signer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(signer)

    now = 1_800_000_000.0
    key = "test-only-certification-key-with-32-bytes"
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    gates = {}
    for gate in REQUIRED_GATES:
        artifact = evidence_dir / f"{gate}.json"
        artifact.write_text(json.dumps({"gate": gate}) + "\n", encoding="utf-8")
        gates[gate] = {
            "passed": True,
            "observedAt": now - 60,
            "evidence": f"evidence/{gate}.json",
        }
    draft = {"buildId": app.BUILD_ID, "gates": gates}

    signed = signer.prepare_and_sign(
        draft,
        evidence_root=tmp_path,
        build_id=app.BUILD_ID,
        issuer="release-officer",
        signing_key=key,
        now=now,
        ttl_seconds=3600,
    )

    assert "test-only-certification-key" not in json.dumps(signed)
    status = live_certification.evaluate_live_certification(
        signed,
        build_id=app.BUILD_ID,
        now=now,
        evidence_root=tmp_path,
        signing_key=key,
        trusted_issuers={"release-officer"},
    )
    assert status["approved"] is True
