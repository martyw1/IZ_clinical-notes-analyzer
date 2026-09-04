[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$AssumeYes,
    [switch]$SkipFrontendBuild,
    [switch]$SkipFrontendCheck,
    [switch]$InitializePackagedRuntime,
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
    $alphabet = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_!@#$%^+='
    $bytes = New-Object byte[] $Length
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        do {
            $rng.GetBytes($bytes)
            $secret = -join ($bytes | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
        } until ($secret -match '[A-Za-z]' -and $secret -match '[0-9]')
    }
    finally {
        if ($rng -and ($rng -is [System.IDisposable])) { $rng.Dispose() }
    }
    return $secret
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
        if (Test-Path -LiteralPath (Join-Path $RootDir 'frontend\package-lock.json')) {
            & $Npm ci
            if ($LASTEXITCODE -ne 0) { throw "npm ci failed with exit $LASTEXITCODE" }
        } else {
            & $Npm install
            if ($LASTEXITCODE -ne 0) { throw "npm install failed with exit $LASTEXITCODE" }
        }
        & $Npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed with exit $LASTEXITCODE" }
        if (Test-FrontendBuildValid) {
            Add-Check 'frontend_build' 'ok' 'Frontend build completed.' $indexFile
        } else {
            Add-Check 'frontend_build' 'fail' 'Frontend build completed, but frontend\dist is missing expected files.' 'Expected index.html plus built JS and CSS assets.'
        }
    } catch {
        Add-Check 'frontend_build' 'fail' 'Frontend build failed.' $_.Exception.Message
    } finally { Pop-Location }
}

function Test-FrontendBuildValid {
    $distDir = Join-Path $RootDir 'frontend\dist'
    $indexFile = Join-Path $distDir 'index.html'
    $assetsDir = Join-Path $distDir 'assets'
    if (-not (Test-Path -LiteralPath $indexFile)) { return $false }
    if (-not (Test-Path -LiteralPath $assetsDir)) { return $false }
    $assetFiles = @(Get-ChildItem -LiteralPath $assetsDir -Recurse -File -ErrorAction SilentlyContinue)
    $jsAssets = @($assetFiles | Where-Object { $_.Extension -eq '.js' -and $_.Length -gt 0 })
    $cssAssets = @($assetFiles | Where-Object { $_.Extension -eq '.css' -and $_.Length -gt 0 })
    if ($jsAssets.Count -eq 0 -or $cssAssets.Count -eq 0) { return $false }
    $indexText = Get-Content -LiteralPath $indexFile -Raw
    return ($indexText -match '/assets/.+\.js')
}

function Ensure-Frontend {
    if ($SkipFrontendBuild) {
        if (Test-FrontendBuildValid) {
            Add-Check 'frontend_build' 'ok' 'Existing built browser UI is present.' (Join-Path $RootDir 'frontend\dist\index.html')
        } else {
            Add-Check 'frontend_build' 'fail' 'Frontend build is missing or incomplete.' 'Run Build-IZ-Windows-Installer.cmd without -SkipFrontendBuild, or install Node.js LTS and rerun setup.'
        }
        return
    }
    $indexFile = Join-Path $RootDir 'frontend\dist\index.html'
    $sourceLatest = Get-LatestFrontendSourceWriteTime
    $buildOldest = Get-OldestFrontendBuildWriteTime
    $buildExists = Test-Path -LiteralPath $indexFile
    $buildValid = Test-FrontendBuildValid
    $buildIsStale = $buildValid -and $buildOldest -and ($sourceLatest -gt $buildOldest)
    if ($buildValid -and -not $buildIsStale) {
        Add-Check 'frontend_build' 'ok' 'Built browser UI is present and current.' $indexFile
        return
    }
    $npm = Find-Npm
    if (-not $npm) {
        if ($buildValid) {
            Add-Check 'frontend_build' 'warn' 'Frontend build may be stale and npm is not available to refresh it.' 'Install Node.js/npm or use a packaged release with rebuilt frontend assets.'
        } else {
            Add-Check 'frontend_build' 'fail' 'Frontend build is missing and npm is not available.' 'Install Node.js LTS from https://nodejs.org/ or run: winget install OpenJS.NodeJS.LTS --scope user'
        }
        return
    }
    if ($buildIsStale) {
        Add-Check 'frontend_build' 'warn' 'Rebuilding frontend because source files are newer than frontend\dist.' ''
    } else {
        Add-Check 'frontend_build' 'warn' 'Building frontend because frontend\dist is missing.' ''
    }
    if (-not (Confirm-SetupAction -Action 'The browser UI needs a frontend build. The launcher can run npm install and npm run build in the frontend folder.' -Detail (Join-Path $RootDir 'frontend'))) {
        if ($buildValid) {
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
import json
from pathlib import Path

import yaml

from app.services.version import build_version_payload
from app.v2.api.routes import router as v2_router

root = Path(r"$RootDir")
rules_path = root / "config" / "rules" / "alleva_treatment_plan_completeness_rules.yaml"
checklist_path = root / "config" / "checklists" / "treatment-plan-v1.json"

rules = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
if not isinstance(rules, dict):
    raise SystemExit("Rules config must be a YAML mapping.")
if not rules.get("rules"):
    raise SystemExit("Rules config must include at least one rule.")
if not rules.get("levels_of_care"):
    raise SystemExit("Rules config must include levels_of_care.")
if rules.get("loc_change_blocker", {}).get("status") != "unvalidated":
    raise SystemExit("LOC-change blocker must remain unvalidated.")

checklist = json.loads(checklist_path.read_text(encoding="utf-8"))
steps = checklist.get("steps")
if not isinstance(steps, list) or len(steps) != 42:
    raise SystemExit("Treatment Plan Checklist must contain 42 steps.")
expected_steps = list(range(1, 43))
actual_steps = [step.get("step") for step in steps]
if actual_steps != expected_steps:
    raise SystemExit("Treatment Plan Checklist steps must be numbered 1 through 42.")

version = build_version_payload()
if version.get("version") != "2.0.0-beta.3" or version.get("release_channel") != "beta-local-desktop-v2":
    raise SystemExit("Active version metadata is not V2 beta.")
if not v2_router.routes:
    raise SystemExit("V2 router has no active routes.")
print("backend configuration ok")
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
if (-not $InitializePackagedRuntime) {
    $python = Ensure-Python
    Ensure-Venv -PythonExe $python
    if ($SkipFrontendCheck) {
        Add-Check 'frontend_build' 'ok' 'Frontend build check deferred to the installer build script.' ''
    } else {
        Ensure-Frontend
    }
    Test-BackendConfig
    Test-Port
}

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
