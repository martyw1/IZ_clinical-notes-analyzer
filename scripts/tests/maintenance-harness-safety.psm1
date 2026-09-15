Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:ProductId = 'r3.iz-clinical-notes-analyzer.desktop'
$script:HarnessMarkerKeys = @('schema', 'product_id', 'owner_sid', 'run_id', 'root_path_hash', 'created_utc')
$script:BuildReceiptKeys = @(
    'schema', 'product_id', 'version', 'build', 'installer_revision', 'source_revision',
    'package_directory', 'zip_path', 'zip_length', 'zip_sha256', 'manifest_sha256',
    'payload_identity', 'gates', 'created_utc'
)
$script:BuildGateKeys = @('name', 'status', 'command', 'exit_code', 'evidence')
$script:BuildGateNames = @(
    'backend_tests', 'frontend_tests', 'frontend_build', 'repository_safety',
    'directory_safety', 'zip_safety', 'frozen_bundle_inspection'
)

function New-IzHarnessSafetyError {
    param([string]$Reason)
    $exception = [IO.InvalidDataException]::new($Reason)
    $exception.Data['iz_reason'] = $Reason
    return $exception
}

function Assert-IzSafetyExactKeys {
    param([object]$Value, [string[]]$Expected, [string]$Reason)
    if ($null -eq $Value -or
        @(Compare-Object @($Value.PSObject.Properties.Name | Sort-Object) @($Expected | Sort-Object)).Count -ne 0) {
        throw (New-IzHarnessSafetyError $Reason)
    }
}

function Get-IzHarnessCurrentSid {
    return [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
}

function Get-IzHarnessSha256 {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw (New-IzHarnessSafetyError 'FILE_REQUIRED')
    }
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Get-IzHarnessTextSha256 {
    param([Parameter(Mandatory)][string]$Text)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
        return ([BitConverter]::ToString($algorithm.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    }
    finally { $algorithm.Dispose() }
}

function Assert-IzSafeLocalPath {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Purpose)
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path.StartsWith('\\') -or
        $Path.StartsWith('//') -or $Path.StartsWith('\\?\') -or $Path.StartsWith('\\.\') -or
        $Path -cnotmatch '^[A-Za-z]:[\\/]') {
        throw (New-IzHarnessSafetyError 'LOCAL_DRIVE_PATH_REQUIRED')
    }
    if ($Path.Substring(2) -match ':') { throw (New-IzHarnessSafetyError 'ALTERNATE_DATA_STREAM_REFUSED') }
    if (@($Path -split '[\\/]' | Where-Object { $_ -in @('.', '..') }).Count -gt 0) {
        throw (New-IzHarnessSafetyError 'PATH_TRAVERSAL_REFUSED')
    }
    try { $fullPath = [IO.Path]::GetFullPath($Path) }
    catch { throw (New-IzHarnessSafetyError 'INVALID_LOCAL_PATH') }
    $root = [IO.Path]::GetPathRoot($fullPath)
    if ($fullPath.TrimEnd('\').Equals($root.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) {
        throw (New-IzHarnessSafetyError 'DRIVE_ROOT_REFUSED')
    }
    return $fullPath
}

function Assert-IzNoReparseAncestors {
    param([Parameter(Mandatory)][string]$Path)
    $fullPath = [IO.Path]::GetFullPath($Path)
    $cursor = $fullPath
    while ($cursor -and -not (Test-Path -LiteralPath $cursor)) { $cursor = Split-Path -Parent $cursor }
    while ($cursor) {
        $item = Get-Item -LiteralPath $cursor -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw (New-IzHarnessSafetyError 'REPARSE_PATH_REFUSED')
        }
        $parent = Split-Path -Parent $cursor
        if (-not $parent -or $parent -eq $cursor) { break }
        $cursor = $parent
    }
}

function Get-IzHarnessPathHash {
    param([Parameter(Mandatory)][string]$Path)
    $canonical = [IO.Path]::GetFullPath($Path).TrimEnd('\').Normalize([Text.NormalizationForm]::FormC)
    $builder = [Text.StringBuilder]::new()
    foreach ($character in $canonical.ToCharArray()) {
        if ($character -ge 'A' -and $character -le 'Z') { $null = $builder.Append([char]([int]$character + 32)) }
        else { $null = $builder.Append($character) }
    }
    return Get-IzHarnessTextSha256 -Text $builder.ToString()
}

function Initialize-IzHarnessEvidenceRoot {
    param([Parameter(Mandatory)][string]$Path)
    $qaParent = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'IZ-CNA-QA'
    $fullPath = Assert-IzSafeLocalPath -Path $Path -Purpose evidence
    if ((Split-Path $fullPath -Parent) -cne $qaParent -or
        (Split-Path $fullPath -Leaf) -cnotmatch '^cmd-[a-f0-9]{12}$') {
        throw (New-IzHarnessSafetyError 'INVALID_EVIDENCE_ROOT_NAME')
    }
    if (-not (Test-Path -LiteralPath $qaParent -PathType Container)) {
        throw (New-IzHarnessSafetyError 'QA_PARENT_MISSING')
    }
    Assert-IzNoReparseAncestors -Path $fullPath
    $markerPath = Join-Path $fullPath '.iz-cna-harness-owned.json'
    if (Test-Path -LiteralPath $fullPath) {
        if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
            throw (New-IzHarnessSafetyError 'UNOWNED_EXISTING_ROOT')
        }
        return Test-IzHarnessEvidenceRoot -Path $fullPath
    }
    $null = New-Item -ItemType Directory -Path $fullPath
    $marker = [ordered]@{
        schema = 'iz-cna-maintenance-harness-root-v1'
        product_id = $script:ProductId
        owner_sid = Get-IzHarnessCurrentSid
        run_id = Split-Path $fullPath -Leaf
        root_path_hash = Get-IzHarnessPathHash -Path $fullPath
        created_utc = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText($markerPath, ($marker | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    return Test-IzHarnessEvidenceRoot -Path $fullPath
}

function Test-IzHarnessEvidenceRoot {
    param([Parameter(Mandatory)][string]$Path)
    $fullPath = Assert-IzSafeLocalPath -Path $Path -Purpose evidence
    Assert-IzNoReparseAncestors -Path $fullPath
    $markerPath = Join-Path $fullPath '.iz-cna-harness-owned.json'
    if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
        throw (New-IzHarnessSafetyError 'HARNESS_MARKER_MISSING')
    }
    try { $marker = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json }
    catch { throw (New-IzHarnessSafetyError 'HARNESS_MARKER_INVALID') }
    Assert-IzSafetyExactKeys $marker $script:HarnessMarkerKeys 'HARNESS_MARKER_INVALID'
    if ($marker.schema -cne 'iz-cna-maintenance-harness-root-v1' -or
        $marker.product_id -cne $script:ProductId -or
        $marker.owner_sid -cne (Get-IzHarnessCurrentSid) -or
        $marker.run_id -cne (Split-Path $fullPath -Leaf) -or
        $marker.root_path_hash -cne (Get-IzHarnessPathHash -Path $fullPath)) {
        throw (New-IzHarnessSafetyError 'HARNESS_MARKER_MISMATCH')
    }
    return [pscustomobject][ordered]@{
        path = $fullPath; marker_path = $markerPath; run_id = $marker.run_id; owner_sid = $marker.owner_sid
    }
}

function Assert-IzSyntheticProductRootsUnowned {
    param([Parameter(Mandatory)][string]$InstallRoot, [Parameter(Mandatory)][string]$DataRoot)
    foreach ($root in @($InstallRoot, $DataRoot)) {
        $fullPath = Assert-IzSafeLocalPath -Path $root -Purpose product
        Assert-IzNoReparseAncestors -Path $fullPath
        if (Test-Path -LiteralPath $fullPath) {
            $marker = Join-Path $fullPath '.iz-cna-owned-root.json'
            if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) {
                throw (New-IzHarnessSafetyError 'UNOWNED_EXISTING_APP')
            }
        }
    }
    return $true
}

function Test-IzHarnessZip {
    param([Parameter(Mandatory)][string]$Path)
    $fullPath = Assert-IzSafeLocalPath -Path $Path -Purpose archive
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        throw (New-IzHarnessSafetyError 'ZIP_REQUIRED')
    }
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($fullPath)
    try {
        $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        [long]$declaredLength = 0
        foreach ($entry in $zip.Entries) {
            $name = $entry.FullName
            $member = $name.TrimEnd('/')
            $segments = @($member -split '/')
            if ([string]::IsNullOrWhiteSpace($member) -or $name.StartsWith('/') -or $name.Contains('\') -or
                $name -match '^[A-Za-z]:' -or $name -match ':' -or
                @($segments | Where-Object { $_ -in @('', '.', '..') }).Count -gt 0 -or
                -not $seen.Add($member)) {
                throw (New-IzHarnessSafetyError 'UNSAFE_ZIP_MEMBER')
            }
            foreach ($segment in $segments) {
                $leaf = $segment.TrimEnd('. ').Split('.')[0]
                if ($leaf -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$') {
                    throw (New-IzHarnessSafetyError 'UNSAFE_ZIP_MEMBER')
                }
            }
            $declaredLength += [long]$entry.Length
            if ($declaredLength -gt 20GB) { throw (New-IzHarnessSafetyError 'ZIP_DECLARED_SIZE_EXCEEDED') }
        }
        if ($zip.Entries.Count -eq 0) { throw (New-IzHarnessSafetyError 'ZIP_EMPTY') }
        return $true
    }
    finally { $zip.Dispose() }
}

function Get-IzHarnessFileDescriptor {
    param([Parameter(Mandatory)][string]$Path)
    $fullPath = Assert-IzSafeLocalPath -Path $Path -Purpose input
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        throw (New-IzHarnessSafetyError 'INPUT_FILE_MISSING')
    }
    $item = Get-Item -LiteralPath $fullPath
    return [pscustomobject][ordered]@{
        path = $fullPath; length = [long]$item.Length; sha256 = Get-IzHarnessSha256 -Path $fullPath
    }
}

function Read-IzHarnessBuildReceipt {
    param(
        [Parameter(Mandatory)][string]$CandidateZip,
        [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{40}$')][string]$ExpectedSourceRevision,
        [string]$CandidateBuildReceipt = ''
    )
    $zipPath = Assert-IzSafeLocalPath -Path $CandidateZip -Purpose candidate
    if (-not (Test-Path -LiteralPath $zipPath -PathType Leaf)) {
        throw (New-IzHarnessSafetyError 'CANDIDATE_ZIP_MISSING')
    }
    $derivedReceiptPath = [IO.Path]::ChangeExtension($zipPath, $null) + '.build-receipt.json'
    $receiptPath = if ($CandidateBuildReceipt) {
        $suppliedReceiptPath = Assert-IzSafeLocalPath -Path $CandidateBuildReceipt -Purpose build_receipt
        if (-not $suppliedReceiptPath.Equals($derivedReceiptPath, [StringComparison]::OrdinalIgnoreCase)) {
            throw (New-IzHarnessSafetyError 'BUILD_RECEIPT_PATH_MISMATCH')
        }
        $suppliedReceiptPath
    }
    else { $derivedReceiptPath }
    if (-not (Test-Path -LiteralPath $receiptPath -PathType Leaf)) {
        throw (New-IzHarnessSafetyError 'BUILD_RECEIPT_MISSING')
    }
    try { $receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json }
    catch { throw (New-IzHarnessSafetyError 'BUILD_RECEIPT_INVALID') }
    Assert-IzSafetyExactKeys $receipt $script:BuildReceiptKeys 'BUILD_RECEIPT_KEYS_INVALID'
    if ($receipt.schema -cne 'iz-cna-build-receipt-v1' -or $receipt.product_id -cne $script:ProductId -or
        $receipt.version -cne '2.0.0-beta.4' -or $receipt.build -cnotmatch '^20[0-9]{2}\.[0-9]{2}\.[0-9]{2}\.[0-9]+$' -or
        $receipt.installer_revision -ne 1 -or $receipt.source_revision -cne $ExpectedSourceRevision -or
        $receipt.manifest_sha256 -cnotmatch '^[a-f0-9]{64}$' -or $receipt.payload_identity -cnotmatch '^[a-f0-9]{64}$') {
        throw (New-IzHarnessSafetyError 'BUILD_RECEIPT_VALUE_INVALID')
    }
    $receiptZip = Assert-IzSafeLocalPath -Path $receipt.zip_path -Purpose candidate
    $packageDirectory = Assert-IzSafeLocalPath -Path $receipt.package_directory -Purpose package
    $expectedLeaf = "IZ-Clinical-Notes-Analyzer-v2.0.0-beta.4-build-$($receipt.build)-installer-r1.zip"
    $expectedPackageLeaf = [IO.Path]::GetFileNameWithoutExtension($expectedLeaf)
    if (-not $receiptZip.Equals($zipPath, [StringComparison]::OrdinalIgnoreCase) -or
        [IO.Path]::GetFileName($zipPath) -cne $expectedLeaf -or
        [IO.Path]::GetFileName($packageDirectory) -cne $expectedPackageLeaf -or
        -not (Test-Path -LiteralPath $packageDirectory -PathType Container)) {
        throw (New-IzHarnessSafetyError 'BUILD_RECEIPT_PATH_MISMATCH')
    }
    $zipItem = Get-Item -LiteralPath $zipPath
    if ($receipt.zip_length -ne $zipItem.Length -or
        $receipt.zip_sha256 -cne (Get-IzHarnessSha256 -Path $zipPath)) {
        throw (New-IzHarnessSafetyError 'BUILD_RECEIPT_ZIP_MISMATCH')
    }
    $gates = @($receipt.gates)
    if ($gates.Count -ne $script:BuildGateNames.Count -or
        @(Compare-Object @($gates.name | Sort-Object) @($script:BuildGateNames | Sort-Object)).Count -ne 0) {
        throw (New-IzHarnessSafetyError 'BUILD_GATE_SET_MISMATCH')
    }
    foreach ($gate in $gates) {
        Assert-IzSafetyExactKeys $gate $script:BuildGateKeys 'BUILD_GATE_KEYS_INVALID'
        if ($gate.status -cne 'passed' -or $gate.exit_code -ne 0 -or [string]::IsNullOrWhiteSpace($gate.command) -or
            [string]$gate.command -match '(?i)(^|\s)(-Skip\S*|skipped|not[ -]run)(\s|$)' -or
            [string]::IsNullOrWhiteSpace($gate.evidence) -or [IO.Path]::IsPathRooted($gate.evidence) -or
            @($gate.evidence -split '[\\/]' | Where-Object { $_ -in @('.', '..') }).Count -gt 0) {
            throw (New-IzHarnessSafetyError 'BUILD_GATE_VALUE_INVALID')
        }
        $gatePath = Join-Path (Split-Path $receiptPath -Parent) $gate.evidence
        if (-not (Test-Path -LiteralPath $gatePath -PathType Leaf) -or (Get-Item -LiteralPath $gatePath).Length -le 0) {
            throw (New-IzHarnessSafetyError 'BUILD_GATE_EVIDENCE_MISSING')
        }
    }
    $manifestPath = Join-Path $packageDirectory 'release-manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf) -or
        (Get-IzHarnessSha256 -Path $manifestPath) -cne [string]$receipt.manifest_sha256) {
        throw (New-IzHarnessSafetyError 'BUILD_RECEIPT_MANIFEST_MISMATCH')
    }
    try { $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json }
    catch { throw (New-IzHarnessSafetyError 'BUILD_RECEIPT_MANIFEST_MISMATCH') }
    if ($manifest.schema -cne 'iz-cna-release-manifest-v1' -or $manifest.product_id -cne $script:ProductId -or
        $manifest.version -cne $receipt.version -or $manifest.build -cne $receipt.build -or
        [int]$manifest.installer_revision -ne [int]$receipt.installer_revision -or
        $manifest.payload_identity -cne $receipt.payload_identity) {
        throw (New-IzHarnessSafetyError 'BUILD_RECEIPT_MANIFEST_MISMATCH')
    }
    $gateEvidence = Join-Path (Split-Path $receiptPath -Parent) ([string]$gates[0].evidence)
    try { $gateDocument = Get-Content -LiteralPath $gateEvidence -Raw | ConvertFrom-Json }
    catch { throw (New-IzHarnessSafetyError 'BUILD_GATE_EVIDENCE_INVALID') }
    if ($gateDocument.schema -cne 'iz-cna-build-gate-evidence-v1' -or
        $gateDocument.product_id -cne $script:ProductId -or $gateDocument.source_revision -cne $receipt.source_revision -or
        $gateDocument.version -cne $receipt.version -or $gateDocument.build -cne $receipt.build -or
        [int]$gateDocument.installer_revision -ne [int]$receipt.installer_revision -or $gateDocument.release_ready -ne $true) {
        throw (New-IzHarnessSafetyError 'BUILD_GATE_EVIDENCE_INVALID')
    }
    foreach ($gateName in $script:BuildGateNames) {
        if ($null -eq $gateDocument.$gateName -or [string]$gateDocument.$gateName.status -cne 'passed') {
            throw (New-IzHarnessSafetyError 'BUILD_GATE_EVIDENCE_INVALID')
        }
    }
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
        $embedded = @($zip.Entries | Where-Object FullName -ceq 'release-manifest.json')
        if ($embedded.Count -ne 1) { throw (New-IzHarnessSafetyError 'BUILD_RECEIPT_MANIFEST_MISMATCH') }
        $stream = $embedded[0].Open()
        $algorithm = [Security.Cryptography.SHA256]::Create()
        try {
            $embeddedHash = ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-', '').ToLowerInvariant()
        }
        finally { $algorithm.Dispose(); $stream.Dispose() }
        if ($embeddedHash -cne [string]$receipt.manifest_sha256) {
            throw (New-IzHarnessSafetyError 'BUILD_RECEIPT_MANIFEST_MISMATCH')
        }
    }
    finally { $zip.Dispose() }
    $null = Test-IzHarnessZip -Path $zipPath
    return [pscustomobject][ordered]@{
        path = $receiptPath
        length = (Get-Item -LiteralPath $receiptPath).Length
        sha256 = Get-IzHarnessSha256 -Path $receiptPath
        receipt = $receipt
    }
}

function Test-IzPackageTierEnvironment {
    param([Parameter(Mandatory)][ValidateSet('Package', 'Home')][string]$Tier)
    $qaParent = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'IZ-CNA-QA'
    $profileMarkerPath = Join-Path $qaParent '.iz-cna-disposable-profile.json'
    if (-not (Test-Path -LiteralPath $profileMarkerPath -PathType Leaf)) {
        throw (New-IzHarnessSafetyError 'DISPOSABLE_PROFILE_NOT_PROVISIONED')
    }
    try { $profileMarker = Get-Content -LiteralPath $profileMarkerPath -Raw | ConvertFrom-Json }
    catch { throw (New-IzHarnessSafetyError 'DISPOSABLE_PROFILE_MARKER_INVALID') }
    Assert-IzSafetyExactKeys $profileMarker @('schema', 'owner_sid', 'profile_path_hash', 'purpose', 'created_utc') 'DISPOSABLE_PROFILE_MARKER_INVALID'
    $profilePath = [Environment]::GetFolderPath('UserProfile')
    if ($profileMarker.schema -cne 'iz-cna-disposable-profile-v1' -or
        $profileMarker.owner_sid -cne (Get-IzHarnessCurrentSid) -or
        $profileMarker.profile_path_hash -cne (Get-IzHarnessPathHash -Path $profilePath) -or
        $profileMarker.purpose -cne 'iz-cna-package-lifecycle-qa') {
        throw (New-IzHarnessSafetyError 'DISPOSABLE_PROFILE_MARKER_MISMATCH')
    }
    $principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw (New-IzHarnessSafetyError 'STANDARD_USER_REQUIRED')
    }
    if ($Tier -ceq 'Home') {
        $os = Get-CimInstance Win32_OperatingSystem
        if ($os.Caption -notmatch 'Windows (10|11) Home') {
            throw (New-IzHarnessSafetyError 'WINDOWS_HOME_REQUIRED')
        }
        foreach ($command in @('python.exe', 'node.exe', 'git.exe', 'docker.exe', 'psql.exe')) {
            if (Get-Command $command -ErrorAction SilentlyContinue) {
                throw (New-IzHarnessSafetyError 'PRISTINE_HOME_IMAGE_REQUIRED')
            }
        }
    }
    return $true
}

Export-ModuleMember -Function @(
    'Get-IzHarnessCurrentSid', 'Get-IzHarnessSha256', 'Assert-IzSafeLocalPath',
    'Initialize-IzHarnessEvidenceRoot', 'Test-IzHarnessEvidenceRoot',
    'Assert-IzSyntheticProductRootsUnowned', 'Test-IzHarnessZip',
    'Get-IzHarnessFileDescriptor', 'Read-IzHarnessBuildReceipt', 'Test-IzPackageTierEnvironment'
)
