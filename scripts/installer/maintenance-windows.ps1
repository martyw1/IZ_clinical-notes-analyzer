[CmdletBinding()]
param(
    [string]$Action = 'Status',
    [string]$PackageRoot = '',
    [switch]$NoPause,
    [switch]$NonInteractive,
    [string]$ResultPath = '',
    [switch]$NoRun,
    [Parameter(ValueFromRemainingArguments=$true)][object[]]$RemainingArguments
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$script:CommonModulePath=Join-Path $PSScriptRoot 'maintenance-common.psm1'
if(-not(Test-Path $script:CommonModulePath -PathType Leaf)){throw 'MAINTENANCE_COMMON_MODULE_MISSING'}
Import-Module $script:CommonModulePath -Force

function New-IzDispatcherError {
    param([string]$Reason,[int]$Code=20)
    $exception=[IO.InvalidDataException]::new($Reason)
    $exception.Data['iz_reason']=$Reason
    $exception.Data['iz_exit_code']=$Code
    return $exception
}

function Get-IzDispatcherReason {
    param([Management.Automation.ErrorRecord]$Record)
    if($Record.Exception.Data.Contains('iz_reason')){
        $reason=[string]$Record.Exception.Data['iz_reason']
        if($reason -match '^[A-Z][A-Z0-9_]{0,63}$'){return $reason}
    }
    return 'MAINTENANCE_PREFLIGHT_FAILED'
}

function Write-IzDispatcherResult {
    param([object]$Result,[string]$Path)
    if($Path){
        $safe=Get-IzCanonicalPath $Path -AllowMissingLeaf
        $parent=Get-IzCanonicalPath (Split-Path $safe -Parent)
        if(-not(Test-Path $parent -PathType Container)){throw(New-IzDispatcherError 'RESULT_PARENT_MISSING')}
        Write-IzMaintenanceResult $safe $Result|Out-Null
    }
    return $Result
}

function New-IzDispatcherResult {
    param([string]$RequestedAction,[string]$Status,[int]$Code,[string]$Reason,[string]$StartedUtc)
    $contractAction=if($RequestedAction -in @('AutoInstall','Repair','Uninstall','RemoveData','Recover','Status')){$RequestedAction}else{'Status'}
    return New-IzMaintenanceResult $contractAction $Status $null $null FINISHED $Code $Reason @() $StartedUtc
}

function Invoke-IzMaintenanceStatus {
    param([object]$Context,[string]$StartedUtc)
    $status=Get-IzPendingMaintenanceStatus $Context
    if($status.status -in @('PENDING','RECOVERY_REQUIRED')){
        return New-IzMaintenanceResult Status RECOVERY_REQUIRED $null $(if($status.journal){$status.journal.transaction_id}else{$null}) FINISHED 31 RECOVERY_REQUIRED @() $StartedUtc
    }
    $reason=if($status.status -eq 'COMMITTED'){'COMMITTED'}else{'CLEAN'}
    return New-IzMaintenanceResult Status NO_OP $null $null FINISHED 0 $reason @() $StartedUtc
}

function Invoke-IzMaintenanceAction {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Action,
        [string]$PackageRoot='',
        [switch]$NoPause,
        [switch]$NonInteractive,
        [string]$ResultPath='',
        [object]$Context,
        [object[]]$RemainingArguments=@()
    )
    $started=[DateTime]::UtcNow.ToString('o')
    $requested=$Action
    $requestedPackageRoot=$PackageRoot
    $requestedNoPause=[bool]$NoPause
    $requestedNonInteractive=[bool]$NonInteractive
    $requestedResultPath=$ResultPath
    $requestedContext=$Context
    try{
        [object[]]$normalizedRemainingArguments=@()
        if($null -ne $RemainingArguments){$normalizedRemainingArguments=@($RemainingArguments)}
        if($normalizedRemainingArguments.Count){throw(New-IzDispatcherError 'UNKNOWN_ARGUMENT')}
        if($requested -notin @('AutoInstall','Repair','Uninstall','RemoveData','Recover','Status')){throw(New-IzDispatcherError 'UNKNOWN_ACTION')}
        if($ResultPath){[void](Get-IzCanonicalPath $ResultPath -AllowMissingLeaf)}
        if($Context){Assert-IzMaintenanceContext $Context|Out-Null}
        if($requested -eq 'Status'){
            $statusContext=if($requestedContext){$requestedContext}elseif($requestedPackageRoot){Get-IzMaintenanceContext -PackageRoot $requestedPackageRoot}else{Get-IzMaintenanceContext}
            return Write-IzDispatcherResult (Invoke-IzMaintenanceStatus $statusContext $started) $requestedResultPath
        }
        if($requested -in @('Uninstall','RemoveData')){
            $controller=Join-Path $PSScriptRoot 'uninstall-windows-release.ps1'
            if(-not(Test-Path $controller -PathType Leaf)){throw(New-IzDispatcherError 'REMOVAL_CONTROLLER_MISSING')}
            . $controller -NoRun
            $removalParameters=@{Action=$requested;PackageRoot=$requestedPackageRoot;NoPause=$true;NonInteractive=$requestedNonInteractive;ResultPath=$requestedResultPath}
            if($requestedContext){$removalParameters.Context=$requestedContext;$removalParameters.PackageRoot=''}
            return Invoke-IzWindowsRemoval @removalParameters
        }
        $controller=Join-Path $PSScriptRoot 'install-windows-release.ps1'
        if(-not(Test-Path $controller -PathType Leaf)){throw(New-IzDispatcherError 'INSTALL_CONTROLLER_MISSING')}
        . $controller -NoRun
        $parameters=@{Action=$requested;PackageRoot=$requestedPackageRoot;NoPause=$true;NonInteractive=$requestedNonInteractive;ResultPath=$requestedResultPath}
        if($requestedContext){$parameters.Context=$requestedContext}
        return Invoke-IzWindowsInstall @parameters
    }catch{
        $code=if($_.Exception.Data.Contains('iz_exit_code')){[int]$_.Exception.Data['iz_exit_code']}else{20}
        if($code -notin @(20,21,31)){$code=20}
        $status=if($code -eq 21){'BUSY'}elseif($code -eq 31){'RECOVERY_REQUIRED'}else{'PREFLIGHT_FAILED'}
        $result=New-IzDispatcherResult $requested $status $code (Get-IzDispatcherReason $_) $started
        return Write-IzDispatcherResult $result $requestedResultPath
    }
}

if(-not $NoRun){
    $result=Invoke-IzMaintenanceAction -Action $Action -PackageRoot $PackageRoot -NoPause:$NoPause -NonInteractive:$NonInteractive -ResultPath $ResultPath -RemainingArguments $RemainingArguments
    Write-Host ($result|ConvertTo-Json -Depth 8 -Compress)
    if(-not $NoPause){Write-Host '';Read-Host 'Press Enter to close'|Out-Null}
    exit [int]$result.code
}
