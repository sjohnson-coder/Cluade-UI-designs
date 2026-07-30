@echo off
REM Compatibility launcher for older shortcuts. Forwards to the current V15.1.2 helper.
call "%~dp0COMPILE_TICK_GUARD_V15_1_0.bat"
exit /b %ERRORLEVEL%
