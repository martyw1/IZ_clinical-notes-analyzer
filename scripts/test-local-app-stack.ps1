[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = 'Stop'
$RootDir = Resolve-Path (Join-Path $PSScriptRoot '..')
$AppDataRoot = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer Test'
$EnvFile = Join-Path $AppDataRoot '.env'
$LogDir = Join-Path $AppDataRoot 'logs'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

function Write-Step($Message) { Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message" }
function New-Secret([int]$Length) {
    $alphabet = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_!@#$%^+=' 
    $bytes = New-Object byte[] $Length
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    $chars = for ($i = 0; $i -lt $Length; $i++) { $alphabet[$bytes[$i] % $alphabet.Length] }
    return -join $chars
}

try {
    Set-Location $RootDir
    $python = Join-Path $RootDir 'backend\.venv\Scripts\python.exe'
    if (!(Test-Path $python)) {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (!$pythonCommand) { throw 'Python 3.11+ is required for source checkout tests.' }
        Write-Step 'Creating backend virtual environment.'
        & $pythonCommand.Source -m venv (Join-Path $RootDir 'backend\.venv')
    }

    if (-not $SkipDependencyInstall) {
        Write-Step 'Installing backend dependencies.'
        & $python -m pip install --upgrade pip
        & $python -m pip install -r (Join-Path $RootDir 'backend\requirements.txt')
    }

    $secretKey = New-Secret 64
    $encryptionKey = New-Secret 64
    $adminPassword = New-Secret 24
    @"
APP_NAME=IZ Clinical Notes Analyzer
ENVIRONMENT=development
BACKEND_PORT=$Port
DATABASE_BACKEND=sqlite
LOCAL_SQLITE_DB_PATH=$AppDataRoot\test-clinical-notes-analyzer.sqlite3
DATABASE_URL=
SECRET_KEY=$secretKey
DATA_ENCRYPTION_KEY=$encryptionKey
FRONTEND_ORIGIN=http://localhost:$Port
FRONTEND_ORIGINS=http://localhost:$Port,http://localhost:5173
ALLOWED_HOSTS=localhost,127.0.0.1,::1,testserver
UPLOAD_DIR=$AppDataRoot\uploads
LOG_DIR=$LogDir
RULES_CONFIG_PATH=$RootDir\config\rules\alleva_treatment_plan_completeness_rules.yaml
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=$adminPassword
RESET_BOOTSTRAP_ADMIN_ON_STARTUP=true
LLM_ENABLED=false
EMR_API_ENABLED=false
"@ | Set-Content -Path $EnvFile -Encoding UTF8

    $env:IZ_CNA_ENV_FILE = $EnvFile
    $env:PYTHONPATH = Join-Path $RootDir 'backend'

    Write-Step 'Running backend unit tests.'
    & $python -m pytest (Join-Path $RootDir 'backend\tests') -q

    $uvicornArgs = @('-m', 'uvicorn', 'app.main:app', '--app-dir', (Join-Path $RootDir 'backend'), '--host', '127.0.0.1', '--port', "$Port")
    Write-Step "Starting test server on http://localhost:$Port ."
    $server = Start-Process -FilePath $python -ArgumentList $uvicornArgs -PassThru -WindowStyle Hidden
    try {
        $ready = $false
        for ($i = 0; $i -lt 40; $i++) {
            try {
                $health = Invoke-RestMethod -Uri "http://localhost:$Port/api/health" -TimeoutSec 2
                if ($health.status -eq 'ok') { $ready = $true; break }
            } catch { Start-Sleep -Seconds 1 }
        }
        if (!$ready) { throw 'API health endpoint did not become ready.' }

        Write-Step 'Checking runtime readiness endpoint.'
        $readiness = Invoke-RestMethod -Uri "http://localhost:$Port/api/readiness" -TimeoutSec 10
        if ($readiness.status -eq 'fail') { throw "Readiness failed: $($readiness | ConvertTo-Json -Depth 6)" }

        Write-Step 'Checking login and authenticated profile call.'
        $login = Invoke-RestMethod -Method Post -Uri "http://localhost:$Port/api/auth/login" -ContentType 'application/json' -Body (@{ username='admin'; password=$adminPassword } | ConvertTo-Json)
        $headers = @{ Authorization = "Bearer $($login.access_token)" }
        Invoke-RestMethod -Uri "http://localhost:$Port/api/users/me" -Headers $headers -TimeoutSec 10 | Out-Null

        Write-Step 'Local stack smoke test passed.'
    }
    finally {
        if ($server -and !$server.HasExited) { Stop-Process -Id $server.Id -Force }
    }
}
catch {
    Write-Error "Local stack smoke test failed: $($_.Exception.Message)"
    throw
}
