@echo off
setlocal EnableDelayedExpansion
title GodMode - Upgrade Helper (validated settings migration)
echo.
echo  ============================================================
echo   GODMODE V14.1.23 VALIDATED UPGRADE HELPER
echo  ============================================================
echo.
echo   This copies your configuration and learned data from an older
echo   GodMode folder into this release. V14.1.23 validates the copied
echo   settings before use. Invalid or corrupt settings are quarantined
echo   and the bot remains fail-closed.
echo.
set /p OLDDIR="  Paste the FULL path of your OLD GodMode folder: "
if not exist "%OLDDIR%\backend\data\settings.json" (
  echo.
  echo   [!] Could not find backend\data\settings.json under:
  echo       %OLDDIR%
  echo   Check the path and run this helper again.
  pause
  exit /b 1
)
echo.
if not exist "%~dp0backend\data" mkdir "%~dp0backend\data"
copy /Y "%OLDDIR%\backend\data\settings.json" "%~dp0backend\data\settings.json" >nul && echo   [OK] settings.json
if exist "%OLDDIR%\backend\data\settings.lastgood.json" copy /Y "%OLDDIR%\backend\data\settings.lastgood.json" "%~dp0backend\data\settings.lastgood.json" >nul && echo   [OK] settings.lastgood.json
if exist "%OLDDIR%\backend\data\decision_journal.jsonl" copy /Y "%OLDDIR%\backend\data\decision_journal.jsonl" "%~dp0backend\data\decision_journal.jsonl" >nul && echo   [OK] decision_journal.jsonl
if exist "%OLDDIR%\backend\data\execution_memory.jsonl" copy /Y "%OLDDIR%\backend\data\execution_memory.jsonl" "%~dp0backend\data\execution_memory.jsonl" >nul && echo   [OK] execution_memory.jsonl
if exist "%OLDDIR%\backend\data\ai_coach_state.json" copy /Y "%OLDDIR%\backend\data\ai_coach_state.json" "%~dp0backend\data\ai_coach_state.json" >nul && echo   [OK] ai_coach_state.json
if exist "%OLDDIR%\backend\data\godmode_memory.sqlite" copy /Y "%OLDDIR%\backend\data\godmode_memory.sqlite" "%~dp0backend\data\godmode_memory.sqlite" >nul && echo   [OK] godmode_memory.sqlite
if exist "%OLDDIR%\backend\data\trade_context.json" copy /Y "%OLDDIR%\backend\data\trade_context.json" "%~dp0backend\data\trade_context.json" >nul && echo   [OK] trade_context.json
echo.
echo   engine_version.json, data_epoch.json and execution_ledger.sqlite
echo   are deliberately not copied. The new engine maintains its own
echo   build identity, execution ledger and trade attribution.
echo.
echo   Done. Start with 1_START_GODMODE_BOT_NO_NPM_REQUIRED.bat
echo   and review the Settings recovery status before enabling trading.
echo.
pause
