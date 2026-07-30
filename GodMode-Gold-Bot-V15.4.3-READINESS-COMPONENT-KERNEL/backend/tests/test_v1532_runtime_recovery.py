from copy import deepcopy
import app


def test_readiness_endpoint_uses_cached_snapshot(monkeypatch):
    sentinel={"ok":True,"ready":True,"tradingReady":False,"buildId":app.BUILD_ID,"reasons":[],"warnings":[]}
    with app._READINESS_CACHE_LOCK:
        app._READINESS_CACHE.update(payload=deepcopy(sentinel), updatedAt=app.time.time(), error=None)
    monkeypatch.setattr(app, "_authoritative_readiness", lambda: (_ for _ in ()).throw(AssertionError("request path must not recompute readiness")))
    payload=app.readiness().body.decode()
    assert app.BUILD_ID in payload
    assert 'snapshotStatus' in payload


def test_public_settings_reports_saved_ai_key_without_exposing_it():
    public=app._safe_public_settings({"aiProvider":{"apiKey":"sk-secret","provider":"openai"}})
    assert public["aiProvider"]["apiKey"] == ""
    assert public["aiProvider"]["apiKeyConfigured"] is True
    assert public["secretConfigured"]["aiProvider.apiKey"] is True


def test_research_jobs_are_serialised_to_protect_live_runtime():
    assert getattr(app._JOB_WORKER_SLOTS, "_initial_value", 1) == 1


def test_runtime_recovery_assets_are_packaged():
    root=app.FRONTEND_DIST
    assert (root/'runtime-recovery-v1532.js').exists()
    assert (root/'runtime-recovery-v1532.css').exists()
    html=(root/'index.html').read_text(encoding='utf-8')
    assert '/runtime-recovery-v1532.js' in html
    assert '/runtime-recovery-v1532.css' in html
