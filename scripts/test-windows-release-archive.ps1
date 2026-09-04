[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$EvidenceRoot,
    [Parameter(Mandatory)][string]$PreservedPackage,
    [switch]$BaselineOnly
)

$ErrorActionPreference = 'Stop'
$qaParent = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'IZ-CNA-QA'
$fullEvidenceRoot = [IO.Path]::GetFullPath($EvidenceRoot)
if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'WINDOWS_PS51_REQUIRED' }
if ((Split-Path $fullEvidenceRoot -Parent) -cne $qaParent -or (Split-Path $fullEvidenceRoot -Leaf) -notmatch '^zlp-[a-f0-9]{12}$') { throw 'OWNED_SHORT_ROOT_REQUIRED' }
if (Test-Path -LiteralPath $fullEvidenceRoot) { throw 'FRESH_ROOT_REQUIRED' }
if ((Get-Item -LiteralPath $qaParent).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'REPARSE_PARENT_REFUSED' }
$package = [IO.Path]::GetFullPath($PreservedPackage).TrimEnd('\')
if ($package -notmatch '^[A-Za-z]:\\' -or -not (Test-Path -LiteralPath $package -PathType Container)) { throw 'PRESERVED_LOCAL_PACKAGE_REQUIRED' }
if ($fullEvidenceRoot.StartsWith($package + '\', [StringComparison]::OrdinalIgnoreCase) -or
    $package.StartsWith($fullEvidenceRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or
    $package.Equals($fullEvidenceRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'PACKAGE_EVIDENCE_OVERLAP_REFUSED' }
New-Item -ItemType Directory -Path $fullEvidenceRoot | Out-Null
@{ owner = 'task-10-packaging-long-path-v1'; root = $fullEvidenceRoot; preserved_package = $package } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $fullEvidenceRoot 'owner.json') -Encoding UTF8
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Get-ExtendedPath([string]$Path) { return '\\?\' + $Path }

function Get-StreamHash([IO.Stream]$Stream) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($Stream)).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Get-FileHashValue([string]$Path) {
    $stream = [IO.File]::OpenRead((Get-ExtendedPath $Path))
    try { return Get-StreamHash $stream } finally { $stream.Dispose() }
}

function Get-TreeManifest([string]$Root) {
    $extended = Get-ExtendedPath $Root
    $rows = @([IO.Directory]::EnumerateFileSystemEntries($extended, '*', [IO.SearchOption]::AllDirectories) | ForEach-Object {
        $attributes = [IO.File]::GetAttributes($_)
        if ($attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'REPARSE_FIXTURE_REFUSED' }
        $name = $_.Substring($extended.Length + 1).Replace('\', '/')
        if ($attributes -band [IO.FileAttributes]::Directory) {
            [ordered]@{ name = $name + '/'; bytes = 0; sha256 = $null }
        } else {
            $stream = [IO.File]::OpenRead($_)
            try { [ordered]@{ name = $name; bytes = $stream.Length; sha256 = (Get-StreamHash $stream) } }
            finally { $stream.Dispose() }
        }
    })
    return @($rows | Sort-Object { $_.name } -CaseSensitive)
}

function Get-ZipManifest([string]$Path) {
    $zip = [IO.Compression.ZipFile]::OpenRead((Get-ExtendedPath $Path))
    try {
        $rows = @($zip.Entries | ForEach-Object {
            if ($_.FullName.StartsWith('/') -or $_.FullName.Contains('\') -or ($_.FullName.Split('/') -contains '..')) { throw 'UNSAFE_ARCHIVE_ENTRY' }
            if ($_.FullName.EndsWith('/')) {
                [ordered]@{ name = $_.FullName; bytes = 0; sha256 = $null }
            } else {
                $stream = $_.Open()
                try { [ordered]@{ name = $_.FullName; bytes = $_.Length; sha256 = (Get-StreamHash $stream) } }
                finally { $stream.Dispose() }
            }
        })
        return @($rows | Sort-Object { $_.name } -CaseSensitive)
    } finally { $zip.Dispose() }
}

function Write-Manifest([string]$Name, [array]$Manifest) {
    ConvertTo-Json -InputObject $Manifest -Depth 5 | Set-Content -LiteralPath (Join-Path $fullEvidenceRoot $Name) -Encoding UTF8
}

function Assert-ManifestEqual([array]$Expected, [array]$Actual) {
    # ZIP stores empty directories explicitly; nonempty directories may be implicit.
    $expectedFiles = @($Expected | Where-Object { $null -ne $_.sha256 })
    $actualFiles = @($Actual | Where-Object { $null -ne $_.sha256 })
    if ((ConvertTo-Json -InputObject $expectedFiles -Compress) -cne (ConvertTo-Json -InputObject $actualFiles -Compress)) { throw 'ARCHIVE_ENTRY_HASH_MISMATCH' }
    foreach ($directory in @($Expected | Where-Object { $null -eq $_.sha256 })) {
        if (-not @($Actual | Where-Object { $_.name.StartsWith($directory.name, [StringComparison]::Ordinal) }).Count) { throw 'ARCHIVE_DIRECTORY_MISSING' }
    }
    foreach ($directory in @($Actual | Where-Object { $null -eq $_.sha256 })) {
        if (-not @($Expected | Where-Object { $_.name -ceq $directory.name }).Count) { throw 'ARCHIVE_DIRECTORY_ADDED' }
    }
}

$result = [ordered]@{
    schema = 'windows-release-archive-regression-v1'; evidence_root = $fullEvidenceRoot
    powershell = $PSVersionTable.PSVersion.ToString(); powershell_executable = (Get-Process -Id $PID).Path
    status = 'running'; phase = 'fixture'; native_exit_code = 1; app_or_browser_launched = $false
    preserved_package = $package; owned_evidence_retained = $true; cleanup_performed = $false
}
try {
    # Given: identical synthetic bytes at short and >260-character paths, plus the real preserved package.
    $source = Join-Path $fullEvidenceRoot 'source with spaces'
    $short = Join-Path $fullEvidenceRoot 'short'
    [IO.Directory]::CreateDirectory((Get-ExtendedPath $source)) | Out-Null
    [IO.Directory]::CreateDirectory((Get-ExtendedPath $short)) | Out-Null
    $unicode = 'caf' + [char]0x00e9 + '-' + [char]0x4e2d + '.txt'
    $nested = Join-Path $source (('long segment ' + ('a' * 70)) + '\' + ('b' * 80) + '\' + ('c' * 65))
    [IO.Directory]::CreateDirectory((Get-ExtendedPath $nested)) | Out-Null
    [IO.Directory]::CreateDirectory((Get-ExtendedPath (Join-Path $source 'empty directory'))) | Out-Null
    $bytes = [Text.Encoding]::UTF8.GetBytes('SYNTHETIC ARCHIVE REGRESSION: preserved bytes, spaces and Unicode.')
    [IO.File]::WriteAllBytes((Get-ExtendedPath (Join-Path $short $unicode)), $bytes)
    [IO.File]::WriteAllBytes((Get-ExtendedPath (Join-Path $source $unicode)), $bytes)
    $longFile = Join-Path $nested $unicode
    [IO.File]::WriteAllBytes((Get-ExtendedPath $longFile), $bytes)
    $result.synthetic_long_path_length = $longFile.Length
    if ($longFile.Length -le 260) { throw 'LONG_FIXTURE_REQUIRED' }
    $fixtureBefore = @(Get-TreeManifest $source)
    Write-Manifest 'fixture-source-before.json' $fixtureBefore
    $packageBefore = @(Get-TreeManifest $package)
    Write-Manifest 'package-source-before.json' $packageBefore
    $guideSource = @($packageBefore | Where-Object { $_.name -cmatch '(^|/)04\. First Sign In Password Change\.png$' } |
        Sort-Object { $_.name.Length } -Descending | Select-Object -First 1)
    if ($guideSource.Count -ne 1) { throw 'PRESERVED_SIGN_IN_GUIDE_REQUIRED' }
    $realRelative = $guideSource[0].name
    $realFile = Join-Path $package $realRelative
    $result.real_long_file = [ordered]@{ path = $realFile; length = $realFile.Length; bytes = $guideSource[0].bytes; sha256 = $guideSource[0].sha256 }
    $latest = Join-Path (Split-Path $package -Parent) 'latest-release-paths.txt'
    $latestBefore = Get-FileHashValue $latest
    $result.latest_pointer_before_sha256 = $latestBefore
    $releaseZip = $package + '.zip'
    $result.release_zip_existed_before = [IO.File]::Exists((Get-ExtendedPath $releaseZip))

    # When: the exact old Compress-Archive operation receives the short then long fixture.
    $result.phase = 'legacy-short'
    $shortZip = Join-Path $fullEvidenceRoot 'legacy-short.zip'
    Compress-Archive -Path (Join-Path $short '*') -DestinationPath $shortZip
    Assert-ManifestEqual @(Get-TreeManifest $short) @(Get-ZipManifest $shortZip)
    $result.legacy_short_passed = $true
    $result.phase = 'legacy-long'
    $legacyFailure = $null
    try { Compress-Archive -Path (Join-Path $source '*') -DestinationPath (Join-Path $fullEvidenceRoot 'legacy-long.zip') }
    catch { $legacyFailure = [ordered]@{ type = $_.Exception.GetType().FullName; hresult = $_.Exception.HResult; id = $_.FullyQualifiedErrorId } }
    if ($null -eq $legacyFailure) { throw 'LEGACY_LONG_FAILURE_NOT_REPRODUCED' }
    $result.legacy_long_failure = $legacyFailure
    if ($BaselineOnly) {
        $result.status = 'red-reproduced'; $result.phase = 'baseline-complete'
        Write-Host 'RED: short Unicode path archived; same bytes under long path failed in Compress-Archive.'
    } else {
        # Read only the current builder's single static ZIP expression; never dot-source or run the builder.
        $result.phase = 'builder-archive-expression'
        $tokens = $null; $parseErrors = $null
        $ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'build-windows-installer.ps1'), [ref]$tokens, [ref]$parseErrors)
        if ($parseErrors.Count) { throw 'BUILDER_PARSE_FAILED' }
        $calls = @($ast.FindAll({ param($node)
            $node -is [Management.Automation.Language.InvokeMemberExpressionAst] -and $node.Static -and
            $node.Expression.TypeName.FullName -eq 'System.IO.Compression.ZipFile' -and $node.Member.Value -eq 'CreateFromDirectory'
        }, $true))
        if ($calls.Count -ne 1 -or $calls[0].Arguments.Count -ne 2) { throw 'SINGLE_REPAIRED_ARCHIVE_EXPRESSION_REQUIRED' }
        $switches = @($ast.FindAll({ param($node)
            $node -is [Management.Automation.Language.InvokeMemberExpressionAst] -and $node.Static -and
            $node.Expression.TypeName.FullName -eq 'System.AppContext' -and $node.Member.Value -eq 'SetSwitch'
        }, $true))
        if ($switches.Count -ne 1 -or $switches[0].Arguments.Count -ne 2 -or
            $switches[0].Arguments[0].Value -cne 'Switch.System.IO.Compression.ZipFile.UseBackslash' -or
            $switches[0].Arguments[1].Extent.Text -cne '$false') { throw 'ZIP_STANDARD_SEPARATOR_SWITCH_REQUIRED' }
        $archiveExpression = [ScriptBlock]::Create($switches[0].Extent.Text + "`n" + $calls[0].Extent.Text)
        function Invoke-CurrentArchive([string]$PackageDir, [string]$zipPath) { & $archiveExpression }
        $result.archive_expression = $archiveExpression.ToString()
        # Then: all relative file names, lengths, bytes and empty directories survive the actual archive operation.
        $result.phase = 'fixed-fixture'
        $fixtureZip = Join-Path $fullEvidenceRoot 'fixture-fixed.zip'
        Invoke-CurrentArchive $source $fixtureZip
        $fixtureArchive = @(Get-ZipManifest $fixtureZip)
        Write-Manifest 'fixture-archive.json' $fixtureArchive
        Assert-ManifestEqual $fixtureBefore $fixtureArchive
        $result.fixture_entry_hashes_equal = $true
        $result.phase = 'fixed-preserved-package'
        $packageZip = Join-Path $fullEvidenceRoot 'preserved-package-copy.zip'
        Invoke-CurrentArchive $package $packageZip
        $packageArchive = @(Get-ZipManifest $packageZip)
        Write-Manifest 'package-archive.json' $packageArchive
        Assert-ManifestEqual $packageBefore $packageArchive
        $guideEntry = @($packageArchive | Where-Object { $_.name -ceq $realRelative })
        if ($guideEntry.Count -ne 1 -or $guideEntry[0].bytes -ne $result.real_long_file.bytes -or
            $guideEntry[0].sha256 -cne $result.real_long_file.sha256) { throw 'LONG_GUIDE_ARCHIVE_MISMATCH' }
        $result.package_entry_hashes_equal = $true
        $result.package_file_count = @($packageBefore | Where-Object { $null -ne $_.sha256 }).Count
        $result.package_zip = [ordered]@{ path = $packageZip; sha256 = (Get-FileHashValue $packageZip); entries = $packageArchive.Count }
        $result.phase = 'zip-safety-scan'
        . (Join-Path $PSScriptRoot 'release-safety.ps1')
        Assert-ZipHasNoForbiddenItems -ZipPath $packageZip
        $result.zip_forbidden_scan_passed = $true
        $result.status = 'passed'; $result.native_exit_code = 0; $result.phase = 'complete'
        Write-Host 'GREEN: current builder archive expression preserved all fixture and real package entries/hashes.'
    }
} catch {
    $result.status = 'failed'
    $result.failure = [ordered]@{ type = $_.Exception.GetType().FullName; hresult = $_.Exception.HResult; code = $_.FullyQualifiedErrorId }
} finally {
    try {
        if ($packageBefore) {
            $packageAfter = @(Get-TreeManifest $package)
            Write-Manifest 'package-source-after.json' $packageAfter
            if ((ConvertTo-Json -InputObject $packageBefore -Compress) -cne (ConvertTo-Json -InputObject $packageAfter -Compress)) { throw 'PRESERVED_PACKAGE_CHANGED' }
            $result.preserved_package_unchanged = $true
        }
        if ($latestBefore) {
            $result.latest_pointer_after_sha256 = Get-FileHashValue $latest
            if ($latestBefore -cne $result.latest_pointer_after_sha256) { throw 'LATEST_POINTER_CHANGED' }
            if ($result.release_zip_existed_before -ne [IO.File]::Exists((Get-ExtendedPath $releaseZip))) { throw 'RELEASE_ZIP_STATE_CHANGED' }
        }
    } catch { $result.status = 'failed'; $result.native_exit_code = 1; $result.preservation_failure = $_.FullyQualifiedErrorId }
    $result.completed_utc = (Get-Date).ToUniversalTime().ToString('o')
    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $fullEvidenceRoot 'result.json') -Encoding UTF8
}
Write-Host ('Evidence: ' + $fullEvidenceRoot)
exit $result.native_exit_code
