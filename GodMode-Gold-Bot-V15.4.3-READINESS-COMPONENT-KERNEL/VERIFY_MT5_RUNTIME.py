#!/usr/bin/env python3
"""Verify the Python/NumPy/MetaTrader5 runtime used by GodMode.

Exit codes:
  0  runtime import is compatible (and connection is healthy when --connect is used)
  10 NumPy is missing or NumPy 2.x is installed
  11 MetaTrader5 import failed
  12 mt5.initialize() failed
  13 terminal initialized but broker connection is offline
  14 unsupported platform/architecture
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path


def _load_terminal_path(root: Path) -> str:
    env_path = os.getenv("MT5_TERMINAL_PATH", "").strip()
    if env_path:
        return env_path
    settings_path = root / "backend" / "data" / "settings.json"
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        return str((data.get("mt5Connection") or {}).get("terminalPath") or "").strip()
    except Exception:
        return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--connect", action="store_true", help="also initialize MT5 and verify broker connection")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    def emit(message: str) -> None:
        if not args.quiet:
            print(message)

    emit(f"Python: {sys.version.split()[0]} ({platform.architecture()[0]})")
    if platform.system() != "Windows" or platform.architecture()[0] != "64bit":
        emit("ERROR: MetaTrader5 requires 64-bit Windows Python.")
        return 14

    try:
        import numpy as np
    except Exception as exc:
        emit(f"ERROR: NumPy import failed: {exc}")
        return 10
    emit(f"NumPy: {np.__version__}")
    try:
        major = int(str(np.__version__).split(".", 1)[0])
    except Exception:
        major = 99
    if major >= 2:
        emit("ERROR: NumPy 2.x is incompatible with the packaged MetaTrader5 binary. Required: NumPy 1.26.4.")
        return 10

    try:
        import MetaTrader5 as mt5
    except Exception as exc:
        emit(f"ERROR: MetaTrader5 import failed: {type(exc).__name__}: {exc}")
        return 11
    emit(f"MetaTrader5: {getattr(mt5, '__version__', 'unknown')}")

    if not args.connect:
        emit("MT5 Python runtime: OK")
        return 0

    root = Path(__file__).resolve().parent
    terminal_path = _load_terminal_path(root)
    try:
        ok = mt5.initialize(path=terminal_path) if terminal_path else mt5.initialize()
    except TypeError:
        ok = mt5.initialize(terminal_path) if terminal_path else mt5.initialize()
    if not ok:
        emit(f"ERROR: mt5.initialize() failed: {mt5.last_error()}")
        return 12
    try:
        info = mt5.terminal_info()
        if not info or not bool(getattr(info, "connected", False)):
            emit("ERROR: MT5 opened, but the terminal is not connected to the broker.")
            return 13
        account = mt5.account_info()
        login = getattr(account, "login", "unknown") if account else "unknown"
        server = getattr(account, "server", "unknown") if account else "unknown"
        emit(f"MT5 broker connection: OK | login={login} | server={server}")
        return 0
    finally:
        try:
            mt5.shutdown()
        except Exception as exc:
            emit(f"WARNING: mt5.shutdown() reported: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
