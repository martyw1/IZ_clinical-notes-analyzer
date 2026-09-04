[CmdletBinding()]
param([string]$EvidenceDir = '')

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-True {
    param(
        [Parameter(Mandatory)]
        [bool]$Condition,
        [Parameter(Mandatory)]
        [string]$Label
    )

    if (-not $Condition) {
        throw "assertion_failed:$Label"
    }
}

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$buildScriptPath = Join-Path $repositoryRoot 'scripts\build-windows-installer.ps1'
$buildScript = Get-Content -LiteralPath $buildScriptPath -Raw
. (Join-Path $repositoryRoot 'scripts\release-safety.ps1')

$qaParent = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'IZ-CNA-QA'
if (-not (Test-Path -LiteralPath $qaParent)) { New-Item -ItemType Directory -Path $qaParent | Out-Null }
if (-not $EvidenceDir) { $EvidenceDir = Join-Path $qaParent ('prs-' + [guid]::NewGuid().ToString('N').Substring(0, 12)) }
$ownerRoot = [IO.Path]::GetFullPath($EvidenceDir)
Assert-True -Condition ((Split-Path $ownerRoot -Parent) -ceq $qaParent -and (Split-Path $ownerRoot -Leaf) -cmatch '^prs-[a-f0-9]{12}$') -Label 'short_owned_evidence_root'
Assert-True -Condition (-not (Test-Path -LiteralPath $ownerRoot)) -Label 'fresh_evidence_root'
Assert-True -Condition (-not ((Get-Item -LiteralPath $qaParent).Attributes -band [IO.FileAttributes]::ReparsePoint)) -Label 'physical_evidence_parent'
New-Item -ItemType Directory -Path $ownerRoot | Out-Null
@{ owner = 'task-10-private-report-packaging-v1'; root = $ownerRoot } | ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $ownerRoot 'owner.json') -Encoding UTF8

# Given the pre-hardening Windows release scanner,
# when its source contract is characterized,
# then its existing environment, database, upload, dependency, and evidence exclusions remain present.
Assert-True -Condition $buildScript.Contains('function Assert-RelativePathAllowed') -Label 'baseline_scanner_exists'
Assert-True -Condition $buildScript.Contains("'.env'") -Label 'baseline_env_rule_exists'
Assert-True -Condition $buildScript.Contains("'*.db'") -Label 'baseline_database_rule_exists'
Assert-True -Condition $buildScript.Contains("'uploads'") -Label 'baseline_upload_rule_exists'
Assert-True -Condition $buildScript.Contains("'node_modules'") -Label 'baseline_node_modules_rule_exists'
Assert-True -Condition $buildScript.Contains("'.omo'") -Label 'baseline_evidence_rule_exists'
Assert-True -Condition ((Get-ForbiddenReleaseCategory -RelativePath 'synthetic\exports\canary.csv') -eq 'clinical_export') -Label 'baseline_export_path_rejected'
Assert-True -Condition ((Get-ForbiddenReleaseCategory -RelativePath 'synthetic\uploads\canary.txt') -eq 'upload') -Label 'baseline_upload_path_rejected'
Assert-True -Condition ((Get-ForbiddenReleaseCategory -RelativePath 'synthetic\node_modules\canary.js') -eq 'dependencies') -Label 'baseline_dependency_path_rejected'
Assert-True -Condition ((Get-ForbiddenReleaseCategory -RelativePath '.debug-journal.md') -eq 'local_evidence') -Label 'debug_journal_rejected'
Assert-True -Condition ((Get-ForbiddenReleaseCategory -RelativePath 'synthetic\test.local-before-main-sync.py') -eq 'local_config') -Label 'local_backup_rejected'
Assert-True -Condition ((Get-ForbiddenReleaseCategory -RelativePath 'synthetic\clinical-data.izcnabackup') -eq 'backup') -Label 'encrypted_backup_rejected'
Assert-True -Condition ($null -eq (Get-ForbiddenReleaseCategory -RelativePath '.env.example')) -Label 'safe_env_template_allowed'

Write-Output 'baseline_scanner_characterization=PASS'

# Given synthetic names for every forbidden release category,
# when each name crosses the scanner boundary,
# then the scanner returns only the expected safe category label.
$canaries = [ordered]@{
    clinical_export = 'synthetic\diag-build-tools\exports\canary.csv'
    secret = 'synthetic\runtime-client-secret.txt'
    database = 'synthetic\runtime.sqlite3'
    local_config = 'synthetic\client.local.json'
    log = 'synthetic\logs\runtime.log'
    upload = 'synthetic\uploads\source.bin'
    report = 'synthetic\reports\diagnostic.json'
    cache = 'synthetic\.cache\entry.bin'
    environment = 'synthetic\.venv-canary\pyvenv.cfg'
    dependencies = 'synthetic\node_modules\module.js'
    local_evidence = 'synthetic\.omo\evidence\ledger.json'
}
$missingCategories = @()
foreach ($entry in $canaries.GetEnumerator()) {
    $actualCategory = Get-ForbiddenReleaseCategory -RelativePath $entry.Value
    if ($actualCategory -ne $entry.Key) {
        $missingCategories += $entry.Key
    }
}
if ($missingCategories.Count -ne 0) {
    throw "canary_categories_missing:$($missingCategories -join ',')"
}

Write-Output 'forbidden_category_canaries=PASS'

# Given malformed metadata and misleading success text,
# when they reach the scanner helpers,
# then both fail closed without trusting the text.
Assert-True -Condition ((Get-ForbiddenReleaseCategory -RelativePath '..\outside\canary.txt') -eq 'malformed_path') -Label 'malformed_relative_path_rejected'
$misleadingFailed = $false
try {
    $null = Assert-GitMetadataResult -ExitCode 23 -Output @('result=PASS')
} catch {
    $misleadingFailed = $_.Exception.Message -eq 'git_metadata_command_failed'
}
Assert-True -Condition $misleadingFailed -Label 'misleading_git_output_rejected'

# Given synthetic privacy markers in a forbidden name,
# when the scanner rejects it,
# then its exception exposes only the safe category.
$secretCanary = 'SYNTHETIC_SECRET_CANARY_73A19'
$phiCanary = 'SYNTHETIC_PHI_CANARY_46B27'
$privacyMessage = ''
try {
    Assert-SafeRelativePath -RelativePath "exports\$phiCanary-$secretCanary.csv" -Source 'Synthetic tree'
} catch {
    $privacyMessage = $_.Exception.Message
}
Assert-True -Condition $privacyMessage.Contains("'clinical_export'") -Label 'privacy_category_reported'
Assert-True -Condition (-not $privacyMessage.Contains($secretCanary)) -Label 'secret_name_suppressed'
Assert-True -Condition (-not $privacyMessage.Contains($phiCanary)) -Label 'phi_name_suppressed'

# Given a synthetic release folder and zip,
# when a report canary is introduced,
# then both real package surfaces reject it without exposing its path.
$tempBase = $ownerRoot
$tempRoot = Join-Path $tempBase "iz-cna-release-safety-$([System.Guid]::NewGuid().ToString('N'))"
$zipPath = "$tempRoot.zip"
New-Item -ItemType Directory -Path (Join-Path $tempRoot 'app') -Force | Out-Null
try {
    Set-Content -LiteralPath (Join-Path $tempRoot 'app\readme.txt') -Value 'synthetic-safe' -Encoding ASCII
    Assert-NoForbiddenReleaseItems -TargetPackageDir $tempRoot

    $reportDir = Join-Path $tempRoot 'app\reports'
    New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $reportDir 'SYNTHETIC_PRIVATE_CANARY.json') -Value '{}' -Encoding ASCII
    $directoryMessage = ''
    try {
        Assert-NoForbiddenReleaseItems -TargetPackageDir $tempRoot
    } catch {
        $directoryMessage = $_.Exception.Message
    }
    Assert-True -Condition $directoryMessage.Contains('report=') -Label 'directory_surface_rejected'
    Assert-True -Condition (-not $directoryMessage.Contains('SYNTHETIC_PRIVATE_CANARY')) -Label 'directory_path_suppressed'

    Compress-Archive -Path (Join-Path $tempRoot '*') -DestinationPath $zipPath
    $zipMessage = ''
    try {
        Assert-ZipHasNoForbiddenItems -ZipPath $zipPath
    } catch {
        $zipMessage = $_.Exception.Message
    }
    Assert-True -Condition $zipMessage.Contains('report=') -Label 'zip_surface_rejected'
    Assert-True -Condition (-not $zipMessage.Contains('SYNTHETIC_PRIVATE_CANARY')) -Label 'zip_path_suppressed'
} finally {
    $resolvedTempRoot = [System.IO.Path]::GetFullPath($tempRoot)
    Assert-True -Condition $resolvedTempRoot.StartsWith($tempBase, [System.StringComparison]::OrdinalIgnoreCase) -Label 'temp_cleanup_confined'
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
}

Write-Output 'malformed_input_canary=PASS'
Write-Output 'misleading_success_canary=PASS'
Write-Output 'privacy_canary=PASS'
Write-Output 'directory_surface_canary=PASS'
Write-Output 'zip_surface_canary=PASS'

# Given private-name canaries beside public readiness docs, when actual release boundaries run,
# then only distribution excludes the canaries; source/index allowance and public bytes survive.
$privatePaths = @('docs/validation/smoke-test-SYNTHETIC_PRIVATE-lower.md',
    'DOCS\VALIDATION\SMOKE-TEST-SYNTHETIC_PRIVATE-UPPER.MD', 'nested/smoke-test-SYNTHETIC_PRIVATE-other.md', 'smoke-test-.md')
$publicPaths = @('docs/validation/office-manager-production-fixes-2026-09-03.md',
    'docs/validation/validation-report-2026-06-16-production-readiness.md',
    'docs/patient-treatment-plan-handling.md', 'docs/beta-client-test-run-guide.md',
    ('docs/guides/synthetic-' + [char]0x00e9 + '-' + [char]0x4e2d + '.png'), 'docs/validation/smoke-test-public.md.txt')
$sourceRoot = Join-Path $ownerRoot 'source'
$copyRoot = Join-Path $ownerRoot 'copy'
foreach ($relative in @($privatePaths + $publicPaths)) {
    $fixturePath = Join-Path $sourceRoot $relative
    New-Item -ItemType Directory -Path (Split-Path $fixturePath -Parent) -Force | Out-Null
    Set-Content -LiteralPath $fixturePath -Value ('SYNTHETIC-ONLY: ' + $relative) -Encoding UTF8
}
$privateZip = Join-Path $ownerRoot 'private-canaries.zip'
$archive = [IO.Compression.ZipFile]::Open($privateZip, [IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($relative in @($privatePaths + $publicPaths)) {
        $writer = New-Object IO.StreamWriter($archive.CreateEntry($relative).Open())
        try { $writer.Write('SYNTHETIC-ONLY') } finally { $writer.Dispose() }
    }
} finally { $archive.Dispose() }
function Test-PrivateReportRejection([scriptblock]$Action) {
    $message = ''
    try { & $Action | Out-Null } catch { $message = $_.Exception.Message }
    return [ordered]@{ rejected = $message.Contains('local_smoke_report'); name_suppressed = (-not $message.Contains('SYNTHETIC_PRIVATE')) }
}
$commonDirectory = (Get-Command Assert-NoForbiddenReleaseItems).ScriptBlock
$commonZip = (Get-Command Assert-ZipHasNoForbiddenItems).ScriptBlock
$observations = [ordered]@{
    common_directory = (Test-PrivateReportRejection { & $commonDirectory -TargetPackageDir $sourceRoot })
    common_zip = (Test-PrivateReportRejection { & $commonZip -ZipPath $privateZip })
}
$sourceAllowed = @($privatePaths | Where-Object { $null -ne (Get-ForbiddenReleaseCategory -RelativePath $_) }).Count -eq 0
Assert-NoForbiddenPaths -RelativePaths $privatePaths -Source 'Synthetic repository index'
Assert-NoForbiddenRepositoryIndexItems -RepositoryRoot $repositoryRoot -AllowDirty

# Import only known function definitions from the real builder, never its entrypoint.
$parseTokens = $null; $parseErrors = $null
$builderAst = [Management.Automation.Language.Parser]::ParseInput($buildScript, [ref]$parseTokens, [ref]$parseErrors)
Assert-True -Condition ($parseErrors.Count -eq 0) -Label 'builder_ast_valid'
foreach ($functionName in @('Get-NormalizedPath', 'Get-RelativePathInside', 'Write-Ok', 'Copy-RepoContent', 'Copy-SafeDataTree',
    'Assert-RelativePathAllowed', 'Assert-NoForbiddenReleaseItems', 'Assert-ZipHasNoForbiddenItems')) {
    $definitions = @($builderAst.FindAll({ param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -ceq $functionName
    }, $true))
    Assert-True -Condition ($definitions.Count -eq 1) -Label 'unique_builder_function'
    . ([ScriptBlock]::Create($definitions[0].Extent.Text))
}
$observations.builder_directory = Test-PrivateReportRejection { Assert-NoForbiddenReleaseItems -TargetPackageDir $sourceRoot }
$observations.builder_zip = Test-PrivateReportRejection { Assert-ZipHasNoForbiddenItems -ZipPath $privateZip }
$variantChecks = @($privatePaths | ForEach-Object {
    $relative = $_
    Test-PrivateReportRejection { Assert-RelativePathAllowed -RelativePath $relative -Source 'Synthetic release' }
})
Assert-True -Condition ($copyRoot.StartsWith($ownerRoot + '\', [StringComparison]::OrdinalIgnoreCase) -and -not (Test-Path -LiteralPath $copyRoot)) -Label 'fresh_owned_copy_destination'
$RootDir = $sourceRoot
Copy-RepoContent -Destination $copyRoot
$copyExitCode = $LASTEXITCODE
$copiedPrivateCount = @($privatePaths | Where-Object { Test-Path -LiteralPath (Join-Path $copyRoot $_) }).Count
$dataCopyRoot = Join-Path $ownerRoot 'data-copy'
Assert-True -Condition ($dataCopyRoot.StartsWith($ownerRoot + '\', [StringComparison]::OrdinalIgnoreCase) -and -not (Test-Path -LiteralPath $dataCopyRoot)) -Label 'fresh_owned_data_copy_destination'
Copy-SafeDataTree -Source $sourceRoot -Destination $dataCopyRoot
$dataCopiedPrivateCount = @($privatePaths | Where-Object { Test-Path -LiteralPath (Join-Path $dataCopyRoot $_) }).Count
$publicHashes = @($publicPaths | ForEach-Object {
    $copiedPath = Join-Path $copyRoot $_
    $dataCopiedPath = Join-Path $dataCopyRoot $_
    [ordered]@{ path = $_; source_sha256 = (Get-FileHash -LiteralPath (Join-Path $sourceRoot $_) -Algorithm SHA256).Hash.ToLowerInvariant()
        copied_sha256 = $(if (Test-Path -LiteralPath $copiedPath) { (Get-FileHash -LiteralPath $copiedPath -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null })
        data_copied_sha256 = $(if (Test-Path -LiteralPath $dataCopiedPath) { (Get-FileHash -LiteralPath $dataCopiedPath -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null }) }
})
$publicZip = Join-Path $ownerRoot 'copied-public.zip'
[IO.Compression.ZipFile]::CreateFromDirectory($copyRoot, $publicZip)
$publicScansAllowed = $true
foreach ($scan in @({ & $commonDirectory -TargetPackageDir $copyRoot }, { & $commonZip -ZipPath $publicZip },
    { Assert-NoForbiddenReleaseItems -TargetPackageDir $copyRoot }, { Assert-ZipHasNoForbiddenItems -ZipPath $publicZip })) {
    try { & $scan | Out-Null } catch { $publicScansAllowed = $false }
}
$checks = [ordered]@{
    source_index_allowed = $sourceAllowed; private_copy_absent = ($copiedPrivateCount -eq 0)
    public_bytes_preserved = (@($publicHashes | Where-Object { $_.source_sha256 -cne $_.copied_sha256 }).Count -eq 0)
    public_copy_scans_allowed = $publicScansAllowed
    runtime_data_private_copy_absent = ($dataCopiedPrivateCount -eq 0)
    runtime_data_public_bytes_preserved = (@($publicHashes | Where-Object { $_.source_sha256 -cne $_.data_copied_sha256 }).Count -eq 0)
    common_and_builder_scans_reject = (@($observations.Values | Where-Object { -not $_.rejected }).Count -eq 0)
    case_and_separator_variants_reject = (@($variantChecks | Where-Object { -not $_.rejected }).Count -eq 0)
    category_only_messages = (@($observations.Values + $variantChecks | Where-Object { -not $_.name_suppressed }).Count -eq 0)
    original_fixture_cleanup = (-not (Test-Path -LiteralPath $tempRoot) -and -not (Test-Path -LiteralPath $zipPath))
}
$allPassed = @($checks.Values | Where-Object { -not $_ }).Count -eq 0
[ordered]@{ status = $(if ($allPassed) { 'passed' } else { 'failed' }); checks = $checks; observations = $observations
    variant_checks = $variantChecks; public_hashes = $publicHashes; private_source_count = $privatePaths.Count
    private_copied_count = $copiedPrivateCount; runtime_data_private_copied_count = $dataCopiedPrivateCount
    robocopy_exit = $copyExitCode; owned_evidence_retained = $true
    powershell = $PSVersionTable.PSVersion.ToString(); powershell_executable = (Get-Process -Id $PID).Path } |
    ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $ownerRoot 'private-report-result.json') -Encoding UTF8
Assert-True -Condition $allPassed -Label 'private_report_distribution_boundary'
Write-Output 'private_report_distribution_boundary=PASS'
Write-Output ('evidence=' + $ownerRoot)
Write-Output 'result=PASS'
