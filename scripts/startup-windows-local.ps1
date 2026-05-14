[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$SkipFrontendBuild,
    [switch]$AssumeYes
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

function Confirm-Install {
    param([string]$Message)
    if ($AssumeYes) { return $true }
    Write-Host ""
    Write-Warn $Message
    $answer = Read-Host 'Do you want to install these now? Type Y for yes or N for no'
    return $answer -match '^(y|yes)$'
}

function New-RandomBytes {
    param([int]$Length)
    $bytes = New-Object byte[] $Length
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) }
    finally {
        if ($rng -and ($rng -is [System.IDisposable])) { $rng.Dispose() }
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
    if ($LASTEXITCODE -ne 0) { throw "Could not run Python at $PythonExe." }
    $version = [version]$versionText.Trim()
    if ($version -lt [version]'3.11.0') { throw "Python 3.11+ is required. Found Python $version at $PythonExe." }
    return $version
}

function Find-SystemPython {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        & $pythonCommand.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { return $pythonCommand.Source }
        Write-Warn "The python command was found at $($pythonCommand.Source), but it is not a working Python 3.11+ runtime."
    }

    $pyCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCommand) {
        & $pyCommand.Source -3.13 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { return "$($pyCommand.Source) -3.13" }
        & $pyCommand.Source -3.12 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { return "$($pyCommand.Source) -3.12" }
        & $pyCommand.Source -3.11 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { return "$($pyCommand.Source) -3.11" }
        & $pyCommand.Source -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { return "$($pyCommand.Source) -3" }
    }

    return $null
}

function Invoke-PythonCommand {
    param(
        [string]$PythonCommand,
        [string[]]$Arguments
    )
    if ($PythonCommand -like '* -3*') {
        $parts = $PythonCommand.Split(' ', 2)
        & $parts[0] $parts[1] @Arguments
    } else {
        & $PythonCommand @Arguments
    }
}

function Invoke-PythonSnippet {
    param(
        [string]$PythonExe,
        [string]$Code
    )

    # Windows PowerShell 5.1 can strip quotes from complex multi-line arguments
    # passed to native commands through `python -c`. Write the check to a
    # temporary .py file instead so the Python code runs exactly as authored.
    $scriptName = "iz-cna-python-check-$([guid]::NewGuid().ToString('N')).py"
    $scriptPath = Join-Path $env:TEMP $scriptName
    try {
        Set-Content -Path $scriptPath -Value $Code -Encoding UTF8
        & $PythonExe $scriptPath
        return $LASTEXITCODE
    }
    finally {
        Remove-Item -Path $scriptPath -Force -ErrorAction SilentlyContinue
    }
}

function New-BackendVirtualEnvironment {
    $venvDir = Join-Path $RootDir 'backend\.venv'
    New-Item -ItemType Directory -Path (Split-Path $venvDir -Parent) -Force | Out-Null

    $systemPython = Find-SystemPython
    if (!$systemPython) {
        throw 'Python 3.11+ was not found. Install Python 3.11+ from python.org or the Microsoft Store, reopen PowerShell, and run this launcher again.'
    }

    Write-Info "Creating backend virtual environment with $systemPython."
    Invoke-PythonCommand -PythonCommand $systemPython -Arguments @('-m', 'venv', $venvDir)
    if ($LASTEXITCODE -ne 0) { throw 'Could not create backend\.venv.' }
}

function Reset-BackendVirtualEnvironment {
    $venvDir = Join-Path $RootDir 'backend\.venv'
    if (Test-Path $venvDir) {
        Write-Warn "Existing backend virtual environment is broken or stale. Recreating $venvDir."
        Remove-Item -Path $venvDir -Recurse -Force
    }
    New-BackendVirtualEnvironment
}

function Get-PythonRuntime {
    $embedded = Join-Path $RootDir 'runtime\python\python.exe'
    if (Test-Path $embedded) {
        $version = Assert-PythonVersion -PythonExe $embedded
        return @{ Path = $embedded; InstallDependencies = $false; Version = $version; Bundled = $true }
    }

    $venvDir = Join-Path $RootDir 'backend\.venv'
    $venv = Join-Path $venvDir 'Scripts\python.exe'
    if (!(Test-Path $venv)) { New-BackendVirtualEnvironment }

    if (Test-Path $venv) {
        try {
            $version = Assert-PythonVersion -PythonExe $venv
            return @{ Path = $venv; InstallDependencies = $true; Version = $version; Bundled = $false }
        }
        catch {
            Write-Warn "The existing backend virtual environment could not run: $($_.Exception.Message)"
            Reset-BackendVirtualEnvironment
            if (Test-Path $venv) {
                $version = Assert-PythonVersion -PythonExe $venv
                return @{ Path = $venv; InstallDependencies = $true; Version = $version; Bundled = $false }
            }
        }
    }

    throw 'Python runtime setup failed. backend\.venv\Scripts\python.exe was not created.'
}

function Test-BackendRuntimeDependencies {
    param([string]$PythonExe)
    $checkCode = @'
import importlib.util
import sys
required = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "sqlalchemy": "sqlalchemy",
    "jose": "python-jose",
    "passlib": "passlib",
    "bcrypt": "bcrypt",
    "multipart": "python-multipart",
    "pydantic_settings": "pydantic-settings",
    "email_validator": "email-validator",
    "pypdf": "pypdf",
    "cryptography": "cryptography",
    "yaml": "PyYAML",
}
missing = [package for module, package in required.items() if importlib.util.find_spec(module) is None]
if missing:
    print("Missing Python packages: " + ", ".join(missing))
    sys.exit(1)
print("Python runtime packages are present.")
'@
    $exitCode = Invoke-PythonSnippet -PythonExe $PythonExe -Code $checkCode
    return $exitCode -eq 0
}

function Ensure-BackendRuntimeDependencies {
    param([string]$PythonExe)
    $runtimeRequirements = Join-Path $RootDir 'backend\requirements-windows-local.txt'
    if (!(Test-Path $runtimeRequirements)) {
        $runtimeRequirements = Join-Path $RootDir 'backend\requirements.txt'
        Write-Warn 'Lean Windows runtime requirements file was not found; falling back to backend\requirements.txt.'
    }

    if (Test-BackendRuntimeDependencies -PythonExe $PythonExe) {
        Write-Pass 'Required local Python packages are already installed.'
        return
    }

    $message = "The app needs local Python packages listed in $runtimeRequirements."
    if (!(Confirm-Install -Message $message)) {
        throw 'Required Python packages are missing and were not installed. Startup cannot continue.'
    }

    Write-Info 'Installing required local Python packages into backend\.venv.'
    & $PythonExe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }

    & $PythonExe -m pip install -r $runtimeRequirements
    if ($LASTEXITCODE -ne 0) { throw 'Python package installation failed.' }

    if (!(Test-BackendRuntimeDependencies -PythonExe $PythonExe)) {
        throw 'Python packages were installed, but the dependency check still failed.'
    }
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

function Test-RulesConfiguration {
    param([string]$PythonExe)
    $rulesPath = Join-Path $RootDir 'config\rules\alleva_treatment_plan_completeness_rules.yaml'
    $checkCode = @"
from app.services.rules_engine import load_rules_config, validate_rules_config
config = load_rules_config(r'$rulesPath')
errors = validate_rules_config(config)
if errors:
    raise SystemExit('; '.join(errors))
print('Rules configuration is valid.')
"@
    $exitCode = Invoke-PythonSnippet -PythonExe $PythonExe -Code $checkCode
    if ($exitCode -ne 0) { throw 'Rules configuration validation failed.' }
    Write-Pass 'Rules configuration validated without requiring pytest.'
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
    if (!$npmCommand) { $npmCommand = Get-Command npm -ErrorAction SilentlyContinue }

    if (!$npmCommand) {
        Write-Warn 'Browser UI build files are missing, and Node.js/npm was not found.'
        Write-Warn 'Install Node.js LTS, then rerun this launcher, or use a packaged release that includes frontend\dist.'
        return
    }

    $message = 'Browser UI build files are missing. The app needs Node.js/npm to install frontend packages and build frontend\dist from source.'
    if (!(Confirm-Install -Message $message)) {
        Write-Warn 'Frontend build was skipped. The backend will still start, but the full browser UI may be unavailable until frontend\dist exists.'
        return
    }

    Write-Info "Building frontend UI with $($npmCommand.Source)."
    Push-Location $frontendDir
    try {
        if (Test-Path (Join-Path $frontendDir 'package-lock.json')) { & $npmCommand.Source ci }
        else { & $npmCommand.Source install }
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }

        & $npmCommand.Source run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }

        if (Test-Path $indexFile) { Write-Pass 'Frontend build completed at frontend\dist.' }
        else { Write-Warn 'Frontend build command finished, but frontend\dist\index.html was not found.' }
    }
    catch {
        Write-Warn "Frontend build did not complete: $($_.Exception.Message)"
        Write-Warn 'The backend will still start and / will show a local status page with build instructions.'
    }
    finally { Pop-Location }
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
        Ensure-BackendRuntimeDependencies -PythonExe $pythonExe
    }

    Write-Info 'Running lightweight readiness checks before launch.'
    Test-RulesConfiguration -PythonExe $pythonExe

    Ensure-FrontendBuild

    $port = 8000
    Write-Info "Starting local app on http://localhost:$port"
    if (-not $NoBrowser) { Start-Process "http://localhost:$port" }
    & $pythonExe -m uvicorn app.desktop_main:app --app-dir (Join-Path $RootDir 'backend') --host 127.0.0.1 --port $port
    if ($LASTEXITCODE -ne 0) { throw 'Local FastAPI server exited with an error.' }
}
catch {
    Write-Error "Startup failed: $($_.Exception.Message)"
    Write-Host "Log file: $LogFile"
    throw
}
finally {
    if ($TranscriptStarted) { Stop-Transcript | Out-Null }
}
