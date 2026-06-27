#!/bin/bash
# =====================================================================
# GodMode Gold Bot - MOBILE / LAN ACCESS for macOS
# Binds to 0.0.0.0 so a phone on the SAME Wi-Fi can connect.
# For access from anywhere, use Tailscale (see MOBILE_REMOTE_ACCESS.md).
# =====================================================================
cd "$(dirname "$0")"
echo "==================================================="
echo "  GodMode Gold Bot - MOBILE / LAN ACCESS (macOS)"
echo "==================================================="
echo "Your Mac's IP address(es) - use one on your phone:"
ipconfig getifaddr en0 2>/dev/null
ipconfig getifaddr en1 2>/dev/null
echo "Then on your phone's browser open:  http://YOUR-MAC-IP:8000"
echo "==================================================="

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. Install from https://www.python.org/downloads/macos/ and retry."
  read -r -p "Press Return to close..."; exit 1
fi
if [ ! -d ".venv" ]; then python3 -m venv .venv; fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null 2>&1
python -m pip install -r backend/requirements.txt

echo ""
echo "SECURITY: set an access key so ONLY you can control the bot remotely."
echo "Enter the SAME key in the app: Settings -> 13. Mobile & Remote Access."
echo "(Leave blank for no key - OK on trusted home Wi-Fi, NOT for internet/Tailscale.)"
read -r -p "Access key (blank = none): " GODMODE_API_KEY
export GODMODE_API_KEY
export GODMODE_API_HOST=0.0.0.0
export GODMODE_ALLOWED_HOSTS="*"
export GODMODE_ALLOWED_ORIGINS="*"
if [ -n "$GODMODE_API_KEY" ]; then echo "Access key SET - enter it in the app Settings."; else echo "No access key - write actions are open on this network."; fi
echo ""

cd backend
exec python -m uvicorn app:app --host 0.0.0.0 --port 8000
