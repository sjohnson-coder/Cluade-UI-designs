from fastapi.testclient import TestClient
import app as app_module


def test_minimal_mode_allows_test_and_recap_messages(monkeypatch):
    original = app_module.SETTINGS_STATE
    try:
        app_module.SETTINGS_STATE = {
            **original,
            "telegram": {
                **(original.get("telegram") or {}),
                "enabled": True,
                "minimalMode": True,
                "sendEntryExitAlerts": True,
            },
        }
        assert app_module._telegram_allowed_by_minimal_mode(
            "GodMode Gold Bot Telegram test: alerts are connected."
        ) == (True, "test")
        allowed, category = app_module._telegram_allowed_by_minimal_mode(
            "📊 *GodMode Daily Recap*\nNet PnL: *0 GBP*"
        )
        assert allowed is True
        assert category == "recap"
    finally:
        app_module.SETTINGS_STATE = original


def test_telegram_status_never_exposes_token(monkeypatch):
    original = app_module.SETTINGS_STATE
    try:
        app_module.SETTINGS_STATE = {
            **original,
            "telegram": {
                **(original.get("telegram") or {}),
                "enabled": True,
                "botToken": "123456:VERY_SECRET_TOKEN",
                "chatId": "8738835307",
            },
        }
        client = TestClient(app_module.app)
        response = client.get("/api/telegram/status")
        assert response.status_code == 200
        body = response.json()
        assert body["configured"] is True
        assert body["tokenConfigured"] is True
        assert body["chatIdMasked"] == "••••5307"
        assert "VERY_SECRET_TOKEN" not in response.text
    finally:
        app_module.SETTINGS_STATE = original


def test_test_button_persists_credentials_and_reports_real_delivery(monkeypatch, tmp_path):
    original = app_module.SETTINGS_STATE
    try:
        app_module.SETTINGS_STATE = {
            **original,
            "telegram": {**(original.get("telegram") or {}), "enabled": False, "botToken": "", "chatId": ""},
        }
        monkeypatch.setattr(app_module, "_commit_settings_patch", lambda patch, **kwargs: app_module.SETTINGS_STATE["telegram"].update(patch["telegram"]) or {"revision": 99})
        monkeypatch.setattr(app_module, "read_public_https", lambda request, timeout=12: b'{"ok":true,"result":{"message_id":1}}')
        client = TestClient(app_module.app)
        response = client.post("/api/telegram/test", json={"enabled": True, "botToken": "123:abc", "chatId": "12345"})
        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert app_module.SETTINGS_STATE["telegram"]["botToken"] == "123:abc"
        assert app_module.SETTINGS_STATE["telegram"]["chatId"] == "12345"
    finally:
        app_module.SETTINGS_STATE = original
