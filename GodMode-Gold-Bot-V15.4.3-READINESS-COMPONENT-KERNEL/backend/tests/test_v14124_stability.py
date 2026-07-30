from pathlib import Path
from fastapi.testclient import TestClient
import importlib.util

ROOT=Path(__file__).resolve().parents[2]

def load_app():
    spec=importlib.util.spec_from_file_location('gm_app_v1424', ROOT/'backend'/'app.py')
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod

def test_tools_csp_allows_its_inline_controls():
    m=load_app(); c=TestClient(m.app)
    r=c.get('/tools')
    assert r.status_code==200
    assert "script-src 'self' 'unsafe-inline'" in r.headers['content-security-policy']
    assert 'onclick="whySilent()"' in r.text

def test_normal_dashboard_csp_stays_strict():
    m=load_app(); c=TestClient(m.app)
    r=c.get('/')
    assert r.status_code==200
    assert "script-src 'self';" in r.headers['content-security-policy']
    assert "script-src 'self' 'unsafe-inline'" not in r.headers['content-security-policy']

def test_telegram_save_is_independent_of_network(monkeypatch, tmp_path):
    m=load_app(); c=TestClient(m.app)
    monkeypatch.setattr(m, 'SETTINGS_FILE', tmp_path/'settings.json')
    r=c.post('/api/telegram/save', json={'enabled':True,'botToken':'123:abc','chatId':'42'}, headers={'Origin':'http://testserver'})
    assert r.status_code==200 and r.json()['saved'] is True
    assert m.SETTINGS_STATE['telegram']['botToken']=='123:abc'

def test_telegram_test_failure_still_saves(monkeypatch, tmp_path):
    m=load_app(); c=TestClient(m.app)
    monkeypatch.setattr(m, 'SETTINGS_FILE', tmp_path/'settings.json')
    def fail(*a, **k): raise OSError('offline')
    monkeypatch.setattr(m, 'read_public_https', fail)
    r=c.post('/api/telegram/test', json={'enabled':True,'botToken':'123:abc','chatId':'42'}, headers={'Origin':'http://testserver'})
    assert r.status_code==502
    assert r.json()['saved'] is True
    assert m.SETTINGS_STATE['telegram']['botToken']=='123:abc'

def test_masked_secret_is_not_overwritten(monkeypatch, tmp_path):
    m=load_app(); monkeypatch.setattr(m, 'SETTINGS_FILE', tmp_path/'settings.json')
    m.SETTINGS_STATE.setdefault('telegram',{})['botToken']='real-token'
    m._commit_settings_patch({'telegram':{'botToken':'••••••••','chatId':'99'}}, reason='test')
    assert m.SETTINGS_STATE['telegram']['botToken']=='real-token'
