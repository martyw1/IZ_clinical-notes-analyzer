@echo off
setlocal DisableDelayedExpansion
set "SCRIPT_DIR=%~dp0"
set "LAUNCHER=%SCRIPT_DIR%launch-packaged-runtime.ps1"

if not exist "%LAUNCHER%" (
    echo [fail] The packaged runtime launcher is missing.
    endlocal
    exit /b 20
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%LAUNCHER%" %*
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
