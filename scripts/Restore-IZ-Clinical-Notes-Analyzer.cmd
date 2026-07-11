@echo off
setlocal
set "ROOT_DIR=%~dp0.."
set "NO_PAUSE="
for %%A in (%*) do (
    if /I "%%~A"=="-NoPause" set "NO_PAUSE=1"
    if /I "%%~A"=="/NoPause" set "NO_PAUSE=1"
)
title Restore IZ Clinical Notes Analyzer
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%\scripts\restore-local-data.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" if not "%NO_PAUSE%"=="1" pause
exit /b %EXIT_CODE%
