[CmdletBinding()]
param(
    [switch]$AssumeYes
)

$ErrorActionPreference = 'Stop'
Write-Host 'Running Windows setup/preflight. Treatment-plan implementation reference: docs\patient-treatment-plan-handling.md'
& (Join-Path $PSScriptRoot 'preflight-windows.ps1') -AssumeYes:$AssumeYes
exit $LASTEXITCODE
