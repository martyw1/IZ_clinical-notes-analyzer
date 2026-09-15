Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Security
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$script:BackupMagic = [Text.Encoding]::ASCII.GetBytes('IZCNABK2')
$script:BackupEncryption = 'aes-256-cbc-hmac-sha256-dpapi-current-user-v1'
$script:DataDirectoryName = 'IZ Clinical Notes Analyzer'
$script:ManifestName = 'backup-manifest.json'
$script:BufferBytes = 1048576
$script:MaxHeaderBytes = 65536
$script:MaxArchiveBytes = [int64]68719476736
$script:MaxEntryBytes = [int64]34359738368
$script:MaxExpandedBytes = [int64]137438953472
$script:MaxEntryCount = 100000
$script:MaxPathChars = 1024
$script:MaxManifestBytes = 67108864

$commonModulePath = Join-Path $PSScriptRoot 'maintenance-common.psm1'
if (-not (Test-Path -LiteralPath $commonModulePath -PathType Leaf)) {
    throw 'MAINTENANCE_COMMON_MODULE_MISSING'
}
Import-Module $commonModulePath -ErrorAction Stop

function New-IzBackupError {
    param(
        [Parameter(Mandatory = $true)][string]$Reason,
        [int]$ExitCode = 20
    )
    $exception = New-Object InvalidOperationException($Reason)
    $exception.Data['iz_reason'] = $Reason
    $exception.Data['iz_exit_code'] = $ExitCode
    return $exception
}

function Throw-IzBackupError {
    param(
        [Parameter(Mandatory = $true)][string]$Reason,
        [int]$ExitCode = 20
    )
    throw (New-IzBackupError -Reason $Reason -ExitCode $ExitCode)
}

function Get-IzSafeErrorReason {
    param([Management.Automation.ErrorRecord]$ErrorRecord, [string]$Fallback)
    if ($ErrorRecord -and $ErrorRecord.Exception -and $ErrorRecord.Exception.Data.Contains('iz_reason')) {
        return [string]$ErrorRecord.Exception.Data['iz_reason']
    }
    return $Fallback
}

function Get-IzFullPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { Throw-IzBackupError 'BACKUP_PATH_INVALID' }
    try { return [IO.Path]::GetFullPath($Path).TrimEnd('\', '/') }
    catch { Throw-IzBackupError 'BACKUP_PATH_INVALID' }
}

function Test-IzSamePath {
    param([string]$Left, [string]$Right)
    return (Get-IzFullPath $Left).Equals((Get-IzFullPath $Right), [StringComparison]::OrdinalIgnoreCase)
}

function Assert-IzBackupContainedPath {
    param([string]$Path, [string]$Parent, [switch]$AllowMissingLeaf)
    Assert-IzContainedPath -Path $Path -Parent $Parent -AllowMissingLeaf:$AllowMissingLeaf | Out-Null
    return (Get-IzFullPath $Path)
}

function Get-IzAsciiPathKey {
    param([Parameter(Mandatory = $true)][string]$Path)
    $normalized = $Path.Normalize([Text.NormalizationForm]::FormC).Replace('\', '/')
    $builder = New-Object Text.StringBuilder($normalized.Length)
    foreach ($character in $normalized.ToCharArray()) {
        $code = [int][char]$character
        if ($code -ge 65 -and $code -le 90) {
            [void]$builder.Append([char]($code + 32))
        } else {
            [void]$builder.Append($character)
        }
    }
    return $builder.ToString()
}

function Get-IzSha256Bytes {
    param([Parameter(Mandatory = $true)][byte[]]$Bytes)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return $sha.ComputeHash($Bytes) } finally { $sha.Dispose() }
}

function ConvertTo-IzHex {
    param([Parameter(Mandatory = $true)][byte[]]$Bytes)
    return ([BitConverter]::ToString($Bytes)).Replace('-', '').ToLowerInvariant()
}

function Get-IzSha256Text {
    param([Parameter(Mandatory = $true)][string]$Text)
    return ConvertTo-IzHex (Get-IzSha256Bytes ([Text.UTF8Encoding]::new($false).GetBytes($Text)))
}

function Get-IzFileSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function New-IzRandomBytes {
    param([Parameter(Mandatory = $true)][int]$Length)
    $bytes = New-Object byte[] $Length
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return $bytes
}

function Write-IzUInt32BigEndian {
    param([IO.Stream]$Stream, [uint32]$Value)
    $bytes = [BitConverter]::GetBytes($Value)
    if ([BitConverter]::IsLittleEndian) { [Array]::Reverse($bytes) }
    $Stream.Write($bytes, 0, $bytes.Length)
}

function Read-IzExactBytes {
    param([IO.Stream]$Stream, [int]$Count, [string]$Reason)
    $bytes = New-Object byte[] $Count
    $offset = 0
    while ($offset -lt $Count) {
        $read = $Stream.Read($bytes, $offset, $Count - $offset)
        if ($read -le 0) { Throw-IzBackupError $Reason }
        $offset += $read
    }
    return $bytes
}

function Read-IzUInt32BigEndian {
    param([IO.Stream]$Stream)
    $bytes = Read-IzExactBytes -Stream $Stream -Count 4 -Reason 'BACKUP_HEADER_TRUNCATED'
    if ([BitConverter]::IsLittleEndian) { [Array]::Reverse($bytes) }
    return [BitConverter]::ToUInt32($bytes, 0)
}

function Test-IzFixedTimeEquals {
    param([byte[]]$Left, [byte[]]$Right)
    if ($null -eq $Left -or $null -eq $Right -or $Left.Length -ne $Right.Length) { return $false }
    $difference = 0
    for ($index = 0; $index -lt $Left.Length; $index++) {
        $difference = $difference -bor ($Left[$index] -bxor $Right[$index])
    }
    return ($difference -eq 0)
}

function Get-IzAvailableBytes {
    param([Parameter(Mandatory = $true)][string]$Path)
    $full = Get-IzFullPath $Path
    try {
        $root = [IO.Path]::GetPathRoot($full)
        if ([string]::IsNullOrWhiteSpace($root)) { Throw-IzBackupError 'BACKUP_VOLUME_INVALID' }
        return [int64]([IO.DriveInfo]::new($root).AvailableFreeSpace)
    } catch {
        if ($_.Exception.Data.Contains('iz_reason')) { throw }
        Throw-IzBackupError 'BACKUP_SPACE_UNAVAILABLE'
    }
}

function Assert-IzFreeSpace {
    param([string]$Path, [int64]$RequiredBytes)
    if ($RequiredBytes -lt 0 -or (Get-IzAvailableBytes $Path) -lt $RequiredBytes) {
        Throw-IzBackupError 'BACKUP_DISK_SPACE_INSUFFICIENT'
    }
}

function Write-IzJsonCreateNew {
    param([string]$Path, [object]$Value)
    $json = $Value | ConvertTo-Json -Depth 12 -Compress
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($json)
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush()
    } finally { $stream.Dispose() }
    Protect-IzMaintenancePath -Path $Path | Out-Null
}

function New-IzRuntimeOperationPaths {
    param([object]$Context, [string]$Stem)
    $suffix = [Guid]::NewGuid().ToString('N').Substring(0, 12)
    $requestPath = Join-Path $Context.requests_root "q-$suffix.json"
    $resultPath = Join-Path $Context.results_root "s-$suffix.json"
    Assert-IzBackupContainedPath -Path $requestPath -Parent $Context.transaction_root -AllowMissingLeaf | Out-Null
    Assert-IzBackupContainedPath -Path $resultPath -Parent $Context.transaction_root -AllowMissingLeaf | Out-Null
    return [pscustomobject]@{ request_path = $requestPath; result_path = $resultPath }
}

function ConvertTo-IzBackupProcessArgument {
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

function Invoke-IzRuntimeMaintenance {
    param(
        [object]$Context,
        [ValidateSet('SnapshotDatabase', 'VerifyData')][string]$Operation,
        [object]$Request,
        [ValidateSet('Installed', 'Package', 'Candidate', 'SourceTest')][string]$RuntimeRole,
        [AllowNull()][object]$Manifest,
        [string]$Stem
    )
    $paths = New-IzRuntimeOperationPaths -Context $Context -Stem $Stem
    Write-IzJsonCreateNew -Path $paths.request_path -Value $Request
    $spec = Get-IzRuntimeCommandSpec -Context $Context -RuntimeRole $RuntimeRole -Operation $Operation -RequestPath $paths.request_path -ResultPath $paths.result_path -Manifest $Manifest
    $exitCode = 31
    $process = $null
    try {
        $start=[Diagnostics.ProcessStartInfo]::new()
        $start.FileName=[string]$spec.file_path;$start.UseShellExecute=$false;$start.CreateNoWindow=$true
        $start.Arguments=(@($spec.arguments|ForEach-Object{ConvertTo-IzBackupProcessArgument ([string]$_)})-join' ')
        if($spec.working_directory){$start.WorkingDirectory=[string]$spec.working_directory}
        foreach($name in @('IZ_CNA_LOCAL_SQLITE_DB_PATH','LOCAL_SQLITE_DB_PATH')){
            if($start.EnvironmentVariables.ContainsKey($name)){$start.EnvironmentVariables.Remove($name)}
        }
        $start.EnvironmentVariables['IZ_CNA_ENV_FILE']=Join-Path $Context.data_root '.env'
        $start.EnvironmentVariables['IZ_CNA_LOCAL_APP_DATA_DIR']=$Context.data_root
        $process=[Diagnostics.Process]::Start($start)
        if(-not $process){Throw-IzBackupError 'RUNTIME_PROCESS_START_FAILED' 31}
        while(-not $process.WaitForExit(1000)){}
        $exitCode=[int]$process.ExitCode
    } finally {
        if($process){
            if(-not $process.HasExited){try{$process.Kill();$process.WaitForExit()}catch{}}
            $process.Dispose()
        }
    }
    if (-not (Test-Path -LiteralPath $paths.result_path -PathType Leaf)) {
        Throw-IzBackupError 'RUNTIME_RESULT_MISSING' 31
    }
    $result = Read-IzRuntimeMaintenanceResult -Path $paths.result_path -Operation $Operation
    if ($exitCode -ne 0 -or $result.status -ne 'success') {
        $reason = if ($result.reason -match '^[a-z0-9_]+$') { "RUNTIME_$(([string]$result.reason).ToUpperInvariant())" } else { 'RUNTIME_OPERATION_FAILED' }
        $code = if ($exitCode -eq 20) { 20 } else { 31 }
        Throw-IzBackupError $reason $code
    }
    return $result
}

function Get-IzDataIdentityValue {
    param([Parameter(Mandatory = $true)][object]$DataIdentity)
    if ($DataIdentity -is [string]) { return [string]$DataIdentity }
    if ($DataIdentity.PSObject.Properties.Name -contains 'data_identity') { return [string]$DataIdentity.data_identity }
    Throw-IzBackupError 'DATA_IDENTITY_INVALID'
}

function Get-IzRelativeArchivePath {
    param([string]$Root, [string]$FullName)
    $rootPath = (Get-IzFullPath $Root) + '\'
    $fullPath = Get-IzFullPath $FullName
    if (-not $fullPath.StartsWith($rootPath, [StringComparison]::OrdinalIgnoreCase)) {
        Throw-IzBackupError 'BACKUP_SOURCE_OUTSIDE_DATA_ROOT'
    }
    $relative = $fullPath.Substring($rootPath.Length).Replace('\', '/')
    if ([string]::IsNullOrWhiteSpace($relative)) { Throw-IzBackupError 'BACKUP_SOURCE_PATH_INVALID' }
    return $relative.Normalize([Text.NormalizationForm]::FormC)
}

function Assert-IzSafeArchiveSegment {
    param([string]$Segment)
    if ([string]::IsNullOrWhiteSpace($Segment) -or $Segment -eq '.' -or $Segment -eq '..') {
        Throw-IzBackupError 'BACKUP_ARCHIVE_PATH_INVALID'
    }
    if ($Segment.Length -gt 255 -or $Segment.EndsWith('.') -or $Segment.EndsWith(' ')) {
        Throw-IzBackupError 'BACKUP_ARCHIVE_PATH_INVALID'
    }
    foreach ($character in $Segment.ToCharArray()) {
        if ([char]::IsControl($character) -or $character -eq ':' -or [IO.Path]::GetInvalidFileNameChars() -contains $character) {
            Throw-IzBackupError 'BACKUP_ARCHIVE_PATH_INVALID'
        }
    }
    $baseName = $Segment.Split('.')[0]
    if ($baseName -match '^(?i:CON|PRN|AUX|NUL|CLOCK\$|CONIN\$|CONOUT\$|COM[1-9]|LPT[1-9])$') {
        Throw-IzBackupError 'BACKUP_ARCHIVE_DEVICE_NAME'
    }
}

function ConvertTo-IzValidatedArchiveName {
    param([Parameter(Mandatory = $true)][string]$Name)
    if ($Name.IndexOf([char]0) -ge 0 -or $Name.StartsWith('/') -or $Name.StartsWith('\') -or $Name -match '^[A-Za-z]:') {
        Throw-IzBackupError 'BACKUP_ARCHIVE_PATH_INVALID'
    }
    $normalized = $Name.Replace('\', '/').Normalize([Text.NormalizationForm]::FormC)
    if ($normalized.Length -gt $script:MaxPathChars) { Throw-IzBackupError 'BACKUP_ARCHIVE_PATH_TOO_LONG' }
    $isDirectory = $normalized.EndsWith('/')
    $trimmed = $normalized.TrimEnd('/')
    if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.Contains('//')) {
        Throw-IzBackupError 'BACKUP_ARCHIVE_PATH_INVALID'
    }
    $segments = @($trimmed.Split('/'))
    foreach ($segment in $segments) { Assert-IzSafeArchiveSegment $segment }
    if ($segments[0] -ne $script:DataDirectoryName -and $trimmed -ne $script:ManifestName) {
        Throw-IzBackupError 'BACKUP_ARCHIVE_LAYOUT_INVALID'
    }
    if ($trimmed -eq $script:ManifestName -and $isDirectory) { Throw-IzBackupError 'BACKUP_ARCHIVE_LAYOUT_INVALID' }
    if ($segments[0] -eq $script:DataDirectoryName -and $segments.Count -eq 1 -and -not $isDirectory) {
        Throw-IzBackupError 'BACKUP_ARCHIVE_LAYOUT_INVALID'
    }
    return [pscustomobject]@{ path = $trimmed; is_directory = $isDirectory; key = $trimmed }
}

function Get-IzBackupSourcePlan {
    param(
        [object]$Context,
        [string]$DatabaseRelativePath,
        [string]$SnapshotDatabasePath
    )
    $dataRoot = Get-IzFullPath $Context.data_root
    $rootItem = Get-Item -Force -LiteralPath $dataRoot
    if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        Throw-IzBackupError 'BACKUP_SOURCE_REPARSE_POINT'
    }
    $databaseKey = $DatabaseRelativePath.Replace('\', '/').Normalize([Text.NormalizationForm]::FormC)
    $excludedDatabaseKeys = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($suffix in @('', '-wal', '-shm', '-journal')) { [void]$excludedDatabaseKeys.Add($databaseKey + $suffix) }
    $archiveKeys = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    [void]$archiveKeys.Add($script:DataDirectoryName)
    $entries = New-Object Collections.Generic.List[object]
    $entries.Add([pscustomobject]@{
        archive_path = "$($script:DataDirectoryName)/"
        relative_path = ''
        source_path = $null
        is_directory = $true
        last_write_utc = $rootItem.LastWriteTimeUtc
        expected_length = [int64]0
    })
    $selectedDatabaseSeen = $false
    $items = @(Get-ChildItem -Force -LiteralPath $dataRoot -Recurse | Sort-Object -Property FullName)
    if ($items.Count + 2 -gt $script:MaxEntryCount) { Throw-IzBackupError 'BACKUP_SOURCE_ENTRY_LIMIT' }
    foreach ($item in $items) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            Throw-IzBackupError 'BACKUP_SOURCE_REPARSE_POINT'
        }
        $relative = Get-IzRelativeArchivePath -Root $dataRoot -FullName $item.FullName
        $safeName = ConvertTo-IzValidatedArchiveName "$($script:DataDirectoryName)/$relative$(if ($item.PSIsContainer) { '/' } else { '' })"
        $relativeKey = $relative.Replace('\', '/').Normalize([Text.NormalizationForm]::FormC)
        if (-not $item.PSIsContainer -and $relativeKey.Equals($databaseKey, [StringComparison]::OrdinalIgnoreCase)) {
            $selectedDatabaseSeen = $true
            continue
        }
        if (-not $item.PSIsContainer -and $excludedDatabaseKeys.Contains($relativeKey)) { continue }
        if (-not $archiveKeys.Add($safeName.key)) { Throw-IzBackupError 'BACKUP_SOURCE_PATH_COLLISION' }
        $length = if ($item.PSIsContainer) { [int64]0 } else { [int64]$item.Length }
        if ($length -gt $script:MaxEntryBytes) { Throw-IzBackupError 'BACKUP_SOURCE_FILE_LIMIT' }
        $entries.Add([pscustomobject]@{
            archive_path = $safeName.path + $(if ($safeName.is_directory) { '/' } else { '' })
            relative_path = $relative
            source_path = $(if ($item.PSIsContainer) { $null } else { $item.FullName })
            is_directory = [bool]$item.PSIsContainer
            last_write_utc = $item.LastWriteTimeUtc
            expected_length = $length
        })
    }
    if (-not $selectedDatabaseSeen) { Throw-IzBackupError 'BACKUP_SELECTED_DATABASE_MISSING' }
    $snapshotItem = Get-Item -Force -LiteralPath $SnapshotDatabasePath
    if ($snapshotItem.PSIsContainer -or ($snapshotItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        Throw-IzBackupError 'BACKUP_SNAPSHOT_INVALID'
    }
    $snapshotName = ConvertTo-IzValidatedArchiveName "$($script:DataDirectoryName)/$DatabaseRelativePath"
    if (-not $archiveKeys.Add($snapshotName.key)) { Throw-IzBackupError 'BACKUP_SOURCE_PATH_COLLISION' }
    $entries.Add([pscustomobject]@{
        archive_path = $snapshotName.path
        relative_path = $DatabaseRelativePath
        source_path = $snapshotItem.FullName
        is_directory = $false
        last_write_utc = $snapshotItem.LastWriteTimeUtc
        expected_length = [int64]$snapshotItem.Length
    })
    $ordered = @($entries | Sort-Object -Property @{ Expression = { Get-IzAsciiPathKey $_.archive_path } })
    $totalBytes = [int64]0
    foreach ($entry in $ordered) {
        if (-not $entry.is_directory) {
            if ($totalBytes -gt $script:MaxExpandedBytes - $entry.expected_length) { Throw-IzBackupError 'BACKUP_SOURCE_SIZE_LIMIT' }
            $totalBytes += $entry.expected_length
        }
    }
    return [pscustomobject]@{ entries = $ordered; total_bytes = $totalBytes }
}

function Set-IzZipEntryTime {
    param([IO.Compression.ZipArchiveEntry]$Entry, [DateTime]$Timestamp)
    $minimum = [DateTimeOffset]::new(1980, 1, 1, 0, 0, 0, [TimeSpan]::Zero)
    $maximum = [DateTimeOffset]::new(2107, 12, 31, 23, 59, 58, [TimeSpan]::Zero)
    $value = [DateTimeOffset]::new($Timestamp.ToUniversalTime())
    if ($value -lt $minimum) { $value = $minimum }
    if ($value -gt $maximum) { $value = $maximum }
    $Entry.LastWriteTime = $value
}

function Copy-IzFileToZipEntry {
    param([string]$SourcePath, [IO.Compression.ZipArchiveEntry]$Entry, [int64]$ExpectedLength)
    $source = $null
    $target = $null
    $sha = $null
    $buffer = New-Object byte[] $script:BufferBytes
    $length = [int64]0
    $hash = $null
    try {
        $source = [IO.File]::Open($SourcePath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        $target = $Entry.Open()
        $sha = [Security.Cryptography.SHA256]::Create()
        while (($read = $source.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $target.Write($buffer, 0, $read)
            [void]$sha.TransformBlock($buffer, 0, $read, $buffer, 0)
            $length += $read
            if ($length -gt $script:MaxEntryBytes) { Throw-IzBackupError 'BACKUP_SOURCE_FILE_LIMIT' }
        }
        [void]$sha.TransformFinalBlock((New-Object byte[] 0), 0, 0)
        $hash = ConvertTo-IzHex $sha.Hash
    } finally {
        if ($target) { $target.Dispose() }
        if ($source) { $source.Dispose() }
        if ($sha) { $sha.Dispose() }
        $buffer = $null
    }
    if ($length -ne $ExpectedLength) { Throw-IzBackupError 'BACKUP_SOURCE_CHANGED' }
    return [pscustomobject]@{ length = $length; sha256 = $hash }
}

function Get-IzInventoryDigest {
    param([object[]]$Files, [string[]]$Directories)
    $canonical = [ordered]@{ files = @($Files); directories = @($Directories) } | ConvertTo-Json -Depth 6 -Compress
    return Get-IzSha256Text $canonical
}

function New-IzPlainArchive {
    param(
        [object]$Context,
        [object]$SnapshotResult,
        [string]$SnapshotDatabasePath,
        [string]$ArchivePath
    )
    $plan = Get-IzBackupSourcePlan -Context $Context -DatabaseRelativePath ([string]$SnapshotResult.database_relative_path) -SnapshotDatabasePath $SnapshotDatabasePath
    Assert-IzFreeSpace -Path $Context.transaction_root -RequiredBytes ([int64]($plan.total_bytes + 67108864))
    $fileInventory = New-Object Collections.Generic.List[object]
    $directoryInventory = New-Object Collections.Generic.List[string]
    $archiveStream = [IO.File]::Open($ArchivePath, [IO.FileMode]::CreateNew, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    $archive = New-Object IO.Compression.ZipArchive($archiveStream, [IO.Compression.ZipArchiveMode]::Create, $true)
    try {
        foreach ($item in $plan.entries) {
            $entry = $archive.CreateEntry([string]$item.archive_path, [IO.Compression.CompressionLevel]::Optimal)
            Set-IzZipEntryTime -Entry $entry -Timestamp $item.last_write_utc
            if ($item.is_directory) {
                if ($item.relative_path) { $directoryInventory.Add([string]$item.relative_path) }
                continue
            }
            $copied = Copy-IzFileToZipEntry -SourcePath $item.source_path -Entry $entry -ExpectedLength $item.expected_length
            $fileInventory.Add([ordered]@{
                path = [string]$item.relative_path
                length = [int64]$copied.length
                sha256 = [string]$copied.sha256
            })
        }
        $files = $fileInventory.ToArray()
        $directories = @($directoryInventory.ToArray() | Sort-Object)
        $manifest = [ordered]@{
            format = 'iz-cna-local-data-v2'
            version = 2
            created_at = [DateTime]::UtcNow.ToString('o')
            source = 'local-app-data'
            restore_scope = 'same-windows-user'
            profile_snapshot_identity = [string]$SnapshotResult.profile_snapshot_identity
            source_identity_hash = [string]$SnapshotResult.source_identity_hash
            environment_sha256 = [string]$SnapshotResult.environment_sha256
            database_relative_path = [string]$SnapshotResult.database_relative_path
            database_sha256 = [string]$SnapshotResult.database_sha256
            schema_version = [int]$SnapshotResult.schema_version
            file_count = [int]$files.Count
            directory_count = [int]$directories.Count
            total_bytes = [int64]$plan.total_bytes
            inventory_sha256 = Get-IzInventoryDigest -Files $files -Directories $directories
            files = $files
            directories = $directories
        }
        $manifestBytes = [Text.UTF8Encoding]::new($false).GetBytes(($manifest | ConvertTo-Json -Depth 8 -Compress))
        if ($manifestBytes.Length -gt $script:MaxManifestBytes) { Throw-IzBackupError 'BACKUP_MANIFEST_SIZE_LIMIT' }
        $manifestEntry = $archive.CreateEntry($script:ManifestName, [IO.Compression.CompressionLevel]::Optimal)
        Set-IzZipEntryTime -Entry $manifestEntry -Timestamp ([DateTime]::UtcNow)
        $manifestStream = $manifestEntry.Open()
        try { $manifestStream.Write($manifestBytes, 0, $manifestBytes.Length) } finally { $manifestStream.Dispose() }
    } finally {
        $archive.Dispose()
        $archiveStream.Dispose()
    }
    $archiveItem = Get-Item -LiteralPath $ArchivePath
    if ($archiveItem.Length -le 0 -or $archiveItem.Length -gt $script:MaxArchiveBytes) { Throw-IzBackupError 'BACKUP_ARCHIVE_SIZE_LIMIT' }
    return [pscustomobject]@{
        path = $archiveItem.FullName
        length = [int64]$archiveItem.Length
        sha256 = Get-IzFileSha256 $archiveItem.FullName
        manifest = $manifest
    }
}

function Protect-IzPlainArchive {
    param([object]$Archive, [string]$OutputPath)
    $rawKey = New-IzRandomBytes 64
    $encKey = New-Object byte[] 32
    $macKey = New-Object byte[] 32
    [Array]::Copy($rawKey, 0, $encKey, 0, 32)
    [Array]::Copy($rawKey, 32, $macKey, 0, 32)
    $iv = New-IzRandomBytes 16
    try {
        try {
            $protectedKey = [Security.Cryptography.ProtectedData]::Protect($rawKey, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
        } catch { Throw-IzBackupError 'BACKUP_KEY_PROTECTION_FAILED' }
        $header = [ordered]@{
            format = 'IZCNABK2'
            version = 2
            created_at = [DateTime]::UtcNow.ToString('o')
            encryption = $script:BackupEncryption
            protected_key = [Convert]::ToBase64String($protectedKey)
            iv = [Convert]::ToBase64String($iv)
            plaintext_sha256 = [string]$Archive.sha256
            plaintext_bytes = [int64]$Archive.length
        }
        $headerBytes = [Text.UTF8Encoding]::new($false).GetBytes(($header | ConvertTo-Json -Compress))
        if ($headerBytes.Length -gt $script:MaxHeaderBytes) { Throw-IzBackupError 'BACKUP_HEADER_SIZE_LIMIT' }
        Assert-IzFreeSpace -Path ([IO.Path]::GetDirectoryName($OutputPath)) -RequiredBytes ([int64]($Archive.length + $headerBytes.Length + 1048576))
        $output = [IO.File]::Open($OutputPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try {
            $output.Write($script:BackupMagic, 0, $script:BackupMagic.Length)
            Write-IzUInt32BigEndian -Stream $output -Value ([uint32]$headerBytes.Length)
            $output.Write($headerBytes, 0, $headerBytes.Length)
            $aes = New-Object Security.Cryptography.AesManaged
            $aes.KeySize = 256
            $aes.BlockSize = 128
            $aes.Mode = [Security.Cryptography.CipherMode]::CBC
            $aes.Padding = [Security.Cryptography.PaddingMode]::PKCS7
            $aes.Key = $encKey
            $aes.IV = $iv
            $encryptor = $aes.CreateEncryptor()
            $crypto = New-Object Security.Cryptography.CryptoStream($output, $encryptor, [Security.Cryptography.CryptoStreamMode]::Write, $true)
            $input = [IO.File]::OpenRead([string]$Archive.path)
            try { $input.CopyTo($crypto, $script:BufferBytes) }
            finally {
                $input.Dispose()
                $crypto.FlushFinalBlock()
                $crypto.Dispose()
                $encryptor.Dispose()
                $aes.Dispose()
            }
            $output.Flush()
        } finally { $output.Dispose() }
        $hmac = New-Object Security.Cryptography.HMACSHA256(,$macKey)
        $input = [IO.File]::OpenRead($OutputPath)
        try { $tag = $hmac.ComputeHash($input) }
        finally { $input.Dispose(); $hmac.Dispose() }
        $append = [IO.File]::Open($OutputPath, [IO.FileMode]::Append, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $append.Write($tag, 0, $tag.Length); $append.Flush() } finally { $append.Dispose() }
    } finally {
        [Array]::Clear($rawKey, 0, $rawKey.Length)
        [Array]::Clear($encKey, 0, $encKey.Length)
        [Array]::Clear($macKey, 0, $macKey.Length)
        [Array]::Clear($iv, 0, $iv.Length)
    }
}

function Read-IzAuthenticatedBackup {
    param([Parameter(Mandatory = $true)][string]$BackupPath)
    $resolved = Get-IzFullPath $BackupPath
    if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) { Throw-IzBackupError 'BACKUP_FILE_MISSING' }
    $item = Get-Item -Force -LiteralPath $resolved
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { Throw-IzBackupError 'BACKUP_FILE_REPARSE_POINT' }
    if ($item.Length -lt 8) { Throw-IzBackupError 'BACKUP_TRUNCATED' }
    $stream = [IO.File]::Open($resolved, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $rawKey = $null
    $encKey = $null
    $macKey = $null
    try {
        $magic = Read-IzExactBytes -Stream $stream -Count 8 -Reason 'BACKUP_TRUNCATED'
        $magicText = [Text.Encoding]::ASCII.GetString($magic)
        if ($magicText -eq 'IZCNABK1') { Throw-IzBackupError 'LEGACY_DATABASE_ONLY_BACKUP' }
        if ($magicText -ne 'IZCNABK2') { Throw-IzBackupError 'BACKUP_MAGIC_INVALID' }
        if ($item.Length -lt 8 + 4 + 2 + 16 + 32) { Throw-IzBackupError 'BACKUP_TRUNCATED' }
        $headerLength = [int64](Read-IzUInt32BigEndian -Stream $stream)
        if ($headerLength -lt 2 -or $headerLength -gt $script:MaxHeaderBytes) { Throw-IzBackupError 'BACKUP_HEADER_LENGTH_INVALID' }
        $headerBytes = Read-IzExactBytes -Stream $stream -Count ([int]$headerLength) -Reason 'BACKUP_HEADER_TRUNCATED'
        try { $header = [Text.UTF8Encoding]::new($false, $true).GetString($headerBytes) | ConvertFrom-Json }
        catch { Throw-IzBackupError 'BACKUP_HEADER_INVALID' }
        $expectedProperties = @('created_at', 'encryption', 'format', 'iv', 'plaintext_bytes', 'plaintext_sha256', 'protected_key', 'version')
        $actualProperties = @($header.PSObject.Properties.Name | Sort-Object)
        if (($actualProperties -join "`n") -ne (($expectedProperties | Sort-Object) -join "`n")) { Throw-IzBackupError 'BACKUP_HEADER_INVALID' }
        if ($header.format -ne 'IZCNABK2' -or [int]$header.version -ne 2 -or $header.encryption -ne $script:BackupEncryption) {
            Throw-IzBackupError 'BACKUP_FORMAT_UNSUPPORTED'
        }
        $plainLength = [int64]$header.plaintext_bytes
        if ($plainLength -le 0 -or $plainLength -gt $script:MaxArchiveBytes) { Throw-IzBackupError 'BACKUP_PLAINTEXT_SIZE_INVALID' }
        if ([string]$header.plaintext_sha256 -notmatch '^[0-9a-f]{64}$') { Throw-IzBackupError 'BACKUP_HEADER_INVALID' }
        try {
            $protectedKey = [Convert]::FromBase64String([string]$header.protected_key)
            $iv = [Convert]::FromBase64String([string]$header.iv)
        } catch { Throw-IzBackupError 'BACKUP_HEADER_INVALID' }
        if ($protectedKey.Length -lt 16 -or $protectedKey.Length -gt 4096 -or $iv.Length -ne 16) { Throw-IzBackupError 'BACKUP_HEADER_INVALID' }
        $payloadOffset = [int64](8 + 4 + $headerLength)
        $payloadLength = [int64]($stream.Length - $payloadOffset - 32)
        if ($payloadLength -le 0 -or ($payloadLength % 16) -ne 0 -or $payloadLength -gt $script:MaxArchiveBytes + 16) {
            Throw-IzBackupError 'BACKUP_PAYLOAD_LENGTH_INVALID'
        }
        try { $rawKey = [Security.Cryptography.ProtectedData]::Unprotect($protectedKey, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser) }
        catch { Throw-IzBackupError 'BACKUP_KEY_UNAVAILABLE' }
        if ($rawKey.Length -ne 64) { Throw-IzBackupError 'BACKUP_KEY_INVALID' }
        $encKey = New-Object byte[] 32
        $macKey = New-Object byte[] 32
        [Array]::Copy($rawKey, 0, $encKey, 0, 32)
        [Array]::Copy($rawKey, 32, $macKey, 0, 32)
        $stream.Position = 0
        $authenticatedLength = [int64]($stream.Length - 32)
        $hmac = [Security.Cryptography.HMACSHA256]::new([byte[]]$macKey)
        $buffer = New-Object byte[] $script:BufferBytes
        $remaining = $authenticatedLength
        try {
            while ($remaining -gt 0) {
                $requested = [int][Math]::Min([int64]$buffer.Length, $remaining)
                $read = $stream.Read($buffer, 0, $requested)
                if ($read -le 0) { Throw-IzBackupError 'BACKUP_TRUNCATED' }
                [void]$hmac.TransformBlock($buffer, 0, $read, $buffer, 0)
                $remaining -= $read
            }
            [void]$hmac.TransformFinalBlock((New-Object byte[] 0), 0, 0)
            $expectedTag = $hmac.Hash
        } finally { $hmac.Dispose(); $buffer = $null }
        $actualTag = Read-IzExactBytes -Stream $stream -Count 32 -Reason 'BACKUP_TAG_TRUNCATED'
        if (-not (Test-IzFixedTimeEquals $expectedTag $actualTag)) { Throw-IzBackupError 'BACKUP_AUTHENTICATION_FAILED' }
        return [pscustomobject]@{
            path = $resolved
            header = $header
            payload_offset = $payloadOffset
            payload_length = $payloadLength
            encryption_key = $encKey.Clone()
            iv = $iv.Clone()
        }
    } finally {
        $stream.Dispose()
        if ($rawKey) { [Array]::Clear($rawKey, 0, $rawKey.Length) }
        if ($encKey) { [Array]::Clear($encKey, 0, $encKey.Length) }
        if ($macKey) { [Array]::Clear($macKey, 0, $macKey.Length) }
    }
}

function Expand-IzEncryptedPayloadToZip {
    param([object]$Authenticated, [string]$ZipPath)
    Assert-IzFreeSpace -Path ([IO.Path]::GetDirectoryName($ZipPath)) -RequiredBytes ([int64]$Authenticated.header.plaintext_bytes + 67108864)
    $input = [IO.File]::Open($Authenticated.path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $output = $null
    $aes = $null
    $decryptor = $null
    $crypto = $null
    $key = [byte[]]$Authenticated.encryption_key.Clone()
    $iv = [byte[]]$Authenticated.iv.Clone()
    try {
        [void]$input.Seek([int64]$Authenticated.payload_offset, [IO.SeekOrigin]::Begin)
        $output = [IO.File]::Open($ZipPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $aes = New-Object Security.Cryptography.AesManaged
        $aes.KeySize = 256
        $aes.BlockSize = 128
        $aes.Mode = [Security.Cryptography.CipherMode]::CBC
        $aes.Padding = [Security.Cryptography.PaddingMode]::PKCS7
        $aes.Key = $key
        $aes.IV = $iv
        $decryptor = $aes.CreateDecryptor()
        $crypto = New-Object Security.Cryptography.CryptoStream($output, $decryptor, [Security.Cryptography.CryptoStreamMode]::Write, $true)
        $buffer = New-Object byte[] $script:BufferBytes
        $remaining = [int64]$Authenticated.payload_length
        while ($remaining -gt 0) {
            $requested = [int][Math]::Min([int64]$buffer.Length, $remaining)
            $read = $input.Read($buffer, 0, $requested)
            if ($read -le 0) { Throw-IzBackupError 'BACKUP_PAYLOAD_TRUNCATED' }
            $crypto.Write($buffer, 0, $read)
            $remaining -= $read
        }
        try { $crypto.FlushFinalBlock() } catch { Throw-IzBackupError 'BACKUP_DECRYPTION_FAILED' }
        $crypto.Dispose(); $crypto = $null
        $output.Flush(); $output.Dispose(); $output = $null
    } finally {
        if ($crypto) { $crypto.Dispose() }
        if ($output) { $output.Dispose() }
        if ($decryptor) { $decryptor.Dispose() }
        if ($aes) { $aes.Dispose() }
        $input.Dispose()
        [Array]::Clear($key, 0, $key.Length)
        [Array]::Clear($iv, 0, $iv.Length)
    }
    $zipItem = Get-Item -LiteralPath $ZipPath
    if ($zipItem.Length -ne [int64]$Authenticated.header.plaintext_bytes) { Throw-IzBackupError 'BACKUP_PLAINTEXT_LENGTH_MISMATCH' }
    if ((Get-IzFileSha256 $ZipPath) -ne [string]$Authenticated.header.plaintext_sha256) { Throw-IzBackupError 'BACKUP_PLAINTEXT_HASH_MISMATCH' }
}

function Test-IzZipEntryType {
    param([IO.Compression.ZipArchiveEntry]$Entry)
    $attributes = [uint32]([int64]$Entry.ExternalAttributes -band 4294967295L)
    $dosAttributes = $attributes -band 0xFFFF
    if (($dosAttributes -band [uint32][IO.FileAttributes]::ReparsePoint) -ne 0) { Throw-IzBackupError 'BACKUP_ARCHIVE_REPARSE_ENTRY' }
    $unixType = ($attributes -shr 16) -band 0xF000
    if ($unixType -notin @(0, 0x4000, 0x8000)) { Throw-IzBackupError 'BACKUP_ARCHIVE_SPECIAL_ENTRY' }
}

function Expand-IzValidatedZip {
    param([string]$ZipPath, [string]$ExtractionRoot)
    $archive = [IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        if ($archive.Entries.Count -le 0 -or $archive.Entries.Count -gt $script:MaxEntryCount) { Throw-IzBackupError 'BACKUP_ARCHIVE_ENTRY_LIMIT' }
        $seen = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        $fileKeys = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        $directoryKeys = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        $plans = New-Object Collections.Generic.List[object]
        $expandedBytes = [int64]0
        $manifestCount = 0
        $dataEntryCount = 0
        foreach ($entry in $archive.Entries) {
            Test-IzZipEntryType $entry
            $validated = ConvertTo-IzValidatedArchiveName ([string]$entry.FullName)
            if (-not $seen.Add($validated.key)) { Throw-IzBackupError 'BACKUP_ARCHIVE_DUPLICATE_ENTRY' }
            $entryIsDirectory = $validated.is_directory
            if ($entryIsDirectory -and ($entry.Length -ne 0 -or $entry.CompressedLength -ne 0)) { Throw-IzBackupError 'BACKUP_ARCHIVE_DIRECTORY_INVALID' }
            if (-not $entryIsDirectory -and $entry.Length -gt $script:MaxEntryBytes) { Throw-IzBackupError 'BACKUP_ARCHIVE_ENTRY_SIZE_LIMIT' }
            if (-not $entryIsDirectory) {
                if ($expandedBytes -gt $script:MaxExpandedBytes - [int64]$entry.Length) { Throw-IzBackupError 'BACKUP_ARCHIVE_EXPANDED_LIMIT' }
                $expandedBytes += [int64]$entry.Length
                [void]$fileKeys.Add($validated.key)
            } else { [void]$directoryKeys.Add($validated.key) }
            if ($validated.path -eq $script:ManifestName) { $manifestCount++ }
            if ($validated.path -eq $script:DataDirectoryName -or $validated.path.StartsWith($script:DataDirectoryName + '/', [StringComparison]::Ordinal)) { $dataEntryCount++ }
            $plans.Add([pscustomobject]@{ entry = $entry; path = $validated.path; key = $validated.key; is_directory = $entryIsDirectory; length = [int64]$entry.Length })
        }
        if ($manifestCount -ne 1) { Throw-IzBackupError 'BACKUP_MANIFEST_MISSING' }
        if ($dataEntryCount -le 0) { Throw-IzBackupError 'BACKUP_DATA_ROOT_MISSING' }
        foreach ($fileKey in $fileKeys) {
            $segments = @($fileKey.Split('/'))
            if ($segments.Count -gt 1) {
                for ($index = 1; $index -lt $segments.Count; $index++) {
                    $parent = ($segments[0..($index - 1)] -join '/')
                    if ($fileKeys.Contains($parent)) { Throw-IzBackupError 'BACKUP_ARCHIVE_PATH_COLLISION' }
                }
            }
            if ($directoryKeys.Contains($fileKey)) { Throw-IzBackupError 'BACKUP_ARCHIVE_PATH_COLLISION' }
        }
        Assert-IzFreeSpace -Path ([IO.Path]::GetDirectoryName($ExtractionRoot)) -RequiredBytes ($expandedBytes + 67108864)
        [IO.Directory]::CreateDirectory($ExtractionRoot) | Out-Null
        foreach ($plan in $plans) {
            $destination = Join-Path $ExtractionRoot ($plan.path.Replace('/', '\'))
            Assert-IzBackupContainedPath -Path $destination -Parent $ExtractionRoot -AllowMissingLeaf | Out-Null
            if ($plan.is_directory) {
                [IO.Directory]::CreateDirectory($destination) | Out-Null
                continue
            }
            $parent = [IO.Path]::GetDirectoryName($destination)
            [IO.Directory]::CreateDirectory($parent) | Out-Null
            $source = $null
            $target = $null
            try {
                $source = $plan.entry.Open()
                $target = [IO.File]::Open($destination, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
                $source.CopyTo($target, $script:BufferBytes)
            } finally {
                if ($target) { $target.Dispose() }
                if ($source) { $source.Dispose() }
            }
            if ((Get-Item -LiteralPath $destination).Length -ne $plan.length) { Throw-IzBackupError 'BACKUP_ARCHIVE_ENTRY_TRUNCATED' }
        }
    } finally { $archive.Dispose() }
}

function Read-IzInnerManifest {
    param([string]$Path)
    $item = Get-Item -LiteralPath $Path
    if ($item.Length -le 0 -or $item.Length -gt $script:MaxManifestBytes) { Throw-IzBackupError 'BACKUP_MANIFEST_INVALID' }
    try { $manifest = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json }
    catch { Throw-IzBackupError 'BACKUP_MANIFEST_INVALID' }
    if ($manifest.format -ne 'iz-cna-local-data-v2' -or $manifest.source -ne 'local-app-data' -or $manifest.restore_scope -ne 'same-windows-user') {
        Throw-IzBackupError 'BACKUP_MANIFEST_INVALID'
    }
    $isCurrent = $manifest.PSObject.Properties.Name -contains 'version'
    if ($isCurrent) {
        if ([int]$manifest.version -ne 2) { Throw-IzBackupError 'BACKUP_MANIFEST_INVALID' }
        foreach ($required in @('profile_snapshot_identity', 'source_identity_hash', 'environment_sha256', 'database_relative_path', 'database_sha256', 'schema_version', 'file_count', 'directory_count', 'total_bytes', 'inventory_sha256', 'files', 'directories')) {
            if ($manifest.PSObject.Properties.Name -notcontains $required) { Throw-IzBackupError 'BACKUP_MANIFEST_INVALID' }
        }
    }
    return [pscustomobject]@{ value = $manifest; is_current = $isCurrent }
}

function Test-IzExtractedInventory {
    param([string]$DataRoot, [object]$Manifest)
    $files = @($Manifest.files)
    $directories = @($Manifest.directories)
    if ($files.Count -ne [int]$Manifest.file_count -or $directories.Count -ne [int]$Manifest.directory_count) { Throw-IzBackupError 'BACKUP_INVENTORY_INVALID' }
    $seen = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $actualTotal = [int64]0
    foreach ($file in $files) {
        $validated = ConvertTo-IzValidatedArchiveName "$($script:DataDirectoryName)/$([string]$file.path)"
        if (-not $seen.Add($validated.key)) { Throw-IzBackupError 'BACKUP_INVENTORY_INVALID' }
        if ([string]$file.sha256 -notmatch '^[0-9a-f]{64}$' -or [int64]$file.length -lt 0) { Throw-IzBackupError 'BACKUP_INVENTORY_INVALID' }
        $path = Join-Path $DataRoot ([string]$file.path).Replace('/', '\')
        Assert-IzBackupContainedPath -Path $path -Parent $DataRoot | Out-Null
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { Throw-IzBackupError 'BACKUP_CONTENT_INCOMPLETE' }
        $item = Get-Item -Force -LiteralPath $path
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or $item.Length -ne [int64]$file.length -or (Get-IzFileSha256 $path) -ne [string]$file.sha256) {
            Throw-IzBackupError 'BACKUP_CONTENT_INTEGRITY_FAILED'
        }
        $actualTotal += [int64]$item.Length
    }
    foreach ($relative in $directories) {
        $validated = ConvertTo-IzValidatedArchiveName "$($script:DataDirectoryName)/$([string]$relative)/"
        if (-not $seen.Add($validated.key)) { Throw-IzBackupError 'BACKUP_INVENTORY_INVALID' }
        $path = Join-Path $DataRoot ([string]$relative).Replace('/', '\')
        Assert-IzBackupContainedPath -Path $path -Parent $DataRoot | Out-Null
        if (-not (Test-Path -LiteralPath $path -PathType Container)) { Throw-IzBackupError 'BACKUP_CONTENT_INCOMPLETE' }
    }
    if ($actualTotal -ne [int64]$Manifest.total_bytes) { Throw-IzBackupError 'BACKUP_CONTENT_INTEGRITY_FAILED' }
    if ((Get-IzInventoryDigest -Files $files -Directories $directories) -ne [string]$Manifest.inventory_sha256) { Throw-IzBackupError 'BACKUP_INVENTORY_INVALID' }
    $actualFiles = @(Get-ChildItem -LiteralPath $DataRoot -Force -Recurse -File)
    if ($actualFiles.Count -ne $files.Count) { Throw-IzBackupError 'BACKUP_CONTENT_UNTRACKED' }
}

function Remove-IzBackupScratch {
    param([object]$Context, [string]$Path, [switch]$RecoveryRequired)
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) { return }
    try {
        Assert-IzBackupContainedPath -Path $Path -Parent $Context.transaction_root | Out-Null
        Remove-Item -LiteralPath $Path -Recurse -Force
    } catch {
        if ($RecoveryRequired) { Throw-IzBackupError 'BACKUP_RECOVERY_ARTIFACT_CLEANUP_FAILED' 31 }
        Throw-IzBackupError 'BACKUP_PLAINTEXT_CLEANUP_FAILED' 31
    }
}

function Test-IzPortableIdentity {
    param([object]$Actual, [object]$Expected, [string]$Reason)
    foreach ($property in @('profile_snapshot_identity', 'source_identity_hash', 'environment_sha256', 'database_relative_path', 'database_sha256', 'schema_version')) {
        if ([string]$Actual.$property -cne [string]$Expected.$property) { Throw-IzBackupError $Reason }
    }
    $actualCounts = $Actual.safe_counts | ConvertTo-Json -Compress
    $expectedCounts = $Expected.safe_counts | ConvertTo-Json -Compress
    if ($actualCounts -cne $expectedCounts -or [int]$Actual.encrypted_payloads_checked -ne [int]$Expected.encrypted_payloads_checked -or [int]$Actual.encrypted_payloads_valid -ne [int]$Expected.encrypted_payloads_valid) {
        Throw-IzBackupError $Reason
    }
}

function Get-IzInternalPublicationPaths {
    param([object]$Context, [string]$FinalPath)
    $final = Assert-IzBackupContainedPath -Path $FinalPath -Parent $Context.transaction_root -AllowMissingLeaf
    if (-not (Test-IzSamePath $final $Context.snapshot_path)) { Throw-IzBackupError 'BACKUP_INTERNAL_DESTINATION_INVALID' }
    $partial = Join-Path ([IO.Path]::GetDirectoryName($final)) ('p-' + (([Guid]$Context.transaction_id).ToString('N').Substring(0, 12)) + '.tmp')
    Assert-IzBackupContainedPath -Path $partial -Parent $Context.transaction_root -AllowMissingLeaf | Out-Null
    if (Test-Path -LiteralPath $final) { Throw-IzBackupError 'BACKUP_DESTINATION_EXISTS' }
    if (Test-Path -LiteralPath $partial) { Throw-IzBackupError 'BACKUP_PARTIAL_EXISTS' }
    return [pscustomobject]@{ final_path = $final; partial_path = $partial; is_external = $false }
}

function Get-IzBackupPublicationPaths {
    param([object]$Context, [string]$BackupPath)
    if (Test-IzSamePath $BackupPath $Context.snapshot_path) {
        return Get-IzInternalPublicationPaths -Context $Context -FinalPath $BackupPath
    }
    $external = Get-IzExternalBackupPublicationPaths -Context $Context -BackupPath $BackupPath -TransactionId ([Guid]$Context.transaction_id)
    return [pscustomobject]@{
        final_path = [string]$external.final_path
        partial_path = [string]$external.partial_path
        is_external = $true
    }
}

function Assert-IzReadableBackupPath {
    param([object]$Context, [string]$BackupPath)
    $resolved = Get-IzCanonicalPath -Path $BackupPath
    if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) { Throw-IzBackupError 'BACKUP_FILE_MISSING' }
    $transactionRoot = Get-IzFullPath $Context.transaction_root
    $ownedTransactionInput = $resolved.StartsWith($transactionRoot + '\', [StringComparison]::OrdinalIgnoreCase)
    foreach ($protectedRoot in @($Context.install_root, $Context.data_root, $Context.maintenance_root)) {
        if ([string]::IsNullOrWhiteSpace([string]$protectedRoot)) { continue }
        $root = Get-IzFullPath $protectedRoot
        if (-not $ownedTransactionInput -and -not (Test-IzSamePath $resolved $Context.snapshot_path) -and ($resolved.Equals($root, [StringComparison]::OrdinalIgnoreCase) -or $resolved.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase))) {
            Throw-IzBackupError 'BACKUP_INPUT_OVERLAPS_PRODUCT_DATA'
        }
    }
    return $resolved
}

function Test-IzFullBackup {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][object]$Context,
        [Parameter(Mandatory = $true)][string]$BackupPath,
        [Parameter(Mandatory = $true)][ValidateSet('Installed', 'Package', 'Candidate', 'SourceTest')][string]$RuntimeRole,
        [AllowNull()][object]$Manifest,
        [string]$ExpectedProfileSnapshotIdentity = ''
    )
    Assert-IzMaintenanceContext -Context $Context | Out-Null
    $resolvedBackup = Assert-IzReadableBackupPath -Context $Context -BackupPath $BackupPath
    $workRoot = Join-Path $Context.verification_root 'r'
    Assert-IzBackupContainedPath -Path $workRoot -Parent $Context.transaction_root -AllowMissingLeaf | Out-Null
    $succeeded = $false
    $authenticated = $null
    try {
        [IO.Directory]::CreateDirectory($workRoot) | Out-Null
        Protect-IzMaintenancePath -Path $workRoot | Out-Null
        $zipPath = Join-Path $workRoot 'payload.zip'
        $extractRoot = $workRoot
        $authenticated = Read-IzAuthenticatedBackup -BackupPath $resolvedBackup
        Expand-IzEncryptedPayloadToZip -Authenticated $authenticated -ZipPath $zipPath
        Expand-IzValidatedZip -ZipPath $zipPath -ExtractionRoot $extractRoot
        Remove-Item -LiteralPath $zipPath -Force
        $manifestPath = Join-Path $extractRoot $script:ManifestName
        $manifestInfo = Read-IzInnerManifest -Path $manifestPath
        $profileRoot = Join-Path $extractRoot $script:DataDirectoryName
        Assert-IzBackupContainedPath -Path $profileRoot -Parent $workRoot | Out-Null
        if ($manifestInfo.is_current) { Test-IzExtractedInventory -DataRoot $profileRoot -Manifest $manifestInfo.value }
        $environmentFile = Join-Path $profileRoot '.env'
        if (-not (Test-Path -LiteralPath $environmentFile -PathType Leaf)) { Throw-IzBackupError 'BACKUP_ENVIRONMENT_MISSING' }
        $expectedDatabasePath = ''
        if ($manifestInfo.is_current) {
            $expectedDatabasePath = Join-Path $profileRoot ([string]$manifestInfo.value.database_relative_path).Replace('/', '\')
            Assert-IzBackupContainedPath -Path $expectedDatabasePath -Parent $profileRoot | Out-Null
        }
        $request = New-IzVerifyDataRequest -Context $Context -EnvironmentFile $environmentFile -ExpectedDatabasePath $expectedDatabasePath
        $verified = Invoke-IzRuntimeMaintenance -Context $Context -Operation VerifyData -Request $request -RuntimeRole $RuntimeRole -Manifest $Manifest -Stem 'backup-rehearsal'
        if ($verified.sqlite_integrity -ne 'ok' -or [int]$verified.foreign_key_violations -ne 0 -or [int]$verified.encrypted_payloads_valid -ne [int]$verified.encrypted_payloads_checked) {
            Throw-IzBackupError 'BACKUP_SEMANTIC_VERIFICATION_FAILED'
        }
        if ($manifestInfo.is_current) {
            foreach ($property in @('profile_snapshot_identity', 'source_identity_hash', 'environment_sha256', 'database_relative_path', 'database_sha256', 'schema_version')) {
                if ([string]$verified.$property -cne [string]$manifestInfo.value.$property) { Throw-IzBackupError 'BACKUP_MANIFEST_IDENTITY_MISMATCH' }
            }
        }
        if ($ExpectedProfileSnapshotIdentity -and [string]$verified.profile_snapshot_identity -cne $ExpectedProfileSnapshotIdentity) {
            Throw-IzBackupError 'BACKUP_EXPECTED_IDENTITY_MISMATCH'
        }
        $succeeded = $true
        return [pscustomobject]@{
            schema = 'iz-cna-full-backup-verification-v1'
            status = 'success'
            reason = 'ok'
            format = 'IZCNABK2'
            path = $resolvedBackup
            length = [int64](Get-Item -LiteralPath $resolvedBackup).Length
            sha256 = Get-IzFileSha256 $resolvedBackup
            data_identity = [string]$verified.data_identity
            source_identity_hash = [string]$verified.source_identity_hash
            profile_snapshot_identity = [string]$verified.profile_snapshot_identity
            environment_sha256 = [string]$verified.environment_sha256
            database_relative_path = [string]$verified.database_relative_path
            database_sha256 = [string]$verified.database_sha256
            sqlite_integrity = [string]$verified.sqlite_integrity
            foreign_key_violations = [int]$verified.foreign_key_violations
            schema_version = [int]$verified.schema_version
            safe_counts = $verified.safe_counts
            encrypted_payloads_checked = [int]$verified.encrypted_payloads_checked
            encrypted_payloads_valid = [int]$verified.encrypted_payloads_valid
            verified = $true
            verification_work_root = $workRoot
            verification_data_root = $profileRoot
        }
    } catch {
        $reason = Get-IzSafeErrorReason $_ 'BACKUP_VERIFICATION_FAILED'
        $code = if ($_.Exception.Data.Contains('iz_exit_code')) { [int]$_.Exception.Data['iz_exit_code'] } else { 20 }
        throw (New-IzBackupError -Reason $reason -ExitCode $code)
    } finally {
        if ($authenticated -and $authenticated.encryption_key) { [Array]::Clear($authenticated.encryption_key, 0, $authenticated.encryption_key.Length) }
        if (-not $succeeded -and (Test-Path -LiteralPath $workRoot)) { Remove-IzBackupScratch -Context $Context -Path $workRoot }
    }
}

function New-IzFullBackup {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][object]$Context,
        [AllowNull()][object]$DataIdentity,
        [Parameter(Mandatory = $true)][ValidateSet('Installed', 'Package', 'Candidate', 'SourceTest')][string]$RuntimeRole,
        [AllowNull()][object]$Manifest,
        [Parameter(Mandatory = $true)][string]$BackupPath
    )
    Assert-IzMaintenanceContext -Context $Context | Out-Null
    $expectedDataIdentity = if ($null -eq $DataIdentity) { '' } else { Get-IzDataIdentityValue $DataIdentity }
    $publication = Get-IzBackupPublicationPaths -Context $Context -BackupPath $BackupPath
    $environmentFile = Join-Path $Context.data_root '.env'
    if (-not (Test-Path -LiteralPath $environmentFile -PathType Leaf)) { Throw-IzBackupError 'BACKUP_ENVIRONMENT_MISSING' }
    $plainArchive = Join-Path (Join-Path $Context.transaction_root 'snapshot') 'payload.zip'
    $snapshotDatabase = Join-Path (Join-Path $Context.transaction_root 'snapshot') 'selected-database.sqlite3'
    Assert-IzBackupContainedPath -Path $plainArchive -Parent $Context.transaction_root -AllowMissingLeaf | Out-Null
    Assert-IzBackupContainedPath -Path $snapshotDatabase -Parent $Context.transaction_root -AllowMissingLeaf | Out-Null
    $verification = $null
    $published = $false
    try {
        Write-Progress -Activity 'IZ Clinical Notes Analyzer backup' -Status 'Validating local data' -PercentComplete 5
        $liveRequest = New-IzVerifyDataRequest -Context $Context -EnvironmentFile $environmentFile -ExpectedDatabasePath ''
        $live = Invoke-IzRuntimeMaintenance -Context $Context -Operation VerifyData -Request $liveRequest -RuntimeRole $RuntimeRole -Manifest $Manifest -Stem 'backup-live'
        if ($expectedDataIdentity -and [string]$live.data_identity -cne $expectedDataIdentity) { Throw-IzBackupError 'BACKUP_DATA_IDENTITY_MISMATCH' }
        if (-not $expectedDataIdentity) { $expectedDataIdentity = [string]$live.data_identity }
        $selectedDatabase = Join-Path $Context.data_root ([string]$live.database_relative_path).Replace('/', '\')
        Assert-IzBackupContainedPath -Path $selectedDatabase -Parent $Context.data_root | Out-Null
        Write-Progress -Activity 'IZ Clinical Notes Analyzer backup' -Status 'Creating consistent database snapshot' -PercentComplete 20
        $snapshotRequest = New-IzDatabaseSnapshotRequest -Context $Context -EnvironmentFile $environmentFile -SourceDatabasePath $selectedDatabase
        $snapshot = Invoke-IzRuntimeMaintenance -Context $Context -Operation SnapshotDatabase -Request $snapshotRequest -RuntimeRole $RuntimeRole -Manifest $Manifest -Stem 'backup-snapshot'
        Test-IzPortableIdentity -Actual $snapshot -Expected $live -Reason 'BACKUP_SOURCE_CHANGED'
        Write-Progress -Activity 'IZ Clinical Notes Analyzer backup' -Status 'Writing encrypted snapshot' -PercentComplete 45
        $archive = New-IzPlainArchive -Context $Context -SnapshotResult $snapshot -SnapshotDatabasePath $snapshotDatabase -ArchivePath $plainArchive
        Protect-IzMaintenancePath -Path $plainArchive | Out-Null
        Protect-IzPlainArchive -Archive $archive -OutputPath $publication.partial_path
        if (-not $publication.is_external) { Protect-IzMaintenancePath -Path $publication.partial_path | Out-Null }
        Remove-Item -LiteralPath $plainArchive -Force
        Remove-Item -LiteralPath $snapshotDatabase -Force
        Write-Progress -Activity 'IZ Clinical Notes Analyzer backup' -Status 'Rehearsing same-user recovery' -PercentComplete 75
        $verification = Test-IzFullBackup -Context $Context -BackupPath $publication.partial_path -RuntimeRole $RuntimeRole -Manifest $Manifest -ExpectedProfileSnapshotIdentity ([string]$snapshot.profile_snapshot_identity)
        Test-IzPortableIdentity -Actual $verification -Expected $snapshot -Reason 'BACKUP_REHEARSAL_IDENTITY_MISMATCH'
        [IO.File]::Move([string]$publication.partial_path, [string]$publication.final_path)
        $published = $true
        $result = [pscustomobject]@{
            schema = 'iz-cna-full-backup-v1'
            status = 'success'
            reason = 'ok'
            format = 'IZCNABK2'
            Path = [string]$publication.final_path
            length = [int64](Get-Item -LiteralPath $publication.final_path).Length
            sha256 = Get-IzFileSha256 $publication.final_path
            data_identity = $expectedDataIdentity
            source_identity_hash = [string]$snapshot.source_identity_hash
            profile_snapshot_identity = [string]$snapshot.profile_snapshot_identity
            environment_sha256 = [string]$snapshot.environment_sha256
            database_relative_path = [string]$snapshot.database_relative_path
            database_sha256 = [string]$snapshot.database_sha256
            sqlite_integrity = [string]$snapshot.sqlite_integrity
            foreign_key_violations = [int]$snapshot.foreign_key_violations
            schema_version = [int]$snapshot.schema_version
            safe_counts = $snapshot.safe_counts
            encrypted_payloads_checked = [int]$snapshot.encrypted_payloads_checked
            encrypted_payloads_valid = [int]$snapshot.encrypted_payloads_valid
            verified = $true
            Encryption = 'DPAPI current-user + AES-256-CBC + HMAC-SHA-256'
            RestoreScope = 'same Windows user'
        }
        Write-Progress -Activity 'IZ Clinical Notes Analyzer backup' -Status 'Verified' -PercentComplete 100
        return $result
    } catch {
        $reason = Get-IzSafeErrorReason $_ 'BACKUP_CREATION_FAILED'
        $code = if ($_.Exception.Data.Contains('iz_exit_code')) { [int]$_.Exception.Data['iz_exit_code'] } else { 20 }
        throw (New-IzBackupError -Reason $reason -ExitCode $code)
    } finally {
        Write-Progress -Activity 'IZ Clinical Notes Analyzer backup' -Completed
        if ($verification -and $verification.verification_work_root -and (Test-Path -LiteralPath $verification.verification_work_root)) {
            Remove-IzBackupScratch -Context $Context -Path $verification.verification_work_root
        }
        foreach ($scratch in @($plainArchive, $snapshotDatabase)) {
            if (Test-Path -LiteralPath $scratch) { Remove-Item -LiteralPath $scratch -Force }
        }
        if (-not $published -and (Test-Path -LiteralPath $publication.partial_path)) { Remove-Item -LiteralPath $publication.partial_path -Force }
    }
}

function Invoke-IzVerifyProfileRoot {
    param(
        [object]$Context,
        [string]$ProfileRoot,
        [string]$ExpectedDatabaseRelativePath,
        [ValidateSet('Installed', 'Package', 'Candidate', 'SourceTest')][string]$RuntimeRole,
        [AllowNull()][object]$Manifest,
        [string]$Stem
    )
    $environmentFile = Join-Path $ProfileRoot '.env'
    if (-not (Test-Path -LiteralPath $environmentFile -PathType Leaf)) { Throw-IzBackupError 'BACKUP_ENVIRONMENT_MISSING' }
    $expectedDatabase = ''
    if ($ExpectedDatabaseRelativePath) {
        $expectedDatabase = Join-Path $ProfileRoot $ExpectedDatabaseRelativePath.Replace('/', '\')
    }
    $request = New-IzVerifyDataRequest -Context $Context -EnvironmentFile $environmentFile -ExpectedDatabasePath $expectedDatabase
    return Invoke-IzRuntimeMaintenance -Context $Context -Operation VerifyData -Request $request -RuntimeRole $RuntimeRole -Manifest $Manifest -Stem $Stem
}

function Restore-IzFullBackup {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][object]$Context,
        [Parameter(Mandatory = $true)][string]$BackupPath,
        [Parameter(Mandatory = $true)][ValidateSet('Installed', 'Package', 'Candidate', 'SourceTest')][string]$RuntimeRole,
        [AllowNull()][object]$Manifest,
        [string]$ExpectedProfileSnapshotIdentity = '',
        [Parameter(Mandatory = $true)][switch]$Confirmed
    )
    Assert-IzMaintenanceContext -Context $Context | Out-Null
    if (-not $Confirmed) { Throw-IzBackupError 'RESTORE_CONFIRMATION_REQUIRED' 10 }
    Write-Progress -Activity 'IZ Clinical Notes Analyzer restore' -Status 'Verifying encrypted backup' -PercentComplete 10
    $verification = Test-IzFullBackup -Context $Context -BackupPath $BackupPath -RuntimeRole $RuntimeRole -Manifest $Manifest -ExpectedProfileSnapshotIdentity $ExpectedProfileSnapshotIdentity
    $transactionToken = ([Guid]$Context.transaction_id).ToString('N')
    $liveRoot = Get-IzFullPath $Context.data_root
    $restoreStage = "$liveRoot.restore-$transactionToken"
    $rollbackRoot = "$liveRoot.rollback-$transactionToken"
    $stageCreated = $false
    $liveMoved = $false
    $stageActivated = $false
    $resolved = $false
    try {
        if (Test-Path -LiteralPath $restoreStage) { Throw-IzBackupError 'RESTORE_STAGE_EXISTS' }
        if (Test-Path -LiteralPath $rollbackRoot) { Throw-IzBackupError 'RESTORE_ROLLBACK_EXISTS' }
        Get-IzCanonicalPath -Path $restoreStage -AllowMissingLeaf | Out-Null
        Get-IzCanonicalPath -Path $rollbackRoot -AllowMissingLeaf | Out-Null
        Write-Progress -Activity 'IZ Clinical Notes Analyzer restore' -Status 'Preparing verified replacement' -PercentComplete 35
        Move-Item -LiteralPath $verification.verification_data_root -Destination $restoreStage
        $stageCreated = $true
        $staged = Invoke-IzVerifyProfileRoot -Context $Context -ProfileRoot $restoreStage -ExpectedDatabaseRelativePath ([string]$verification.database_relative_path) -RuntimeRole $RuntimeRole -Manifest $Manifest -Stem 'restore-stage'
        Test-IzPortableIdentity -Actual $staged -Expected $verification -Reason 'RESTORE_STAGE_IDENTITY_MISMATCH'
        Write-Progress -Activity 'IZ Clinical Notes Analyzer restore' -Status 'Activating verified replacement' -PercentComplete 65
        if (Test-Path -LiteralPath $liveRoot -PathType Container) {
            Move-Item -LiteralPath $liveRoot -Destination $rollbackRoot
            $liveMoved = $true
        } elseif (Test-Path -LiteralPath $liveRoot) {
            Throw-IzBackupError 'RESTORE_DATA_ROOT_INVALID'
        }
        try {
            Move-Item -LiteralPath $restoreStage -Destination $liveRoot
            $stageCreated = $false
            $stageActivated = $true
            $activated = Invoke-IzVerifyProfileRoot -Context $Context -ProfileRoot $liveRoot -ExpectedDatabaseRelativePath ([string]$verification.database_relative_path) -RuntimeRole $RuntimeRole -Manifest $Manifest -Stem 'restore-active'
            Test-IzPortableIdentity -Actual $activated -Expected $verification -Reason 'RESTORE_ACTIVE_IDENTITY_MISMATCH'
        } catch {
            $activationError = $_
            try {
                if ($stageActivated -and (Test-Path -LiteralPath $liveRoot)) {
                    Move-Item -LiteralPath $liveRoot -Destination $restoreStage
                    $stageCreated = $true
                    $stageActivated = $false
                }
                if ($liveMoved -and (Test-Path -LiteralPath $rollbackRoot)) {
                    Move-Item -LiteralPath $rollbackRoot -Destination $liveRoot
                    $liveMoved = $false
                }
            } catch { Throw-IzBackupError 'RESTORE_RECOVERY_REQUIRED' 31 }
            $reason = Get-IzSafeErrorReason $activationError 'RESTORE_ACTIVATION_FAILED'
            $code = if ($activationError.Exception.Data.Contains('iz_exit_code')) { [int]$activationError.Exception.Data['iz_exit_code'] } else { 20 }
            throw (New-IzBackupError -Reason $reason -ExitCode $code)
        }
        if ($liveMoved -and (Test-Path -LiteralPath $rollbackRoot)) {
            Remove-Item -LiteralPath $rollbackRoot -Recurse -Force
            $liveMoved = $false
        }
        $resolved = $true
        Write-Progress -Activity 'IZ Clinical Notes Analyzer restore' -Status 'Verified' -PercentComplete 100
        return [pscustomobject]@{
            schema = 'iz-cna-full-backup-restore-v1'
            status = 'success'
            reason = 'ok'
            format = 'IZCNABK2'
            data_identity = [string]$activated.data_identity
            source_identity_hash = [string]$verification.source_identity_hash
            profile_snapshot_identity = [string]$verification.profile_snapshot_identity
            environment_sha256 = [string]$verification.environment_sha256
            database_relative_path = [string]$verification.database_relative_path
            database_sha256 = [string]$verification.database_sha256
            sqlite_integrity = [string]$activated.sqlite_integrity
            foreign_key_violations = [int]$activated.foreign_key_violations
            schema_version = [int]$verification.schema_version
            safe_counts = $activated.safe_counts
            encrypted_payloads_checked = [int]$activated.encrypted_payloads_checked
            encrypted_payloads_valid = [int]$activated.encrypted_payloads_valid
            verified = $true
        }
    } catch {
        $reason = Get-IzSafeErrorReason $_ 'RESTORE_FAILED'
        $code = if ($_.Exception.Data.Contains('iz_exit_code')) { [int]$_.Exception.Data['iz_exit_code'] } else { 20 }
        throw (New-IzBackupError -Reason $reason -ExitCode $code)
    } finally {
        Write-Progress -Activity 'IZ Clinical Notes Analyzer restore' -Completed
        if ($resolved) {
            if ($stageCreated -and (Test-Path -LiteralPath $restoreStage)) { Remove-Item -LiteralPath $restoreStage -Recurse -Force }
            if ($verification.verification_work_root -and (Test-Path -LiteralPath $verification.verification_work_root)) {
                Remove-IzBackupScratch -Context $Context -Path $verification.verification_work_root
            }
        }
    }
}

Export-ModuleMember -Function New-IzFullBackup, Test-IzFullBackup, Restore-IzFullBackup
