@echo off
setlocal DisableDelayedExpansion
title Complete Uninstall IZ Clinical Notes Analyzer
echo Complete uninstall removes app files AND app-owned local data for this Windows user.
echo External backups, downloaded packages, and other Windows profiles are outside its scope.
echo The PowerShell prompt requires the exact phrase REMOVE IZ DATA.
echo.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\start-package.ps1" -Action RemoveData -SourceRoot "%~dp0\" %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%EXIT_CODE%"=="0" echo [ok] Complete uninstall finished.
if "%EXIT_CODE%"=="10" echo [cancelled] No app files or local data were deleted.
if "%EXIT_CODE%"=="40" echo [partial] Some app-owned items remain; review the result before retrying.
if "%EXIT_CODE%"=="41" echo [partial] The app and local data were removed, but temporary cleanup remains.
if not "%EXIT_CODE%"=="0" if not "%EXIT_CODE%"=="10" if not "%EXIT_CODE%"=="40" if not "%EXIT_CODE%"=="41" echo [fail] Complete uninstall did not complete.
exit /b %EXIT_CODE%
