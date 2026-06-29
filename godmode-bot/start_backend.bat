@echo off
title GodMode Gold Bot Backend + Built UI
cd /d "%~dp0backend"
echo ===================================================
echo Starting GodMode API and built dashboard on port 8000
echo Open: http://127.0.0.1:8000
echo ===================================================
echo Ensuring requirements (incl. matplotlib for Telegram charts)...
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
pause
