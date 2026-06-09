[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$SkipFrontendBuild,
    [switch]$AssumeYes
)

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'preflight-windows.ps1') -AssumeYes:$AssumeYes -SkipFrontendBuild:$SkipFrontendBuild
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $PSScriptRoot 'startup-windows-local.ps1') -NoBrowser:$NoBrowser -SkipFrontendBuild:$SkipFrontendBuild -AssumeYes:$AssumeYes
exit $LASTEXITCODE
