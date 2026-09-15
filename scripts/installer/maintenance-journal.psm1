Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'maintenance-paths.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'maintenance-version.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'maintenance-contracts.psm1') -Force

$script:States=@('PREPARING','PAYLOAD_VERIFIED','QUIESCED','SNAPSHOT_VERIFIED','SWAP_INTENT','OLD_MOVED','NEW_MOVED','VALIDATING','COMMITTED','ROLLBACK_INTENT','ROLLED_BACK','RECOVERY_REQUIRED')
$script:Steps=@('PAYLOAD_STAGED','PAYLOAD_VERIFIED','RUNTIME_QUIESCED','SNAPSHOT_CREATED','SNAPSHOT_VERIFIED','OLD_MOVE_INTENT_RECORDED','OLD_PROGRAM_MOVED','NEW_MOVE_INTENT_RECORDED','NEW_PROGRAM_MOVED','CANDIDATE_STARTED','CANDIDATE_VALIDATED','INSTALL_RECEIPT_WRITTEN','COMMIT_RECORDED','ROLLBACK_INTENT_RECORDED','CANDIDATE_STOPPED','DATA_RESTORE_INTENT_RECORDED','DATA_RESTORED','PROGRAM_RESTORE_INTENT_RECORDED','OLD_PROGRAM_RESTORED','OLD_RECEIPT_RESTORED','ROLLBACK_VALIDATED')
$script:ProgramFields=@('stage_payload_identity','stage_inventory_relative_path','stage_inventory_sha256','stage_marker_sha256','previous_payload_identity','previous_inventory_relative_path','previous_inventory_sha256','previous_marker_sha256','active_payload_identity')
$script:Transitions=@{
    PREPARING=@('PREPARING','PAYLOAD_VERIFIED','ROLLBACK_INTENT','RECOVERY_REQUIRED')
    PAYLOAD_VERIFIED=@('QUIESCED','ROLLBACK_INTENT','RECOVERY_REQUIRED')
    QUIESCED=@('SNAPSHOT_VERIFIED','ROLLBACK_INTENT','RECOVERY_REQUIRED')
    SNAPSHOT_VERIFIED=@('SWAP_INTENT','ROLLBACK_INTENT','RECOVERY_REQUIRED')
    SWAP_INTENT=@('OLD_MOVED','ROLLBACK_INTENT','RECOVERY_REQUIRED')
    OLD_MOVED=@('OLD_MOVED','NEW_MOVED','ROLLBACK_INTENT','RECOVERY_REQUIRED')
    NEW_MOVED=@('VALIDATING','ROLLBACK_INTENT','RECOVERY_REQUIRED')
    VALIDATING=@('VALIDATING','COMMITTED','ROLLBACK_INTENT','RECOVERY_REQUIRED')
    ROLLBACK_INTENT=@('ROLLBACK_INTENT','ROLLED_BACK','RECOVERY_REQUIRED')
    RECOVERY_REQUIRED=@('RECOVERY_REQUIRED','ROLLBACK_INTENT')
    COMMITTED=@()
    ROLLED_BACK=@()
}

function New-IzJournalError {
    param([string]$Reason,[int]$Code=31)
    $exception=[IO.InvalidDataException]::new($Reason);$exception.Data['iz_reason']=$Reason;$exception.Data['iz_exit_code']=$Code;return $exception
}

function ConvertTo-IzReleaseOrNull {
    param([AllowNull()][object]$Value)
    if($null -eq $Value){return $null}
    try{return Assert-IzReleaseIdentityObject $Value}catch{throw(New-IzJournalError 'JOURNAL_RELEASE_INVALID')}
}

function ConvertTo-IzJournalSnapshot {
    param([AllowNull()][object]$Value)
    if($null -eq $Value){return $null}
    [void](Assert-IzExactProperties $Value @('format','relative_path','length','sha256','data_identity','source_identity_hash','profile_snapshot_identity','verified') 'JOURNAL_SNAPSHOT_INVALID')
    if($Value.format -ne 'IZCNABK2' -or $Value.relative_path -isnot [string] -or [long]$Value.length -lt 0 -or
        $Value.sha256 -notmatch '^[0-9a-f]{64}$' -or $Value.data_identity -notmatch '^[0-9a-f]{64}$' -or
        $Value.source_identity_hash -notmatch '^[0-9a-f]{64}$' -or $Value.profile_snapshot_identity -notmatch '^[0-9a-f]{64}$' -or $Value.verified -isnot [bool]){
        throw(New-IzJournalError 'JOURNAL_SNAPSHOT_INVALID')
    }
    [void](ConvertTo-IzRelativePath $Value.relative_path 'JOURNAL_SNAPSHOT_INVALID');return $Value
}

function ConvertTo-IzJournalProgram {
    param([object]$Value)
    [void](Assert-IzExactProperties $Value $script:ProgramFields 'JOURNAL_PROGRAM_INVALID')
    foreach($name in $script:ProgramFields){
        $item=$Value.$name
        if($null -ne $item -and ($item -isnot [string] -or ($name -like '*sha256' -or $name -like '*identity') -and $item -notmatch '^[0-9a-f]{64}$')){throw(New-IzJournalError 'JOURNAL_PROGRAM_INVALID')}
        if($item -and $name -like '*relative_path'){[void](ConvertTo-IzRelativePath $item 'JOURNAL_PROGRAM_INVALID')}
    }
    return $Value
}

function ConvertTo-IzMaintenanceJournal {
    param([object]$Context,[object]$Value)
    [void](Assert-IzMaintenanceContext $Context)
    [void](Assert-IzExactProperties $Value @('schema','product_id','owner_sid','scope_id','transaction_id','action','state','sequence','created_utc','updated_utc','source_release','target_release','data_identity','payload_identity','prior_receipt_sha256','snapshot','program','completed_steps') 'JOURNAL_INVALID')
    if($Value.schema -ne 'iz-cna-maintenance-journal-v1'){throw(New-IzJournalError 'UNSUPPORTED_SCHEMA')}
    if($Value.product_id -ne $Context.product_id -or $Value.owner_sid -ne $Context.owner_sid -or $Value.scope_id -ne $Context.scope_id -or
       $Value.transaction_id -notmatch '^[0-9a-f]{32}$' -or ($Context.transaction_id -and $Value.transaction_id -ne $Context.transaction_id)){throw(New-IzJournalError 'JOURNAL_IDENTITY_MISMATCH')}
    if($Value.action -notin @('AutoInstall','Repair','Uninstall','RemoveData','Recover','Backup','Restore') -or $Value.state -notin $script:States -or $Value.sequence -isnot [ValueType] -or [long]$Value.sequence -lt 0){throw(New-IzJournalError 'JOURNAL_INVALID')}
    [void](ConvertTo-IzReleaseOrNull $Value.source_release);[void](ConvertTo-IzReleaseOrNull $Value.target_release)
    foreach($name in @('data_identity','payload_identity','prior_receipt_sha256')){if($null -ne $Value.$name -and ($Value.$name -isnot [string] -or $Value.$name -notmatch '^[0-9a-f]{64}$')){throw(New-IzJournalError 'JOURNAL_INVALID')}}
    [void](ConvertTo-IzJournalSnapshot $Value.snapshot);[void](ConvertTo-IzJournalProgram $Value.program)
    $seen=@{};foreach($step in @($Value.completed_steps)){if($step -notin $script:Steps -or $seen.ContainsKey($step)){throw(New-IzJournalError 'JOURNAL_STEPS_INVALID')};$seen[$step]=$true}
    return $Value
}

function New-IzMaintenanceJournal {
    [CmdletBinding()]
    param([object]$Context,[ValidateSet('AutoInstall','Repair','Uninstall','RemoveData','Recover','Backup','Restore')][string]$Action,[AllowNull()][object]$SourceRelease,[AllowNull()][object]$TargetRelease,[AllowNull()][object]$DataIdentity,[AllowNull()][object]$PayloadIdentity,[AllowNull()][object]$PriorReceiptSha256)
    Assert-IzMaintenanceContext $Context|Out-Null;if(-not $Context.transaction_id){throw(New-IzJournalError 'TRANSACTION_ID_REQUIRED' 20)}
    $program=[pscustomobject][ordered]@{stage_payload_identity=$null;stage_inventory_relative_path=$null;stage_inventory_sha256=$null;stage_marker_sha256=$null;previous_payload_identity=$null;previous_inventory_relative_path=$null;previous_inventory_sha256=$null;previous_marker_sha256=$null;active_payload_identity=$null}
    $now=[DateTime]::UtcNow.ToString('o')
    $dataValue=if($null -eq $DataIdentity){$null}else{[string]$DataIdentity};$payloadValue=if($null -eq $PayloadIdentity){$null}else{[string]$PayloadIdentity};$receiptValue=if($null -eq $PriorReceiptSha256){$null}else{[string]$PriorReceiptSha256}
    $journal=[pscustomobject][ordered]@{schema='iz-cna-maintenance-journal-v1';product_id=$Context.product_id;owner_sid=$Context.owner_sid;scope_id=$Context.scope_id;transaction_id=$Context.transaction_id;action=$Action;state='PREPARING';sequence=[long]0;created_utc=$now;updated_utc=$now;source_release=(ConvertTo-IzReleaseOrNull $SourceRelease);target_release=(ConvertTo-IzReleaseOrNull $TargetRelease);data_identity=$dataValue;payload_identity=$payloadValue;prior_receipt_sha256=$receiptValue;snapshot=$null;program=$program;completed_steps=@()}
    return ConvertTo-IzMaintenanceJournal $Context $journal
}

function Read-IzMaintenanceJournal {
    param([object]$Context)
    try{$value=Read-IzStrictJsonFile $Context.journal_path 'JOURNAL_MISSING' 'JOURNAL_CORRUPT'}catch{if($_.Exception.Data['iz_reason']){throw};throw(New-IzJournalError 'JOURNAL_CORRUPT')}
    return ConvertTo-IzMaintenanceJournal $Context $value
}

function Read-IzResolvedMaintenanceJournal {
    param([object]$Context)
    [void](Assert-IzMaintenanceContext $Context)
    if(-not $Context.transaction_id){throw(New-IzJournalError 'TRANSACTION_ID_REQUIRED')}
    $path=Assert-IzContainedPath (Join-Path $Context.transaction_root 'resolved-maintenance-journal.json') $Context.transaction_root
    try{$value=Read-IzStrictJsonFile $path 'JOURNAL_MISSING' 'JOURNAL_CORRUPT'}catch{if($_.Exception.Data['iz_reason']){throw};throw(New-IzJournalError 'JOURNAL_CORRUPT')}
    $journal=ConvertTo-IzMaintenanceJournal $Context $value
    if($journal.state -notin @('COMMITTED','ROLLED_BACK')){throw(New-IzJournalError 'JOURNAL_NOT_RESOLVED')}
    return $journal
}

function Write-IzMaintenanceJournal {
    [CmdletBinding()]
    param([object]$Context,[object]$Journal,[long]$ExpectedSequence)
    $value=ConvertTo-IzMaintenanceJournal $Context $Journal
    $exists=Test-Path -LiteralPath $Context.journal_path
    if($ExpectedSequence -eq -1){if($exists -or [long]$value.sequence -ne 0){throw(New-IzJournalError 'JOURNAL_SEQUENCE_CONFLICT' 31)}}
    else{
        if(-not $exists){throw(New-IzJournalError 'JOURNAL_SEQUENCE_CONFLICT' 31)}
        $current=Read-IzMaintenanceJournal $Context
        if([long]$current.sequence -ne $ExpectedSequence -or [long]$value.sequence -ne ($ExpectedSequence+1)){throw(New-IzJournalError 'JOURNAL_SEQUENCE_CONFLICT' 31)}
    }
    [void](Write-IzAtomicJson $Context.journal_path $value $Context.journal_previous_path);return $value
}

function Merge-IzJournalPatch {
    param([object]$Journal,[AllowNull()][object]$Patch)
    if($null -eq $Patch){return}
    $allowed=@('source_release','target_release','data_identity','payload_identity','prior_receipt_sha256','snapshot','program')
    foreach($property in $Patch.PSObject.Properties){
        if($property.Name -notin $allowed){throw(New-IzJournalError 'JOURNAL_PATCH_INVALID' 20)}
        if($property.Name -eq 'program'){
            foreach($nested in $property.Value.PSObject.Properties){if($nested.Name -notin $script:ProgramFields){throw(New-IzJournalError 'JOURNAL_PATCH_INVALID' 20)};$Journal.program.($nested.Name)=$nested.Value}
        }else{$Journal.($property.Name)=$property.Value}
    }
}

function New-IzMaintenanceTransition {
    [CmdletBinding()]
    param([object]$Journal,[ValidateSet('PREPARING','PAYLOAD_VERIFIED','QUIESCED','SNAPSHOT_VERIFIED','SWAP_INTENT','OLD_MOVED','NEW_MOVED','VALIDATING','COMMITTED','ROLLBACK_INTENT','ROLLED_BACK','RECOVERY_REQUIRED')][string]$NextState,[string[]]$CompletedSteps=@(),[AllowNull()][object]$Patch)
    $currentState=[string]$Journal.state
    if(-not $script:Transitions.ContainsKey($currentState) -or $NextState -notin @($script:Transitions[$currentState])){throw(New-IzJournalError 'JOURNAL_TRANSITION_INVALID' 31)}
    $clone=ConvertFrom-Json ($Journal|ConvertTo-Json -Depth 16)
    $allSteps=@($clone.completed_steps)+@($CompletedSteps)
    $commitRequired=@('INSTALL_RECEIPT_WRITTEN','COMMIT_RECORDED')
    if($NextState -eq 'COMMITTED' -and @($commitRequired|Where-Object{$_ -notin $allSteps}).Count){throw(New-IzJournalError 'COMMIT_RECEIPT_REQUIRED' 31)}
    if($NextState -eq 'ROLLED_BACK'){
        $required=@('OLD_PROGRAM_RESTORED','OLD_RECEIPT_RESTORED','ROLLBACK_VALIDATED')
        if('CANDIDATE_STARTED' -in $allSteps){$required+=@('DATA_RESTORED')}
        if(@($required|Where-Object{$_ -notin $allSteps}).Count){throw(New-IzJournalError 'ROLLBACK_VALIDATION_REQUIRED' 31)}
    }
    Merge-IzJournalPatch $clone $Patch
    $seen=@{};$steps=@();foreach($step in @($clone.completed_steps)+@($CompletedSteps)){if($step -notin $script:Steps){throw(New-IzJournalError 'JOURNAL_STEPS_INVALID' 20)};if(-not $seen.ContainsKey($step)){$seen[$step]=$true;$steps+=$step}}
    $clone.completed_steps=@($steps);$clone.state=$NextState;$clone.sequence=[long]$clone.sequence+1;$clone.updated_utc=[DateTime]::UtcNow.ToString('o')
    return $clone
}

function Assert-IzJournalFileRecords {
    param([string]$Root,[object[]]$Records,[switch]$Exact)
    $canonical=Get-IzCanonicalPath $Root
    Assert-IzCurrentUserOwner $canonical
    $expected=@{}
    foreach($record in @($Records)){
        $relative=ConvertTo-IzRelativePath $record.path
        $key=$relative.ToUpperInvariant()
        if($expected.ContainsKey($key)){throw(New-IzJournalError 'ROLLBACK_PROGRAM_INVALID')}
        $path=Assert-IzContainedPath (Join-Path $canonical $relative.Replace('/','\')) $canonical
        $item=Get-Item -LiteralPath $path -Force
        if($item.PSIsContainer -or ($item.Attributes-band[IO.FileAttributes]::ReparsePoint) -ne 0 -or [long]$item.Length -ne [long]$record.length -or (Get-IzFileSha256 $path) -cne [string]$record.sha256){throw(New-IzJournalError 'ROLLBACK_PROGRAM_INVALID')}
        Assert-IzCurrentUserOwner $path
        $expected[$key]=$true
    }
    if($Exact){
        $actual=@{};$pending=[Collections.Stack]::new();$pending.Push($canonical)
        while($pending.Count){
            $directory=[string]$pending.Pop()
            foreach($item in @(Get-ChildItem -LiteralPath $directory -Force)){
                if(($item.Attributes-band[IO.FileAttributes]::ReparsePoint) -ne 0){throw(New-IzJournalError 'ROLLBACK_PROGRAM_INVALID')}
                Assert-IzCurrentUserOwner $item.FullName
                if($item.PSIsContainer){$pending.Push($item.FullName);continue}
                $relative=$item.FullName.Substring($canonical.Length+1).Replace('\','/')
                $actual[$relative.ToUpperInvariant()]=$true
            }
        }
        if($actual.Count -ne $expected.Count -or @($actual.Keys|Where-Object{-not $expected.ContainsKey($_)}).Count){throw(New-IzJournalError 'ROLLBACK_PROGRAM_INVALID')}
    }
}

function Assert-IzRollbackInventory {
    param([object]$Context,[object]$Journal,[object]$Source)
    foreach($name in @('previous_payload_identity','previous_inventory_relative_path','previous_inventory_sha256','previous_marker_sha256')){if(-not $Journal.program.$name){throw(New-IzJournalError 'ROLLBACK_PROGRAM_INVALID')}}
    if($Journal.program.previous_payload_identity -cne $Source.payload_identity){throw(New-IzJournalError 'ROLLBACK_PROGRAM_INVALID')}
    $transactionContext=Get-IzJournalTransactionContext $Context $Journal
    $inventoryPath=Assert-IzContainedPath (Join-Path $transactionContext.transaction_root $Journal.program.previous_inventory_relative_path.Replace('/','\')) $transactionContext.transaction_root
    if((Get-IzFileSha256 $inventoryPath) -cne $Journal.program.previous_inventory_sha256){throw(New-IzJournalError 'ROLLBACK_PROGRAM_INVALID')}
    $inventory=Read-IzProgramInventory $transactionContext $inventoryPath
    if($inventory.product_id -cne $Context.product_id -or $inventory.owner_sid -cne $Context.owner_sid -or $inventory.scope_id -cne $Context.scope_id -or $inventory.transaction_id -cne $Journal.transaction_id -or $inventory.role -cne 'previous' -or $inventory.root_path_hash -cne (Get-IzRootPathHash $transactionContext.previous_root) -or $inventory.payload_identity -cne $Source.payload_identity){throw(New-IzJournalError 'ROLLBACK_PROGRAM_INVALID')}
    Assert-IzJournalFileRecords $Context.install_root $inventory.files -Exact
}

function Assert-IzRollbackSnapshot {
    param([object]$Context,[object]$Journal)
    if(-not $Journal.snapshot -or -not $Journal.snapshot.verified -or $Journal.snapshot.data_identity -cne $Journal.data_identity -or 'DATA_RESTORED' -notin $Journal.completed_steps){throw(New-IzJournalError 'ROLLBACK_DATA_INVALID')}
    $transactionContext=Get-IzJournalTransactionContext $Context $Journal
    if($Journal.snapshot.relative_path -cne 'snapshot/pre-change.izcnabackup'){throw(New-IzJournalError 'ROLLBACK_DATA_INVALID')}
    $path=Assert-IzContainedPath (Join-Path $transactionContext.transaction_root $Journal.snapshot.relative_path.Replace('/','\')) $transactionContext.transaction_root
    if(-not $path.Equals($transactionContext.snapshot_path,[StringComparison]::OrdinalIgnoreCase) -or [long](Get-Item $path).Length -ne [long]$Journal.snapshot.length -or (Get-IzFileSha256 $path) -cne $Journal.snapshot.sha256){throw(New-IzJournalError 'ROLLBACK_DATA_INVALID')}
    Assert-IzCurrentUserOwner $path
}

function Get-IzMaintenanceAuthority {
    param([object]$Context,[object]$Journal,[AllowNull()][object]$InstallReceipt)
    $value=ConvertTo-IzMaintenanceJournal $Context $Journal
    if($value.state -eq 'COMMITTED'){return [pscustomobject][ordered]@{state=$value.state;program_authority='candidate';data_authority='current';launch_policy='candidate';recovery_required=$false;reason='COMMITTED'}}
    if($value.state -eq 'ROLLED_BACK' -and $InstallReceipt){
        try{
            $required=@('OLD_PROGRAM_RESTORED','OLD_RECEIPT_RESTORED','ROLLBACK_VALIDATED')
            if(@($required|Where-Object{$_ -notin $value.completed_steps}).Count){throw(New-IzJournalError 'ROLLBACK_VALIDATION_REQUIRED')}
            $source=ConvertTo-IzReleaseOrNull $value.source_release
            if(-not $source -or $value.prior_receipt_sha256 -notmatch '^[0-9a-f]{64}$' -or $value.program.active_payload_identity -cne $source.payload_identity){throw(New-IzJournalError 'ROLLBACK_IDENTITY_INVALID')}
            if(-not(Test-Path $Context.install_receipt_path -PathType Leaf) -or (Get-IzFileSha256 $Context.install_receipt_path) -cne $value.prior_receipt_sha256){throw(New-IzJournalError 'ROLLBACK_RECEIPT_INVALID')}
            $receipt=Read-IzInstallReceipt $Context
            $provided=ConvertTo-IzInstallReceipt $Context $InstallReceipt
            foreach($name in @('install_identity','data_identity','version','build','installer_revision','payload_identity','last_committed_transaction')){if($provided.$name -cne $receipt.$name){throw(New-IzJournalError 'ROLLBACK_RECEIPT_INVALID')}}
            if($receipt.version -cne $source.version -or $receipt.build -cne $source.build -or [int]$receipt.installer_revision -ne [int]$source.installer_revision -or $receipt.payload_identity -cne $source.payload_identity -or $receipt.data_identity -cne $value.data_identity -or $receipt.last_committed_transaction -ceq $value.transaction_id){throw(New-IzJournalError 'ROLLBACK_RECEIPT_INVALID')}
            if(-not @($receipt.owned_files|Where-Object{$_.path -ceq 'runtime/IZClinicalNotesAnalyzer.exe'}).Count){throw(New-IzJournalError 'ROLLBACK_PROGRAM_INVALID')}
            [void](Get-IzCanonicalPath $Context.install_root);Assert-IzCurrentUserOwner $Context.install_root
            [void](Get-IzCanonicalPath $Context.data_root);Assert-IzCurrentUserOwner $Context.data_root
            if('OLD_PROGRAM_MOVED' -in $value.completed_steps){Assert-IzRollbackInventory $Context $value $source}
            else{
                try{Assert-IzJournalFileRecords $Context.install_root $receipt.owned_files -Exact}
                catch{Assert-IzRollbackInventory $Context $value $source}
            }
            if('CANDIDATE_STARTED' -in $value.completed_steps){Assert-IzRollbackSnapshot $Context $value}
            return [pscustomobject][ordered]@{state=$value.state;program_authority='source';data_authority='restored';launch_policy='source';recovery_required=$false;reason='ROLLBACK_VALIDATED'}
        }catch{}
    }
    $required=$value.state -eq 'RECOVERY_REQUIRED' -or $value.state -eq 'ROLLED_BACK'
    return [pscustomobject][ordered]@{state=$value.state;program_authority='blocked';data_authority='protected';launch_policy='blocked';recovery_required=$required;reason=$(if($required){'RECOVERY_REQUIRED'}else{'TRANSACTION_PENDING'})}
}

function Get-IzJournalTransactionContext {
    param([object]$Context,[object]$Journal)
    if($Context.transaction_id){return $Context}
    $derived=$Context|Select-Object *;$tx=[string]$Journal.transaction_id
    $derived.transaction_id=$tx;$derived.transaction_root=Join-Path $Context.transactions_root $tx
    $derived.stage_root=Join-Path $Context.program_parent "IZ Clinical Notes Analyzer.stage-$tx"
    $derived.previous_root=Join-Path $Context.program_parent "IZ Clinical Notes Analyzer.previous-$tx"
    $derived.snapshot_path=Join-Path $derived.transaction_root 'snapshot\pre-change.izcnabackup'
    $derived.verification_root=Join-Path $derived.transaction_root 'verification'
    $derived.requests_root=Join-Path $derived.transaction_root 'requests';$derived.results_root=Join-Path $derived.transaction_root 'results'
    return Assert-IzMaintenanceContext $derived
}

function Get-IzAuxiliaryProgramDescriptor {
    param([object]$Context,[object]$Journal,[ValidateSet('stage','previous')][string]$Role)
    $root=if($Role -eq 'stage'){$Context.stage_root}else{$Context.previous_root}
    if(-not(Test-Path -LiteralPath $root -PathType Container)){return $null}
    $prefix=if($Role -eq 'stage'){'stage'}else{'previous'}
    $relative=[string]$Journal.program.($prefix+'_inventory_relative_path')
    $inventorySha=[string]$Journal.program.($prefix+'_inventory_sha256')
    $markerSha=[string]$Journal.program.($prefix+'_marker_sha256')
    $payload=[string]$Journal.program.($prefix+'_payload_identity')
    if(-not $relative -or $inventorySha -notmatch '^[0-9a-f]{64}$' -or $markerSha -notmatch '^[0-9a-f]{64}$' -or $payload -notmatch '^[0-9a-f]{64}$'){throw(New-IzJournalError 'AUXILIARY_PROGRAM_INVALID')}
    $inventoryPath=Assert-IzContainedPath (Join-Path $Context.transaction_root $relative.Replace('/','\')) $Context.transaction_root
    if((Get-IzFileSha256 $inventoryPath) -ne $inventorySha){throw(New-IzJournalError 'AUXILIARY_PROGRAM_INVALID')}
    $inventory=Read-IzProgramInventory $Context $inventoryPath
    if($inventory.role -ne $Role -or $inventory.transaction_id -ne $Journal.transaction_id -or $inventory.payload_identity -ne $payload){throw(New-IzJournalError 'AUXILIARY_PROGRAM_INVALID')}
    [void](Test-IzProgramInventory $Context $inventory $root)
    [void](Test-IzOwnedRootMarker $Context $root $Role ([Guid]$Journal.transaction_id))
    if((Get-IzFileSha256 (Join-Path $root '.iz-cna-owned-root.json')) -ne $markerSha){throw(New-IzJournalError 'AUXILIARY_PROGRAM_INVALID')}
    $owned=@($inventory.files|Where-Object{$_.owned}|ForEach-Object{[pscustomobject][ordered]@{path=$_.path;length=[long]$_.length;sha256=$_.sha256}})
    return [pscustomobject][ordered]@{role=$Role;path=$root;transaction_id=$Journal.transaction_id;marker_sha256=$markerSha;payload_identity=$payload;owned_files=$owned}
}

function Get-IzPendingMaintenanceStatus {
    param([object]$Context)
    Assert-IzMaintenanceContext $Context|Out-Null
    if(-not(Test-Path $Context.journal_path)){return [pscustomobject][ordered]@{status='CLEAN';journal=$null;authority=$null;auxiliary_program_roots=@();reason='NO_JOURNAL'}}
    try{
        $journal=Read-IzMaintenanceJournal $Context;$receipt=if(Test-Path $Context.install_receipt_path){Read-IzInstallReceipt $Context}else{$null};$authority=Get-IzMaintenanceAuthority $Context $journal $receipt
        $auxiliary=@()
        if($journal.state -eq 'COMMITTED'){
            $transactionContext=Get-IzJournalTransactionContext $Context $journal
            foreach($role in @('stage','previous')){$descriptor=Get-IzAuxiliaryProgramDescriptor $transactionContext $journal $role;if($descriptor){$auxiliary+=$descriptor}}
        }
    }
    catch{return [pscustomobject][ordered]@{status='RECOVERY_REQUIRED';journal=$null;authority=$null;auxiliary_program_roots=@();reason='JOURNAL_INVALID'}}
    $status=if($journal.state -eq 'COMMITTED'){'COMMITTED'}elseif($authority.recovery_required){'RECOVERY_REQUIRED'}else{'PENDING'}
    return [pscustomobject][ordered]@{status=$status;journal=$journal;authority=$authority;auxiliary_program_roots=@($auxiliary);reason=$authority.reason}
}

Export-ModuleMember -Function New-IzMaintenanceJournal,Read-IzMaintenanceJournal,Read-IzResolvedMaintenanceJournal,Write-IzMaintenanceJournal,New-IzMaintenanceTransition,Get-IzMaintenanceAuthority,Get-IzPendingMaintenanceStatus
