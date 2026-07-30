#!/bin/bash
# =====================================================================
# GodMode Gold Bot - ONE-CLICK START for macOS (iMac / MacBook)
#
# Double-click this file in Finder. It installs everything the bot needs
# (first run only, 1-2 min) and opens the dashboard in your browser -
# exactly like start_all.bat does on Windows.
#
# FIRST RUN ONLY: if macOS says "unidentified developer", right-click this
# file -> Open -> Open. You only do that once.
# =====================================================================
cd "$(dirname "$0")" || exit 1

# Self-heal: a downloaded/unzipped folder can lose the executable bit and carry a
# Gatekeeper "quarantine" flag that blocks double-click. Fix both, best-effort.
chmod +x "$0" ./*.command 2>/dev/null
xattr -dr com.apple.quarantine . 2>/dev/null

echo "==================================================="
echo "  GodMode Gold Bot - macOS launcher"
echo "  Dashboard will open at: http://127.0.0.1:8000"
echo "==================================================="

# ---------------------------------------------------------------------
# 1) Find a usable Python 3 (>=3.9). Check the common Homebrew/python.org spots.
# ---------------------------------------------------------------------
PY=""
for c in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,9) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo ""
  echo "  Python 3.9+ was not found on this Mac."
  echo "  Install it (2 minutes), then double-click this file again:"
  echo "     - Easiest: https://www.python.org/downloads/macos/  (run the installer)"
  echo "     - Or with Homebrew:  brew install python"
  echo ""
  read -r -p "Press Return to close..."
  exit 1
fi
echo "Using Python: $("$PY" --version 2>&1)  ($PY)"

# ---------------------------------------------------------------------
# 2) First-run setup: an isolated virtual environment in .venv
# ---------------------------------------------------------------------
if [ ! -d ".venv" ]; then
  echo "First-time setup: creating an isolated Python environment..."
  "$PY" -m venv .venv || {
    echo "Could not create the environment with 'venv'."
    echo "Try:  $PY -m pip install --user virtualenv  &&  $PY -m virtualenv .venv"
    read -r -p "Press Return to close..."; exit 1
  }
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip wheel setuptools >/dev/null 2>&1

# ---------------------------------------------------------------------
# 3) Install the backend requirements (first run: 1-2 min; quick after).
#    We try the full requirements first (identical to Windows). If that hits
#    a snag - almost always the OPTIONAL 'matplotlib' on the very newest
#    Python - we fall back to the core packages so the bot still starts.
# ---------------------------------------------------------------------
echo "Installing backend requirements (first run takes 1-2 minutes)..."
if python -m pip install -r backend/requirements.txt; then
  echo "All requirements installed."
else
  echo ""
  echo "  Full install hit a snag (usually the optional 'matplotlib' on the newest Python)."
  echo "  Installing the CORE packages the bot needs to run..."
  if ! python -m pip install "fastapi==0.111.0" "uvicorn[standard]==0.30.1" "pydantic==2.7.4" "python-dotenv==1.0.1"; then
    echo "  Retrying core packages without version pins..."
    python -m pip install fastapi "uvicorn[standard]" pydantic python-dotenv || {
      echo "  Could not install the core packages. Check your internet connection and retry."
      read -r -p "Press Return to close..."; exit 1
    }
  fi
  # matplotlib is OPTIONAL (Telegram chart images). Best-effort; never blocks startup.
  python -m pip install matplotlib >/dev/null 2>&1 \
    && echo "  (matplotlib installed - Telegram charts ON)" \
    || echo "  (matplotlib not installed - Telegram charts OFF, everything else works)"
fi

# ---------------------------------------------------------------------
# 4) Sanity check: the app must import before we launch.
# ---------------------------------------------------------------------
if ! ( cd backend && python -c "import app" >/dev/null 2>&1 ); then
  echo ""
  echo "  The backend failed to import. Showing the error:"
  ( cd backend && python -c "import app" )
  read -r -p "Press Return to close..."; exit 1
fi

# ---------------------------------------------------------------------
# 5) Open the dashboard, then start the server (leave this window OPEN).
# ---------------------------------------------------------------------
echo ""
echo "Starting GodMode... the dashboard will open in your browser."
echo "Leave this Terminal window OPEN while you use the bot. Close it to stop."
( sleep 3; open "http://127.0.0.1:8000" >/dev/null 2>&1 ) &
cd backend
exec python -m uvicorn app:app --host 127.0.0.1 --port 8000
