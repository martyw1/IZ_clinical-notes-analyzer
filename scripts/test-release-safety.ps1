[CmdletBinding()]
param()

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
$tempBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
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
Write-Output 'result=PASS'
