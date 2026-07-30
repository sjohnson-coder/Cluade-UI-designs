from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SETTINGS_FILE = ROOT / "backend" / "data" / "settings.json"
APP_FILE = ROOT / "backend" / "app.py"


def _build_id() -> str:
    match = re.search(
        r'^BUILD_ID\s*=\s*"([^"]+)"',
        APP_FILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if not match:
        raise RuntimeError("BUILD_ID was not found in backend/app.py")
    return match.group(1)


def _settings() -> dict:
    try:
        row = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return row if isinstance(row, dict) else {}
    except Exception:
        return {}


def _resolve_files_dir(mt5, settings: dict) -> tuple[Path | None, str]:
    """Resolve the terminal that is actually producing the newest heartbeat.

    A migrated settings file can point at an old broker profile that still exists.
    Existence alone is not evidence that it is the terminal connected through the
    Python bridge, so prefer the directory with the freshest heartbeat and then the
    active terminal data path.
    """
    auto = settings.get("automation") if isinstance(settings.get("automation"), dict) else {}
    heartbeat_name = str(auto.get("tickGuardHeartbeatFileName") or "godmode_tickguard_heartbeat.csv")
    candidates: list[tuple[Path, str]] = []
    configured = str(auto.get("mql5ControlFilePath") or "").strip()
    if configured:
        candidate = Path(configured)
        candidate = candidate if candidate.is_dir() or not candidate.suffix else candidate.parent
        if candidate.exists():
            candidates.append((candidate, "configured settings path"))
    info = mt5.terminal_info()
    data_path = str(getattr(info, "data_path", "") or "").strip() if info else ""
    active = Path(data_path) / "MQL5" / "Files" if data_path else None
    if active is not None:
        active.mkdir(parents=True, exist_ok=True)
        if not any(path.resolve() == active.resolve() for path, _ in candidates):
            candidates.append((active, "active connected MT5 terminal"))
    fresh: list[tuple[float, Path, str]] = []
    for path, source in candidates:
        heartbeat = path / heartbeat_name
        try:
            if heartbeat.is_file():
                fresh.append((heartbeat.stat().st_mtime, path, source))
        except OSError:
            continue
    if fresh:
        _mtime, path, source = max(fresh, key=lambda row: row[0])
        return path, source
    if active is not None:
        return active, "active connected MT5 terminal"
    if candidates:
        return candidates[0]
    return None, "unresolved"


def verify(wait_seconds: int = 0) -> int:
    try:
        import MetaTrader5 as mt5  # type: ignore
    except Exception as exc:
        print(f"FAIL: MetaTrader5 Python module could not load: {exc}")
        return 2

    settings = _settings()
    mt5_cfg = settings.get("mt5Connection") if isinstance(settings.get("mt5Connection"), dict) else {}
    terminal_path = str(mt5_cfg.get("terminalPath") or "").strip()
    initialized = mt5.initialize(path=terminal_path) if terminal_path else mt5.initialize()
    if not initialized:
        print(f"FAIL: MT5 initialize failed: {mt5.last_error()}")
        return 3

    info = mt5.terminal_info()
    if not info or not bool(getattr(info, "connected", False)):
        print("FAIL: MT5 terminal is not connected to the broker.")
        return 4

    files_dir, source = _resolve_files_dir(mt5, settings)
    if files_dir is None:
        print("FAIL: Could not resolve the active terminal MQL5\\Files folder.")
        return 5

    auto = settings.get("automation") if isinstance(settings.get("automation"), dict) else {}
    heartbeat_name = str(auto.get("tickGuardHeartbeatFileName") or "godmode_tickguard_heartbeat.csv")
    heartbeat = files_dir / heartbeat_name
    deadline = time.time() + max(0, wait_seconds)
    while not heartbeat.exists() and time.time() < deadline:
        time.sleep(1)

    print(f"Build: {_build_id()}")
    print(f"MT5 terminal: {getattr(info, 'name', '')}")
    print(f"MT5 data path: {getattr(info, 'data_path', '')}")
    print(f"Tick Guard files path: {files_dir} ({source})")
    print(f"Heartbeat: {heartbeat}")

    if not heartbeat.exists():
        print("FAIL: Heartbeat file does not exist.")
        print("Remove any older EA from the chart, compile V15.0.7, attach it to XAUUSD,")
        print("tick Allow Algo Trading, and ensure the MT5 Algo Trading toolbar button is green.")
        return 6

    try:
        parts = heartbeat.read_text(encoding="ascii", errors="strict").strip().split(",")
        if len(parts) < 5:
            raise ValueError("heartbeat format is incomplete")
        created = float(parts[0])
        build = parts[1].strip()
        magic = int(float(parts[2]))
        prefix = parts[3].strip()
        symbol = parts[4].strip().upper()
    except Exception as exc:
        print(f"FAIL: Heartbeat could not be parsed: {exc}")
        return 7

    now = time.time()
    timestamp_age = now - created
    file_age = now - heartbeat.stat().st_mtime
    trading = settings.get("trading") if isinstance(settings.get("trading"), dict) else {}
    expected_build = _build_id()
    expected_magic = int(trading.get("magicNumber") or 20250525)
    expected_prefix = str(trading.get("commentPrefix") or "GODMODE_")
    expected_symbol = str(trading.get("symbol") or "XAUUSD").upper()

    failures: list[str] = []
    if build != expected_build:
        failures.append(f"EA build is {build!r}, expected {expected_build!r}")
    if magic != expected_magic:
        failures.append(f"EA MagicNumber is {magic}, expected {expected_magic}")
    if prefix != expected_prefix:
        failures.append(f"EA CommentPrefix is {prefix!r}, expected {expected_prefix!r}")
    if symbol != expected_symbol:
        failures.append(f"EA chart symbol is {symbol!r}, expected {expected_symbol!r}")
    if file_age < -5 or file_age > 30:
        failures.append(f"heartbeat file is stale ({file_age:.1f}s)")
    if not (-5 <= timestamp_age <= 30) and abs(timestamp_age) < 300:
        failures.append(f"heartbeat timestamp is stale ({timestamp_age:.1f}s)")

    print(f"Heartbeat build: {build}")
    print(f"Heartbeat file age: {file_age:.1f}s")
    print(f"Heartbeat timestamp age: {timestamp_age:.1f}s")
    print(f"Magic / prefix / symbol: {magic} / {prefix} / {symbol}")

    if failures:
        print("FAIL:")
        for item in failures:
            print(f"  - {item}")
        return 8

    if abs(timestamp_age) >= 300:
        print("NOTE: Broker clock offset detected; local file freshness confirms the EA is active.")
    print("PASS: Exact-build Tick Guard heartbeat is fresh and matched to this bot.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the active GodMode Tick Guard EA.")
    parser.add_argument("--wait", type=int, default=0, help="seconds to wait for the heartbeat")
    args = parser.parse_args()
    return verify(max(0, args.wait))


if __name__ == "__main__":
    raise SystemExit(main())
