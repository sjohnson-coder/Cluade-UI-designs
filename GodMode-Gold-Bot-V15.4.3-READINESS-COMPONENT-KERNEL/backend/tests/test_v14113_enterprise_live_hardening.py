from __future__ import annotations

import io
import copy
import hashlib
import json
import os
import socket
import time
import urllib.request
from pathlib import Path

import pytest

from services import safe_http
from services.dynamic_sl_v14 import (
    BrokerRules,
    DynamicSLState,
    PositionSnapshot,
    decide,
)
from services.live_certification import (
    REQUIRED_GATES,
    evaluate_live_certification,
    sign_certification_payload,
)
from services.exit_policy_replay import replay_dynamic_sl
from services.runtime_safety import LoopLatencyWatchdog, atomic_write_json


class _Headers(dict[str, str]):
    def get(self, key: str, default=None):  # type: ignore[no-untyped-def]
        return super().get(key, default)


class _FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.reason = "OK"
        self.headers = _Headers(headers or {})
        self._stream = io.BytesIO(body)

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def close(self) -> None:
        pass


class _FakePinnedConnection:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.requests: list[tuple[str, str, bytes | None, dict[str, str]]] = []

    def request(
        self,
        method: str,
        target: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.requests.append((method, target, body, headers or {}))

    def getresponse(self) -> _FakeResponse:
        return self._response

    def close(self) -> None:
        pass


def _public_dns(*_args, **_kwargs):  # type: ignore[no-untyped-def]
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


def test_safe_http_pins_request_to_validated_address_and_tolerates_bad_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _FakeResponse(b'{"ok":true}', headers={"Content-Length": "not-a-number"})
    fake = _FakePinnedConnection(response)
    opened: list[tuple[str, int, str, float]] = []

    monkeypatch.setattr(safe_http.socket, "getaddrinfo", _public_dns)

    def open_connection(host: str, port: int, address: str, timeout: float):
        opened.append((host, port, address, timeout))
        return fake

    monkeypatch.setattr(safe_http, "_open_pinned_connection", open_connection)
    request = urllib.request.Request(
        "https://feeds.example.test/v1/data?symbol=XAUUSD",
        data=b'{"window":20}',
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    result = safe_http.read_public_https(request, timeout=3, max_bytes=1024)

    assert result == b'{"ok":true}'
    assert opened == [("feeds.example.test", 443, "93.184.216.34", 3.0)]
    assert fake.requests == [
        (
            "POST",
            "/v1/data?symbol=XAUUSD",
            b'{"window":20}',
            {
                "Content-type": "application/json",
                "Host": "feeds.example.test",
                "Connection": "close",
            },
        )
    ]


def test_safe_http_rejects_private_or_changed_connected_peer() -> None:
    with pytest.raises(ValueError, match="non-public"):
        safe_http.validate_connected_public_peer(
            "127.0.0.1",
            "93.184.216.34",
        )
    with pytest.raises(ValueError, match="does not match"):
        safe_http.validate_connected_public_peer(
            "93.184.216.35",
            "93.184.216.34",
        )
    assert (
        safe_http.validate_connected_public_peer(
            "93.184.216.34",
            "93.184.216.34",
        )
        == "93.184.216.34"
    )


def test_safe_http_preserves_a_bounded_http_error_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _FakeResponse(
        b'{"error":"rate limited"}',
        status=429,
        headers={"Content-Length": "24"},
    )
    fake = _FakePinnedConnection(response)
    monkeypatch.setattr(safe_http.socket, "getaddrinfo", _public_dns)
    monkeypatch.setattr(
        safe_http,
        "_open_pinned_connection",
        lambda *_args, **_kwargs: fake,
    )

    with pytest.raises(urllib.error.HTTPError) as caught:
        safe_http.read_public_https(
            "https://api.example.test/v1/request",
            max_bytes=1024,
        )

    assert caught.value.code == 429
    assert caught.value.read() == b'{"error":"rate limited"}'


@pytest.mark.parametrize(
    ("side", "entry", "bid", "ask", "current_sl", "desired_sl", "expected_floor"),
    [
        ("BUY", 100.0, 106.0, 106.2, 105.8, 100.5, 105.5),
        ("SELL", 4050.0, 4043.8, 4044.0, 4042.5, 4049.5, 4044.5),
    ],
)
def test_dynamic_sl_breathing_never_bypasses_peak_retention_floor(
    side: str,
    entry: float,
    bid: float,
    ask: float,
    current_sl: float,
    desired_sl: float,
    expected_floor: float,
) -> None:
    snapshot = PositionSnapshot(
        ticket=901,
        symbol="XAUUSD",
        side=side,
        entry=entry,
        bid=bid,
        ask=ask,
        sl=current_sl,
        tp=None,
        volume=0.01,
        initial_risk_price=5.0,
        peak_profit_r=2.0,
        current_profit_r=1.2,
        timestamp=time.time(),
        sequence=7,
    )
    rules = BrokerRules(
        tick_size=0.1,
        point=0.1,
        stops_level_points=1.0,
        freeze_level_points=1.0,
    )

    decision = decide(
        snapshot,
        rules,
        state=DynamicSLState.TRAILING_CONTINUATION,
        recovery_score=72,
        invalidated=False,
        max_giveback_fraction=0.45,
        desired_sl=desired_sl,
    )

    assert decision.blocked is False
    assert decision.state_after is DynamicSLState.BREATHING
    assert decision.proposed_sl == expected_floor
    assert "PEAK_RETENTION_FLOOR" in decision.reason_codes


def test_atomic_json_write_preserves_last_good_file_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "protection_state.json"
    target.write_text('{"generation":1}\n', encoding="utf-8")

    def failed_replace(_source, _target):  # type: ignore[no-untyped-def]
        raise OSError("simulated disk/replace failure")

    monkeypatch.setattr(os, "replace", failed_replace)

    with pytest.raises(OSError, match="simulated"):
        atomic_write_json(target, {"generation": 2})

    assert json.loads(target.read_text(encoding="utf-8")) == {"generation": 1}
    assert not list(tmp_path.glob(".protection_state.json.*.tmp"))


def test_atomic_json_write_fsyncs_replaces_and_reads_back(tmp_path: Path) -> None:
    target = tmp_path / "protection_state.json"
    atomic_write_json(target, {"generation": 3, "tickets": {"44": {"sl": 4044.5}}})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "generation": 3,
        "tickets": {"44": {"sl": 4044.5}},
    }
    assert not list(tmp_path.glob(".protection_state.json.*.tmp"))


def test_loop_latency_watchdog_requires_sustained_lag_and_recovers() -> None:
    watchdog = LoopLatencyWatchdog(
        expected_interval_seconds=1.0,
        lag_threshold_seconds=0.5,
        breach_limit=3,
        recovery_limit=2,
    )

    assert watchdog.observe(1.7)["ok"] is True
    assert watchdog.observe(1.8)["ok"] is True
    failed = watchdog.observe(1.6)
    assert failed["ok"] is False
    assert failed["consecutiveBreaches"] == 3
    assert failed["lagSeconds"] == pytest.approx(0.6)

    assert watchdog.observe(1.1)["ok"] is False
    recovered = watchdog.observe(1.0)
    assert recovered["ok"] is True
    assert recovered["consecutiveBreaches"] == 0


def _certification_payload(
    build_id: str,
    now: float,
    evidence_root: Path,
    signing_key: str,
) -> dict:
    evidence_root.mkdir(parents=True, exist_ok=True)
    gates = {}
    for gate in REQUIRED_GATES:
        artifact = evidence_root / f"{gate}.json"
        artifact.write_text(
            json.dumps({"gate": gate, "buildId": build_id}) + "\n",
            encoding="utf-8",
        )
        gates[gate] = {
            "passed": True,
            "observedAt": now - 60,
            "evidence": f"{gate}.json",
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        }
    payload = {
        "schemaVersion": 2,
        "buildId": build_id,
        "issuer": "release-officer",
        "signatureAlgorithm": "hmac-sha256",
        "issuedAt": now - 60,
        "expiresAt": now + 3600,
        "gates": gates,
    }
    payload["signature"] = sign_certification_payload(
        payload,
        signing_key=signing_key,
    )
    return payload


def test_live_certification_is_fail_closed_complete_and_build_bound(
    tmp_path: Path,
) -> None:
    now = 1_800_000_000.0
    build_id = "V15.4.3-READINESS-COMPONENT-KERNEL"
    signing_key = "test-only-certification-key-with-32-bytes"
    verification = {
        "evidence_root": tmp_path,
        "signing_key": signing_key,
        "trusted_issuers": {"release-officer"},
    }

    missing = evaluate_live_certification(
        {},
        build_id=build_id,
        now=now,
        **verification,
    )
    assert missing["approved"] is False
    assert missing["grade"] == "NOT_CERTIFIED"
    assert set(missing["missingGates"]) == set(REQUIRED_GATES)

    valid = evaluate_live_certification(
        _certification_payload(build_id, now, tmp_path, signing_key),
        build_id=build_id,
        now=now,
        **verification,
    )
    assert valid["approved"] is True
    assert valid["grade"] == "A+"

    wrong_build = evaluate_live_certification(
        _certification_payload("V14.1.12-OTHER", now, tmp_path, signing_key),
        build_id=build_id,
        now=now,
        **verification,
    )
    assert wrong_build["approved"] is False
    assert "BUILD_ID_MISMATCH" in wrong_build["failures"]

    expired_payload = _certification_payload(build_id, now, tmp_path, signing_key)
    expired_payload["expiresAt"] = now - 1
    expired_payload["signature"] = sign_certification_payload(
        expired_payload,
        signing_key=signing_key,
    )
    expired = evaluate_live_certification(
        expired_payload,
        build_id=build_id,
        now=now,
        **verification,
    )
    assert expired["approved"] is False
    assert "CERTIFICATION_EXPIRED" in expired["failures"]


def test_backend_defaults_to_build_bound_live_certification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app as backend_app

    monkeypatch.setattr(
        backend_app,
        "LIVE_CERTIFICATION_FILE",
        tmp_path / "live_certification.json",
    )
    settings = copy.deepcopy(backend_app.SETTINGS_STATE)
    settings.setdefault("execution", {})["liveCertificationMode"] = "enterprise_evidence"
    monkeypatch.setattr(backend_app, "SETTINGS_STATE", settings)

    assert (
        backend_app._default_settings()["execution"]["requireLiveCertification"]
        is True
    )
    status = backend_app._live_certification_status()
    assert status["approved"] is False
    assert status["buildId"] == "V15.4.3-READINESS-COMPONENT-KERNEL"


def test_dynamic_sl_tick_replay_protects_chart_like_sell_retracement() -> None:
    """A +2.9R SELL must not be allowed to round-trip to break-even."""
    entry = 4050.55
    spread = 0.20
    mids = [
        4050.45,
        4049.00,
        4047.00,
        4044.00,
        4041.50,
        4042.00,
        4043.50,
        4045.80,
        4047.00,
    ]
    ticks = [
        {
            "time": 1_800_000_000 + index,
            "bid": mid - spread / 2,
            "ask": mid + spread / 2,
            "recoveryScore": 72,
        }
        for index, mid in enumerate(mids)
    ]

    result = replay_dynamic_sl(
        ticks,
        side="SELL",
        entry=entry,
        initial_sl=4053.65,
        tick_size=0.01,
        point=0.01,
        max_giveback_fraction=0.45,
        protect_start_r=0.55,
    )

    assert result["ok"] is True
    assert result["exitReason"] == "STOP_HIT"
    assert result["peakR"] > 2.8
    assert result["realizedR"] > 1.4
    assert result["realizedR"] >= result["peakR"] * 0.50
    assert any(
        "PEAK_RETENTION_FLOOR" in event.get("reasonCodes", [])
        or event.get("lockedR", 0) >= 1.5
        for event in result["events"]
    )


def test_trade_protection_telemetry_is_derived_not_hardcoded() -> None:
    import app as backend_app

    row = backend_app._decorate_trade_protection(
        {
            "ticket": 77,
            "direction": "SELL",
            "entryPrice": 4050.55,
            "currentPrice": 4044.55,
            "sl": 4045.55,
        },
        {
            "riskBasis": 3.10,
            "peakR": 2.90,
            "currentR": 1.94,
            "recoveryScore": 72,
            "beMoved": True,
            "trailLevel": 4045.55,
            "breathCount": 1,
            "dynamicSlDecision": {
                "state_after": "BREATHING",
                "reason_codes": [
                    "V14_STATE_TRANSITION",
                    "PEAK_RETENTION_FLOOR",
                ],
                "created_at": time.time(),
                "blocked": False,
            },
        },
    )

    assert row["dynamicSlState"] == "BREATHING"
    assert row["dynamicSlDecisionSource"] == "deterministic_v14"
    assert row["peakR"] == 2.9
    assert row["currentR"] == 1.94
    assert row["lockedR"] == round((4050.55 - 4045.55) / 3.10, 3)
    assert row["givebackR"] == pytest.approx(0.96)
    assert row["brokerProtected"] is True
    assert row["dynamicSlReasonCodes"] == [
        "V14_STATE_TRANSITION",
        "PEAK_RETENTION_FLOOR",
    ]


def test_burst_concurrent_evaluation_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app as backend_app

    monkeypatch.setattr(
        backend_app,
        "_protected_burst_cfg",
        lambda: {"enabled": True},
    )
    assert backend_app.PROTECTED_BURST_EVALUATION_LOCK.acquire(blocking=False)
    try:
        result = backend_app._maybe_execute_protected_burst_add(
            [{"ticket": 1, "symbol": "XAUUSD", "direction": "SELL"}],
            {"symbol": "XAUUSD", "price": 4040.0},
            {"side": "SELL"},
        )
    finally:
        backend_app.PROTECTED_BURST_EVALUATION_LOCK.release()

    assert result == {
        "ok": False,
        "blocked": True,
        "reason": "protected_burst_busy",
        "message": "Protected Burst evaluation already in progress.",
    }


def test_telegram_group_commands_require_the_configured_human_user() -> None:
    import app as backend_app

    group_chat = "-100998877"
    update = {
        "message": {
            "chat": {"id": group_chat, "type": "supergroup"},
            "from": {"id": 445566},
            "text": "/burst_now",
        }
    }

    assert not backend_app._telegram_update_is_authorized(
        update,
        group_chat,
        "",
    )
    assert not backend_app._telegram_update_is_authorized(
        update,
        group_chat,
        "112233",
    )
    assert backend_app._telegram_update_is_authorized(
        update,
        group_chat,
        "445566",
    )


def test_health_center_surfaces_certification_and_event_loop_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app as backend_app

    monkeypatch.setattr(
        backend_app,
        "_live_certification_status",
        lambda: {
            "approved": False,
            "grade": "NOT CERTIFIED",
            "detail": "Required broker evidence is missing.",
        },
    )
    monkeypatch.setattr(
        backend_app.RUNTIME_HEALTH,
        "snapshot",
        lambda _thresholds: {
            "event_loop": {
                "ok": False,
                "detail": "Sustained event-loop lag detected.",
            }
        },
    )

    payload = backend_app.health_full()
    components = {row["id"]: row for row in payload["components"]}

    assert payload["liveCertification"]["approved"] is False
    assert components["liveCertification"]["status"] == "warn"
    assert components["eventLoop"]["status"] == "down"
    assert payload["tradingAllowed"] is False


def test_release_extractor_rejects_windows_traversal_and_duplicate_members(
    tmp_path: Path,
) -> None:
    import importlib.util
    import zipfile

    verifier_path = Path(__file__).resolve().parents[2] / "VERIFY_RELEASE.py"
    spec = importlib.util.spec_from_file_location("v14113_release_verifier", verifier_path)
    assert spec and spec.loader
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)

    archive = tmp_path / "hostile.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(r"..\escape.txt", "not allowed")
        bundle.writestr("release/duplicate.txt", "first")
        with pytest.warns(UserWarning, match="Duplicate name"):
            bundle.writestr("release/duplicate.txt", "second")

    errors = verifier.safe_extract(archive, tmp_path / "extract")

    assert any("unsafe archive path" in row for row in errors)
    assert any("duplicate archive member" in row for row in errors)
    assert not (tmp_path / "escape.txt").exists()


def test_all_production_https_calls_use_the_dns_pinned_transport() -> None:
    backend = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    for path in sorted(backend.rglob("*.py")):
        if "tests" in path.parts or path.name == "safe_http.py":
            continue
        if "urllib.request.urlopen(" in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(backend).as_posix())

    assert offenders == [], (
        "Direct urlopen bypasses DNS pinning, peer validation, proxy isolation, "
        f"redirect revalidation, and response bounds: {offenders}"
    )
