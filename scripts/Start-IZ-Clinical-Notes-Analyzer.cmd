@echo off
setlocal

REM Double-click launcher for non-technical Windows 10/11 users.
REM It starts the local app and keeps this window open if startup fails.

set SCRIPT_DIR=%~dp0
set ROOT_DIR=%SCRIPT_DIR%..
set NO_PAUSE=
for %%A in (%*) do (
    if /I "%%~A"=="-NoPause" set NO_PAUSE=1
    if /I "%%~A"=="/NoPause" set NO_PAUSE=1
)
cd /d "%ROOT_DIR%"

title IZ Clinical Notes Analyzer
echo ============================================================
echo Starting IZ Clinical Notes Analyzer...
echo ============================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%\scripts\start-windows-local.ps1" -AssumeYes %*
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [fail] The app did not start.
    echo Review the startup log under:
    echo %%LOCALAPPDATA%%\IZ Clinical Notes Analyzer\logs
    echo.
    echo Common fixes:
    echo   - Close any other app using http://localhost:8000.
    echo   - Reconnect to the internet if dependency installation was interrupted.
    echo   - Run Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd if support asks.
    echo.
    if not "%NO_PAUSE%"=="1" pause
    endlocal
    exit /b %EXIT_CODE%
)

endlocal
exit /b 0
