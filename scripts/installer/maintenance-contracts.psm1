Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'maintenance-paths.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'maintenance-version.psm1') -Force

$script:ProductId = 'r3.iz-clinical-notes-analyzer.desktop'
$script:Hex64 = '^[0-9a-f]{64}$'
$script:AtomicWriteInterruption = $null
$script:RequiredPayloadFiles = @(
    'Backup-IZ-Clinical-Notes-Analyzer.cmd','Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd','Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd','Install-IZ-Clinical-Notes-Analyzer.cmd',
    'Launch-IZ-Clinical-Notes-Analyzer.cmd','Restore-IZ-Clinical-Notes-Analyzer.cmd','Stop-IZ-Clinical-Notes-Analyzer.cmd','Uninstall-IZ-Clinical-Notes-Analyzer.cmd',
    'app/runtime/IZClinicalNotesAnalyzer.exe','app/frontend/dist/index.html','app/config/checklists/treatment-plan-v1.json','app/VERSION','app/VERSION.json',
    'installer/maintenance-windows.ps1','installer/install-windows-release.ps1','installer/uninstall-windows-release.ps1','installer/maintenance-common.psm1',
    'installer/maintenance-contracts.psm1','installer/maintenance-paths.psm1','installer/maintenance-version.psm1','installer/maintenance-lock.psm1','installer/maintenance-journal.psm1',
    'installer/backup-verification.psm1','installer/maintenance-runtime.psm1','installer/maintenance-transaction.psm1','installer/Remove-IZ-Clinical-Notes-Analyzer.bootstrap.ps1','installer/maintenance-bundle-manifest.json','installer/legacy-program-inventory.json'
)

function New-IzContractError {
    param([string]$Reason,[int]$Code=20)
    $exception=[IO.InvalidDataException]::new($Reason)
    $exception.Data['iz_reason']=$Reason
    $exception.Data['iz_exit_code']=$Code
    return $exception
}

function Assert-IzExactProperties {
    param([object]$Value,[string[]]$Expected,[string]$Reason='CONTRACT_INVALID')
    if ($null -eq $Value -or $Value -is [Array] -or $Value -is [string]) { throw (New-IzContractError $Reason) }
    $actual=@($Value.PSObject.Properties.Name)
    if ($actual.Count -ne $Expected.Count -or @($Expected | Where-Object { $_ -notin $actual }).Count) {
        throw (New-IzContractError $Reason)
    }
    return $Value
}

function Assert-IzString {
    param([object]$Value,[string]$Reason,[string]$Pattern='')
    if ($Value -isnot [string] -or ($Pattern -and $Value -notmatch $Pattern)) { throw (New-IzContractError $Reason) }
    return [string]$Value
}

function Read-IzStrictJsonFile {
    param([Parameter(Mandatory)][string]$Path,[string]$MissingReason='CONTRACT_MISSING',[string]$CorruptReason='CONTRACT_CORRUPT')
    $canonical=Get-IzCanonicalPath $Path -AllowMissingLeaf
    if (-not (Test-Path -LiteralPath $canonical -PathType Leaf)) { throw (New-IzContractError $MissingReason) }
    try {
        $text=[IO.File]::ReadAllText($canonical,[Text.UTF8Encoding]::new($false,$true))
        if ([string]::IsNullOrWhiteSpace($text)) { throw 'empty' }
        return ConvertFrom-Json -InputObject $text -ErrorAction Stop
    } catch { throw (New-IzContractError $CorruptReason) }
}

function Get-IzFileSha256 {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw (New-IzContractError 'FILE_MISSING') }
    $stream=[IO.File]::Open($Path,'Open','Read','Read')
    $sha=[Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose(); $stream.Dispose() }
}

function Write-IzAtomicJson {
    param([string]$Path,[object]$Value,[string]$PreviousPath)
    $canonical=Get-IzCanonicalPath $Path -AllowMissingLeaf
    $parent=[IO.Path]::GetDirectoryName($canonical)
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) { throw (New-IzContractError 'RESULT_PARENT_MISSING') }
    $json=$Value | ConvertTo-Json -Depth 16
    $temp=Join-Path $parent ('.iz-'+[IO.Path]::GetRandomFileName())
    $backup=$null
    try {
        $options=[IO.FileOptions]::WriteThrough
        $stream=[IO.FileStream]::new($temp,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None,4096,$options)
        try {
            $bytes=[Text.UTF8Encoding]::new($false).GetBytes($json)
            $stream.Write($bytes,0,$bytes.Length); $stream.Flush($true)
        } finally { $stream.Dispose() }
        Protect-IzMaintenancePath $temp | Out-Null
        if ($script:AtomicWriteInterruption) { & $script:AtomicWriteInterruption $canonical }
        if (Test-Path -LiteralPath $canonical) {
            $backup=Join-Path $parent ('.izb-'+[IO.Path]::GetRandomFileName())
            [IO.File]::Replace($temp,$canonical,$backup,$true)
            if($PreviousPath){if(Test-Path $PreviousPath){[IO.File]::Delete($PreviousPath)};[IO.File]::Move($backup,$PreviousPath)}
            elseif(Test-Path $backup){[IO.File]::Delete($backup)}
        } else { [IO.File]::Move($temp,$canonical) }
        Protect-IzMaintenancePath $canonical | Out-Null
    } finally {
        if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force }
        if ($backup -and (Test-Path -LiteralPath $backup)) { Remove-Item -LiteralPath $backup -Force }
    }
    return $canonical
}

function ConvertTo-IzRelativePath {
    param([object]$Value,[string]$Reason='RELATIVE_PATH_INVALID')
    $path=Assert-IzString $Value $Reason
    if (-not $path -or $path.StartsWith('/') -or $path.StartsWith('\') -or $path.Contains('\') -or
        $path.Contains(':') -or ($path -split '/') -contains '.' -or ($path -split '/') -contains '..') {
        throw (New-IzContractError $Reason)
    }
    return $path.Normalize([Text.NormalizationForm]::FormC)
}

function Resolve-IzMarkerRolePath {
    param([object]$Context,[string]$Path,[string]$Role,[switch]$AllowMissing)
    Assert-IzMaintenanceContext $Context | Out-Null
    if ($Role -notin @('maintenance','transaction','stage','previous','verification','temp_helper')) { throw (New-IzContractError 'MARKER_ROLE_INVALID') }
    $canonical=Get-IzCanonicalPath $Path -AllowMissingLeaf:$AllowMissing
    $expected=switch($Role){
        maintenance {$Context.maintenance_root}; transaction {$Context.transaction_root}; stage {$Context.stage_root}
        previous {$Context.previous_root}; verification {$Context.verification_root}; temp_helper {$null}
    }
    if ($Role -eq 'temp_helper') {
        $tempRoot=Get-IzCanonicalPath ([IO.Path]::GetTempPath())
        $expectedName='IZ-CNA-Maintenance-'+$Context.scope_id.Substring(0,16)+'-'+$Context.transaction_id
        if (-not (Split-Path $canonical -Parent).Equals($tempRoot,[StringComparison]::OrdinalIgnoreCase) -or
            (Split-Path $canonical -Leaf) -cne $expectedName) { throw (New-IzContractError 'MARKER_PATH_MISMATCH') }
        foreach($protected in @($Context.install_root,$Context.data_root,$Context.maintenance_root,$Context.package_root)){
            if(-not $protected){continue};$a=ConvertTo-IzPathKey $canonical;$b=ConvertTo-IzPathKey $protected
            if($a -eq $b -or $a.StartsWith($b+'\') -or $b.StartsWith($a+'\')){throw(New-IzContractError 'PATH_OVERLAP')}
        }
    } elseif (-not $expected -or -not $canonical.Equals($expected,[StringComparison]::OrdinalIgnoreCase)) {
        throw (New-IzContractError 'MARKER_PATH_MISMATCH')
    }
    Assert-IzCurrentUserOwner $canonical
    return $canonical
}

function New-IzOwnedRootMarker {
    param([object]$Context,[string]$Path,[ValidateSet('maintenance','transaction','stage','previous','verification','temp_helper')][string]$Role,[Guid]$TransactionId=[Guid]::Empty)
    $root=Resolve-IzMarkerRolePath $Context $Path $Role
    $tx=if($Role -eq 'maintenance'){$null}elseif($TransactionId -ne [Guid]::Empty){$TransactionId.ToString('N')}else{$Context.transaction_id}
    if ($Role -ne 'maintenance' -and -not $tx) { throw (New-IzContractError 'TRANSACTION_ID_REQUIRED') }
    return [pscustomobject][ordered]@{schema='iz-cna-owned-root-v1';product_id=$script:ProductId;owner_sid=$Context.owner_sid;scope_id=$Context.scope_id;role=$Role;transaction_id=$tx;root_path_hash=(Get-IzRootPathHash $root);created_utc=[DateTime]::UtcNow.ToString('o')}
}

function Write-IzOwnedRootMarker {
    param([object]$Context,[string]$Path,[ValidateSet('maintenance','transaction','stage','previous','verification','temp_helper')][string]$Role,[Guid]$TransactionId=[Guid]::Empty)
    $root=Resolve-IzMarkerRolePath $Context $Path $Role
    $marker=New-IzOwnedRootMarker $Context $root $Role $TransactionId
    [void](Write-IzAtomicJson (Join-Path $root '.iz-cna-owned-root.json') $marker $null)
    return $marker
}

function Read-IzOwnedRootMarker {
    param([Parameter(Mandatory)][string]$Path)
    $value=Read-IzStrictJsonFile $Path 'OWNED_ROOT_MARKER_MISSING' 'OWNED_ROOT_MARKER_CORRUPT'
    [void](Assert-IzExactProperties $value @('schema','product_id','owner_sid','scope_id','role','transaction_id','root_path_hash','created_utc') 'OWNED_ROOT_MARKER_INVALID')
    if ($value.schema -ne 'iz-cna-owned-root-v1') { throw (New-IzContractError 'UNSUPPORTED_SCHEMA') }
    foreach($name in @('product_id','owner_sid','scope_id','role','root_path_hash','created_utc')){[void](Assert-IzString $value.$name 'OWNED_ROOT_MARKER_INVALID')}
    if ($null -ne $value.transaction_id -and ($value.transaction_id -isnot [string] -or $value.transaction_id -notmatch '^[0-9a-f]{32}$')) { throw (New-IzContractError 'OWNED_ROOT_MARKER_INVALID') }
    return $value
}

function Test-IzOwnedRootMarker {
    param([object]$Context,[string]$Path,[ValidateSet('maintenance','transaction','stage','previous','verification','temp_helper')][string]$Role,[Guid]$TransactionId=[Guid]::Empty)
    $root=Resolve-IzMarkerRolePath $Context $Path $Role
    $marker=Read-IzOwnedRootMarker (Join-Path $root '.iz-cna-owned-root.json')
    $tx=if($Role -eq 'maintenance'){$null}elseif($TransactionId -ne [Guid]::Empty){$TransactionId.ToString('N')}else{$Context.transaction_id}
    if($marker.product_id -ne $script:ProductId -or $marker.owner_sid -ne $Context.owner_sid -or $marker.scope_id -ne $Context.scope_id -or $marker.role -ne $Role -or $marker.transaction_id -ne $tx -or $marker.root_path_hash -ne (Get-IzRootPathHash $root)){throw (New-IzContractError 'OWNED_ROOT_MARKER_MISMATCH')}
    return $true
}

function ConvertTo-IzOwnedFiles {
    param([object[]]$Files,[switch]$Inventory)
    $result=@(); $seen=@{}
    foreach($file in @($Files)){
        $expected=if($Inventory){@('path','length','sha256','owned')}else{@('path','length','sha256')}
        [void](Assert-IzExactProperties $file $expected 'FILE_RECORD_INVALID')
        $path=ConvertTo-IzRelativePath $file.path
        $key=$path.ToUpperInvariant(); if($seen.ContainsKey($key)){throw (New-IzContractError 'DUPLICATE_FILE_RECORD')};$seen[$key]=$true
        if($file.length -isnot [ValueType] -or [long]$file.length -lt 0 -or [string]$file.sha256 -notmatch $script:Hex64){throw (New-IzContractError 'FILE_RECORD_INVALID')}
        $record=[ordered]@{path=$path;length=[long]$file.length;sha256=[string]$file.sha256}
        if($Inventory){if($file.owned -isnot [bool]){throw (New-IzContractError 'FILE_RECORD_INVALID')};$record.owned=[bool]$file.owned}
        $result += [pscustomobject]$record
    }
    return @($result)
}

function ConvertTo-IzOwnedShortcuts {
    param([object[]]$Shortcuts)
    $result=@();$seen=@{}
    foreach($shortcut in @($Shortcuts)){
        [void](Assert-IzExactProperties $shortcut @('location','name','target_kind','target_relative_path','arguments_sha256') 'SHORTCUT_RECORD_INVALID')
        $name=ConvertTo-IzRelativePath $shortcut.name 'SHORTCUT_RECORD_INVALID'
        if($shortcut.location -notin @('start_menu','desktop') -or $shortcut.target_kind -notin @('installed_relative','system_powershell') -or
            $name.Length -gt 512 -or $name -notmatch '^(?:[^\\/:*?"<>|\x00-\x1f]{1,128}/)*[^\\/:*?"<>|\x00-\x1f]{1,124}\.lnk$' -or
            $shortcut.arguments_sha256 -isnot [string] -or $shortcut.arguments_sha256 -notmatch $script:Hex64){throw (New-IzContractError 'SHORTCUT_RECORD_INVALID')}
        $target=if($shortcut.target_kind -eq 'system_powershell'){
            if($shortcut.target_relative_path -cne 'System32\WindowsPowerShell\v1.0\powershell.exe'){throw(New-IzContractError 'SHORTCUT_RECORD_INVALID')};[string]$shortcut.target_relative_path
        }else{ConvertTo-IzRelativePath $shortcut.target_relative_path 'SHORTCUT_RECORD_INVALID'}
        $key=([string]$shortcut.location+'|'+$name).ToUpperInvariant()
        if($seen.ContainsKey($key)){throw (New-IzContractError 'DUPLICATE_SHORTCUT_RECORD')};$seen[$key]=$true
        $result += [pscustomobject][ordered]@{location=[string]$shortcut.location;name=$name;target_kind=[string]$shortcut.target_kind;target_relative_path=$target;arguments_sha256=[string]$shortcut.arguments_sha256}
    }
    return @($result)
}

function New-IzProgramInventory {
    param([object]$Context,[string]$RootPath,[ValidateSet('stage','previous')][string]$Role,[string]$PayloadIdentity,[object[]]$Files,[Guid]$TransactionId=[Guid]::Empty)
    $root=Resolve-IzMarkerRolePath $Context $RootPath $Role -AllowMissing
    if($PayloadIdentity -notmatch $script:Hex64){throw (New-IzContractError 'PAYLOAD_IDENTITY_INVALID')}
    $tx=if($TransactionId -ne [Guid]::Empty){$TransactionId.ToString('N')}else{$Context.transaction_id}
    return [pscustomobject][ordered]@{schema='iz-cna-program-inventory-v1';product_id=$script:ProductId;owner_sid=$Context.owner_sid;scope_id=$Context.scope_id;transaction_id=$tx;role=$Role;root_path_hash=(Get-IzRootPathHash $root);payload_identity=$PayloadIdentity;files=@(ConvertTo-IzOwnedFiles $Files -Inventory)}
}

function Read-IzProgramInventory {
    param([object]$Context,[string]$Path)
    [void](Assert-IzContainedPath $Path $Context.transaction_root)
    $value=Read-IzStrictJsonFile $Path 'PROGRAM_INVENTORY_MISSING' 'PROGRAM_INVENTORY_CORRUPT'
    [void](Assert-IzExactProperties $value @('schema','product_id','owner_sid','scope_id','transaction_id','role','root_path_hash','payload_identity','files') 'PROGRAM_INVENTORY_INVALID')
    if($value.schema -ne 'iz-cna-program-inventory-v1'){throw (New-IzContractError 'UNSUPPORTED_SCHEMA')}
    $value.files=@(ConvertTo-IzOwnedFiles $value.files -Inventory)
    return $value
}

function Test-IzProgramInventory { param([object]$Context,[object]$Inventory,[string]$RootPath)
    Assert-IzMaintenanceContext $Context|Out-Null
    [void](Assert-IzExactProperties $Inventory @('schema','product_id','owner_sid','scope_id','transaction_id','role','root_path_hash','payload_identity','files') 'PROGRAM_INVENTORY_INVALID')
    $root=Resolve-IzMarkerRolePath $Context $RootPath $Inventory.role
    if($Inventory.schema -cne 'iz-cna-program-inventory-v1' -or $Inventory.product_id -cne $script:ProductId -or $Inventory.owner_sid -cne $Context.owner_sid -or $Inventory.scope_id -cne $Context.scope_id -or $Inventory.transaction_id -cne $Context.transaction_id -or $Inventory.role -notin @('stage','previous') -or $Inventory.root_path_hash -cne (Get-IzRootPathHash $root) -or $Inventory.payload_identity -notmatch $script:Hex64){throw (New-IzContractError 'PROGRAM_INVENTORY_MISMATCH')}
    $files=@(ConvertTo-IzOwnedFiles $Inventory.files -Inventory);$expected=@{};$directories=@{}
    foreach($record in $files){
        $expected[$record.path.ToUpperInvariant()]=$record
        $segments=$record.path.Split('/')
        for($index=1;$index -lt $segments.Count;$index++){$directories[(($segments[0..($index-1)] -join '/').ToUpperInvariant())]=$true}
        $path=Assert-IzContainedPath (Join-Path $root $record.path.Replace('/','\')) $root
        $item=Get-Item -LiteralPath $path -Force
        if($item.PSIsContainer -or ($item.Attributes-band[IO.FileAttributes]::ReparsePoint) -ne 0 -or [long]$item.Length -ne [long]$record.length -or (Get-IzFileSha256 $path) -cne $record.sha256){throw(New-IzContractError 'PROGRAM_INVENTORY_MISMATCH')}
        Assert-IzCurrentUserOwner $path
    }
    $actual=@{};$pending=[Collections.Stack]::new();$pending.Push($root)
    while($pending.Count){
        $parent=[string]$pending.Pop()
        foreach($item in @(Get-ChildItem -LiteralPath $parent -Force)){
            if(($item.Attributes-band[IO.FileAttributes]::ReparsePoint) -ne 0){throw(New-IzContractError 'PROGRAM_INVENTORY_MISMATCH')}
            Assert-IzCurrentUserOwner $item.FullName
            $relative=$item.FullName.Substring($root.Length+1).Replace('\','/')
            if($item.PSIsContainer){if(-not $directories.ContainsKey($relative.ToUpperInvariant())){throw(New-IzContractError 'PROGRAM_INVENTORY_MISMATCH')};$pending.Push($item.FullName)}
            elseif($relative -cne '.iz-cna-owned-root.json'){$actual[$relative.ToUpperInvariant()]=$true}
        }
    }
    if($actual.Count -ne $expected.Count -or @($actual.Keys|Where-Object{-not $expected.ContainsKey($_)}).Count){throw(New-IzContractError 'PROGRAM_INVENTORY_MISMATCH')}
    return $true
}

function New-IzDataIdentity {
    param([object]$Context,[string]$SelectedDatabasePath)
    Assert-IzMaintenanceContext $Context|Out-Null
    $database=Assert-IzContainedPath $SelectedDatabasePath $Context.data_root -AllowMissingLeaf
    $relative=$database.Substring($Context.data_root.TrimEnd('\').Length+1)
    $relativeKey=(ConvertTo-IzPathKey ('C:\'+$relative)).Substring(3)
    $inputValue="iz-cna-data-identity-v1`n$script:ProductId`n$($Context.owner_sid)`n$(ConvertTo-IzPathKey $Context.data_root)`n$relativeKey"
    return [pscustomobject][ordered]@{data_identity=(Get-IzUtf8Sha256 $inputValue);database_relative_path=$relative}
}

function ConvertTo-IzManifest {
    param([object]$Value)
    [void](Assert-IzExactProperties $Value @('schema','product_id','version','build','installer_revision','release_channel','compatibility','payload_identity','files') 'MANIFEST_INVALID')
    if($Value.schema -ne 'iz-cna-release-manifest-v1'){throw (New-IzContractError 'UNSUPPORTED_SCHEMA')}
    if($Value.product_id -ne $script:ProductId){throw (New-IzContractError 'PRODUCT_ID_MISMATCH')}
    [void](New-IzReleaseIdentity $Value.version $Value.build ([int]$Value.installer_revision) $Value.payload_identity)
    [void](Assert-IzExactProperties $Value.compatibility @('source_version_minimum','source_version_maximum','source_build_minimum','source_build_maximum','source_schema_minimum','source_schema_maximum','target_schema') 'MANIFEST_COMPATIBILITY_INVALID')
    [void](ConvertTo-IzSemanticVersion $Value.compatibility.source_version_minimum);[void](ConvertTo-IzSemanticVersion $Value.compatibility.source_version_maximum)
    [void](ConvertTo-IzBuildVersion $Value.compatibility.source_build_minimum);[void](ConvertTo-IzBuildVersion $Value.compatibility.source_build_maximum)
    $Value.files=@(ConvertTo-IzOwnedFiles $Value.files)
    for($index=1;$index -lt $Value.files.Count;$index++){if([StringComparer]::Ordinal.Compare($Value.files[$index-1].path,$Value.files[$index].path) -ge 0){throw(New-IzContractError 'MANIFEST_FILE_ORDER_INVALID')}}
    $records=@($Value.files|ForEach-Object{"$($_.path)`t$($_.length)`t$($_.sha256)`n"}) -join ''
    if((Get-IzUtf8Sha256 $records) -ne $Value.payload_identity){throw (New-IzContractError 'PAYLOAD_IDENTITY_MISMATCH')}
    return $Value
}

function Read-IzReleaseManifest {
    param([Parameter(Mandatory)][string]$PackageRoot,[string]$ManifestPath)
    $root=Get-IzCanonicalPath $PackageRoot
    $path=if($ManifestPath){Assert-IzContainedPath $ManifestPath $root}else{Join-Path $root 'release-manifest.json'}
    return ConvertTo-IzManifest (Read-IzStrictJsonFile $path 'MANIFEST_MISSING' 'MANIFEST_CORRUPT')
}

function Test-IzReleasePayload {
    param([string]$PackageRoot,[object]$Manifest)
    $root=Get-IzCanonicalPath $PackageRoot
    $value=ConvertTo-IzManifest $Manifest
    $listed=@{}
    foreach($record in $value.files){
        $path=Assert-IzContainedPath (Join-Path $root $record.path.Replace('/','\')) $root
        if(-not(Test-Path $path -PathType Leaf)-or (Get-Item $path).Length -ne $record.length -or (Get-IzFileSha256 $path) -ne $record.sha256){throw (New-IzContractError 'PAYLOAD_FILE_MISMATCH')}
        $listed[$record.path.ToUpperInvariant()]=$true
    }
    foreach($required in $script:RequiredPayloadFiles){
        if(-not $listed.ContainsKey($required.ToUpperInvariant())){throw(New-IzContractError 'PAYLOAD_REQUIRED_FILE_MISSING')}
    }
    if(-not @($value.files|Where-Object{$_.path.StartsWith('app/frontend/dist/assets/',[StringComparison]::OrdinalIgnoreCase)}).Count -or
       -not @($value.files|Where-Object{$_.path.StartsWith('app/config/rules/',[StringComparison]::OrdinalIgnoreCase)}).Count){throw(New-IzContractError 'PAYLOAD_REQUIRED_FILE_MISSING')}
    $actual=@(Get-ChildItem -LiteralPath $root -File -Recurse -Force|ForEach-Object{$_.FullName.Substring($root.Length+1).Replace('\','/')}|Where-Object{$_ -ne 'release-manifest.json'})
    if($actual.Count -ne $listed.Count -or @($actual|Where-Object{-not $listed.ContainsKey($_.ToUpperInvariant())}).Count){throw (New-IzContractError 'PAYLOAD_FILE_SET_MISMATCH')}
    return $true
}

function New-IzInstallReceipt {
    param([object]$Context,[string]$DataIdentity,[object]$ReleaseIdentity,[object[]]$OwnedFiles,[object[]]$OwnedShortcuts,[Guid]$LastCommittedTransaction)
    Assert-IzMaintenanceContext $Context|Out-Null;$release=Assert-IzReleaseIdentityObject $ReleaseIdentity
    if($DataIdentity -notmatch $script:Hex64){throw (New-IzContractError 'DATA_IDENTITY_INVALID')}
    $files=@(ConvertTo-IzOwnedFiles $OwnedFiles);$shortcuts=@(ConvertTo-IzOwnedShortcuts $OwnedShortcuts)
    $installIdentity=Get-IzUtf8Sha256 "iz-cna-install-identity-v1`n$script:ProductId`n$($Context.owner_sid)`n$(ConvertTo-IzPathKey $Context.install_root)"
    return [pscustomobject][ordered]@{schema='iz-cna-install-receipt-v1';product_id=$script:ProductId;owner_sid=$Context.owner_sid;scope_id=$Context.scope_id;install_identity=$installIdentity;data_identity=$DataIdentity;version=$release.version;build=$release.build;installer_revision=$release.installer_revision;payload_identity=$release.payload_identity;owned_files=$files;owned_shortcuts=$shortcuts;last_committed_transaction=$LastCommittedTransaction.ToString('N');recovery_format='IZCNABK2';written_utc=[DateTime]::UtcNow.ToString('o')}
}

function ConvertTo-IzInstallReceipt {
    param([object]$Context,[object]$Value)
    Assert-IzMaintenanceContext $Context|Out-Null
    [void](Assert-IzExactProperties $Value @('schema','product_id','owner_sid','scope_id','install_identity','data_identity','version','build','installer_revision','payload_identity','owned_files','owned_shortcuts','last_committed_transaction','recovery_format','written_utc') 'INSTALL_RECEIPT_INVALID')
    if($Value.schema -ne 'iz-cna-install-receipt-v1'){throw (New-IzContractError 'UNSUPPORTED_SCHEMA')}
    if($Value.product_id -ne $script:ProductId -or $Value.owner_sid -ne $Context.owner_sid -or $Value.scope_id -ne $Context.scope_id){throw (New-IzContractError 'INSTALL_RECEIPT_IDENTITY_MISMATCH')}
    [void](New-IzReleaseIdentity $Value.version $Value.build ([int]$Value.installer_revision) $Value.payload_identity)
    $expectedInstall=Get-IzUtf8Sha256 "iz-cna-install-identity-v1`n$script:ProductId`n$($Context.owner_sid)`n$(ConvertTo-IzPathKey $Context.install_root)"
    if($Value.install_identity -ne $expectedInstall -or $Value.data_identity -notmatch $script:Hex64 -or $Value.last_committed_transaction -notmatch '^[0-9a-f]{32}$' -or $Value.recovery_format -ne 'IZCNABK2'){throw (New-IzContractError 'INSTALL_RECEIPT_INVALID')}
    $Value.owned_files=@(ConvertTo-IzOwnedFiles $Value.owned_files);$Value.owned_shortcuts=@(ConvertTo-IzOwnedShortcuts $Value.owned_shortcuts);return $Value
}

function Read-IzInstallReceipt { param([object]$Context) return ConvertTo-IzInstallReceipt $Context (Read-IzStrictJsonFile $Context.install_receipt_path 'INSTALL_RECEIPT_MISSING' 'INSTALL_RECEIPT_CORRUPT') }
function Write-IzInstallReceipt {
    param([object]$Context,[object]$Receipt,[AllowNull()][object]$ExpectedPreviousSha256)
    $value=ConvertTo-IzInstallReceipt $Context $Receipt;$exists=Test-Path $Context.install_receipt_path
    if($null -eq $ExpectedPreviousSha256){if($exists){throw(New-IzContractError 'INSTALL_RECEIPT_CONFLICT')}}elseif($ExpectedPreviousSha256 -isnot [string] -or $ExpectedPreviousSha256 -notmatch $script:Hex64 -or -not $exists -or (Get-IzFileSha256 $Context.install_receipt_path) -ne $ExpectedPreviousSha256){throw(New-IzContractError 'INSTALL_RECEIPT_CONFLICT')}
    [void](Write-IzAtomicJson $Context.install_receipt_path $value $null);return $value
}

function New-IzMaintenanceResult {
    param([ValidateSet('AutoInstall','Repair','Uninstall','RemoveData','Recover','Status')][string]$Action,[ValidateSet('SUCCEEDED','NO_OP','CANCELLED','PREFLIGHT_FAILED','BUSY','ROLLED_BACK','RECOVERY_REQUIRED','REMOVAL_INCOMPLETE','REMOVED_CLEANUP_PENDING')][string]$Status,[AllowNull()][object]$ReleaseIdentity,[AllowNull()][object]$TransactionId,[ValidateSet('CHECKING','PREPARING_FILES','CLOSING_APP','PROTECTING_DATA','INSTALLING','CHECKING_STARTUP','RECOVERING','REMOVING','CLEANING_UP','FINISHED')][string]$Stage,[int]$Code,[string]$Reason,[string[]]$Evidence=@(),[string]$StartedUtc=([DateTime]::UtcNow.ToString('o')))
    $codes=@{SUCCEEDED=0;NO_OP=0;CANCELLED=10;PREFLIGHT_FAILED=20;BUSY=21;ROLLED_BACK=30;RECOVERY_REQUIRED=31;REMOVAL_INCOMPLETE=40;REMOVED_CLEANUP_PENDING=41}
    if($codes[$Status] -ne $Code -or $Reason -notmatch '^[A-Z][A-Z0-9_]{0,63}$'){throw(New-IzContractError 'RESULT_INVALID')}
    foreach($item in $Evidence){[void](ConvertTo-IzRelativePath $item 'RESULT_EVIDENCE_INVALID')}
    $release=if($ReleaseIdentity){Assert-IzReleaseIdentityObject $ReleaseIdentity}else{$null};$tx=if($TransactionId){([Guid]$TransactionId).ToString('N')}else{$null}
    return [pscustomobject][ordered]@{schema='iz-cna-maintenance-result-v1';product_id=$script:ProductId;action=$Action;status=$Status;version=$(if($release){$release.version}else{$null});build=$(if($release){$release.build}else{$null});installer_revision=$(if($release){$release.installer_revision}else{$null});transaction_id=$tx;stage=$Stage;code=$Code;reason=$Reason;evidence=@($Evidence);started_utc=$StartedUtc;completed_utc=[DateTime]::UtcNow.ToString('o')}
}

function ConvertTo-IzMaintenanceResult { param([object]$Value)
    if($null -ne $Value -and $Value.PSObject.Properties['schema'] -and $Value.schema -ne 'iz-cna-maintenance-result-v1'){throw(New-IzContractError 'UNSUPPORTED_SCHEMA')}
    [void](Assert-IzExactProperties $Value @('schema','product_id','action','status','version','build','installer_revision','transaction_id','stage','code','reason','evidence','started_utc','completed_utc') 'RESULT_INVALID')
    if($Value.product_id -ne $script:ProductId){throw(New-IzContractError 'RESULT_INVALID')}
    $release=if($null -ne $Value.version){New-IzReleaseIdentity $Value.version $Value.build ([int]$Value.installer_revision) ('0'*64)}else{$null}
    [void](New-IzMaintenanceResult $Value.action $Value.status $release $Value.transaction_id $Value.stage ([int]$Value.code) $Value.reason @($Value.evidence) $Value.started_utc);return $Value
}
function Read-IzMaintenanceResult { param([string]$Path) return ConvertTo-IzMaintenanceResult (Read-IzStrictJsonFile $Path 'RESULT_MISSING' 'RESULT_CORRUPT') }
function Write-IzMaintenanceResult { param([string]$ResultPath,[object]$Result) $value=ConvertTo-IzMaintenanceResult $Result;[void](Write-IzAtomicJson $ResultPath $value $null);return $value }

Export-ModuleMember -Function Assert-IzExactProperties,Read-IzStrictJsonFile,Write-IzAtomicJson,Get-IzFileSha256,ConvertTo-IzRelativePath,New-IzOwnedRootMarker,Write-IzOwnedRootMarker,Read-IzOwnedRootMarker,Test-IzOwnedRootMarker,New-IzProgramInventory,Read-IzProgramInventory,Test-IzProgramInventory,New-IzDataIdentity,ConvertTo-IzManifest,Read-IzReleaseManifest,Test-IzReleasePayload,New-IzInstallReceipt,ConvertTo-IzInstallReceipt,Read-IzInstallReceipt,Write-IzInstallReceipt,New-IzMaintenanceResult,Read-IzMaintenanceResult,Write-IzMaintenanceResult
