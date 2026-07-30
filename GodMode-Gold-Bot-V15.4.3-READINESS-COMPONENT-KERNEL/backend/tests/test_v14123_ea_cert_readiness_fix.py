from __future__ import annotations

import copy
import inspect
import os
import time
from pathlib import Path

import app
from services import runtime_safety
from services.runtime_safety import RuntimeHealth


def _heartbeat(path: Path, *, created: int | None = None, symbol: str = "XAUUSD") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"{created or int(time.time())},{app.BUILD_ID},{app.mt5_bridge.magic},"
        f"{app.mt5_bridge.comment_prefix},{symbol}\n",
        encoding="ascii",
    )
    return path


def test_windows_atomic_json_does_not_attempt_directory_fsync(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    monkeypatch.setattr(runtime_safety, "_directory_fsync_supported", lambda: False)

    def forbidden_directory_open(*_args, **_kwargs):
        raise AssertionError("directory open must not be attempted on Windows")

    monkeypatch.setattr(runtime_safety.os, "open", forbidden_directory_open)
    runtime_safety.atomic_write_json(target, {"ok": True})
    assert target.exists()


def test_tick_guard_auto_discovers_active_terminal_files_path(tmp_path, monkeypatch):
    files = tmp_path / "MQL5" / "Files"
    heartbeat = _heartbeat(files / "godmode_tickguard_heartbeat.csv")
    settings = copy.deepcopy(app.SETTINGS_STATE)
    settings.setdefault("automation", {}).update(
        {
            "mql5ControlFilePath": "",
            "requireTickGuardForLive": True,
            "tickGuardHeartbeatFileName": heartbeat.name,
        }
    )
    monkeypatch.setattr(app, "SETTINGS_STATE", settings)
    monkeypatch.setattr(
        app.mt5_bridge,
        "status",
        lambda: {
            "connected": True,
            "tradeAllowed": True,
            "terminalDataPath": str(tmp_path),
        },
    )
    monkeypatch.setattr(app, "RUNTIME_HEALTH", RuntimeHealth())

    status = app._tick_guard_heartbeat_status()

    assert status["ok"] is True
    assert status["pathSource"] == "active_mt5_terminal"
    assert Path(status["resolvedFilesPath"]) == files


def test_tick_guard_accepts_fresh_file_when_broker_clock_is_two_hours_ahead(tmp_path, monkeypatch):
    heartbeat = _heartbeat(
        tmp_path / "godmode_tickguard_heartbeat.csv",
        created=int(time.time()) + 2 * 60 * 60,
    )
    settings = copy.deepcopy(app.SETTINGS_STATE)
    settings.setdefault("automation", {}).update(
        {
            "mql5ControlFilePath": str(tmp_path),
            "requireTickGuardForLive": True,
            "tickGuardHeartbeatFileName": heartbeat.name,
        }
    )
    monkeypatch.setattr(app, "SETTINGS_STATE", settings)
    monkeypatch.setattr(app, "RUNTIME_HEALTH", RuntimeHealth())

    status = app._tick_guard_heartbeat_status()

    assert status["ok"] is True
    assert "clock offset" in status["message"]
    assert status["fileAgeSeconds"] < 5


def test_local_runtime_certification_approves_verified_running_system(tmp_path, monkeypatch):
    settings = copy.deepcopy(app.SETTINGS_STATE)
    settings.setdefault("execution", {}).update(
        {"requireLiveCertification": True, "liveCertificationMode": "local_runtime"}
    )
    monkeypatch.setattr(app, "SETTINGS_STATE", settings)
    monkeypatch.setattr(app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        app.mt5_bridge,
        "status",
        lambda: {"connected": True, "tradeAllowed": True},
    )
    monkeypatch.setattr(
        app,
        "_tick_guard_heartbeat_status",
        lambda: {"ok": True, "buildId": app.BUILD_ID},
    )
    monkeypatch.setattr(app.EXECUTION_LEDGER, "unresolved", lambda: [])
    health = RuntimeHealth()
    health.beat("trade_protection")
    health.beat("event_loop")
    health.beat("reconciliation")
    monkeypatch.setattr(app, "RUNTIME_HEALTH", health)

    status = app._live_certification_status()

    assert status["approved"] is True
    assert status["certificationType"] == "local_runtime"
    assert status["grade"] == "LOCAL_RUNTIME_ATTESTED"


def test_ea_uses_utc_for_heartbeat_and_control_expiry():
    text = (Path(__file__).resolve().parents[2] / "mt5_ea" / "GodModeTickGuard.mq5").read_text(
        encoding="utf-8"
    )
    assert "IntegerToString((long)TimeGMT())" in text
    assert "TimeGMT()>expiry" in text
    assert "TimeGMT() <= g_ctrlExpiry" in text
    assert "TimeCurrent()" not in text


def test_close_reconcile_throttle_does_not_use_stopiteration_as_flow_control():
    source = inspect.getsource(app._auto_manage_open_trades)
    assert 'raise StopIteration("close_reconcile_throttled")' not in source


def test_installer_prefers_the_active_connected_terminal():
    source = (Path(__file__).resolve().parents[2] / "install_ea.py").read_text(
        encoding="utf-8"
    )
    assert "active_terminal_data_path" in source
    assert 'getattr(info, "data_path"' in source
    assert "terminals = [active_terminal]" in source


def test_authoritative_readiness_allows_live_after_runtime_attestation(tmp_path, monkeypatch):
    settings = copy.deepcopy(app.SETTINGS_STATE)
    settings.setdefault("execution", {}).update(
        {
            "liveTradingEnabled": True,
            "autoTradingEnabled": True,
            "dryRun": False,
            "requireLiveCertification": True,
            "liveCertificationMode": "local_runtime",
        }
    )
    settings.setdefault("automation", {})["mql5ControlFilePath"] = str(tmp_path)
    monkeypatch.setattr(app, "SETTINGS_STATE", settings)
    monkeypatch.setattr(app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        app.mt5_bridge,
        "status",
        lambda: {
            "connected": True,
            "liveTradingEnabled": True,
            "tradeAllowed": True,
        },
    )
    monkeypatch.setattr(app, "_market_state", lambda: {"open": True})
    monkeypatch.setattr(app.kill_switch, "status", lambda: {"active": False})
    monkeypatch.setattr(app.EXECUTION_LEDGER, "unresolved", lambda: [])
    monkeypatch.setattr(app, "_validation_status", lambda: {"enabled": False, "passed": True})
    monkeypatch.setattr(
        app,
        "_tick_guard_heartbeat_status",
        lambda: {"ok": True, "required": True, "buildId": app.BUILD_ID},
    )
    monkeypatch.setattr(
        app,
        "_live_certification_status",
        lambda: {"approved": True, "certificationType": "local_runtime"},
    )
    health = RuntimeHealth()
    health.beat("reconciliation")
    health.beat("auto_loop")
    health.beat("trade_protection")
    health.beat("event_loop")
    health.beat("mql5_control_bridge")
    monkeypatch.setattr(app, "RUNTIME_HEALTH", health)

    result = app._authoritative_readiness()

    assert result["ready"] is True
    assert result["tradingReady"] is True
    assert result["reasons"] == []


def test_tick_guard_ignores_stale_existing_configured_path_when_active_terminal_is_fresh(tmp_path, monkeypatch):
    configured = tmp_path / "old-terminal" / "MQL5" / "Files"
    active_root = tmp_path / "active-terminal"
    active = active_root / "MQL5" / "Files"
    old = _heartbeat(configured / "godmode_tickguard_heartbeat.csv", created=int(time.time()) - 7200)
    fresh = _heartbeat(active / "godmode_tickguard_heartbeat.csv")
    old_time = time.time() - 7200
    os.utime(old, (old_time, old_time))
    settings = copy.deepcopy(app.SETTINGS_STATE)
    settings.setdefault("automation", {}).update(
        {
            "mql5ControlFilePath": str(configured),
            "requireTickGuardForLive": True,
            "tickGuardHeartbeatFileName": fresh.name,
        }
    )
    monkeypatch.setattr(app, "SETTINGS_STATE", settings)
    monkeypatch.setattr(
        app.mt5_bridge,
        "status",
        lambda: {
            "connected": True,
            "tradeAllowed": True,
            "terminalDataPath": str(active_root),
        },
    )
    monkeypatch.setattr(app, "RUNTIME_HEALTH", RuntimeHealth())

    status = app._tick_guard_heartbeat_status()

    assert status["ok"] is True
    assert status["pathSource"] == "active_mt5_terminal"
    assert Path(status["resolvedFilesPath"]) == active


def test_standalone_tick_guard_check_prefers_fresh_active_terminal(tmp_path):
    import VERIFY_TICK_GUARD as verifier

    configured = tmp_path / "old" / "MQL5" / "Files"
    active_root = tmp_path / "active"
    active = active_root / "MQL5" / "Files"
    configured.mkdir(parents=True)
    active.mkdir(parents=True)
    name = "godmode_tickguard_heartbeat.csv"
    old = configured / name
    fresh = active / name
    old.write_text("old", encoding="ascii")
    fresh.write_text("fresh", encoding="ascii")
    old_time = time.time() - 3600
    os.utime(old, (old_time, old_time))

    class Info:
        data_path = str(active_root)

    class FakeMT5:
        @staticmethod
        def terminal_info():
            return Info()

    settings = {
        "automation": {
            "mql5ControlFilePath": str(configured),
            "tickGuardHeartbeatFileName": name,
        }
    }
    resolved, source = verifier._resolve_files_dir(FakeMT5(), settings)

    assert resolved == active
    assert source == "active connected MT5 terminal"
