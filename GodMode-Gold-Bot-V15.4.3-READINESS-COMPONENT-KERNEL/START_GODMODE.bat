@echo off
setlocal EnableExtensions EnableDelayedExpansion
title GodMode Gold Bot V15.4.3
cd /d "%~dp0"

set "GODMODE_BUILD=V15.4.3-READINESS-COMPONENT-KERNEL"
set "GODMODE_KEEP_HISTORY_ON_UPGRADE=1"
set "GODMODE_SKIP_AUTO_FRONTEND_BUILD=1"
set "DASHBOARD_URL=http://127.0.0.1:8000/?build=V1543-READINESS-COMPONENT-KERNEL"

echo ==============================================================
echo   GODMODE GOLD BOT V15.4.3 - VERIFIED ONE-CLICK START
echo ==============================================================
echo.

where py >nul 2>nul
if not errorlevel 1 (
  set "SYSTEM_PY=py -3"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Python 3 was not found.
    echo Install Python 3.11 or newer and tick "Add Python to PATH".
    pause
    exit /b 1
  )
  set "SYSTEM_PY=python"
)

REM Reuse only the exact build. A stale GodMode backend is identified by its own
REM /api/health service marker, not by a fragile command-line guess. This closes old
REM python app.py and uvicorn launch styles while refusing to kill unrelated software.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$build='%GODMODE_BUILD%'; $isGodMode=$false; $runningBuild='';" ^
  "try {$r=Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 2; $isGodMode=($r.service -eq 'godmode-backend'); $runningBuild=[string]$r.buildId; if($isGodMode -and $runningBuild -eq $build){exit 10}} catch {}" ^
  "$listener=Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1;" ^
  "if($listener){$proc=Get-CimInstance Win32_Process -Filter ('ProcessId='+$listener.OwningProcess) -ErrorAction SilentlyContinue; $cmd=[string]$proc.CommandLine; if($isGodMode){Write-Host ('[INFO] Closing stale GodMode backend '+$runningBuild+' on port 8000...'); Stop-Process -Id $listener.OwningProcess -Force; Start-Sleep -Seconds 2; exit 0}; $expected=[IO.Path]::GetFullPath('%~dp0.venv\Scripts\python.exe').ToLowerInvariant(); $sameRuntime=($cmd.ToLowerInvariant().Contains($expected) -and $cmd -match 'uvicorn' -and $cmd -match 'app:app'); if($sameRuntime){Write-Host '[INFO] Closing an incomplete stale GodMode startup on port 8000...'; Stop-Process -Id $listener.OwningProcess -Force; Start-Sleep -Seconds 2; exit 0}; Write-Host '[ERROR] Port 8000 is used by another application:' $cmd; exit 20}; exit 0"
set "PORT_RESULT=%ERRORLEVEL%"
if "%PORT_RESULT%"=="10" (
  echo [OK] Exact V15.4.3 backend is already running.
  start "" "%DASHBOARD_URL%"
  exit /b 0
)
if "%PORT_RESULT%"=="20" (
  echo.
  echo Close the application shown above or free port 8000, then run START_GODMODE.bat again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/6] Creating the isolated Python environment...
  %SYSTEM_PY% -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Could not create .venv.
    pause
    exit /b 1
  )
) else (
  echo [1/6] Python environment found.
)

set "BOT_PY=%~dp0.venv\Scripts\python.exe"
"%BOT_PY%" -c "import fastapi,uvicorn,pydantic,dotenv" >nul 2>nul
if errorlevel 1 (
  echo [2/6] Installing required packages. This happens only on first start...
  "%BOT_PY%" -m pip install --disable-pip-version-check --no-warn-script-location -r "backend\requirements.txt"
  if errorlevel 1 (
    echo [ERROR] Required packages could not be installed. Check the internet connection and run again.
    pause
    exit /b 1
  )
) else (
  echo [2/6] Core packages are ready.
)

echo [3/6] Verifying NumPy and MetaTrader5 binary compatibility...
"%BOT_PY%" VERIFY_MT5_RUNTIME.py --quiet >nul 2>nul
if errorlevel 1 (
  echo [INFO] Repairing the incompatible MetaTrader5 runtime...
  "%BOT_PY%" -m pip uninstall -y numpy MetaTrader5 >nul 2>nul
  "%BOT_PY%" -m pip install --disable-pip-version-check --no-cache-dir --force-reinstall "numpy==1.26.4" "MetaTrader5==5.0.45"
  if errorlevel 1 (
    echo [ERROR] NumPy / MetaTrader5 repair failed. Check the internet connection.
    pause
    exit /b 1
  )
  "%BOT_PY%" -m pip install --disable-pip-version-check --no-warn-script-location -r "backend\requirements.txt"
)
"%BOT_PY%" VERIFY_MT5_RUNTIME.py
if errorlevel 1 (
  echo [ERROR] MetaTrader5 cannot load in this virtual environment.
  echo Run FIX_MT5_RUNTIME.bat, then start the bot again.
  pause
  exit /b 1
)

echo [4/6] Starting backend and dashboard...
pushd "%~dp0backend"
start "GodMode Backend V15.4.3" cmd /k ""%BOT_PY%" -m uvicorn app:app --host 127.0.0.1 --port 8000"
popd

set "READY=0"
for /l %%I in (1,1,60) do (
  if "!READY!"=="0" (
    "%BOT_PY%" -c "import json,urllib.request,sys; d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=2)); sys.exit(0 if d.get('buildId')=='%GODMODE_BUILD%' else 1)" >nul 2>nul
    if not errorlevel 1 (
      set "READY=1"
    ) else (
      timeout /t 1 /nobreak >nul
    )
  )
)

if not "%READY%"=="1" (
  echo.
  echo [ERROR] V15.4.3 did not become ready. Review the GodMode Backend window.
  pause
  exit /b 1
)

REM A second independent build proof verifies the live priority-intent endpoint, not
REM only the lightweight health route. This prevents a stale backend from producing
REM old 82%% / 0.76 ATR Telegram alerts while a newer dashboard is open.
"%BOT_PY%" -c "import json,urllib.request,sys; d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/fast-sniper/status',timeout=5)); p=d.get('priorityIntent') or {}; ok=d.get('buildId')=='%GODMODE_BUILD%' and p.get('buildId')=='%GODMODE_BUILD%'; sys.exit(0 if ok else 1)" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Priority Intent endpoint is not running the exact V15.4.3 build.
  echo Close every older GodMode backend window and run START_GODMODE.bat again.
  pause
  exit /b 1
)

echo [5/6] Verifying the exact browser settings path...
"%BOT_PY%" -c "import json,os,urllib.request,sys; b='http://127.0.0.1:8000'; h={'Content-Type':'application/json','Origin':b,'Sec-Fetch-Site':'same-origin'}; k=os.getenv('GODMODE_API_KEY','').strip(); h.update({'X-GodMode-Key':k} if k else {}); rq=lambda p,m='GET',x=None: json.load(urllib.request.urlopen(urllib.request.Request(b+p,data=None if x is None else json.dumps(x).encode(),method=m,headers=h),timeout=12)); s=rq('/api/settings'); l=bool(s['execution']['liveTradingEnabled']); a=bool(s['execution']['autoTradingEnabled']); rev=int(s.get('settingsRevision') or s.get('meta',{}).get('settingsRevision') or 0); r1=rq('/api/mt5/live-mode','POST',{'enabled':l,'expectedRevision':rev}); rev1=int((r1.get('settings') or {}).get('settingsRevision') or (r1.get('settings') or {}).get('meta',{}).get('settingsRevision') or rev); r2=rq('/api/mt5/auto-trading','POST',{'enabled':a,'expectedRevision':rev1}); rev2=int((r2.get('settings') or {}).get('settingsRevision') or (r2.get('settings') or {}).get('meta',{}).get('settingsRevision') or rev1); r3=rq('/api/settings','POST',{'settings':r2.get('settings') or r1.get('settings') or s,'expectedRevision':rev2}); f=rq('/api/settings'); ok=r1.get('ok') and r2.get('ok') and r3.get('ok') and bool(f['execution']['liveTradingEnabled'])==l and bool(f['execution']['autoTradingEnabled'])==a; sys.exit(0 if ok else 1)" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Browser-origin settings write/read-back test failed.
  echo The dashboard will not open because its settings path is not verified.
  echo Review the backend window for the exact HTTP error.
  pause
  exit /b 1
)

echo [6/6] Checking the exact-build Tick Guard heartbeat...
"%BOT_PY%" VERIFY_TICK_GUARD.py --wait 3
if errorlevel 1 (
  echo [NOTICE] The dashboard will open, but live entries remain protected until the
  echo          V15.4.3 Tick Guard is compiled and attached to the active XAUUSD chart.
  echo          Run CHECK_TICK_GUARD.bat after attaching the EA.
) else (
  echo [OK] Tick Guard heartbeat and active MT5 profile verified.
)

echo Exact build, MT5 runtime and settings persistence verified.
start "" "%DASHBOARD_URL%"
echo.
echo Dashboard: %DASHBOARD_URL%
echo Use only START_GODMODE.bat to start the bot.
echo Leave the "GodMode Backend V15.4.3" window open.
timeout /t 5 /nobreak >nul
endlocal
