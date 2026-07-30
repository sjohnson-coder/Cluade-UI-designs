from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app


def _install_temp_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    state = copy.deepcopy(app._default_settings())
    state.setdefault("meta", {})["settingsRevision"] = 1
    monkeypatch.setattr(app, "SETTINGS_STATE", state)
    monkeypatch.setattr(app, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(app, "SETTINGS_LAST_GOOD_FILE", tmp_path / "settings.lastgood.json")
    monkeypatch.setattr(app, "_apply_runtime_settings", lambda: None)


def test_validation_lock_endpoint_switches_both_fields_atomically(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_temp_settings(monkeypatch, tmp_path)
    client = TestClient(app.app)

    response = client.post(
        "/api/settings/validation-lock",
        json={"enabled": False, "expectedRevision": 1},
        headers={"Origin": "http://testserver"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["enabled"] is False
    assert payload["settings"]["validation"]["enabled"] is False
    assert payload["settings"]["execution"]["validationLockEnabled"] is False
    assert app.SETTINGS_STATE["validation"]["enabled"] is False
    assert app.SETTINGS_STATE["execution"]["validationLockEnabled"] is False


def test_atomic_toggles_do_not_enforce_expected_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    """V15.2.8: atomic single-field toggles must NOT enforce optimistic concurrency.

    This test previously asserted the opposite — that the toggles forwarded the caller's
    expectedRevision into the commit, causing a 409 on any mismatch. That behaviour was the
    root cause of the reported "validation lock will not switch off" and "auto is not
    working": the browser caches the revision it last saw, ANY background settings write
    (MT5 status heartbeat, autosave, maintenance patch) advances it, and the next toggle
    click then submits a stale value and is rejected, so Settings.tsx rolls the switch back.

    Optimistic concurrency exists to prevent LOST UPDATES when two writers edit overlapping
    field sets. These endpoints each mutate exactly one boolean and are idempotent, so there
    is no lost-update hazard for it to prevent here — only a false-conflict hazard. The same
    fix was already applied to POST /api/settings and simply never propagated to the toggles.

    Multi-field writers (/api/mt5/connect, config_import, rollback) still enforce strictly;
    see test_multi_field_writers_still_enforce_expected_revision.
    """
    seen: list[tuple[str, int | None]] = []

    def commit(_patch, *, reason: str, expected_revision: int | None = None):
        seen.append((reason, expected_revision))
        return {"ok": True, "revision": 8}

    monkeypatch.setattr(app, "_commit_settings_patch", commit)
    monkeypatch.setattr(app, "_safe_public_settings", lambda _settings: {"execution": {}})
    monkeypatch.setattr(app, "_settings_revision", lambda: 8)
    monkeypatch.setattr(app.mt5_bridge, "status", lambda: {"connected": True})

    # Deliberately stale revision (7 while server is at 8) — must still succeed.
    app.mt5_live_mode({"enabled": True, "expectedRevision": 7})
    app.mt5_auto_trading({"enabled": True, "expectedRevision": 7})
    app.validation_lock_toggle({"enabled": False, "expectedRevision": 7})

    assert seen == [
        ("live_mode_toggle", None),
        ("auto_trading_toggle", None),
        ("validation_lock_toggle", None),
    ], "atomic toggles must pass expected_revision=None so a stale UI revision cannot revert them"


def test_multi_field_writers_still_enforce_expected_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    """The concurrency guard is correct for writers that can genuinely clobber."""
    seen: list[tuple[str, int | None]] = []

    def commit(_patch, *, reason: str, expected_revision: int | None = None):
        seen.append((reason, expected_revision))
        return {"ok": True, "revision": 8}

    monkeypatch.setattr(app, "_commit_settings_patch", commit)
    monkeypatch.setattr(app, "_safe_public_settings", lambda _settings: {})
    monkeypatch.setattr(app, "_settings_revision", lambda: 8)
    app.config_import({"settings": {"appearance": {"density": "compact"}}, "expectedRevision": 7})
    assert seen and seen[-1][1] == 7, "config_import must keep enforcing expectedRevision"


def test_telegram_send_text_rejects_api_level_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = copy.deepcopy(app.SETTINGS_STATE)
    settings["telegram"] = {
        "enabled": True,
        "botToken": "123:abc",
        "chatId": "42",
        "minimalMode": False,
        "dedupeSeconds": 0,
    }
    monkeypatch.setattr(app, "SETTINGS_STATE", settings)
    monkeypatch.setattr(
        app,
        "read_public_https",
        lambda *_args, **_kwargs: b'{"ok":false,"description":"Bad Request: chat not found"}',
    )

    result = app._telegram_send_text("GodMode test")

    assert result["ok"] is False
    assert "chat not found" in result["message"]


def test_telegram_recap_reports_disabled_instead_of_false_success(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = copy.deepcopy(app.SETTINGS_STATE)
    settings["telegram"] = {"enabled": False, "botToken": "123:abc", "chatId": "42"}
    monkeypatch.setattr(app, "SETTINGS_STATE", settings)
    client = TestClient(app.app)

    response = client.post(
        "/api/telegram/recap",
        json={"weekly": False, "withForecast": False},
        headers={"Origin": "http://testserver"},
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["ok"] is False
    assert "disabled" in payload["message"].lower()


def test_telegram_recap_reports_actual_send_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = copy.deepcopy(app.SETTINGS_STATE)
    settings["telegram"] = {
        "enabled": True,
        "botToken": "123:abc",
        "chatId": "42",
        "sendCharts": False,
        "minimalMode": False,
        "dedupeSeconds": 0,
    }
    monkeypatch.setattr(app, "SETTINGS_STATE", settings)
    monkeypatch.setattr(app, "_live_analytics", lambda: {"kpis": {}, "currency": "GBP", "equityCurve": []})
    monkeypatch.setattr(app, "_telegram_send_text", lambda *_a, **_k: {"ok": False, "message": "Telegram send failed: offline"})
    client = TestClient(app.app)

    response = client.post(
        "/api/telegram/recap",
        json={"weekly": False, "withForecast": False},
        headers={"Origin": "http://testserver"},
    )

    assert response.status_code == 502
    payload = response.json()
    assert payload["ok"] is False
    assert "offline" in payload["message"]


def test_telegram_recap_success_requires_actual_send(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = copy.deepcopy(app.SETTINGS_STATE)
    settings["telegram"] = {
        "enabled": True,
        "botToken": "123:abc",
        "chatId": "42",
        "sendCharts": False,
        "minimalMode": False,
        "dedupeSeconds": 0,
    }
    monkeypatch.setattr(app, "SETTINGS_STATE", settings)
    monkeypatch.setattr(app, "_live_analytics", lambda: {"kpis": {}, "currency": "GBP", "equityCurve": []})
    monkeypatch.setattr(app, "_telegram_send_text", lambda *_a, **_k: {"ok": True, "message": "Telegram notification sent."})
    client = TestClient(app.app)

    response = client.post(
        "/api/telegram/recap",
        json={"weekly": False, "withForecast": False},
        headers={"Origin": "http://testserver"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["recap"]["ok"] is True


def _live_validation_settings() -> dict:
    settings = copy.deepcopy(app.SETTINGS_STATE)
    settings.setdefault("execution", {}).update(
        {
            "dryRun": False,
            "liveTradingEnabled": True,
            "requireLiveCertification": False,
        }
    )
    settings.setdefault("validation", {})["enabled"] = False
    settings.setdefault("automation", {})["requireTickGuardForLive"] = False
    return settings


def test_flat_manual_entry_is_not_blocked_by_uninitialised_protection_heartbeat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app, "SETTINGS_STATE", _live_validation_settings())
    monkeypatch.setattr(app.mt5_bridge, "live_enabled", True)
    monkeypatch.setattr(app.mt5_bridge, "status", lambda: {"connected": True, "tradeAllowed": True})
    monkeypatch.setattr(app.mt5_bridge, "open_positions", lambda bot_only=True: [])
    monkeypatch.setattr(app.EXECUTION_LEDGER, "stale", lambda older_than_seconds=0: [])
    monkeypatch.setattr(
        app.RUNTIME_HEALTH,
        "snapshot",
        lambda thresholds: (
            {"event_loop": {"ok": True, "stale": False}}
            if "event_loop" in thresholds
            else {"trade_protection": {}}
        ),
    )
    monkeypatch.setattr(app, "_tick_guard_heartbeat_status", lambda: {"required": False, "ok": True})
    monkeypatch.setattr(app, "_live_certification_status", lambda: {"approved": False})

    result = app._execution_validation_check("manual_trigger", allow_validation_override=True)

    assert result["ok"] is True


def test_open_position_still_requires_fresh_protection_heartbeat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app, "SETTINGS_STATE", _live_validation_settings())
    monkeypatch.setattr(app.mt5_bridge, "live_enabled", True)
    monkeypatch.setattr(app.mt5_bridge, "status", lambda: {"connected": True, "tradeAllowed": True})
    monkeypatch.setattr(app.mt5_bridge, "open_positions", lambda bot_only=True: [{"ticket": 1}])
    monkeypatch.setattr(app.EXECUTION_LEDGER, "stale", lambda older_than_seconds=0: [])
    monkeypatch.setattr(app.RUNTIME_HEALTH, "snapshot", lambda _thresholds: {"trade_protection": {"ok": False, "stale": True}})

    result = app._execution_validation_check("manual_trigger", allow_validation_override=True)

    assert result["ok"] is False
    assert "protection" in result["message"].lower()


def test_frontend_source_uses_authoritative_backend_execution_gate() -> None:
    root = Path(__file__).resolve().parents[2]
    api_source = (root / "frontend" / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
    assert "if (executionMutation && safetyState !== 'LIVE')" not in api_source
    assert "refreshExecutionReadiness" in api_source


def test_reference_typography_is_applied_without_font_binaries() -> None:
    root = Path(__file__).resolve().parents[2]
    html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    css = (root / "frontend" / "src" / "styles" / "theme.css").read_text(encoding="utf-8")
    assert "family=Archivo" in html
    assert "Playfair+Display" not in html
    assert "Fraunces" not in html
    # Archivo is now referenced through the --font-display token rather than repeated as a literal
    # stack in a dozen rules, so assert the token is defined with Archivo and that display surfaces
    # consume it. That is the property this test cares about; the spelling is incidental.
    assert '--font-display:"Archivo"' in css
    assert 'font-family:var(--font-display)' in css
    assert not list((root / "frontend").rglob("*.woff*"))


def test_validation_toggle_is_immediate_and_transactional_in_source() -> None:
    root = Path(__file__).resolve().parents[2]
    settings = (root / "frontend" / "src" / "pages" / "Settings.tsx").read_text(encoding="utf-8")
    assert "const validationToggle=async" in settings
    assert "onChange={validationToggle}" in settings


def test_production_bundle_has_no_stale_release_controls() -> None:
    root = Path(__file__).resolve().parents[2]
    dist = root / "frontend" / "dist"
    text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in dist.rglob("*") if p.is_file())
    assert "V14.1.22" not in text
    assert "V14.1.23" not in text
    assert "V15.4.3-READINESS-COMPONENT-KERNEL" in text
    assert "Archivo" in text


def test_auto_control_status_surfaces_authoritative_execution_blocker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app.mt5_bridge, "live_enabled", True)
    monkeypatch.setattr(app.mt5_bridge, "status", lambda: {"connected": True, "liveTradingEnabled": True})
    monkeypatch.setattr(app, "_market_state", lambda: {"open": True, "reason": "Market open"})
    monkeypatch.setattr(app.kill_switch, "status", lambda: {"active": False})
    monkeypatch.setattr(app, "_authoritative_readiness", lambda: {"reasons": [], "warnings": []})
    monkeypatch.setattr(
        app,
        "_execution_validation_check",
        lambda context="auto_control_status", **kwargs: {
            "ok": False,
            "blocked": True,
            "message": "Execution lock: validation gate is not passed.",
        },
    )
    monkeypatch.setitem(
        app.SETTINGS_STATE,
        "execution",
        {
            "liveTradingEnabled": True,
            "autoTradingEnabled": True,
            "dryRun": False,
            "deploymentMode": "LIVE_RESTRICTED",
            "preLiveSafety": {"mode": "LIVE_RESTRICTED"},
        },
    )

    status = app._auto_control_status()

    assert status["armed"] is False
    assert "Execution lock: validation gate is not passed." in status["blockers"]
    assert status["executionGate"]["ok"] is False


def test_readiness_trading_ready_requires_validation_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app.mt5_bridge, "status", lambda: {"connected": True, "liveTradingEnabled": True})
    monkeypatch.setattr(app, "_market_state", lambda: {"open": True, "reason": "Market open"})
    monkeypatch.setattr(app.EXECUTION_LEDGER, "unresolved", lambda: [])
    monkeypatch.setattr(app.RUNTIME_HEALTH, "snapshot", lambda *_args, **_kwargs: {
        "reconciliation": {"ok": True, "stale": False},
        "auto_loop": {"ok": True, "stale": False},
        "trade_protection": {"ok": True, "stale": False},
        "event_loop": {"ok": True, "stale": False},
    })
    monkeypatch.setattr(app, "_validation_status", lambda: {"enabled": True, "passed": False})
    monkeypatch.setattr(app, "_tick_guard_heartbeat_status", lambda: {"required": False, "ok": True})
    monkeypatch.setattr(app, "_live_certification_status", lambda: {"approved": True, "certificationType": "local_runtime"})
    monkeypatch.setattr(app.kill_switch, "status", lambda: {"active": False})
    monkeypatch.setattr(app.os, "access", lambda *_args, **_kwargs: True)
    monkeypatch.setitem(app.SETTINGS_STATE, "execution", {"requireLiveCertification": True, "dryRun": False})

    ready = app._authoritative_readiness()

    assert ready["ready"] is True
    assert ready["validationPassed"] is False
    assert ready["tradingReady"] is False


def test_release_verifier_and_active_installers_target_v1504() -> None:
    root = Path(__file__).resolve().parents[2]
    verifier = (root / "VERIFY_RELEASE.py").read_text(encoding="utf-8")
    assert "V1543-READINESS-COMPONENT-KERNEL" in verifier
    assert "15.043" in verifier
    assert "V15_1_0_RELEASE_NOTES.md" in verifier
    assert "V15_1_0_VERIFICATION_REPORT.md" in verifier
    assert "COMPILE_TICK_GUARD_V15_1_0.bat" in verifier
    assert "V1503-PRE-LIVE-SAFETY-HARDENED" not in verifier
    active_files = [
        "README.md",
        "START_INSTRUCTIONS.txt",
        "start_all.bat",
        "start_backend.bat",
        "start_backend_mobile.bat",
        "CHECK_TICK_GUARD.bat",
        "2_INSTALL_EA_AND_START_GODMODE.bat",
        "mt5_ea/README_EA_INSTALL.md",
    ]
    for relative in active_files:
        text = (root / relative).read_text(encoding="utf-8")
        assert "V15.4.3" in text, relative
        assert "V14.1.23" not in text, relative
        assert "V15.0.3" not in text, relative


def test_release_verifier_checks_manifest_file_inventory() -> None:
    root = Path(__file__).resolve().parents[2]
    verifier = (root / "VERIFY_RELEASE.py").read_text(encoding="utf-8")
    assert "manifest file checksum mismatch" in verifier
    assert "manifest missing file" in verifier
    assert "manifest unexpected file" in verifier


def test_failed_telegram_send_does_not_poison_dedupe_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = copy.deepcopy(app.SETTINGS_STATE)
    settings["telegram"] = {
        "enabled": True,
        "botToken": "123:abc",
        "chatId": "42",
        "minimalMode": False,
        "dedupeSeconds": 90,
    }
    monkeypatch.setattr(app, "SETTINGS_STATE", settings)
    app.TELEGRAM_SEND_STATE.clear()
    replies = iter([
        b'{"ok":false,"description":"temporary failure"}',
        b'{"ok":true,"result":{"message_id":2}}',
    ])
    monkeypatch.setattr(app, "read_public_https", lambda *_a, **_k: next(replies))

    first = app._telegram_send_text("Daily recap test")
    second = app._telegram_send_text("Daily recap test")

    assert first["ok"] is False
    assert second["ok"] is True
    assert second.get("skipped") is not True


def test_recap_with_forecast_fails_when_forecast_delivery_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app, "_send_recap", lambda weekly=False: {"ok": True, "message": "recap sent"})
    monkeypatch.setattr(app, "_send_wait_forecast", lambda: {"ok": False, "message": "forecast failed"})
    client = TestClient(app.app)

    response = client.post(
        "/api/telegram/recap",
        json={"weekly": False, "withForecast": True},
        headers={"Origin": "http://testserver"},
    )

    assert response.status_code == 502
    payload = response.json()
    assert payload["ok"] is False
    assert "forecast failed" in payload["message"]


def test_wait_forecast_cooldown_is_recorded_only_after_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = copy.deepcopy(app.SETTINGS_STATE)
    settings["telegram"] = {
        "enabled": True,
        "sendWaitForecast": True,
        "waitForecastMinutes": 30,
    }
    monkeypatch.setattr(app, "SETTINGS_STATE", settings)
    monkeypatch.setattr(app, "_market_state", lambda: {"open": True})
    monkeypatch.setattr(app.mt5_bridge, "open_positions", lambda bot_only=True: [])
    monkeypatch.setattr(
        app,
        "_decision",
        lambda: {
            "action": "WAIT",
            "computedSide": "BUY",
            "marketRegime": "TREND",
            "decisionBlocks": ["wait for retest"],
            "confidence": 70,
            "symbol": "XAUUSD",
        },
    )
    monkeypatch.setattr(app, "_telegram_rich_trade_alert", lambda *_a, **_k: {"ok": False, "message": "offline"})
    app.RECAP_STATE["lastWaitForecast"] = 0.0

    result = app._send_wait_forecast()

    assert result["ok"] is False
    assert app.RECAP_STATE["lastWaitForecast"] == 0.0


def test_telegram_save_does_not_claim_network_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app, "_commit_settings_patch", lambda *_a, **_k: {"revision": 3})
    client = TestClient(app.app)

    response = client.post(
        "/api/telegram/save",
        json={"enabled": True, "botToken": "123:abc", "chatId": "42"},
        headers={"Origin": "http://testserver"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "verified" not in payload["message"].lower()


def test_frontend_test_recap_requests_forecast_only_when_enabled() -> None:
    root = Path(__file__).resolve().parents[2]
    settings = (root / "frontend" / "src" / "pages" / "Settings.tsx").read_text(encoding="utf-8")
    assert "withForecast:Boolean(payload.sendWaitForecast)" in settings
    assert "telegramRecap({withForecast:true})" not in settings


def test_scheduled_recap_marks_period_only_after_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio
    fixed = app.time.struct_time((2026, 7, 27, 21, 0, 0, 0, 208, 0))
    settings = copy.deepcopy(app.SETTINGS_STATE)
    settings["telegram"] = {"enabled": True, "dailyRecap": True, "weeklyRecap": False, "recapHourUtc": 21}
    settings["strategyLab"] = {"autoRunDaily": False, "autoDiscover": False}
    monkeypatch.setattr(app, "SETTINGS_STATE", settings)
    monkeypatch.setattr(app.time, "gmtime", lambda: fixed)
    monkeypatch.setattr(app, "_check_market_transition", lambda: None)
    monkeypatch.setattr(app, "_send_wait_forecast", lambda: {"ok": False, "skipped": True})
    monkeypatch.setattr(app, "_send_recap", lambda weekly=False: {"ok": False, "message": "offline"})
    async def stop_after_cycle(_seconds: float) -> None:
        raise asyncio.CancelledError
    monkeypatch.setattr(app.asyncio, "sleep", stop_after_cycle)
    app.RECAP_STATE["lastDaily"] = ""

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(app._recap_loop())

    assert app.RECAP_STATE["lastDaily"] == ""
