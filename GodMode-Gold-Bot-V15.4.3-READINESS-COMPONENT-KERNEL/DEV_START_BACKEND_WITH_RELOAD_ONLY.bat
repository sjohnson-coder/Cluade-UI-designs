@echo off
REM Keep trade history across engine upgrades so the validation base keeps accumulating.
set GODMODE_KEEP_HISTORY_ON_UPGRADE=1

title GodMode DEV Backend with Reload
cd /d "%~dp0backend"
echo ===================================================
echo DEV ONLY: starts backend with --reload.
echo Do NOT use this for live trading, because saving settings under backend\data can restart the server/UI.
echo Use start_backend.bat or 1_START_GODMODE_BOT_NO_NPM_REQUIRED.bat for live use.
echo ===================================================
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
pause
