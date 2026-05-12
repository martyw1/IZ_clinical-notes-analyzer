[CmdletBinding()]
param(
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$RootDir = Resolve-Path (Join-Path $PSScriptRoot '..')
$AppDataRoot = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer'
$LogDir = Join-Path $AppDataRoot 'logs'
$EnvFile = Join-Path $AppDataRoot '.env'
$Timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogFile = Join-Path $LogDir "startup-windows-local-$Timestamp.log"

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
Start-Transcript -Path $LogFile -Append | Out-Null

function Write-Info($Message) { Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [INFO] $Message" }
function Write-Pass($Message) { Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [PASS] $Message" -ForegroundColor Green }
function Write-Warn($Message) { Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [WARN] $Message" -ForegroundColor Yellow }

function New-LocalSecret {
    param([int]$Length)
    $alphabet = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_!@#$%^+=' 
    $bytes = New-Object byte[] $Length
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    $chars = for ($i = 0; $i -lt $Length; $i++) { $alphabet[$bytes[$i] % $alphabet.Length] }
    return -join $chars
}

function Ensure-EnvFile {
    if (!(Test-Path $EnvFile)) {
        New-Item -ItemType Directory -Path $AppDataRoot -Force | Out-Null
        $secretKey = New-LocalSecret -Length 64
        $encryptionKey = New-LocalSecret -Length 64
        $adminPassword = New-LocalSecret -Length 24
        @"
APP_NAME=IZ Clinical Notes Analyzer
ENVIRONMENT=local-client
BACKEND_PORT=8000
FRONTEND_PORT=5173
DATABASE_BACKEND=sqlite
LOCAL_SQLITE_DB_PATH=clinical-notes-analyzer.sqlite3
DATABASE_URL=
SECRET_KEY=$secretKey
DATA_ENCRYPTION_KEY=$encryptionKey
FRONTEND_ORIGIN=http://localhost:8000
FRONTEND_ORIGINS=http://localhost:8000,http://localhost:5173
ALLOWED_HOSTS=localhost,127.0.0.1,::1,testserver
UPLOAD_DIR=uploads
LOG_DIR=logs
RULES_CONFIG_PATH=$RootDir\config\rules\alleva_treatment_plan_completeness_rules.yaml
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=$adminPassword
RESET_BOOTSTRAP_ADMIN_ON_STARTUP=true
LLM_ENABLED=false
EMR_API_ENABLED=false
"@ | Set-Content -Path $EnvFile -Encoding UTF8
        Write-Pass "Created local app settings at $EnvFile"
        Write-Host ""
        Write-Host "First sign-in credentials:"
        Write-Host "  Username: admin"
        Write-Host "  Password: $adminPassword"
        Write-Host ""
        Write-Warn "Save this password in a secure place. It is stored in the local app settings file."
    } else {
        Write-Pass "Using existing local app settings at $EnvFile"
    }
}

function Get-PythonExe {
    $embedded = Join-Path $RootDir 'runtime\python\python.exe'
    if (Test-Path $embedded) { return $embedded }
    $venv = Join-Path $RootDir 'backend\.venv\Scripts\python.exe'
    if (Test-Path $venv) { return $venv }
    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    if ($systemPython) { return $systemPython.Source }
    throw 'Python was not found. For source checkout runs, install Python 3.11+. For end-user runs, use the packaged release build.'
}

try {
    Set-Location $RootDir
    Ensure-EnvFile
    $env:IZ_CNA_ENV_FILE = $EnvFile
    $env:PYTHONPATH = Join-Path $RootDir 'backend'
    $pythonExe = Get-PythonExe
    Write-Info "Using Python runtime: $pythonExe"

    if ($pythonExe -like '*\.venv\*' -or $pythonExe -eq (Get-Command python -ErrorAction SilentlyContinue).Source) {
        Write-Info 'Installing or refreshing backend dependencies for source checkout run.'
        & $pythonExe -m pip install --upgrade pip
        & $pythonExe -m pip install -r (Join-Path $RootDir 'backend\requirements.txt')
    }

    Write-Info 'Running backend readiness checks before launch.'
    & $pythonExe -m pytest (Join-Path $RootDir 'backend\tests\test_rules_engine.py') -q

    $port = 8000
    Write-Info "Starting local app on http://localhost:$port"
    if (-not $NoBrowser) {
        Start-Process "http://localhost:$port"
    }
    & $pythonExe -m uvicorn app.main:app --app-dir (Join-Path $RootDir 'backend') --host 127.0.0.1 --port $port
}
catch {
    Write-Error "Startup failed: $($_.Exception.Message)"
    Write-Host "Log file: $LogFile"
    throw
}
finally {
    Stop-Transcript | Out-Null
}
