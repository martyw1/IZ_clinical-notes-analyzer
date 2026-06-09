[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$SkipFrontendBuild,
    [switch]$AssumeYes
)

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'startup-windows-local.ps1') -NoBrowser:$NoBrowser -SkipFrontendBuild:$SkipFrontendBuild -AssumeYes:$AssumeYes
exit $LASTEXITCODE
