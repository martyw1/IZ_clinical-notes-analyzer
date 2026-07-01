@echo off
setlocal
set NO_PAUSE=
for %%A in (%*) do (
    if /I "%%~A"=="-NoPause" set NO_PAUSE=1
    if /I "%%~A"=="/NoPause" set NO_PAUSE=1
)
title IZ Clinical Notes Analyzer Diagnostics
echo Collecting IZ Clinical Notes Analyzer diagnostics...
echo This excludes uploaded clinical documents, raw .env secrets, and SQLite databases.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0collect-diagnostics.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%EXIT_CODE%"=="0" (
    echo [ok] Diagnostics collection finished.
) else (
    echo [fail] Diagnostics collection did not complete.
)
echo.
if not "%NO_PAUSE%"=="1" pause
exit /b %EXIT_CODE%
