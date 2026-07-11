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

function Wait-ForReadiness {
    param(
        [System.Diagnostics.Process]$Process,
        [int]$Port
    )

    $deadline = (Get-Date).AddSeconds(45)
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/api/readiness" -TimeoutSec 2
            if ($response.StatusCode -eq 200 -and $response.Content -match '"status"') {
                return
            }
        }
        catch {
        }
        if ($Process.HasExited) {
            throw "Startup readiness check failed because the local runtime exited with code $($Process.ExitCode)."
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)

    throw 'Startup readiness check failed because the local runtime did not become ready within 45 seconds.'
}

if ($Foreground) {
    & $startupScript -NoBrowser:$NoBrowser -SkipFrontendBuild:$SkipFrontendBuild -AssumeYes:$AssumeYes
    exit $LASTEXITCODE
}

$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$startupScript`""
if ($SkipFrontendBuild) { $arguments += ' -SkipFrontendBuild' }
if ($AssumeYes) { $arguments += ' -AssumeYes' }
if ($NoBrowser) { $arguments += ' -NoBrowser' }
$process = Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -WorkingDirectory (Split-Path $PSScriptRoot -Parent) -WindowStyle Hidden -PassThru
Wait-ForReadiness -Process $process -Port 8000
Write-Host "IZ Clinical Notes Analyzer is starting in the background (PID $($process.Id))."
Write-Host 'Readiness: http://127.0.0.1:8000/api/readiness'
Write-Host 'Version: http://127.0.0.1:8000/api/version'
