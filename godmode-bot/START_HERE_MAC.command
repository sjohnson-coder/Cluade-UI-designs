#!/bin/bash
# =====================================================================
# GodMode Gold Bot - ONE-CLICK START for macOS (iMac / MacBook)
# Double-click this file in Finder. The dashboard opens in your browser.
# (First run only: it sets up Python and installs the backend - 1-2 min.)
# =====================================================================
cd "$(dirname "$0")"
echo "==================================================="
echo "  GodMode Gold Bot - macOS launcher"
echo "  Dashboard: http://127.0.0.1:8000"
echo "==================================================="

# 1) Require Python 3
if ! command -v python3 >/dev/null 2>&1; then
  echo ""
  echo "Python 3 is not installed on this Mac."
  echo "Install it the easy way:"
  echo "   1) Open the App Store or https://www.python.org/downloads/macos/"
  echo "   2) Install Python 3, then double-click this file again."
  echo "(Or, if you use Homebrew:  brew install python )"
  echo ""
  read -r -p "Press Return to close..."
  exit 1
fi

# 2) First-run setup: virtual environment + backend dependencies
if [ ! -d ".venv" ]; then
  echo "First-time setup: creating a Python environment (1-2 minutes)..."
  python3 -m venv .venv || { echo "Could not create the environment."; read -r -p "Press Return..."; exit 1; }
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "Checking backend requirements (this is quick after the first run)..."
python -m pip install --upgrade pip >/dev/null 2>&1
python -m pip install -r backend/requirements.txt || { echo "Dependency install failed."; read -r -p "Press Return..."; exit 1; }

# 3) Open the dashboard in the default browser, then start the server
echo ""
echo "Starting GodMode... the dashboard will open automatically."
echo "Leave this Terminal window OPEN while you use the bot. Close it to stop."
( sleep 3; open "http://127.0.0.1:8000" >/dev/null 2>&1 ) &
cd backend
exec python -m uvicorn app:app --host 127.0.0.1 --port 8000
