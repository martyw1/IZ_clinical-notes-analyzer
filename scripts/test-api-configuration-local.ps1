[CmdletBinding()]
param(
    [int]$Port = 8020,
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = 'Stop'
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$AppDataRoot = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer API Config Test'
$DatabasePath = Join-Path $AppDataRoot 'api-config-test.sqlite3'
$EnvFile = Join-Path $AppDataRoot '.env'
$LogDir = Join-Path $AppDataRoot 'logs'
$BaseUrl = "http://127.0.0.1:$Port"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

function Write-Step($Message) { Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message" }

function Reset-SmokeDatabase {
    param([string]$DatabasePath)

    foreach ($path in @($DatabasePath, "$DatabasePath-shm", "$DatabasePath-wal")) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force
        }
    }
}

function New-RandomSecret([int]$Length) {
    $alphabet = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_!@#$%^+='
    $bytes = New-Object byte[] $Length
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) }
    finally { if ($rng -and ($rng -is [System.IDisposable])) { $rng.Dispose() } }
    $chars = for ($i = 0; $i -lt $Length; $i++) { $alphabet[$bytes[$i] % $alphabet.Length] }
    return -join $chars
}

function Assert-PythonVersion([string]$PythonExe) {
    $versionText = & $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
    if ($LASTEXITCODE -ne 0) { throw "Could not run Python at $PythonExe." }
    $version = [version]$versionText.Trim()
    if ($version -lt [version]'3.11.0') { throw "Python 3.11+ is required. Found Python $version at $PythonExe." }
    return $version
}

function Ensure-BackendVirtualEnvironment {
    $venvDir = Join-Path $RootDir 'backend\.venv'
    $python = Join-Path $venvDir 'Scripts\python.exe'
    if (Test-Path $python) { return $python }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        & $pythonCommand.Source -m venv $venvDir
        if (Test-Path $python) { return $python }
    }

    $pyCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCommand) {
        & $pyCommand.Source -3.11 -m venv $venvDir
        if (Test-Path $python) { return $python }
        & $pyCommand.Source -3 -m venv $venvDir
        if (Test-Path $python) { return $python }
    }

    throw 'Could not create backend\.venv. Install Python 3.11+ and reopen PowerShell.'
}

try {
    Set-Location $RootDir
    Reset-SmokeDatabase -DatabasePath $DatabasePath
    $python = Ensure-BackendVirtualEnvironment
    $pythonVersion = Assert-PythonVersion $python
    Write-Step "Using Python $pythonVersion at $python."

    if (-not $SkipDependencyInstall) {
        Write-Step 'Installing backend dependencies.'
        & $python -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
        & $python -m pip install -r (Join-Path $RootDir 'backend\requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
    }

    $adminPassword = New-RandomSecret 24
    @"
APP_NAME=IZ Clinical Notes Analyzer
ENVIRONMENT=development
BACKEND_PORT=$Port
DATABASE_BACKEND=sqlite
LOCAL_SQLITE_DB_PATH=$DatabasePath
IZ_CNA_LOCAL_APP_DATA_DIR=$AppDataRoot
DATABASE_URL=
SECRET_KEY=$(New-RandomSecret 64)
DATA_ENCRYPTION_KEY=$(New-RandomSecret 64)
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

    $previousEnvFile = $env:IZ_CNA_ENV_FILE
    try {
        Remove-Item Env:\IZ_CNA_ENV_FILE -ErrorAction SilentlyContinue
    $env:PYTHONPATH = Join-Path $RootDir 'backend'

    Write-Step 'Running focused backend V2 API harness tests.'
    $focusedTests = @(
        Join-Path $RootDir 'backend\tests\test_v2_runtime_readiness.py'
        Join-Path $RootDir 'backend\tests\test_v2_oauth_connectivity.py'
        Join-Path $RootDir 'backend\tests\test_v2_openapi_pull.py'
        Join-Path $RootDir 'backend\tests\test_v2_operation_test.py'
        Join-Path $RootDir 'backend\tests\test_v2_harness_job_persistence.py'
    )
    & $python -m pytest $focusedTests -q
    if ($LASTEXITCODE -ne 0) { throw 'V2 API harness unit tests failed.' }

    $env:IZ_CNA_ENV_FILE = $EnvFile

    Write-Step "Starting desktop app test server on $BaseUrl ."
    $appDir = Join-Path $RootDir 'backend'
    $uvicornArgs = "-m uvicorn app.desktop_main:app --app-dir `"$appDir`" --host 127.0.0.1 --port $Port"
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

        Write-Step 'Checking API configuration page.'
        $page = Invoke-WebRequest -Uri "$BaseUrl/api-configuration" -TimeoutSec 10 -UseBasicParsing
        if ($page.StatusCode -ne 200 -or $page.Content -notmatch 'API Configuration and Connectivity Test') {
            throw 'API configuration page did not load as expected.'
        }

        Write-Step 'Signing in as bootstrap admin.'
        $loginBody = @{ username = 'admin'; password = $adminPassword } | ConvertTo-Json
        $login = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/auth/login" -ContentType 'application/json' -Body $loginBody
        $headers = @{ Authorization = "Bearer $($login.access_token)" }
        if ($login.must_reset_password) {
            Write-Step 'Completing bootstrap administrator password change.'
            $activeAdminPassword = New-RandomSecret 24
            $passwordChangeBody = @{ current_password = $adminPassword; new_password = $activeAdminPassword } | ConvertTo-Json
            Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/users/me/change-password" -Headers $headers -ContentType 'application/json' -Body $passwordChangeBody | Out-Null
            $adminPassword = $activeAdminPassword
            $loginBody = @{ username = 'admin'; password = $adminPassword } | ConvertTo-Json
            $login = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/auth/login" -ContentType 'application/json' -Body $loginBody
            $headers = @{ Authorization = "Bearer $($login.access_token)" }
        }

        Write-Step 'Saving API configuration and encrypted API key placeholder.'
        $configBody = @{
            vendor_name = 'Local Test API'
            api_base_url = $BaseUrl
            openapi_url = "$BaseUrl/api/api-configuration/sample-openapi.json"
            api_key = (New-RandomSecret 20)
            timeout_seconds = 5
            api_enabled = $false
        } | ConvertTo-Json
        $config = Invoke-RestMethod -Method Patch -Uri "$BaseUrl/api/api-configuration" -Headers $headers -ContentType 'application/json' -Body $configBody
        if (-not $config.api_key_configured) { throw 'Saved API key was not reported as configured.' }

        Write-Step 'Pulling local sample API definition through the in-app tester.'
        $definition = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/api-configuration/pull-definitions" -Headers $headers
        if ($definition.status -ne 'ok') { throw "API definition pull did not pass: $($definition | ConvertTo-Json -Depth 8)" }
        if ($definition.definition_summary.title -notmatch 'Connectivity Test Definition') { throw 'API definition summary was not returned as expected.' }
        if ($definition.definition_summary.operation_count -ne 1 -or $definition.redaction_status -ne 'safe_summary_only') { throw "API definition pull did not return the expected safe summary: $($definition | ConvertTo-Json -Depth 8)" }

        Write-Step 'Verifying the local API profile leaves live harness execution disabled.'
        if ($config.api_enabled) { throw 'Local API configuration unexpectedly enabled live harness execution.' }

        Write-Step 'API configuration local smoke test passed.'
    }
    finally {
        if ($server -and !$server.HasExited) { Stop-Process -Id $server.Id -Force }
    }
    }
    finally {
        if ($null -eq $previousEnvFile) {
            Remove-Item Env:\IZ_CNA_ENV_FILE -ErrorAction SilentlyContinue
        }
        else {
            $env:IZ_CNA_ENV_FILE = $previousEnvFile
        }
    }
}
catch {
    Write-Error "API configuration local smoke test failed: $($_.Exception.Message)"
    throw
}
