@echo off
setlocal

REM Double-click launcher for non-technical Windows 10/11 users.
REM It starts the local app and keeps this window open if startup fails.
REM If the richer PowerShell startup wrapper reports a false dependency-check
REM failure, this launcher falls back to the already-created local Python venv.

set SCRIPT_DIR=%~dp0
set ROOT_DIR=%SCRIPT_DIR%..
cd /d "%ROOT_DIR%"

title IZ Clinical Notes Analyzer
echo Starting IZ Clinical Notes Analyzer...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%\scripts\start-windows-local.ps1" -AssumeYes
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Primary startup returned exit code %EXIT_CODE%.
    echo Trying direct local server fallback using backend\.venv...
    echo.

    if not exist "%ROOT_DIR%\backend\.venv\Scripts\python.exe" (
        echo backend\.venv\Scripts\python.exe was not found.
        echo Review the startup log under:
        echo %%LOCALAPPDATA%%\IZ Clinical Notes Analyzer\logs
        echo.
        pause
        endlocal
        exit /b %EXIT_CODE%
    )

    set IZ_CNA_ENV_FILE=%LOCALAPPDATA%\IZ Clinical Notes Analyzer\.env
    set PYTHONPATH=%ROOT_DIR%\backend
    start "" "http://localhost:8000"
    "%ROOT_DIR%\backend\.venv\Scripts\python.exe" -m uvicorn app.desktop_main:app --app-dir "%ROOT_DIR%\backend" --host 127.0.0.1 --port 8000
    set FALLBACK_EXIT_CODE=%ERRORLEVEL%

    if not "%FALLBACK_EXIT_CODE%"=="0" (
        echo.
        echo Direct fallback also failed with exit code %FALLBACK_EXIT_CODE%.
        echo Review the startup log under:
        echo %%LOCALAPPDATA%%\IZ Clinical Notes Analyzer\logs
        echo.
        pause
        endlocal
        exit /b %FALLBACK_EXIT_CODE%
    )
)

endlocal
exit /b 0
