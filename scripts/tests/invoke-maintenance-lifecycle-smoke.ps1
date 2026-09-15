[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$BaselineZip,
    [Parameter(Mandatory)][string]$OriginalBeta4Zip,
    [Parameter(Mandatory)][string]$CandidateZip,
    [Parameter(Mandatory)][string]$CandidatePackage,
    [Parameter(Mandatory)][string]$ValidationSummary,
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{40}$')][string]$ExpectedSourceRevision,
    [Parameter(Mandatory)][string]$EvidenceRoot,
    [Parameter(Mandatory)][ValidateSet('msedge','chrome')][string]$BrowserChannel
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$previousModuleCachePath = $env:PSModuleAnalysisCachePath
$moduleCachePath = $null
$receiptPath = $null
$exitCode = 1
$started = [DateTime]::UtcNow.ToString('o')
$productWriteAttempted = $false
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
try {
    $qaParent = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'IZ-CNA-QA'
    if (-not (Test-Path -LiteralPath $qaParent -PathType Container)) { throw 'QA_PARENT_INVALID' }
    $moduleCachePath = Join-Path $qaParent ('.iz-cna-validation-smoke-module-analysis-' + $PID + '-' + [Guid]::NewGuid().ToString('N') + '.cache')
    $env:PSModuleAnalysisCachePath = $moduleCachePath
    Import-Module (Join-Path $PSScriptRoot 'maintenance-harness-lifecycle.psm1') -Force
    Import-Module (Join-Path $PSScriptRoot 'maintenance-harness-contracts.psm1') -Force
    Import-Module (Join-Path $PSScriptRoot 'maintenance-harness-safety.psm1') -Force
    . (Join-Path $PSScriptRoot 'maintenance-fixture.ps1')

    $revision = (& git.exe -C $repositoryRoot rev-parse HEAD 2>$null).Trim()
    if ($LASTEXITCODE -ne 0 -or $revision -cne $ExpectedSourceRevision) { throw 'EXPECTED_SOURCE_REVISION_MISMATCH' }
    $baseline = Get-IzHarnessFileDescriptor -Path $BaselineZip
    $original = Get-IzHarnessFileDescriptor -Path $OriginalBeta4Zip
    if ($baseline.sha256 -cne '9c5fd47203242e1a21df612f719f1c14fa4240c86ba869f924ec4690834fc89c' -or
        $original.sha256 -cne '67b83eea402566658dea6d64ac6cba37a192a7d1bd670cf560541324c0092b14') {
        throw 'PRESERVED_ARCHIVE_HASH_MISMATCH'
    }
    $owned = Initialize-IzHarnessEvidenceRoot -Path $EvidenceRoot
    $publicRoot = Join-Path $repositoryRoot ".omo\evidence\windows-cmd-maintenance\$($owned.run_id)-validation-only"
    if (Test-Path -LiteralPath $publicRoot) { throw 'PUBLIC_EVIDENCE_ALREADY_EXISTS' }
    $null = New-Item -ItemType Directory -Path $publicRoot
    $receiptPath = Join-Path $publicRoot 'validation-lifecycle-receipt.json'
    $fixture = New-IzMaintenanceFixture -HarnessRoot $owned -CaseId V00 -ShortComponentRoot
    $binding = New-IzLifecycleCandidateBinding -QualificationMode ValidationOnly -CandidateZip $CandidateZip `
        -CandidatePackageRoot $CandidatePackage -ValidationSummary $ValidationSummary `
        -ExpectedSourceRevision $ExpectedSourceRevision
    $productWriteAttempted = $true
    $outcome = Invoke-IzComponentLifecycleSmoke -RepositoryRoot $repositoryRoot -Fixture $fixture `
        -PublicCaseRoot $publicRoot -BaselineZip $baseline.path -OriginalBeta4Zip $original.path `
        -Binding $binding -BrowserChannel $BrowserChannel -CaseId V00
    $artifacts = [Collections.Generic.List[object]]::new()
    $artifacts.Add((New-IzHarnessArtifact -Kind 'validation_lifecycle_smoke' -Path $outcome.artifact_path))
    if ($outcome.browser_artifact_path) {
        $artifacts.Add((New-IzHarnessArtifact -Kind 'validation_browser_smoke' -Path $outcome.browser_artifact_path))
    }
    $receipt = [ordered]@{
        schema = 'iz-cna-maintenance-validation-lifecycle-receipt-v1'
        qualification_mode = 'validation_only'; release_qualification = $false
        qualified_case_ids = @(); tier = 'Component'; status = [string]$outcome.status; reason = [string]$outcome.reason
        source_revision = $ExpectedSourceRevision
        inputs = [ordered]@{
            baseline_zip = [ordered]@{ length=[long]$baseline.length; sha256=[string]$baseline.sha256 }
            original_beta4_zip = [ordered]@{ length=[long]$original.length; sha256=[string]$original.sha256 }
            candidate_zip = [ordered]@{ length=[long]$binding.zip.length; sha256=[string]$binding.zip.sha256 }
            manifest_sha256 = [string]$binding.manifest_sha256
            payload_identity = [string]$binding.manifest.payload_identity
            validation_summary_sha256 = [string]$binding.validation_summary.sha256
        }
        execution = [ordered]@{
            actual_executable = [bool]$outcome.actual_executable; actual_http = [bool]$outcome.actual_http
            actual_browser = [bool]$outcome.actual_browser
            actual_installer = $false; actual_default_profile = $false; synthetic_data_only = $true
        }
        observable = [string]$outcome.observable
        artifacts = @($artifacts)
        cleanup = $outcome.cleanup
        started_utc = $started; completed_utc = [DateTime]::UtcNow.ToString('o')
    }
    $null = Write-IzHarnessJson -Path $receiptPath -Value $receipt
    $exitCode = if ($outcome.status -ceq 'passed') { 0 } else { 1 }
}
catch {
    $reason = if ($_.Exception.Data.Contains('iz_reason') -and
        [string]$_.Exception.Data['iz_reason'] -cmatch '^[A-Z][A-Z0-9_]{0,63}$') {
        [string]$_.Exception.Data['iz_reason']
    } elseif ($_.Exception.Message -cmatch '^[A-Z][A-Z0-9_]{0,63}$') { [string]$_.Exception.Message }
    else { 'VALIDATION_LIFECYCLE_ENTRYPOINT_FAILED' }
    if (-not $receiptPath) {
        $failureRoot = Join-Path $repositoryRoot ('.omo\evidence\windows-cmd-maintenance\validation-failure-' + [Guid]::NewGuid().ToString('N').Substring(0,12))
        $null = New-Item -ItemType Directory -Path $failureRoot
        $receiptPath = Join-Path $failureRoot 'validation-lifecycle-receipt.json'
    }
    $failure = [ordered]@{
        schema='iz-cna-maintenance-validation-lifecycle-terminal-failure-v1'
        qualification_mode='validation_only'; release_qualification=$false; qualified_case_ids=@()
        status='failed'; reason=$reason; source_revision=$ExpectedSourceRevision
        product_write_attempted=$productWriteAttempted; started_utc=$started; completed_utc=[DateTime]::UtcNow.ToString('o')
    }
    if (-not (Test-Path -LiteralPath $receiptPath)) {
        [IO.File]::WriteAllText($receiptPath, ($failure | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    }
    $exitCode = 1
}
finally {
    if ($null -eq $previousModuleCachePath) { Remove-Item Env:\PSModuleAnalysisCachePath -ErrorAction SilentlyContinue }
    else { $env:PSModuleAnalysisCachePath = $previousModuleCachePath }
    if ($moduleCachePath -and (Test-Path -LiteralPath $moduleCachePath -PathType Leaf)) {
        Remove-Item -LiteralPath $moduleCachePath -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "VALIDATION_LIFECYCLE_RECEIPT_PATH=$receiptPath"
exit $exitCode
