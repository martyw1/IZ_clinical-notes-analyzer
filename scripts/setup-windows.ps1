[CmdletBinding()]
param(
    [switch]$AssumeYes
)

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'preflight-windows.ps1') -AssumeYes:$AssumeYes
exit $LASTEXITCODE
