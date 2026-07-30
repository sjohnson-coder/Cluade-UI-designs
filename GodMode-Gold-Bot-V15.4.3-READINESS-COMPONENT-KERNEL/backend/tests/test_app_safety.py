import app


def test_version_and_truthful_status():
    assert app.APP_VERSION == "15.4.3"
    status = app.status()
    if not status["mt5"].get("connected"):
        assert status["mt5Connected"] is False
        assert status["liveConnection"] is False


def test_settings_save_is_atomic(tmp_path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(app, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(app, "SETTINGS_LAST_GOOD_FILE", tmp_path / "settings.last-good.json")
    receipt = app._save_settings("test")
    assert receipt["ok"] is True
    assert settings_file.exists()
