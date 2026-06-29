@echo off
title GodMode Gold Bot Frontend Dev Server
cd /d "%~dp0frontend"
echo ===================================================
echo Starting Vite frontend dev server on port 5173
echo This is optional. For normal preview, use start_backend.bat and open http://127.0.0.1:8000
echo ===================================================
if exist node_modules (
  npm run dev
) else (
  npm ci --no-audit --no-fund
  if errorlevel 1 (
    echo npm ci failed. Trying npm install fallback...
    npm install --no-audit --no-fund
  )
  npm run dev
)
pause
