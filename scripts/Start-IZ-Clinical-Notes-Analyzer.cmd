@echo off
setlocal

REM Double-click launcher for non-technical Windows 10/11 users.
REM It starts the local app and keeps this window open if startup fails.

set SCRIPT_DIR=%~dp0
set ROOT_DIR=%SCRIPT_DIR%..
cd /d "%ROOT_DIR%"

title IZ Clinical Notes Analyzer
echo Starting IZ Clinical Notes Analyzer...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%\scripts\startup-windows-local.ps1"
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Startup failed with exit code %EXIT_CODE%.
    echo Review the messages above and the startup log under:
    echo %%LOCALAPPDATA%%\IZ Clinical Notes Analyzer\logs
    echo.
    pause
)

endlocal
exit /b %EXIT_CODE%
