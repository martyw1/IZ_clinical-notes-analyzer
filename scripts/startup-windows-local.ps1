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

function Get-EnvValue {
    param(
        [string]$Name,
        [string]$Default = ''
    )

    if (!(Test-Path $EnvFile)) { return $Default }
    $line = Get-Content -Path $EnvFile -ErrorAction SilentlyContinue | Where-Object { $_ -match "^$([regex]::Escape($Name))=" } | Select-Object -First 1
    if (!$line) { return $Default }
    return ($line -replace "^$([regex]::Escape($Name))=", '').Trim()
}

function Write-CloudSyncWarning {
    $lower = $RootDir.ToLowerInvariant()
    $markers = @('onedrive', 'dropbox', 'icloud', 'google drive')
    foreach ($marker in $markers) {
        if ($lower.Contains($marker)) {
            Write-Warn "This source checkout appears to be inside a cloud-synced folder ($RootDir). Runtime database, logs, and uploads stay under $AppDataRoot, but Python/Node setup is usually more reliable from a non-synced local folder such as C:\IZ Clinical Notes Analyzer."
            return
        }
    }
}

function Assert-PortAvailable {
    param([int]$Port)
    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse('127.0.0.1'), $Port)
        $listener.Start()
    }
    catch {
        throw "Port $Port is already in use on 127.0.0.1. Close the other local app/server using http://localhost:$Port, then rerun this launcher. Log file: $LogFile"
    }
    finally {
        if ($listener) { $listener.Stop() }
    }
}

function Invoke-Preflight {
    param([int]$Port)

    $preflight = Join-Path $PSScriptRoot 'preflight-windows.ps1'
    if (!(Test-Path $preflight)) {
        throw "Could not find preflight script at $preflight. Keep this script in the repo scripts folder."
    }

    Write-Info 'Running Windows preflight before launch.'
    & $preflight -AssumeYes:$AssumeYes -SkipFrontendBuild:$SkipFrontendBuild -Port $Port
    $exitCode = [int]$LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "Windows preflight failed with exit code $exitCode. Review $AppDataRoot\logs\preflight-windows-latest.json."
    }
}

try {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    Start-Transcript -Path $LogFile -Append | Out-Null
    $TranscriptStarted = $true

    Set-Location $RootDir
    Write-CloudSyncWarning

    $portText = Get-EnvValue -Name 'BACKEND_PORT' -Default '8000'
    $port = 8000
    if (-not [int]::TryParse($portText, [ref]$port)) { $port = 8000 }

    Invoke-Preflight -Port $port

    $pythonExe = Join-Path $RootDir 'backend\.venv\Scripts\python.exe'
    if (!(Test-Path $pythonExe)) {
        throw "Backend Python runtime was not found at $pythonExe after preflight."
    }

    $env:IZ_CNA_ENV_FILE = $EnvFile
    $env:PYTHONPATH = Join-Path $RootDir 'backend'

    Write-Info "Using Python runtime: $pythonExe"
    & $pythonExe -c "import sys; print('Python version: ' + sys.version.split()[0])"
    if ($LASTEXITCODE -ne 0) { throw "Could not run Python at $pythonExe." }

    Assert-PortAvailable -Port $port
    Write-Pass 'Startup checks completed without the legacy dependency-check false failure path.'
    Write-Info "Starting local app on http://localhost:$port"

    if (-not $NoBrowser) { Start-Process "http://localhost:$port" }
    & $pythonExe -m uvicorn app.desktop_main:app --app-dir (Join-Path $RootDir 'backend') --host 127.0.0.1 --port $port --no-access-log
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
