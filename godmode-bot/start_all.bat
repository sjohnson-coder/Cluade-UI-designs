@echo off
title GodMode Gold Trading Bot - One Click Start
cd /d "%~dp0"
echo ===================================================
echo Starting GodMode Bot
 echo Backend will also serve the built UI.
echo Open: http://127.0.0.1:8000
echo ===================================================
start "GodMode Backend + UI" cmd /k "%~dp0start_backend.bat"
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:8000"
