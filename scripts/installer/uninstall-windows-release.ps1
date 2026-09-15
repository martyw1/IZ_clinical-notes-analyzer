[CmdletBinding()]
param(
    [ValidateSet('Uninstall', 'RemoveData')]
    [string]$Action = 'Uninstall',
    [string]$PackageRoot = '',
    [switch]$NoPause,
    [switch]$NonInteractive,
    [string]$ResultPath = '',
    [switch]$NoRun
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$script:RemovalMutationObserved = $false
$script:CommonModulePath = Join-Path $PSScriptRoot 'maintenance-common.psm1'
$script:RuntimeModulePath = Join-Path $PSScriptRoot 'maintenance-runtime.psm1'

if (-not (Test-Path -LiteralPath $script:CommonModulePath -PathType Leaf)) { throw 'MAINTENANCE_COMMON_MODULE_MISSING' }
if (-not (Test-Path -LiteralPath $script:RuntimeModulePath -PathType Leaf)) { throw 'MAINTENANCE_RUNTIME_MODULE_MISSING' }
Import-Module -Name $script:CommonModulePath -Force -ErrorAction Stop
Import-Module -Name $script:RuntimeModulePath -Force -ErrorAction Stop

function New-IzRemovalError {
    param([string]$Reason, [int]$Code = 20)
    $exception = [IO.InvalidDataException]::new($Reason)
    $exception.Data['iz_reason'] = $Reason
    $exception.Data['iz_exit_code'] = $Code
    return $exception
}

function Get-IzRemovalExceptionCode {
    param([Management.Automation.ErrorRecord]$Record, [bool]$MutationStarted)
    if ($Record.Exception.Data.Contains('iz_exit_code')) {
        $value = [int]$Record.Exception.Data['iz_exit_code']
        if ($value -in @(10, 20, 21, 30, 31, 40, 41)) { return $value }
    }
    if ($MutationStarted) { return 40 }
    return 20
}

function Get-IzRemovalExceptionReason {
    param([Management.Automation.ErrorRecord]$Record, [int]$Code)
    if ($Record.Exception.Data.Contains('iz_reason')) {
        $reason = [string]$Record.Exception.Data['iz_reason']
        if ($reason -match '^[A-Z][A-Z0-9_]{0,63}$') { return $reason }
    }
    $reason = switch ($Code) {
        21 { 'MAINTENANCE_BUSY' }
        31 { 'RECOVERY_REQUIRED' }
        40 { 'REMOVAL_INCOMPLETE' }
        default { 'REMOVAL_PREFLIGHT_FAILED' }
    }
    return $reason
}

function Get-IzRemovalStatus {
    param([int]$Code, [bool]$NoOp = $false)
    if ($Code -eq 0) { if ($NoOp) { return 'NO_OP' } else { return 'SUCCEEDED' } }
    $status = switch ($Code) {
        10 { 'CANCELLED' }
        20 { 'PREFLIGHT_FAILED' }
        21 { 'BUSY' }
        30 { 'ROLLED_BACK' }
        31 { 'RECOVERY_REQUIRED' }
        40 { 'REMOVAL_INCOMPLETE' }
        41 { 'REMOVED_CLEANUP_PENDING' }
        default { 'PREFLIGHT_FAILED' }
    }
    return $status
}

function New-IzRemovalOutcome {
    param(
        [string]$RequestedAction,
        [int]$Code,
        [string]$Reason,
        [AllowNull()][object]$ReleaseIdentity,
        [string[]]$Evidence,
        [string]$StartedUtc,
        [bool]$NoOp = $false
    )
    return New-IzMaintenanceResult -Action $RequestedAction -Status (Get-IzRemovalStatus -Code $Code -NoOp:$NoOp) -ReleaseIdentity $ReleaseIdentity -TransactionId $null -Stage FINISHED -Code $Code -Reason $Reason -Evidence $Evidence -StartedUtc $StartedUtc
}

function Write-IzRemovalOutcome {
    param([object]$Result, [string]$Path)
    if ($Path) { Write-IzMaintenanceResult -ResultPath $Path -Result $Result | Out-Null }
    return $Result
}

function Resolve-IzRemovalRelativePath {
    param(
        [string]$Root,
        [object]$RelativePath,
        [switch]$AllowBackslash
    )
    if ($RelativePath -isnot [string] -or [string]::IsNullOrWhiteSpace([string]$RelativePath)) {
        throw (New-IzRemovalError 'RELATIVE_PATH_INVALID')
    }
    $relative = [string]$RelativePath
    if (-not $AllowBackslash -and $relative.Contains('\')) { throw (New-IzRemovalError 'RELATIVE_PATH_INVALID') }
    $normalized = $relative.Replace('/', '\')
    if ([IO.Path]::IsPathRooted($normalized) -or $normalized.Contains(':') -or
        $normalized.IndexOfAny([char[]]@([char]0, [char]10, [char]13)) -ge 0) {
        throw (New-IzRemovalError 'RELATIVE_PATH_INVALID')
    }
    foreach ($segment in ($normalized -split '\\')) {
        if (-not $segment -or $segment -in @('.', '..') -or $segment.EndsWith(' ') -or $segment.EndsWith('.')) {
            throw (New-IzRemovalError 'RELATIVE_PATH_INVALID')
        }
    }
    $candidate = Join-Path $Root $normalized
    return Assert-IzContainedPath -Path $candidate -Parent $Root -AllowMissingLeaf
}

function Assert-IzRemovalTreeNoReparse {
    param([string]$Root)
    if (-not (Test-Path -LiteralPath $Root)) { return }
    [void](Get-IzCanonicalPath -Path $Root)
    $rootItem = Get-Item -LiteralPath $Root -Force
    if (-not $rootItem.PSIsContainer) {
        if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw (New-IzRemovalError 'PATH_REPARSE_POINT') }
        return
    }
    $pending = [Collections.Generic.Stack[string]]::new()
    $pending.Push($rootItem.FullName)
    while ($pending.Count -gt 0) {
        $directory = $pending.Pop()
        try { $children = @(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop) }
        catch { throw (New-IzRemovalError 'REMOVAL_TREE_UNREADABLE') }
        foreach ($child in $children) {
            if (($child.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw (New-IzRemovalError 'PATH_REPARSE_POINT')
            }
            if ($child.PSIsContainer) { $pending.Push($child.FullName) }
        }
    }
}

function Remove-IzExactItemWithRetry {
    param([string]$Path, [switch]$Directory)
    if (-not (Test-Path -LiteralPath $Path)) { return $true }
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    $nextProgress = [DateTime]::UtcNow.AddSeconds(5)
    while ($true) {
        try {
            if ($Directory) { Remove-Item -LiteralPath $Path -Force -ErrorAction Stop }
            else { Remove-Item -LiteralPath $Path -Force -ErrorAction Stop }
            $script:RemovalMutationObserved = $true
            return -not (Test-Path -LiteralPath $Path)
        } catch {
            if ([DateTime]::UtcNow -ge $deadline) { return $false }
            if ([DateTime]::UtcNow -ge $nextProgress) {
                Write-Host 'Waiting for an app-owned file to be released...'
                $nextProgress = [DateTime]::UtcNow.AddSeconds(5)
            }
            Start-Sleep -Milliseconds 200
        }
    }
}

function Remove-IzEmptyDirectories {
    param([string]$Root)
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { return }
    $directories = @(Get-ChildItem -LiteralPath $Root -Directory -Force -Recurse | Sort-Object { $_.FullName.Length } -Descending)
    foreach ($directory in $directories) {
        if (@(Get-ChildItem -LiteralPath $directory.FullName -Force).Count -eq 0) {
            [void](Remove-IzExactItemWithRetry -Path $directory.FullName -Directory)
        }
    }
    if (@(Get-ChildItem -LiteralPath $Root -Force).Count -eq 0) {
        [void](Remove-IzExactItemWithRetry -Path $Root -Directory)
    }
}

function Remove-IzDirectoryIfEmpty {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path -PathType Container) {
        if (@(Get-ChildItem -LiteralPath $Path -Force).Count -eq 0) {
            [void](Remove-IzExactItemWithRetry -Path $Path -Directory)
        }
    }
}

function Test-IzOwnedFileRecord {
    param([object]$Record)
    $properties = @($Record.PSObject.Properties.Name)
    if ($properties.Count -ne 3 -or @(@('path', 'length', 'sha256') | Where-Object { $_ -notin $properties }).Count -gt 0) {
        throw (New-IzRemovalError 'FILE_RECORD_INVALID')
    }
    if ($Record.length -isnot [ValueType] -or [long]$Record.length -lt 0 -or [string]$Record.sha256 -notmatch '^[0-9a-f]{64}$') {
        throw (New-IzRemovalError 'FILE_RECORD_INVALID')
    }
}

function Get-IzRemovalTransactionContext {
    param([object]$Context, [Guid]$TransactionId)
    Assert-IzMaintenanceContext -Context $Context | Out-Null
    $transactionText = $TransactionId.ToString('N')
    $derived = $Context | Select-Object *
    $derived.transaction_id = $transactionText
    $derived.transaction_root = Join-Path $Context.transactions_root $transactionText
    $derived.stage_root = Join-Path $Context.program_parent "IZ Clinical Notes Analyzer.stage-$transactionText"
    $derived.previous_root = Join-Path $Context.program_parent "IZ Clinical Notes Analyzer.previous-$transactionText"
    $derived.snapshot_path = Join-Path $derived.transaction_root 'snapshot\pre-change.izcnabackup'
    $derived.verification_root = Join-Path $derived.transaction_root 'verification'
    $derived.requests_root = Join-Path $derived.transaction_root 'requests'
    $derived.results_root = Join-Path $derived.transaction_root 'results'
    Assert-IzMaintenanceContext -Context $derived | Out-Null
    return $derived
}

function Remove-IzOwnedProgramRoot {
    param(
        [string]$Root,
        [object[]]$OwnedFiles,
        [Collections.Generic.List[string]]$Unresolved,
        [string]$EvidenceName,
        [string]$AuthorizedMarkerPath = ''
    )
    if (-not (Test-Path -LiteralPath $Root)) { return }
    $ownedDirectories = [Collections.Generic.List[string]]::new()
    foreach ($record in @($OwnedFiles)) {
        Test-IzOwnedFileRecord $record
        $path = Resolve-IzRemovalRelativePath -Root $Root -RelativePath $record.path
        $parent = Split-Path -Parent $path
        while ($parent -and -not $parent.Equals($Root, [StringComparison]::OrdinalIgnoreCase)) {
            if (-not $ownedDirectories.Contains($parent)) { $ownedDirectories.Add($parent) }
            $parent = Split-Path -Parent $parent
        }
        if (-not (Test-Path -LiteralPath $path)) { continue }
        $item = Get-Item -LiteralPath $path -Force
        $matches = $false
        if (-not $item.PSIsContainer -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0 -and [long]$item.Length -eq [long]$record.length) {
            try { $matches = ((Get-IzFileSha256 -Path $path) -eq [string]$record.sha256) } catch { $matches = $false }
        }
        if (-not $matches -or -not (Remove-IzExactItemWithRetry -Path $path)) {
            if (-not $Unresolved.Contains($EvidenceName)) { $Unresolved.Add($EvidenceName) }
        }
    }
    foreach ($directory in @($ownedDirectories | Sort-Object { $_.Length } -Descending)) {
        Remove-IzDirectoryIfEmpty -Path $directory
    }
    if ($AuthorizedMarkerPath -and (Test-Path -LiteralPath $Root -PathType Container)) {
        $remaining = @(Get-ChildItem -LiteralPath $Root -Force | Where-Object { -not $_.FullName.Equals($AuthorizedMarkerPath, [StringComparison]::OrdinalIgnoreCase) })
        if ($remaining.Count -eq 0 -and (Test-Path -LiteralPath $AuthorizedMarkerPath -PathType Leaf)) {
            [void](Remove-IzExactItemWithRetry -Path $AuthorizedMarkerPath)
        }
    }
    Remove-IzDirectoryIfEmpty -Path $Root
    if (Test-Path -LiteralPath $Root) {
        if (-not $Unresolved.Contains($EvidenceName)) { $Unresolved.Add($EvidenceName) }
    }
}

function Remove-IzOwnedAuxiliaryProgramRoot {
    param([object]$Context, [object]$Descriptor, [Collections.Generic.List[string]]$Unresolved)
    $properties = @($Descriptor.PSObject.Properties.Name)
    $required = @('role', 'path', 'transaction_id', 'marker_sha256', 'payload_identity', 'owned_files')
    if ($properties.Count -ne $required.Count -or @($required | Where-Object { $_ -notin $properties }).Count -gt 0 -or
        $Descriptor.role -notin @('stage', 'previous') -or [string]$Descriptor.transaction_id -notmatch '^[0-9a-f]{32}$' -or
        [string]$Descriptor.marker_sha256 -notmatch '^[0-9a-f]{64}$' -or [string]$Descriptor.payload_identity -notmatch '^[0-9a-f]{64}$') {
        throw (New-IzRemovalError 'AUXILIARY_DESCRIPTOR_INVALID' 31)
    }
    $transactionId = [Guid]([string]$Descriptor.transaction_id)
    $transactionContext = Get-IzRemovalTransactionContext -Context $Context -TransactionId $transactionId
    $expectedRoot = if ($Descriptor.role -eq 'stage') { $transactionContext.stage_root } else { $transactionContext.previous_root }
    $root = Get-IzCanonicalPath -Path ([string]$Descriptor.path) -AllowMissingLeaf
    if (-not $root.Equals((Get-IzCanonicalPath -Path $expectedRoot -AllowMissingLeaf), [StringComparison]::OrdinalIgnoreCase)) {
        throw (New-IzRemovalError 'AUXILIARY_DESCRIPTOR_INVALID' 31)
    }
    if (-not (Test-Path -LiteralPath $root)) { return }
    [void](Test-IzOwnedRootMarker -Context $transactionContext -Path $root -Role ([string]$Descriptor.role) -TransactionId $transactionId)
    $markerPath = Join-Path $root '.iz-cna-owned-root.json'
    if ((Get-IzFileSha256 -Path $markerPath) -ne [string]$Descriptor.marker_sha256) { throw (New-IzRemovalError 'AUXILIARY_DESCRIPTOR_INVALID' 31) }
    Remove-IzOwnedProgramRoot -Root $root -OwnedFiles @($Descriptor.owned_files) -Unresolved $Unresolved -EvidenceName 'auxiliary-program-incomplete' -AuthorizedMarkerPath $markerPath
}

function Get-IzExpectedShortcutTarget {
    param([object]$Context, [object]$Shortcut)
    if ($Shortcut.target_kind -eq 'installed_relative') {
        return Resolve-IzRemovalRelativePath -Root $Context.install_root -RelativePath $Shortcut.target_relative_path -AllowBackslash
    }
    if ($Shortcut.target_kind -eq 'system_powershell') {
        if ([string]$Shortcut.target_relative_path -ne 'System32\WindowsPowerShell\v1.0\powershell.exe') {
            throw (New-IzRemovalError 'SHORTCUT_RECORD_INVALID')
        }
        return Get-IzCanonicalPath -Path (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe')
    }
    throw (New-IzRemovalError 'SHORTCUT_RECORD_INVALID')
}

function Remove-IzOwnedShortcuts {
    param([object]$Context, [object[]]$Shortcuts, [Collections.Generic.List[string]]$Unresolved)
    foreach ($shortcutRecord in @($Shortcuts)) {
        $properties = @($shortcutRecord.PSObject.Properties.Name)
        if ($properties.Count -ne 5 -or @(@('location', 'name', 'target_kind', 'target_relative_path', 'arguments_sha256') | Where-Object { $_ -notin $properties }).Count -gt 0) {
            throw (New-IzRemovalError 'SHORTCUT_RECORD_INVALID')
        }
        if ($shortcutRecord.location -notin @('start_menu', 'desktop') -or [string]$shortcutRecord.arguments_sha256 -notmatch '^[0-9a-f]{64}$') {
            throw (New-IzRemovalError 'SHORTCUT_RECORD_INVALID')
        }
        $shortcutRoot = if ($shortcutRecord.location -eq 'start_menu') { $Context.start_menu_root } else { $Context.desktop_root }
        $shortcutPath = Resolve-IzRemovalRelativePath -Root $shortcutRoot -RelativePath $shortcutRecord.name -AllowBackslash
        if (-not (Test-Path -LiteralPath $shortcutPath -PathType Leaf)) { continue }
        $expectedTarget = Get-IzExpectedShortcutTarget -Context $Context -Shortcut $shortcutRecord
        try {
            $shell = New-Object -ComObject WScript.Shell
            $actual = $shell.CreateShortcut($shortcutPath)
            $actualTarget = Get-IzCanonicalPath -Path ([string]$actual.TargetPath) -AllowMissingLeaf
            $argumentsHash = Get-IzUtf8Sha256 -Value ([string]$actual.Arguments)
            $matches = $actualTarget.Equals($expectedTarget, [StringComparison]::OrdinalIgnoreCase) -and $argumentsHash -eq [string]$shortcutRecord.arguments_sha256
        } catch { $matches = $false }
        if (-not $matches -or -not (Remove-IzExactItemWithRetry -Path $shortcutPath)) {
            if (-not $Unresolved.Contains('shortcut-incomplete')) { $Unresolved.Add('shortcut-incomplete') }
        } else {
            $parent = Split-Path -Parent $shortcutPath
            while ($parent -and -not $parent.Equals($shortcutRoot, [StringComparison]::OrdinalIgnoreCase)) {
                Remove-IzDirectoryIfEmpty -Path $parent
                if (Test-Path -LiteralPath $parent) { break }
                $parent = Split-Path -Parent $parent
            }
        }
    }
}

function Get-IzConfiguredDatabasePath {
    param([object]$Context, [Collections.Generic.List[string]]$Unresolved)
    $envPath = Join-Path $Context.data_root '.env'
    $configured = ''
    if (Test-Path -LiteralPath $envPath -PathType Leaf) {
        $item = Get-Item -LiteralPath $envPath
        if ($item.Length -gt 1048576) { throw (New-IzRemovalError 'DATA_ENV_INVALID') }
        try { $lines = [IO.File]::ReadAllLines($envPath, [Text.UTF8Encoding]::new($false, $true)) }
        catch { throw (New-IzRemovalError 'DATA_ENV_INVALID') }
        foreach ($name in @('IZ_CNA_LOCAL_SQLITE_DB_PATH', 'LOCAL_SQLITE_DB_PATH')) {
            foreach ($line in $lines) {
                if ($line -match ('^\s*' + $name + '\s*=\s*(.*)\s*$')) {
                    $configured = ([string]$Matches[1]).Trim().Trim('"').Trim("'")
                    break
                }
            }
            if ($configured) { break }
        }
    }
    if (-not $configured) {
        foreach ($defaultName in @('clinical-notes-analyzer.sqlite3', 'clinical-notes-analyzer-v2.sqlite3')) {
            $candidate = Join-Path $Context.data_root $defaultName
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
        }
        return $null
    }
    if ([IO.Path]::IsPathRooted($configured)) {
        try { return Assert-IzContainedPath -Path $configured -Parent $Context.data_root }
        catch {
            if (-not $Unresolved.Contains('external-database-preserved')) { $Unresolved.Add('external-database-preserved') }
            return $null
        }
    }
    return Resolve-IzRemovalRelativePath -Root $Context.data_root -RelativePath $configured -AllowBackslash
}

function New-IzDataRemovalPlan {
    param([object]$Context, [object]$Receipt, [Collections.Generic.List[string]]$Unresolved)
    $files = [Collections.Generic.List[string]]::new()
    $directories = [Collections.Generic.List[string]]::new()
    if (-not (Test-Path -LiteralPath $Context.data_root)) {
        return [pscustomobject]@{ files = @(); directories = @() }
    }
    $database = Get-IzConfiguredDatabasePath -Context $Context -Unresolved $Unresolved
    if ($database -and (Test-Path -LiteralPath $database -PathType Leaf)) {
        $identity = New-IzDataIdentity -Context $Context -SelectedDatabasePath $database
        if ($identity.data_identity -ne $Receipt.data_identity) { throw (New-IzRemovalError 'DATA_IDENTITY_MISMATCH') }
    }
    foreach ($fileName in @('.env', 'clinical-notes-analyzer.sqlite3', 'clinical-notes-analyzer-v2.sqlite3')) {
        $candidate = Join-Path $Context.data_root $fileName
        if (-not $files.Contains($candidate)) { $files.Add($candidate) }
        foreach ($suffix in @('-wal', '-shm', '-journal')) { $files.Add($candidate + $suffix) }
    }
    if ($database) {
        if (-not $files.Contains($database)) { $files.Add($database) }
        foreach ($suffix in @('-wal', '-shm', '-journal')) {
            $candidate = $database + $suffix
            if (-not $files.Contains($candidate)) { $files.Add($candidate) }
        }
    }
    foreach ($directoryName in @('uploads', 'manual-uploads', 'logs', 'backups', 'admin-recovery-backups', 'exports', 'reports', 'api-reports', 'api-connectivity-reports', 'api-harness-runs', 'alleva-api-test-logs', 'diagnostics')) {
        $directories.Add((Join-Path $Context.data_root $directoryName))
    }
    foreach ($item in @(Get-ChildItem -LiteralPath $Context.data_root -Force)) {
        if ($item.PSIsContainer) {
            if (-not $directories.Contains($item.FullName)) {
                if (-not $Unresolved.Contains('data-incomplete')) { $Unresolved.Add('data-incomplete') }
            }
        } elseif (-not $files.Contains($item.FullName)) {
            $ownedBackup = $false
            try {
                if ($item.Length -ge 8) {
                    $stream = [IO.File]::Open($item.FullName, 'Open', 'Read', 'Read')
                    try {
                        $magicBytes = New-Object byte[] 8
                        if ($stream.Read($magicBytes, 0, 8) -eq 8) {
                            $magic = [Text.Encoding]::ASCII.GetString($magicBytes)
                            $ownedBackup = $magic -in @('IZCNABK1', 'IZCNABK2')
                        }
                    } finally { $stream.Dispose() }
                }
            } catch { $ownedBackup = $false }
            if ($ownedBackup) { $files.Add($item.FullName) }
            elseif (-not $Unresolved.Contains('data-incomplete')) { $Unresolved.Add('data-incomplete') }
        }
    }
    return [pscustomobject]@{ files = @($files); directories = @($directories) }
}

function Remove-IzClassifiedDirectory {
    param([string]$Path, [Collections.Generic.List[string]]$Unresolved, [string]$EvidenceName)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return }
    $files = @(Get-ChildItem -LiteralPath $Path -File -Force -Recurse | Sort-Object FullName -Descending)
    foreach ($file in $files) {
        if (-not (Remove-IzExactItemWithRetry -Path $file.FullName)) {
            if (-not $Unresolved.Contains($EvidenceName)) { $Unresolved.Add($EvidenceName) }
        }
    }
    Remove-IzEmptyDirectories -Root $Path
    if ((Test-Path -LiteralPath $Path) -and -not $Unresolved.Contains($EvidenceName)) { $Unresolved.Add($EvidenceName) }
}

function Remove-IzDataPlan {
    param([object]$Context, [object]$Plan, [Collections.Generic.List[string]]$Unresolved)
    foreach ($file in @($Plan.files)) {
        if (Test-Path -LiteralPath $file -PathType Leaf) {
            if (-not (Remove-IzExactItemWithRetry -Path $file) -and -not $Unresolved.Contains('data-incomplete')) { $Unresolved.Add('data-incomplete') }
        }
    }
    foreach ($directory in @($Plan.directories)) { Remove-IzClassifiedDirectory -Path $directory -Unresolved $Unresolved -EvidenceName 'data-incomplete' }
    Remove-IzDirectoryIfEmpty -Path $Context.data_root
    if ((Test-Path -LiteralPath $Context.data_root) -and -not $Unresolved.Contains('data-incomplete')) { $Unresolved.Add('data-incomplete') }
}

function New-IzEmptyMaintenanceRemovalPlan {
    return [pscustomobject]@{
        files = [Collections.Generic.List[string]]::new()
        file_keys = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        directories = [Collections.Generic.List[string]]::new()
        directory_keys = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        marker_keys = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        transaction_roots = [Collections.Generic.List[string]]::new()
    }
}

function Add-IzMaintenanceRemovalDirectory {
    param([object]$Plan, [object]$Context, [string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return $false }
    $root = Get-IzCanonicalPath -Path $Context.maintenance_root
    $candidate = Get-IzCanonicalPath -Path $Path
    $safe = if ($candidate.Equals($root, [StringComparison]::OrdinalIgnoreCase)) { $root } else {
        Assert-IzContainedPath -Path $candidate -Parent $root
    }
    $item = Get-Item -LiteralPath $safe -Force
    if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw (New-IzRemovalError 'MAINTENANCE_ARTIFACT_INVALID' 40)
    }
    Assert-IzCurrentUserOwner -Path $safe
    if ($Plan.directory_keys.Add($safe)) { $Plan.directories.Add($safe) }
    return $true
}

function Add-IzMaintenanceRemovalFile {
    param(
        [object]$Plan,
        [object]$Context,
        [string]$Path,
        [string]$ExpectedSha256 = '',
        [long]$ExpectedLength = -1
    )
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    $safe = Assert-IzContainedPath -Path $Path -Parent $Context.maintenance_root
    $item = Get-Item -LiteralPath $safe -Force
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
        ($ExpectedLength -ge 0 -and [long]$item.Length -ne $ExpectedLength) -or
        ($ExpectedSha256 -and (Get-IzFileSha256 -Path $safe) -cne $ExpectedSha256)) {
        throw (New-IzRemovalError 'MAINTENANCE_ARTIFACT_INVALID' 40)
    }
    Assert-IzCurrentUserOwner -Path $safe
    if ($Plan.file_keys.Add($safe)) { $Plan.files.Add($safe) }
    $parent = Split-Path -Parent $safe
    while ($parent -and -not $parent.Equals($Context.maintenance_root, [StringComparison]::OrdinalIgnoreCase)) {
        [void](Add-IzMaintenanceRemovalDirectory -Plan $Plan -Context $Context -Path $parent)
        $parent = Split-Path -Parent $parent
    }
    return $true
}

function Merge-IzMaintenanceRemovalPlan {
    param([object]$Target, [object]$Source)
    foreach ($path in $Source.files) { if ($Target.file_keys.Add($path)) { $Target.files.Add($path) } }
    foreach ($path in $Source.directories) { if ($Target.directory_keys.Add($path)) { $Target.directories.Add($path) } }
    foreach ($path in $Source.marker_keys) { [void]$Target.marker_keys.Add($path) }
    foreach ($path in $Source.transaction_roots) { if ($path -notin $Target.transaction_roots) { $Target.transaction_roots.Add($path) } }
}

function Add-IzPriorShortcutRemovalArtifacts {
    param([object]$Plan, [object]$Context, [object]$TransactionContext, [object]$PriorReceipt)
    $manifestPath = Join-Path $TransactionContext.transaction_root 'prior-shortcuts.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { return }
    $manifest = Read-IzStrictJsonFile -Path $manifestPath -MissingReason 'PRIOR_SHORTCUTS_MISSING' -CorruptReason 'PRIOR_SHORTCUTS_INVALID'
    [void](Assert-IzExactProperties -Value $manifest -Expected @('shortcuts') -Reason 'PRIOR_SHORTCUTS_INVALID')
    $records = @($manifest.shortcuts)
    $expected = @($PriorReceipt.owned_shortcuts)
    if ($records.Count -ne $expected.Count) { throw (New-IzRemovalError 'PRIOR_SHORTCUTS_INVALID' 40) }
    $copyRoot = Join-Path $TransactionContext.transaction_root 'prior-shortcuts'
    if (Test-Path -LiteralPath $copyRoot) { [void](Add-IzMaintenanceRemovalDirectory -Plan $Plan -Context $Context -Path $copyRoot) }
    for ($index = 0; $index -lt $records.Count; $index++) {
        $record = $records[$index]
        [void](Assert-IzExactProperties -Value $record -Expected @('location','name','present','sha256','copy_name') -Reason 'PRIOR_SHORTCUTS_INVALID')
        if ($record.location -cne $expected[$index].location -or $record.name -cne $expected[$index].name -or $record.present -isnot [bool]) {
            throw (New-IzRemovalError 'PRIOR_SHORTCUTS_INVALID' 40)
        }
        $copyName = "$index.lnk"
        $copyPath = Join-Path $copyRoot $copyName
        if ([bool]$record.present) {
            if ([string]$record.copy_name -cne $copyName -or [string]$record.sha256 -notmatch '^[0-9a-f]{64}$' -or
                -not (Add-IzMaintenanceRemovalFile -Plan $Plan -Context $Context -Path $copyPath -ExpectedSha256 ([string]$record.sha256))) {
                throw (New-IzRemovalError 'PRIOR_SHORTCUTS_INVALID' 40)
            }
        } elseif ($null -ne $record.sha256 -or $null -ne $record.copy_name -or (Test-Path -LiteralPath $copyPath)) {
            throw (New-IzRemovalError 'PRIOR_SHORTCUTS_INVALID' 40)
        }
    }
    [void](Add-IzMaintenanceRemovalFile -Plan $Plan -Context $Context -Path $manifestPath)
}

function New-IzTransactionMaintenanceRemovalPlan {
    param([object]$Context, [object]$TransactionContext, [object]$Journal, [bool]$Archived)
    $plan = New-IzEmptyMaintenanceRemovalPlan
    $transactionId = [Guid]$TransactionContext.transaction_id
    $transactionRoot = [string]$TransactionContext.transaction_root
    [void](Test-IzOwnedRootMarker -Context $TransactionContext -Path $transactionRoot -Role transaction -TransactionId $transactionId)
    [void]$plan.marker_keys.Add((Join-Path $transactionRoot '.iz-cna-owned-root.json'))
    $plan.transaction_roots.Add($transactionRoot)
    [void](Add-IzMaintenanceRemovalDirectory -Plan $plan -Context $Context -Path $transactionRoot)

    if ($Archived) {
        $archivePath = Join-Path $transactionRoot 'resolved-maintenance-journal.json'
        if (-not (Add-IzMaintenanceRemovalFile -Plan $plan -Context $Context -Path $archivePath)) {
            throw (New-IzRemovalError 'RESOLVED_JOURNAL_INVALID' 40)
        }
    } elseif ($Journal.state -cne 'COMMITTED') {
        throw (New-IzRemovalError 'MAINTENANCE_JOURNAL_INVALID' 40)
    }

    foreach ($prefix in @('stage','previous')) {
        $relative = [string]$Journal.program.($prefix + '_inventory_relative_path')
        $expectedHash = [string]$Journal.program.($prefix + '_inventory_sha256')
        if (-not $relative) { continue }
        if ($expectedHash -notmatch '^[0-9a-f]{64}$') { throw (New-IzRemovalError 'MAINTENANCE_INVENTORY_INVALID' 40) }
        $inventoryPath = Resolve-IzRemovalRelativePath -Root $transactionRoot -RelativePath $relative
        if (Test-Path -LiteralPath $inventoryPath -PathType Leaf) {
            [void](Add-IzMaintenanceRemovalFile -Plan $plan -Context $Context -Path $inventoryPath -ExpectedSha256 $expectedHash)
            $inventory = Read-IzProgramInventory -Context $TransactionContext -Path $inventoryPath
            $expectedPayload = [string]$Journal.program.($prefix + '_payload_identity')
            if ($inventory.product_id -cne $Context.product_id -or $inventory.owner_sid -cne $Context.owner_sid -or
                $inventory.scope_id -cne $Context.scope_id -or $inventory.transaction_id -cne $TransactionContext.transaction_id -or
                $inventory.role -cne $prefix -or $inventory.payload_identity -cne $expectedPayload) {
                throw (New-IzRemovalError 'MAINTENANCE_INVENTORY_INVALID' 40)
            }
        }
    }

    $previousMarkerPath = Join-Path $transactionRoot 'program-previous-marker.json'
    if (Test-Path -LiteralPath $previousMarkerPath) {
        $markerHash = [string]$Journal.program.previous_marker_sha256
        if ($markerHash -notmatch '^[0-9a-f]{64}$') { throw (New-IzRemovalError 'MAINTENANCE_MARKER_INVALID' 40) }
        [void](Add-IzMaintenanceRemovalFile -Plan $plan -Context $Context -Path $previousMarkerPath -ExpectedSha256 $markerHash)
    }

    $priorReceipt = $null
    $priorReceiptPath = Join-Path $transactionRoot 'prior-install-receipt.json'
    if (Test-Path -LiteralPath $priorReceiptPath) {
        if ([string]$Journal.prior_receipt_sha256 -notmatch '^[0-9a-f]{64}$') { throw (New-IzRemovalError 'PRIOR_RECEIPT_INVALID' 40) }
        [void](Add-IzMaintenanceRemovalFile -Plan $plan -Context $Context -Path $priorReceiptPath -ExpectedSha256 ([string]$Journal.prior_receipt_sha256))
        $priorReceipt = ConvertTo-IzInstallReceipt -Context $Context -Value (Read-IzStrictJsonFile -Path $priorReceiptPath -MissingReason 'PRIOR_RECEIPT_MISSING' -CorruptReason 'PRIOR_RECEIPT_INVALID')
        Add-IzPriorShortcutRemovalArtifacts -Plan $plan -Context $Context -TransactionContext $TransactionContext -PriorReceipt $priorReceipt
    }

    $manifestPath = Join-Path $transactionRoot 'target-release-manifest.json'
    if (Test-Path -LiteralPath $manifestPath) {
        if (-not $Journal.target_release) { throw (New-IzRemovalError 'STORED_MANIFEST_INVALID' 40) }
        $manifest = Read-IzReleaseManifest -PackageRoot $transactionRoot -ManifestPath $manifestPath
        $manifestRelease = New-IzReleaseIdentity -Version $manifest.version -Build $manifest.build -InstallerRevision ([int]$manifest.installer_revision) -PayloadIdentity $manifest.payload_identity
        if ((Compare-IzReleaseIdentity -Left $manifestRelease -Right $Journal.target_release) -ne 0) { throw (New-IzRemovalError 'STORED_MANIFEST_INVALID' 40) }
        [void](Add-IzMaintenanceRemovalFile -Plan $plan -Context $Context -Path $manifestPath)
    }

    $freshPath = Join-Path $transactionRoot 'fresh-data-root.json'
    if (Test-Path -LiteralPath $freshPath) {
        $fresh = Read-IzStrictJsonFile -Path $freshPath -MissingReason 'FRESH_DATA_ROOT_INVALID' -CorruptReason 'FRESH_DATA_ROOT_INVALID'
        [void](Assert-IzExactProperties -Value $fresh -Expected @('schema','product_id','owner_sid','scope_id','transaction_id','data_root','data_identity') -Reason 'FRESH_DATA_ROOT_INVALID')
        if ($fresh.schema -cne 'iz-cna-fresh-data-root-v1' -or $fresh.product_id -cne $Context.product_id -or
            $fresh.owner_sid -cne $Context.owner_sid -or $fresh.scope_id -cne $Context.scope_id -or
            $fresh.transaction_id -cne $TransactionContext.transaction_id -or $fresh.data_identity -cne $Journal.data_identity -or
            -not ([IO.Path]::GetFullPath([string]$fresh.data_root).Equals([IO.Path]::GetFullPath([string]$Context.data_root), [StringComparison]::OrdinalIgnoreCase))) {
            throw (New-IzRemovalError 'FRESH_DATA_ROOT_INVALID' 40)
        }
        [void](Add-IzMaintenanceRemovalFile -Plan $plan -Context $Context -Path $freshPath)
    }

    $snapshotRoot = Split-Path -Parent $TransactionContext.snapshot_path
    if (Test-Path -LiteralPath $snapshotRoot -PathType Container) {
        [void](Add-IzMaintenanceRemovalDirectory -Plan $plan -Context $Context -Path $snapshotRoot)
        $snapshotAuthorized = $false
        if (Test-Path -LiteralPath $TransactionContext.snapshot_path -PathType Leaf) {
            if ($Journal.snapshot) {
                [void](Add-IzMaintenanceRemovalFile -Plan $plan -Context $Context -Path $TransactionContext.snapshot_path -ExpectedSha256 ([string]$Journal.snapshot.sha256) -ExpectedLength ([long]$Journal.snapshot.length))
            } else {
                $stream = [IO.File]::Open($TransactionContext.snapshot_path, 'Open', 'Read', 'Read')
                try {
                    $bytes = New-Object byte[] 8
                    if ($stream.Read($bytes, 0, 8) -ne 8 -or [Text.Encoding]::ASCII.GetString($bytes) -notin @('IZCNABK1','IZCNABK2')) {
                        throw (New-IzRemovalError 'MAINTENANCE_SNAPSHOT_INVALID' 40)
                    }
                } finally { $stream.Dispose() }
                [void](Add-IzMaintenanceRemovalFile -Plan $plan -Context $Context -Path $TransactionContext.snapshot_path)
            }
            $snapshotAuthorized = $true
        } elseif ($Journal.snapshot) { $snapshotAuthorized = $true }
        if ($snapshotAuthorized) {
            foreach ($name in @('payload.zip','selected-database.sqlite3','selected-database.sqlite3-wal','selected-database.sqlite3-shm')) {
                [void](Add-IzMaintenanceRemovalFile -Plan $plan -Context $Context -Path (Join-Path $snapshotRoot $name))
            }
        }
    }

    foreach ($descriptor in @(
        [pscustomobject]@{ root=$TransactionContext.requests_root; pattern='^(?:candidate-verify|q-[0-9a-f]{12})\.json$' },
        [pscustomobject]@{ root=$TransactionContext.results_root; pattern='^(?:candidate-verify|installer-failure|s-[0-9a-f]{12})\.json$' }
    )) {
        if (-not (Test-Path -LiteralPath $descriptor.root -PathType Container)) { continue }
        [void](Add-IzMaintenanceRemovalDirectory -Plan $plan -Context $Context -Path $descriptor.root)
        foreach ($item in @(Get-ChildItem -LiteralPath $descriptor.root -Force)) {
            if (-not $item.PSIsContainer -and $item.Name -cmatch $descriptor.pattern) {
                [void](Add-IzMaintenanceRemovalFile -Plan $plan -Context $Context -Path $item.FullName)
            }
        }
    }

    if (Test-Path -LiteralPath $TransactionContext.verification_root -PathType Container) {
        [void](Test-IzOwnedRootMarker -Context $TransactionContext -Path $TransactionContext.verification_root -Role verification -TransactionId $transactionId)
        [void](Add-IzMaintenanceRemovalDirectory -Plan $plan -Context $Context -Path $TransactionContext.verification_root)
        [void](Add-IzMaintenanceRemovalFile -Plan $plan -Context $Context -Path (Join-Path $TransactionContext.verification_root '.iz-cna-owned-root.json'))
    }
    return $plan
}

function New-IzMaintenanceRemovalPlan {
    param([object]$Context, [object]$PendingStatus, [object]$Receipt, [Collections.Generic.List[string]]$Unresolved)
    $plan = New-IzEmptyMaintenanceRemovalPlan
    [void](Test-IzOwnedRootMarker -Context $Context -Path $Context.maintenance_root -Role maintenance)
    [void]$plan.marker_keys.Add((Join-Path $Context.maintenance_root '.iz-cna-owned-root.json'))
    [void](Add-IzMaintenanceRemovalDirectory -Plan $plan -Context $Context -Path $Context.maintenance_root)
    [void](Add-IzMaintenanceRemovalDirectory -Plan $plan -Context $Context -Path $Context.transactions_root)
    [void](Add-IzMaintenanceRemovalDirectory -Plan $plan -Context $Context -Path $Context.state_root)

    if (Test-Path -LiteralPath $Context.transactions_root -PathType Container) {
        foreach ($transactionDirectory in @(Get-ChildItem -LiteralPath $Context.transactions_root -Directory -Force)) {
            if ($transactionDirectory.Name -notmatch '^[0-9a-f]{32}$') {
                if (-not $Unresolved.Contains('maintenance-incomplete')) { $Unresolved.Add('maintenance-incomplete') }
                continue
            }
            try {
                $transactionContext = Get-IzRemovalTransactionContext -Context $Context -TransactionId ([Guid]$transactionDirectory.Name
                )
                $isCurrent = $PendingStatus.journal -and [string]$PendingStatus.journal.transaction_id -ceq $transactionDirectory.Name
                $journal = if ($isCurrent) { $PendingStatus.journal } else { Read-IzResolvedMaintenanceJournal -Context $transactionContext }
                $transactionPlan = New-IzTransactionMaintenanceRemovalPlan -Context $Context -TransactionContext $transactionContext -Journal $journal -Archived:(-not $isCurrent)
                Merge-IzMaintenanceRemovalPlan -Target $plan -Source $transactionPlan
            } catch {
                if (-not $Unresolved.Contains('maintenance-incomplete')) { $Unresolved.Add('maintenance-incomplete') }
            }
        }
    }

    foreach ($stateFile in @($Context.runtime_identity_path, $Context.journal_path, $Context.journal_previous_path, $Context.install_receipt_path, $Context.lock_owner_path, $Context.operation_lock_path)) {
        [void](Add-IzMaintenanceRemovalFile -Plan $plan -Context $Context -Path $stateFile)
    }
    if ($Receipt) {
        $runtimeLock = Join-Path $Context.state_root ("runtime-$($Context.scope_id.Substring(0,16))-$(([string]$Receipt.data_identity).Substring(0,16)).lock")
        if (Add-IzMaintenanceRemovalFile -Plan $plan -Context $Context -Path $runtimeLock -ExpectedLength 1) {
            $stream = $null
            try {
                $stream = [IO.File]::Open($runtimeLock, 'Open', 'ReadWrite', 'None')
            } catch { throw (New-IzRemovalError 'RUNTIME_LOCK_ACTIVE' 40) }
            try {
                if ($stream.ReadByte() -ne 0) { throw (New-IzRemovalError 'RUNTIME_LOCK_INVALID' 40) }
            } finally { $stream.Dispose() }
        }
    }

    foreach ($item in @(Get-ChildItem -LiteralPath $Context.maintenance_root -Force -Recurse)) {
        $path = [IO.Path]::GetFullPath($item.FullName)
        $known = if ($item.PSIsContainer) { $plan.directory_keys.Contains($path) } else { $plan.file_keys.Contains($path) -or $plan.marker_keys.Contains($path) }
        if (-not $known -and -not $Unresolved.Contains('maintenance-incomplete')) { $Unresolved.Add('maintenance-incomplete') }
    }
    return $plan
}

function Remove-IzMaintenanceState {
    param([object]$Context, [object]$PendingStatus, [object]$Receipt, [Collections.Generic.List[string]]$Unresolved)
    if (-not (Test-Path -LiteralPath $Context.maintenance_root)) { return }
    try { $plan = New-IzMaintenanceRemovalPlan -Context $Context -PendingStatus $PendingStatus -Receipt $Receipt -Unresolved $Unresolved }
    catch {
        if (-not $Unresolved.Contains('maintenance-incomplete')) { $Unresolved.Add('maintenance-incomplete') }
        return
    }
    foreach ($path in @($plan.files | Sort-Object { $_.Length } -Descending)) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            if (-not (Remove-IzExactItemWithRetry -Path $path) -and -not $Unresolved.Contains('maintenance-incomplete')) { $Unresolved.Add('maintenance-incomplete') }
        }
    }
    foreach ($path in @($plan.directories | Sort-Object { $_.Length } -Descending)) { Remove-IzDirectoryIfEmpty -Path $path }
    foreach ($transactionRoot in $plan.transaction_roots) {
        if (-not (Test-Path -LiteralPath $transactionRoot -PathType Container)) { continue }
        $markerPath = Join-Path $transactionRoot '.iz-cna-owned-root.json'
        $remaining = @(Get-ChildItem -LiteralPath $transactionRoot -Force | Where-Object { -not $_.FullName.Equals($markerPath, [StringComparison]::OrdinalIgnoreCase) })
        if ($remaining.Count -eq 0) {
            if (Test-Path -LiteralPath $markerPath -PathType Leaf) { [void](Remove-IzExactItemWithRetry -Path $markerPath) }
            Remove-IzDirectoryIfEmpty -Path $transactionRoot
        }
        if ((Test-Path -LiteralPath $transactionRoot) -and -not $Unresolved.Contains('maintenance-incomplete')) { $Unresolved.Add('maintenance-incomplete') }
    }
    Remove-IzDirectoryIfEmpty -Path $Context.transactions_root
    Remove-IzDirectoryIfEmpty -Path $Context.state_root
    $maintenanceMarker = Join-Path $Context.maintenance_root '.iz-cna-owned-root.json'
    $remaining = @(Get-ChildItem -LiteralPath $Context.maintenance_root -Force | Where-Object { -not $_.FullName.Equals($maintenanceMarker, [StringComparison]::OrdinalIgnoreCase) })
    if ($remaining.Count -eq 0) {
        if (Test-Path -LiteralPath $maintenanceMarker -PathType Leaf) { [void](Remove-IzExactItemWithRetry -Path $maintenanceMarker) }
        Remove-IzDirectoryIfEmpty -Path $Context.maintenance_root
    }
    if ((Test-Path -LiteralPath $Context.maintenance_root) -and -not $Unresolved.Contains('maintenance-incomplete')) { $Unresolved.Add('maintenance-incomplete') }
}

function Get-IzPendingRemovalStatus {
    param([object]$Context)
    if (-not (Test-Path -LiteralPath $Context.maintenance_root)) {
        return [pscustomobject]@{ status = 'CLEAN'; journal = $null; authority = $null; auxiliary_program_roots = @(); reason = 'NO_MAINTENANCE_STATE' }
    }
    try {
        [void](Test-IzOwnedRootMarker -Context $Context -Path $Context.maintenance_root -Role maintenance)
        return Get-IzPendingMaintenanceStatus -Context $Context
    } catch {
        throw (New-IzRemovalError 'RECOVERY_REQUIRED' 31)
    }
}

function Invoke-IzWindowsRemoval {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidateSet('Uninstall', 'RemoveData')][string]$Action,
        [string]$PackageRoot = '',
        [switch]$NoPause,
        [switch]$NonInteractive,
        [string]$ResultPath = '',
        [AllowNull()][object]$Context = $null
    )
    $startedUtc = [DateTime]::UtcNow.ToString('o')
    $script:RemovalMutationObserved = $false
    $releaseIdentity = $null
    $receipt = $null
    $lockHandle = $null
    $lockReleased = $false
    $unresolved = [Collections.Generic.List[string]]::new()
    try {
        if ($Context -and $PackageRoot) { throw (New-IzRemovalError 'CONTEXT_PACKAGE_CONFLICT') }
        if ($Context) {
            Assert-IzMaintenanceContext -Context $Context | Out-Null
            $context = $Context
        } else {
            $contextParameters = @{}
            if ($PackageRoot) { $contextParameters.PackageRoot = $PackageRoot }
            $context = Get-IzMaintenanceContext @contextParameters
            Assert-IzMaintenanceContext -Context $context | Out-Null
        }
        $hasInstall = Test-Path -LiteralPath $context.install_root
        $hasData = Test-Path -LiteralPath $context.data_root
        $hasMaintenance = Test-Path -LiteralPath $context.maintenance_root

        if ($hasMaintenance -and (Test-Path -LiteralPath $context.install_receipt_path -PathType Leaf)) {
            $receipt = Read-IzInstallReceipt -Context $context
            $releaseIdentity = New-IzReleaseIdentity -Version $receipt.version -Build $receipt.build -InstallerRevision ([int]$receipt.installer_revision) -PayloadIdentity $receipt.payload_identity
        }
        if (-not $receipt -and $hasInstall) { throw (New-IzRemovalError 'INSTALL_RECEIPT_REQUIRED') }
        if ($Action -eq 'RemoveData' -and -not $receipt -and $hasData) { throw (New-IzRemovalError 'DATA_OWNERSHIP_UNPROVEN') }

        $pending = Get-IzPendingRemovalStatus -Context $context
        if ($pending.status -in @('PENDING', 'RECOVERY_REQUIRED')) {
            throw (New-IzRemovalError 'RECOVERY_REQUIRED' 31)
        }
        if ($pending.status -notin @('CLEAN', 'COMMITTED')) { throw (New-IzRemovalError 'RECOVERY_REQUIRED' 31) }

        if (-not $hasInstall -and -not $hasMaintenance -and ($Action -eq 'Uninstall' -or -not $hasData)) {
            $noOp = New-IzRemovalOutcome -RequestedAction $Action -Code 0 -Reason ALREADY_REMOVED -ReleaseIdentity $releaseIdentity -Evidence @() -StartedUtc $startedUtc -NoOp $true
            return Write-IzRemovalOutcome -Result $noOp -Path $ResultPath
        }

        Assert-IzRemovalTreeNoReparse -Root $context.install_root
        foreach ($auxiliary in @($pending.auxiliary_program_roots)) { Assert-IzRemovalTreeNoReparse -Root ([string]$auxiliary.path) }
        if ($Action -eq 'RemoveData') {
            Assert-IzRemovalTreeNoReparse -Root $context.data_root
            Assert-IzRemovalTreeNoReparse -Root $context.maintenance_root
            Write-Host ''
            Write-Host 'Complete uninstall will remove these app-owned roots for this Windows user:' -ForegroundColor Yellow
            Write-Host '  Program files: the per-user IZ Clinical Notes Analyzer installation'
            Write-Host '  Local data: database, encrypted uploads, settings, logs, and in-root backups'
            Write-Host '  Maintenance data: app-owned recovery snapshots and transaction state'
            Write-Host 'External backups, downloaded packages, and other Windows profiles are not included.'
            $answer = Read-Host 'Type REMOVE IZ DATA to continue'
            if ($null -eq $answer -or ([string]$answer).Trim() -cne 'REMOVE IZ DATA') {
                $cancelled = New-IzRemovalOutcome -RequestedAction $Action -Code 10 -Reason CONFIRMATION_REQUIRED -ReleaseIdentity $releaseIdentity -Evidence @() -StartedUtc $startedUtc
                return Write-IzRemovalOutcome -Result $cancelled -Path $ResultPath
            }
        }

        $dataPlan = $null
        if ($Action -eq 'RemoveData' -and $hasData) { $dataPlan = New-IzDataRemovalPlan -Context $context -Receipt $receipt -Unresolved $unresolved }

        if ($hasMaintenance) {
            $transactionId = if ($receipt) { [Guid]$receipt.last_committed_transaction } else { [Guid]::NewGuid() }
            $lockHandle = Enter-IzMaintenanceLock -Context $context -Action $Action -TransactionId $transactionId
            $pending = Get-IzPendingRemovalStatus -Context $context
            if ($pending.status -in @('PENDING', 'RECOVERY_REQUIRED')) { throw (New-IzRemovalError 'RECOVERY_REQUIRED' 31) }
        }

        if ($receipt) {
            Write-Host 'Closing the owned IZ Clinical Notes Analyzer runtime...'
            $stopResult = Stop-IzOwnedRuntime -Context $context -TimeoutSeconds 30
            if ($stopResult.status -notin @('stopped', 'already_stopped')) { throw (New-IzRemovalError 'RUNTIME_STOP_FAILED') }
        }

        Write-Host 'Removing verified app-owned files and shortcuts...'
        if ($receipt) { Remove-IzOwnedShortcuts -Context $context -Shortcuts @($receipt.owned_shortcuts) -Unresolved $unresolved }
        foreach ($auxiliary in @($pending.auxiliary_program_roots)) {
            Remove-IzOwnedAuxiliaryProgramRoot -Context $context -Descriptor $auxiliary -Unresolved $unresolved
        }
        if ($receipt) { Remove-IzOwnedProgramRoot -Root $context.install_root -OwnedFiles @($receipt.owned_files) -Unresolved $unresolved -EvidenceName 'program-incomplete' }

        if ($Action -eq 'RemoveData' -and $dataPlan) {
            Write-Host 'Removing classified app-owned local data...'
            Remove-IzDataPlan -Context $context -Plan $dataPlan -Unresolved $unresolved
        }

        if ($lockHandle) {
            Exit-IzMaintenanceLock -LockHandle $lockHandle
            $lockReleased = $true
        }
        if ($Action -eq 'RemoveData' -and $unresolved.Count -eq 0) {
            Write-Host 'Removing classified app-owned maintenance state...'
            Remove-IzMaintenanceState -Context $context -PendingStatus $pending -Receipt $receipt -Unresolved $unresolved
        }

        $code = if ($unresolved.Count -eq 0) { 0 } else { 40 }
        $reason = if ($code -eq 0) { if ($script:RemovalMutationObserved) { 'REMOVAL_COMPLETED' } else { 'ALREADY_REMOVED' } } else { 'REMOVAL_INCOMPLETE' }
        $result = New-IzRemovalOutcome -RequestedAction $Action -Code $code -Reason $reason -ReleaseIdentity $releaseIdentity -Evidence @($unresolved | Sort-Object -Unique) -StartedUtc $startedUtc -NoOp:($code -eq 0 -and -not $script:RemovalMutationObserved)
        return Write-IzRemovalOutcome -Result $result -Path $ResultPath
    } catch {
        $code = Get-IzRemovalExceptionCode -Record $_ -MutationStarted:$script:RemovalMutationObserved
        $reason = Get-IzRemovalExceptionReason -Record $_ -Code $code
        [string[]]$failureEvidence = @()
        if ($code -eq 40) { $failureEvidence = @('removal-interrupted') }
        $result = New-IzRemovalOutcome -RequestedAction $Action -Code $code -Reason $reason -ReleaseIdentity $releaseIdentity -Evidence $failureEvidence -StartedUtc $startedUtc
        return Write-IzRemovalOutcome -Result $result -Path $ResultPath
    } finally {
        if ($lockHandle -and -not $lockReleased) {
            try { Exit-IzMaintenanceLock -LockHandle $lockHandle } catch { }
        }
    }
}

if (-not $NoRun) {
    $result = Invoke-IzWindowsRemoval -Action $Action -PackageRoot $PackageRoot -NoPause:$NoPause -NonInteractive:$NonInteractive -ResultPath $ResultPath
    Write-Host ($result | ConvertTo-Json -Depth 8 -Compress)
    if (-not $NoPause) {
        Write-Host ''
        Read-Host 'Press Enter to close' | Out-Null
    }
    exit ([int]$result.code)
}
