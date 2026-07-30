@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title GodMode V14.1.23 - Repair MT5 Runtime

echo ==============================================================
echo   GODMODE V14.1.23 - REPAIR PYTHON / NUMPY / METATRADER 5
echo ==============================================================
echo.

echo Close the GodMode backend window before continuing.
where py >nul 2>nul
if not errorlevel 1 (
  set "SYSTEM_PY=py -3"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Python 3 was not found.
    pause
    exit /b 1
  )
  set "SYSTEM_PY=python"
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/5] Creating a clean virtual environment...
  %SYSTEM_PY% -m venv .venv
  if errorlevel 1 (echo [ERROR] Could not create .venv. & pause & exit /b 1)
)
set "BOT_PY=%~dp0.venv\Scripts\python.exe"

echo [2/5] Removing the incompatible NumPy / MetaTrader5 binaries...
"%BOT_PY%" -m pip uninstall -y numpy MetaTrader5 >nul 2>nul

echo [3/5] Installing the compatible MT5 runtime...
"%BOT_PY%" -m pip install --disable-pip-version-check --no-cache-dir --force-reinstall "numpy==1.26.4" "MetaTrader5==5.0.45"
if errorlevel 1 (echo [ERROR] MT5 runtime installation failed. Check internet access. & pause & exit /b 1)

echo [4/5] Installing the remaining GodMode requirements...
"%BOT_PY%" -m pip install --disable-pip-version-check --no-warn-script-location -r "backend\requirements.txt"
if errorlevel 1 (echo [ERROR] GodMode requirements installation failed. & pause & exit /b 1)

echo [5/5] Verifying binary compatibility...
"%BOT_PY%" VERIFY_MT5_RUNTIME.py
if errorlevel 1 (
  echo [ERROR] MetaTrader5 still cannot import. Delete the .venv folder and run this repair again.
  pause
  exit /b 1
)

echo.
echo [OK] NumPy and MetaTrader5 are compatible.
echo Open and log in to MetaTrader 5, then run START_GODMODE.bat.
pause
endlocal
