from __future__ import annotations

import json
from copy import deepcopy

from fastapi.testclient import TestClient

import app


def _isolate_settings(tmp_path, monkeypatch):
    prior_state = deepcopy(app.SETTINGS_STATE)
    prior_recovery = deepcopy(app.SETTINGS_RECOVERY_STATE)
    settings_file = tmp_path / "settings.json"
    last_good = tmp_path / "settings.lastgood.json"
    validated = app._validate_settings_candidate(deepcopy(prior_state))
    validated.setdefault("meta", {})["settingsRevision"] = 41
    settings_file.write_text(json.dumps(validated), encoding="utf-8")
    last_good.write_text(json.dumps(validated), encoding="utf-8")
    monkeypatch.setattr(app, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(app, "SETTINGS_LAST_GOOD_FILE", last_good)
    app.SETTINGS_STATE.clear()
    app.SETTINGS_STATE.update(deepcopy(validated))
    return prior_state, prior_recovery


def _restore_settings(prior_state, prior_recovery):
    app.SETTINGS_STATE.clear()
    app.SETTINGS_STATE.update(prior_state)
    app.SETTINGS_RECOVERY_STATE.clear()
    app.SETTINGS_RECOVERY_STATE.update(prior_recovery)
    app._apply_runtime_settings()


def test_production_dashboard_origin_can_toggle_and_save(tmp_path, monkeypatch):
    prior_state, prior_recovery = _isolate_settings(tmp_path, monkeypatch)
    client = TestClient(app.app)
    headers = {
        "Host": "127.0.0.1:8000",
        "Origin": "http://127.0.0.1:8000",
        "Sec-Fetch-Site": "same-origin",
    }
    try:
        live = client.post("/api/mt5/live-mode", json={"enabled": True}, headers=headers)
        auto = client.post("/api/mt5/auto-trading", json={"enabled": True}, headers=headers)
        saved = client.get("/api/settings", headers=headers)

        assert live.status_code == 200, live.text
        assert auto.status_code == 200, auto.text
        assert live.json()["ok"] is True
        assert auto.json()["ok"] is True
        execution = saved.json()["execution"]
        assert execution["liveTradingEnabled"] is True
        assert execution["dryRun"] is False
        assert execution["autoTradingEnabled"] is True
    finally:
        client.close()
        _restore_settings(prior_state, prior_recovery)


def test_localhost_alias_is_allowed_on_same_port(tmp_path, monkeypatch):
    prior_state, prior_recovery = _isolate_settings(tmp_path, monkeypatch)
    client = TestClient(app.app)
    headers = {
        "Host": "127.0.0.1:8000",
        "Origin": "http://localhost:8000",
        "Sec-Fetch-Site": "same-site",
    }
    try:
        response = client.post("/api/mt5/auto-trading", json={"enabled": True}, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["ok"] is True
    finally:
        client.close()
        _restore_settings(prior_state, prior_recovery)


def test_cross_site_browser_post_is_still_rejected():
    client = TestClient(app.app)
    try:
        response = client.post(
            "/api/mt5/live-mode",
            json={"enabled": True},
            headers={
                "Host": "127.0.0.1:8000",
                "Origin": "https://evil.example",
                "Sec-Fetch-Site": "cross-site",
            },
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Cross-site state-changing request rejected."
    finally:
        client.close()
