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
if ($Foreground) {
    & $startupScript -NoBrowser:$NoBrowser -SkipFrontendBuild:$SkipFrontendBuild -AssumeYes:$AssumeYes
    exit $LASTEXITCODE
}

$skipFrontendValue = [bool]$SkipFrontendBuild
$assumeYesValue = [bool]$AssumeYes
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$startupScript`" -SkipFrontendBuild:$skipFrontendValue -AssumeYes:$assumeYesValue"
if ($NoBrowser) { $arguments += ' -NoBrowser' }
$process = Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -WorkingDirectory (Split-Path $PSScriptRoot -Parent) -WindowStyle Hidden -PassThru
Write-Host "IZ Clinical Notes Analyzer is starting in the background (PID $($process.Id))."
Write-Host 'Readiness: http://127.0.0.1:8000/api/readiness'
Write-Host 'Version: http://127.0.0.1:8000/api/version'
