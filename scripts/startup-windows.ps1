[CmdletBinding()]
param(
    [switch]$SkipWingetInstall
)

$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Path $PSScriptRoot -Parent
$LogDir = Join-Path $RootDir 'logs'
if (!(Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}
$Timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogFile = Join-Path $LogDir "startup-windows-$Timestamp.log"
Start-Transcript -Path $LogFile -Append | Out-Null

function Write-Info($Message) { Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [INFO] $Message" }
function Write-Warn($Message) { Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [WARN] $Message" -ForegroundColor Yellow }
function Write-Pass($Message) { Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [PASS] $Message" -ForegroundColor Green }

function Ensure-Command {
    param(
        [string]$Command,
        [string]$WingetId,
        [string]$DisplayName
    )

    if (Get-Command $Command -ErrorAction SilentlyContinue) {
        Write-Pass "Found $DisplayName"
        return
    }

    if ($SkipWingetInstall) {
        throw "$DisplayName is missing and -SkipWingetInstall was provided."
    }

    if (!(Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "winget is required to install missing dependencies automatically."
    }

    Write-Info "Installing $DisplayName via winget ($WingetId)"
    winget install --id $WingetId --accept-source-agreements --accept-package-agreements --silent
}

try {
    Set-Location $RootDir
    Write-Info "Starting Windows bootstrap from $RootDir"

    if (!(Test-Path (Join-Path $RootDir '.env'))) {
        Copy-Item (Join-Path $RootDir '.env.example') (Join-Path $RootDir '.env')
        Write-Info 'Created .env from .env.example'
    } else {
        Write-Pass '.env already exists'
    }

    Ensure-Command -Command git -WingetId Git.Git -DisplayName 'Git'
    Ensure-Command -Command python -WingetId Python.Python.3.11 -DisplayName 'Python 3.11+'
    Ensure-Command -Command npm -WingetId OpenJS.NodeJS.LTS -DisplayName 'Node.js LTS (npm)'
    Ensure-Command -Command docker -WingetId Docker.DockerDesktop -DisplayName 'Docker Desktop'

    Write-Info 'Validating Docker engine availability'
    docker info | Out-Null
    docker compose version | Out-Null
    Write-Pass 'Docker engine and compose plugin are available'

    Write-Info 'Setting up backend Python environment'
    python -m venv backend/.venv
    & (Join-Path $RootDir 'backend/.venv/Scripts/python.exe') -m pip install --upgrade pip
    & (Join-Path $RootDir 'backend/.venv/Scripts/python.exe') -m pip install -r (Join-Path $RootDir 'backend/requirements.txt')

    Write-Info 'Setting up frontend Node environment'
    Set-Location (Join-Path $RootDir 'frontend')
    npm install
    Set-Location $RootDir

    Write-Info 'Starting Docker Compose stack'
    docker compose pull
    $composeArgs = @()
    $useInternal = if ($env:USE_INTERNAL_POSTGRES) { $env:USE_INTERNAL_POSTGRES } else { '1' }
    $dbMode = if ($env:DATABASE_HOST_MODE) { $env:DATABASE_HOST_MODE } else { 'internal' }
    if ($useInternal -eq '1') { $composeArgs += '--profile'; $composeArgs += 'internal-db' }
    Write-Info "DB mode: $dbMode (USE_INTERNAL_POSTGRES=$useInternal)"
    docker compose @composeArgs up -d --build

    Write-Info 'Current service status'
    docker compose @composeArgs ps

    Write-Pass "Startup complete. Logs are in $LogFile"
}
catch {
    Write-Error "Startup failed: $($_.Exception.Message)"
    throw
}
finally {
    Stop-Transcript | Out-Null
}
