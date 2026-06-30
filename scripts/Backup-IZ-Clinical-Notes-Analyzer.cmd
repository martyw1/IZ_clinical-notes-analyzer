@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0backup-local-data.ps1"
if not "%ERRORLEVEL%"=="0" pause
exit /b %ERRORLEVEL%
