[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$SkipFrontendBuild,
    [switch]$AssumeYes,
    [switch]$NoPause,
    [switch]$Foreground
)

$ErrorActionPreference = 'Stop'
$startupScript = Join-Path $PSScriptRoot 'startup-windows-local.ps1'
$envFile = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer\\.env'

function Get-ConfiguredPort {
    $port = 8000
    if (Test-Path -LiteralPath $envFile) {
        $portLine = Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^BACKEND_PORT=' } | Select-Object -First 1
        $candidate = 0
        if ($portLine -and [int]::TryParse(($portLine -replace '^BACKEND_PORT=', '').Trim(), [ref]$candidate) -and $candidate -ge 1 -and $candidate -le 65535) {
            $port = $candidate
        }
    }
    return $port
}

function Assert-PortAvailable {
    param([int]$Port)

    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse('127.0.0.1'), $Port)
        $listener.Start()
    }
    catch {
        throw "Port $Port is already in use on 127.0.0.1. Stop the existing local app before starting another instance."
    }
    finally {
        if ($listener) { $listener.Stop() }
    }
}

function Wait-ForReadiness {
    param(
        [System.Diagnostics.Process]$Process,
        [int]$Port
    )

    $deadline = (Get-Date).AddMinutes(10)
    do {
        if ($Process.HasExited) {
            throw "Startup readiness check failed because the local runtime exited with code $($Process.ExitCode)."
        }
        $ready = $false
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/api/readiness" -TimeoutSec 2
            $ready = $response.StatusCode -eq 200 -and $response.Content -match '"status"'
        }
        catch {
        }
        if ($Process.HasExited) {
            throw "Startup readiness check failed because the local runtime exited with code $($Process.ExitCode)."
        }
        if ($ready) { return }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)

    throw 'Startup readiness check failed because the local runtime did not become ready within 10 minutes.'
}

if ($Foreground) {
    & $startupScript -NoBrowser:$NoBrowser -SkipFrontendBuild:$SkipFrontendBuild -AssumeYes:$AssumeYes
    exit $LASTEXITCODE
}

$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$startupScript`""
if ($SkipFrontendBuild) { $arguments += ' -SkipFrontendBuild' }
if ($AssumeYes) { $arguments += ' -AssumeYes' }
if ($NoBrowser) { $arguments += ' -NoBrowser' }
$port = Get-ConfiguredPort
Assert-PortAvailable -Port $port
$process = Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -WorkingDirectory (Split-Path $PSScriptRoot -Parent) -WindowStyle Hidden -PassThru
Wait-ForReadiness -Process $process -Port $port
Write-Host "IZ Clinical Notes Analyzer is starting in the background (PID $($process.Id))."
Write-Host "Readiness: http://127.0.0.1:$port/api/readiness"
Write-Host "Version: http://127.0.0.1:$port/api/version"
