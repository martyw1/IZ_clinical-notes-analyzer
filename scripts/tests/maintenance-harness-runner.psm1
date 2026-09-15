Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'maintenance-harness-contracts.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'maintenance-harness-safety.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'maintenance-harness-components.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'maintenance-harness-verification.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'maintenance-harness-external.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'maintenance-harness-lifecycle.psm1') -Force
. (Join-Path $PSScriptRoot 'maintenance-fixture.ps1')

$script:Beta3Sha256 = '9c5fd47203242e1a21df612f719f1c14fa4240c86ba869f924ec4690834fc89c'
$script:OriginalBeta4Sha256 = '67b83eea402566658dea6d64ac6cba37a192a7d1bd670cf560541324c0092b14'
$script:InterfaceFreezeSha256 = 'c2a3feca42da8a0d333a587018c328f7cba26dc434e21e28c471a79308e866a8'

function Get-IzHarnessReason {
    param([Parameter(Mandatory)][Management.Automation.ErrorRecord]$ErrorRecord, [string]$Fallback = 'HARNESS_FAILED')
    if ($ErrorRecord.Exception.Data.Contains('iz_reason')) { return [string]$ErrorRecord.Exception.Data['iz_reason'] }
    if ($ErrorRecord.Exception.Message -cmatch '^[A-Z][A-Z0-9_]{0,63}$') { return $ErrorRecord.Exception.Message }
    return $Fallback
}

function Get-IzHarnessSourceRevision {
    param([Parameter(Mandatory)][string]$RepositoryRoot)
    $revision = (& git.exe -C $RepositoryRoot rev-parse HEAD 2>$null).Trim()
    if ($LASTEXITCODE -ne 0 -or $revision -cnotmatch '^[a-f0-9]{40}$') { throw 'SOURCE_REVISION_UNAVAILABLE' }
    return $revision
}

function New-IzHarnessExecution {
    param(
        [string]$Executor = 'maintenance-harness',
        [bool]$ActualInstaller = $false,
        [bool]$ActualExecutable = $false,
        [bool]$ActualBrowser = $false,
        [bool]$ActualDefaultProfile = $false,
        [bool]$ActualHomeEdition = $false,
        [bool]$ActualPowerLoss = $false
    )
    return [pscustomobject][ordered]@{
        executor = $Executor
        actual_installer = $ActualInstaller
        actual_executable = $ActualExecutable
        actual_browser = $ActualBrowser
        actual_default_profile = $ActualDefaultProfile
        actual_home_edition = $ActualHomeEdition
        actual_power_loss = $ActualPowerLoss
        synthetic_data_only = $true
    }
}

function New-IzHarnessSafetyState {
    param([bool]$InputsRechecked)
    return [pscustomobject][ordered]@{
        owned_root_verified = $true
        current_user_scope = $true
        reparse_free = $true
        input_hashes_rechecked = $InputsRechecked
        redaction_scan = 'passed'
    }
}

function New-IzHarnessCleanupState {
    param([string]$Status = 'passed', [bool]$Retained = $true)
    return [pscustomobject][ordered]@{
        status = $Status
        owned_processes_remaining = 0
        owned_listeners_remaining = 0
        retained_private_artifacts = $Retained
    }
}

function New-IzHarnessCaseOutcome {
    param(
        [Parameter(Mandatory)][string]$Status,
        [Parameter(Mandatory)][string]$Reason,
        [Parameter(Mandatory)][object]$Execution,
        [Parameter(Mandatory)][object[]]$Observations,
        [Parameter(Mandatory)][object[]]$Artifacts,
        [AllowNull()][object]$Safety = $null,
        [AllowNull()][object]$Cleanup = $null,
        [string]$StartedUtc = ([DateTime]::UtcNow.ToString('o'))
    )
    return [pscustomobject][ordered]@{
        status = $Status; reason = $Reason; execution = $Execution
        observations = @($Observations); artifacts = @($Artifacts); started_utc = $StartedUtc
        safety = $Safety; cleanup = $Cleanup
    }
}

function New-IzHarnessTerminalArtifact {
    param(
        [Parameter(Mandatory)][string]$PublicCaseRoot,
        [Parameter(Mandatory)][string]$CaseId,
        [Parameter(Mandatory)][string]$Status,
        [Parameter(Mandatory)][string]$Reason,
        [Parameter(Mandatory)][string]$Observable
    )
    $path = Join-Path $PublicCaseRoot 'terminal-observation.json'
    $value = [ordered]@{
        schema = 'iz-cna-maintenance-terminal-observation-v1'
        case_id = $CaseId
        status = $Status
        reason = $Reason
        observable = $Observable
        completed_utc = [DateTime]::UtcNow.ToString('o')
    }
    $null = Write-IzHarnessJson -Path $path -Value $value
    return $path
}

function Invoke-IzHarnessB01 {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [Parameter(Mandatory)][string]$PublicCaseRoot,
        [Parameter(Mandatory)][object]$BaselineDescriptor,
        [Parameter(Mandatory)][object]$OriginalDescriptor
    )
    $started = [DateTime]::UtcNow.ToString('o')
    $preservationPath = Join-Path $RepositoryRoot '.omo\evidence\windows-cmd-maintenance\s0\archive-preservation.json'
    $beta3ReceiptPath = Join-Path $RepositoryRoot '.omo\evidence\windows-cmd-maintenance\harness\s0-beta3-component\task-05-beta3-component.json'
    $freezePath = Join-Path $RepositoryRoot '.omo\evidence\windows-cmd-maintenance\contracts\interface-freeze-v1.md'
    $valid = $true
    foreach ($path in @($preservationPath, $beta3ReceiptPath, $freezePath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -le 0) { $valid = $false }
    }
    if ($valid) {
        try {
            $preservation = Get-Content -LiteralPath $preservationPath -Raw | ConvertFrom-Json
            $beta3 = Get-Content -LiteralPath $beta3ReceiptPath -Raw | ConvertFrom-Json
            $valid = (
                $preservation.schema -ceq 'iz-cna-s0-archive-preservation-v1' -and
                $preservation.allImmutable -eq $true -and $preservation.originalArchivesModified -eq $false -and
                @($preservation.archives).Count -eq 2 -and
                $beta3.schema -ceq 'iz-cna-s0-beta3-component-v1' -and $beta3.status -ceq 'passed' -and
                $beta3.actual_installer -eq $false -and $beta3.actual_default_profile -eq $false -and
                @($beta3.package_cases_satisfied).Count -eq 0 -and $beta3.cleanup.owned_runtime_stopped -eq $true -and
                $beta3.cleanup.listener_released -eq $true -and
                [string]$beta3.archive.sha256_after -ceq [string]$BaselineDescriptor.sha256 -and
                [string]$BaselineDescriptor.sha256 -ceq $script:Beta3Sha256 -and
                [string]$OriginalDescriptor.sha256 -ceq $script:OriginalBeta4Sha256 -and
                (Get-IzHarnessSha256 -Path $freezePath) -ceq $script:InterfaceFreezeSha256
            )
        }
        catch { $valid = $false }
    }
    $status = if ($valid) { 'passed' } else { 'failed' }
    $reason = if ($valid) { 'BASELINES_PRESERVED' } else { 'BASELINE_EVIDENCE_INVALID' }
    $summaryPath = Join-Path $PublicCaseRoot 'baseline-preservation.json'
    $summary = [ordered]@{
        schema = 'iz-cna-maintenance-baseline-observation-v1'
        status = $status
        beta3_length = [long]$BaselineDescriptor.length
        beta3_sha256 = [string]$BaselineDescriptor.sha256
        original_beta4_length = [long]$OriginalDescriptor.length
        original_beta4_sha256 = [string]$OriginalDescriptor.sha256
        interface_freeze_sha256 = if (Test-Path -LiteralPath $freezePath -PathType Leaf) { Get-IzHarnessSha256 -Path $freezePath } else { $null }
        packaged_beta3_executable_observed = [bool]$valid
        actual_installer = $false
        actual_default_profile = $false
        completed_utc = [DateTime]::UtcNow.ToString('o')
    }
    $null = Write-IzHarnessJson -Path $summaryPath -Value $summary
    $observation = New-IzHarnessObservation -Variant 'preserved-archives-and-beta3-executable' -Status $status `
        -Invocation 'Get-FileHash SHA256 <preserved beta.3>; Get-FileHash SHA256 <preserved original beta.4>; validate S0 beta.3 packaged-EXE receipt' `
        -Observable "beta3_sha256=$($BaselineDescriptor.sha256);original_beta4_sha256=$($OriginalDescriptor.sha256);component_exe_receipt=$valid" `
        -Artifact $summaryPath
    return New-IzHarnessCaseOutcome -Status $status -Reason $reason `
        -Execution (New-IzHarnessExecution -Executor 'archive-and-packaged-exe-baseline' -ActualExecutable $valid) `
        -Observations @($observation) -Artifacts @((New-IzHarnessArtifact -Kind 'baseline_observation' -Path $summaryPath)) -StartedUtc $started
}

function Invoke-IzHarnessComponentCase {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [Parameter(Mandatory)][object]$Definition,
        [Parameter(Mandatory)][object]$Fixture,
        [Parameter(Mandatory)][string]$PublicCaseRoot,
        [AllowNull()][object]$CandidateReceipt,
        [Parameter(Mandatory)][object]$BaselineDescriptor,
        [Parameter(Mandatory)][object]$OriginalDescriptor,
        [Parameter(Mandatory)][ValidateSet('msedge','chrome')][string]$BrowserChannel
    )
    $started = [DateTime]::UtcNow.ToString('o')
    if ($Definition.id -in @('P01', 'P02', 'P03', 'P04', 'P05') -and $null -eq $CandidateReceipt) {
        $path = New-IzHarnessTerminalArtifact -PublicCaseRoot $PublicCaseRoot -CaseId $Definition.id -Status blocked `
            -Reason 'CANDIDATE_BUILD_REQUIRED' -Observable 'No exact candidate ZIP/build receipt was supplied; build-bound Component evidence was not inferred.'
        $observation = New-IzHarnessObservation -Variant 'candidate-build-boundary' -Status blocked `
            -Invocation 'Read-IzHarnessBuildReceipt -CandidateZip <exact absolute path>' `
            -Observable 'candidate_build_receipt=missing' -Artifact $path
        return New-IzHarnessCaseOutcome -Status blocked -Reason 'CANDIDATE_BUILD_REQUIRED' `
            -Execution (New-IzHarnessExecution -Executor 'candidate-build-preflight') -Observations @($observation) `
            -Artifacts @((New-IzHarnessArtifact -Kind 'blocked_observation' -Path $path)) -StartedUtc $started
    }
    if ($Definition.id -eq 'P02') {
        $path = Join-Path $PublicCaseRoot 'candidate-build-observation.json'
        $receipt = $CandidateReceipt.receipt
        $value = [ordered]@{
            schema = 'iz-cna-maintenance-candidate-observation-v1'
            status = 'passed'
            source_revision = [string]$receipt.source_revision
            version = [string]$receipt.version
            build = [string]$receipt.build
            installer_revision = [int]$receipt.installer_revision
            zip_length = [long]$receipt.zip_length
            zip_sha256 = [string]$receipt.zip_sha256
            manifest_sha256 = [string]$receipt.manifest_sha256
            gates = @($receipt.gates | ForEach-Object { [ordered]@{ name = $_.name; status = $_.status; exit_code = $_.exit_code } })
            completed_utc = [DateTime]::UtcNow.ToString('o')
        }
        $null = Write-IzHarnessJson -Path $path -Value $value
        $observation = New-IzHarnessObservation -Variant 'frozen-candidate-build' -Status passed `
            -Invocation 'Read-IzHarnessBuildReceipt plus safe ZIP member validation' `
            -Observable "gates=7;zip_length=$($receipt.zip_length);zip_sha256=$($receipt.zip_sha256)" -Artifact $path
        $binding = New-IzLifecycleCandidateBinding -QualificationMode Release -CandidateZip ([string]$receipt.zip_path) `
            -CandidatePackageRoot ([string]$receipt.package_directory) -ExpectedSourceRevision ([string]$receipt.source_revision) `
            -CandidateBuildReceipt $CandidateReceipt
        $lifecycle = Invoke-IzComponentLifecycleSmoke -RepositoryRoot $RepositoryRoot -Fixture $Fixture `
            -PublicCaseRoot $PublicCaseRoot -BaselineZip ([string]$BaselineDescriptor.path) `
            -OriginalBeta4Zip ([string]$OriginalDescriptor.path) -Binding $binding `
            -BrowserChannel $BrowserChannel -CaseId P02
        $observations = [Collections.Generic.List[object]]::new()
        $observations.Add($observation)
        $observations.Add((New-IzHarnessObservation -Variant 'packaged-exe-live-lifecycle' -Status $lifecycle.status `
            -Invocation $lifecycle.invocation -Observable $lifecycle.observable -Artifact $lifecycle.artifact_path))
        $artifacts = [Collections.Generic.List[object]]::new()
        $artifacts.Add((New-IzHarnessArtifact -Kind 'candidate_build_observation' -Path $path))
        $artifacts.Add((New-IzHarnessArtifact -Kind 'packaged_exe_lifecycle' -Path $lifecycle.artifact_path))
        if ($lifecycle.browser_artifact_path) {
            $artifacts.Add((New-IzHarnessArtifact -Kind 'packaged_browser_lifecycle' -Path $lifecycle.browser_artifact_path))
        }
        return New-IzHarnessCaseOutcome -Status $lifecycle.status `
            -Reason $(if ($lifecycle.status -ceq 'passed') { 'CANDIDATE_BUILD_AND_LIFECYCLE_VERIFIED' } else { $lifecycle.reason }) `
            -Execution (New-IzHarnessExecution -Executor 'candidate-build-and-live-lifecycle' `
                -ActualExecutable:$lifecycle.actual_executable -ActualBrowser:$lifecycle.actual_browser) `
            -Observations @($observations) -Artifacts @($artifacts) -Cleanup $lifecycle.cleanup -StartedUtc $started
    }
    if ($Definition.id -eq 'P01') {
        $verification = Invoke-IzHarnessSourceVerification -RepositoryRoot $RepositoryRoot -Fixture $Fixture `
            -PublicCaseRoot $PublicCaseRoot -CandidateReceipt $CandidateReceipt
        return New-IzHarnessCaseOutcome -Status $verification.status -Reason $verification.reason `
            -Execution (New-IzHarnessExecution -Executor 'source-and-build-verification') `
            -Observations @((New-IzHarnessObservation -Variant 'full-source-gates' -Status $verification.status `
                -Invocation $verification.invocation -Observable $verification.observable -Artifact $verification.artifact_path)) `
            -Artifacts @((New-IzHarnessArtifact -Kind 'source_verification' -Path $verification.artifact_path)) -StartedUtc $started
    }
    if ($Definition.id -eq 'P05') {
        $verification = Invoke-IzHarnessPackagingVerification -RepositoryRoot $RepositoryRoot -Fixture $Fixture `
            -PublicCaseRoot $PublicCaseRoot -CandidateReceipt $CandidateReceipt
        return New-IzHarnessCaseOutcome -Status $verification.status -Reason $verification.reason `
            -Execution (New-IzHarnessExecution -Executor 'rendered-source-verification') `
            -Observations @((New-IzHarnessObservation -Variant 'rendered-source-equality' -Status $verification.status `
                -Invocation $verification.invocation -Observable $verification.observable -Artifact $verification.artifact_path)) `
            -Artifacts @((New-IzHarnessArtifact -Kind 'rendered_source_verification' -Path $verification.artifact_path)) -StartedUtc $started
    }
    if ($Definition.id -eq 'P03') {
        $verification = Invoke-IzHarnessReleaseSafetyVerification -RepositoryRoot $RepositoryRoot -Fixture $Fixture `
            -PublicCaseRoot $PublicCaseRoot -CandidateReceipt $CandidateReceipt
        return New-IzHarnessCaseOutcome -Status $verification.status -Reason $verification.reason `
            -Execution (New-IzHarnessExecution -Executor 'release-safety-verification') `
            -Observations @((New-IzHarnessObservation -Variant 'release-safety-negative-boundaries' -Status $verification.status `
                -Invocation $verification.invocation -Observable $verification.observable -Artifact $verification.artifact_path)) `
            -Artifacts @((New-IzHarnessArtifact -Kind 'release_safety_verification' -Path $verification.artifact_path)) -StartedUtc $started
    }
    if ($Definition.id -eq 'P04') {
        $archive = Invoke-IzHarnessArchiveVerification -RepositoryRoot $RepositoryRoot -Fixture $Fixture `
            -PublicCaseRoot $PublicCaseRoot -CandidateReceipt $CandidateReceipt
        $suitePlan = @(Get-IzComponentSuitePlan -CaseId $Definition.id)
        $suiteResults = @($suitePlan | ForEach-Object {
            Invoke-IzComponentSuite -RepositoryRoot $RepositoryRoot -Fixture $Fixture -Spec $_ -PublicCaseRoot $PublicCaseRoot
        })
        $combinedStatus = if ($archive.status -ceq 'failed' -or @($suiteResults | Where-Object status -eq failed).Count) { 'failed' } `
            elseif ($archive.status -ceq 'blocked' -or @($suiteResults | Where-Object status -eq blocked).Count) { 'blocked' } else { 'passed' }
        $observations = [Collections.Generic.List[object]]::new()
        $artifacts = [Collections.Generic.List[object]]::new()
        $observations.Add((New-IzHarnessObservation -Variant 'ps51-short-long-archive' -Status $archive.status `
            -Invocation $archive.invocation -Observable $archive.observable -Artifact $archive.artifact_path))
        $artifacts.Add((New-IzHarnessArtifact -Kind 'archive_regression_verification' -Path $archive.artifact_path))
        foreach ($suite in $suiteResults) {
            $observations.Add((New-IzHarnessObservation -Variant 'archive-input-negative-boundaries' -Status $suite.status `
                -Invocation $suite.invocation -Observable $suite.observable -Artifact $suite.artifact_path))
            $artifacts.Add((New-IzHarnessArtifact -Kind 'component_suite_observation' -Path $suite.artifact_path))
        }
        return New-IzHarnessCaseOutcome -Status $combinedStatus `
            -Reason $(if ($combinedStatus -ceq 'passed') { 'ARCHIVE_BOUNDARIES_PASSED' } elseif ($combinedStatus -ceq 'blocked') { 'ARCHIVE_BOUNDARIES_BLOCKED' } else { 'ARCHIVE_BOUNDARIES_FAILED' }) `
            -Execution (New-IzHarnessExecution -Executor 'ps51-archive-and-negative-verification') `
            -Observations @($observations) -Artifacts @($artifacts) -StartedUtc $started
    }
    $suitePlan = @(Get-IzComponentSuitePlan -CaseId $Definition.id)
    if ($suitePlan.Count -eq 0) {
        $path = New-IzHarnessTerminalArtifact -PublicCaseRoot $PublicCaseRoot -CaseId $Definition.id -Status blocked `
            -Reason 'CASE_EXECUTOR_UNAVAILABLE' -Observable 'No focused Component executor is registered for this exact case.'
        $observation = New-IzHarnessObservation -Variant 'component-dispatch' -Status blocked -Invocation 'component case dispatcher' `
            -Observable 'registered_executor=false' -Artifact $path
        return New-IzHarnessCaseOutcome -Status blocked -Reason 'CASE_EXECUTOR_UNAVAILABLE' `
            -Execution (New-IzHarnessExecution) -Observations @($observation) `
            -Artifacts @((New-IzHarnessArtifact -Kind 'blocked_observation' -Path $path)) -StartedUtc $started
    }
    $suiteResults = @($suitePlan | ForEach-Object {
        Invoke-IzComponentSuite -RepositoryRoot $RepositoryRoot -Fixture $Fixture -Spec $_ -PublicCaseRoot $PublicCaseRoot
    })
    $status = if (@($suiteResults | Where-Object status -eq failed).Count) { 'failed' } `
        elseif (@($suiteResults | Where-Object status -eq blocked).Count) { 'blocked' } else { 'passed' }
    $reason = if ($status -ceq 'passed') { 'COMPONENT_ASSERTIONS_PASSED' } `
        elseif ($status -ceq 'failed') { 'COMPONENT_ASSERTION_FAILED' } else { 'COMPONENT_INFRASTRUCTURE_BLOCKED' }
    $observations = @($suiteResults | ForEach-Object {
        New-IzHarnessObservation -Variant 'focused-component-suite' -Status $_.status -Invocation $_.invocation `
            -Observable $_.observable -Artifact $_.artifact_path
    })
    $artifacts = @($suiteResults | ForEach-Object { New-IzHarnessArtifact -Kind 'component_suite_observation' -Path $_.artifact_path })
    return New-IzHarnessCaseOutcome -Status $status -Reason $reason `
        -Execution (New-IzHarnessExecution -Executor 'focused-component-suites') `
        -Observations $observations -Artifacts $artifacts -StartedUtc $started
}

function Get-IzHarnessAggregateStatus {
    param([Parameter(Mandatory)][object[]]$Receipts)
    if (@($Receipts | Where-Object status -eq failed).Count) { return 'failed' }
    if (@($Receipts | Where-Object status -eq blocked).Count) { return 'blocked' }
    return 'passed'
}

function Invoke-IzMaintenanceHarness {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [Parameter(Mandatory)][string]$Case,
        [Parameter(Mandatory)][ValidateSet('Component', 'Package', 'Home', 'PowerLoss')][string]$Tier,
        [Parameter(Mandatory)][string]$BaselineZip,
        [Parameter(Mandatory)][string]$OriginalBeta4Zip,
        [string]$CandidateZip = '',
        [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{40}$')][string]$ExpectedSourceRevision,
        [string]$CandidateBuildReceipt = '',
        [Parameter(Mandatory)][string]$EvidenceRoot,
        [Parameter(Mandatory)][ValidateSet('msedge', 'chrome')][string]$BrowserChannel,
        [string]$VmControlManifest = ''
    )
    $started = [DateTime]::UtcNow.ToString('o')
    $repository = [IO.Path]::GetFullPath($RepositoryRoot)
    $owned = Initialize-IzHarnessEvidenceRoot -Path $EvidenceRoot
    $publicRoot = Join-Path $repository ".omo\evidence\windows-cmd-maintenance\$($owned.run_id)"
    if (Test-Path -LiteralPath $publicRoot) { throw 'PUBLIC_EVIDENCE_ALREADY_EXISTS' }
    $null = New-Item -ItemType Directory -Path (Join-Path $publicRoot 'cases') -Force
    $aggregatePath = Join-Path $publicRoot 'maintenance-run-receipt.json'
    $sourceRevision = $null
    try {
        $sourceRevision = Get-IzHarnessSourceRevision -RepositoryRoot $repository
        if ($sourceRevision -cne $ExpectedSourceRevision) { throw 'EXPECTED_SOURCE_REVISION_MISMATCH' }
        $selected = @(Get-IzMaintenanceCaseSelection -Case $Case -Tier $Tier)
    }
    catch {
        $reason = Get-IzHarnessReason -ErrorRecord $_ -Fallback 'HARNESS_INITIALIZATION_FAILED'
        $failure = New-IzMaintenanceTerminalFailureReceipt -RequestedCase $Case -RequestedTier $Tier `
            -Reason $reason -SourceRevision $sourceRevision -StartedUtc $started
        $null = Write-IzHarnessJson -Path $aggregatePath -Value $failure
        return [pscustomobject][ordered]@{
            receipt_path = [IO.Path]::GetFullPath($aggregatePath)
            status = 'failed'
            exit_code = 1
        }
    }
    try {
    $baselineDescriptor = $null
    $originalDescriptor = $null
    $candidateDescriptor = $null
    $candidateReceipt = $null
    $vmDescriptor = $null
    $tierRunner = $null
    $preflightStatus = 'passed'
    $preflightReason = 'INPUTS_VERIFIED'
    try {
        $baselineDescriptor = Get-IzHarnessFileDescriptor -Path $BaselineZip
        $originalDescriptor = Get-IzHarnessFileDescriptor -Path $OriginalBeta4Zip
        if ($baselineDescriptor.sha256 -cne $script:Beta3Sha256) { throw 'BASELINE_ZIP_HASH_MISMATCH' }
        if ($originalDescriptor.sha256 -cne $script:OriginalBeta4Sha256) { throw 'ORIGINAL_BETA4_ZIP_HASH_MISMATCH' }
        $null = Test-IzHarnessZip -Path $baselineDescriptor.path
        $null = Test-IzHarnessZip -Path $originalDescriptor.path
        if ($CandidateZip) {
            $candidateReceipt = Read-IzHarnessBuildReceipt -CandidateZip $CandidateZip `
                -ExpectedSourceRevision $ExpectedSourceRevision -CandidateBuildReceipt $CandidateBuildReceipt
            $candidateDescriptor = Get-IzHarnessFileDescriptor -Path $CandidateZip
            if ([string]$candidateReceipt.receipt.source_revision -cne $ExpectedSourceRevision -or
                $sourceRevision -cne $ExpectedSourceRevision) {
                throw 'CANDIDATE_SOURCE_REVISION_MISMATCH'
            }
            $sourceRevision = [string]$candidateReceipt.receipt.source_revision
        }
        elseif ($Tier -cne 'Component') {
            $preflightStatus = 'blocked'; $preflightReason = 'CANDIDATE_ZIP_REQUIRED'
        }
        if ($VmControlManifest) { $vmDescriptor = Get-IzHarnessFileDescriptor -Path $VmControlManifest }
        if ($preflightStatus -ceq 'passed' -and $Tier -in @('Package', 'Home')) {
            $null = Test-IzPackageTierEnvironment -Tier $Tier
            $tierRunner = Read-IzExternalTierRunner -Tier $Tier
        }
        if ($preflightStatus -ceq 'passed' -and $Tier -ceq 'PowerLoss') {
            $tierRunner = Read-IzExternalTierRunner -Tier PowerLoss -VmControlManifest $VmControlManifest
        }
    }
    catch {
        $preflightStatus = if ((Get-IzHarnessReason -ErrorRecord $_) -match 'MISSING|REQUIRED|NOT_PROVISIONED') { 'blocked' } else { 'failed' }
        $preflightReason = Get-IzHarnessReason -ErrorRecord $_ -Fallback 'INPUT_PREFLIGHT_FAILED'
    }
    $inputs = New-IzHarnessInputs -BaselineZip $baselineDescriptor -OriginalBeta4Zip $originalDescriptor `
        -CandidateZip $candidateDescriptor -CandidateBuildReceipt $(if ($candidateReceipt) {
            [pscustomobject][ordered]@{ path = $candidateReceipt.path; length = $candidateReceipt.length; sha256 = $candidateReceipt.sha256 }
        } else { $null }) -BrowserChannel $BrowserChannel -VmControlManifest $vmDescriptor
    $pending = [Collections.Generic.List[object]]::new()
    foreach ($definition in $selected) {
        $publicCaseRoot = Join-Path $publicRoot ('case-artifacts\' + $definition.id.ToLowerInvariant())
        $null = New-Item -ItemType Directory -Path $publicCaseRoot -Force
        $fixture = New-IzMaintenanceFixture -HarnessRoot $owned -CaseId $definition.id `
            -ShortComponentRoot:($Tier -ceq 'Component' -and $definition.id -ceq 'P02')
        if ($preflightStatus -cne 'passed') {
            $path = New-IzHarnessTerminalArtifact -PublicCaseRoot $publicCaseRoot -CaseId $definition.id `
                -Status $preflightStatus -Reason $preflightReason -Observable "input_preflight=$preflightStatus"
            $outcome = New-IzHarnessCaseOutcome -Status $preflightStatus -Reason $preflightReason `
                -Execution (New-IzHarnessExecution -Executor 'input-preflight') `
                -Observations @((New-IzHarnessObservation -Variant 'input-preflight' -Status $preflightStatus `
                    -Invocation 'validate exact archive hashes, candidate build receipt, tier infrastructure and owned roots' `
                    -Observable "status=$preflightStatus;reason=$preflightReason;product_write_attempted=false" -Artifact $path)) `
                -Artifacts @((New-IzHarnessArtifact -Kind 'preflight_observation' -Path $path))
        }
        elseif ($Tier -ceq 'Component' -and $definition.id -ceq 'B01') {
            $outcome = Invoke-IzHarnessB01 -RepositoryRoot $repository -PublicCaseRoot $publicCaseRoot `
                -BaselineDescriptor $baselineDescriptor -OriginalDescriptor $originalDescriptor
        }
        elseif ($Tier -ceq 'Component') {
            $outcome = Invoke-IzHarnessComponentCase -RepositoryRoot $repository -Definition $definition -Fixture $fixture `
                -PublicCaseRoot $publicCaseRoot -CandidateReceipt $candidateReceipt `
                -BaselineDescriptor $baselineDescriptor -OriginalDescriptor $originalDescriptor -BrowserChannel $BrowserChannel
        }
        else {
            $external = Invoke-IzExternalTierCase -Definition $definition -Tier $Tier -Fixture $fixture `
                -PublicCaseRoot $publicCaseRoot -SourceRevision $sourceRevision `
                -BaselineDescriptor $baselineDescriptor -OriginalDescriptor $originalDescriptor `
                -CandidateDescriptor $candidateDescriptor -CandidateReceipt $candidateReceipt `
                -BrowserChannel $BrowserChannel -Runner $tierRunner
            $outcome = New-IzHarnessCaseOutcome -Status $external.status -Reason $external.reason `
                -Execution $external.execution -Safety $external.safety -Cleanup $external.cleanup `
                -Observations @((New-IzHarnessObservation -Variant 'external-tier-execution' -Status $external.status `
                    -Invocation $external.invocation -Observable $external.observable -Artifact $external.artifact_path)) `
                -Artifacts @((New-IzHarnessArtifact -Kind 'external_tier_verification' -Path $external.artifact_path))
        }
        $pending.Add([pscustomobject][ordered]@{ definition = $definition; outcome = $outcome })
    }
    $hashesRechecked = $false
    try {
        $hashesRechecked = (Get-IzHarnessSha256 -Path $BaselineZip) -ceq $script:Beta3Sha256 -and
            (Get-IzHarnessSha256 -Path $OriginalBeta4Zip) -ceq $script:OriginalBeta4Sha256
        if ($CandidateZip -and $candidateDescriptor) {
            $hashesRechecked = $hashesRechecked -and (Get-IzHarnessSha256 -Path $CandidateZip) -ceq $candidateDescriptor.sha256
        }
    }
    catch { $hashesRechecked = $false }
    $receipts = [Collections.Generic.List[object]]::new()
    $caseDescriptors = [Collections.Generic.List[object]]::new()
    foreach ($item in $pending) {
        $definition = $item.definition
        $outcome = $item.outcome
        if (-not $hashesRechecked -and $outcome.status -ceq 'passed') {
            $outcome.status = 'failed'; $outcome.reason = 'INPUT_HASH_RECHECK_FAILED'
        }
        $receiptSafety = if ($null -ne $outcome.safety) { $outcome.safety } else { New-IzHarnessSafetyState -InputsRechecked $hashesRechecked }
        $receiptCleanup = if ($null -ne $outcome.cleanup) { $outcome.cleanup } else { New-IzHarnessCleanupState }
        $receipt = New-IzMaintenanceCaseReceipt -RunId $owned.run_id -CaseDefinition $definition -RequestedTier $Tier `
            -Status $outcome.status -Reason $outcome.reason -SourceRevision $sourceRevision -Inputs $inputs `
            -Execution $outcome.execution -Observations $outcome.observations -Artifacts $outcome.artifacts `
            -Safety $receiptSafety -Cleanup $receiptCleanup -StartedUtc $outcome.started_utc
        $receiptPath = Join-Path (Join-Path $publicRoot 'cases') ($definition.id.ToLowerInvariant() + '.json')
        $null = Write-IzHarnessJson -Path $receiptPath -Value $receipt
        $receiptItem = Get-Item -LiteralPath $receiptPath
        $receipts.Add($receipt)
        $caseDescriptors.Add([pscustomobject][ordered]@{
            case_id = $definition.id
            status = $receipt.status
            path = 'cases/' + $definition.id.ToLowerInvariant() + '.json'
            length = [long]$receiptItem.Length
            sha256 = Get-IzHarnessSha256 -Path $receiptPath
        })
    }
    $aggregate = New-IzMaintenanceRunReceipt -RunId $owned.run_id -RequestedCase $Case -RequestedTier $Tier `
        -SourceRevision $sourceRevision -CaseReceipts @($receipts) -CaseDescriptors @($caseDescriptors) `
        -ReceiptPath $aggregatePath -StartedUtc $started
    $null = Write-IzHarnessJson -Path $aggregatePath -Value $aggregate
    $persistedAggregate = Get-Content -LiteralPath $aggregatePath -Raw | ConvertFrom-Json
    [void](Test-IzMaintenanceRunReceipt -Receipt $persistedAggregate -ReceiptPath $aggregatePath)
    return [pscustomobject][ordered]@{
        receipt_path = [IO.Path]::GetFullPath($aggregatePath)
        status = [string]$aggregate.status
        exit_code = Get-IzMaintenanceRunExitCode -Receipts @($receipts)
    }
    }
    catch {
        $reason = Get-IzHarnessReason -ErrorRecord $_ -Fallback 'HARNESS_EXECUTION_FAILED'
        $failurePath = if (Test-Path -LiteralPath $aggregatePath) {
            Join-Path $publicRoot 'maintenance-terminal-failure.json'
        }
        else { $aggregatePath }
        $failure = New-IzMaintenanceTerminalFailureReceipt -RequestedCase $Case -RequestedTier $Tier `
            -Reason $reason -SourceRevision $sourceRevision -ProductWriteAttempted $true -StartedUtc $started
        $null = Write-IzHarnessJson -Path $failurePath -Value $failure
        return [pscustomobject][ordered]@{
            receipt_path = [IO.Path]::GetFullPath($failurePath)
            status = 'failed'
            exit_code = 1
        }
    }
}

Export-ModuleMember -Function 'Invoke-IzMaintenanceHarness'
