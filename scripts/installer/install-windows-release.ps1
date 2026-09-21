[CmdletBinding()]
param(
    [ValidateSet('AutoInstall','Repair','Recover')][string]$Action = 'AutoInstall',
    [string]$PackageRoot = '',
    [switch]$NoPause,
    [switch]$NonInteractive,
    [string]$ResultPath = '',
    [switch]$NoRun
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'maintenance-common.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'maintenance-contracts.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'maintenance-version.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'maintenance-runtime.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'maintenance-transaction.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'backup-verification.psm1') -Force

function New-IzInstallError {
    param([string]$Reason,[int]$Code=20)
    $exception=[IO.InvalidDataException]::new($Reason)
    $exception.Data['iz_reason']=$Reason
    $exception.Data['iz_exit_code']=$Code
    return $exception
}

function Get-IzInstallReason {
    param([Management.Automation.ErrorRecord]$Record,[string]$Fallback='INSTALL_PREFLIGHT_FAILED')
    if($Record.Exception.Data.Contains('iz_reason')){
        $reason=[string]$Record.Exception.Data['iz_reason']
        if($reason -match '^[A-Z][A-Z0-9_]{0,63}$'){return $reason}
    }
    if($Record.Exception.Message -match '^[A-Z][A-Z0-9_]{0,63}$'){return [string]$Record.Exception.Message}
    return $Fallback
}

function New-IzInstallOutcome {
    param([string]$RequestedAction,[string]$Status,[int]$Code,[string]$Reason,[object]$Release,[object]$TransactionId,[string[]]$Evidence,[string]$StartedUtc)
    New-IzMaintenanceResult -Action $RequestedAction -Status $Status -ReleaseIdentity $Release -TransactionId $TransactionId -Stage FINISHED -Code $Code -Reason $Reason -Evidence $Evidence -StartedUtc $StartedUtc
}

function Write-IzInstallOutcome {
    param([object]$Result,[string]$Path)
    if($Path){Write-IzMaintenanceResult -ResultPath $Path -Result $Result|Out-Null}
    return $Result
}

function Write-IzInstallFailureEvidence {
    param(
        [object]$Context,
        [string]$RequestedAction,
        [string]$PrimaryReason,
        [int]$PrimaryCode,
        [AllowNull()][string]$RecoveryReason
    )
    [void](Assert-IzMaintenanceContext $Context)
    if(-not $Context.transaction_id -or $RequestedAction -notin @('AutoInstall','Repair','Recover') -or
       $PrimaryReason -notmatch '^[A-Z][A-Z0-9_]{0,63}$' -or $PrimaryCode -lt 0 -or $PrimaryCode -gt 255 -or
       (-not [string]::IsNullOrEmpty($RecoveryReason) -and $RecoveryReason -notmatch '^[A-Z][A-Z0-9_]{0,63}$')){
        throw(New-IzInstallError 'FAILURE_EVIDENCE_INVALID' 31)
    }
    $relativePath='transactions/'+$Context.transaction_id+'/results/installer-failure.json'
    $path=Assert-IzContainedPath (Join-Path $Context.results_root 'installer-failure.json') $Context.results_root -AllowMissingLeaf
    $now=[DateTime]::UtcNow.ToString('o');$recorded=$now
    if(Test-Path -LiteralPath $path -PathType Leaf){
        $existing=Read-IzStrictJsonFile $path 'FAILURE_EVIDENCE_INVALID' 'FAILURE_EVIDENCE_INVALID'
        [void](Assert-IzExactProperties $existing @('schema','product_id','owner_sid','scope_id','transaction_id','action','primary_reason','primary_code','recovery_reason','recorded_utc','updated_utc') 'FAILURE_EVIDENCE_INVALID')
        if($existing.schema -cne 'iz-cna-install-failure-evidence-v1' -or $existing.product_id -cne $Context.product_id -or
           $existing.owner_sid -cne $Context.owner_sid -or $existing.scope_id -cne $Context.scope_id -or
           $existing.transaction_id -cne $Context.transaction_id -or $existing.action -cne $RequestedAction -or
           $existing.primary_reason -cne $PrimaryReason -or [int]$existing.primary_code -ne $PrimaryCode){
            throw(New-IzInstallError 'FAILURE_EVIDENCE_INVALID' 31)
        }
        $recorded=[string]$existing.recorded_utc
    }
    $value=[pscustomobject][ordered]@{
        schema='iz-cna-install-failure-evidence-v1';product_id=$Context.product_id;owner_sid=$Context.owner_sid
        scope_id=$Context.scope_id;transaction_id=$Context.transaction_id;action=$RequestedAction
        primary_reason=$PrimaryReason;primary_code=$PrimaryCode;recovery_reason=$(if([string]::IsNullOrEmpty($RecoveryReason)){$null}else{$RecoveryReason})
        recorded_utc=$recorded;updated_utc=$now
    }
    [void](Write-IzAtomicJson $path $value $null)
    return [pscustomobject][ordered]@{path=$path;relative_path=$relativePath;value=$value}
}

function Get-IzRelatedContext {
    param([object]$Seed,[Guid]$TransactionId=[Guid]::Empty,[string]$Package='')
    $parameters=@{}
    if($Package){$parameters.PackageRoot=$Package}
    if($TransactionId -ne [Guid]::Empty){$parameters.TransactionId=$TransactionId}
    $component=Split-Path $Seed.local_app_data_root -Parent
    if((Split-Path $component -Leaf)-match '^iz-cna-component-[0-9a-f]{12}$' -and
       (Split-Path $Seed.local_app_data_root -Leaf)-eq 'LocalAppData'){$parameters.ComponentTestRoot=$component}
    return Get-IzMaintenanceContext @parameters
}

function Write-IzStoredManifest {
    param([object]$Context,[object]$Manifest)
    $path=Join-Path $Context.transaction_root 'target-release-manifest.json'
    if(Test-Path $path){throw(New-IzInstallError 'TRANSACTION_ARTIFACT_EXISTS' 31)}
    [IO.File]::WriteAllText($path,($Manifest|ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
    Protect-IzMaintenancePath $path|Out-Null
}

function Read-IzStoredManifest {
    param([object]$Context)
    $path=Join-Path $Context.transaction_root 'target-release-manifest.json'
    if(-not(Test-Path $path -PathType Leaf)){return $null}
    try{$manifest=[IO.File]::ReadAllText($path,[Text.Encoding]::UTF8)|ConvertFrom-Json}
    catch{throw(New-IzInstallError 'STORED_MANIFEST_INVALID' 31)}
    $target=New-IzReleaseIdentity $manifest.version $manifest.build ([int]$manifest.installer_revision) $manifest.payload_identity
    $journal=Read-IzMaintenanceJournal $Context
    [void](Compare-IzReleaseIdentity $target $journal.target_release)
    return $manifest
}

function Close-IzResolvedJournal {
    param([object]$Context,[object]$Journal)
    if($Journal.state -notin @('COMMITTED','ROLLED_BACK')){throw(New-IzInstallError 'JOURNAL_NOT_RESOLVED' 31)}
    [void](Test-IzOwnedRootMarker $Context $Context.transaction_root transaction ([Guid]$Context.transaction_id))
    $archive=Join-Path $Context.transaction_root 'resolved-maintenance-journal.json'
    if(Test-Path $archive){
        if((Get-IzFileSha256 $archive)-cne(Get-IzFileSha256 $Context.journal_path)){throw(New-IzInstallError 'JOURNAL_ARCHIVE_CONFLICT' 31)}
    }else{
        [IO.File]::Copy($Context.journal_path,$archive,$false)
        Protect-IzMaintenancePath $archive|Out-Null
    }
    Remove-Item $Context.journal_path -Force
    if(Test-Path $Context.journal_previous_path){Remove-Item $Context.journal_previous_path -Force}
}

function Get-IzProfileSelection {
    param([object]$Context,[switch]$AllowAbsent)
    $environmentPath=Join-Path $Context.data_root '.env'
    if(-not(Test-Path $environmentPath -PathType Leaf)){
        if($AllowAbsent){return [pscustomobject]@{environment_path=$environmentPath;database_path=(Join-Path $Context.data_root 'clinical-notes-analyzer.sqlite3')}}
        throw(New-IzInstallError 'DATA_ENVIRONMENT_MISSING')
    }
    if((Get-Item $environmentPath).Length -gt 1048576){throw(New-IzInstallError 'DATA_ENVIRONMENT_INVALID')}
    try{$lines=[IO.File]::ReadAllLines((Get-IzCanonicalPath $environmentPath),[Text.UTF8Encoding]::new($false,$true))}
    catch{throw(New-IzInstallError 'DATA_ENVIRONMENT_INVALID')}
    foreach($binding in @(
        @('IZ_CNA_ENV_FILE',$environmentPath,'ENVIRONMENT_PATH_CONFLICT'),
        @('IZ_CNA_LOCAL_APP_DATA_DIR',$Context.data_root,'DATA_ROOT_CONFLICT')
    )){
        $configured=@()
        $processValue=[Environment]::GetEnvironmentVariable($binding[0],'Process')
        if(-not[string]::IsNullOrWhiteSpace($processValue)){$configured+=@($processValue.Trim().Trim('"').Trim("'"))}
        foreach($line in $lines){if($line-match('^\s*'+$binding[0]+'\s*=\s*(.*?)\s*$')){$configured+=@(([string]$Matches[1]).Trim().Trim('"').Trim("'"))}}
        foreach($value in @($configured|Where-Object{$_})){
            if(-not[IO.Path]::IsPathRooted($value)-or(Get-IzCanonicalPath $value -AllowMissingLeaf)-ine(Get-IzCanonicalPath $binding[1] -AllowMissingLeaf)){
                throw(New-IzInstallError $binding[2])
            }
        }
    }
    $values=[Collections.Generic.List[string]]::new()
    foreach($name in @('IZ_CNA_LOCAL_SQLITE_DB_PATH','LOCAL_SQLITE_DB_PATH')){
        $processValue=[Environment]::GetEnvironmentVariable($name,'Process')
        if(-not[string]::IsNullOrWhiteSpace($processValue)){$values.Add($processValue.Trim().Trim('"').Trim("'"))}
        foreach($line in $lines){
            if($line -match ('^\s*'+$name+'\s*=\s*(.*?)\s*$')){
                $value=([string]$Matches[1]).Trim().Trim('"').Trim("'")
                if($value){$values.Add($value)}
            }
        }
    }
    $paths=[Collections.Generic.List[string]]::new()
    foreach($value in $values){
        $candidate=if([IO.Path]::IsPathRooted($value)){$value}else{Join-Path $Context.data_root $value}
        $candidate=Assert-IzContainedPath $candidate $Context.data_root -AllowMissingLeaf
        if(-not($paths|Where-Object{$_.Equals($candidate,[StringComparison]::OrdinalIgnoreCase)})){$paths.Add($candidate)}
    }
    if($paths.Count -gt 1){throw(New-IzInstallError 'DATABASE_SELECTION_AMBIGUOUS')}
    if($paths.Count -eq 1){$database=$paths[0]}
    else{
        $candidates=@(Get-ChildItem $Context.data_root -File -Filter '*.sqlite3' -ErrorAction SilentlyContinue)
        if($candidates.Count -ne 1){throw(New-IzInstallError 'DATABASE_SELECTION_AMBIGUOUS')}
        $database=$candidates[0].FullName
    }
    if(-not(Test-Path $database -PathType Leaf)){throw(New-IzInstallError 'DATABASE_FILE_MISSING')}
    return [pscustomobject]@{environment_path=(Get-IzCanonicalPath $environmentPath);database_path=(Get-IzCanonicalPath $database)}
}

function Get-IzTreePayloadIdentity {
    param([string]$Root)
    $records=@(Get-ChildItem $Root -File -Recurse -Force|ForEach-Object{
        $path=Get-IzCanonicalPath $_.FullName
        [pscustomobject]@{path=$path.Substring($Root.Length+1).Replace('\','/');length=[long]$_.Length;sha256=(Get-IzFileSha256 $path)}
    }|Sort-Object path)
    $canonical=@($records|ForEach-Object{([string]$_.path)+[char]9+$_.length+[char]9+$_.sha256+[char]10})-join''
    return Get-IzUtf8Sha256 $canonical
}

function Read-IzLegacyProgramInventory {
    param([object]$Context,[object]$Manifest,[object]$Source)
    $relativePath='installer/legacy-program-inventory.json'
    $manifestRecords=@($Manifest.files|Where-Object{$_.path -ceq $relativePath})
    if($manifestRecords.Count -ne 1){throw(New-IzInstallError 'LEGACY_INVENTORY_BINDING_INVALID')}
    $path=Assert-IzContainedPath (Join-Path $Context.package_root $relativePath.Replace('/','\')) $Context.package_root
    $item=Get-Item -LiteralPath $path -Force
    if($item.PSIsContainer -or ($item.Attributes-band[IO.FileAttributes]::ReparsePoint) -ne 0 -or
       [long]$item.Length -gt 16777216L -or [long]$item.Length -ne [long]$manifestRecords[0].length -or
       (Get-IzFileSha256 $path)-cne[string]$manifestRecords[0].sha256){
        throw(New-IzInstallError 'LEGACY_INVENTORY_BINDING_INVALID')
    }
    $inventory=Read-IzStrictJsonFile $path 'LEGACY_INVENTORY_MISSING' 'LEGACY_INVENTORY_INVALID'
    [void](Assert-IzExactProperties $inventory @('schema','product_id','sources') 'LEGACY_INVENTORY_INVALID')
    if($inventory.schema -cne 'iz-cna-legacy-program-inventory-v1' -or
       $inventory.product_id -cne $Context.product_id){throw(New-IzInstallError 'LEGACY_INVENTORY_INVALID')}
    $expected=@(
        [pscustomobject]@{archive_name='IZ-Clinical-Notes-Analyzer-v2.0.0-beta.3.zip';archive_length=43716351L;archive_sha256='9c5fd47203242e1a21df612f719f1c14fa4240c86ba869f924ec4690834fc89c';version='2.0.0-beta.3';build='2026.09.03.1'},
        [pscustomobject]@{archive_name='IZ-Clinical-Notes-Analyzer-v2.0.0-beta.4.zip';archive_length=43873389L;archive_sha256='67b83eea402566658dea6d64ac6cba37a192a7d1bd670cf560541324c0092b14';version='2.0.0-beta.4';build='2026.09.10.2'}
    )
    $sources=@($inventory.sources)
    if($sources.Count -ne $expected.Count){throw(New-IzInstallError 'LEGACY_INVENTORY_INVALID')}
    $selected=$null
    for($sourceIndex=0;$sourceIndex -lt $expected.Count;$sourceIndex++){
        $candidate=$sources[$sourceIndex];$descriptor=$expected[$sourceIndex]
        [void](Assert-IzExactProperties $candidate @('archive_name','archive_length','archive_sha256','version','build','files') 'LEGACY_INVENTORY_INVALID')
        foreach($name in @('archive_name','archive_sha256','version','build')){
            if($candidate.$name -isnot [string] -or $candidate.$name -cne $descriptor.$name){throw(New-IzInstallError 'LEGACY_INVENTORY_INVALID')}
        }
        if([long]$candidate.archive_length -ne [long]$descriptor.archive_length){throw(New-IzInstallError 'LEGACY_INVENTORY_INVALID')}
        $files=@($candidate.files)
        if($files.Count -lt 3 -or $files.Count -gt 10000){throw(New-IzInstallError 'LEGACY_INVENTORY_INVALID')}
        $keys=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        $previous=$null
        foreach($file in $files){
            [void](Assert-IzExactProperties $file @('path','length','sha256') 'LEGACY_INVENTORY_INVALID')
            if($file.path -isnot [string] -or $file.path.Length -gt 1024 -or $file.path.Contains('//') -or
               $file.path.IndexOf([char]0) -ge 0 -or (ConvertTo-IzRelativePath $file.path 'LEGACY_INVENTORY_INVALID') -cne $file.path -or
               [long]$file.length -lt 0 -or $file.sha256 -isnot [string] -or $file.sha256 -notmatch '^[0-9a-f]{64}$' -or
               -not $keys.Add([string]$file.path) -or ($previous -and [StringComparer]::Ordinal.Compare($previous,[string]$file.path) -ge 0)){
                throw(New-IzInstallError 'LEGACY_INVENTORY_INVALID')
            }
            $previous=[string]$file.path
        }
        if($candidate.version -ceq $Source.release.version -and $candidate.build -ceq $Source.release.build){$selected=$files}
    }
    if($null -eq $selected){throw(New-IzInstallError 'LEGACY_VERSION_UNSUPPORTED')}
    return @($selected)
}

function Get-IzSourceState {
    param([object]$Context)
    $hasProgram=Test-Path $Context.install_root -PathType Container
    $hasData=Test-Path $Context.data_root -PathType Container
    $hasReceipt=Test-Path $Context.install_receipt_path -PathType Leaf
    $receipt=if($hasReceipt){Read-IzInstallReceipt $Context}else{$null}
    if($hasReceipt -and -not $hasData){throw(New-IzInstallError 'DATA_ROOT_MISSING')}
    if(-not $hasProgram -and -not $hasData -and -not $hasReceipt){
        return [pscustomobject]@{mode='fresh';receipt=$null;release=$null;prior_receipt_sha256=$null;profile=(Get-IzProfileSelection $Context -AllowAbsent);data_identity=$null}
    }
    if(-not $hasData){throw(New-IzInstallError 'DATA_ROOT_MISSING')}
    $profile=Get-IzProfileSelection $Context
    $identity=New-IzDataIdentity $Context $profile.database_path
    if($receipt -and $identity.data_identity -cne $receipt.data_identity){throw(New-IzInstallError 'DATA_IDENTITY_MISMATCH')}
    if(-not $hasProgram){
        if(-not $receipt){throw(New-IzInstallError 'DATA_OWNERSHIP_UNPROVEN')}
        $release=New-IzReleaseIdentity $receipt.version $receipt.build ([int]$receipt.installer_revision) $receipt.payload_identity
        return [pscustomobject]@{mode='reinstall';receipt=$receipt;release=$release;prior_receipt_sha256=(Get-IzFileSha256 $Context.install_receipt_path);profile=$profile;data_identity=$identity}
    }
    foreach($required in @('runtime\IZClinicalNotesAnalyzer.exe','frontend\dist\index.html','VERSION.json')){
        if(-not(Test-Path (Join-Path $Context.install_root $required) -PathType Leaf)){throw(New-IzInstallError 'LEGACY_PROGRAM_INVALID')}
    }
    if($receipt){
        $release=New-IzReleaseIdentity $receipt.version $receipt.build ([int]$receipt.installer_revision) $receipt.payload_identity
        return [pscustomobject]@{mode='owned';receipt=$receipt;release=$release;prior_receipt_sha256=(Get-IzFileSha256 $Context.install_receipt_path);profile=$profile;data_identity=$identity}
    }
    try{$metadata=[IO.File]::ReadAllText((Join-Path $Context.install_root 'VERSION.json'),[Text.Encoding]::UTF8)|ConvertFrom-Json}
    catch{throw(New-IzInstallError 'LEGACY_VERSION_INVALID')}
    if(-not(($metadata.version -ceq '2.0.0-beta.3' -and $metadata.build -ceq '2026.09.03.1')-or
            ($metadata.version -ceq '2.0.0-beta.4' -and $metadata.build -ceq '2026.09.10.2'))){throw(New-IzInstallError 'LEGACY_VERSION_UNSUPPORTED')}
    $release=New-IzReleaseIdentity $metadata.version $metadata.build 0 (Get-IzTreePayloadIdentity $Context.install_root)
    return [pscustomobject]@{mode='legacy';receipt=$null;release=$release;prior_receipt_sha256=$null;profile=$profile;data_identity=$identity}
}

function Test-IzReceiptProgramMatches {
    param([object]$Context,[object]$Receipt)
    foreach($file in @($Receipt.owned_files)){
        $path=Assert-IzContainedPath (Join-Path $Context.install_root $file.path.Replace('/','\')) $Context.install_root -AllowMissingLeaf
        if(-not(Test-Path $path -PathType Leaf)-or(Get-Item $path).Length-ne[long]$file.length-or(Get-IzFileSha256 $path)-cne$file.sha256){return $false}
    }
    return $true
}

function New-IzLegacyAdoptionReceipt {
    param([object]$Context,[object]$Source,[object]$Manifest,[Guid]$CurrentTransaction)
    if($Source.mode -cne 'legacy' -or $Source.receipt){throw(New-IzInstallError 'LEGACY_ADOPTION_INVALID')}
    $owned=[Collections.Generic.List[object]]::new()
    $required=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach($relative in @('runtime/IZClinicalNotesAnalyzer.exe','frontend/dist/index.html','VERSION.json')){[void]$required.Add($relative)}
    $matched=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach($record in @(Read-IzLegacyProgramInventory $Context $Manifest $Source)){
        $path=Assert-IzContainedPath (Join-Path $Context.install_root $record.path.Replace('/','\')) $Context.install_root -AllowMissingLeaf
        if(-not(Test-Path -LiteralPath $path -PathType Leaf)){continue}
        $item=Get-Item -LiteralPath $path -Force
        if(($item.Attributes-band[IO.FileAttributes]::ReparsePoint) -ne 0){throw(New-IzInstallError 'LEGACY_PROGRAM_INVALID')}
        if([long]$item.Length -eq [long]$record.length -and (Get-IzFileSha256 $path)-ceq[string]$record.sha256){
            $owned.Add([pscustomobject][ordered]@{path=[string]$record.path;length=[long]$record.length;sha256=[string]$record.sha256})
            [void]$matched.Add([string]$record.path)
        }
    }
    if(@($required|Where-Object{-not $matched.Contains($_)}).Count){throw(New-IzInstallError 'LEGACY_PROGRAM_INVALID')}
    do{$priorTransaction=[Guid]::NewGuid()}while($priorTransaction -eq $CurrentTransaction)
    $receipt=New-IzInstallReceipt $Context $Source.data_identity.data_identity $Source.release @($owned.ToArray()) @() $priorTransaction
    Write-IzInstallReceipt $Context $receipt $null|Out-Null
    return [pscustomobject]@{receipt=$receipt;sha256=(Get-IzFileSha256 $Context.install_receipt_path)}
}

function New-IzRandomSecret {
    $bytes=New-Object byte[] 48
    $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
    try{$rng.GetBytes($bytes);return [Convert]::ToBase64String($bytes)}
    finally{$rng.Dispose();[Array]::Clear($bytes,0,$bytes.Length)}
}

function New-IzFreshProfile {
    param([object]$Context,[object]$Profile)
    if(Test-Path $Context.data_root){throw(New-IzInstallError 'FRESH_DATA_ROOT_EXISTS')}
    [IO.Directory]::CreateDirectory($Context.data_root)|Out-Null
    Protect-IzMaintenancePath $Context.data_root|Out-Null
    $port=Get-IzConfiguredRuntimePort $Context
    $lines=@(
        'APP_NAME=IZ Clinical Notes Analyzer','ENVIRONMENT=local-client',('BACKEND_PORT='+$port),'FRONTEND_PORT=5173',
        'DATABASE_BACKEND=sqlite','LOCAL_SQLITE_DB_PATH=clinical-notes-analyzer.sqlite3','DATABASE_URL=',
        ('SECRET_KEY='+(New-IzRandomSecret)),('DATA_ENCRYPTION_KEY='+(New-IzRandomSecret)),
        ('FRONTEND_ORIGIN=http://localhost:'+$port),('FRONTEND_ORIGINS=http://localhost:'+$port+',http://localhost:5173'),
        'ALLOWED_HOSTS=localhost,127.0.0.1,::1,testserver','UPLOAD_DIR=uploads','LOG_DIR=logs',
        ('RULES_CONFIG_PATH='+$Context.install_root+'\config\rules\alleva_treatment_plan_completeness_rules.yaml'),
        'BOOTSTRAP_ADMIN_USERNAME=admin','BOOTSTRAP_ADMIN_PASSWORD=r3mar123ABC','RESET_BOOTSTRAP_ADMIN_ON_STARTUP=false',
        'LLM_ENABLED=false','EMR_API_ENABLED=false'
    )
    [IO.File]::WriteAllText($Profile.environment_path,($lines-join([string][char]10))+[char]10,[Text.UTF8Encoding]::new($false))
    $identity=New-IzDataIdentity $Context $Profile.database_path
    Register-IzFreshDataRoot $Context $identity.data_identity|Out-Null
    return $identity
}

function ConvertTo-IzProcessArgument {
    param([string]$Value)
    if($Value -notmatch '[\s"]'){return $Value}
    $result='"';$slashes=0
    foreach($character in $Value.ToCharArray()){
        if($character -eq '\'){$slashes++;continue}
        if($character -eq '"'){$result+=('\'*(2*$slashes+1))+'"';$slashes=0;continue}
        if($slashes){$result+=('\'*$slashes);$slashes=0}
        $result+=$character
    }
    if($slashes){$result+=('\'*(2*$slashes))}
    return $result+'"'
}

function Invoke-IzInstalledDataVerification {
    param([object]$Context,[object]$Manifest,[string]$DatabasePath)
    $requestPath=Join-Path $Context.requests_root 'candidate-verify.json'
    $resultPath=Join-Path $Context.results_root 'candidate-verify.json'
    $request=New-IzVerifyDataRequest $Context (Join-Path $Context.data_root '.env') $DatabasePath
    [IO.File]::WriteAllText($requestPath,($request|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
    Protect-IzMaintenancePath $requestPath|Out-Null
    if(Test-Path $resultPath){throw(New-IzInstallError 'RUNTIME_RESULT_PREEXISTED' 31)}
    $spec=Get-IzRuntimeCommandSpec $Context Installed VerifyData $requestPath $resultPath $Manifest
    $start=[Diagnostics.ProcessStartInfo]::new()
    $start.FileName=$spec.file_path;$start.UseShellExecute=$false;$start.CreateNoWindow=$true
    $start.Arguments = (@($spec.arguments | ForEach-Object { ConvertTo-IzProcessArgument ([string]$_) }) -join ' ')
    if($spec.working_directory){$start.WorkingDirectory=$spec.working_directory}
    foreach($name in @('IZ_CNA_LOCAL_SQLITE_DB_PATH','LOCAL_SQLITE_DB_PATH')){
        if($start.EnvironmentVariables.ContainsKey($name)){$start.EnvironmentVariables.Remove($name)}
    }
    $start.EnvironmentVariables['IZ_CNA_ENV_FILE']=Join-Path $Context.data_root '.env'
    $start.EnvironmentVariables['IZ_CNA_LOCAL_APP_DATA_DIR']=$Context.data_root
    $start.EnvironmentVariables['IZ_CNA_LOCAL_SQLITE_DB_PATH']=$DatabasePath
    $process=[Diagnostics.Process]::Start($start)
    if(-not $process.WaitForExit(120000)){try{$process.Kill()}catch{};throw(New-IzInstallError 'DATA_VERIFICATION_TIMEOUT' 31)}
    if($process.ExitCode -ne 0){throw(New-IzInstallError 'DATA_VERIFICATION_FAILED' 31)}
    $result=Read-IzRuntimeMaintenanceResult $resultPath VerifyData
    if($result.status -ne 'success' -or $result.sqlite_integrity -cne 'ok' -or [int]$result.foreign_key_violations -ne 0 -or
       [int]$result.encrypted_payloads_checked -ne [int]$result.encrypted_payloads_valid){throw(New-IzInstallError 'DATA_VERIFICATION_FAILED' 31)}
    return $result
}

function Test-IzExistingShortcutOwnership {
    param([object]$Context,[string]$Location,[string]$Name,[object]$PriorReceipt)
    $base=if($Location -eq 'start_menu'){$Context.start_menu_root}else{$Context.desktop_root}
    $path=Assert-IzContainedPath (Join-Path $base $Name) $base -AllowMissingLeaf
    if(-not(Test-Path $path -PathType Leaf)){return}
    $record=$null
    if($PriorReceipt){$record=@($PriorReceipt.owned_shortcuts|Where-Object{$_.location -eq $Location -and $_.name -eq $Name}|Select-Object -First 1)}
    $shell=New-Object -ComObject WScript.Shell
    $actual=$shell.CreateShortcut($path)
    if($record){
        $expected=if($record.target_kind -eq 'installed_relative'){Join-Path $Context.install_root $record.target_relative_path}else{Join-Path $env:SystemRoot $record.target_relative_path}
        if((Get-IzCanonicalPath $actual.TargetPath -AllowMissingLeaf) -ine (Get-IzCanonicalPath $expected -AllowMissingLeaf) -or
           (Get-IzUtf8Sha256 ([string]$actual.Arguments)) -cne $record.arguments_sha256){throw(New-IzInstallError 'SHORTCUT_OWNERSHIP_UNPROVEN')}
    }else{
        $target=Get-IzCanonicalPath $actual.TargetPath -AllowMissingLeaf
        if(-not $target.StartsWith($Context.install_root.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase) -or [string]$actual.Arguments){
            throw(New-IzInstallError 'SHORTCUT_OWNERSHIP_UNPROVEN')
        }
    }
}

function Get-IzRemovalArguments {
    param([object]$Context,[object]$Manifest,[ValidateSet('Uninstall','RemoveData')][string]$RemovalAction)
    $relative='installer/Remove-IZ-Clinical-Notes-Analyzer.bootstrap.ps1'
    $record=@($Manifest.files|Where-Object{$_.path -ceq $relative})
    if($record.Count -ne 1){throw(New-IzInstallError 'BOOTSTRAP_MANIFEST_RECORD_MISSING')}
    $bootstrap=Join-Path $Context.install_root $relative.Replace('/','\')
    if((Get-IzFileSha256 $bootstrap) -cne $record[0].sha256){throw(New-IzInstallError 'BOOTSTRAP_HASH_MISMATCH')}
    $digest=[string]$record[0].sha256
    $loader=@(
        "$" + "k=[Environment]::GetFolderPath('LocalApplicationData','DoNotVerify')",
        "if(!$" + "k){throw 'KNOWN_FOLDER_UNAVAILABLE'}",
        "$" + "k=[IO.Path]::GetFullPath($" + "k).TrimEnd('\')",
        "if($" + "env:LOCALAPPDATA -and [IO.Path]::GetFullPath($" + "env:LOCALAPPDATA).TrimEnd('\') -ine $" + "k){throw 'KNOWN_FOLDER_OVERRIDE_CONFLICT'}",
        "$" + "p=Join-Path $" + "k 'Programs\IZ Clinical Notes Analyzer\installer\Remove-IZ-Clinical-Notes-Analyzer.bootstrap.ps1'",
        "if(!(Test-Path -LiteralPath $" + "p -PathType Leaf)){throw 'BOOTSTRAP_MISSING'}",
        "$" + "c=[IO.Path]::GetPathRoot($" + "p)",
        "foreach($" + "s in $" + "p.Substring($" + "c.Length).Split('\')){if($" + "s){$" + "c=Join-Path $" + "c $" + "s;if((Get-Item -LiteralPath $" + "c -Force).Attributes -band 1024){throw 'BOOTSTRAP_REPARSE'}}}",
        "if((Get-FileHash -LiteralPath $" + "p -Algorithm SHA256).Hash.ToLowerInvariant() -cne '$digest'){throw 'BOOTSTRAP_HASH_MISMATCH'}",
        "$" + "r=Split-Path $" + "p",
        ". $" + "p -NoRun -SourceRoot $" + "r",
        "$" + "x=Invoke-IzRemovalBootstrap -Action '$RemovalAction' -SourceRoot $" + "r -SourceKind Installed",
        "exit [int]$" + "x"
    )-join ';'
    $arguments='-NoP -EP Bypass -C "'+$loader+'"'
    if($arguments.Length -gt 1023){throw(New-IzInstallError 'SHORTCUT_ARGUMENTS_TOO_LONG')}
    return $arguments
}

function New-IzInstalledShortcuts {
    param([object]$Context,[object]$Manifest,[object]$PriorReceipt)
    $definitions=[Collections.Generic.List[object]]::new()
    $definitions.Add([pscustomobject]@{location='start_menu';name='IZ Clinical Notes Analyzer/IZ Clinical Notes Analyzer.lnk';target_kind='installed_relative';target='scripts/launch-packaged-runtime.cmd';arguments=''})
    $definitions.Add([pscustomobject]@{location='desktop';name='IZ Clinical Notes Analyzer.lnk';target_kind='installed_relative';target='scripts/launch-packaged-runtime.cmd';arguments=''})
    foreach($entry in @(
        @('Stop IZ Clinical Notes Analyzer.lnk','scripts/Stop-IZ-Clinical-Notes-Analyzer.cmd'),
        @('IZ Clinical Notes Analyzer Diagnostics.lnk','scripts/Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd'),
        @('Backup IZ Clinical Notes Analyzer.lnk','scripts/Backup-IZ-Clinical-Notes-Analyzer.cmd'),
        @('Restore IZ Clinical Notes Analyzer.lnk','scripts/Restore-IZ-Clinical-Notes-Analyzer.cmd')
    )){
        if(Test-Path (Join-Path $Context.install_root $entry[1]) -PathType Leaf){
            $definitions.Add([pscustomobject]@{location='start_menu';name=('IZ Clinical Notes Analyzer/'+$entry[0]);target_kind='installed_relative';target=$entry[1];arguments=''})
        }
    }
    foreach($removal in @(@('Uninstall IZ Clinical Notes Analyzer.lnk','Uninstall'),@('Complete Uninstall IZ Clinical Notes Analyzer.lnk','RemoveData'))){
        $definitions.Add([pscustomobject]@{location='start_menu';name=('IZ Clinical Notes Analyzer/'+$removal[0]);target_kind='system_powershell';target='System32\WindowsPowerShell\v1.0\powershell.exe';arguments=(Get-IzRemovalArguments $Context $Manifest $removal[1])})
    }
    $records=@();$shell=New-Object -ComObject WScript.Shell
    foreach($definition in $definitions){
        Test-IzExistingShortcutOwnership $Context $definition.location $definition.name $PriorReceipt
        $base=if($definition.location -eq 'start_menu'){$Context.start_menu_root}else{$Context.desktop_root}
        $path=Assert-IzContainedPath (Join-Path $base $definition.name) $base -AllowMissingLeaf
        [IO.Directory]::CreateDirectory((Split-Path $path -Parent))|Out-Null
        $target=if($definition.target_kind -eq 'installed_relative'){Join-Path $Context.install_root $definition.target}else{Join-Path $env:SystemRoot $definition.target}
        if(-not(Test-Path $target -PathType Leaf)){throw(New-IzInstallError 'SHORTCUT_TARGET_MISSING')}
        $shortcut=$shell.CreateShortcut($path)
        $shortcut.TargetPath=$target;$shortcut.Arguments=$definition.arguments;$shortcut.WorkingDirectory=$Context.install_root;$shortcut.Save()
        $records += [pscustomobject][ordered]@{location=$definition.location;name=$definition.name;target_kind=$definition.target_kind;target_relative_path=$definition.target;arguments_sha256=(Get-IzUtf8Sha256 $definition.arguments)}
    }
    return @($records)
}

function Invoke-IzRecoveryForJournal {
    param([object]$Seed,[object]$Journal,[object]$IncomingManifest,[string]$Package)
    $context=Get-IzRelatedContext $Seed ([Guid]$Journal.transaction_id) $Package
    $manifest=$null
    if($IncomingManifest){
        $incoming=New-IzReleaseIdentity $IncomingManifest.version $IncomingManifest.build ([int]$IncomingManifest.installer_revision) $IncomingManifest.payload_identity
        try{if((Compare-IzReleaseIdentity $incoming $Journal.target_release) -eq 0){$manifest=$IncomingManifest}}catch{}
    }
    if(-not $manifest){$manifest=Read-IzStoredManifest $context}
    return [pscustomobject]@{context=$context;recovery=(Invoke-IzInstallRecovery $context $Journal $manifest)}
}

function Confirm-IzRestoredRuntime {
    param([object]$Context,[object]$Journal)
    if(-not $Journal.source_release -or -not(Test-Path $Context.install_root -PathType Container)){
        return [pscustomobject]@{status='no_program'}
    }
    $pending=Get-IzPendingMaintenanceStatus $Context
    if($pending.status -ne 'PENDING' -or $pending.journal.state -ne 'ROLLED_BACK' -or $pending.authority.launch_policy -ne 'source'){
        throw(New-IzInstallError 'RESTORED_RUNTIME_AUTHORITY_INVALID' 31)
    }
    $source=$pending.journal.source_release
    if([int]$source.installer_revision -eq 0){
        return Start-IzLegacyRuntime $Context $source -TimeoutSeconds 120
    }
    return Start-IzOwnedRuntime $Context Installed -TimeoutSeconds 120 -NoBrowser
}

function Invoke-IzWindowsInstall {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidateSet('AutoInstall','Repair','Recover')][string]$Action,
        [string]$PackageRoot='',
        [switch]$NoPause,
        [switch]$NonInteractive,
        [string]$ResultPath='',
        [object]$Context
    )
    $started=[DateTime]::UtcNow.ToString('o')
    $target=$null;$transactionId=$null;$lock=$null;$journal=$null;$manifest=$null;$work=$null;$committed=$false
    try{
        if($Action -ne 'Recover' -and -not $PackageRoot){throw(New-IzInstallError 'PACKAGE_ROOT_REQUIRED')}
        $seed=if($Context){Assert-IzMaintenanceContext $Context}else{Get-IzMaintenanceContext -PackageRoot $PackageRoot}
        $package=if($PackageRoot){Get-IzCanonicalPath $PackageRoot}else{[string]$seed.package_root}
        if($package){
            $manifest=Read-IzReleaseManifest $package
            [void](Test-IzReleasePayload $package $manifest)
            $target=New-IzReleaseIdentity $manifest.version $manifest.build ([int]$manifest.installer_revision) $manifest.payload_identity
        }
        $base=Get-IzRelatedContext $seed ([Guid]::Empty) $package
        $pending=Get-IzPendingMaintenanceStatus $base
        if($pending.status -eq 'RECOVERY_REQUIRED' -and -not $pending.journal){throw(New-IzInstallError 'RECOVERY_REQUIRED' 31)}
        if($Action -eq 'Recover'){
            if($pending.status -eq 'CLEAN'){
                return Write-IzInstallOutcome (New-IzInstallOutcome $Action NO_OP 0 NO_PENDING_TRANSACTION $null $null @() $started) $ResultPath
            }
            $journal=$pending.journal;$transactionId=[Guid]$journal.transaction_id
            $work=Get-IzRelatedContext $seed $transactionId $package
            $lock=Enter-IzMaintenanceLock $work Recover $transactionId
            if($journal.state -in @('COMMITTED','ROLLED_BACK')){
                return Write-IzInstallOutcome (New-IzInstallOutcome $Action NO_OP 0 TRANSACTION_ALREADY_RESOLVED $journal.target_release $transactionId @() $started) $ResultPath
            }
            $resolved=Invoke-IzRecoveryForJournal $seed $journal $manifest $package
            if($resolved.recovery.status -eq 'rolled_back'){
                try{[void](Confirm-IzRestoredRuntime $resolved.context $resolved.recovery.journal)}
                catch{return Write-IzInstallOutcome (New-IzInstallOutcome $Action RECOVERY_REQUIRED 31 RESTORED_RUNTIME_VALIDATION_FAILED $journal.target_release $transactionId @('transactions/'+$journal.transaction_id) $started) $ResultPath}
                return Write-IzInstallOutcome (New-IzInstallOutcome $Action ROLLED_BACK 30 ROLLBACK_VALIDATED $journal.target_release $transactionId @('transactions/'+$journal.transaction_id) $started) $ResultPath
            }
            return Write-IzInstallOutcome (New-IzInstallOutcome $Action RECOVERY_REQUIRED 31 $resolved.recovery.reason $journal.target_release $transactionId @('transactions/'+$journal.transaction_id) $started) $ResultPath
        }

        $transactionId=if($Context -and $Context.transaction_id){[Guid]$Context.transaction_id}else{[Guid]::NewGuid()}
        $work=Get-IzRelatedContext $seed $transactionId $package
        Initialize-IzMaintenanceStorage $work|Out-Null
        $lock=Enter-IzMaintenanceLock $work $Action $transactionId
        $pending=Get-IzPendingMaintenanceStatus $base
        if($pending.status -ne 'CLEAN'){
            if(-not $pending.journal){throw(New-IzInstallError 'RECOVERY_REQUIRED' 31)}
            $oldJournal=$pending.journal
            $oldContext=Get-IzRelatedContext $seed ([Guid]$oldJournal.transaction_id) $package
            if($oldJournal.state -in @('COMMITTED','ROLLED_BACK')){Close-IzResolvedJournal $oldContext $oldJournal}
            else{
                $resolved=Invoke-IzRecoveryForJournal $seed $oldJournal $manifest $package
                if($resolved.recovery.status -ne 'rolled_back'){throw(New-IzInstallError $resolved.recovery.reason 31)}
                Close-IzResolvedJournal $resolved.context $resolved.recovery.journal
            }
        }

        $source=Get-IzSourceState $work
        $effectiveAction=$Action
        if($source.release){
            $comparison=Compare-IzReleaseIdentity $source.release $target
            if($comparison -gt 0 -and (Test-IzProductionVersionTransition $source.release $manifest)){$comparison=-1}
            if($comparison -gt 0){throw(New-IzInstallError 'DOWNGRADE_BLOCKED')}
            if($Action -eq 'Repair' -and $comparison -ne 0){throw(New-IzInstallError 'REPAIR_VERSION_MISMATCH')}
            if($comparison -eq 0 -and $source.mode -eq 'owned'){
                if($Action -ne 'Repair' -and (Test-IzReceiptProgramMatches $work $source.receipt)){
                    [void](Start-IzOwnedRuntime $work Installed -TimeoutSeconds 120 -NoBrowser:$NonInteractive)
                    return Write-IzInstallOutcome (New-IzInstallOutcome $Action NO_OP 0 ALREADY_CURRENT $target $transactionId @() $started) $ResultPath
                }
                $effectiveAction='Repair'
            }
            if($comparison -lt 0){[void](Test-IzReleaseCompatibility $source.release ([int]$manifest.compatibility.source_schema_minimum) $manifest)}
        }

        if($source.mode -eq 'legacy'){
            $adoption=New-IzLegacyAdoptionReceipt $work $source $manifest $transactionId
            $source.receipt=$adoption.receipt
            $source.prior_receipt_sha256=$adoption.sha256
        }

        Write-IzStoredManifest $work $manifest
        $dataIdentity=if($source.data_identity){$source.data_identity.data_identity}else{$null}
        $journal=New-IzMaintenanceJournal $work $effectiveAction $source.release $target $dataIdentity $target.payload_identity $source.prior_receipt_sha256
        $previousBinding=Initialize-IzPreviousProgramBinding $work $journal $source.receipt
        if($previousBinding){
            foreach($property in $previousBinding.journal_patch.PSObject.Properties){$journal.program.($property.Name)=$property.Value}
        }
        Write-IzMaintenanceJournal $work $journal -1|Out-Null
        if($source.mode -eq 'fresh'){
            $fresh=New-IzFreshProfile $work $source.profile;$dataIdentity=$fresh.data_identity
            $next=New-IzMaintenanceTransition $journal PREPARING @() ([pscustomobject]@{data_identity=$dataIdentity})
            Write-IzMaintenanceJournal $work $next $journal.sequence|Out-Null;$journal=$next
        }

        $stage=Copy-IzStagedProgram $work $manifest
        $next=New-IzMaintenanceTransition $journal PAYLOAD_VERIFIED @('PAYLOAD_STAGED','PAYLOAD_VERIFIED') ([pscustomobject]@{program=$stage.journal_patch})
        Write-IzMaintenanceJournal $work $next $journal.sequence|Out-Null;$journal=$next
        $stop=Stop-IzOwnedRuntime $work -TimeoutSeconds 30 -AllowLegacyFallback
        if($stop.status -eq 'failure'){throw(New-IzInstallError $stop.reason)}
        $next=New-IzMaintenanceTransition $journal QUIESCED @('RUNTIME_QUIESCED')
        Write-IzMaintenanceJournal $work $next $journal.sequence|Out-Null;$journal=$next

        if($source.mode -ne 'fresh'){
            $backup=New-IzFullBackup $work $source.data_identity Candidate $manifest $work.snapshot_path
            if(-not $backup.verified -or $backup.data_identity -cne $dataIdentity){throw(New-IzInstallError 'SNAPSHOT_VERIFICATION_FAILED')}
            [void](Test-IzReleaseCompatibility $source.release ([int]$backup.schema_version) $manifest -Repair:($effectiveAction -eq 'Repair' -or $source.mode -eq 'reinstall'))
            $snapshot=[pscustomobject][ordered]@{format='IZCNABK2';relative_path='snapshot/pre-change.izcnabackup';length=[long]$backup.length;sha256=$backup.sha256;data_identity=$backup.data_identity;source_identity_hash=$backup.source_identity_hash;profile_snapshot_identity=$backup.profile_snapshot_identity;verified=$true}
            $next=New-IzMaintenanceTransition $journal SNAPSHOT_VERIFIED @('SNAPSHOT_CREATED','SNAPSHOT_VERIFIED') ([pscustomobject]@{snapshot=$snapshot})
        }else{$next=New-IzMaintenanceTransition $journal SNAPSHOT_VERIFIED}
        Write-IzMaintenanceJournal $work $next $journal.sequence|Out-Null;$journal=$next

        $journal=Invoke-IzProgramSwap $work $journal $stage $source.receipt
        $next=New-IzMaintenanceTransition $journal VALIDATING
        Write-IzMaintenanceJournal $work $next $journal.sequence|Out-Null;$journal=$next
        $candidate=Start-IzOwnedRuntime $work Candidate $transactionId -TimeoutSeconds 120 -NoBrowser
        $next=New-IzMaintenanceTransition $journal VALIDATING @('CANDIDATE_STARTED')
        Write-IzMaintenanceJournal $work $next $journal.sequence|Out-Null;$journal=$next
        [void](Test-IzRuntimeHttpSurface $work $candidate.identity $target $manifest)
        $verified=Invoke-IzInstalledDataVerification $work $manifest $source.profile.database_path
        if($verified.data_identity -cne $dataIdentity -or [int]$verified.schema_version -ne [int]$manifest.compatibility.target_schema){
            throw(New-IzInstallError 'CANDIDATE_DATA_IDENTITY_MISMATCH' 31)
        }
        $next=New-IzMaintenanceTransition $journal VALIDATING @('CANDIDATE_VALIDATED')
        Write-IzMaintenanceJournal $work $next $journal.sequence|Out-Null;$journal=$next

        $shortcuts=New-IzInstalledShortcuts $work $manifest $source.receipt
        $ownedFiles=@($stage.files|ForEach-Object{[pscustomobject][ordered]@{path=$_.path;length=[long]$_.length;sha256=$_.sha256}})
        $receipt=New-IzInstallReceipt $work $dataIdentity $target $ownedFiles $shortcuts $transactionId
        Write-IzInstallReceipt $work $receipt $source.prior_receipt_sha256|Out-Null
        $next=New-IzMaintenanceTransition $journal VALIDATING @('INSTALL_RECEIPT_WRITTEN')
        Write-IzMaintenanceJournal $work $next $journal.sequence|Out-Null;$journal=$next
        $next=New-IzMaintenanceTransition $journal COMMITTED @('COMMIT_RECORDED')
        Write-IzMaintenanceJournal $work $next $journal.sequence|Out-Null;$journal=$next;$committed=$true

        $commit=Invoke-IzRuntimeControl $work commit $transactionId $candidate.identity 5
        if($commit.status -cne 'ok' -or $commit.reason -cne 'committed' -or $commit.gate -cne 'open' -or [bool]$commit.draining){
            throw(New-IzInstallError 'COMMIT_ACKNOWLEDGEMENT_FAILED' 31)
        }
        $cleanupEvidence=@()
        try{Remove-IzCommittedProgramArtifacts $work $journal}
        catch{$cleanupEvidence=@('transactions/'+$work.transaction_id+'/program-previous.json')}
        if(-not $NonInteractive){Start-Process ('http://127.0.0.1:{0}/' -f [int]$candidate.identity.port)|Out-Null}
        $reason=if($cleanupEvidence.Count){'INSTALL_COMMITTED_CLEANUP_PENDING'}else{'INSTALL_COMMITTED'}
        return Write-IzInstallOutcome (New-IzInstallOutcome $Action SUCCEEDED 0 $reason $target $transactionId $cleanupEvidence $started) $ResultPath
    }catch{
        $reason=Get-IzInstallReason $_
        $code=if($_.Exception.Data.Contains('iz_exit_code')){[int]$_.Exception.Data['iz_exit_code']}else{20}
        if($journal -and -not $committed){
            $failureArtifact=$null
            try{$failureArtifact=Write-IzInstallFailureEvidence $work $Action $reason $code $null}catch{}
            $recovery=Invoke-IzInstallRecovery $work $journal $manifest
            if($recovery.status -eq 'rolled_back'){
                try{[void](Confirm-IzRestoredRuntime $work $recovery.journal)}
                catch{
                    $restoredRuntimeReason=Get-IzInstallReason $_ 'RESTORED_RUNTIME_VALIDATION_FAILED'
                    try{$failureArtifact=Write-IzInstallFailureEvidence $work $Action $reason $code $restoredRuntimeReason}catch{}
                    $evidence=@('transactions/'+$work.transaction_id);if($failureArtifact -and (Test-Path -LiteralPath $failureArtifact.path -PathType Leaf)){$evidence+=@($failureArtifact.relative_path)}
                    return Write-IzInstallOutcome (New-IzInstallOutcome $Action RECOVERY_REQUIRED 31 $reason $target $transactionId $evidence $started) $ResultPath
                }
                try{$failureArtifact=Write-IzInstallFailureEvidence $work $Action $reason $code ROLLBACK_VALIDATED}catch{}
                $evidence=@('transactions/'+$work.transaction_id);if($failureArtifact -and (Test-Path -LiteralPath $failureArtifact.path -PathType Leaf)){$evidence+=@($failureArtifact.relative_path)}
                return Write-IzInstallOutcome (New-IzInstallOutcome $Action ROLLED_BACK 30 $reason $target $transactionId $evidence $started) $ResultPath
            }
            try{$failureArtifact=Write-IzInstallFailureEvidence $work $Action $reason $code ([string]$recovery.reason)}catch{}
            $evidence=@('transactions/'+$work.transaction_id);if($failureArtifact -and (Test-Path -LiteralPath $failureArtifact.path -PathType Leaf)){$evidence+=@($failureArtifact.relative_path)}
            return Write-IzInstallOutcome (New-IzInstallOutcome $Action RECOVERY_REQUIRED 31 $reason $target $transactionId $evidence $started) $ResultPath
        }
        if($committed){$code=31;$reason='COMMIT_ACKNOWLEDGEMENT_FAILED'}
        $status=if($code -eq 21){'BUSY'}elseif($code -eq 31){'RECOVERY_REQUIRED'}else{'PREFLIGHT_FAILED'}
        return Write-IzInstallOutcome (New-IzInstallOutcome $Action $status $code $reason $target $transactionId @() $started) $ResultPath
    }finally{
        if($lock){try{Exit-IzMaintenanceLock $lock}catch{}}
    }
}

if(-not $NoRun){
    $result=Invoke-IzWindowsInstall -Action $Action -PackageRoot $PackageRoot -NoPause:$NoPause -NonInteractive:$NonInteractive -ResultPath $ResultPath
    Write-Host ($result|ConvertTo-Json -Depth 8 -Compress)
    if(-not $NoPause){Write-Host '';Read-Host 'Press Enter to close'|Out-Null}
    exit [int]$result.code
}
