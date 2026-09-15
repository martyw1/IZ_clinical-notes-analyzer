@echo off
setlocal DisableDelayedExpansion
set "PACKAGE_DIR=%~dp0"
call "%PACKAGE_DIR%app\scripts\Restore-IZ-Clinical-Notes-Analyzer.cmd" %*
set "EXIT_CODE=%ERRORLEVEL%"
exit /b %EXIT_CODE%
