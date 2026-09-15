[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,
    [switch]$NoStop,
    [switch]$AssumeYes,
    [switch]$NoPause
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$script:ExitCode = 0
$script:LockHandle = $null
$script:Context = $null

function New-IzRestoreEntryPointError {
    param([string]$Reason, [int]$Code = 20)
    $exception = [InvalidOperationException]::new($Reason)
    $exception.Data['iz_reason'] = $Reason
    $exception.Data['iz_exit_code'] = $Code
    return $exception
}

function Get-IzSafeRestoreReason {
    param([Management.Automation.ErrorRecord]$Record)
    if ($Record.Exception.Data.Contains('iz_reason')) { return [string]$Record.Exception.Data['iz_reason'] }
    return 'RESTORE_FAILED'
}

function Get-IzRestoreRuntimeLayout {
    $applicationRoot = Get-IzCanonicalPath -Path (Split-Path $PSScriptRoot -Parent)
    $containerRoot = Get-IzCanonicalPath -Path (Split-Path $applicationRoot -Parent)
    $runtimePath = Join-Path $applicationRoot 'runtime\IZClinicalNotesAnalyzer.exe'
    $sourcePython = Join-Path $applicationRoot 'backend\.venv\Scripts\python.exe'
    $sourceRuntime = Join-Path $applicationRoot 'backend\app\desktop_runtime.py'
    $sourceVersion = Join-Path $applicationRoot 'VERSION.json'
    $installedManifest = Join-Path $applicationRoot 'release-manifest.json'
    $packageManifest = Join-Path $containerRoot 'release-manifest.json'
    $matches = New-Object Collections.Generic.List[object]
    if ((Test-Path -LiteralPath $sourcePython -PathType Leaf) -and (Test-Path -LiteralPath $sourceRuntime -PathType Leaf) -and (Test-Path -LiteralPath $sourceVersion -PathType Leaf)) {
        $matches.Add([pscustomobject]@{ role = 'SourceTest'; package_root = $applicationRoot; manifest_root = $null })
    }
    if ((Test-Path -LiteralPath $runtimePath -PathType Leaf) -and (Test-Path -LiteralPath $packageManifest -PathType Leaf) -and (Split-Path $applicationRoot -Leaf) -eq 'app') {
        $matches.Add([pscustomobject]@{ role = 'Package'; package_root = $containerRoot; manifest_root = $containerRoot })
    }
    if ((Test-Path -LiteralPath $runtimePath -PathType Leaf) -and (Test-Path -LiteralPath $installedManifest -PathType Leaf)) {
        $matches.Add([pscustomobject]@{ role = 'Installed'; package_root = $null; manifest_root = $applicationRoot })
    }
    if ($matches.Count -ne 1) { throw (New-IzRestoreEntryPointError 'RESTORE_RUNTIME_LAYOUT_INVALID') }
    $selected = $matches[0]
    $manifest = if ($selected.manifest_root) { Read-IzReleaseManifest -PackageRoot $selected.manifest_root } else { $null }
    return [pscustomobject]@{ role = [string]$selected.role; package_root = $selected.package_root; manifest = $manifest }
}

function Assert-IzExternalRestoreInput {
    param([object]$Context, [string]$Path)
    $candidate = Get-IzCanonicalPath -Path $Path
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw (New-IzRestoreEntryPointError 'BACKUP_FILE_MISSING') }
    foreach ($root in @($Context.install_root, $Context.data_root, $Context.maintenance_root, $Context.package_root)) {
        if (-not $root) { continue }
        try {
            [void](Assert-IzContainedPath -Path $candidate -Parent $root -AllowEqual)
            throw (New-IzRestoreEntryPointError 'BACKUP_INPUT_OVERLAPS_PRODUCT_DATA')
        } catch {
            if (-not $_.Exception.Data.Contains('iz_reason') -or $_.Exception.Data['iz_reason'] -ne 'PATH_OUTSIDE_SCOPE') { throw }
        }
    }
    return $candidate
}

function Confirm-IzRestore {
    if ($AssumeYes) { return $true }
    Write-Host ''
    Write-Host 'This will replace this Windows user''s current IZ Clinical Notes Analyzer local data with the encrypted backup.' -ForegroundColor Yellow
    return ((Read-Host 'Type RESTORE to continue').Trim() -eq 'RESTORE')
}

function Invoke-IzStopForRestore {
    if ($NoStop) { return }
    $stopScript = Join-Path $PSScriptRoot 'stop-windows-local.ps1'
    if (-not (Test-Path -LiteralPath $stopScript -PathType Leaf)) { throw (New-IzRestoreEntryPointError 'RESTORE_STOP_HELPER_MISSING') }
    & $stopScript -NoRestartPrompt -NoPause
    if ($LASTEXITCODE -ne 0) { throw (New-IzRestoreEntryPointError 'RESTORE_STOP_FAILED') }
}

function Remove-IzResolvedRestoreTransaction {
    if (-not $script:Context -or -not (Test-Path -LiteralPath $script:Context.transaction_root)) { return }
    [void](Test-IzOwnedRootMarker -Context $script:Context -Path $script:Context.transaction_root -Role transaction -TransactionId ([Guid]$script:Context.transaction_id))
    Remove-Item -LiteralPath $script:Context.transaction_root -Recurse -Force
}

try {
    $commonModule = Join-Path $PSScriptRoot 'installer\maintenance-common.psm1'
    $backupModule = Join-Path $PSScriptRoot 'installer\backup-verification.psm1'
    if (-not (Test-Path -LiteralPath $commonModule -PathType Leaf) -or -not (Test-Path -LiteralPath $backupModule -PathType Leaf)) {
        throw (New-IzRestoreEntryPointError 'RESTORE_HELPER_MISSING')
    }
    Import-Module $commonModule -Force
    Import-Module $backupModule -Force
    $layout = Get-IzRestoreRuntimeLayout
    $transactionId = [Guid]::NewGuid()
    $contextArguments = @{ TransactionId = $transactionId }
    if ($layout.package_root) { $contextArguments.PackageRoot = [string]$layout.package_root }
    $script:Context = Get-IzMaintenanceContext @contextArguments
    $resolvedBackup = Assert-IzExternalRestoreInput -Context $script:Context -Path $BackupPath
    if (-not (Confirm-IzRestore)) {
        Write-Host 'Restore cancelled.'
        $script:ExitCode = 10
    } else {
        Initialize-IzMaintenanceStorage -Context $script:Context | Out-Null
        $script:LockHandle = Enter-IzMaintenanceLock -Context $script:Context -Action Restore -TransactionId $transactionId
        Invoke-IzStopForRestore
        [void](Restore-IzFullBackup -Context $script:Context -BackupPath $resolvedBackup -RuntimeRole $layout.role -Manifest $layout.manifest -Confirmed)
        Remove-IzResolvedRestoreTransaction
        Write-Host 'Encrypted backup restored and semantically verified for this Windows user.' -ForegroundColor Green
    }
} catch {
    $reason = Get-IzSafeRestoreReason -Record $_
    $script:ExitCode = if ($_.Exception.Data.Contains('iz_exit_code')) { [int]$_.Exception.Data['iz_exit_code'] } else { 20 }
    Write-Error "Restore did not complete: $reason" -ErrorAction Continue
} finally {
    if ($script:LockHandle) { Exit-IzMaintenanceLock -LockHandle $script:LockHandle }
}

exit $script:ExitCode
