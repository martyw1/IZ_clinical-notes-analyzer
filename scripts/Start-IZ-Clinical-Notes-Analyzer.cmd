@echo off
setlocal

REM Double-click launcher for non-technical Windows 10/11 users.
REM It starts the local FastAPI app using the bundled/local Python environment.

set SCRIPT_DIR=%~dp0
set ROOT_DIR=%SCRIPT_DIR%..
cd /d "%ROOT_DIR%"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%\scripts\startup-windows-local.ps1"

endlocal
