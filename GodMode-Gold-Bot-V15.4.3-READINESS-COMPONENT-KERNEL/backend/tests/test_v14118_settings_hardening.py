from __future__ import annotations

import asyncio
import json
import threading
import time
from copy import deepcopy

import pytest

import app
from services import live_market_feeds as feeds


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    prior_state = deepcopy(app.SETTINGS_STATE)
    prior_recovery = deepcopy(app.SETTINGS_RECOVERY_STATE)
    settings_file = tmp_path / "settings.json"
    last_good = tmp_path / "settings.lastgood.json"
    monkeypatch.setattr(app, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(app, "SETTINGS_LAST_GOOD_FILE", last_good)
    validated = app._validate_settings_candidate(prior_state)
    validated.setdefault("meta", {})["settingsRevision"] = 7
    settings_file.write_text(json.dumps(validated), encoding="utf-8")
    last_good.write_text(json.dumps(validated), encoding="utf-8")
    app.SETTINGS_STATE.clear(); app.SETTINGS_STATE.update(deepcopy(validated))
    try:
        yield settings_file, last_good, validated
    finally:
        app.SETTINGS_STATE.clear(); app.SETTINGS_STATE.update(prior_state)
        app.SETTINGS_RECOVERY_STATE.clear(); app.SETTINGS_RECOVERY_STATE.update(prior_recovery)
        app._apply_runtime_settings()


def test_critical_switches_require_real_json_booleans():
    candidate = deepcopy(app.SETTINGS_STATE)
    candidate["execution"]["liveTradingEnabled"] = "false"
    with pytest.raises(ValueError, match="must be true or false"):
        app._validate_settings_candidate(candidate)


def test_unsafe_numeric_settings_are_rejected():
    candidate = deepcopy(app.SETTINGS_STATE)
    candidate["trading"]["riskPerTrade"] = -999
    with pytest.raises(ValueError, match="trading.riskPerTrade"):
        app._validate_settings_candidate(candidate)



def test_settings_endpoint_rejects_malformed_nested_section_with_422(isolated_settings):
    response = app.update_settings({
        "settings": {**deepcopy(app.SETTINGS_STATE), "execution": "oops"},
        "expectedRevision": 7,
    })
    assert response.status_code == 422
    body = json.loads(response.body)
    assert body["validationError"] is True
    assert "execution must be an object" in body["message"]
    assert app._settings_revision() == 7

def test_stale_revision_cannot_overwrite_newer_settings(isolated_settings):
    _, _, before = isolated_settings
    with pytest.raises(app.SettingsConflictError):
        app._commit_settings_patch(
            {"execution": {"liveTradingEnabled": True, "dryRun": False}},
            reason="test_stale_revision",
            expected_revision=6,
        )
    assert app.SETTINGS_STATE["execution"]["liveTradingEnabled"] is before["execution"]["liveTradingEnabled"]
    assert app._settings_revision() == 7


def test_validation_alias_patch_is_symmetric(isolated_settings):
    receipt = app._commit_settings_patch(
        {"execution": {"validationLockEnabled": False}},
        reason="test_validation_sync",
        expected_revision=7,
    )
    assert receipt["revision"] == 8
    assert app.SETTINGS_STATE["execution"]["validationLockEnabled"] is False
    assert app.SETTINGS_STATE["validation"]["enabled"] is False


def test_disk_failure_restores_disk_and_runtime_state(isolated_settings, monkeypatch):
    settings_file, _, before = isolated_settings
    real_write = app._write_settings_payload
    calls = {"count": 0}

    def fail_first_write(path, payload):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("simulated disk failure")
        return real_write(path, payload)

    monkeypatch.setattr(app, "_write_settings_payload", fail_first_write)
    with pytest.raises(RuntimeError, match="rolled back"):
        app._commit_settings_patch(
            {"execution": {"liveTradingEnabled": True, "dryRun": False}},
            reason="test_write_failure",
            expected_revision=7,
        )
    restored = json.loads(settings_file.read_text(encoding="utf-8"))
    assert restored["execution"]["liveTradingEnabled"] is before["execution"]["liveTradingEnabled"]
    assert app.SETTINGS_STATE["execution"]["liveTradingEnabled"] is before["execution"]["liveTradingEnabled"]
    assert app._settings_revision() == 7



def test_concurrent_writers_with_same_revision_cannot_both_commit(isolated_settings):
    barrier = threading.Barrier(3)
    outcomes: list[tuple[str, object]] = []
    guard = threading.Lock()

    def writer(name: str, patch: dict):
        barrier.wait()
        try:
            receipt = app._commit_settings_patch(patch, reason=f"concurrent_{name}", expected_revision=7)
            outcome = ("ok", receipt["revision"])
        except app.SettingsConflictError as exc:
            outcome = ("conflict", exc.current)
        with guard:
            outcomes.append(outcome)

    first = threading.Thread(target=writer, args=("appearance", {"appearance": {"density": "compact"}}))
    second = threading.Thread(target=writer, args=("sound", {"notifications": {"soundEnabled": False}}))
    first.start(); second.start(); barrier.wait(); first.join(2); second.join(2)

    assert not first.is_alive() and not second.is_alive()
    assert sorted(kind for kind, _ in outcomes) == ["conflict", "ok"]
    assert app._settings_revision() == 8


def test_corrupt_primary_recovers_last_known_good_without_default_reset(tmp_path, monkeypatch):
    prior_state = deepcopy(app.SETTINGS_STATE)
    prior_recovery = deepcopy(app.SETTINGS_RECOVERY_STATE)
    settings_file = tmp_path / "settings.json"
    last_good = tmp_path / "settings.lastgood.json"
    good = app._validate_settings_candidate(deepcopy(prior_state))
    good["execution"]["autoTradingEnabled"] = True
    good.setdefault("meta", {})["settingsRevision"] = 23
    settings_file.write_text('{"execution":', encoding="utf-8")
    last_good.write_text(json.dumps(good), encoding="utf-8")
    monkeypatch.setattr(app, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(app, "SETTINGS_LAST_GOOD_FILE", last_good)
    try:
        loaded = app._load_settings()
        assert loaded["execution"]["autoTradingEnabled"] is True
        assert loaded["meta"]["settingsRevision"] == 23
        assert app.SETTINGS_RECOVERY_STATE["status"] == "recovered_last_good"
        quarantined = list(tmp_path.glob("settings.corrupt-*.json"))
        assert len(quarantined) == 1
        assert json.loads(settings_file.read_text(encoding="utf-8"))["meta"]["settingsRevision"] == 23
    finally:
        app.SETTINGS_STATE.clear(); app.SETTINGS_STATE.update(prior_state)
        app.SETTINGS_RECOVERY_STATE.clear(); app.SETTINGS_RECOVERY_STATE.update(prior_recovery)
        app._apply_runtime_settings()

def test_background_timeout_does_not_starve_other_lane():
    release = threading.Event()

    def stuck():
        release.wait(1.0)
        return {"ok": True}

    async def scenario():
        first = await app._run_background_job("v14118_stuck_lane", stuck, timeout=0.02)
        second = await app._run_background_job("v14118_independent_lane", lambda: {"ok": True, "lane": "independent"}, timeout=0.5)
        release.set()
        return first, second

    first, second = asyncio.run(scenario())
    assert first["timeout"] is True
    assert second == {"ok": True, "lane": "independent"}


def test_macro_feed_cache_and_429_backoff(monkeypatch):
    macro = feeds.MacroFeed()
    calls = {"count": 0}

    def live_text(url, headers=None, timeout=4.0):
        calls["count"] += 1
        return '{"price": 104.2, "changePercent": -0.1}'

    monkeypatch.setattr(feeds, "get_text", live_text)
    first = macro._one("DXY", "https://example.com/dxy", "", 104.21)
    second = macro._one("DXY", "https://example.com/dxy", "", 104.21)
    assert first["status"] == "live"
    assert second["cached"] is True
    assert calls["count"] == 1

    macro._cache["DXY"]["_cachedAt"] = time.time() - macro.CACHE_TTL_SECONDS - 1

    def rate_limited(url, headers=None, timeout=4.0):
        calls["count"] += 1
        raise feeds.urllib.error.HTTPError(url, 429, "Too Many Requests", None, None)

    monkeypatch.setattr(feeds, "get_text", rate_limited)
    stale = macro._one("DXY", "https://example.com/dxy", "", 104.21)
    calls_after_429 = calls["count"]
    suppressed = macro._one("DXY", "https://example.com/dxy", "", 104.21)
    assert stale["status"] == "stale_live"
    assert "429" in stale["detail"]
    assert suppressed["status"] == "stale_live"
    assert calls["count"] == calls_after_429
