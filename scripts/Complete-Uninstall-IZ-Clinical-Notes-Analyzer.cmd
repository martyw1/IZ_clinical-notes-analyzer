@echo off
setlocal
set NO_PAUSE=
for %%A in (%*) do (
    if /I "%%~A"=="-NoPause" set NO_PAUSE=1
    if /I "%%~A"=="/NoPause" set NO_PAUSE=1
)
title Complete Uninstall IZ Clinical Notes Analyzer
echo Complete uninstall removes app files AND local IZ Clinical Notes Analyzer data.
echo Use this only when R3 intentionally wants this Windows user account cleaned.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0complete-uninstall-local-data.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%EXIT_CODE%"=="0" (
    echo [ok] Complete uninstall finished.
) else (
    echo [fail] Complete uninstall did not complete.
)
echo.
if not "%NO_PAUSE%"=="1" pause
exit /b %EXIT_CODE%
