@echo off
setlocal
set "APP_ROOT=%~dp0.."
set "RUNTIME_EXE=%APP_ROOT%\runtime\IZClinicalNotesAnalyzer.exe"
set "IZ_CNA_ENV_FILE=%LOCALAPPDATA%\IZ Clinical Notes Analyzer\.env"
set "IZ_CNA_PORT=8000"
if not exist "%RUNTIME_EXE%" (
    echo [fail] The bundled IZ Clinical Notes Analyzer runtime is missing.
    exit /b 1
)
start "" /b "%RUNTIME_EXE%"
echo IZ Clinical Notes Analyzer is starting in the background.
echo Readiness: http://127.0.0.1:8000/api/readiness
echo Version: http://127.0.0.1:8000/api/version
exit /b 0
