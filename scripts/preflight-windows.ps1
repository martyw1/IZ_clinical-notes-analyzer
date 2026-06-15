[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$AssumeYes,
    [switch]$SkipFrontendBuild,
    [string]$ReportPath = ''
)

$ErrorActionPreference = 'Stop'
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$AppDataRoot = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer'
$LogDir = Join-Path $AppDataRoot 'logs'
$UploadDir = Join-Path $AppDataRoot 'uploads'
$ExportDir = Join-Path $AppDataRoot 'exports'
$ApiReportDir = Join-Path $AppDataRoot 'api-connectivity-reports'
$EnvFile = Join-Path $AppDataRoot '.env'
$VenvDir = Join-Path $RootDir 'backend\.venv'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
$DefaultReportPath = Join-Path $LogDir 'preflight-windows-latest.json'
$ReportFile = if ($ReportPath) { $ReportPath } else { $DefaultReportPath }
$Results = New-Object System.Collections.Generic.List[object]

function Add-Check {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Message,
        [string]$Detail = ''
    )
    $Results.Add([ordered]@{
        name = $Name
        status = $Status
        message = $Message
        detail = $Detail
    }) | Out-Null
    $color = if ($Status -eq 'ok') { 'Green' } elseif ($Status -eq 'warn') { 'Yellow' } else { 'Red' }
    Write-Host "[$Status] $Name - $Message $Detail" -ForegroundColor $color
}

function Confirm-SetupAction {
    param(
        [string]$Action,
        [string]$Detail = ''
    )

    if ($AssumeYes) { return $true }
    Write-Host ''
    Write-Host $Action -ForegroundColor Yellow
    if ($Detail) { Write-Host $Detail }
    $answer = Read-Host 'Continue? Type Y to proceed'
    return ($answer.Trim().ToLowerInvariant() -match '^(y|yes)$')
}

function Invoke-PythonSnippetFile {
    param(
        [string]$PythonExe,
        [string]$Code
    )

    if (-not (Test-Path $PythonExe)) { return 9009 }
    $scriptName = "iz-cna-preflight-$([guid]::NewGuid().ToString('N')).py"
    $scriptPath = Join-Path $env:TEMP $scriptName
    try {
        Set-Content -Path $scriptPath -Value $Code -Encoding UTF8
        $output = & $PythonExe $scriptPath 2>&1
        $exitCode = [int]$LASTEXITCODE
        foreach ($line in $output) {
            if ($null -ne $line -and "$line".Length -gt 0) { Write-Host $line }
        }
        return $exitCode
    }
    finally {
        Remove-Item -Path $scriptPath -Force -ErrorAction SilentlyContinue
    }
}

function New-RandomSecret {
    param([int]$Length = 64)
    $bytes = New-Object byte[] $Length
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) }
    finally {
        if ($rng -and ($rng -is [System.IDisposable])) { $rng.Dispose() }
    }
    $alphabet = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_!@#$%^+=' 
    return -join ($bytes | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
}

function Find-Python {
    $candidates = @(
        (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe')
    ) | Where-Object { $_ -and (Test-Path $_) }

    foreach ($candidate in $candidates) {
        try {
            $versionCode = "import sys; print('{}.{}.{}'.format(sys.version_info.major, sys.version_info.minor, sys.version_info.micro))"
            $versionText = & $candidate -c $versionCode 2>$null
            if ($LASTEXITCODE -eq 0 -and [version]$versionText -ge [version]'3.11.0') { return $candidate }
        } catch { continue }
    }
    return $null
}

function Ensure-Python {
    $python = Find-Python
    if ($python) {
        Add-Check 'python' 'ok' 'Python 3.11 or newer is available.' $python
        return $python
    }

    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        Add-Check 'python' 'fail' 'Python 3.11+ is missing and winget is unavailable.' 'Install Python 3.12 from python.org, then rerun preflight.'
        return $null
    }
    if (-not (Confirm-SetupAction -Action 'Python 3.11 or newer is missing. The launcher can install Python 3.12 for this Windows user account through winget.' -Detail 'This installs the standard Python runtime required by the local app.')) {
        Add-Check 'python' 'fail' 'Python 3.11+ is missing.' 'Install Python 3.12 from python.org, or rerun with -AssumeYes to install through winget.'
        return $null
    }

    Add-Check 'python_install' 'warn' 'Installing Python 3.12 through winget.' ''
    & $winget.Source install --id Python.Python.3.12 -e --scope user --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Add-Check 'python_install' 'fail' 'Python installation failed.' "exit=$LASTEXITCODE"
        return $null
    }
    $python = Find-Python
    if ($python) {
        Add-Check 'python' 'ok' 'Python 3.12 installed successfully.' $python
        return $python
    }
    Add-Check 'python' 'fail' 'Python installation completed but python.exe was not found.' ''
    return $null
}

function Ensure-EnvFile {
    New-Item -ItemType Directory -Path $AppDataRoot, $LogDir, $UploadDir, $ExportDir, $ApiReportDir -Force | Out-Null
    if (Test-Path $EnvFile) {
        Add-Check 'local_env' 'ok' 'Using existing local configuration outside the repo.' $EnvFile
        return
    }
    $secretKey = New-RandomSecret 64
    $encryptionKey = New-RandomSecret 64
    $adminPassword = New-RandomSecret 24
    @"
APP_NAME=IZ Clinical Notes Analyzer
ENVIRONMENT=local-client
BACKEND_PORT=$Port
FRONTEND_PORT=5173
DATABASE_BACKEND=sqlite
LOCAL_SQLITE_DB_PATH=clinical-notes-analyzer.sqlite3
DATABASE_URL=
SECRET_KEY=$secretKey
DATA_ENCRYPTION_KEY=$encryptionKey
FRONTEND_ORIGIN=http://localhost:$Port
FRONTEND_ORIGINS=http://localhost:$Port,http://localhost:5173
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
    Add-Check 'local_env' 'ok' 'Created local configuration outside the repo.' $EnvFile
    Add-Check 'first_sign_in' 'warn' 'First sign-in password was generated in the local .env file.' 'Username: admin. Store the generated password securely.'
}

function Test-BackendDependencyImports {
    if (-not (Test-Path $VenvPython)) { return $false }
    $code = @'
import importlib.util
import sys
required = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "sqlalchemy": "SQLAlchemy",
    "jose": "python-jose",
    "passlib": "passlib",
    "bcrypt": "bcrypt",
    "multipart": "python-multipart",
    "pydantic_settings": "pydantic-settings",
    "email_validator": "email-validator",
    "pypdf": "pypdf",
    "cryptography": "cryptography",
    "yaml": "PyYAML",
    "httpx": "httpx",
}
missing = [package for module, package in required.items() if importlib.util.find_spec(module) is None]
if missing:
    print("Missing Python packages: " + ", ".join(missing))
    raise SystemExit(1)
print("Python dependency check passed for " + sys.executable)
'@
    $exitCode = Invoke-PythonSnippetFile -PythonExe $VenvPython -Code $code
    return ([int]$exitCode -eq 0)
}

function Ensure-Venv {
    param([string]$PythonExe)
    if (-not $PythonExe) { return }
    if (-not (Test-Path $VenvPython)) {
        Add-Check 'backend_venv' 'warn' 'Creating backend virtual environment.' $VenvDir
        & $PythonExe -m venv $VenvDir
        if ($LASTEXITCODE -ne 0) {
            Add-Check 'backend_venv' 'fail' 'Could not create backend virtual environment.' "exit=$LASTEXITCODE"
            return
        }
    }
    Add-Check 'backend_venv' 'ok' 'Backend virtual environment exists.' $VenvPython

    $requirements = Join-Path $RootDir 'backend\requirements-windows-local.txt'
    if (-not (Test-Path $requirements)) { $requirements = Join-Path $RootDir 'backend\requirements.txt' }
    if (Test-BackendDependencyImports) {
        Add-Check 'backend_dependencies' 'ok' 'Backend runtime dependencies import successfully.' ''
        return
    }
    if (-not (Confirm-SetupAction -Action 'Backend Python packages are missing. The launcher can install them into backend\.venv for this checkout.' -Detail $requirements)) {
        Add-Check 'backend_dependencies' 'fail' 'Backend runtime dependencies are missing.' 'Install them manually with backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-windows-local.txt, or rerun with -AssumeYes.'
        return
    }
    Add-Check 'backend_dependencies' 'warn' 'Installing backend runtime dependencies.' $requirements
    & $VenvPython -m pip install -r $requirements
    if ($LASTEXITCODE -ne 0) {
        Add-Check 'backend_dependencies' 'fail' 'Backend dependency installation failed.' "exit=$LASTEXITCODE"
        return
    }
    if (Test-BackendDependencyImports) {
        Add-Check 'backend_dependencies' 'ok' 'Backend runtime dependencies installed and validated.' ''
    } else {
        Add-Check 'backend_dependencies' 'fail' 'Backend dependency installation completed, but imports still failed.' 'Review the Python output above.'
    }
}

function Find-Npm {
    $commands = @(
        (Get-Command npm.cmd -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
        (Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages') -Recurse -Filter npm.cmd -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName)
    ) | Where-Object { $_ -and (Test-Path $_) }
    return $commands | Select-Object -First 1
}

function Get-LatestFrontendSourceWriteTime {
    $frontendDir = Join-Path $RootDir 'frontend'
    $paths = @(
        (Join-Path $frontendDir 'src'),
        (Join-Path $frontendDir 'index.html'),
        (Join-Path $frontendDir 'package.json'),
        (Join-Path $frontendDir 'package-lock.json'),
        (Join-Path $frontendDir 'tsconfig.json'),
        (Join-Path $frontendDir 'vite.config.ts')
    )
    $latest = [datetime]::MinValue
    foreach ($path in $paths) {
        if (-not (Test-Path -LiteralPath $path)) { continue }
        $items = @(Get-ChildItem -LiteralPath $path -Recurse -File -ErrorAction SilentlyContinue)
        foreach ($item in $items) {
            if ($item.LastWriteTimeUtc -gt $latest) { $latest = $item.LastWriteTimeUtc }
        }
    }
    return $latest
}

function Get-OldestFrontendBuildWriteTime {
    $distDir = Join-Path $RootDir 'frontend\dist'
    $indexFile = Join-Path $distDir 'index.html'
    $assetsDir = Join-Path $distDir 'assets'
    if (-not (Test-Path -LiteralPath $indexFile)) { return $null }
    $files = @((Get-Item -LiteralPath $indexFile))
    if (Test-Path -LiteralPath $assetsDir) {
        $files += @(Get-ChildItem -LiteralPath $assetsDir -Recurse -File -ErrorAction SilentlyContinue)
    }
    if (-not $files.Count) { return $null }
    return ($files | Sort-Object LastWriteTimeUtc | Select-Object -First 1).LastWriteTimeUtc
}

function Invoke-FrontendBuild {
    param([string]$Npm)

    $indexFile = Join-Path $RootDir 'frontend\dist\index.html'
    Push-Location (Join-Path $RootDir 'frontend')
    try {
        & $Npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install failed with exit $LASTEXITCODE" }
        & $Npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed with exit $LASTEXITCODE" }
        Add-Check 'frontend_build' 'ok' 'Frontend build completed.' $indexFile
    } catch {
        Add-Check 'frontend_build' 'fail' 'Frontend build failed.' $_.Exception.Message
    } finally { Pop-Location }
}

function Ensure-Frontend {
    if ($SkipFrontendBuild) {
        Add-Check 'frontend_build' 'warn' 'Frontend build check skipped.' ''
        return
    }
    $indexFile = Join-Path $RootDir 'frontend\dist\index.html'
    $sourceLatest = Get-LatestFrontendSourceWriteTime
    $buildOldest = Get-OldestFrontendBuildWriteTime
    $buildExists = Test-Path -LiteralPath $indexFile
    $buildIsStale = $buildExists -and $buildOldest -and ($sourceLatest -gt $buildOldest)
    if ($buildExists -and -not $buildIsStale) {
        Add-Check 'frontend_build' 'ok' 'Built browser UI is present and current.' $indexFile
        return
    }
    $npm = Find-Npm
    if (-not $npm) {
        if ($buildExists) {
            Add-Check 'frontend_build' 'warn' 'Frontend build may be stale and npm is not available to refresh it.' 'Install Node.js/npm or use a packaged release with rebuilt frontend assets.'
        } else {
            Add-Check 'frontend_build' 'warn' 'Frontend build missing and npm is not available.' 'Packaged releases should include frontend\dist.'
        }
        return
    }
    if ($buildIsStale) {
        Add-Check 'frontend_build' 'warn' 'Rebuilding frontend because source files are newer than frontend\dist.' ''
    } else {
        Add-Check 'frontend_build' 'warn' 'Building frontend because frontend\dist is missing.' ''
    }
    if (-not (Confirm-SetupAction -Action 'The browser UI needs a frontend build. The launcher can run npm install and npm run build in the frontend folder.' -Detail (Join-Path $RootDir 'frontend'))) {
        if ($buildExists) {
            Add-Check 'frontend_build' 'warn' 'Frontend rebuild was declined; using the existing built browser UI.' $indexFile
            return
        }
        Add-Check 'frontend_build' 'fail' 'Frontend build is missing and rebuild was declined.' 'Use a packaged release with frontend\dist, or rerun with -AssumeYes to build from source.'
        return
    }
    Invoke-FrontendBuild -Npm $npm
}

function Test-Port {
    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse('127.0.0.1'), $Port)
        $listener.Start()
        Add-Check 'port' 'ok' "Port $Port is available on 127.0.0.1." ''
    } catch {
        Add-Check 'port' 'fail' "Port $Port is already in use." $_.Exception.Message
    } finally {
        if ($listener) { $listener.Stop() }
    }
}

function Test-BackendConfig {
    if (-not (Test-Path $VenvPython)) { return }
    $env:IZ_CNA_ENV_FILE = $EnvFile
    $env:PYTHONPATH = Join-Path $RootDir 'backend'
    $code = @"
from app.services.rules_engine import load_rules_config, validate_rules_config
from app.services.treatment_plan_checklist import load_treatment_plan_checklist, validate_treatment_plan_checklist
rules = load_rules_config()
errors = validate_rules_config(rules)
if errors:
    raise SystemExit('; '.join(errors))
checklist = load_treatment_plan_checklist()
checklist_errors = validate_treatment_plan_checklist(checklist)
if checklist_errors:
    raise SystemExit('; '.join(checklist_errors))
if len(checklist['steps']) != 42:
    raise SystemExit('Treatment Plan Checklist must contain 42 steps.')
print('backend configuration ok')
"@
    $exitCode = Invoke-PythonSnippetFile -PythonExe $VenvPython -Code $code
    if ([int]$exitCode -eq 0) {
        Add-Check 'backend_config' 'ok' 'Rules and Treatment Plan Checklist validated.' ''
    } else {
        Add-Check 'backend_config' 'fail' 'Rules or Treatment Plan Checklist validation failed.' "exit=$exitCode"
    }
}

Set-Location $RootDir
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
Add-Check 'repo' 'ok' 'Repository root located.' $RootDir
Add-Check 'appdata' 'ok' 'Local AppData folders are writable.' $AppDataRoot
Ensure-EnvFile
$python = Ensure-Python
Ensure-Venv -PythonExe $python
Ensure-Frontend
Test-BackendConfig
Test-Port

$failed = ($Results | Where-Object { $_.status -eq 'fail' }).Count
$warnings = ($Results | Where-Object { $_.status -eq 'warn' }).Count
$payload = [ordered]@{
    generated_at = (Get-Date).ToUniversalTime().ToString('o')
    repo_root = $RootDir
    app_data_root = $AppDataRoot
    status = if ($failed) { 'fail' } elseif ($warnings) { 'warn' } else { 'ok' }
    failed = $failed
    warnings = $warnings
    checks = $Results
}
New-Item -ItemType Directory -Path (Split-Path $ReportFile -Parent) -Force | Out-Null
$payload | ConvertTo-Json -Depth 6 | Set-Content -Path $ReportFile -Encoding UTF8
Write-Host "Preflight report: $ReportFile"
if ($failed) { exit 1 }
exit 0
