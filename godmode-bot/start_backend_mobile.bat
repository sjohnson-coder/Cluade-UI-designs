@echo off
title GodMode Gold Bot - MOBILE / LAN ACCESS
cd /d "%~dp0"
echo ===================================================
echo GODMODE GOLD BOT - MOBILE / LAN ACCESS
echo Binds to 0.0.0.0 so a phone on the SAME Wi-Fi can connect.
echo ===================================================
echo Your PC IPv4 address(es) - use one of these on your phone:
ipconfig | findstr /C:"IPv4"
echo.
echo Then on your phone's browser open:  http://YOUR-PC-IP:8000
echo (Example: http://192.168.1.20:8000)
echo MT5 must stay running on this PC.
echo ===================================================

if not exist ".venv\Scripts\python.exe" (
  echo Creating Python virtual environment...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
echo Installing backend requirements...
python -m pip install --upgrade pip >nul
python -m pip install -r backend\requirements.txt

REM Relax host/origin checks so the phone (a different host/IP) is allowed.
set GODMODE_API_HOST=0.0.0.0
set GODMODE_ALLOWED_HOSTS=*
set GODMODE_ALLOWED_ORIGINS=*

echo ===================================================
echo SECURITY: set an access key so ONLY you can control the bot remotely.
echo Enter the SAME key in the app: Settings -^> 13. Mobile ^& Remote Access.
echo (Leave blank for no key - fine on trusted home Wi-Fi, NOT for internet/Tailscale.)
echo ===================================================
set /p GODMODE_API_KEY=Access key (blank = none):
if defined GODMODE_API_KEY (echo Access key SET - remember to enter it in the app Settings.) else (echo No access key - write actions are open on this network.)
echo.

cd /d "%~dp0backend"
python -m uvicorn app:app --host 0.0.0.0 --port 8000
pause
