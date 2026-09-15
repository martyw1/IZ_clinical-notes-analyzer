Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'maintenance-paths.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'maintenance-contracts.psm1') -Force

function New-IzLockError {
    param([string]$Reason,[int]$Code=20)
    $exception=[IO.InvalidDataException]::new($Reason)
    $exception.Data['iz_reason']=$Reason
    $exception.Data['iz_exit_code']=$Code
    return $exception
}

function Test-IzLockOwnerRecord {
    param([object]$Context,[object]$Owner)
    [void](Assert-IzExactProperties $Owner @('schema','product_id','owner_sid','scope_id','transaction_id','action','process_id','process_started_utc','lock_token','acquired_utc') 'LOCK_OWNER_INVALID')
    if($Owner.schema -ne 'iz-cna-lock-owner-v1'){throw(New-IzLockError 'UNSUPPORTED_SCHEMA')}
    if($Owner.product_id -ne $Context.product_id -or $Owner.owner_sid -ne $Context.owner_sid -or $Owner.scope_id -ne $Context.scope_id){throw(New-IzLockError 'LOCK_OWNER_IDENTITY_MISMATCH')}
    if($Owner.transaction_id -notmatch '^[0-9a-f]{32}$' -or $Owner.lock_token -notmatch '^[0-9a-f]{32}$' -or $Owner.process_id -isnot [ValueType]){throw(New-IzLockError 'LOCK_OWNER_INVALID')}
    return $true
}

function Enter-IzMaintenanceLock {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][object]$Context,
        [Parameter(Mandatory)][ValidateSet('AutoInstall','Repair','Uninstall','RemoveData','Recover','Backup','Restore')][string]$Action,
        [Parameter(Mandatory)][Guid]$TransactionId
    )
    Assert-IzMaintenanceContext $Context|Out-Null
    if(-not(Test-Path $Context.state_root -PathType Container)){throw(New-IzLockError 'MAINTENANCE_STORAGE_MISSING')}
    $stream=$null
    try {
        $stream=[IO.FileStream]::new($Context.operation_lock_path,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None,1,[IO.FileOptions]::WriteThrough)
    } catch [IO.IOException] { throw(New-IzLockError 'MAINTENANCE_BUSY' 21) }
    try {
        Protect-IzMaintenancePath $Context.operation_lock_path|Out-Null
        if(Test-Path $Context.lock_owner_path){
            try{$previous=Read-IzStrictJsonFile $Context.lock_owner_path 'LOCK_OWNER_MISSING' 'LOCK_OWNER_CORRUPT';[void](Test-IzLockOwnerRecord $Context $previous)}
            catch{$stream.Dispose();throw}
        }
        $token=[Guid]::NewGuid().ToString('N')
        $process=Get-Process -Id $PID
        $owner=[pscustomobject][ordered]@{
            schema='iz-cna-lock-owner-v1';product_id=$Context.product_id;owner_sid=$Context.owner_sid;scope_id=$Context.scope_id
            transaction_id=$TransactionId.ToString('N');action=$Action;process_id=$PID
            process_started_utc=$process.StartTime.ToUniversalTime().ToString('o');lock_token=$token;acquired_utc=[DateTime]::UtcNow.ToString('o')
        }
        [void](Write-IzAtomicJson $Context.lock_owner_path $owner $null)
        $handle=[pscustomobject][ordered]@{schema='iz-cna-maintenance-lock-handle-v1';context=$Context;lock_token=$token;stream=$stream;released=$false}
        $handle.PSObject.TypeNames.Insert(0,'IzCna.MaintenanceLockHandle')
        return $handle
    } catch { if($stream){$stream.Dispose()};throw }
}

function Exit-IzMaintenanceLock {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$LockHandle)
    if($LockHandle.schema -ne 'iz-cna-maintenance-lock-handle-v1' -or -not $LockHandle.stream){throw(New-IzLockError 'LOCK_HANDLE_INVALID')}
    if($LockHandle.released){return}
    try {
        if(Test-Path $LockHandle.context.lock_owner_path){
            $owner=Read-IzStrictJsonFile $LockHandle.context.lock_owner_path 'LOCK_OWNER_MISSING' 'LOCK_OWNER_CORRUPT'
            [void](Test-IzLockOwnerRecord $LockHandle.context $owner)
            if($owner.lock_token -ne $LockHandle.lock_token){throw(New-IzLockError 'LOCK_OWNER_CHANGED')}
            Remove-Item -LiteralPath $LockHandle.context.lock_owner_path -Force
        }
    } finally {
        $LockHandle.stream.Dispose()
        $LockHandle.released=$true
    }
}

Export-ModuleMember -Function Enter-IzMaintenanceLock,Exit-IzMaintenanceLock
