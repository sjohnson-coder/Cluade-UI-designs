@echo off
REM GodMode Gold Bot — one-tap dashboard rebuild (only needed if auto-build didn't run)
echo Rebuilding the GodMode dashboard bundle...
cd /d "%~dp0frontend"
if not exist node_modules (
  echo First run: installing packages (needs internet, ~1-2 min)...
  call npm install --no-audit --no-fund
)
call npm run build
echo.
echo Done. Refresh your browser (Ctrl+F5) to load the latest dashboard.
pause
