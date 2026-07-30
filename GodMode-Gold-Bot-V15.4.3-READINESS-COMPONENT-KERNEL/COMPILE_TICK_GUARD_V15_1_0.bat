@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title GodMode V15.1.2 - Install and Compile Tick Guard

echo ==============================================================
echo   GODMODE V15.1.2 - INSTALL / COMPILE ACTIVE MT5 TICK GUARD
echo ==============================================================
echo.
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] The bot Python environment is missing.
  echo Run START_GODMODE.bat once, then run this file again.
  pause
  exit /b 1
)

echo Installing the exact-build EA into the MT5 terminal currently used by the bot...
"%~dp0.venv\Scripts\python.exe" "%~dp0install_ea.py"
if errorlevel 1 (
  echo.
  echo [ERROR] EA installation or compilation failed.
  echo Review the messages above and mt5_ea\README_EA_INSTALL.md.
  pause
  exit /b 1
)

echo.
echo NEXT REQUIRED MT5 STEP:
echo   1. Remove any older GodModeTickGuard from all charts.
echo   2. In MT5 Navigator, refresh Expert Advisors.
echo   3. Attach GodModeTickGuard to the active XAUUSD chart.
echo   4. Tick Allow Algo Trading and keep the toolbar Algo Trading button green.
echo   5. Keep the EA inputs MagicNumber and CommentPrefix matched to Settings.
echo.
echo After attaching the EA, run CHECK_TICK_GUARD.bat.
pause
exit /b 0
