@echo off
setlocal EnableExtensions
title R3 Alleva End-User Data Pull Tool

rem -----------------------------------------------------------------------------
rem R3 / Alleva End-User Data Pull Tool launcher
rem
rem Double-click this .cmd file or run it from Command Prompt.
rem It starts the PowerShell menu script from this same folder and uses a
rem process-only execution-policy bypass. That does not permanently change the
rem computer's PowerShell policy.
rem -----------------------------------------------------------------------------

set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%Invoke-AllevaEndUserTools.ps1"
set "POWERSHELL_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

echo.
echo ================================================================
echo  R3 / Alleva End-User Data Pull Tool
echo ================================================================
echo.
echo This tool calls Alleva directly. Logs and exports may contain PHI.
echo Keep generated files local, access-controlled, and out of Git/email/chat.
echo.

if not exist "%PS_SCRIPT%" (
    echo ERROR: Could not find the PowerShell script:
    echo   "%PS_SCRIPT%"
    echo.
    echo Make sure this launcher is in the same folder as Invoke-AllevaEndUserTools.ps1.
    echo.
    pause
    exit /b 1
)

if not exist "%POWERSHELL_EXE%" (
    echo ERROR: Windows PowerShell was not found at:
    echo   "%POWERSHELL_EXE%"
    echo.
    echo Try opening PowerShell manually and run:
    echo   powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
    echo.
    pause
    exit /b 1
)

cd /d "%SCRIPT_DIR%"

echo Starting PowerShell menu...
echo.
"%POWERSHELL_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo Tool closed normally.
) else (
    echo Tool exited with error code %EXIT_CODE%.
)
echo.
echo Logs are normally written under:
echo   "%SCRIPT_DIR%logs"
echo Exports are normally written under:
echo   "%SCRIPT_DIR%exports"
echo.
pause
exit /b %EXIT_CODE%
