"""GodMode tick-EA installer.

Automates everything that CAN be automated for the GodModeTickGuard MT5 EA:
  1. Finds every MetaTrader 5 data folder on this PC.
  2. Copies GodModeTickGuard.mq5 into each terminal's MQL5\\Experts folder.
  3. Tries to compile it to .ex5 using that terminal's MetaEditor (so it's ready to run).
  4. Auto-fills the bot's `automation.mql5ControlFilePath` setting to the terminal's
     MQL5\\Files folder so the AI <-> EA bridge works out of the box.

The ONE step MT5 does not allow any tool to automate: dragging the EA onto a chart
and enabling Algo Trading. The script prints exactly what to do at the end.

Pure standard library — no extra installs.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    import MetaTrader5 as mt5  # type: ignore
except Exception:
    mt5 = None

HERE = Path(__file__).resolve().parent
EA_SRC = HERE / "mt5_ea" / "GodModeTickGuard.mq5"
SETTINGS = HERE / "backend" / "data" / "settings.json"


def _p(msg: str) -> None:
    print(msg, flush=True)


def find_terminals() -> list[Path]:
    appdata = os.environ.get("APPDATA", "")
    base = Path(appdata) / "MetaQuotes" / "Terminal"
    out: list[Path] = []
    if base.exists():
        for d in base.iterdir():
            try:
                if d.is_dir() and d.name.lower() != "common" and (d / "MQL5").exists():
                    out.append(d)
            except OSError as exc:
                _p(f"   - warning: unable to inspect terminal folder {d}: {exc}")
    return out


def active_terminal_data_path() -> Path | None:
    """Return the data folder of the terminal actually connected by Python MT5.

    Selecting the first AppData profile is unreliable when several brokers are
    installed. The EA must be copied into the same terminal profile that the bot
    is connected to, otherwise its heartbeat is written to a different Files
    directory and the backend reports that the guard is missing.
    """
    if mt5 is None:
        return None
    try:
        terminal_path = ""
        try:
            if SETTINGS.exists():
                row = json.loads(SETTINGS.read_text(encoding="utf-8"))
                terminal_path = str(
                    (row.get("mt5Connection") or {}).get("terminalPath") or ""
                ).strip()
        except Exception:
            terminal_path = ""
        initialized = mt5.initialize(path=terminal_path) if terminal_path else mt5.initialize()
        if not initialized:
            return None
        info = mt5.terminal_info()
        raw = str(getattr(info, "data_path", "") or "").strip() if info else ""
        return Path(raw) if raw and Path(raw).exists() else None
    except Exception:
        return None


def read_origin_install_dir(term: Path) -> Path | None:
    """origin.txt inside the data folder points at the terminal's install directory."""
    origin = term / "origin.txt"
    if not origin.exists():
        return None
    for enc in ("utf-16", "utf-16-le", "utf-8", "latin-1"):
        try:
            raw = origin.read_text(encoding=enc, errors="ignore")
            cleaned = raw.replace("\x00", "").strip().strip('"')
            if cleaned and Path(cleaned).exists():
                return Path(cleaned)
        except Exception:
            continue
    return None


def find_metaeditor(term: Path) -> Path | None:
    inst = read_origin_install_dir(term)
    if inst:
        cand = inst / "metaeditor64.exe"
        if cand.exists():
            return cand
        cand32 = inst / "metaeditor.exe"
        if cand32.exists():
            return cand32
    # Fallback: scan common install roots (first match wins).
    for root in (r"C:\Program Files", r"C:\Program Files (x86)"):
        rp = Path(root)
        if not rp.exists():
            continue
        try:
            for m in rp.glob("*/metaeditor64.exe"):
                return m
        except OSError as exc:
            _p(f"   - warning: unable to scan {rp}: {exc}")
    return None


def compile_ea(term: Path, mq5_path: Path) -> bool:
    editor = find_metaeditor(term)
    if not editor:
        return False
    log_path = mq5_path.with_suffix(".compile.log")
    ex5 = mq5_path.with_suffix(".ex5")
    # Never let a stale binary masquerade as this source revision. Preserve the
    # previous build under a non-loadable name, then require MetaEditor to create
    # a genuinely new .ex5 beside the copied source.
    if ex5.exists():
        backup = ex5.with_name(f"{ex5.name}.previous-{time.time_ns()}")
        try:
            ex5.replace(backup)
        except OSError:
            return False
    try:
        completed = subprocess.run(
            [str(editor), f"/compile:{mq5_path}", f"/log:{log_path}"],
            timeout=150,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
    except Exception:
        return False
    if completed.returncode not in (0, 1):
        return False
    # MetaEditor sometimes returns before the file is flushed — poll briefly.
    for _ in range(10):
        if ex5.exists():
            after_ns = ex5.stat().st_mtime_ns
            if after_ns >= mq5_path.stat().st_mtime_ns:
                return True
        time.sleep(0.5)
    return False


def set_control_path(files_dir: Path) -> None:
    try:
        data = {}
        if SETTINGS.exists():
            try:
                data = json.loads(SETTINGS.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data.setdefault("automation", {})["mql5ControlFilePath"] = str(files_dir)
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        temporary = SETTINGS.with_name(f".{SETTINGS.name}.ea-installer.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, SETTINGS)
        _p(f"   - control-file path set in settings: {files_dir}")
    except Exception as exc:
        _p(f"   - (could not auto-set control path: {exc})")


def main() -> int:
    _p("GodMode tick-EA installer")
    _p("=" * 50)
    if not EA_SRC.exists():
        _p(f"ERROR: EA source not found at {EA_SRC}")
        return 1
    terminals = find_terminals()
    active_terminal = active_terminal_data_path()
    if active_terminal is not None:
        terminals = [active_terminal] + [p for p in terminals if p.resolve() != active_terminal.resolve()]
    if not terminals:
        _p("No MetaTrader 5 data folder found under %APPDATA%\\MetaQuotes\\Terminal.")
        _p("Open MT5 at least once (and log in), then run this installer again.")
        _p("Or copy mt5_ea\\GodModeTickGuard.mq5 manually into MT5: File > Open Data")
        _p("Folder > MQL5 > Experts, then compile with F7 in MetaEditor.")
        return 0  # not fatal — the bot still starts

    _p(f"Found {len(terminals)} MetaTrader 5 terminal(s).")
    chosen_files: Path | None = None
    any_compiled = False
    for term in terminals:
        experts = term / "MQL5" / "Experts"
        files = term / "MQL5" / "Files"
        experts.mkdir(parents=True, exist_ok=True)
        files.mkdir(parents=True, exist_ok=True)
        dst = experts / EA_SRC.name
        try:
            shutil.copy2(EA_SRC, dst)
            _p(f" * {term.name}: EA copied to MQL5\\Experts")
        except Exception as exc:
            _p(f" * {term.name}: copy failed ({exc})")
            continue
        compiled = compile_ea(term, dst)
        any_compiled = any_compiled or compiled
        _p(f"   - compile: {'OK (.ex5 ready)' if compiled else 'skipped — press F7 in MetaEditor to compile'}")
        if chosen_files is None or (active_terminal is not None and term.resolve() == active_terminal.resolve()):
            chosen_files = files

    if chosen_files is not None:
        set_control_path(chosen_files)

    _p("=" * 50)
    _p("ALMOST DONE — one manual step MT5 requires:")
    _p("  1. Open MetaTrader 5.")
    if not any_compiled:
        _p("  2. Press F4 (MetaEditor), open GodModeTickGuard, press F7 to compile.")
        _p("  3. In MT5, drag 'GodModeTickGuard' from Navigator onto an XAUUSD chart.")
    else:
        _p("  2. In MT5, open the Navigator (Ctrl+N), find 'GodModeTickGuard' under")
        _p("     Expert Advisors, and drag it onto an XAUUSD chart.")
    _p("  -> On the dialog tick 'Allow Algo Trading', and make sure the toolbar")
    _p("     'Algo Trading' button is green. Match MagicNumber/CommentPrefix to the bot.")
    _p("  -> IMPORTANT: remove any older GodModeTickGuard from the chart, then attach")
    _p("     the newly compiled build. Its heartbeat uses UTC and must show V15.0.7.")
    _p("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
