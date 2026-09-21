@echo off
setlocal DisableDelayedExpansion
set "PACKAGE_DIR=%~dp0"
cd /d "%PACKAGE_DIR%"
if errorlevel 1 (
    echo [fail] Could not open the IZ Clinical Notes Analyzer package folder.
    exit /b 20
)

title Install IZ Clinical Notes Analyzer
echo IZ Clinical Notes Analyzer installer
echo.
echo This installs or repairs the app for the current Windows user.
echo Administrator access is not required. Existing local data is protected.
echo.

"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PACKAGE_DIR%installer\start-package.ps1" -Action AutoInstall -SourceRoot "%PACKAGE_DIR%\" %*
set "EXIT_CODE=%ERRORLEVEL%"
exit /b %EXIT_CODE%
