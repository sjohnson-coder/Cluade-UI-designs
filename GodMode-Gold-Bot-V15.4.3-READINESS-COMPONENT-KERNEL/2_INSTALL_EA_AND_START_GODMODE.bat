@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title GodMode V15.4.3 - Install Tick Guard and Start

echo ==============================================================
echo   GODMODE V15.4.3 - INSTALL TICK GUARD + START BOT
echo ==============================================================
echo.
where py >nul 2>nul
if not errorlevel 1 (
  set "SYSTEM_PY=py -3"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Python 3 was not found.
    echo Install Python 3.11 or newer and add it to PATH.
    pause
    exit /b 1
  )
  set "SYSTEM_PY=python"
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Creating Python virtual environment...
  %SYSTEM_PY% -m venv .venv || (echo [ERROR] Could not create .venv. & pause & exit /b 1)
)
set "BOT_PY=%~dp0.venv\Scripts\python.exe"

echo [2/4] Installing backend requirements and the compatible MT5 runtime...
"%BOT_PY%" -m pip install --disable-pip-version-check --no-warn-script-location -r "backend\requirements.txt"
if errorlevel 1 (echo [ERROR] Backend requirements failed. & pause & exit /b 1)
"%BOT_PY%" VERIFY_MT5_RUNTIME.py
if errorlevel 1 (
  echo [INFO] Repairing NumPy and MetaTrader5...
  "%BOT_PY%" -m pip uninstall -y numpy MetaTrader5 >nul 2>nul
  "%BOT_PY%" -m pip install --disable-pip-version-check --no-cache-dir --force-reinstall "numpy==1.26.4" "MetaTrader5==5.0.45"
  "%BOT_PY%" VERIFY_MT5_RUNTIME.py || (echo [ERROR] MT5 runtime repair failed. & pause & exit /b 1)
)

echo [3/4] Installing and compiling GodModeTickGuard in MetaTrader 5...
"%BOT_PY%" install_ea.py
if errorlevel 1 (
  echo.
  echo [WARNING] Automatic EA installation did not complete.
  echo Run COMPILE_TICK_GUARD_V15_1_0.bat or follow mt5_ea\README_EA_INSTALL.md.
  pause
)

echo [4/4] Starting the verified dashboard and backend...
call "%~dp0START_GODMODE.bat"
exit /b %ERRORLEVEL%
