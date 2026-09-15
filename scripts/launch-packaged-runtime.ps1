[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$NoPause
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$exitCode = 0

try {
    $installRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
    $commonPath = Join-Path $installRoot 'installer\maintenance-common.psm1'
    $runtimePath = Join-Path $installRoot 'installer\maintenance-runtime.psm1'
    if (-not (Test-Path -LiteralPath $commonPath -PathType Leaf) -or -not (Test-Path -LiteralPath $runtimePath -PathType Leaf)) {
        throw 'INSTALLED_MAINTENANCE_MODULE_MISSING'
    }
    Import-Module $commonPath -Force
    Import-Module $runtimePath
    $context = Get-IzMaintenanceContext
    if (-not $installRoot.Equals($context.install_root, [StringComparison]::OrdinalIgnoreCase)) { throw 'INSTALL_ROOT_IDENTITY_MISMATCH' }
    $pending = Get-IzPendingMaintenanceStatus -Context $context
    if ($pending.status -eq 'PENDING' -or $pending.status -eq 'RECOVERY_REQUIRED') { throw 'MAINTENANCE_RECOVERY_REQUIRED' }
    if ($pending.status -eq 'COMMITTED' -and $pending.authority.launch_policy -ne 'candidate') { throw 'MAINTENANCE_AUTHORITY_INVALID' }
    $started = Start-IzOwnedRuntime -Context $context -RuntimeRole Installed -NoBrowser:$NoBrowser
    Write-Host ("[pass] IZ Clinical Notes Analyzer runtime {0} on http://127.0.0.1:{1}/" -f $started.status, [int]$started.identity.port)
} catch {
    $exitCode = if ($_.Exception.Data.Contains('iz_exit_code')) { [int]$_.Exception.Data['iz_exit_code'] } else { 20 }
    $reason = if ($_.Exception.Data.Contains('iz_reason')) { [string]$_.Exception.Data['iz_reason'] } elseif ($_.Exception.Message -match '^[A-Z][A-Z0-9_]+$') { $_.Exception.Message } else { 'RUNTIME_LAUNCH_FAILED' }
    Write-Host "[fail] $reason" -ForegroundColor Red
} finally {
    if ($exitCode -ne 0 -and -not $NoPause) { Read-Host 'Press Enter to close this window' | Out-Null }
}
exit $exitCode
