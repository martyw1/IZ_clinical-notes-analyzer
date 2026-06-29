@echo off
setlocal

REM Double-click cleanup launcher for Windows users.
REM It stops app-specific local processes that can block a clean restart,
REM then asks whether to start the normal app launcher again.

set "SCRIPT_DIR=%~dp0"
set "ROOT_DIR=%SCRIPT_DIR%.."
cd /d "%ROOT_DIR%"

title IZ Clinical Notes Analyzer Cleanup
echo IZ Clinical Notes Analyzer cleanup
echo.

if not exist "%ROOT_DIR%\scripts\stop-windows-local.ps1" (
    echo Cleanup script was not found:
    echo %ROOT_DIR%\scripts\stop-windows-local.ps1
    echo.
    pause
    endlocal
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%\scripts\stop-windows-local.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

endlocal
exit /b %EXIT_CODE%
