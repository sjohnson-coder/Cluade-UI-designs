@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Install GodMode V14.1.23

echo Installing the isolated Python runtime and backend requirements...
where py >nul 2>nul
if not errorlevel 1 (set "SYSTEM_PY=py -3") else (set "SYSTEM_PY=python")
if not exist ".venv\Scripts\python.exe" %SYSTEM_PY% -m venv .venv
if errorlevel 1 (echo [ERROR] Python environment creation failed. & pause & exit /b 1)
set "BOT_PY=%~dp0.venv\Scripts\python.exe"
"%BOT_PY%" -m pip install --disable-pip-version-check --no-warn-script-location -r "backend\requirements.txt"
if errorlevel 1 (echo [ERROR] Backend installation failed. & pause & exit /b 1)
"%BOT_PY%" VERIFY_MT5_RUNTIME.py
if errorlevel 1 (
  echo [ERROR] MetaTrader5 runtime verification failed.
  echo Run FIX_MT5_RUNTIME.bat.
  pause
  exit /b 1
)

echo.
echo The production dashboard is already included. Node.js is optional.
echo Use REBUILD_DASHBOARD.bat only when editing frontend source.
echo Installation complete. Run START_GODMODE.bat or start_all.bat.
pause
