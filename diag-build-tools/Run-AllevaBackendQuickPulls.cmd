@echo off
setlocal
set SCRIPT_DIR=%~dp0
REM Compatibility wrapper: the actual tool is standalone and calls Alleva directly, not the local app backend.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%Invoke-AllevaRemoteDiagnostics.ps1"
endlocal
