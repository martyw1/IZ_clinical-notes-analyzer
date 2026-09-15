Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'maintenance-common.psm1')
Import-Module (Join-Path $PSScriptRoot 'maintenance-contracts.psm1')
Import-Module (Join-Path $PSScriptRoot 'maintenance-runtime.psm1')

function New-IzTransactionError {
    param([string]$Reason,[int]$Code=31)
    $exception=[IO.InvalidDataException]::new($Reason);$exception.Data['iz_reason']=$Reason;$exception.Data['iz_exit_code']=$Code;return $exception
}

function Write-IzTransactionJson {
    param([object]$Context,[string]$RelativePath,[object]$Value)
    $path=Assert-IzContainedPath (Join-Path $Context.transaction_root $RelativePath) $Context.transaction_root -AllowMissingLeaf
    if(Test-Path -LiteralPath $path){throw(New-IzTransactionError 'TRANSACTION_ARTIFACT_EXISTS')}
    $bytes=[Text.UTF8Encoding]::new($false).GetBytes(($Value|ConvertTo-Json -Depth 16))
    $stream=[IO.FileStream]::new($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None,4096,[IO.FileOptions]::WriteThrough)
    try{$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
    Protect-IzMaintenancePath $path|Out-Null
    return [pscustomobject]@{path=$path;relative_path=$RelativePath;sha256=(Get-IzFileSha256 $path)}
}

function Get-IzInstallFileRecords {
    param([object]$Manifest)
    $records=@();$seen=@{}
    foreach($file in @($Manifest.files)){
        $source=[string]$file.path;$target=$null
        if($source.StartsWith('app/',[StringComparison]::Ordinal)){$target=$source.Substring(4)}
        elseif($source.StartsWith('installer/',[StringComparison]::Ordinal)){$target=$source}
        else{continue}
        if(-not $target -or $seen.ContainsKey($target.ToUpperInvariant())){throw(New-IzTransactionError 'STAGE_PATH_COLLISION' 20)}
        $seen[$target.ToUpperInvariant()]=$true
        $records += [pscustomobject][ordered]@{source_path=$source;path=$target;length=[long]$file.length;sha256=[string]$file.sha256;owned=$true}
    }
    if(@($records|Where-Object{$_.path -eq 'runtime/IZClinicalNotesAnalyzer.exe'}).Count -ne 1 -or
       @($records|Where-Object{$_.path -eq 'frontend/dist/index.html'}).Count -ne 1 -or
       @($records|Where-Object{$_.path -eq 'VERSION.json'}).Count -ne 1){throw(New-IzTransactionError 'STAGE_REQUIRED_FILE_MISSING' 20)}
    return @($records)
}

function Test-IzProgramFiles {
    param([string]$Root,[object[]]$Files,[switch]$AllowMarker)
    $canonical=Get-IzCanonicalPath $Root
    $expected=@{}
    foreach($file in @($Files)){
        $path=Assert-IzContainedPath (Join-Path $canonical ([string]$file.path).Replace('/','\')) $canonical
        if (-not (Test-Path $path -PathType Leaf) -or (Get-Item $path).Length -ne [long]$file.length -or
            (Get-IzFileSha256 $path) -cne [string]$file.sha256) { throw (New-IzTransactionError 'PROGRAM_INVENTORY_MISMATCH') }
        $expected[[string]$file.path.ToUpperInvariant()]=$true
    }
    $actual=@(Get-ChildItem -LiteralPath $canonical -File -Recurse -Force|ForEach-Object{$_.FullName.Substring($canonical.Length+1).Replace('\','/')}|Where-Object{-not ($AllowMarker -and $_ -ceq '.iz-cna-owned-root.json')})
    if ($actual.Count -ne $expected.Count -or @($actual|Where-Object{-not $expected.ContainsKey($_.ToUpperInvariant())}).Count) { throw (New-IzTransactionError 'PROGRAM_FILE_SET_MISMATCH') }
    return $true
}

function Copy-IzStagedProgram {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Context,[Parameter(Mandatory)][object]$Manifest)
    Assert-IzMaintenanceContext $Context|Out-Null
    if (-not $Context.transaction_id -or -not $Context.package_root) { throw (New-IzTransactionError 'TRANSACTION_CONTEXT_REQUIRED' 20) }
    [void](Test-IzReleasePayload -PackageRoot $Context.package_root -Manifest $Manifest)
    if ((Test-Path $Context.stage_root) -or (Test-Path $Context.previous_root)) { throw (New-IzTransactionError 'AUXILIARY_PROGRAM_ROOT_EXISTS' 31) }
    $files=@(Get-IzInstallFileRecords $Manifest)
    $manifestPath=Join-Path $Context.package_root 'release-manifest.json'
    $files += [pscustomobject][ordered]@{source_path='release-manifest.json';path='release-manifest.json';length=[long](Get-Item $manifestPath).Length;sha256=(Get-IzFileSha256 $manifestPath);owned=$true}
    $required=[long](($files|Measure-Object length -Sum).Sum)+67108864
    $drive=[IO.DriveInfo]::new([IO.Path]::GetPathRoot($Context.program_parent))
    if($drive.AvailableFreeSpace -lt $required){throw(New-IzTransactionError 'INSUFFICIENT_STAGE_SPACE' 20)}
    [IO.Directory]::CreateDirectory($Context.stage_root)|Out-Null;Protect-IzMaintenancePath $Context.stage_root|Out-Null
    try{
        foreach($file in $files){
            $source=Assert-IzContainedPath (Join-Path $Context.package_root $file.source_path.Replace('/','\')) $Context.package_root
            $target=Assert-IzContainedPath (Join-Path $Context.stage_root $file.path.Replace('/','\')) $Context.stage_root -AllowMissingLeaf
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))|Out-Null
            [IO.File]::Copy($source,$target,$false)
            if ((Get-Item $target).Length -ne $file.length -or (Get-IzFileSha256 $target) -cne $file.sha256) { throw (New-IzTransactionError 'STAGE_COPY_MISMATCH' 20) }
        }
        $marker=Write-IzOwnedRootMarker $Context $Context.stage_root stage ([Guid]$Context.transaction_id)
        $inventoryFiles=@($files|ForEach-Object{[pscustomobject][ordered]@{path=$_.path;length=$_.length;sha256=$_.sha256;owned=$true}})
        $inventory=New-IzProgramInventory $Context $Context.stage_root stage $Manifest.payload_identity $inventoryFiles ([Guid]$Context.transaction_id)
        $artifact=Write-IzTransactionJson $Context 'program-stage.json' $inventory
        [void](Test-IzProgramFiles $Context.stage_root $inventoryFiles -AllowMarker)
        $markerHash=Get-IzFileSha256 (Join-Path $Context.stage_root '.iz-cna-owned-root.json')
        $patch=[pscustomobject][ordered]@{stage_payload_identity=$Manifest.payload_identity;stage_inventory_relative_path=$artifact.relative_path;stage_inventory_sha256=$artifact.sha256;stage_marker_sha256=$markerHash}
        return [pscustomobject][ordered]@{schema='iz-cna-program-binding-v1';role='stage';root_path=$Context.stage_root;payload_identity=$Manifest.payload_identity;files=$inventoryFiles;inventory=$inventory;inventory_path=$artifact.path;marker=$marker;journal_patch=$patch}
    }catch{
        if(Test-Path $Context.stage_root){
            try{[void](Test-IzOwnedRootMarker $Context $Context.stage_root stage ([Guid]$Context.transaction_id));Remove-Item $Context.stage_root -Recurse -Force}catch{}
        }
        throw
    }
}

function Save-IzPriorReceiptAndShortcuts {
    param([object]$Context,[AllowNull()][object]$PriorReceipt)
    if(-not $PriorReceipt){return}
    $receiptPath=Join-Path $Context.transaction_root 'prior-install-receipt.json'
    if(-not(Test-Path $receiptPath)){
        [IO.File]::Copy($Context.install_receipt_path,$receiptPath,$false);Protect-IzMaintenancePath $receiptPath|Out-Null
    }
    $expected=Read-IzMaintenanceJournal $Context
    if((Get-IzFileSha256 $receiptPath)-cne$expected.prior_receipt_sha256){throw(New-IzTransactionError 'PRIOR_RECEIPT_HASH_MISMATCH')}
    $shortcutRoot=Join-Path $Context.transaction_root 'prior-shortcuts';[IO.Directory]::CreateDirectory($shortcutRoot)|Out-Null
    $records=@();$index=0
    foreach($shortcut in @($PriorReceipt.owned_shortcuts)){
        $base=if ($shortcut.location -eq 'start_menu') {$Context.start_menu_root} else {$Context.desktop_root}
        $path=Assert-IzContainedPath (Join-Path $base $shortcut.name) $base -AllowMissingLeaf
        $copy=$null;$sha=$null
        if(Test-Path $path -PathType Leaf){$copy=Join-Path $shortcutRoot ("$index.lnk");[IO.File]::Copy($path,$copy,$false);$sha=Get-IzFileSha256 $copy}
        $records += [pscustomobject][ordered]@{location=$shortcut.location;name=$shortcut.name;present=($null -ne $copy);sha256=$sha;copy_name=$(if($copy){Split-Path $copy -Leaf}else{$null})}
        $index++
    }
    if(-not(Test-Path (Join-Path $Context.transaction_root 'prior-shortcuts.json'))){[void](Write-IzTransactionJson $Context 'prior-shortcuts.json' ([pscustomobject]@{shortcuts=$records}))}
}

function New-IzPreviousBinding {
    param([object]$Context,[object]$Journal,[AllowNull()][object]$PriorReceipt)
    if(-not(Test-Path $Context.install_root -PathType Container)){return $null}
    $allFiles=@(Get-ChildItem $Context.install_root -File -Recurse -Force)
    if(-not $allFiles.Count){throw(New-IzTransactionError 'INSTALLED_PROGRAM_EMPTY')}
    $receiptMap=@{};if($PriorReceipt){foreach($file in @($PriorReceipt.owned_files)){$receiptMap[[string]$file.path.ToUpperInvariant()]=$file}}
    $files=@();foreach($file in $allFiles){
        $relative=$file.FullName.Substring($Context.install_root.Length+1).Replace('\','/');$owned=$false
        $hash=Get-IzFileSha256 $file.FullName
        if($PriorReceipt){
            # Ownership requires both a receipt path and the exact bytes that the
            # receipt recorded. Unknown or modified files remain unowned.
            if($receiptMap.ContainsKey($relative.ToUpperInvariant())){
                $expected=$receiptMap[$relative.ToUpperInvariant()]
                $owned=([long]$file.Length -eq [long]$expected.length -and $hash -ceq [string]$expected.sha256)
            }
        }else{$owned=$true}
        $files += [pscustomobject][ordered]@{path=$relative;length=[long]$file.Length;sha256=$hash;owned=$owned}
    }
    $payload=if($PriorReceipt){$PriorReceipt.payload_identity}elseif($Journal.source_release){$Journal.source_release.payload_identity}else{throw(New-IzTransactionError 'SOURCE_PROGRAM_IDENTITY_MISSING')}
    [IO.Directory]::CreateDirectory($Context.previous_root)|Out-Null;Protect-IzMaintenancePath $Context.previous_root|Out-Null
    $marker=Write-IzOwnedRootMarker $Context $Context.previous_root previous ([Guid]$Context.transaction_id)
    $markerStash=Join-Path $Context.transaction_root 'program-previous-marker.json'
    [IO.File]::Move((Join-Path $Context.previous_root '.iz-cna-owned-root.json'),$markerStash);Remove-Item $Context.previous_root -Force
    $inventory=New-IzProgramInventory $Context $Context.previous_root previous $payload $files ([Guid]$Context.transaction_id)
    $artifact=Write-IzTransactionJson $Context 'program-previous.json' $inventory
    return [pscustomobject][ordered]@{schema='iz-cna-program-binding-v1';role='previous';root_path=$Context.previous_root;payload_identity=$payload;files=$files;inventory=$inventory;inventory_path=$artifact.path;marker_stash=$markerStash;marker_sha256=(Get-IzFileSha256 $markerStash);journal_patch=[pscustomobject][ordered]@{previous_payload_identity=$payload;previous_inventory_relative_path=$artifact.relative_path;previous_inventory_sha256=$artifact.sha256;previous_marker_sha256=(Get-IzFileSha256 $markerStash)}}
}

function Read-IzPreviousBinding {
    param([object]$Context,[object]$Journal)
    $relative=[string]$Journal.program.previous_inventory_relative_path
    $path=Assert-IzContainedPath (Join-Path $Context.transaction_root $relative.Replace('/','\')) $Context.transaction_root
    if((Get-IzFileSha256 $path)-cne$Journal.program.previous_inventory_sha256){throw(New-IzTransactionError 'PREVIOUS_INVENTORY_HASH_MISMATCH')}
    $inventory=Read-IzProgramInventory $Context $path
    if($inventory.role-cne'previous'-or$inventory.transaction_id-cne$Context.transaction_id-or$inventory.payload_identity-cne$Journal.program.previous_payload_identity){
        throw(New-IzTransactionError 'PREVIOUS_INVENTORY_MISMATCH')
    }
    $markerStash=Join-Path $Context.transaction_root 'program-previous-marker.json'
    if((Get-IzFileSha256 $markerStash)-cne$Journal.program.previous_marker_sha256){throw(New-IzTransactionError 'PREVIOUS_MARKER_HASH_MISMATCH')}
    return [pscustomobject][ordered]@{schema='iz-cna-program-binding-v1';role='previous';root_path=$Context.previous_root;payload_identity=$inventory.payload_identity;files=@($inventory.files);inventory=$inventory;inventory_path=$path;marker_stash=$markerStash;marker_sha256=$Journal.program.previous_marker_sha256;journal_patch=[pscustomobject][ordered]@{previous_payload_identity=$Journal.program.previous_payload_identity;previous_inventory_relative_path=$relative;previous_inventory_sha256=$Journal.program.previous_inventory_sha256;previous_marker_sha256=$Journal.program.previous_marker_sha256}}
}

function Initialize-IzPreviousProgramBinding {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Context,[Parameter(Mandatory)][object]$Journal,[AllowNull()][object]$PriorReceipt)
    Assert-IzMaintenanceContext $Context|Out-Null
    if($Journal.program.previous_inventory_relative_path){return Read-IzPreviousBinding $Context $Journal}
    return New-IzPreviousBinding $Context $Journal $PriorReceipt
}

function Register-IzFreshDataRoot {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Context,[Parameter(Mandatory)][string]$DataIdentity)
    Assert-IzMaintenanceContext $Context|Out-Null
    if(-not $Context.transaction_id -or -not(Test-Path $Context.data_root -PathType Container)){throw(New-IzTransactionError 'FRESH_DATA_ROOT_INVALID' 20)}
    $root=Get-IzCanonicalPath $Context.data_root
    if($DataIdentity -notmatch '^[0-9a-f]{64}$'){throw(New-IzTransactionError 'DATA_IDENTITY_INVALID' 20)}
    return Write-IzTransactionJson $Context 'fresh-data-root.json' ([pscustomobject][ordered]@{
        schema='iz-cna-fresh-data-root-v1';product_id=$Context.product_id;owner_sid=$Context.owner_sid
        scope_id=$Context.scope_id;transaction_id=$Context.transaction_id;data_root=$root;data_identity=$DataIdentity
    })
}

function Remove-IzFreshDataRoot {
    param([object]$Context,[object]$Journal)
    $recordPath=Join-Path $Context.transaction_root 'fresh-data-root.json'
    if(-not(Test-Path $recordPath -PathType Leaf)){return $false}
    try{$record=[IO.File]::ReadAllText($recordPath,[Text.Encoding]::UTF8)|ConvertFrom-Json}catch{throw(New-IzTransactionError 'FRESH_DATA_RECORD_INVALID')}
    $names=@($record.PSObject.Properties.Name|Sort-Object);$expected=@('data_identity','data_root','owner_sid','product_id','schema','scope_id','transaction_id')
    if(($names -join '|')-cne($expected -join '|') -or $record.schema -cne 'iz-cna-fresh-data-root-v1' -or
       $record.product_id -cne $Context.product_id -or $record.owner_sid -cne $Context.owner_sid -or
       $record.scope_id -cne $Context.scope_id -or $record.transaction_id -cne $Context.transaction_id -or
       $record.data_identity -cne $Journal.data_identity -or
       (Get-IzCanonicalPath $record.data_root) -ine (Get-IzCanonicalPath $Context.data_root)){
        throw(New-IzTransactionError 'FRESH_DATA_RECORD_MISMATCH')
    }
    if(Test-Path $Context.data_root){[void](Get-IzCanonicalPath $Context.data_root);Remove-Item $Context.data_root -Recurse -Force}
    return $true
}

function Write-IzTransition {
    param([object]$Context,[object]$Journal,[string]$State,[string[]]$Steps=@(),[AllowNull()][object]$Patch)
    $next=New-IzMaintenanceTransition -Journal $Journal -NextState $State -CompletedSteps $Steps -Patch $Patch
    Write-IzMaintenanceJournal -Context $Context -Journal $next -ExpectedSequence $Journal.sequence|Out-Null
    return $next
}

function Invoke-IzProgramSwap {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Context,[Parameter(Mandatory)][object]$Journal,[Parameter(Mandatory)][object]$StageBinding,[AllowNull()][object]$PriorReceipt)
    Assert-IzMaintenanceContext $Context|Out-Null
    if ($Journal.state -cne 'SNAPSHOT_VERIFIED') {throw(New-IzTransactionError 'SNAPSHOT_NOT_VERIFIED')}
    [void](Test-IzOwnedRootMarker $Context $Context.stage_root stage ([Guid]$Context.transaction_id));[void](Test-IzProgramFiles $Context.stage_root $StageBinding.files -AllowMarker)
    Save-IzPriorReceiptAndShortcuts $Context $PriorReceipt
    $previous=Initialize-IzPreviousProgramBinding $Context $Journal $PriorReceipt
    $program=[ordered]@{};foreach($property in $StageBinding.journal_patch.PSObject.Properties){$program[$property.Name]=$property.Value}
    if($previous){foreach($property in $previous.journal_patch.PSObject.Properties){$program[$property.Name]=$property.Value}}
    $current=Write-IzTransition $Context $Journal SWAP_INTENT @('OLD_MOVE_INTENT_RECORDED') ([pscustomobject]@{program=[pscustomobject]$program})
    if(Test-Path $Context.install_root){[IO.Directory]::Move($Context.install_root,$Context.previous_root);[IO.File]::Copy($previous.marker_stash,(Join-Path $Context.previous_root '.iz-cna-owned-root.json'),$false);[void](Test-IzProgramFiles $Context.previous_root $previous.files -AllowMarker)}
    $current=Write-IzTransition $Context $current OLD_MOVED @('OLD_PROGRAM_MOVED') $null
    $current=Write-IzTransition $Context $current OLD_MOVED @('NEW_MOVE_INTENT_RECORDED') $null
    if(Test-Path $Context.install_root){throw(New-IzTransactionError 'INSTALL_ROOT_NOT_EMPTY')}
    [IO.Directory]::Move($Context.stage_root,$Context.install_root);[void](Test-IzProgramFiles $Context.install_root $StageBinding.files -AllowMarker)
    $current=Write-IzTransition $Context $current NEW_MOVED @('NEW_PROGRAM_MOVED') ([pscustomobject]@{program=[pscustomobject]@{active_payload_identity=$StageBinding.payload_identity}})
    return $current
}

function Restore-IzPriorShortcuts {
    param([object]$Context)
    $manifestPath=Join-Path $Context.transaction_root 'prior-shortcuts.json';if(-not(Test-Path $manifestPath)){return}
    $manifest=[IO.File]::ReadAllText($manifestPath,[Text.Encoding]::UTF8)|ConvertFrom-Json
    foreach($record in @($manifest.shortcuts)){
        $base=if ($record.location -eq 'start_menu') {$Context.start_menu_root} else {$Context.desktop_root};[IO.Directory]::CreateDirectory($base)|Out-Null
        $target=Assert-IzContainedPath (Join-Path $base $record.name) $base -AllowMissingLeaf
        if($record.present){$source=Join-Path (Join-Path $Context.transaction_root 'prior-shortcuts') $record.copy_name;if((Get-IzFileSha256 $source)-cne$record.sha256){throw(New-IzTransactionError 'PRIOR_SHORTCUT_HASH_MISMATCH')};[IO.File]::Copy($source,$target,$true)}
        elseif(Test-Path $target){Remove-Item $target -Force}
    }
}

function Set-IzRecoveryRequired {
    param([object]$Context,[object]$Journal,[string]$Reason)
    try{$current=Read-IzMaintenanceJournal $Context;if($current.state -ne 'RECOVERY_REQUIRED'){$current=Write-IzTransition $Context $current RECOVERY_REQUIRED @() $null}}catch{$current=$Journal}
    return [pscustomobject][ordered]@{schema='iz-cna-install-recovery-v1';status='recovery_required';reason=$Reason;journal=$current}
}

function Invoke-IzInstallRecovery {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Context,[Parameter(Mandatory)][object]$Journal,[object]$Manifest)
    Assert-IzMaintenanceContext $Context|Out-Null
    try{
        $current=Read-IzMaintenanceJournal $Context
        if($current.state -eq 'COMMITTED'){return [pscustomobject][ordered]@{schema='iz-cna-install-recovery-v1';status='committed';reason='COMMITTED_NO_ROLLBACK';journal=$current}}
        $wasValidating=$current.state -eq 'VALIDATING'
        if($current.state -ne 'ROLLBACK_INTENT'){$current=Write-IzTransition $Context $current ROLLBACK_INTENT @('ROLLBACK_INTENT_RECORDED') $null}
        $stop=Stop-IzOwnedRuntime -Context $Context -TimeoutSeconds 30 -AllowLegacyFallback
        if($stop.status -eq 'failure'){throw(New-IzTransactionError $stop.reason)}
        if('CANDIDATE_STARTED'-in$current.completed_steps -or $wasValidating){
            $current=Write-IzTransition $Context $current ROLLBACK_INTENT @('CANDIDATE_STOPPED') $null
            if($current.snapshot -and $current.snapshot.verified){
                if(-not $Manifest){throw(New-IzTransactionError 'VERIFIED_SNAPSHOT_REQUIRED')}
                $current=Write-IzTransition $Context $current ROLLBACK_INTENT @('DATA_RESTORE_INTENT_RECORDED') $null
                Import-Module (Join-Path $PSScriptRoot 'backup-verification.psm1') -Force
                $restore=Restore-IzFullBackup -Context $Context -BackupPath $Context.snapshot_path -RuntimeRole Installed -Manifest $Manifest -ExpectedProfileSnapshotIdentity $current.snapshot.profile_snapshot_identity -Confirmed
                if($restore.status -ne 'success'){throw(New-IzTransactionError 'DATA_RESTORE_FAILED')}
                $current=Write-IzTransition $Context $current ROLLBACK_INTENT @('DATA_RESTORED') $null
            }elseif(Remove-IzFreshDataRoot $Context $current){
                $current=Write-IzTransition $Context $current ROLLBACK_INTENT @('DATA_RESTORE_INTENT_RECORDED','DATA_RESTORED') $null
            }else{throw(New-IzTransactionError 'VERIFIED_SNAPSHOT_REQUIRED')}
        }
        elseif(Remove-IzFreshDataRoot $Context $current){
            $current=Write-IzTransition $Context $current ROLLBACK_INTENT @('DATA_RESTORE_INTENT_RECORDED','DATA_RESTORED') $null
        }
        $programMutation=('OLD_MOVE_INTENT_RECORDED'-in$current.completed_steps)-or('OLD_PROGRAM_MOVED'-in$current.completed_steps)-or('NEW_PROGRAM_MOVED'-in$current.completed_steps)
        if(-not $programMutation){
            if(Test-Path $Context.stage_root){[void](Test-IzOwnedRootMarker $Context $Context.stage_root stage ([Guid]$Context.transaction_id));Remove-Item $Context.stage_root -Recurse -Force}
            $current=Write-IzTransition $Context $current ROLLBACK_INTENT @('PROGRAM_RESTORE_INTENT_RECORDED','OLD_PROGRAM_RESTORED','OLD_RECEIPT_RESTORED') $null
            $rollbackPatch=if($current.source_release){[pscustomobject]@{program=[pscustomobject]@{active_payload_identity=$current.source_release.payload_identity}}}else{$null}
            $current=Write-IzTransition $Context $current ROLLED_BACK @('ROLLBACK_VALIDATED') $rollbackPatch
            return [pscustomobject][ordered]@{schema='iz-cna-install-recovery-v1';status='rolled_back';reason='ROLLBACK_VALIDATED';journal=$current}
        }
        $current=Write-IzTransition $Context $current ROLLBACK_INTENT @('PROGRAM_RESTORE_INTENT_RECORDED') $null
        $sourceExists=$null -ne $current.program.previous_inventory_relative_path;$previousExists=Test-Path $Context.previous_root -PathType Container;$installExists=Test-Path $Context.install_root -PathType Container
        if($previousExists){
            if($installExists){if(Test-Path $Context.stage_root){throw(New-IzTransactionError 'PROGRAM_ROOTS_AMBIGUOUS')};[IO.Directory]::Move($Context.install_root,$Context.stage_root)}
            [IO.Directory]::Move($Context.previous_root,$Context.install_root)
        }elseif(-not $sourceExists){
            if($installExists){if(Test-Path $Context.stage_root){throw(New-IzTransactionError 'PROGRAM_ROOTS_AMBIGUOUS')};[IO.Directory]::Move($Context.install_root,$Context.stage_root)}
        }elseif(-not $installExists){throw(New-IzTransactionError 'SOURCE_PROGRAM_MISSING')}
        if($sourceExists){
            $inventoryPath=Join-Path $Context.transaction_root $current.program.previous_inventory_relative_path
            $inventory=Read-IzProgramInventory $Context $inventoryPath;[void](Test-IzProgramFiles $Context.install_root $inventory.files -AllowMarker)
            $stale=Join-Path $Context.install_root '.iz-cna-owned-root.json';if(Test-Path $stale){Remove-Item $stale -Force}
        }
        $current=Write-IzTransition $Context $current ROLLBACK_INTENT @('OLD_PROGRAM_RESTORED') $null
        $priorPath=Join-Path $Context.transaction_root 'prior-install-receipt.json'
        if(Test-Path $priorPath){
            if((Get-IzFileSha256 $priorPath)-cne$current.prior_receipt_sha256){throw(New-IzTransactionError 'PRIOR_RECEIPT_HASH_MISMATCH')}
            $prior=[IO.File]::ReadAllText($priorPath,[Text.Encoding]::UTF8)|ConvertFrom-Json
            $expected=if(Test-Path $Context.install_receipt_path){Get-IzFileSha256 $Context.install_receipt_path}else{$null}
            Write-IzInstallReceipt $Context $prior $expected|Out-Null
        }elseif(Test-Path $Context.install_receipt_path){Remove-Item $Context.install_receipt_path -Force}
        Restore-IzPriorShortcuts $Context
        $rollbackPatch=if($current.source_release){[pscustomobject]@{program=[pscustomobject]@{active_payload_identity=$current.source_release.payload_identity}}}else{$null}
        $current=Write-IzTransition $Context $current ROLLED_BACK @('OLD_RECEIPT_RESTORED','ROLLBACK_VALIDATED') $rollbackPatch
        return [pscustomobject][ordered]@{schema='iz-cna-install-recovery-v1';status='rolled_back';reason='ROLLBACK_VALIDATED';journal=$current}
    }catch{
        $reason=if($_.Exception.Data.Contains('iz_reason')){[string]$_.Exception.Data['iz_reason']}else{'RECOVERY_FAILED'}
        return Set-IzRecoveryRequired $Context $Journal $reason
    }
}

function Remove-IzCommittedProgramArtifacts {
    param([object]$Context,[object]$Journal)
    if($Journal.state -ne 'COMMITTED'){throw(New-IzTransactionError 'COMMIT_REQUIRED')}
    $marker=Join-Path $Context.install_root '.iz-cna-owned-root.json';if(Test-Path $marker){Remove-Item $marker -Force}
    if(Test-Path $Context.previous_root){[void](Test-IzOwnedRootMarker $Context $Context.previous_root previous ([Guid]$Context.transaction_id));$inventory=Read-IzProgramInventory $Context (Join-Path $Context.transaction_root $Journal.program.previous_inventory_relative_path);[void](Test-IzProgramFiles $Context.previous_root $inventory.files -AllowMarker);if(@($inventory.files|Where-Object{-not $_.owned}).Count -eq 0){Remove-Item $Context.previous_root -Recurse -Force}}
}

Export-ModuleMember -Function Copy-IzStagedProgram,Initialize-IzPreviousProgramBinding,Register-IzFreshDataRoot,Invoke-IzProgramSwap,Invoke-IzInstallRecovery,Remove-IzCommittedProgramArtifacts
