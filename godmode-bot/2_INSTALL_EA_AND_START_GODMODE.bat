@echo off
title GodMode - Install Tick EA + Start Bot
cd /d "%~dp0"
echo ============================================================
echo   GODMODE - INSTALL TICK EA + START BOT (one click)
echo ------------------------------------------------------------
echo   This will:
echo     1) set up Python + backend requirements
echo     2) copy + compile the GodModeTickGuard EA into MetaTrader 5
echo     3) auto-fill the AI control-file path in your settings
echo     4) start the bot and open http://127.0.0.1:8000
echo   (MT5 should be installed and opened at least once first.)
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Creating Python virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo Failed to create the virtual environment. Install Python 3.11+ and add it to PATH.
    pause
    exit /b 1
  )
)
call .venv\Scripts\activate.bat

echo [2/4] Installing backend requirements...
python -m pip install --upgrade pip >nul
python -m pip install -r backend\requirements.txt
if errorlevel 1 (
  echo Backend requirements failed to install.
  pause
  exit /b 1
)

echo.
echo [3/4] Installing the GodMode tick EA into MetaTrader 5...
python install_ea.py
echo.
echo Press any key once you have read the EA steps above to start the bot...
pause >nul

echo [4/4] Opening dashboard and starting the GodMode API...
start "" "http://127.0.0.1:8000"
cd /d "%~dp0backend"
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
pause
