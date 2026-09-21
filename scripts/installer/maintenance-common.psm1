Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'maintenance-paths.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'maintenance-version.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'maintenance-contracts.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'maintenance-lock.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'maintenance-journal.psm1') -Force

function New-IzCommonError {
    param([string]$Reason,[int]$Code=20)
    $exception=[IO.InvalidDataException]::new($Reason);$exception.Data['iz_reason']=$Reason;$exception.Data['iz_exit_code']=$Code;return $exception
}

function Initialize-IzMaintenanceStorage {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Context)
    Assert-IzMaintenanceContext $Context|Out-Null
    $directories=@($Context.local_app_data_root,$Context.maintenance_root,$Context.state_root,$Context.transactions_root)
    if($Context.transaction_id){
        $directories+=@($Context.transaction_root,(Join-Path $Context.transaction_root 'snapshot'),$Context.verification_root,$Context.requests_root,$Context.results_root)
    }
    foreach($directory in $directories){
        if(-not(Test-Path -LiteralPath $directory)){[IO.Directory]::CreateDirectory($directory)|Out-Null}
        if(-not(Test-Path -LiteralPath $directory -PathType Container)){throw(New-IzCommonError 'MAINTENANCE_STORAGE_INVALID')}
        Protect-IzMaintenancePath $directory|Out-Null
    }
    $maintenanceMarker=Join-Path $Context.maintenance_root '.iz-cna-owned-root.json'
    if(Test-Path $maintenanceMarker){[void](Test-IzOwnedRootMarker $Context $Context.maintenance_root maintenance)}else{[void](Write-IzOwnedRootMarker $Context $Context.maintenance_root maintenance)}
    if($Context.transaction_id){
        $tx=[Guid]$Context.transaction_id
        foreach($entry in @(@($Context.transaction_root,'transaction'),@($Context.verification_root,'verification'))){
            $marker=Join-Path $entry[0] '.iz-cna-owned-root.json'
            if(Test-Path $marker){[void](Test-IzOwnedRootMarker $Context $entry[0] $entry[1] $tx)}else{[void](Write-IzOwnedRootMarker $Context $entry[0] $entry[1] $tx)}
        }
    }
    return $Context
}

function New-IzDatabaseSnapshotRequest {
    [CmdletBinding()]
    param([object]$Context,[string]$EnvironmentFile,[string]$SourceDatabasePath)
    Assert-IzMaintenanceContext $Context|Out-Null
    if(-not $Context.transaction_id){throw(New-IzCommonError 'TRANSACTION_ID_REQUIRED')}
    [void](Test-IzOwnedRootMarker $Context $Context.transaction_root transaction ([Guid]$Context.transaction_id))
    $environment=Get-IzCanonicalPath $EnvironmentFile
    if(-not $environment.Equals((Join-Path $Context.data_root '.env'),[StringComparison]::OrdinalIgnoreCase)){throw(New-IzCommonError 'ENVIRONMENT_PATH_INVALID')}
    $database=Assert-IzContainedPath $SourceDatabasePath $Context.data_root
    $snapshotDatabase=Join-Path $Context.transaction_root 'snapshot\selected-database.sqlite3'
    [void](Assert-IzContainedPath $snapshotDatabase $Context.transaction_root -AllowMissingLeaf)
    if(Test-Path $snapshotDatabase){throw(New-IzCommonError 'SNAPSHOT_DATABASE_EXISTS')}
    return [pscustomobject][ordered]@{schema='iz-cna-database-snapshot-request-v1';data_root=$Context.data_root;environment_file=$environment;source_database_path=$database;owned_output_root=$Context.transaction_root;snapshot_database_path=$snapshotDatabase}
}

function New-IzVerifyDataRequest {
    [CmdletBinding()]
    param([object]$Context,[string]$EnvironmentFile,[string]$ExpectedDatabasePath)
    Assert-IzMaintenanceContext $Context|Out-Null
    $environment=Get-IzCanonicalPath $EnvironmentFile
    if((Split-Path $environment -Leaf) -ne '.env'){throw(New-IzCommonError 'ENVIRONMENT_PATH_INVALID')}
    $dataRoot=Get-IzCanonicalPath (Split-Path $environment -Parent)
    $restoreRoot=$Context.data_root+'.restore-'+$Context.transaction_id
    $allowed=$dataRoot.Equals($Context.data_root,[StringComparison]::OrdinalIgnoreCase) -or $dataRoot.Equals($restoreRoot,[StringComparison]::OrdinalIgnoreCase)
    if(-not $allowed -and $Context.verification_root){
        try{[void](Test-IzOwnedRootMarker $Context $Context.verification_root verification ([Guid]$Context.transaction_id));[void](Assert-IzContainedPath $dataRoot $Context.verification_root -AllowEqual);$allowed=$true}catch{$allowed=$false}
    }
    if(-not $allowed){throw(New-IzCommonError 'VERIFY_DATA_ROOT_INVALID')}
    $database=if([string]::IsNullOrEmpty($ExpectedDatabasePath)){''}else{Assert-IzContainedPath $ExpectedDatabasePath $dataRoot}
    return [pscustomobject][ordered]@{schema='iz-cna-data-verification-request-v1';data_root=$dataRoot;environment_file=$environment;expected_database_path=$database}
}

function Read-IzRuntimeMaintenanceResult {
    [CmdletBinding()]
    param([string]$Path,[ValidateSet('SnapshotDatabase','VerifyData','InspectData')][string]$Operation)
    $value=Read-IzStrictJsonFile $Path 'RUNTIME_RESULT_MISSING' 'RUNTIME_RESULT_CORRUPT'
    $schema=@{SnapshotDatabase='iz-cna-database-snapshot-v1';VerifyData='iz-cna-data-verification-v1';InspectData='iz-cna-data-inspection-v1'}[$Operation]
    if($value.schema -ne $schema){throw(New-IzCommonError 'UNSUPPORTED_SCHEMA')}
    if($value.status -eq 'failed'){
        [void](Assert-IzExactProperties $value @('schema','operation','status','reason') 'RUNTIME_RESULT_INVALID')
        if($value.reason -notmatch '^[a-z][a-z0-9_]{0,63}$'){throw(New-IzCommonError 'RUNTIME_RESULT_INVALID')}
        return $value
    }
    $expected=@('schema','operation','status','reason','data_identity','source_identity_hash','profile_snapshot_identity','environment_sha256','database_relative_path','database_sha256','sqlite_integrity','foreign_key_violations','schema_version','safe_counts','encrypted_payloads_checked','encrypted_payloads_valid')
    if($Operation -eq 'SnapshotDatabase'){$expected+=@('snapshot_sha256')}
    [void](Assert-IzExactProperties $value $expected 'RUNTIME_RESULT_INVALID')
    if($value.status -ne 'success' -or $value.reason -notmatch '^[a-z][a-z0-9_]{0,63}$'){throw(New-IzCommonError 'RUNTIME_RESULT_INVALID')}
    foreach($name in @('data_identity','source_identity_hash','profile_snapshot_identity','environment_sha256','database_sha256')){if($value.$name -notmatch '^[0-9a-f]{64}$'){throw(New-IzCommonError 'RUNTIME_RESULT_INVALID')}}
    if($Operation -eq 'SnapshotDatabase' -and $value.snapshot_sha256 -notmatch '^[0-9a-f]{64}$'){throw(New-IzCommonError 'RUNTIME_RESULT_INVALID')}
    foreach($name in @('foreign_key_violations','schema_version','encrypted_payloads_checked','encrypted_payloads_valid')){if($value.$name -isnot [ValueType] -or [long]$value.$name -lt 0){throw(New-IzCommonError 'RUNTIME_RESULT_INVALID')}}
    return $value
}

function Get-IzRuntimeCommandSpec {
    [CmdletBinding()]
    param([object]$Context,[ValidateSet('Installed','Package','Candidate','SourceTest')][string]$RuntimeRole,[ValidateSet('SnapshotDatabase','VerifyData')][string]$Operation,[string]$RequestPath,[string]$ResultPath,[AllowNull()][object]$Manifest)
    Assert-IzMaintenanceContext $Context|Out-Null
    $request=Assert-IzContainedPath $RequestPath $Context.requests_root
    $result=Assert-IzContainedPath $ResultPath $Context.results_root -AllowMissingLeaf
    if($RuntimeRole -eq 'SourceTest'){
        if(-not $Context.package_root){throw(New-IzCommonError 'SOURCE_LAYOUT_INVALID')}
        $backend=Join-Path $Context.package_root 'backend';$python=Join-Path $backend '.venv\Scripts\python.exe';$versionPath=Join-Path $Context.package_root 'VERSION.json'
        if(-not(Test-Path $python -PathType Leaf)-or -not(Test-Path $versionPath -PathType Leaf)-or $Manifest){throw(New-IzCommonError 'SOURCE_LAYOUT_INVALID')}
        [void](Read-IzStrictJsonFile $versionPath 'SOURCE_VERSION_MISSING' 'SOURCE_VERSION_INVALID')
        $arguments=@('-m','app.desktop_runtime','maintenance',$(if($Operation -eq 'SnapshotDatabase'){'snapshot-database'}else{'verify-data'}),'--request',$request,'--result',$result)
        return [pscustomobject][ordered]@{file_path=(Get-IzCanonicalPath $python);arguments=$arguments;working_directory=(Get-IzCanonicalPath $backend)}
    }
    if(-not $Manifest){throw(New-IzCommonError 'MANIFEST_REQUIRED')}
    $root=switch($RuntimeRole){Installed{$Context.install_root};Package{Join-Path $Context.package_root 'app'};Candidate{$Context.stage_root}}
    if(-not $root){throw(New-IzCommonError 'RUNTIME_LAYOUT_INVALID')}
    $exe=Join-Path $root 'runtime\IZClinicalNotesAnalyzer.exe';$canonical=Get-IzCanonicalPath $exe
    $relative='app/runtime/IZClinicalNotesAnalyzer.exe';$record=@($Manifest.files|Where-Object{$_.path -eq $relative})
    if($record.Count -ne 1 -or [long]$record[0].length -ne (Get-Item $canonical).Length -or $record[0].sha256 -ne (Get-IzFileSha256 $canonical)){throw(New-IzCommonError 'RUNTIME_MANIFEST_MISMATCH')}
    $arguments=@('maintenance',$(if($Operation -eq 'SnapshotDatabase'){'snapshot-database'}else{'verify-data'}),'--request',$request,'--result',$result)
    return [pscustomobject][ordered]@{file_path=$canonical;arguments=$arguments;working_directory=$null}
}

$exports=@(
 'Assert-IzPathSyntax','ConvertTo-IzManifest',
 'Get-IzCurrentUserSid','Get-IzMaintenanceContext','Initialize-IzMaintenanceStorage','Get-IzCanonicalPath','Assert-IzCurrentUserOwner','Assert-IzContainedPath','Assert-IzMaintenanceContext','Protect-IzMaintenancePath','Assert-IzExternalBackupDestination','Get-IzExternalBackupPublicationPaths','Get-IzFileSha256','Get-IzUtf8Sha256',
 'New-IzOwnedRootMarker','Write-IzOwnedRootMarker','Read-IzOwnedRootMarker','Test-IzOwnedRootMarker','New-IzProgramInventory','Read-IzProgramInventory','Test-IzProgramInventory','New-IzDataIdentity',
 'Assert-IzExactProperties','Read-IzStrictJsonFile','ConvertTo-IzSemanticVersion','ConvertTo-IzBuildVersion','New-IzReleaseIdentity','Compare-IzReleaseIdentity','Test-IzReleaseCompatibility','Test-IzProductionVersionTransition','Read-IzReleaseManifest','Test-IzReleasePayload','New-IzInstallReceipt','ConvertTo-IzInstallReceipt','Read-IzInstallReceipt','Write-IzInstallReceipt',
 'Enter-IzMaintenanceLock','Exit-IzMaintenanceLock','New-IzMaintenanceJournal','Read-IzMaintenanceJournal','Read-IzResolvedMaintenanceJournal','Write-IzMaintenanceJournal','New-IzMaintenanceTransition','Get-IzMaintenanceAuthority','Get-IzPendingMaintenanceStatus',
 'New-IzMaintenanceResult','Read-IzMaintenanceResult','Write-IzMaintenanceResult','New-IzDatabaseSnapshotRequest','New-IzVerifyDataRequest','Read-IzRuntimeMaintenanceResult','Get-IzRuntimeCommandSpec'
)
Export-ModuleMember -Function $exports
