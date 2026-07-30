@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "EXPECTED=V15.3.2-NONBLOCKING-RUNTIME-RECOVERY"
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
  where py >nul 2>nul && set "PY=py -3"
)
if "%PY%"==".venv\Scripts\python.exe" if not exist "%PY%" (
  where python >nul 2>nul && set "PY=python"
)

echo Checking active GodMode runtime...
%PY% -c "import json,urllib.request,sys; b='http://127.0.0.1:8000'; h=json.load(urllib.request.urlopen(b+'/api/health',timeout=4)); s=json.load(urllib.request.urlopen(b+'/api/fast-sniper/status',timeout=6)); p=s.get('priorityIntent') or {}; print('Health build :',h.get('buildId')); print('Priority build:',p.get('buildId')); print('Priority state:',p.get('runtimeStatus')); print('Last blocker  :',p.get('lastBlocker') or 'none'); print('MT5 connected :',bool((s.get('mt5') or {}).get('connected'))); ok=h.get('service')=='godmode-backend' and h.get('buildId')=='%EXPECTED%' and s.get('buildId')=='%EXPECTED%' and p.get('buildId')=='%EXPECTED%'; print('RESULT        :','PASS' if ok else 'FAIL - stale or wrong backend'); sys.exit(0 if ok else 1)"
if errorlevel 1 (
  echo.
  echo Close every old GodMode Backend window, then start this version only with START_GODMODE.bat.
  pause
  exit /b 1
)
echo.
echo Exact build verified. Telegram alerts from this build include the build ID at the bottom.
pause
