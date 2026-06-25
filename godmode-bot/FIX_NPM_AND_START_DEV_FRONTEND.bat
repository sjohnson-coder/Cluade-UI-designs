@echo off
title GodMode Frontend - NPM Repair + Dev Start
cd /d "%~dp0frontend"
echo ===================================================
echo Repairing npm install for frontend dev mode
 echo Normal preview does not need this. Use 1_START_GODMODE_BOT_NO_NPM_REQUIRED.bat instead.
echo ===================================================

taskkill /F /IM node.exe >nul 2>nul
npm cache clean --force
if exist node_modules rmdir /s /q node_modules
if exist package-lock.json (
  npm ci --no-audit --no-fund
) else (
  npm install --no-audit --no-fund
)
if errorlevel 1 (
  echo npm install still failed. This is a local npm/node issue. Please install Node.js 20 LTS or use the no-npm launcher.
  pause
  exit /b 1
)

npm run dev
pause
