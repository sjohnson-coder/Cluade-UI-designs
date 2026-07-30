from copy import deepcopy
from fastapi.testclient import TestClient

import app


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(app, 'SETTINGS_FILE', tmp_path / 'settings.json')
    monkeypatch.setattr(app, 'SETTINGS_LAST_GOOD_FILE', tmp_path / 'settings.last_good.json')
    state = app._validate_settings_candidate(app._default_settings(), strict_ranges=False)
    app.SETTINGS_STATE.clear(); app.SETTINGS_STATE.update(deepcopy(state))
    return TestClient(app.app)


def test_public_settings_round_trip_drops_derived_secret_flags(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    app.SETTINGS_STATE['telegram']['botToken'] = '123:abc'
    public = app._safe_public_settings(app.SETTINGS_STATE)
    public['validation']['allowTelegramManualOverride'] = True
    public['execution']['mode'] = 'auto'
    r = c.post('/api/settings', json={'settings': public, 'expectedRevision': 0})
    assert r.status_code == 200, r.text
    assert r.json()['ok'] is True
    assert app.SETTINGS_STATE['validation']['allowTelegramManualOverride'] is True
    assert app.SETTINGS_STATE['execution']['mode'] == 'auto'
    assert 'secretConfigured' not in app.SETTINGS_STATE
    assert 'botTokenConfigured' not in app.SETTINGS_STATE['telegram']
    assert app.SETTINGS_STATE['telegram']['botToken'] == '123:abc'


def test_telegram_save_accepts_public_telegram_object_without_persisting_flags(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    app.SETTINGS_STATE['telegram']['botToken'] = '123:abc'
    public = app._safe_public_settings(app.SETTINGS_STATE)['telegram']
    public.update({'chatId': '42', 'enabled': True})
    r = c.post('/api/telegram/save', json=public)
    assert r.status_code == 200, r.text
    assert r.json()['ok'] is True
    assert app.SETTINGS_STATE['telegram']['botToken'] == '123:abc'
    assert 'botTokenConfigured' not in app.SETTINGS_STATE['telegram']
