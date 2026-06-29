@echo off
title GodMode Gold Trading Bot - No NPM Required
cd /d "%~dp0"
echo ===================================================
echo GODMODE GOLD TRADING BOT
echo This launcher does NOT require npm install.
echo It serves the already-built dashboard from the backend.
echo Dashboard: http://127.0.0.1:8000
echo ===================================================

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Creating Python virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo Failed to create virtual environment. Make sure Python is installed and added to PATH.
    pause
    exit /b 1
  )
)

call .venv\Scripts\activate.bat

echo [2/4] Installing backend requirements...
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
if errorlevel 1 (
  echo Backend requirements failed to install.
  pause
  exit /b 1
)

echo [3/4] Opening dashboard...
start "" "http://127.0.0.1:8000"

echo [4/4] Starting API + built dashboard server...
cd /d "%~dp0backend"
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
pause
