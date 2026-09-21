@echo off
setlocal DisableDelayedExpansion
if not defined LOCALAPPDATA (
    echo [fail] The current Windows user profile could not be located.
    echo Run Install-IZ-Clinical-Notes-Analyzer.cmd first.
    exit /b 20
)
set "INSTALLED_LAUNCHER=%LOCALAPPDATA%\Programs\IZ Clinical Notes Analyzer\scripts\Backup-IZ-Clinical-Notes-Analyzer.cmd"
if not exist "%INSTALLED_LAUNCHER%" (
    echo [fail] IZ Clinical Notes Analyzer is not installed for this Windows user.
    echo Run Install-IZ-Clinical-Notes-Analyzer.cmd first.
    exit /b 20
)
call "%INSTALLED_LAUNCHER%" %*
set "EXIT_CODE=%ERRORLEVEL%"
exit /b %EXIT_CODE%
