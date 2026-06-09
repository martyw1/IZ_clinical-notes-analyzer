[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = 'Stop'
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$AppDataRoot = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer Test'
$EnvFile = Join-Path $AppDataRoot '.env'
$LogDir = Join-Path $AppDataRoot 'logs'
$BaseUrl = "http://127.0.0.1:$Port"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

function Write-Step($Message) { Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message" }

function New-RandomBytes {
    param([int]$Length)
    $bytes = New-Object byte[] $Length
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    }
    finally {
        if ($rng -and ($rng -is [System.IDisposable])) {
            $rng.Dispose()
        }
    }
    return $bytes
}

function New-Secret([int]$Length) {
    $alphabet = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_!@#$%^+=' 
    $bytes = New-RandomBytes -Length $Length
    $chars = for ($i = 0; $i -lt $Length; $i++) { $alphabet[$bytes[$i] % $alphabet.Length] }
    return -join $chars
}

function Assert-PythonVersion {
    param([string]$PythonExe)
    $versionText = & $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
    if ($LASTEXITCODE -ne 0) { throw "Could not run Python at $PythonExe." }
    $version = [version]$versionText.Trim()
    if ($version -lt [version]'3.11.0') { throw "Python 3.11+ is required. Found Python $version at $PythonExe." }
    return $version
}

function New-BackendVirtualEnvironment {
    $venvDir = Join-Path $RootDir 'backend\.venv'
    New-Item -ItemType Directory -Path (Split-Path $venvDir -Parent) -Force | Out-Null

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        Write-Step "Creating backend virtual environment with $($pythonCommand.Source)."
        & $pythonCommand.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
        if ($LASTEXITCODE -eq 0) {
            & $pythonCommand.Source -m venv $venvDir
            if ($LASTEXITCODE -eq 0) { return }
        }
    }

    $pyCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCommand) {
        Write-Step "Creating backend virtual environment with Python Launcher at $($pyCommand.Source)."
        & $pyCommand.Source -3.11 -m venv $venvDir
        if ($LASTEXITCODE -eq 0) { return }
        & $pyCommand.Source -3 -m venv $venvDir
        if ($LASTEXITCODE -eq 0) { return }
    }

    throw 'Python 3.11+ was not found or could not create backend\.venv. Install Python 3.11+ and reopen PowerShell.'
}

try {
    Set-Location $RootDir
    $python = Join-Path $RootDir 'backend\.venv\Scripts\python.exe'
    if (!(Test-Path $python)) {
        New-BackendVirtualEnvironment
    }
    if (!(Test-Path $python)) { throw 'backend\.venv\Scripts\python.exe was not created.' }
    $pythonVersion = Assert-PythonVersion -PythonExe $python
    Write-Step "Using Python $pythonVersion at $python."

    if (-not $SkipDependencyInstall) {
        Write-Step 'Installing backend dependencies.'
        & $python -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
        & $python -m pip install -r (Join-Path $RootDir 'backend\requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
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
FRONTEND_ORIGIN=$BaseUrl
FRONTEND_ORIGINS=$BaseUrl,http://localhost:$Port,http://localhost:5173
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
    if ($LASTEXITCODE -ne 0) { throw 'Backend unit tests failed.' }

    $appDir = Join-Path $RootDir 'backend'
    $uvicornArgs = "-m uvicorn app.main:app --app-dir `"$appDir`" --host 127.0.0.1 --port $Port"
    Write-Step "Starting test server on $BaseUrl ."
    $server = Start-Process -FilePath $python -ArgumentList $uvicornArgs -WorkingDirectory $RootDir -PassThru -WindowStyle Hidden
    try {
        $ready = $false
        for ($i = 0; $i -lt 40; $i++) {
            try {
                $health = Invoke-RestMethod -Uri "$BaseUrl/api/health" -TimeoutSec 2
                if ($health.status -eq 'ok') { $ready = $true; break }
            } catch { Start-Sleep -Seconds 1 }
        }
        if (!$ready) { throw 'API health endpoint did not become ready.' }

        Write-Step 'Checking runtime readiness endpoint.'
        $readiness = Invoke-RestMethod -Uri "$BaseUrl/api/readiness" -TimeoutSec 10
        if ($readiness.status -eq 'fail') { throw "Readiness failed: $($readiness | ConvertTo-Json -Depth 6)" }

        Write-Step 'Checking version endpoint.'
        $version = Invoke-RestMethod -Uri "$BaseUrl/api/version" -TimeoutSec 10
        if (!$version.version) { throw "Version endpoint did not return version metadata: $($version | ConvertTo-Json -Depth 6)" }

        Write-Step 'Checking login and authenticated profile call.'
        $login = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/auth/login" -ContentType 'application/json' -Body (@{ username='admin'; password=$adminPassword } | ConvertTo-Json)
        $headers = @{ Authorization = "Bearer $($login.access_token)" }
        Invoke-RestMethod -Uri "$BaseUrl/api/users/me" -Headers $headers -TimeoutSec 10 | Out-Null

        Write-Step 'Checking workflow profile API.'
        Invoke-RestMethod -Uri "$BaseUrl/api/workflow-definitions?include_archived=true" -Headers $headers -TimeoutSec 10 | Out-Null

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
