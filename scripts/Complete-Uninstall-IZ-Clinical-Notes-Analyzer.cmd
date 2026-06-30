@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0complete-uninstall-local-data.ps1"
if not "%ERRORLEVEL%"=="0" pause
exit /b %ERRORLEVEL%
