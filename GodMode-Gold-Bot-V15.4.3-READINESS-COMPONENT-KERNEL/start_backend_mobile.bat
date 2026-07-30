@echo off
setlocal EnableExtensions
title GodMode Gold Bot V15.4.3 - MOBILE / LAN ACCESS
cd /d "%~dp0"
set GODMODE_KEEP_HISTORY_ON_UPGRADE=1

echo ===================================================
echo GODMODE GOLD BOT - MOBILE / LAN ACCESS
echo ===================================================
ipconfig | findstr /C:"IPv4"
echo.
echo On your phone open: http://YOUR-PC-IP:8000

echo.
where py >nul 2>nul
if not errorlevel 1 (set "SYSTEM_PY=py -3") else (set "SYSTEM_PY=python")
if not exist ".venv\Scripts\python.exe" %SYSTEM_PY% -m venv .venv
if errorlevel 1 (echo [ERROR] Could not create .venv. & pause & exit /b 1)
set "BOT_PY=%~dp0.venv\Scripts\python.exe"

"%BOT_PY%" -m pip install --disable-pip-version-check --no-warn-script-location -r "backend\requirements.txt"
if errorlevel 1 (echo [ERROR] Requirements installation failed. & pause & exit /b 1)
"%BOT_PY%" VERIFY_MT5_RUNTIME.py
if errorlevel 1 (echo [ERROR] Run FIX_MT5_RUNTIME.bat first. & pause & exit /b 1)

set GODMODE_API_HOST=0.0.0.0
set GODMODE_ALLOWED_HOSTS=*
set GODMODE_ALLOWED_ORIGINS=*
set /p GODMODE_API_KEY=Required access key (minimum 16 characters):
if not defined GODMODE_API_KEY (echo ERROR: Mobile/LAN mode requires an API key. & pause & exit /b 1)
for /f %%L in ('powershell -NoProfile -Command "$env:GODMODE_API_KEY.Length"') do set KEYLEN=%%L
if %KEYLEN% LSS 16 (echo ERROR: API key must be at least 16 characters. & pause & exit /b 1)

cd /d "%~dp0backend"
"%BOT_PY%" -m uvicorn app:app --host 0.0.0.0 --port 8000
pause
