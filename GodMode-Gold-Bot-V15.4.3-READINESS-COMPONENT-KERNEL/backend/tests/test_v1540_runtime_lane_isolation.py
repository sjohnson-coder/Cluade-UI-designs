import asyncio
import time
from copy import deepcopy

import app
from services.runtime_lanes import ProtectedThreadLane


def test_readiness_cache_tracks_last_success_separately_from_failed_attempt(monkeypatch):
    good={"ok":True,"ready":True,"tradingReady":True,"reasons":[],"warnings":[],"buildId":app.BUILD_ID}
    with app._READINESS_CACHE_LOCK:
        app._READINESS_CACHE.update(payload=deepcopy(good), lastSuccessAt=time.time(), lastAttemptAt=time.time(), error=None)
    monkeypatch.setattr(app, "_authoritative_readiness", lambda: (_ for _ in ()).throw(RuntimeError("probe blocked")))
    app._record_readiness_failure("probe blocked")
    payload=app._cached_readiness_snapshot()
    assert payload["ready"] is True
    assert payload["snapshotStatus"] == "LIVE"
    assert payload["refreshError"] == "probe blocked"
    assert payload["lastAttemptAgeSeconds"] is not None


def test_protected_lane_rotates_after_timeout():
    async def scenario():
        lane=ProtectedThreadLane("test", timeout_seconds=0.02)
        try:
            try:
                await lane.run(lambda: time.sleep(0.15))
            except asyncio.TimeoutError:
                timed_out = True
            else:
                timed_out = False
            assert timed_out is True
            result=await lane.run(lambda: "ok", timeout_seconds=0.2)
            snap=lane.snapshot()
            assert result == "ok"
            assert snap["timeouts"] == 1
            assert snap["rotations"] == 1
            assert snap["successes"] == 1
        finally:
            lane.shutdown()
    asyncio.run(scenario())


def test_research_throttle_detects_live_runtime_pressure(monkeypatch):
    monkeypatch.setattr(app, "_live_runtime_pressure", lambda: {"busy":True,"reason":"open_position"})
    assert app._research_pause_seconds() >= 0.05


def test_runtime_lane_identity_and_assets_are_packaged():
    assert app.BUILD_ID == "V15.4.3-READINESS-COMPONENT-KERNEL"
    assert app.READINESS_LANE.name == "readiness"


def test_runtime_lanes_endpoint_exposes_health(monkeypatch):
    monkeypatch.setattr(app, "_live_runtime_pressure", lambda: {"busy":False,"reason":""})
    payload=app.runtime_lanes()
    assert payload["buildId"] == app.BUILD_ID
    assert payload["readiness"]["name"] == "readiness"
    assert "priorityIntent" in payload
