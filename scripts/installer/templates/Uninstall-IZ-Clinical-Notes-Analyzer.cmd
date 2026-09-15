@echo off
setlocal DisableDelayedExpansion
title Uninstall IZ Clinical Notes Analyzer
echo Removing IZ Clinical Notes Analyzer app files for this Windows user.
echo Local data and recovery backups will be preserved.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\Remove-IZ-Clinical-Notes-Analyzer.bootstrap.ps1" -Action Uninstall -SourceRoot "%~dp0installer" -SourceKind Package %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%EXIT_CODE%"=="0" echo [ok] App removal finished. Local data was preserved.
if "%EXIT_CODE%"=="10" echo [cancelled] App removal was cancelled before deletion.
if "%EXIT_CODE%"=="40" echo [partial] Some app-owned items could not be removed. Local data was preserved.
if "%EXIT_CODE%"=="41" echo [partial] The app was removed, but temporary cleanup remains.
if not "%EXIT_CODE%"=="0" if not "%EXIT_CODE%"=="10" if not "%EXIT_CODE%"=="40" if not "%EXIT_CODE%"=="41" echo [fail] App removal did not complete.
exit /b %EXIT_CODE%
