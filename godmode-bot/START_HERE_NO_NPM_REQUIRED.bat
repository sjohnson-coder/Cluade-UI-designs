@echo off
title GodMode Gold Bot - No NPM Preview
cd /d "%~dp0backend"
echo ===================================================
echo GodMode Gold Bot - No NPM Required
echo The dashboard is already built in frontend/dist.
echo Open: http://127.0.0.1:8000
echo ===================================================
start "" "http://127.0.0.1:8000"
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
pause
