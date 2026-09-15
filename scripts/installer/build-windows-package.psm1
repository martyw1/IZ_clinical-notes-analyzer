Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:ProductId = 'r3.iz-clinical-notes-analyzer.desktop'
$script:RootCommandNames = @(
    'Install-IZ-Clinical-Notes-Analyzer.cmd',
    'Launch-IZ-Clinical-Notes-Analyzer.cmd',
    'Stop-IZ-Clinical-Notes-Analyzer.cmd',
    'Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd',
    'Backup-IZ-Clinical-Notes-Analyzer.cmd',
    'Restore-IZ-Clinical-Notes-Analyzer.cmd',
    'Uninstall-IZ-Clinical-Notes-Analyzer.cmd',
    'Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd'
)
$script:CopiedInstallerNames = @(
    'maintenance-windows.ps1',
    'install-windows-release.ps1',
    'uninstall-windows-release.ps1',
    'maintenance-common.psm1',
    'maintenance-contracts.psm1',
    'maintenance-paths.psm1',
    'maintenance-version.psm1',
    'maintenance-lock.psm1',
    'maintenance-journal.psm1',
    'backup-verification.psm1',
    'maintenance-runtime.psm1',
    'maintenance-transaction.psm1'
)
$script:InstallerNames = @(
    $script:CopiedInstallerNames +
    'Remove-IZ-Clinical-Notes-Analyzer.bootstrap.ps1' +
    'maintenance-bundle-manifest.json' +
    'legacy-program-inventory.json'
)
$script:MaintenanceBundleNames = @(
    'maintenance-windows.ps1',
    'uninstall-windows-release.ps1',
    'maintenance-common.psm1',
    'maintenance-contracts.psm1',
    'maintenance-paths.psm1',
    'maintenance-version.psm1',
    'maintenance-lock.psm1',
    'maintenance-journal.psm1',
    'maintenance-runtime.psm1'
)
$script:GateNames = @(
    'backend_tests',
    'frontend_tests',
    'frontend_build',
    'repository_safety',
    'directory_safety',
    'zip_safety',
    'frozen_bundle_inspection'
)

function Get-IzFileSha256 {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$Path)

    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-IzStringSha256 {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($Value)
        return ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
}

function Write-IzUtf8NoBomJson {
    param(
        [Parameter(Mandatory = $true)]$Value,
        [Parameter(Mandatory = $true)][string]$Path,
        [int]$Depth = 10
    )

    $json = $Value | ConvertTo-Json -Depth $Depth
    [System.IO.File]::WriteAllText($Path, $json, [System.Text.UTF8Encoding]::new($false))
}

function Read-IzUtf8Json {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Reason
    )

    try {
        $json = [System.IO.File]::ReadAllText($Path, [System.Text.UTF8Encoding]::new($false, $true))
        return $json | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw $Reason
    }
}

function Get-IzOrdinalSortedStrings {
    param([AllowEmptyCollection()][string[]]$Values = @())

    $copy = [string[]]@($Values)
    [Array]::Sort($copy, [System.StringComparer]::Ordinal)
    return $copy
}

function Assert-IzExactProperties {
    param(
        [Parameter(Mandatory = $true)]$Value,
        [Parameter(Mandatory = $true)][string[]]$Names,
        [Parameter(Mandatory = $true)][string]$Reason
    )

    if ($null -eq $Value) { throw $Reason }
    $actual = Get-IzOrdinalSortedStrings -Values @($Value.PSObject.Properties.Name)
    $expected = Get-IzOrdinalSortedStrings -Values $Names
    if (($actual -join "`n") -cne ($expected -join "`n")) { throw $Reason }
}

function Assert-IzSimpleFileName {
    param([Parameter(Mandatory = $true)][string]$Name)

    if (-not $Name -or $Name -ne [System.IO.Path]::GetFileName($Name) -or
        $Name.Contains('/') -or $Name.Contains('\') -or $Name -in @('.', '..')) {
        throw 'INVALID_PACKAGE_FILE_NAME'
    }
}

function Get-IzInstallerRuntimeRelativePaths {
    [CmdletBinding()]
    param()

    return @($script:InstallerNames)
}

function Get-IzMaintenanceBundleRelativePaths {
    [CmdletBinding()]
    param()

    return @($script:MaintenanceBundleNames)
}

function Assert-IzArtifactPathsAvailable {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string[]]$Paths)

    $identities = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($path in $Paths) {
        if (-not [System.IO.Path]::IsPathRooted($path)) { throw 'ARTIFACT_PATH_NOT_ABSOLUTE' }
        $fullPath = [System.IO.Path]::GetFullPath($path)
        if (-not $identities.Add($fullPath)) { throw 'ARTIFACT_PATH_DUPLICATE' }
        if (Test-Path -LiteralPath $fullPath) { throw 'ARTIFACT_COLLISION' }
    }
}

function ConvertTo-IzCrlf {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)

    $normalized = $Value.Replace("`r`n", "`n").Replace("`r", "`n")
    return $normalized.Replace("`n", "`r`n")
}

function Write-IzRenderedTemplate {
    param(
        [Parameter(Mandatory = $true)][string]$SourcePath,
        [Parameter(Mandatory = $true)][string]$DestinationPath,
        [hashtable]$Tokens = @{},
        [ValidateSet('AsciiCrlf', 'Utf8Bom')][string]$Encoding
    )

    $content = [System.IO.File]::ReadAllText($SourcePath)
    foreach ($tokenName in (Get-IzOrdinalSortedStrings -Values @($Tokens.Keys))) {
        $token = "@@$tokenName@@"
        if (-not $content.Contains($token)) { throw "REQUIRED_TEMPLATE_TOKEN_MISSING:$tokenName" }
        $content = $content.Replace($token, [string]$Tokens[$tokenName])
    }
    if ($content -match '@@[A-Z][A-Z0-9_]*@@') { throw 'UNRESOLVED_TEMPLATE_TOKEN' }

    if ($Encoding -eq 'AsciiCrlf') {
        $content = ConvertTo-IzCrlf -Value $content
        if ($content.ToCharArray() | Where-Object { [int]$_ -gt 127 } | Select-Object -First 1) {
            throw 'CMD_TEMPLATE_NOT_ASCII'
        }
        [System.IO.File]::WriteAllText($DestinationPath, $content, [System.Text.ASCIIEncoding]::new())
        return
    }
    [System.IO.File]::WriteAllText($DestinationPath, $content, [System.Text.UTF8Encoding]::new($true))
}

function New-IzFileRecord {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$RelativePath
    )

    $item = Get-Item -LiteralPath $Path
    return [ordered]@{
        path = $RelativePath
        length = [long]$item.Length
        sha256 = Get-IzFileSha256 -Path $item.FullName
    }
}

function Write-IzMaintenanceBundleManifest {
    param([Parameter(Mandatory = $true)][string]$InstallerDirectory)

    $recordsByName = @{}
    foreach ($name in $script:MaintenanceBundleNames) {
        Assert-IzSimpleFileName -Name $name
        $path = Join-Path $InstallerDirectory $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "PACKAGE_SOURCE_MISSING:$name" }
        $recordsByName[$name] = New-IzFileRecord -Path $path -RelativePath $name
    }
    $sortedNames = Get-IzOrdinalSortedStrings -Values $script:MaintenanceBundleNames
    $manifest = [ordered]@{
        schema = 'iz-cna-maintenance-bundle-v1'
        product_id = $script:ProductId
        files = @($sortedNames | ForEach-Object { $recordsByName[$_] })
    }
    $path = Join-Path $InstallerDirectory 'maintenance-bundle-manifest.json'
    if (Test-Path -LiteralPath $path) { throw 'ARTIFACT_COLLISION' }
    Write-IzUtf8NoBomJson -Value $manifest -Path $path -Depth 5
    return $manifest
}

function Assert-IzMaintenanceBundleManifest {
    param([Parameter(Mandatory = $true)][string]$InstallerDirectory)

    $manifestPath = Join-Path $InstallerDirectory 'maintenance-bundle-manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw 'MAINTENANCE_BUNDLE_MANIFEST_MISSING'
    }
    $manifest = Read-IzUtf8Json -Path $manifestPath -Reason 'MAINTENANCE_BUNDLE_MANIFEST_INVALID'
    Assert-IzExactProperties -Value $manifest -Names @('schema', 'product_id', 'files') -Reason 'MAINTENANCE_BUNDLE_MANIFEST_INVALID'
    if ($manifest.schema -cne 'iz-cna-maintenance-bundle-v1' -or $manifest.product_id -cne $script:ProductId) {
        throw 'MAINTENANCE_BUNDLE_MANIFEST_INVALID'
    }
    $records = @($manifest.files)
    $expectedNames = @(Get-IzOrdinalSortedStrings -Values $script:MaintenanceBundleNames)
    if ($records.Count -ne $expectedNames.Count) { throw 'MAINTENANCE_BUNDLE_FILE_SET_MISMATCH' }
    for ($index = 0; $index -lt $expectedNames.Count; $index++) {
        $record = $records[$index]
        Assert-IzExactProperties -Value $record -Names @('path', 'length', 'sha256') -Reason 'MAINTENANCE_BUNDLE_FILE_RECORD_INVALID'
        $name = [string]$record.path
        Assert-IzSimpleFileName -Name $name
        if ($name -cne $expectedNames[$index] -or [long]$record.length -lt 0 -or
            [string]$record.sha256 -notmatch '^[0-9a-f]{64}$') {
            throw 'MAINTENANCE_BUNDLE_FILE_RECORD_INVALID'
        }
        $sourcePath = Join-Path $InstallerDirectory $name
        if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf) -or
            [long](Get-Item -LiteralPath $sourcePath).Length -ne [long]$record.length -or
            (Get-IzFileSha256 -Path $sourcePath) -cne [string]$record.sha256) {
            throw 'MAINTENANCE_BUNDLE_FILE_MISMATCH'
        }
    }
    return $manifest
}

function Write-IzPackageInstallerFiles {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][string]$PackageRoot,
        [Parameter(Mandatory = $true)]$LegacyProgramInventory
    )

    $resolvedRepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
    $resolvedPackageRoot = (Resolve-Path -LiteralPath $PackageRoot).Path
    $sourceInstallerRoot = Join-Path $resolvedRepositoryRoot 'scripts\installer'
    $sourceTemplateRoot = Join-Path $sourceInstallerRoot 'templates'
    $bootstrapTemplateName = 'Remove-IZ-Clinical-Notes-Analyzer.bootstrap.ps1'

    $requiredSources = @(
        $script:CopiedInstallerNames | ForEach-Object { Join-Path $sourceInstallerRoot $_ }
    ) + @(
        $script:RootCommandNames | ForEach-Object { Join-Path $sourceTemplateRoot $_ }
    ) + @(
        (Join-Path $sourceTemplateRoot $bootstrapTemplateName)
    )
    foreach ($sourcePath in $requiredSources) {
        if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
            throw "PACKAGE_SOURCE_MISSING:$([System.IO.Path]::GetFileName($sourcePath))"
        }
    }

    $targetPaths = @(
        $script:RootCommandNames | ForEach-Object { Join-Path $resolvedPackageRoot $_ }
    ) + @(
        $script:InstallerNames | ForEach-Object { Join-Path (Join-Path $resolvedPackageRoot 'installer') $_ }
    )
    foreach ($targetPath in $targetPaths) {
        if (Test-Path -LiteralPath $targetPath) { throw 'ARTIFACT_COLLISION' }
    }

    $targetInstallerRoot = Join-Path $resolvedPackageRoot 'installer'
    New-Item -ItemType Directory -Path $targetInstallerRoot -Force | Out-Null
    foreach ($name in $script:CopiedInstallerNames) {
        Copy-Item -LiteralPath (Join-Path $sourceInstallerRoot $name) -Destination (Join-Path $targetInstallerRoot $name)
    }

    $null = Write-IzMaintenanceBundleManifest -InstallerDirectory $targetInstallerRoot
    $null = Assert-IzMaintenanceBundleManifest -InstallerDirectory $targetInstallerRoot
    $bundlePath = Join-Path $targetInstallerRoot 'maintenance-bundle-manifest.json'
    $bundleSha256 = Get-IzFileSha256 -Path $bundlePath
    Write-IzUtf8NoBomJson `
        -Value $LegacyProgramInventory `
        -Path (Join-Path $targetInstallerRoot 'legacy-program-inventory.json') `
        -Depth 8
    Write-IzRenderedTemplate `
        -SourcePath (Join-Path $sourceTemplateRoot $bootstrapTemplateName) `
        -DestinationPath (Join-Path $targetInstallerRoot $bootstrapTemplateName) `
        -Tokens @{ MAINTENANCE_BUNDLE_MANIFEST_SHA256 = $bundleSha256 } `
        -Encoding Utf8Bom

    foreach ($name in $script:RootCommandNames) {
        Write-IzRenderedTemplate `
            -SourcePath (Join-Path $sourceTemplateRoot $name) `
            -DestinationPath (Join-Path $resolvedPackageRoot $name) `
            -Encoding AsciiCrlf
    }

    $actualInstallerNames = @(
        Get-ChildItem -LiteralPath $targetInstallerRoot -File | ForEach-Object Name
    )
    $actualSorted = Get-IzOrdinalSortedStrings -Values $actualInstallerNames
    $expectedSorted = Get-IzOrdinalSortedStrings -Values $script:InstallerNames
    if (($actualSorted -join "`n") -cne ($expectedSorted -join "`n")) {
        throw 'INSTALLER_ALLOWLIST_MISMATCH'
    }

    return [pscustomobject][ordered]@{
        maintenance_bundle_manifest_sha256 = $bundleSha256
        root_commands = @($script:RootCommandNames)
        installer_files = @($script:InstallerNames)
    }
}

function Get-IzPackageRelativeFilePaths {
    param([Parameter(Mandatory = $true)][string]$PackageRoot)

    $resolvedPackageRoot = (Resolve-Path -LiteralPath $PackageRoot).Path.TrimEnd([char[]]@('\', '/'))
    $prefix = $resolvedPackageRoot + [System.IO.Path]::DirectorySeparatorChar
    $paths = @(
        Get-ChildItem -LiteralPath $resolvedPackageRoot -Recurse -File -Force | ForEach-Object {
            $fullPath = [System.IO.Path]::GetFullPath($_.FullName)
            if (-not $fullPath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw 'PACKAGE_PATH_ESCAPE'
            }
            $fullPath.Substring($prefix.Length).Replace('\', '/')
        }
    )
    return @(Get-IzOrdinalSortedStrings -Values $paths)
}

function Assert-IzPackageLayout {
    param(
        [Parameter(Mandatory = $true)][string]$PackageRoot,
        [switch]$ManifestExpected
    )

    foreach ($item in Get-ChildItem -LiteralPath $PackageRoot -Recurse -Force -ErrorAction Stop) {
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            throw 'PACKAGE_REPARSE_POINT'
        }
    }

    foreach ($name in $script:RootCommandNames) {
        if (-not (Test-Path -LiteralPath (Join-Path $PackageRoot $name) -PathType Leaf)) {
            throw "REQUIRED_PACKAGE_MEMBER_MISSING:$name"
        }
    }
    foreach ($name in $script:InstallerNames) {
        if (-not (Test-Path -LiteralPath (Join-Path (Join-Path $PackageRoot 'installer') $name) -PathType Leaf)) {
            throw "REQUIRED_PACKAGE_MEMBER_MISSING:installer/$name"
        }
    }
    foreach ($relativePath in @(
        'app\runtime\IZClinicalNotesAnalyzer.exe',
        'app\frontend\dist\index.html',
        'app\config\checklists\treatment-plan-v1.json',
        'app\VERSION',
        'app\VERSION.json'
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $PackageRoot $relativePath) -PathType Leaf)) {
            throw "REQUIRED_PACKAGE_MEMBER_MISSING:$($relativePath.Replace('\', '/'))"
        }
    }
    if (@(Get-ChildItem -LiteralPath (Join-Path $PackageRoot 'app\frontend\dist\assets') -File -Recurse -ErrorAction SilentlyContinue).Count -lt 1) {
        throw 'REQUIRED_PACKAGE_MEMBER_MISSING:app/frontend/dist/assets'
    }
    if (@(Get-ChildItem -LiteralPath (Join-Path $PackageRoot 'app\config\rules') -File -Recurse -ErrorAction SilentlyContinue).Count -lt 1) {
        throw 'REQUIRED_PACKAGE_MEMBER_MISSING:app/config/rules'
    }

    $topLevelDirectories = @(Get-ChildItem -LiteralPath $PackageRoot -Directory -Force | ForEach-Object Name)
    $expectedDirectories = @('app', 'installer')
    if (((Get-IzOrdinalSortedStrings $topLevelDirectories) -join "`n") -cne ((Get-IzOrdinalSortedStrings $expectedDirectories) -join "`n")) {
        throw 'PACKAGE_TOP_LEVEL_DIRECTORY_MISMATCH'
    }
    $allowedTopFiles = @($script:RootCommandNames)
    if ($ManifestExpected) { $allowedTopFiles += 'release-manifest.json' }
    $topLevelFiles = @(Get-ChildItem -LiteralPath $PackageRoot -File -Force | ForEach-Object Name)
    if (((Get-IzOrdinalSortedStrings $topLevelFiles) -join "`n") -cne ((Get-IzOrdinalSortedStrings $allowedTopFiles) -join "`n")) {
        throw 'PACKAGE_TOP_LEVEL_FILE_MISMATCH'
    }

    $actualInstallerNames = @(Get-ChildItem -LiteralPath (Join-Path $PackageRoot 'installer') -File -Force | ForEach-Object Name)
    if (((Get-IzOrdinalSortedStrings $actualInstallerNames) -join "`n") -cne ((Get-IzOrdinalSortedStrings $script:InstallerNames) -join "`n")) {
        throw 'INSTALLER_ALLOWLIST_MISMATCH'
    }
    if (@(Get-ChildItem -LiteralPath (Join-Path $PackageRoot 'installer') -Directory -Force -ErrorAction SilentlyContinue).Count -ne 0) {
        throw 'INSTALLER_SUBDIRECTORY_NOT_ALLOWED'
    }
    $null = Assert-IzMaintenanceBundleManifest -InstallerDirectory (Join-Path $PackageRoot 'installer')

    foreach ($relativePath in (Get-IzPackageRelativeFilePaths -PackageRoot $PackageRoot)) {
        $lower = $relativePath.ToLowerInvariant()
        if ($lower -match '(^|/)(tests?|test-results|e2e|templates?|fixtures?|evidence)(/|$)' -or
            $lower -match '(^|/)(test[-_.]|[^/]+\.(test|spec)\.)' -or
            $lower -match '(^|/)[^/]*controller[^/]*$' -or
            $lower -in @(
                'app/scripts/complete-uninstall-local-data.ps1',
                'app/scripts/complete-uninstall-iz-clinical-notes-analyzer.cmd'
            )) {
            throw 'FORBIDDEN_PACKAGE_DEVELOPER_MEMBER'
        }
    }
}

function New-IzReleaseFileRecords {
    param([Parameter(Mandatory = $true)][string]$PackageRoot)

    $paths = @(Get-IzPackageRelativeFilePaths -PackageRoot $PackageRoot | Where-Object { $_ -cne 'release-manifest.json' })
    $seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    $records = @()
    foreach ($relativePath in $paths) {
        if (-not $seen.Add($relativePath)) { throw 'DUPLICATE_PACKAGE_MEMBER' }
        $records += New-IzFileRecord `
            -Path (Join-Path $PackageRoot $relativePath.Replace('/', '\')) `
            -RelativePath $relativePath
    }
    return @($records)
}

function Get-IzPayloadIdentity {
    param([Parameter(Mandatory = $true)][object[]]$Files)

    $canonical = @($Files | ForEach-Object {
        "{0}`t{1}`t{2}`n" -f $_.path, $_.length, $_.sha256
    }) -join ''
    return Get-IzStringSha256 -Value $canonical
}

function Write-IzReleaseManifest {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$PackageRoot,
        [Parameter(Mandatory = $true)][string]$Version,
        [Parameter(Mandatory = $true)][string]$Build,
        [Parameter(Mandatory = $true)][int]$InstallerRevision,
        [Parameter(Mandatory = $true)][string]$ReleaseChannel
    )

    if ($Build -notmatch '^\d{4}\.\d{2}\.\d{2}\.\d+$') { throw 'INVALID_BUILD_VERSION' }
    if ($InstallerRevision -ne 1) { throw 'INVALID_INSTALLER_REVISION' }
    $manifestPath = Join-Path $PackageRoot 'release-manifest.json'
    if (Test-Path -LiteralPath $manifestPath) { throw 'ARTIFACT_COLLISION' }
    Assert-IzPackageLayout -PackageRoot $PackageRoot
    $files = @(New-IzReleaseFileRecords -PackageRoot $PackageRoot)
    $manifest = [ordered]@{
        schema = 'iz-cna-release-manifest-v1'
        product_id = $script:ProductId
        version = $Version
        build = $Build
        installer_revision = $InstallerRevision
        release_channel = $ReleaseChannel
        compatibility = [ordered]@{
            source_version_minimum = '2.0.0-beta.3'
            source_version_maximum = '2.0.0-beta.4'
            source_build_minimum = '2026.09.03.1'
            source_build_maximum = '2026.09.10.2'
            source_schema_minimum = 12
            source_schema_maximum = 12
            target_schema = 12
        }
        payload_identity = Get-IzPayloadIdentity -Files $files
        files = @($files)
    }
    Write-IzUtf8NoBomJson -Value $manifest -Path $manifestPath -Depth 8
    $null = Assert-IzReleaseManifest -PackageRoot $PackageRoot
    return [pscustomobject]$manifest
}

function Assert-IzReleaseManifest {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$PackageRoot)

    $manifestPath = Join-Path $PackageRoot 'release-manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'RELEASE_MANIFEST_MISSING' }
    $manifest = Read-IzUtf8Json -Path $manifestPath -Reason 'RELEASE_MANIFEST_INVALID'
    Assert-IzExactProperties -Value $manifest -Names @(
        'schema', 'product_id', 'version', 'build', 'installer_revision', 'release_channel',
        'compatibility', 'payload_identity', 'files'
    ) -Reason 'RELEASE_MANIFEST_KEYS_INVALID'
    Assert-IzExactProperties -Value $manifest.compatibility -Names @(
        'source_version_minimum', 'source_version_maximum', 'source_build_minimum',
        'source_build_maximum', 'source_schema_minimum', 'source_schema_maximum', 'target_schema'
    ) -Reason 'RELEASE_MANIFEST_COMPATIBILITY_KEYS_INVALID'
    if ($manifest.schema -cne 'iz-cna-release-manifest-v1' -or $manifest.product_id -cne $script:ProductId) {
        throw 'RELEASE_MANIFEST_IDENTITY_INVALID'
    }
    $expectedCompatibility = @(
        '2.0.0-beta.3', '2.0.0-beta.4', '2026.09.03.1', '2026.09.10.2', 12, 12, 12
    )
    $actualCompatibility = @(
        $manifest.compatibility.source_version_minimum,
        $manifest.compatibility.source_version_maximum,
        $manifest.compatibility.source_build_minimum,
        $manifest.compatibility.source_build_maximum,
        $manifest.compatibility.source_schema_minimum,
        $manifest.compatibility.source_schema_maximum,
        $manifest.compatibility.target_schema
    )
    if (($actualCompatibility -join "`n") -cne ($expectedCompatibility -join "`n")) {
        throw 'RELEASE_MANIFEST_COMPATIBILITY_INVALID'
    }

    Assert-IzPackageLayout -PackageRoot $PackageRoot -ManifestExpected
    $actualFiles = @(New-IzReleaseFileRecords -PackageRoot $PackageRoot)
    $manifestFiles = @($manifest.files)
    if ($manifestFiles.Count -ne $actualFiles.Count) { throw 'RELEASE_MANIFEST_FILE_COUNT_MISMATCH' }
    for ($index = 0; $index -lt $actualFiles.Count; $index++) {
        Assert-IzExactProperties -Value $manifestFiles[$index] -Names @('path', 'length', 'sha256') -Reason 'RELEASE_MANIFEST_FILE_KEYS_INVALID'
        if ($manifestFiles[$index].path -cne $actualFiles[$index].path -or
            [long]$manifestFiles[$index].length -ne [long]$actualFiles[$index].length -or
            $manifestFiles[$index].sha256 -cne $actualFiles[$index].sha256) {
            throw 'RELEASE_MANIFEST_FILE_MISMATCH'
        }
    }
    $payloadIdentity = Get-IzPayloadIdentity -Files $actualFiles
    if ($manifest.payload_identity -cne $payloadIdentity) { throw 'RELEASE_MANIFEST_PAYLOAD_IDENTITY_MISMATCH' }
    return $manifest
}

function Assert-IzSafeEvidencePath {
    param(
        [Parameter(Mandatory = $true)][string]$ReceiptDirectory,
        [Parameter(Mandatory = $true)][string]$RelativePath
    )

    if (-not $RelativePath -or $RelativePath.Contains('\') -or
        [System.IO.Path]::IsPathRooted($RelativePath) -or $RelativePath.Contains(':')) {
        throw 'BUILD_GATE_EVIDENCE_PATH_INVALID'
    }
    $parts = @($RelativePath.Split('/') | Where-Object { $_ })
    if ($parts.Count -eq 0 -or @($parts | Where-Object { $_ -in @('.', '..') }).Count -ne 0) {
        throw 'BUILD_GATE_EVIDENCE_PATH_INVALID'
    }
    $receiptRoot = [System.IO.Path]::GetFullPath($ReceiptDirectory).TrimEnd([char[]]@('\', '/'))
    $evidencePath = [System.IO.Path]::GetFullPath((Join-Path $receiptRoot $RelativePath.Replace('/', '\')))
    if (-not $evidencePath.StartsWith($receiptRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'BUILD_GATE_EVIDENCE_PATH_INVALID'
    }
    if (-not (Test-Path -LiteralPath $evidencePath -PathType Leaf) -or (Get-Item -LiteralPath $evidencePath).Length -le 0) {
        throw 'BUILD_GATE_EVIDENCE_MISSING'
    }
    $currentPath = $evidencePath
    while ($currentPath -and
        ($currentPath -ieq $receiptRoot -or
            $currentPath.StartsWith($receiptRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase))) {
        $current = Get-Item -LiteralPath $currentPath -Force
        if ($current.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw 'BUILD_GATE_EVIDENCE_REPARSE_POINT' }
        if ($currentPath -ieq $receiptRoot) { break }
        $currentPath = Split-Path $currentPath -Parent
    }
}

function Write-IzBuildReceipt {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$ReceiptPath,
        [Parameter(Mandatory = $true)][string]$ProductId,
        [Parameter(Mandatory = $true)][string]$Version,
        [Parameter(Mandatory = $true)][string]$Build,
        [Parameter(Mandatory = $true)][int]$InstallerRevision,
        [Parameter(Mandatory = $true)][string]$SourceRevision,
        [Parameter(Mandatory = $true)][string]$PackageDirectory,
        [Parameter(Mandatory = $true)][string]$ZipPath,
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][string]$PayloadIdentity,
        [Parameter(Mandatory = $true)][object[]]$Gates
    )

    foreach ($path in @($ReceiptPath, $PackageDirectory, $ZipPath, $ManifestPath)) {
        if (-not [System.IO.Path]::IsPathRooted($path)) { throw 'BUILD_RECEIPT_PATH_NOT_ABSOLUTE' }
    }
    $fullReceiptPath = [System.IO.Path]::GetFullPath($ReceiptPath)
    if (Test-Path -LiteralPath $fullReceiptPath) { throw 'ARTIFACT_COLLISION' }
    $fullPackageDirectory = (Resolve-Path -LiteralPath $PackageDirectory).Path
    $fullZipPath = (Resolve-Path -LiteralPath $ZipPath).Path
    $fullManifestPath = (Resolve-Path -LiteralPath $ManifestPath).Path
    if ($ProductId -cne $script:ProductId -or $InstallerRevision -ne 1 -or
        $Build -notmatch '^\d{4}\.\d{2}\.\d{2}\.\d+$' -or
        $SourceRevision -notmatch '^[0-9a-f]{40}$' -or $PayloadIdentity -notmatch '^[0-9a-f]{64}$') {
        throw 'BUILD_RECEIPT_IDENTITY_INVALID'
    }
    if ($Gates.Count -ne $script:GateNames.Count) { throw 'BUILD_RECEIPT_GATES_INVALID' }
    $normalizedGates = @()
    $receiptDirectory = Split-Path $fullReceiptPath -Parent
    for ($index = 0; $index -lt $script:GateNames.Count; $index++) {
        $gate = $Gates[$index]
        $gateName = if ($gate -is [System.Collections.IDictionary]) { [string]$gate['name'] } else { [string]$gate.name }
        $gateStatus = if ($gate -is [System.Collections.IDictionary]) { [string]$gate['status'] } else { [string]$gate.status }
        $gateCommand = if ($gate -is [System.Collections.IDictionary]) { [string]$gate['command'] } else { [string]$gate.command }
        $gateExitCode = if ($gate -is [System.Collections.IDictionary]) { [int]$gate['exit_code'] } else { [int]$gate.exit_code }
        $gateEvidence = if ($gate -is [System.Collections.IDictionary]) { [string]$gate['evidence'] } else { [string]$gate.evidence }
        if ($gateName -cne $script:GateNames[$index] -or $gateStatus -cne 'passed' -or
            $gateExitCode -ne 0 -or -not $gateCommand) {
            throw 'BUILD_RECEIPT_GATES_INVALID'
        }
        Assert-IzSafeEvidencePath -ReceiptDirectory $receiptDirectory -RelativePath $gateEvidence
        $normalizedGates += [ordered]@{
            name = $gateName
            status = $gateStatus
            command = $gateCommand
            exit_code = $gateExitCode
            evidence = $gateEvidence
        }
    }

    $manifest = Assert-IzReleaseManifest -PackageRoot $fullPackageDirectory
    $expectedManifestPath = Join-Path $fullPackageDirectory 'release-manifest.json'
    if ($manifest.product_id -cne $ProductId -or $manifest.version -cne $Version -or
        $manifest.build -cne $Build -or [int]$manifest.installer_revision -ne $InstallerRevision -or
        $manifest.payload_identity -cne $PayloadIdentity -or
        -not [string]::Equals($fullManifestPath, $expectedManifestPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'BUILD_RECEIPT_MANIFEST_MISMATCH'
    }
    $zipItem = Get-Item -LiteralPath $fullZipPath
    if ($zipItem.Length -le 0) { throw 'BUILD_RECEIPT_ZIP_EMPTY' }
    $receipt = [ordered]@{
        schema = 'iz-cna-build-receipt-v1'
        product_id = $ProductId
        version = $Version
        build = $Build
        installer_revision = $InstallerRevision
        source_revision = $SourceRevision
        package_directory = $fullPackageDirectory
        zip_path = $fullZipPath
        zip_length = [long]$zipItem.Length
        zip_sha256 = Get-IzFileSha256 -Path $fullZipPath
        manifest_sha256 = Get-IzFileSha256 -Path $fullManifestPath
        payload_identity = $PayloadIdentity
        gates = @($normalizedGates)
        created_utc = [DateTime]::UtcNow.ToString('o')
    }
    Write-IzUtf8NoBomJson -Value $receipt -Path $fullReceiptPath -Depth 8
    return [pscustomobject]$receipt
}

Export-ModuleMember -Function @(
    'Get-IzFileSha256',
    'Get-IzInstallerRuntimeRelativePaths',
    'Get-IzMaintenanceBundleRelativePaths',
    'Assert-IzArtifactPathsAvailable',
    'Write-IzPackageInstallerFiles',
    'Write-IzReleaseManifest',
    'Assert-IzReleaseManifest',
    'Write-IzBuildReceipt'
)
