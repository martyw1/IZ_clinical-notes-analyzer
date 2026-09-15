[CmdletBinding()]
param(
    [string]$EvidenceRoot = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$qaParent = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'IZ-CNA-QA'
if (-not (Test-Path -LiteralPath $qaParent)) { $null = New-Item -ItemType Directory -Path $qaParent }
$moduleCachePath = Join-Path $qaParent ('.iz-cna-harness-test-module-analysis-' + $PID + '.cache')
$env:PSModuleAnalysisCachePath = $moduleCachePath
Import-Module (Join-Path $PSScriptRoot 'maintenance-harness-runner.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'maintenance-harness-contracts.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'maintenance-harness-safety.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'maintenance-harness-external.psm1') -Force

function Assert-True {
    param([bool]$Condition, [string]$Label)
    if (-not $Condition) { throw "ASSERTION_FAILED_$Label" }
}

function Assert-Reason {
    param([scriptblock]$Action, [string]$Reason)
    $observed = ''
    try { & $Action }
    catch { $observed = [string]$_.Exception.Data['iz_reason'] }
    Assert-True ($observed -ceq $Reason) "REASON_$Reason"
}

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $EvidenceRoot) {
    $EvidenceRoot = Join-Path $qaParent ('cmd-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
}
$resultRoot = Join-Path $repositoryRoot '.omo\evidence\windows-cmd-maintenance\harness-tests'
if (-not (Test-Path -LiteralPath $resultRoot)) { $null = New-Item -ItemType Directory -Path $resultRoot -Force }

$assertionCount = 0
function Pass-Assertion { $script:assertionCount += 1 }

# Given the frozen smoke matrix, when its catalog is loaded, then every exact ID and tier is retained.
$catalog = @(Get-IzMaintenanceCaseCatalog)
Assert-True ($catalog.Count -eq 63) 'CATALOG_COUNT'; Pass-Assertion
$expectedIds = @('B01', 'B02', 'B03') +
    @(1..10 | ForEach-Object { 'I{0:d2}' -f $_ }) +
    @(1..13 | ForEach-Object { 'U{0:d2}' -f $_ }) +
    @(1..10 | ForEach-Object { 'R{0:d2}' -f $_ }) +
    @(1..11 | ForEach-Object { 'D{0:d2}' -f $_ }) +
    @(1..8 | ForEach-Object { 'A{0:d2}' -f $_ }) +
    @(1..8 | ForEach-Object { 'P{0:d2}' -f $_ })
Assert-True (@(Compare-Object $expectedIds @($catalog.id)).Count -eq 0) 'CATALOG_IDS'; Pass-Assertion
Assert-True (@($catalog | Where-Object { $_.tiers -contains 'Component' }).Count -eq 13) 'COMPONENT_COUNT'; Pass-Assertion
Assert-True (@($catalog | Where-Object { $_.tiers -contains 'Package' }).Count -eq 54) 'PACKAGE_COUNT'; Pass-Assertion
Assert-True (@($catalog | Where-Object { $_.tiers -contains 'Home' }).Count -eq 12) 'HOME_COUNT'; Pass-Assertion
Assert-True (@($catalog | Where-Object { $_.tiers -contains 'PowerLoss' }).Count -eq 1) 'POWERLOSS_COUNT'; Pass-Assertion
foreach ($tier in @('Component', 'Package', 'Home', 'PowerLoss')) {
    $selection = @(Get-IzMaintenanceCaseSelection -Case All -Tier $tier)
    $expected = @($catalog | Where-Object { $_.tiers -contains $tier })
    Assert-True (@(Compare-Object @($expected.id) @($selection.id)).Count -eq 0) "ALL_$($tier.ToUpperInvariant())"
    Pass-Assertion
}
Assert-Reason { Get-IzMaintenanceCaseSelection -Case B02 -Tier Component } 'CASE_TIER_MISMATCH'; Pass-Assertion
Assert-Reason { Get-IzMaintenanceCaseSelection -Case X99 -Tier Component } 'UNKNOWN_CASE_ID'; Pass-Assertion

# Given a fresh owned QA path, when initialized, then a typed marker binds it to this SID and path.
$owned = Initialize-IzHarnessEvidenceRoot -Path $EvidenceRoot
Assert-True (Test-Path -LiteralPath $owned.marker_path -PathType Leaf) 'OWNED_MARKER'; Pass-Assertion
$verified = Test-IzHarnessEvidenceRoot -Path $EvidenceRoot
Assert-True ($verified.run_id -ceq (Split-Path $EvidenceRoot -Leaf)) 'OWNED_RUN_ID'; Pass-Assertion
Assert-True ($verified.owner_sid -ceq (Get-IzHarnessCurrentSid)) 'OWNED_SID'; Pass-Assertion

# Given an existing unowned root and unsafe paths, when the guard runs, then no marker or product write appears.
$unowned = Join-Path $qaParent ('cmd-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
$null = New-Item -ItemType Directory -Path $unowned
$canary = Join-Path $unowned 'unowned-canary.txt'
[IO.File]::WriteAllText($canary, 'SYNTHETIC-UNOWNED-CANARY')
Assert-Reason { Initialize-IzHarnessEvidenceRoot -Path $unowned } 'UNOWNED_EXISTING_ROOT'; Pass-Assertion
Assert-True (([IO.File]::ReadAllText($canary)) -ceq 'SYNTHETIC-UNOWNED-CANARY') 'UNOWNED_CANARY'; Pass-Assertion
Assert-True (-not (Test-Path -LiteralPath (Join-Path $unowned '.iz-cna-harness-owned.json'))) 'UNOWNED_NO_MARKER'; Pass-Assertion
Assert-Reason { Initialize-IzHarnessEvidenceRoot -Path (Join-Path $qaParent '..\escape') } 'PATH_TRAVERSAL_REFUSED'; Pass-Assertion
Assert-Reason { Assert-IzSafeLocalPath -Path '\\server\share\qa' -Purpose evidence } 'LOCAL_DRIVE_PATH_REQUIRED'; Pass-Assertion
Assert-Reason { Assert-IzSafeLocalPath -Path 'C:\qa\file.txt:stream' -Purpose evidence } 'ALTERNATE_DATA_STREAM_REFUSED'; Pass-Assertion

# Given an unowned synthetic App root, when the product-target guard runs, then it fails before changing the canary.
$componentProfile = Join-Path $EvidenceRoot 'synthetic-profile'
$unownedInstall = Join-Path $componentProfile 'AppData\Local\Programs\IZ Clinical Notes Analyzer'
$unownedData = Join-Path $componentProfile 'AppData\Local\IZ Clinical Notes Analyzer'
$null = New-Item -ItemType Directory -Path $unownedInstall -Force
$null = New-Item -ItemType Directory -Path $unownedData -Force
$productCanary = Join-Path $unownedInstall 'existing-app-canary.bin'
[IO.File]::WriteAllBytes($productCanary, [byte[]](1, 3, 3, 7))
Assert-Reason {
    Assert-IzSyntheticProductRootsUnowned -InstallRoot $unownedInstall -DataRoot $unownedData
} 'UNOWNED_EXISTING_APP'; Pass-Assertion
Assert-True ((Get-IzHarnessSha256 -Path $productCanary) -ceq 'acb86a9cb70a84f695de89e7fe22819466205759d798d52d4a3dd95b0cdaa2a1') 'PRODUCT_CANARY'; Pass-Assertion

# Given malformed ZIP members, when archive validation runs, then extraction is never attempted.
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$unsafeZip = Join-Path $EvidenceRoot 'unsafe.zip'
$stream = [IO.File]::Open($unsafeZip, [IO.FileMode]::CreateNew, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
$archive = [IO.Compression.ZipArchive]::new($stream, [IO.Compression.ZipArchiveMode]::Create)
try {
    $writer = [IO.StreamWriter]::new($archive.CreateEntry('../outside.txt').Open())
    try { $writer.Write('synthetic') } finally { $writer.Dispose() }
}
finally { $archive.Dispose(); $stream.Dispose() }
Assert-Reason { Test-IzHarnessZip -Path $unsafeZip } 'UNSAFE_ZIP_MEMBER'; Pass-Assertion
Assert-True (-not (Test-Path -LiteralPath (Join-Path (Split-Path $EvidenceRoot -Parent) 'outside.txt'))) 'ZIP_NOT_EXTRACTED'; Pass-Assertion

# Given a receipt missing one frozen gate, when candidate validation runs, then it fails without touching an app canary.
$candidate = Join-Path $EvidenceRoot 'IZ-Clinical-Notes-Analyzer-v2.0.0-beta.4-build-2026.09.14.1-installer-r1.zip'
[IO.File]::WriteAllBytes($candidate, [Text.Encoding]::ASCII.GetBytes('synthetic-candidate'))
$receiptPath = [IO.Path]::ChangeExtension($candidate, $null) + '.build-receipt.json'
$gateDir = Split-Path $receiptPath -Parent
$packageDirectory = Join-Path $EvidenceRoot 'IZ-Clinical-Notes-Analyzer-v2.0.0-beta.4-build-2026.09.14.1-installer-r1'
$null = New-Item -ItemType Directory -Path $packageDirectory
$gateNames = @('backend_tests', 'frontend_tests', 'frontend_build', 'repository_safety', 'directory_safety', 'zip_safety')
$gates = @($gateNames | ForEach-Object {
    $evidence = "gate-$_.txt"
    [IO.File]::WriteAllText((Join-Path $gateDir $evidence), 'passed')
    [ordered]@{ name = $_; status = 'passed'; command = 'synthetic command'; exit_code = 0; evidence = $evidence }
})
$badReceipt = [ordered]@{
    schema = 'iz-cna-build-receipt-v1'; product_id = 'r3.iz-clinical-notes-analyzer.desktop'
    version = '2.0.0-beta.4'; build = '2026.09.14.1'; installer_revision = 1
    source_revision = ('a' * 40); package_directory = $packageDirectory; zip_path = $candidate
    zip_length = (Get-Item -LiteralPath $candidate).Length; zip_sha256 = Get-IzHarnessSha256 -Path $candidate
    manifest_sha256 = ('b' * 64); payload_identity = ('c' * 64); gates = $gates
    created_utc = [DateTime]::UtcNow.ToString('o')
}
$badReceipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
Assert-Reason { Read-IzHarnessBuildReceipt -CandidateZip $candidate -ExpectedSourceRevision ('a' * 40) } 'BUILD_GATE_SET_MISMATCH'; Pass-Assertion
Assert-True ((Get-IzHarnessSha256 -Path $productCanary) -ceq 'acb86a9cb70a84f695de89e7fe22819466205759d798d52d4a3dd95b0cdaa2a1') 'BUILD_REFUSAL_CANARY'; Pass-Assertion

# Given terminal observations, when receipts are built, then Component cannot satisfy Package and failure stays nonzero.
$artifactPath = Join-Path $EvidenceRoot 'observable.txt'
[IO.File]::WriteAllText($artifactPath, 'binary-observable=synthetic')
$artifact = New-IzHarnessArtifact -Kind 'command_receipt' -Path $artifactPath
$observation = New-IzHarnessObservation -Variant 'synthetic-boundary' -Status passed -Invocation 'synthetic.exe --probe' -Observable 'exit_code=0' -Artifact $artifactPath
$caseDefinition = @($catalog | Where-Object id -eq B01)[0]
$emptyInputs = New-IzHarnessInputs
$passedReceipt = New-IzMaintenanceCaseReceipt -RunId $verified.run_id -CaseDefinition $caseDefinition -RequestedTier Component `
    -Status passed -Reason 'COMPONENT_ASSERTIONS_PASSED' -SourceRevision ('d' * 40) -Inputs $emptyInputs `
    -Execution ([pscustomobject][ordered]@{ executor = 'synthetic'; actual_installer = $false; actual_executable = $false; actual_browser = $false; actual_default_profile = $false; actual_home_edition = $false; actual_power_loss = $false; synthetic_data_only = $true }) `
    -Observations @($observation) -Artifacts @($artifact) -Safety ([pscustomobject][ordered]@{ owned_root_verified = $true; current_user_scope = $true; reparse_free = $true; input_hashes_rechecked = $true; redaction_scan = 'passed' }) `
    -Cleanup ([pscustomobject][ordered]@{ status = 'passed'; owned_processes_remaining = 0; owned_listeners_remaining = 0; retained_private_artifacts = $true })
Assert-True ((Test-IzMaintenanceCaseReceipt -Receipt $passedReceipt) -eq $true) 'PASSED_RECEIPT'; Pass-Assertion
$contradictoryObservation = $passedReceipt | ConvertTo-Json -Depth 20 | ConvertFrom-Json
$contradictoryObservation.observations[0].status = 'failed'
Assert-Reason { Test-IzMaintenanceCaseReceipt -Receipt $contradictoryObservation } 'CASE_PASSED_WITH_NONPASSING_OBSERVATION'; Pass-Assertion
$contradictorySafety = $passedReceipt | ConvertTo-Json -Depth 20 | ConvertFrom-Json
$contradictorySafety.safety.redaction_scan = 'failed'
Assert-Reason { Test-IzMaintenanceCaseReceipt -Receipt $contradictorySafety } 'CASE_PASSED_WITH_FAILED_SAFETY'; Pass-Assertion
$contradictoryCleanup = $passedReceipt | ConvertTo-Json -Depth 20 | ConvertFrom-Json
$contradictoryCleanup.cleanup.status = 'failed'
$contradictoryCleanup.cleanup.owned_processes_remaining = 4
Assert-Reason { Test-IzMaintenanceCaseReceipt -Receipt $contradictoryCleanup } 'CASE_PASSED_WITH_FAILED_CLEANUP'; Pass-Assertion
Assert-Reason {
    New-IzMaintenanceCaseReceipt -RunId $verified.run_id -CaseDefinition $caseDefinition -RequestedTier Package `
        -Status passed -Reason 'PACKAGE_PASSED' -SourceRevision ('d' * 40) -Inputs $emptyInputs `
        -Execution $passedReceipt.execution -Observations @($observation) -Artifacts @($artifact) `
        -Safety $passedReceipt.safety -Cleanup $passedReceipt.cleanup
} 'CASE_TIER_MISMATCH'; Pass-Assertion
$failedReceipt = New-IzMaintenanceCaseReceipt -RunId $verified.run_id -CaseDefinition $caseDefinition -RequestedTier Component `
    -Status failed -Reason 'DELIBERATE_ASSERTION_FAILURE' -SourceRevision ('d' * 40) -Inputs $emptyInputs `
    -Execution $passedReceipt.execution -Observations @($observation) -Artifacts @($artifact) `
    -Safety $passedReceipt.safety -Cleanup $passedReceipt.cleanup
Assert-True ((Get-IzMaintenanceRunExitCode -Receipts @($passedReceipt)) -eq 0) 'PASS_EXIT'; Pass-Assertion
Assert-True ((Get-IzMaintenanceRunExitCode -Receipts @($passedReceipt, $failedReceipt)) -ne 0) 'FAIL_EXIT'; Pass-Assertion
$blockedReceipt = New-IzMaintenanceCaseReceipt -RunId $verified.run_id -CaseDefinition $caseDefinition -RequestedTier Component `
    -Status blocked -Reason 'MISSING_REQUIRED_RUNNER' -SourceRevision ('d' * 40) -Inputs $emptyInputs `
    -Execution $passedReceipt.execution -Observations @($observation) -Artifacts @($artifact) `
    -Safety $passedReceipt.safety -Cleanup $passedReceipt.cleanup
Assert-True ((Get-IzMaintenanceRunExitCode -Receipts @($blockedReceipt)) -eq 2) 'BLOCKED_EXIT'; Pass-Assertion

# Given a complete Component index, when it is validated, then duplicate substitution and body/index drift are rejected.
$aggregateRoot = Join-Path $EvidenceRoot 'aggregate-public'
$aggregateCases = Join-Path $aggregateRoot 'cases'
$null = New-Item -ItemType Directory -Path $aggregateCases -Force
$aggregateReceipts = [Collections.Generic.List[object]]::new()
$aggregateDescriptors = [Collections.Generic.List[object]]::new()
foreach ($definition in @($catalog | Where-Object { $_.tiers -contains 'Component' })) {
    $caseArtifact = Join-Path $aggregateRoot ('artifacts\' + $definition.id.ToLowerInvariant() + '.json')
    $null = New-Item -ItemType Directory -Path (Split-Path $caseArtifact -Parent) -Force
    [IO.File]::WriteAllText($caseArtifact, '{"observable":"synthetic-blocked-infrastructure"}', [Text.UTF8Encoding]::new($false))
    $caseObservation = New-IzHarnessObservation -Variant 'aggregate-contract' -Status blocked `
        -Invocation 'synthetic aggregate contract fixture' -Observable 'infrastructure=blocked' -Artifact $caseArtifact
    $caseReceipt = New-IzMaintenanceCaseReceipt -RunId $verified.run_id -CaseDefinition $definition -RequestedTier Component `
        -Status blocked -Reason 'SYNTHETIC_INFRASTRUCTURE_BLOCKED' -SourceRevision ('d' * 40) -Inputs $emptyInputs `
        -Execution $passedReceipt.execution -Observations @($caseObservation) `
        -Artifacts @((New-IzHarnessArtifact -Kind 'aggregate_contract_observation' -Path $caseArtifact)) `
        -Safety $passedReceipt.safety -Cleanup $passedReceipt.cleanup
    $casePath = Join-Path $aggregateCases ($definition.id.ToLowerInvariant() + '.json')
    $null = Write-IzHarnessJson -Path $casePath -Value $caseReceipt
    $item = Get-Item -LiteralPath $casePath
    $aggregateReceipts.Add($caseReceipt)
    $aggregateDescriptors.Add([pscustomobject][ordered]@{
        case_id = $definition.id; status = 'blocked'; path = 'cases/' + $definition.id.ToLowerInvariant() + '.json'
        length = [long]$item.Length; sha256 = Get-IzHarnessSha256 -Path $casePath
    })
}
$aggregatePath = Join-Path $aggregateRoot 'maintenance-run-receipt.json'
$aggregate = New-IzMaintenanceRunReceipt -RunId $verified.run_id -RequestedCase All -RequestedTier Component `
    -SourceRevision ('d' * 40) -CaseReceipts @($aggregateReceipts) -CaseDescriptors @($aggregateDescriptors) `
    -ReceiptPath $aggregatePath
Assert-True ((Test-IzMaintenanceRunReceipt -Receipt $aggregate -ReceiptPath $aggregatePath) -eq $true) 'AGGREGATE_VALID'; Pass-Assertion
$duplicateIndex = $aggregate | ConvertTo-Json -Depth 30 | ConvertFrom-Json
$duplicateIndex.case_receipts[1] = $duplicateIndex.case_receipts[0]
Assert-Reason { Test-IzMaintenanceRunReceipt -Receipt $duplicateIndex -ReceiptPath $aggregatePath } 'RUN_CASE_INDEX_INVALID'; Pass-Assertion
$bodyMismatch = $aggregate | ConvertTo-Json -Depth 30 | ConvertFrom-Json
$bodyMismatch.case_receipts[0].status = 'failed'
Assert-Reason { Test-IzMaintenanceRunReceipt -Receipt $bodyMismatch -ReceiptPath $aggregatePath } 'RUN_CASE_BODY_MISMATCH'; Pass-Assertion

# Given a provisioned tier runner result, when the external boundary validates it, then a real driver can pass and a live listener contradiction cannot.
$externalRoot = Join-Path $EvidenceRoot 'external-result-contract'
$null = New-Item -ItemType Directory -Path $externalRoot
$externalArtifactPath = Join-Path $externalRoot 'binary-observable.json'
[IO.File]::WriteAllText($externalArtifactPath, '{"observable":"actual packaged command completed"}', [Text.UTF8Encoding]::new($false))
$externalArtifactItem = Get-Item -LiteralPath $externalArtifactPath
$externalDefinition = @($catalog | Where-Object id -eq I03)[0]
$externalResult = [pscustomobject][ordered]@{
    schema = 'iz-cna-maintenance-tier-case-result-v1'; case_id = 'I03'; tier = 'Package'; status = 'passed'
    reason = 'PACKAGE_SCENARIO_PASSED'; source_revision = ('d' * 40); candidate_zip_sha256 = ('e' * 64)
    scenario = [string]$externalDefinition.scenario
    execution = [pscustomobject][ordered]@{ executor = 'provisioned-tier-runner'; actual_installer = $true; actual_executable = $false; actual_browser = $false; actual_default_profile = $true; actual_home_edition = $false; actual_power_loss = $false; synthetic_data_only = $true }
    observations = @([pscustomobject][ordered]@{ variant = 'path-variants'; status = 'passed'; invocation = 'package runner path variants'; observable = 'exit_code=0;variants=7'; artifact = 'binary-observable.json' })
    artifacts = @([pscustomobject][ordered]@{ kind = 'command_receipt'; path = 'binary-observable.json'; length = [long]$externalArtifactItem.Length; sha256 = Get-IzHarnessSha256 $externalArtifactPath })
    safety = [pscustomobject][ordered]@{ owned_root_verified = $true; current_user_scope = $true; reparse_free = $true; input_hashes_rechecked = $true; redaction_scan = 'passed' }
    cleanup = [pscustomobject][ordered]@{ status = 'passed'; owned_processes_remaining = 0; owned_listeners_remaining = 0; retained_private_artifacts = $true }
    completed_utc = [DateTime]::UtcNow.ToString('o')
}
Assert-True ((Test-IzExternalTierResult -Result $externalResult -Definition $externalDefinition -Tier Package `
    -SourceRevision ('d' * 40) -CandidateSha256 ('e' * 64) -EvidenceRoot $externalRoot -ExitCode 0) -eq $true) 'EXTERNAL_TIER_DRIVER_REACHABLE'; Pass-Assertion
$externalContradiction = $externalResult | ConvertTo-Json -Depth 20 | ConvertFrom-Json
$externalContradiction.cleanup.owned_listeners_remaining = 1
Assert-Reason { Test-IzExternalTierResult -Result $externalContradiction -Definition $externalDefinition -Tier Package `
    -SourceRevision ('d' * 40) -CandidateSha256 ('e' * 64) -EvidenceRoot $externalRoot -ExitCode 0 } 'TIER_RESULT_PASS_UNDERPROVEN'; Pass-Assertion

# Given an unknown ID and a safe fresh root, when the runner rejects selection, then it still returns a terminal machine receipt.
$unknownRoot = Join-Path $qaParent ('cmd-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
$currentRevision = (& git.exe -C $repositoryRoot rev-parse HEAD).Trim()
$unknownResult = Invoke-IzMaintenanceHarness -RepositoryRoot $repositoryRoot -Case X99 -Tier Component `
    -BaselineZip 'C:\not-read-before-selection\beta3.zip' -OriginalBeta4Zip 'C:\not-read-before-selection\beta4.zip' `
    -ExpectedSourceRevision $currentRevision -EvidenceRoot $unknownRoot -BrowserChannel msedge
$unknownReceipt = Get-Content -LiteralPath $unknownResult.receipt_path -Raw | ConvertFrom-Json
Assert-True ($unknownResult.exit_code -eq 1 -and $unknownReceipt.schema -ceq 'iz-cna-maintenance-terminal-failure-v1' -and
    $unknownReceipt.reason -ceq 'UNKNOWN_CASE_ID' -and $unknownReceipt.product_write_attempted -eq $false) 'UNKNOWN_CASE_TERMINAL_RECEIPT'; Pass-Assertion

# Given an unowned evidence root, when the public entry point rejects it before runner setup, then console and GITHUB_OUTPUT still locate safe terminal evidence.
$githubOutputPath = Join-Path $EvidenceRoot 'github-output.txt'
$previousGithubOutput = $env:GITHUB_OUTPUT
try {
    $env:GITHUB_OUTPUT = $githubOutputPath
    $publicOutput = @(& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass `
        -File (Join-Path $repositoryRoot 'scripts\test-cmd-maintenance.ps1') -Case B01 -Tier Component `
        -BaselineZip 'C:\not-read-before-root-guard\beta3.zip' -OriginalBeta4Zip 'C:\not-read-before-root-guard\beta4.zip' `
        -ExpectedSourceRevision $currentRevision -EvidenceRoot $unowned -BrowserChannel msedge 2>&1)
    $publicExit = [int]$LASTEXITCODE
}
finally {
    if ($null -eq $previousGithubOutput) { Remove-Item Env:\GITHUB_OUTPUT -ErrorAction SilentlyContinue }
    else { $env:GITHUB_OUTPUT = $previousGithubOutput }
}
$locator = @($publicOutput | ForEach-Object { [string]$_ } | Where-Object { $_ -cmatch '^MAINTENANCE_RECEIPT_PATH=' })
Assert-True ($publicExit -eq 1 -and $locator.Count -eq 1) 'PUBLIC_PREFLIGHT_LOCATOR'; Pass-Assertion
$publicFailurePath = $locator[0].Substring('MAINTENANCE_RECEIPT_PATH='.Length)
$publicFailure = Get-Content -LiteralPath $publicFailurePath -Raw | ConvertFrom-Json
$githubOutputText = Get-Content -LiteralPath $githubOutputPath -Raw
Assert-True ($publicFailure.schema -ceq 'iz-cna-maintenance-terminal-failure-v1' -and
    $publicFailure.reason -ceq 'UNOWNED_EXISTING_ROOT' -and $publicFailure.product_write_attempted -eq $false -and
    $githubOutputText.Trim() -ceq "maintenance_receipt_path=$publicFailurePath") 'PUBLIC_PREFLIGHT_TERMINAL_RECEIPT'; Pass-Assertion

# Given a secret canary in a receipt, when sanitized JSON is written, then it is refused and no file appears.
$secretCanary = 'SYNTHETIC_SECRET_CANARY_8D9A3E0F'
$env:IZ_CNA_QA_SECRET_CANARY = $secretCanary
$leakPath = Join-Path $resultRoot 'should-not-exist-secret.json'
Assert-Reason { Write-IzHarnessJson -Path $leakPath -Value ([ordered]@{ value = $secretCanary }) } 'PRIVATE_VALUE_IN_EVIDENCE'; Pass-Assertion
Assert-True (-not (Test-Path -LiteralPath $leakPath)) 'NO_SECRET_ARTIFACT'; Pass-Assertion
Remove-Item Env:IZ_CNA_QA_SECRET_CANARY

$report = [ordered]@{
    schema = 'iz-cna-maintenance-harness-test-v1'
    status = 'passed'
    assertion_count = $assertionCount
    catalog_count = $catalog.Count
    tier_counts = [ordered]@{ component = 13; package = 54; home = 12; power_loss = 1 }
    owned_root = $EvidenceRoot
    deliberate_failure_exit_nonzero = $true
    unsafe_and_unowned_fail_before_write = $true
    completed_utc = [DateTime]::UtcNow.ToString('o')
}
$reportPath = Join-Path $resultRoot ("task-05-harness-$((Split-Path $EvidenceRoot -Leaf)).json")
$null = Write-IzHarnessJson -Path $reportPath -Value $report
Write-Output "PASS maintenance harness assertions=$assertionCount evidence=$reportPath"
if (Test-Path -LiteralPath $moduleCachePath -PathType Leaf) { Remove-Item -LiteralPath $moduleCachePath -Force -ErrorAction SilentlyContinue }
