<#
.SYNOPSIS
Runs isolated synthetic office-manager scenarios in installed Edge or Chrome.
.DESCRIPTION
Uses existing dependencies only. Each run creates a unique OS-local runtime,
keeps credentials only in child-process memory, and records sanitized evidence.
BaseUrl and LocalAppDataDir exist for fail-closed guard testing, not app attachment.
InteractiveSeconds opens a separate headed QA browser after automated checks and
keeps only the owned runtime alive for a bounded hands-on verification session.
InteractiveCredentialsFromEnvironment optionally accepts a fresh synthetic password
from the native controller's child environment, only with a bounded session.
.EXAMPLE
powershell -NoProfile -File scripts/test-office-manager-smoke.ps1 -Scenario harness -Case all -BrowserChannel msedge -EvidenceDir .omo/evidence/office-manager-production-fixes
#>
[CmdletBinding()]
param(
    [ValidatePattern('^[a-z0-9-]+$')][string]$Scenario = 'harness',
    [ValidateSet('happy', 'edge', 'all')][string]$Case = 'all',
    [ValidateSet('msedge', 'chrome')][string]$BrowserChannel = 'msedge',
    [string]$EvidenceDir = '.omo/evidence/office-manager-production-fixes',
    [ValidateSet('checkout', 'prepared')][string]$RuntimeMode = 'checkout',
    [string]$PreparedExecutable = '',
    [string]$BaseUrl = '',
    [string]$LocalAppDataDir = '',
    [ValidateRange(0, 900)][int]$InteractiveSeconds = 0,
    [switch]$InteractiveCredentialsFromEnvironment,
    [ValidateSet('admin', 'office_manager', 'counselor', 'viewer')][string]$InteractiveRole = 'office_manager',
    [switch]$Headed
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $repoRoot 'frontend/e2e/office-manager/support/runner.mjs'
$node = Get-Command node -ErrorAction Stop
$arguments = @(
    $runner, '--scenario', $Scenario, '--case', $Case, '--browser-channel', $BrowserChannel,
    '--evidence-dir', $EvidenceDir, '--runtime-mode', $RuntimeMode,
    '--interactive-seconds', [string]$InteractiveSeconds, '--interactive-role', $InteractiveRole
)
if ($PreparedExecutable) { $arguments += @('--prepared-executable', $PreparedExecutable) }
if ($BaseUrl) { $arguments += @('--base-url', $BaseUrl) }
if ($LocalAppDataDir) { $arguments += @('--local-app-data-dir', $LocalAppDataDir) }
if ($Headed) { $arguments += '--headed' }
if ($InteractiveCredentialsFromEnvironment) { $arguments += '--interactive-credentials-from-environment' }
& $node.Source @arguments
exit $LASTEXITCODE
