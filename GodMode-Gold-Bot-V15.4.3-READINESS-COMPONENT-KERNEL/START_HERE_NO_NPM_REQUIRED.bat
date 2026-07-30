@echo off
setlocal
cd /d "%~dp0"
echo Starting the packaged dashboard. npm is not required.
call "%~dp0START_GODMODE.bat"
exit /b %ERRORLEVEL%
