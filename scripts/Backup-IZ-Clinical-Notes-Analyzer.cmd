@echo off
setlocal
set NO_PAUSE=
for %%A in (%*) do (
    if /I "%%~A"=="-NoPause" set NO_PAUSE=1
    if /I "%%~A"=="/NoPause" set NO_PAUSE=1
)
title Backup IZ Clinical Notes Analyzer
echo Backup IZ Clinical Notes Analyzer local data
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0backup-local-data.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%EXIT_CODE%"=="0" (
    echo [ok] Backup command finished.
) else (
    echo [fail] Backup did not complete.
)
echo.
if not "%NO_PAUSE%"=="1" pause
exit /b %EXIT_CODE%
