@echo off
setlocal DisableDelayedExpansion
set "PACKAGE_DIR=%~dp0"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PACKAGE_DIR%app\scripts\collect-diagnostics.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
exit /b %EXIT_CODE%
