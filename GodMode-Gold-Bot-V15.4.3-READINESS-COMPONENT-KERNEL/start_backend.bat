@echo off
setlocal
cd /d "%~dp0"
echo Starting the verified V15.4.3 backend and packaged dashboard...
call "%~dp0START_GODMODE.bat"
exit /b %ERRORLEVEL%
