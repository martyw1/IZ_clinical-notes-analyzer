[CmdletBinding()]
param(
    [Alias('OutputDir')]
    [string]$OutputRoot = '',
    [switch]$NoStop,
    [switch]$AssumeYes,
    [switch]$NoPause,
    [switch]$PassThru
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$script:ExitCode = 0
$script:LockHandle = $null
$script:Context = $null

function New-IzEntryPointError {
    param([string]$Reason, [int]$Code = 20)
    $exception = [InvalidOperationException]::new($Reason)
    $exception.Data['iz_reason'] = $Reason
    $exception.Data['iz_exit_code'] = $Code
    return $exception
}

function Get-IzSafeEntryPointReason {
    param([Management.Automation.ErrorRecord]$Record, [string]$Fallback)
    if ($Record.Exception.Data.Contains('iz_reason')) { return [string]$Record.Exception.Data['iz_reason'] }
    return $Fallback
}

function Get-IzPublicRuntimeLayout {
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
    if ($matches.Count -ne 1) { throw (New-IzEntryPointError 'BACKUP_RUNTIME_LAYOUT_INVALID') }
    $selected = $matches[0]
    $manifest = if ($selected.manifest_root) { Read-IzReleaseManifest -PackageRoot $selected.manifest_root } else { $null }
    return [pscustomobject]@{ role = [string]$selected.role; package_root = $selected.package_root; manifest = $manifest }
}

function Assert-IzExternalCandidatePath {
    param([object]$Context, [string]$Path)
    $candidate = Get-IzCanonicalPath -Path $Path -AllowMissingLeaf
    foreach ($root in @($Context.install_root, $Context.data_root, $Context.maintenance_root, $Context.package_root)) {
        if (-not $root) { continue }
        try {
            [void](Assert-IzContainedPath -Path $candidate -Parent $root -AllowEqual -AllowMissingLeaf)
            throw (New-IzEntryPointError 'BACKUP_DESTINATION_OVERLAP')
        } catch {
            if (-not $_.Exception.Data.Contains('iz_reason') -or $_.Exception.Data['iz_reason'] -ne 'PATH_OUTSIDE_SCOPE') { throw }
        }
        try {
            [void](Assert-IzContainedPath -Path $root -Parent $candidate -AllowEqual -AllowMissingLeaf)
            throw (New-IzEntryPointError 'BACKUP_DESTINATION_OVERLAP')
        } catch {
            if (-not $_.Exception.Data.Contains('iz_reason') -or $_.Exception.Data['iz_reason'] -ne 'PATH_OUTSIDE_SCOPE') { throw }
        }
    }
    return $candidate
}

function Confirm-IzBackup {
    if ($AssumeYes) { return $true }
    Write-Host ''
    Write-Host 'This creates an encrypted backup of local clinical data, configuration, and encryption material.' -ForegroundColor Yellow
    Write-Host 'It can be restored only by this Windows user account. Store it according to R3 policy.'
    return ((Read-Host 'Type BACKUP to create the encrypted backup').Trim() -eq 'BACKUP')
}

function Invoke-IzStopForBackup {
    if ($NoStop) { return }
    $stopScript = Join-Path $PSScriptRoot 'stop-windows-local.ps1'
    if (-not (Test-Path -LiteralPath $stopScript -PathType Leaf)) { throw (New-IzEntryPointError 'BACKUP_STOP_HELPER_MISSING') }
    & $stopScript -NoRestartPrompt -NoPause
    if ($LASTEXITCODE -ne 0) { throw (New-IzEntryPointError 'BACKUP_STOP_FAILED') }
}

function Remove-IzResolvedBackupTransaction {
    if (-not $script:Context -or -not (Test-Path -LiteralPath $script:Context.transaction_root)) { return }
    [void](Test-IzOwnedRootMarker -Context $script:Context -Path $script:Context.transaction_root -Role transaction -TransactionId ([Guid]$script:Context.transaction_id))
    Remove-Item -LiteralPath $script:Context.transaction_root -Recurse -Force
}

try {
    $commonModule = Join-Path $PSScriptRoot 'installer\maintenance-common.psm1'
    $backupModule = Join-Path $PSScriptRoot 'installer\backup-verification.psm1'
    if (-not (Test-Path -LiteralPath $commonModule -PathType Leaf) -or -not (Test-Path -LiteralPath $backupModule -PathType Leaf)) {
        throw (New-IzEntryPointError 'BACKUP_HELPER_MISSING')
    }
    Import-Module $commonModule -Force
    Import-Module $backupModule -Force
    $layout = Get-IzPublicRuntimeLayout
    $transactionId = [Guid]::NewGuid()
    $contextArguments = @{ TransactionId = $transactionId }
    if ($layout.package_root) { $contextArguments.PackageRoot = [string]$layout.package_root }
    $script:Context = Get-IzMaintenanceContext @contextArguments
    if (-not (Test-Path -LiteralPath $script:Context.data_root -PathType Container) -or -not (Test-Path -LiteralPath (Join-Path $script:Context.data_root '.env') -PathType Leaf)) {
        throw (New-IzEntryPointError 'BACKUP_PROFILE_MISSING')
    }
    if (-not $OutputRoot) {
        if ([string]::IsNullOrWhiteSpace($env:USERPROFILE)) { throw (New-IzEntryPointError 'BACKUP_OUTPUT_ROOT_REQUIRED') }
        $OutputRoot = Join-Path $env:USERPROFILE 'Documents\IZ Clinical Notes Analyzer Backups'
    }
    $resolvedOutputRoot = Get-IzCanonicalPath -Path $OutputRoot -AllowMissingLeaf
    if ((Test-Path -LiteralPath $resolvedOutputRoot) -and -not (Test-Path -LiteralPath $resolvedOutputRoot -PathType Container)) {
        throw (New-IzEntryPointError 'BACKUP_OUTPUT_ROOT_INVALID')
    }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backupPath = Assert-IzExternalCandidatePath -Context $script:Context -Path (Join-Path $resolvedOutputRoot "IZ-Clinical-Notes-Analyzer-backup-$stamp.izcnabackup")
    if (-not (Confirm-IzBackup)) {
        Write-Host 'Backup cancelled.'
        $script:ExitCode = 10
    } else {
        [IO.Directory]::CreateDirectory($resolvedOutputRoot) | Out-Null
        Initialize-IzMaintenanceStorage -Context $script:Context | Out-Null
        $script:LockHandle = Enter-IzMaintenanceLock -Context $script:Context -Action Backup -TransactionId $transactionId
        Invoke-IzStopForBackup
        $result = New-IzFullBackup -Context $script:Context -DataIdentity $null -RuntimeRole $layout.role -Manifest $layout.manifest -BackupPath $backupPath
        Remove-IzResolvedBackupTransaction
        Write-Host "Encrypted backup created: $($result.Path)" -ForegroundColor Green
        Write-Host 'The backup was decrypted and semantically verified for this Windows user before publication.'
        if ($PassThru) { Write-Output $result }
    }
} catch {
    $reason = Get-IzSafeEntryPointReason -Record $_ -Fallback 'BACKUP_FAILED'
    $script:ExitCode = if ($_.Exception.Data.Contains('iz_exit_code')) { [int]$_.Exception.Data['iz_exit_code'] } else { 20 }
    Write-Error "Backup did not complete: $reason" -ErrorAction Continue
} finally {
    if ($script:LockHandle) { Exit-IzMaintenanceLock -LockHandle $script:LockHandle }
}

exit $script:ExitCode
