[CmdletBinding()]
param(
    [ValidateSet('Uninstall', 'RemoveData')]
    [string]$Action = 'Uninstall',
    [Parameter(Mandatory)]
    [string]$SourceRoot,
    [ValidateSet('Package', 'Installed')]
    [string]$SourceKind = 'Package',
    [switch]$NoPause,
    [switch]$NonInteractive,
    [string]$ResultPath = '',
    [switch]$AssumeYes,
    [switch]$NoRun,
    [Parameter(ValueFromRemainingArguments = $true)]
    [object[]]$RemainingArguments
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$script:ProductId = 'r3.iz-clinical-notes-analyzer.desktop'
$script:BundleManifestSchema = 'iz-cna-maintenance-bundle-v1'
$script:ExpectedManifestSha256 = '@@MAINTENANCE_BUNDLE_MANIFEST_SHA256@@'
$script:BundleFiles = @(
    'maintenance-common.psm1',
    'maintenance-contracts.psm1',
    'maintenance-journal.psm1',
    'maintenance-lock.psm1',
    'maintenance-paths.psm1',
    'maintenance-runtime.psm1',
    'maintenance-version.psm1',
    'maintenance-windows.ps1',
    'uninstall-windows-release.ps1'
)

function Get-IzBootstrapFileSha256 {
    param([string]$Path)
    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose(); $stream.Dispose() }
}

function Get-IzBootstrapUtf8Sha256 {
    param([string]$Value)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes($Value)
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    } finally { $sha.Dispose() }
}

function Get-IzBootstrapCanonicalPath {
    param([string]$Path, [switch]$AllowMissingLeaf)
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path -notmatch '^[A-Za-z]:[\\/]') { throw 'PATH_NOT_LOCAL_ABSOLUTE' }
    if ($Path.StartsWith('\\') -or $Path.StartsWith('\\?\') -or $Path.StartsWith('\\.\') -or $Path.Substring(2).Contains(':')) { throw 'PATH_DEVICE_OR_UNC' }
    foreach ($segment in ($Path.Substring(2) -split '[\\/]')) {
        if ($segment -in @('.', '..')) { throw 'PATH_TRAVERSAL' }
    }
    $full = [IO.Path]::GetFullPath($Path).Replace('/', '\').TrimEnd('\')
    $probe = $full
    while (-not (Test-Path -LiteralPath $probe)) {
        if (-not $AllowMissingLeaf) { throw 'PATH_NOT_FOUND' }
        $parent = [IO.Path]::GetDirectoryName($probe)
        if (-not $parent -or $parent -eq $probe) { break }
        $probe = $parent
    }
    if (Test-Path -LiteralPath $probe) {
        $cursor = [IO.Path]::GetPathRoot($probe)
        foreach ($segment in ($probe.Substring($cursor.Length) -split '\\')) {
            if (-not $segment) { continue }
            $cursor = Join-Path $cursor $segment
            $item = Get-Item -LiteralPath $cursor -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'PATH_REPARSE_POINT' }
        }
    }
    return $full
}

function ConvertTo-IzBootstrapPathKey {
    param([string]$Path)
    $normalized = (Get-IzBootstrapCanonicalPath -Path $Path -AllowMissingLeaf).Normalize([Text.NormalizationForm]::FormC)
    $builder = [Text.StringBuilder]::new($normalized.Length)
    foreach ($character in $normalized.ToCharArray()) {
        $code = [int]$character
        if ($code -ge 65 -and $code -le 90) { [void]$builder.Append([char]($code + 32)) }
        else { [void]$builder.Append($character) }
    }
    return $builder.ToString()
}

function Test-IzBootstrapOverlap {
    param([string]$First, [string]$Second)
    $a = ConvertTo-IzBootstrapPathKey $First
    $b = ConvertTo-IzBootstrapPathKey $Second
    return $a -eq $b -or $a.StartsWith($b + '\', [StringComparison]::Ordinal) -or $b.StartsWith($a + '\', [StringComparison]::Ordinal)
}

function Get-IzBootstrapContextValues {
    $local = if ($env:LOCALAPPDATA) { Get-IzBootstrapCanonicalPath $env:LOCALAPPDATA -AllowMissingLeaf } else { Get-IzBootstrapCanonicalPath ([Environment]::GetFolderPath('LocalApplicationData')) }
    $install = Join-Path $local 'Programs\IZ Clinical Notes Analyzer'
    $data = Join-Path $local 'IZ Clinical Notes Analyzer'
    $maintenance = Join-Path $local 'IZ Clinical Notes Analyzer Maintenance'
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not $identity.User) { throw 'CURRENT_USER_SID_UNAVAILABLE' }
    $scopeInput = "iz-cna-maintenance-scope-v1`n$script:ProductId`n$($identity.User.Value)`n$(ConvertTo-IzBootstrapPathKey $install)`n$(ConvertTo-IzBootstrapPathKey $data)"
    return [pscustomobject]@{
        owner_sid = $identity.User.Value
        scope_id = Get-IzBootstrapUtf8Sha256 $scopeInput
        install_root = Get-IzBootstrapCanonicalPath $install -AllowMissingLeaf
        data_root = Get-IzBootstrapCanonicalPath $data -AllowMissingLeaf
        maintenance_root = Get-IzBootstrapCanonicalPath $maintenance -AllowMissingLeaf
    }
}

function Get-IzProvidedBootstrapContextValues {
    param([object]$Context)
    $required = @('owner_sid', 'scope_id', 'local_app_data_root', 'install_root', 'data_root', 'maintenance_root', 'transaction_id')
    $properties = @($Context.PSObject.Properties.Name)
    if (@($required | Where-Object { $_ -notin $properties }).Count -gt 0 -or $Context.transaction_id) { throw 'INTERNAL_CONTEXT_INVALID' }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not $identity.User -or [string]$Context.owner_sid -ne $identity.User.Value -or [string]$Context.scope_id -notmatch '^[0-9a-f]{64}$') { throw 'INTERNAL_CONTEXT_INVALID' }
    $local = Get-IzBootstrapCanonicalPath ([string]$Context.local_app_data_root) -AllowMissingLeaf
    $install = Get-IzBootstrapCanonicalPath ([string]$Context.install_root) -AllowMissingLeaf
    $data = Get-IzBootstrapCanonicalPath ([string]$Context.data_root) -AllowMissingLeaf
    $maintenance = Get-IzBootstrapCanonicalPath ([string]$Context.maintenance_root) -AllowMissingLeaf
    if (-not $install.Equals((Get-IzBootstrapCanonicalPath (Join-Path $local 'Programs\IZ Clinical Notes Analyzer') -AllowMissingLeaf), [StringComparison]::OrdinalIgnoreCase) -or
        -not $data.Equals((Get-IzBootstrapCanonicalPath (Join-Path $local 'IZ Clinical Notes Analyzer') -AllowMissingLeaf), [StringComparison]::OrdinalIgnoreCase) -or
        -not $maintenance.Equals((Get-IzBootstrapCanonicalPath (Join-Path $local 'IZ Clinical Notes Analyzer Maintenance') -AllowMissingLeaf), [StringComparison]::OrdinalIgnoreCase)) {
        throw 'INTERNAL_CONTEXT_INVALID'
    }
    $scopeInput = "iz-cna-maintenance-scope-v1`n$script:ProductId`n$($identity.User.Value)`n$(ConvertTo-IzBootstrapPathKey $install)`n$(ConvertTo-IzBootstrapPathKey $data)"
    if ((Get-IzBootstrapUtf8Sha256 $scopeInput) -cne [string]$Context.scope_id) { throw 'INTERNAL_CONTEXT_INVALID' }
    return [pscustomobject]@{
        owner_sid = [string]$Context.owner_sid
        scope_id = [string]$Context.scope_id
        install_root = $install
        data_root = $data
        maintenance_root = $maintenance
    }
}

function Get-IzBootstrapTransactionContext {
    param([object]$Context, [Guid]$TransactionId)
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

function Assert-IzBootstrapTreeNoReparse {
    param([string]$Root)
    if (-not (Test-Path -LiteralPath $Root)) { return }
    [void](Get-IzBootstrapCanonicalPath $Root)
    $pending = [Collections.Generic.Stack[string]]::new()
    $rootItem = Get-Item -LiteralPath $Root -Force
    if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'PATH_REPARSE_POINT' }
    if (-not $rootItem.PSIsContainer) { return }
    $pending.Push($rootItem.FullName)
    while ($pending.Count -gt 0) {
        $directory = $pending.Pop()
        foreach ($child in @(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop)) {
            if (($child.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'PATH_REPARSE_POINT' }
            if ($child.PSIsContainer) { $pending.Push($child.FullName) }
        }
    }
}

function Get-IzBootstrapTreeFingerprint {
    param([string]$Root, [switch]$SnapshotsOnly)
    if (-not (Test-Path -LiteralPath $Root)) { return Get-IzBootstrapUtf8Sha256 '<absent>' }
    Assert-IzBootstrapTreeNoReparse $Root
    $canonical = Get-IzBootstrapCanonicalPath $Root
    $rows = [Collections.Generic.List[string]]::new()
    foreach ($item in @(Get-ChildItem -LiteralPath $canonical -Force -Recurse | Sort-Object FullName)) {
        $relative = $item.FullName.Substring($canonical.Length).TrimStart('\').Replace('\', '/')
        if ($SnapshotsOnly -and ('/' + $relative + '/') -notmatch '/snapshot/') { continue }
        if ($item.PSIsContainer) { $rows.Add("directory|$relative") }
        else { $rows.Add("file|$relative|$($item.Length)|$(Get-IzBootstrapFileSha256 $item.FullName)") }
    }
    return Get-IzBootstrapUtf8Sha256 ($rows -join "`n")
}

function New-IzBootstrapDirectorySecurity {
    param([string]$OwnerSid)
    $sid = [Security.Principal.SecurityIdentifier]::new($OwnerSid)
    $security = [Security.AccessControl.DirectorySecurity]::new()
    $inheritance = [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
    $rule = [Security.AccessControl.FileSystemAccessRule]::new($sid, 'FullControl', $inheritance, 'None', 'Allow')
    $security.SetAccessRuleProtection($true, $false)
    $security.SetOwner($sid)
    [void]$security.AddAccessRule($rule)
    return $security
}

function New-IzBootstrapResult {
    param([string]$RequestedAction, [int]$Code, [string]$Reason, [AllowNull()][object]$Previous)
    [object[]]$previousEvidence = @()
    if ($Previous) { [object[]]$previousEvidence = @($Previous.evidence) }
    $status = switch ($Code) {
        0 { 'SUCCEEDED' }; 10 { 'CANCELLED' }; 20 { 'PREFLIGHT_FAILED' }; 21 { 'BUSY' }
        31 { 'RECOVERY_REQUIRED' }; 40 { 'REMOVAL_INCOMPLETE' }; 41 { 'REMOVED_CLEANUP_PENDING' }
        default { 'PREFLIGHT_FAILED' }
    }
    return [pscustomobject][ordered]@{
        schema = 'iz-cna-maintenance-result-v1'
        product_id = $script:ProductId
        action = $RequestedAction
        status = $status
        version = if ($Previous) { $Previous.version } else { $null }
        build = if ($Previous) { $Previous.build } else { $null }
        installer_revision = if ($Previous) { $Previous.installer_revision } else { $null }
        transaction_id = if ($Previous) { $Previous.transaction_id } else { $null }
        stage = 'FINISHED'
        code = $Code
        reason = $Reason
        evidence = @($previousEvidence)
        started_utc = if ($Previous) { $Previous.started_utc } else { [DateTime]::UtcNow.ToString('o') }
        completed_utc = [DateTime]::UtcNow.ToString('o')
    }
}

function Write-IzBootstrapExternalResult {
    param([object]$Result, [string]$Path, [AllowNull()][object]$Context)
    if (-not $Path) { return }
    if ($Context -and (Get-Command Write-IzMaintenanceResult -ErrorAction SilentlyContinue)) {
        Write-IzMaintenanceResult -ResultPath $Path -Result $Result | Out-Null
        return
    }
    try {
        $canonical = Get-IzBootstrapCanonicalPath $Path -AllowMissingLeaf
        $parent = Split-Path -Parent $canonical
        if (-not (Test-Path -LiteralPath $parent -PathType Container)) { return }
        [IO.File]::WriteAllText($canonical, ($Result | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    } catch { }
}

function Remove-IzBootstrapTemporaryRoot {
    param(
        [string]$Root,
        [object[]]$Records,
        [AllowNull()][object]$Context,
        [Guid]$TransactionId,
        [AllowNull()][string]$ControllerResultPath,
        [bool]$ControllerResultValidated
    )
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { return $true }
    $markerPath = Join-Path $Root '.iz-cna-owned-root.json'
    $markerValidated = $false
    if ($Context -and (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
        try {
            [void](Test-IzOwnedRootMarker -Context $Context -Path $Root -Role temp_helper -TransactionId $TransactionId)
            $markerValidated = $true
        } catch { return $false }
    }
    foreach ($record in @($Records)) {
        $path = Join-Path $Root ([string]$record.path)
        if (-not (Test-Path -LiteralPath $path)) { continue }
        try {
            $item = Get-Item -LiteralPath $path -Force
            if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
                [long]$item.Length -ne [long]$record.length -or (Get-IzBootstrapFileSha256 $path) -ne [string]$record.sha256) { return $false }
            [IO.File]::Delete($path)
            if (Test-Path -LiteralPath $path) { return $false }
        } catch { return $false }
    }
    if ($ControllerResultPath -and (Test-Path -LiteralPath $ControllerResultPath)) {
        if (-not $ControllerResultValidated) { return $false }
        try {
            $item = Get-Item -LiteralPath $ControllerResultPath -Force
            if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { return $false }
            [IO.File]::Delete($ControllerResultPath)
            if (Test-Path -LiteralPath $ControllerResultPath) { return $false }
        } catch { return $false }
    }
    $remaining = @(Get-ChildItem -LiteralPath $Root -Force | Where-Object { -not $_.FullName.Equals($markerPath, [StringComparison]::OrdinalIgnoreCase) })
    if ($remaining.Count -ne 0) { return $false }
    if (Test-Path -LiteralPath $markerPath) {
        if (-not $markerValidated) { return $false }
        try { [IO.File]::Delete($markerPath) } catch { return $false }
    }
    if (@(Get-ChildItem -LiteralPath $Root -Force).Count -ne 0) { return $false }
    try { [IO.Directory]::Delete($Root, $false) } catch { return $false }
    return -not (Test-Path -LiteralPath $Root)
}

function Invoke-IzRemovalBootstrap {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidateSet('Uninstall', 'RemoveData')][string]$Action,
        [Parameter(Mandatory)][string]$SourceRoot,
        [ValidateSet('Package', 'Installed')][string]$SourceKind = 'Package',
        [switch]$NoPause,
        [switch]$NonInteractive,
        [string]$ResultPath = '',
        [switch]$AssumeYes,
        [object[]]$RemainingArguments = @(),
        [AllowNull()][object]$Context = $null
    )
    $requestedAction = [string]$Action
    $requestedSourceRoot = [string]$SourceRoot
    $requestedSourceKind = [string]$SourceKind
    $requestedNoPause = [bool]$NoPause
    $requestedNonInteractive = [bool]$NonInteractive
    $requestedResultPath = [string]$ResultPath
    $requestedAssumeYes = [bool]$AssumeYes
    [object[]]$requestedRemainingArguments = @()
    if ($null -ne $RemainingArguments) { $requestedRemainingArguments = @($RemainingArguments) }
    $requestedContext = $Context
    $temporaryRoot = $null
    $maintenanceContext = $null
    $markerContext = $null
    $result = $null
    $applicationOutcomeVerified = $false
    $cleanupSucceeded = $true
    $records = @()
    $transactionId = [Guid]::Empty
    $controllerResultPath = $null
    $controllerResultValidated = $false
    try {
        if ($requestedRemainingArguments.Count -gt 0) { throw 'UNSUPPORTED_ARGUMENT' }
        if ($requestedAssumeYes) { Write-Host 'The legacy AssumeYes flag does not authorize local-data deletion.' -ForegroundColor Yellow }
        $bootstrapContext = if ($requestedContext) { Get-IzProvidedBootstrapContextValues -Context $requestedContext } else { Get-IzBootstrapContextValues }
        $source = Get-IzBootstrapCanonicalPath $requestedSourceRoot
        Assert-IzBootstrapTreeNoReparse $source
        $expectedInstalledSource = Join-Path $bootstrapContext.install_root 'installer'
        if ($requestedSourceKind -eq 'Installed') {
            if (-not $source.Equals((Get-IzBootstrapCanonicalPath $expectedInstalledSource), [StringComparison]::OrdinalIgnoreCase)) { throw 'INSTALLED_SOURCE_ROOT_MISMATCH' }
        } else {
            foreach ($protectedRoot in @($bootstrapContext.install_root, $bootstrapContext.data_root, $bootstrapContext.maintenance_root)) {
                if (Test-IzBootstrapOverlap $source $protectedRoot) { throw 'PACKAGE_SOURCE_OVERLAP' }
            }
        }

        $manifestPath = Join-Path $source 'maintenance-bundle-manifest.json'
        if ($script:ExpectedManifestSha256 -notmatch '^[0-9a-f]{64}$') { throw 'BUNDLE_MANIFEST_HASH_UNRENDERED' }
        if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf) -or (Get-IzBootstrapFileSha256 $manifestPath) -ne $script:ExpectedManifestSha256) { throw 'BUNDLE_MANIFEST_HASH_MISMATCH' }
        try { $manifest = ConvertFrom-Json -InputObject ([IO.File]::ReadAllText($manifestPath, [Text.UTF8Encoding]::new($false, $true))) -ErrorAction Stop }
        catch { throw 'BUNDLE_MANIFEST_CORRUPT' }
        $manifestProperties = @($manifest.PSObject.Properties.Name)
        if ($manifestProperties.Count -ne 3 -or @(@('schema', 'product_id', 'files') | Where-Object { $_ -notin $manifestProperties }).Count -gt 0) { throw 'BUNDLE_MANIFEST_INVALID' }
        if ($manifest.schema -ne $script:BundleManifestSchema -or $manifest.product_id -ne $script:ProductId) { throw 'BUNDLE_MANIFEST_INVALID' }
        $records = @($manifest.files)
        if ($records.Count -ne $script:BundleFiles.Count) { throw 'BUNDLE_FILE_SET_INVALID' }
        for ($index = 0; $index -lt $script:BundleFiles.Count; $index++) {
            $record = $records[$index]
            $properties = @($record.PSObject.Properties.Name)
            if ($properties.Count -ne 3 -or @(@('path', 'length', 'sha256') | Where-Object { $_ -notin $properties }).Count -gt 0) { throw 'BUNDLE_FILE_RECORD_INVALID' }
            if ([string]$record.path -cne $script:BundleFiles[$index] -or $record.length -isnot [ValueType] -or [long]$record.length -lt 0 -or [string]$record.sha256 -notmatch '^[0-9a-f]{64}$') { throw 'BUNDLE_FILE_RECORD_INVALID' }
            $sourceFile = Join-Path $source ([string]$record.path)
            if (-not (Test-Path -LiteralPath $sourceFile -PathType Leaf)) { throw 'BUNDLE_FILE_MISSING' }
            $sourceItem = Get-Item -LiteralPath $sourceFile
            if ([long]$sourceItem.Length -ne [long]$record.length -or (Get-IzBootstrapFileSha256 $sourceFile) -ne [string]$record.sha256) { throw 'BUNDLE_FILE_HASH_MISMATCH' }
        }

        $transactionId = [Guid]::NewGuid()
        $temporaryParent = Get-IzBootstrapCanonicalPath ([IO.Path]::GetTempPath())
        $temporaryName = 'IZ-CNA-Maintenance-' + $bootstrapContext.scope_id.Substring(0, 16) + '-' + $transactionId.ToString('N')
        $temporaryRoot = Get-IzBootstrapCanonicalPath (Join-Path $temporaryParent $temporaryName) -AllowMissingLeaf
        foreach ($protectedRoot in @($bootstrapContext.install_root, $bootstrapContext.data_root, $bootstrapContext.maintenance_root, $source)) {
            if (Test-IzBootstrapOverlap $temporaryRoot $protectedRoot) { throw 'TEMP_HELPER_OVERLAP' }
        }
        if (Test-Path -LiteralPath $temporaryRoot) { throw 'TEMP_HELPER_EXISTS' }
        $security = New-IzBootstrapDirectorySecurity $bootstrapContext.owner_sid
        [IO.Directory]::CreateDirectory($temporaryRoot, $security) | Out-Null

        foreach ($record in $records) {
            $sourceFile = Join-Path $source ([string]$record.path)
            $destinationFile = Join-Path $temporaryRoot ([string]$record.path)
            $input = [IO.File]::Open($sourceFile, 'Open', 'Read', 'Read')
            $output = [IO.File]::Open($destinationFile, 'CreateNew', 'Write', 'None')
            try { $input.CopyTo($output); $output.Flush($true) }
            finally { $output.Dispose(); $input.Dispose() }
            if ((Get-Item -LiteralPath $destinationFile).Length -ne [long]$record.length -or (Get-IzBootstrapFileSha256 $destinationFile) -ne [string]$record.sha256) { throw 'TEMP_BUNDLE_HASH_MISMATCH' }
        }

        Import-Module (Join-Path $temporaryRoot 'maintenance-common.psm1') -Force -ErrorAction Stop
        Import-Module (Join-Path $temporaryRoot 'maintenance-runtime.psm1') -Force -ErrorAction Stop
        $maintenanceContext = if ($requestedContext) { $requestedContext } else { Get-IzMaintenanceContext }
        Assert-IzMaintenanceContext -Context $maintenanceContext | Out-Null
        if ($maintenanceContext.transaction_id) { throw 'INTERNAL_CONTEXT_INVALID' }
        $markerContext = Get-IzBootstrapTransactionContext -Context $maintenanceContext -TransactionId $transactionId
        [void](Write-IzOwnedRootMarker -Context $markerContext -Path $temporaryRoot -Role temp_helper -TransactionId $transactionId)
        [void](Test-IzOwnedRootMarker -Context $markerContext -Path $temporaryRoot -Role temp_helper -TransactionId $transactionId)

        if (Test-Path -LiteralPath $maintenanceContext.install_receipt_path -PathType Leaf) {
            $stopResult = Stop-IzOwnedRuntime -Context $maintenanceContext -TimeoutSeconds 30
            if ($stopResult.status -notin @('stopped', 'already_stopped')) { throw 'RUNTIME_STOP_FAILED' }
        }

        if ($requestedResultPath) {
            $externalResult = Get-IzCanonicalPath -Path $requestedResultPath -AllowMissingLeaf
            foreach ($protectedRoot in @($temporaryRoot, $maintenanceContext.install_root, $maintenanceContext.data_root, $maintenanceContext.maintenance_root, $source)) {
                if (Test-IzBootstrapOverlap $externalResult $protectedRoot) { throw 'RESULT_PATH_OVERLAP' }
            }
        }
        $programBefore = Get-IzBootstrapTreeFingerprint $maintenanceContext.install_root
        $dataBefore = Get-IzBootstrapTreeFingerprint $maintenanceContext.data_root
        $snapshotBefore = Get-IzBootstrapTreeFingerprint $maintenanceContext.maintenance_root -SnapshotsOnly

        $controllerResultPath = Join-Path $temporaryRoot 'controller-result.json'
        Set-Location $temporaryRoot
        . (Join-Path $temporaryRoot 'maintenance-windows.ps1') -NoRun
        $invokeParameters = @{ Action = $requestedAction; NoPause = $true; ResultPath = $controllerResultPath; Context = $maintenanceContext }
        if ($requestedNonInteractive) { $invokeParameters.NonInteractive = $true }
        $returned = Invoke-IzMaintenanceAction @invokeParameters
        $result = Read-IzMaintenanceResult -Path $controllerResultPath
        if ($null -eq $returned -or [int]$returned.code -ne [int]$result.code -or [string]$returned.status -ne [string]$result.status -or [string]$result.action -ne $requestedAction) { throw 'CONTROLLER_RESULT_MISMATCH' }
        $controllerResultValidated = $true

        if ([int]$result.code -eq 0) {
            if ($requestedAction -eq 'Uninstall') {
                $applicationOutcomeVerified = -not (Test-Path -LiteralPath $maintenanceContext.install_root) -and
                    (Get-IzBootstrapTreeFingerprint $maintenanceContext.data_root) -eq $dataBefore -and
                    (Get-IzBootstrapTreeFingerprint $maintenanceContext.maintenance_root -SnapshotsOnly) -eq $snapshotBefore
            } else {
                $applicationOutcomeVerified = -not (Test-Path -LiteralPath $maintenanceContext.install_root) -and
                    -not (Test-Path -LiteralPath $maintenanceContext.data_root) -and
                    -not (Test-Path -LiteralPath $maintenanceContext.maintenance_root)
            }
            if (-not $applicationOutcomeVerified) { $result = New-IzBootstrapResult -RequestedAction $Action -Code 40 -Reason FINAL_VERIFICATION_FAILED -Previous $result }
        } elseif ([int]$result.code -in @(10, 20, 31)) {
            $programUnchanged = (Get-IzBootstrapTreeFingerprint $maintenanceContext.install_root) -eq $programBefore
            $dataUnchanged = (Get-IzBootstrapTreeFingerprint $maintenanceContext.data_root) -eq $dataBefore
            if (-not ($programUnchanged -and $dataUnchanged)) { $result = New-IzBootstrapResult -RequestedAction $Action -Code 40 -Reason PREMATURE_MUTATION_DETECTED -Previous $result }
        }
    } catch {
        if (-not $result) { $result = New-IzBootstrapResult -RequestedAction $requestedAction -Code 20 -Reason BOOTSTRAP_PREFLIGHT_FAILED -Previous $null }
    } finally {
        if ($temporaryRoot -and (Test-Path -LiteralPath $temporaryRoot)) {
            try {
                Set-Location (Split-Path -Parent $temporaryRoot)
                $cleanupSucceeded = Remove-IzBootstrapTemporaryRoot -Root $temporaryRoot -Records @($records) -Context $markerContext -TransactionId $transactionId -ControllerResultPath $controllerResultPath -ControllerResultValidated $controllerResultValidated
            } catch { $cleanupSucceeded = $false }
        }
    }

    if (-not $result) { $result = New-IzBootstrapResult -RequestedAction $requestedAction -Code 20 -Reason BOOTSTRAP_PREFLIGHT_FAILED -Previous $null }
    if ([int]$result.code -eq 0 -and -not $cleanupSucceeded) {
        $result = New-IzBootstrapResult -RequestedAction $requestedAction -Code 41 -Reason TEMP_CLEANUP_PENDING -Previous $result
    }
    Write-IzBootstrapExternalResult -Result $result -Path $requestedResultPath -Context $maintenanceContext
    Write-Host ($result | ConvertTo-Json -Depth 8 -Compress)
    if (-not $requestedNoPause) {
        Write-Host ''
        Read-Host 'Press Enter to close' | Out-Null
    }
    return [int]$result.code
}

if (-not $NoRun) {
    $exitCode = Invoke-IzRemovalBootstrap -Action $Action -SourceRoot $SourceRoot -SourceKind $SourceKind -NoPause:$NoPause -NonInteractive:$NonInteractive -ResultPath $ResultPath -AssumeYes:$AssumeYes -RemainingArguments $RemainingArguments
    exit [int]$exitCode
}
