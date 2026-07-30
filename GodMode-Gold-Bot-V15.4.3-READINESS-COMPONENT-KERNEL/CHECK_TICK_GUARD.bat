@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title GodMode V15.4.3 - Tick Guard Check
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] The bot Python environment is missing.
  echo Run START_GODMODE.bat first.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0VERIFY_TICK_GUARD.py" --wait 20
echo.
if errorlevel 1 (
  echo Tick Guard verification failed. Follow the exact message above.
) else (
  echo Tick Guard verification passed.
)
pause
exit /b %ERRORLEVEL%
