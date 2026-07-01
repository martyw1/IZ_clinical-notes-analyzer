@echo off
setlocal

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

title Build IZ Clinical Notes Analyzer Windows Installer
echo ============================================================
echo IZ Clinical Notes Analyzer - Windows Installer Build
echo ============================================================
echo.
echo This build runs from the repository folder:
echo %ROOT_DIR%
echo.
echo Administrator access is not required.
echo The release will include current treatment-plan handling docs and will scan out local data, logs, and secrets.
echo.

if not exist "%ROOT_DIR%scripts\build-windows-installer.ps1" (
    echo [fail] Could not find scripts\build-windows-installer.ps1.
    echo Make sure this command is still in the repository root folder.
    echo.
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%scripts\build-windows-installer.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo [ok] Windows installer build completed.
    if exist "%ROOT_DIR%dist\windows-release\latest-release-paths.txt" (
        echo.
        type "%ROOT_DIR%dist\windows-release\latest-release-paths.txt"
    )
) else (
    echo [fail] Windows installer build did not complete.
    echo Read the message above. It names the missing dependency, failed test, or unsafe file.
    echo After fixing it, double-click Build-IZ-Windows-Installer.cmd again.
)

echo.
pause
exit /b %EXIT_CODE%
