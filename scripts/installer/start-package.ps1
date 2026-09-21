[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SourceRoot,
    [ValidateSet('AutoInstall','Repair','Recover','Uninstall','RemoveData')][string]$Action='AutoInstall',
    [switch]$NoPause,
    [switch]$NonInteractive,
    [string]$ResultPath='',
    [switch]$AssumeYes,
    [Parameter(ValueFromRemainingArguments=$true)][object[]]$RemainingArguments
)
Set-StrictMode -Version 2.0
$ErrorActionPreference='Stop'
$stage=$null
$exitCode=20
$originalLocation=Get-Location
$requestedAction=$Action
$requestedNoPause=$NoPause
$requestedNonInteractive=$NonInteractive
$requestedResultPath=$ResultPath
$requestedAssumeYes=$AssumeYes
$startedUtc=[DateTime]::UtcNow.ToString('o')
try {
    Import-Module (Join-Path $PSScriptRoot 'maintenance-common.psm1') -Force
    if (@($RemainingArguments | Where-Object { $null -ne $_ }).Count) { throw 'UNKNOWN_ARGUMENT' }
    Import-Module (Join-Path $PSScriptRoot 'package-source.psm1') -Force
    $stage=New-IzPackageStage $SourceRoot
    if ($Action -in @('Uninstall','RemoveData')) {
        $dispatchOptions=@{Action=$requestedAction;SourceRoot=(Join-Path $stage.package_root 'installer');SourceKind='Package';NoPause=$true;NonInteractive=$requestedNonInteractive;ResultPath=$requestedResultPath;AssumeYes=$requestedAssumeYes}
        $result=& { . (Join-Path $stage.package_root 'installer\Remove-IZ-Clinical-Notes-Analyzer.bootstrap.ps1') -NoRun; Invoke-IzRemovalBootstrap @dispatchOptions }
    } else {
        if ($AssumeYes) { throw 'UNKNOWN_ARGUMENT' }
        $dispatchOptions=@{Action=$requestedAction;PackageRoot=$stage.package_root;NoPause=$true;NonInteractive=$requestedNonInteractive;ResultPath=$requestedResultPath}
        $result=& { . (Join-Path $stage.package_root 'installer\maintenance-windows.ps1') -NoRun; Invoke-IzMaintenanceAction @dispatchOptions }
    }
    $exitCode=[int]$result.code
    Write-Host ($result | ConvertTo-Json -Depth 8 -Compress)
} catch {
    $reason=if ($_.Exception.Data.Contains('iz_reason')) { [string]$_.Exception.Data['iz_reason'] } elseif ($_.Exception.Message -cmatch '^[A-Z][A-Z0-9_]{0,63}$') { $_.Exception.Message } else { 'PACKAGE_PREPARATION_FAILED' }
    Write-Host ('[fail] '+$reason)
    $result=New-IzMaintenanceResult $requestedAction PREFLIGHT_FAILED $null $null FINISHED 20 $reason @() $startedUtc
    if ($requestedResultPath) { [void](Write-IzMaintenanceResult $requestedResultPath $result) }
    Write-Host ($result | ConvertTo-Json -Depth 8 -Compress)
    Write-Host 'Extract the complete ZIP and keep its files together. Cloud files must be available on this device.'
} finally {
    Set-Location $originalLocation
    if ($stage -and -not (Remove-IzPackageStage $stage)) { Write-Host '[warn] Temporary package cleanup was incomplete; local app data was not removed.' }
}
if (-not $requestedNoPause) { Write-Host ''; [void](Read-Host 'Press Enter to close') }
exit $exitCode
