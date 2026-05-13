[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$SkipFrontendBuild
)

$ErrorActionPreference = 'Stop'
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$AppDataRoot = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer'
$LogDir = Join-Path $AppDataRoot 'logs'
$EnvFile = Join-Path $AppDataRoot '.env'
$Timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogFile = Join-Path $LogDir "startup-windows-local-$Timestamp.log"
$TranscriptStarted = $false

function Write-Info($Message) { Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [INFO] $Message" }
function Write-Pass($Message) { Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [PASS] $Message" -ForegroundColor Green }
function Write-Warn($Message) { Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [WARN] $Message" -ForegroundColor Yellow }

function New-RandomBytes {
    param([int]$Length)
    $bytes = New-Object byte[] $Length

    # Windows PowerShell 5.1 runs on .NET Framework, where the static
    # RandomNumberGenerator::Fill(byte[]) helper is not available. Use the
    # older Create()/GetBytes() pattern so startup works on plain Windows 10/11.
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

function New-LocalSecret {
    param([int]$Length)
    $alphabet = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_!@#$%^+=' 
    $bytes = New-RandomBytes -Length $Length
    $chars = for ($i = 0; $i -lt $Length; $i++) { $alphabet[$bytes[$i] % $alphabet.Length] }
    return -join $chars
}

function Assert-PythonVersion {
    param([string]$PythonExe)

    $versionText = & $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not run Python at $PythonExe."
    }

    $version = [version]$versionText.Trim()
    if ($version -lt [version]'3.11.0') {
        throw "Python 3.11+ is required. Found Python $version at $PythonExe."
    }

    return $version
}

function New-BackendVirtualEnvironment {
    $venvDir = Join-Path $RootDir 'backend\.venv'
    New-Item -ItemType Directory -Path (Split-Path $venvDir -Parent) -Force | Out-Null

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        Write-Info "Creating backend virtual environment with $($pythonCommand.Source)."
        & $pythonCommand.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
        if ($LASTEXITCODE -eq 0) {
            & $pythonCommand.Source -m venv $venvDir
            if ($LASTEXITCODE -eq 0) { return }
        }
        Write-Warn 'The python command was found, but it is not Python 3.11+ or could not create the virtual environment.'
    }

    $pyCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCommand) {
        Write-Info "Creating backend virtual environment with Python Launcher at $($pyCommand.Source)."
        & $pyCommand.Source -3.11 -m venv $venvDir
        if ($LASTEXITCODE -eq 0) { return }

        & $pyCommand.Source -3 -m venv $venvDir
        if ($LASTEXITCODE -eq 0) { return }
    }

    throw 'Python 3.11+ was not found or could not create backend\.venv. Install Python 3.11+ and reopen PowerShell.'
}

function Get-PythonRuntime {
    $embedded = Join-Path $RootDir 'runtime\python\python.exe'
    if (Test-Path $embedded) {
        $version = Assert-PythonVersion -PythonExe $embedded
        return @{ Path = $embedded; InstallDependencies = $false; Version = $version }
    }

    $venv = Join-Path $RootDir 'backend\.venv\Scripts\python.exe'
    if (!(Test-Path $venv)) {
        New-BackendVirtualEnvironment
    }

    if (Test-Path $venv) {
        $version = Assert-PythonVersion -PythonExe $venv
        return @{ Path = $venv; InstallDependencies = $true; Version = $version }
    }

    throw 'Python runtime setup failed. backend\.venv\Scripts\python.exe was not created.'
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
        Write-Warn 'Save this password in a secure place. It is stored in the local app settings file.'
    } else {
        Write-Pass "Using existing local app settings at $EnvFile"
    }
}

function Ensure-FrontendBuild {
    if ($SkipFrontendBuild) {
        Write-Warn 'Skipping frontend build because -SkipFrontendBuild was supplied.'
        return
    }

    $frontendDir = Join-Path $RootDir 'frontend'
    $packageJson = Join-Path $frontendDir 'package.json'
    $indexFile = Join-Path $frontendDir 'dist\index.html'

    if (!(Test-Path $packageJson)) {
        Write-Warn 'No frontend\package.json found. The backend will start, but no React UI can be built.'
        return
    }

    if (Test-Path $indexFile) {
        Write-Pass 'Frontend build already exists at frontend\dist.'
        return
    }

    $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (!$npmCommand) {
        $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
    }

    if (!$npmCommand) {
        Write-Warn 'Node.js/npm was not found. The backend will start, but the browser UI cannot be built from source.'
        Write-Warn 'Install Node.js LTS, then rerun this startup script, or use a packaged release with frontend\dist included.'
        return
    }

    Write-Info "Building frontend UI with $($npmCommand.Source)."
    Push-Location $frontendDir
    try {
        if (Test-Path (Join-Path $frontendDir 'package-lock.json')) {
            & $npmCommand.Source ci
        } else {
            & $npmCommand.Source install
        }
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }

        & $npmCommand.Source run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }

        if (Test-Path $indexFile) {
            Write-Pass 'Frontend build completed at frontend\dist.'
        } else {
            Write-Warn 'Frontend build command finished, but frontend\dist\index.html was not found.'
        }
    }
    catch {
        Write-Warn "Frontend build did not complete: $($_.Exception.Message)"
        Write-Warn 'The backend will still start and / will show a local status page with build instructions.'
    }
    finally {
        Pop-Location
    }
}

try {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    Start-Transcript -Path $LogFile -Append | Out-Null
    $TranscriptStarted = $true

    Set-Location $RootDir

    if (!(Test-Path (Join-Path $RootDir 'backend\requirements.txt'))) {
        throw "Could not find backend\requirements.txt under $RootDir. Keep this script in the repo scripts folder."
    }

    Ensure-EnvFile
    $env:IZ_CNA_ENV_FILE = $EnvFile
    $env:PYTHONPATH = Join-Path $RootDir 'backend'

    $pythonRuntime = Get-PythonRuntime
    $pythonExe = $pythonRuntime.Path
    Write-Info "Using Python runtime: $pythonExe"
    Write-Info "Python version: $($pythonRuntime.Version)"

    if ($pythonRuntime.InstallDependencies) {
        Write-Info 'Installing or refreshing backend dependencies in backend\.venv.'
        & $pythonExe -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }

        & $pythonExe -m pip install -r (Join-Path $RootDir 'backend\requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
    }

    Write-Info 'Running backend readiness checks before launch.'
    & $pythonExe -m pytest (Join-Path $RootDir 'backend\tests\test_rules_engine.py') -q
    if ($LASTEXITCODE -ne 0) { throw 'Rules-engine test failed.' }

    Ensure-FrontendBuild

    $port = 8000
    Write-Info "Starting local app on http://localhost:$port"
    if (-not $NoBrowser) {
        Start-Process "http://localhost:$port"
    }
    & $pythonExe -m uvicorn app.desktop_main:app --app-dir (Join-Path $RootDir 'backend') --host 127.0.0.1 --port $port
    if ($LASTEXITCODE -ne 0) { throw 'Local FastAPI server exited with an error.' }
}
catch {
    Write-Error "Startup failed: $($_.Exception.Message)"
    Write-Host "Log file: $LogFile"
    throw
}
finally {
    if ($TranscriptStarted) {
        Stop-Transcript | Out-Null
    }
}
