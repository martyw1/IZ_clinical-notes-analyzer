Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -Force -ErrorAction Stop

$script:ProductId = 'r3.iz-clinical-notes-analyzer.desktop'
$script:ContextSchema = 'iz-cna-maintenance-context-v1'
$script:Hex64 = '^[0-9a-f]{64}$'

function New-IzPathError {
    param([string]$Reason, [int]$Code = 20)
    $exception = [IO.InvalidDataException]::new($Reason)
    $exception.Data['iz_reason'] = $Reason
    $exception.Data['iz_exit_code'] = $Code
    return $exception
}

function Get-IzCurrentUserSid {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not $identity.User) { throw (New-IzPathError 'CURRENT_USER_SID_UNAVAILABLE') }
    return $identity.User.Value
}

function Get-IzUtf8Sha256 {
    param([Parameter(Mandatory)][AllowEmptyString()][string]$Value)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes($Value)
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    } finally { $sha.Dispose() }
}

function Assert-IzPathSyntax {
    param([Parameter(Mandatory)][string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path -notmatch '^[A-Za-z]:[\\/]') {
        throw (New-IzPathError 'PATH_NOT_LOCAL_ABSOLUTE')
    }
    if ($Path.StartsWith('\\', [StringComparison]::Ordinal) -or
        $Path.StartsWith('\\?\', [StringComparison]::Ordinal) -or
        $Path.StartsWith('\\.\', [StringComparison]::Ordinal)) {
        throw (New-IzPathError 'PATH_DEVICE_OR_UNC')
    }
    if ($Path.Substring(2).Contains(':')) { throw (New-IzPathError 'PATH_ALTERNATE_DATA_STREAM') }
    if ($Path.IndexOfAny([char[]]@([char]0, [char]10, [char]13)) -ge 0) {
        throw (New-IzPathError 'PATH_CONTROL_CHARACTER')
    }
    foreach ($segment in ($Path.Substring(2) -split '[\\/]')) {
        if ($segment -eq '.' -or $segment -eq '..') { throw (New-IzPathError 'PATH_TRAVERSAL') }
        if ($segment.EndsWith(' ', [StringComparison]::Ordinal) -or
            $segment.EndsWith('.', [StringComparison]::Ordinal)) {
            throw (New-IzPathError 'PATH_AMBIGUOUS_SEGMENT')
        }
        $base = ($segment -split '\.')[0]
        if ($base -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$') {
            throw (New-IzPathError 'PATH_RESERVED_NAME')
        }
    }
}

function Get-IzCanonicalPath {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Path,
        [switch]$AllowMissingLeaf
    )
    Assert-IzPathSyntax -Path $Path
    try { $full = [IO.Path]::GetFullPath($Path).Replace('/', '\') }
    catch { throw (New-IzPathError 'PATH_INVALID') }
    $root = [IO.Path]::GetPathRoot($full)
    if ($full.Length -gt $root.Length) { $full = $full.TrimEnd('\') }

    $probe = $full
    while (-not (Test-Path -LiteralPath $probe)) {
        if (-not $AllowMissingLeaf) { throw (New-IzPathError 'PATH_NOT_FOUND') }
        $parent = [IO.Path]::GetDirectoryName($probe)
        if ([string]::IsNullOrEmpty($parent) -or $parent -eq $probe) { break }
        $probe = $parent
    }
    if (Test-Path -LiteralPath $probe) {
        $cursor = [IO.Path]::GetPathRoot($probe)
        $relative = $probe.Substring($cursor.Length)
        foreach ($segment in ($relative -split '\\')) {
            if (-not $segment) { continue }
            $cursor = Join-Path $cursor $segment
            $item = Get-Item -LiteralPath $cursor -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw (New-IzPathError 'PATH_REPARSE_POINT')
            }
        }
    }
    return $full
}

function ConvertTo-IzPathKey {
    param([Parameter(Mandatory)][string]$Path)
    $canonical = Get-IzCanonicalPath -Path $Path -AllowMissingLeaf
    $normalized = $canonical.Normalize([Text.NormalizationForm]::FormC)
    $builder = [Text.StringBuilder]::new($normalized.Length)
    foreach ($character in $normalized.ToCharArray()) {
        $code = [int]$character
        if ($code -ge 65 -and $code -le 90) { [void]$builder.Append([char]($code + 32)) }
        else { [void]$builder.Append($character) }
    }
    return $builder.ToString()
}

function Get-IzRootPathHash {
    param([Parameter(Mandatory)][string]$Path)
    return Get-IzUtf8Sha256 -Value ("iz-cna-root-path-v1`n" + (ConvertTo-IzPathKey -Path $Path))
}

function Get-IzExistingOwnerSid {
    param([Parameter(Mandatory)][string]$Path)
    $probe = $Path
    while (-not (Test-Path -LiteralPath $probe)) {
        $probe = [IO.Path]::GetDirectoryName($probe)
        if (-not $probe) { throw (New-IzPathError 'PATH_OWNER_UNAVAILABLE') }
    }
    try {
        $owner = (Get-Acl -LiteralPath $probe).GetOwner([Security.Principal.SecurityIdentifier])
        if(-not $owner){throw 'OWNER_SID_EMPTY'}
        return $owner.Value
    } catch { throw (New-IzPathError 'PATH_OWNER_UNAVAILABLE') }
}

function Assert-IzCurrentUserOwner {
    param([Parameter(Mandatory)][string]$Path)
    if ((Get-IzExistingOwnerSid -Path $Path) -ne (Get-IzCurrentUserSid)) {
        throw (New-IzPathError 'PATH_OWNER_MISMATCH')
    }
}

function Assert-IzContainedPath {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Parent,
        [switch]$AllowEqual,
        [switch]$AllowMissingLeaf
    )
    $childPath = Get-IzCanonicalPath -Path $Path -AllowMissingLeaf:$AllowMissingLeaf
    $parentPath = Get-IzCanonicalPath -Path $Parent -AllowMissingLeaf
    if ($AllowEqual -and $childPath.Equals($parentPath, [StringComparison]::OrdinalIgnoreCase)) {
        return $childPath
    }
    if (-not $childPath.StartsWith($parentPath.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw (New-IzPathError 'PATH_OUTSIDE_SCOPE')
    }
    return $childPath
}

function Get-IzScopeId {
    param([string]$OwnerSid, [string]$InstallRoot, [string]$DataRoot)
    $inputValue = "iz-cna-maintenance-scope-v1`n$script:ProductId`n$OwnerSid`n$(ConvertTo-IzPathKey $InstallRoot)`n$(ConvertTo-IzPathKey $DataRoot)"
    return Get-IzUtf8Sha256 $inputValue
}

function Get-IzKnownFolderPath {
    param([Environment+SpecialFolder]$Folder)
    $path=[Environment]::GetFolderPath($Folder,[Environment+SpecialFolderOption]::DoNotVerify)
    if([string]::IsNullOrWhiteSpace($path)){throw(New-IzPathError 'KNOWN_FOLDER_UNAVAILABLE')}
    return Get-IzCanonicalPath $path -AllowMissingLeaf
}

function Assert-IzInheritedPathMatches {
    param([AllowNull()][string]$Inherited,[string]$KnownPath)
    if($Inherited -and -not (Get-IzCanonicalPath $Inherited -AllowMissingLeaf).Equals($KnownPath,[StringComparison]::OrdinalIgnoreCase)){throw(New-IzPathError 'KNOWN_FOLDER_OVERRIDE_CONFLICT')}
}

function Get-IzMaintenanceContext {
    [CmdletBinding()]
    param(
        [string]$PackageRoot,
        [Guid]$TransactionId = [Guid]::Empty,
        [string]$ComponentTestRoot
    )
    $sid = Get-IzCurrentUserSid
    if ($PSBoundParameters.ContainsKey('ComponentTestRoot')) {
        $component = Get-IzCanonicalPath -Path $ComponentTestRoot
        if ((Split-Path $component -Leaf) -notmatch '^iz-cna-component-[0-9a-f]{12}$' -or
            -not (Test-Path -LiteralPath $component -PathType Container)) {
            throw (New-IzPathError 'COMPONENT_ROOT_INVALID')
        }
        Assert-IzCurrentUserOwner $component
        $local = Join-Path $component 'LocalAppData'
        $appData = Join-Path $component 'AppData'
        $profile = Join-Path $component 'UserProfile'
        $startMenu = Join-Path $appData 'Microsoft\Windows\Start Menu\Programs'
        $desktop = Join-Path $profile 'Desktop'
    } else {
        $local = Get-IzKnownFolderPath ([Environment+SpecialFolder]::LocalApplicationData)
        $appData = Get-IzKnownFolderPath ([Environment+SpecialFolder]::ApplicationData)
        $profile = Get-IzKnownFolderPath ([Environment+SpecialFolder]::UserProfile)
        $startMenu = Get-IzKnownFolderPath ([Environment+SpecialFolder]::Programs)
        $desktop = Get-IzKnownFolderPath ([Environment+SpecialFolder]::DesktopDirectory)
        Assert-IzInheritedPathMatches $env:LOCALAPPDATA $local;Assert-IzInheritedPathMatches $env:APPDATA $appData;Assert-IzInheritedPathMatches $env:USERPROFILE $profile
        foreach($known in @($local,$appData,$profile,$startMenu,$desktop)){Assert-IzCurrentUserOwner $known}
    }
    $local = Get-IzCanonicalPath $local -AllowMissingLeaf
    $programParent = Join-Path $local 'Programs'
    $install = Join-Path $programParent 'IZ Clinical Notes Analyzer'
    $data = Join-Path $local 'IZ Clinical Notes Analyzer'
    $maintenance = Join-Path $local 'IZ Clinical Notes Analyzer Maintenance'
    $state = Join-Path $maintenance 'state'
    $transactions = Join-Path $maintenance 'transactions'
    $txText = if ($TransactionId -eq [Guid]::Empty) { $null } else { $TransactionId.ToString('N') }
    $transactionRoot = if ($txText) { Join-Path $transactions $txText } else { $null }
    $package = if ($PackageRoot) { Get-IzCanonicalPath $PackageRoot } else { $null }
    $scope = Get-IzScopeId $sid $install $data
    $object = [ordered]@{
        schema=$script:ContextSchema; product_id=$script:ProductId; owner_sid=$sid; scope_id=$scope
        local_app_data_root=$local; program_parent=$programParent; install_root=$install; data_root=$data
        maintenance_root=$maintenance; state_root=$state; transactions_root=$transactions
        journal_path=(Join-Path $state 'maintenance-journal.json'); journal_previous_path=(Join-Path $state 'maintenance-journal.previous.json')
        install_receipt_path=(Join-Path $state 'install-receipt.json'); operation_lock_path=(Join-Path $state 'operation.lock')
        lock_owner_path=(Join-Path $state 'lock-owner.json'); runtime_identity_path=(Join-Path $state 'runtime-identity.json')
        start_menu_root=$startMenu; desktop_root=$desktop
        package_root=$package; transaction_id=$txText; transaction_root=$transactionRoot
        stage_root=$(if ($txText) { Join-Path $programParent "IZ Clinical Notes Analyzer.stage-$txText" } else { $null })
        previous_root=$(if ($txText) { Join-Path $programParent "IZ Clinical Notes Analyzer.previous-$txText" } else { $null })
        snapshot_path=$(if ($txText) { Join-Path $transactionRoot 'snapshot\pre-change.izcnabackup' } else { $null })
        verification_root=$(if ($txText) { Join-Path $transactionRoot 'verification' } else { $null })
        requests_root=$(if ($txText) { Join-Path $transactionRoot 'requests' } else { $null })
        results_root=$(if ($txText) { Join-Path $transactionRoot 'results' } else { $null })
        pipe_name=('iz-cna-runtime-v1-' + $scope.Substring(0,32))
    }
    $context = [pscustomobject]$object
    $context.PSObject.TypeNames.Insert(0, 'IzCna.MaintenanceContext')
    Assert-IzMaintenanceContext $context | Out-Null
    return $context
}

function Assert-IzContextPath {
    param([AllowNull()][object]$Actual,[AllowNull()][object]$Expected)
    if($null -eq $Expected){if($null -ne $Actual){throw(New-IzPathError 'CONTEXT_PATH_MISMATCH')};return}
    if($Actual -isnot [string]){throw(New-IzPathError 'CONTEXT_PATH_MISMATCH')}
    $actualPath=Get-IzCanonicalPath ([string]$Actual) -AllowMissingLeaf
    $expectedPath=Get-IzCanonicalPath ([string]$Expected) -AllowMissingLeaf
    if(-not $actualPath.Equals($expectedPath,[StringComparison]::OrdinalIgnoreCase)){throw(New-IzPathError 'CONTEXT_PATH_MISMATCH')}
}

function Assert-IzMaintenanceContext {
    param([Parameter(Mandatory)][object]$Context)
    $expected = @('schema','product_id','owner_sid','scope_id','local_app_data_root','program_parent','install_root','data_root','maintenance_root','state_root','transactions_root','journal_path','journal_previous_path','install_receipt_path','operation_lock_path','lock_owner_path','runtime_identity_path','start_menu_root','desktop_root','package_root','transaction_id','transaction_root','stage_root','previous_root','snapshot_path','verification_root','requests_root','results_root','pipe_name')
    $actual = @($Context.PSObject.Properties.Name)
    if ($actual.Count -ne $expected.Count -or @($expected | Where-Object { $_ -notin $actual }).Count) { throw (New-IzPathError 'CONTEXT_INVALID') }
    if ($Context.schema -ne $script:ContextSchema -or $Context.product_id -ne $script:ProductId -or $Context.owner_sid -ne (Get-IzCurrentUserSid)) { throw (New-IzPathError 'CONTEXT_IDENTITY_MISMATCH') }
    $local=Get-IzCanonicalPath ([string]$Context.local_app_data_root) -AllowMissingLeaf
    $component=Split-Path $local -Parent
    $isComponent=(Split-Path $component -Leaf) -match '^iz-cna-component-[0-9a-f]{12}$' -and $local.Equals((Join-Path $component 'LocalAppData'),[StringComparison]::OrdinalIgnoreCase)
    if($isComponent){Assert-IzCurrentUserOwner $component;$appData=Join-Path $component 'AppData';$profile=Join-Path $component 'UserProfile';$startMenu=Join-Path $appData 'Microsoft\Windows\Start Menu\Programs';$desktop=Join-Path $profile 'Desktop'}
    else{$expectedLocal=Get-IzKnownFolderPath ([Environment+SpecialFolder]::LocalApplicationData);Assert-IzContextPath $local $expectedLocal;$appData=Get-IzKnownFolderPath ([Environment+SpecialFolder]::ApplicationData);$profile=Get-IzKnownFolderPath ([Environment+SpecialFolder]::UserProfile);$startMenu=Get-IzKnownFolderPath ([Environment+SpecialFolder]::Programs);$desktop=Get-IzKnownFolderPath ([Environment+SpecialFolder]::DesktopDirectory);Assert-IzInheritedPathMatches $env:LOCALAPPDATA $expectedLocal;Assert-IzInheritedPathMatches $env:APPDATA $appData;Assert-IzInheritedPathMatches $env:USERPROFILE $profile}
    $programParent=Join-Path $local 'Programs';$install=Join-Path $programParent 'IZ Clinical Notes Analyzer';$data=Join-Path $local 'IZ Clinical Notes Analyzer';$maintenance=Join-Path $local 'IZ Clinical Notes Analyzer Maintenance';$state=Join-Path $maintenance 'state';$transactions=Join-Path $maintenance 'transactions'
    $fixed=[ordered]@{program_parent=$programParent;install_root=$install;data_root=$data;maintenance_root=$maintenance;state_root=$state;transactions_root=$transactions;journal_path=(Join-Path $state 'maintenance-journal.json');journal_previous_path=(Join-Path $state 'maintenance-journal.previous.json');install_receipt_path=(Join-Path $state 'install-receipt.json');operation_lock_path=(Join-Path $state 'operation.lock');lock_owner_path=(Join-Path $state 'lock-owner.json');runtime_identity_path=(Join-Path $state 'runtime-identity.json');start_menu_root=$startMenu;desktop_root=$desktop}
    foreach($entry in $fixed.GetEnumerator()){Assert-IzContextPath $Context.($entry.Key) $entry.Value}
    if ($Context.scope_id -ne (Get-IzScopeId $Context.owner_sid $Context.install_root $Context.data_root)) { throw (New-IzPathError 'CONTEXT_SCOPE_MISMATCH') }
    foreach ($pair in @(@($Context.install_root,$Context.data_root),@($Context.install_root,$Context.maintenance_root),@($Context.data_root,$Context.maintenance_root))) {
        $a=(ConvertTo-IzPathKey $pair[0]); $b=(ConvertTo-IzPathKey $pair[1])
        if ($a -eq $b -or $a.StartsWith($b+'\') -or $b.StartsWith($a+'\')) { throw (New-IzPathError 'PATH_OVERLAP') }
    }
    if ($Context.transaction_id) {
        if ($Context.transaction_id -notmatch '^[0-9a-f]{32}$') { throw (New-IzPathError 'TRANSACTION_ID_INVALID') }
        $txRoot=Join-Path $transactions $Context.transaction_id
        $derived=[ordered]@{transaction_root=$txRoot;stage_root=(Join-Path $programParent "IZ Clinical Notes Analyzer.stage-$($Context.transaction_id)");previous_root=(Join-Path $programParent "IZ Clinical Notes Analyzer.previous-$($Context.transaction_id)");snapshot_path=(Join-Path $txRoot 'snapshot\pre-change.izcnabackup');verification_root=(Join-Path $txRoot 'verification');requests_root=(Join-Path $txRoot 'requests');results_root=(Join-Path $txRoot 'results')}
        foreach($entry in $derived.GetEnumerator()){Assert-IzContextPath $Context.($entry.Key) $entry.Value}
    }else{foreach($name in @('transaction_root','stage_root','previous_root','snapshot_path','verification_root','requests_root','results_root')){if($null -ne $Context.$name){throw(New-IzPathError 'CONTEXT_PATH_MISMATCH')}}}
    if($Context.pipe_name -cne ('iz-cna-runtime-v1-'+$Context.scope_id.Substring(0,32))){throw(New-IzPathError 'CONTEXT_PATH_MISMATCH')}
    $bounded=@($Context.journal_path,$Context.journal_previous_path,$Context.install_receipt_path,$Context.operation_lock_path,$Context.lock_owner_path,$Context.runtime_identity_path)
    foreach($root in @($Context.maintenance_root,$Context.transaction_root,$Context.stage_root,$Context.previous_root,$Context.verification_root)){if($root){$bounded+=Join-Path $root '.iz-cna-owned-root.json'}}
    if(@($bounded|Where-Object{$_.Length -gt 259}).Count){throw(New-IzPathError 'PATH_TOO_LONG')}
    if($Context.package_root){$package=Get-IzCanonicalPath $Context.package_root;Assert-IzCurrentUserOwner $package;foreach($root in @($install,$data,$maintenance)){$a=ConvertTo-IzPathKey $package;$b=ConvertTo-IzPathKey $root;if($a -eq $b -or $a.StartsWith($b+'\') -or $b.StartsWith($a+'\')){throw(New-IzPathError 'PATH_OVERLAP')}}}
    return $Context
}

function Protect-IzMaintenancePath {
    param([Parameter(Mandatory)][string]$Path)
    $canonical = Get-IzCanonicalPath $Path
    Assert-IzCurrentUserOwner $canonical
    $sid = [Security.Principal.SecurityIdentifier]::new((Get-IzCurrentUserSid))
    $item = Get-Item -LiteralPath $canonical -Force
    if ($item.PSIsContainer) {
        & "$env:SystemRoot\System32\icacls.exe" $canonical '/inheritance:r' '/grant:r' "*$($sid.Value):(OI)(CI)F" | Out-Null
    } else {
        & "$env:SystemRoot\System32\icacls.exe" $canonical '/inheritance:r' '/grant:r' "*$($sid.Value):F" | Out-Null
    }
    if($LASTEXITCODE -ne 0){throw(New-IzPathError 'PATH_ACL_FAILED')}
    return $canonical
}

function Get-IzExternalBackupPublicationPaths {
    param([Parameter(Mandatory)][object]$Context,[Parameter(Mandatory)][string]$BackupPath,[Parameter(Mandatory)][Guid]$TransactionId)
    Assert-IzMaintenanceContext $Context | Out-Null
    $final = Get-IzCanonicalPath $BackupPath -AllowMissingLeaf
    $parent = Get-IzCanonicalPath ([IO.Path]::GetDirectoryName($final))
    Assert-IzCurrentUserOwner $parent
    foreach ($root in @($Context.install_root,$Context.data_root,$Context.maintenance_root,$Context.package_root)) {
        if (-not $root) { continue }
        $f=ConvertTo-IzPathKey $final; $r=ConvertTo-IzPathKey $root
        if ($f -eq $r -or $f.StartsWith($r+'\') -or $r.StartsWith($f+'\')) { throw (New-IzPathError 'BACKUP_DESTINATION_OVERLAP') }
    }
    $partial = $final + '.partial-' + $TransactionId.ToString('N')
    if ((Test-Path -LiteralPath $final) -or (Test-Path -LiteralPath $partial)) { throw (New-IzPathError 'BACKUP_DESTINATION_EXISTS') }
    return [pscustomobject][ordered]@{ final_path=$final; partial_path=$partial }
}

function Assert-IzExternalBackupDestination {
    param([Parameter(Mandatory)][object]$Context,[Parameter(Mandatory)][string]$BackupPath,[Parameter(Mandatory)][Guid]$TransactionId)
    return Get-IzExternalBackupPublicationPaths -Context $Context -BackupPath $BackupPath -TransactionId $TransactionId
}

Export-ModuleMember -Function Get-IzCurrentUserSid,Get-IzCanonicalPath,ConvertTo-IzPathKey,Get-IzRootPathHash,Get-IzUtf8Sha256,Assert-IzCurrentUserOwner,Assert-IzContainedPath,Get-IzMaintenanceContext,Assert-IzMaintenanceContext,Protect-IzMaintenancePath,Get-IzExternalBackupPublicationPaths,Assert-IzExternalBackupDestination
