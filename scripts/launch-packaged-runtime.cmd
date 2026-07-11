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
echo Waiting for the local runtime readiness check...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$deadline = (Get-Date).AddSeconds(30); do { try { $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/api/readiness' -TimeoutSec 2; if ($response.StatusCode -eq 200 -and $response.Content -match '\"status\"') { exit 0 } } catch { } Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 (
    echo [fail] Readiness check failed. The app did not become available within 30 seconds.
    echo Review the startup log under %LOCALAPPDATA%\IZ Clinical Notes Analyzer\logs.
    exit /b 1
)
echo IZ Clinical Notes Analyzer is starting in the background.
echo Readiness: http://127.0.0.1:8000/api/readiness
echo Version: http://127.0.0.1:8000/api/version
exit /b 0
