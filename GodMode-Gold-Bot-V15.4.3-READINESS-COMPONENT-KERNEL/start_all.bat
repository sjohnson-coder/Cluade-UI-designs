@echo off
setlocal
cd /d "%~dp0"
echo Starting GodMode through the verified V15.4.3 launcher...
call "%~dp0START_GODMODE.bat"
exit /b %ERRORLEVEL%
