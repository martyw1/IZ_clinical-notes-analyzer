Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:ProductId = 'r3.iz-clinical-notes-analyzer.desktop'
$script:Tiers = @('Component', 'Package', 'Home', 'PowerLoss')
$script:TerminalStatuses = @('passed', 'failed', 'blocked')
$script:ReceiptKeys = @(
    'schema', 'run_id', 'case_id', 'requested_tier', 'required_tiers', 'status', 'reason',
    'source_revision', 'scenario', 'inputs', 'execution', 'observations', 'artifacts',
    'safety', 'cleanup', 'started_utc', 'completed_utc'
)
$script:InputKeys = @(
    'baseline_zip', 'original_beta4_zip', 'candidate_zip', 'candidate_build_receipt',
    'browser_channel', 'vm_control_manifest'
)
$script:ExecutionKeys = @(
    'executor', 'actual_installer', 'actual_executable', 'actual_browser',
    'actual_default_profile', 'actual_home_edition', 'actual_power_loss', 'synthetic_data_only'
)
$script:ObservationKeys = @('variant', 'status', 'invocation', 'observable', 'artifact')
$script:ArtifactKeys = @('kind', 'path', 'length', 'sha256')
$script:SafetyKeys = @(
    'owned_root_verified', 'current_user_scope', 'reparse_free', 'input_hashes_rechecked', 'redaction_scan'
)
$script:CleanupKeys = @(
    'status', 'owned_processes_remaining', 'owned_listeners_remaining', 'retained_private_artifacts'
)
$script:RunReceiptKeys = @(
    'schema', 'run_id', 'requested_case', 'requested_tier', 'source_revision',
    'required_case_ids', 'case_receipts', 'counts', 'status', 'reason',
    'started_utc', 'completed_utc'
)
$script:RunCaseIndexKeys = @('case_id', 'status', 'path', 'length', 'sha256')
$script:RunCountKeys = @('total', 'passed', 'failed', 'blocked')

function New-IzHarnessContractError {
    param([string]$Reason)
    $exception = [IO.InvalidDataException]::new($Reason)
    $exception.Data['iz_reason'] = $Reason
    return $exception
}

function Assert-IzHarnessExactKeys {
    param([object]$Value, [string[]]$Expected, [string]$Reason)
    if ($null -eq $Value) { throw (New-IzHarnessContractError $Reason) }
    $actual = @($Value.PSObject.Properties.Name | Sort-Object)
    $wanted = @($Expected | Sort-Object)
    if (@(Compare-Object $actual $wanted).Count -ne 0) { throw (New-IzHarnessContractError $Reason) }
}

function Get-IzMaintenanceCaseCatalog {
    $path = Join-Path $PSScriptRoot 'maintenance-cases.json'
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw (New-IzHarnessContractError 'CASE_CATALOG_MISSING')
    }
    $document = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    Assert-IzHarnessExactKeys $document @('schema', 'count', 'cases') 'CASE_CATALOG_SCHEMA_INVALID'
    if ($document.schema -cne 'iz-cna-maintenance-case-catalog-v1' -or $document.count -ne 63) {
        throw (New-IzHarnessContractError 'CASE_CATALOG_SCHEMA_INVALID')
    }
    $cases = @($document.cases)
    if ($cases.Count -ne 63) { throw (New-IzHarnessContractError 'CASE_CATALOG_COUNT_INVALID') }
    $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($case in $cases) {
        Assert-IzHarnessExactKeys $case @('id', 'tiers', 'scenario') 'CASE_DEFINITION_INVALID'
        if ($case.id -cnotmatch '^[BIURDAP][0-9]{2}$' -or -not $seen.Add([string]$case.id)) {
            throw (New-IzHarnessContractError 'CASE_ID_INVALID')
        }
        $tiers = @($case.tiers)
        if ($tiers.Count -lt 1 -or @($tiers | Where-Object { $_ -notin $script:Tiers }).Count -gt 0 -or
            @($tiers | Sort-Object -Unique).Count -ne $tiers.Count -or [string]::IsNullOrWhiteSpace($case.scenario)) {
            throw (New-IzHarnessContractError 'CASE_DEFINITION_INVALID')
        }
    }
    return $cases
}

function Get-IzMaintenanceCaseSelection {
    param(
        [Parameter(Mandatory)][string]$Case,
        [Parameter(Mandatory)][ValidateSet('Component', 'Package', 'Home', 'PowerLoss')][string]$Tier
    )
    $catalog = @(Get-IzMaintenanceCaseCatalog)
    if ($Case -ceq 'All') { return @($catalog | Where-Object { $_.tiers -contains $Tier }) }
    if ($Case -cnotmatch '^[BIURDAP][0-9]{2}$') { throw (New-IzHarnessContractError 'UNKNOWN_CASE_ID') }
    $selected = @($catalog | Where-Object { $_.id -ceq $Case })
    if ($selected.Count -ne 1) { throw (New-IzHarnessContractError 'UNKNOWN_CASE_ID') }
    if ($selected[0].tiers -notcontains $Tier) { throw (New-IzHarnessContractError 'CASE_TIER_MISMATCH') }
    return $selected
}

function New-IzHarnessInputs {
    param(
        [object]$BaselineZip = $null,
        [object]$OriginalBeta4Zip = $null,
        [object]$CandidateZip = $null,
        [object]$CandidateBuildReceipt = $null,
        [AllowNull()][string]$BrowserChannel = $null,
        [object]$VmControlManifest = $null
    )
    return [pscustomobject][ordered]@{
        baseline_zip = $BaselineZip
        original_beta4_zip = $OriginalBeta4Zip
        candidate_zip = $CandidateZip
        candidate_build_receipt = $CandidateBuildReceipt
        browser_channel = $BrowserChannel
        vm_control_manifest = $VmControlManifest
    }
}

function New-IzHarnessObservation {
    param(
        [Parameter(Mandatory)][string]$Variant,
        [Parameter(Mandatory)][ValidateSet('passed', 'failed', 'blocked')][string]$Status,
        [Parameter(Mandatory)][string]$Invocation,
        [Parameter(Mandatory)][string]$Observable,
        [Parameter(Mandatory)][string]$Artifact
    )
    return [pscustomobject][ordered]@{
        variant = $Variant; status = $Status; invocation = $Invocation
        observable = $Observable; artifact = $Artifact
    }
}

function New-IzHarnessArtifact {
    param([Parameter(Mandatory)][string]$Kind, [Parameter(Mandatory)][string]$Path)
    $fullPath = [IO.Path]::GetFullPath($Path)
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        throw (New-IzHarnessContractError 'ARTIFACT_MISSING')
    }
    $item = Get-Item -LiteralPath $fullPath
    if ($item.Length -le 0) { throw (New-IzHarnessContractError 'ARTIFACT_EMPTY') }
    return [pscustomobject][ordered]@{
        kind = $Kind
        path = $fullPath
        length = [long]$item.Length
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $fullPath).Hash.ToLowerInvariant()
    }
}

function Test-IzMaintenanceCaseReceipt {
    param([Parameter(Mandatory)][object]$Receipt)
    Assert-IzHarnessExactKeys $Receipt $script:ReceiptKeys 'CASE_RECEIPT_KEYS_INVALID'
    if ($Receipt.schema -cne 'iz-cna-maintenance-case-receipt-v1' -or
        $Receipt.run_id -cnotmatch '^cmd-[a-f0-9]{12}$' -or
        $Receipt.case_id -cnotmatch '^[BIURDAP][0-9]{2}$' -or
        $Receipt.requested_tier -notin $script:Tiers -or
        $Receipt.status -notin $script:TerminalStatuses -or
        $Receipt.reason -cnotmatch '^[A-Z][A-Z0-9_]{0,63}$' -or
        $Receipt.source_revision -cnotmatch '^[a-f0-9]{40}$') {
        throw (New-IzHarnessContractError 'CASE_RECEIPT_VALUE_INVALID')
    }
    $definition = @(Get-IzMaintenanceCaseCatalog | Where-Object id -eq $Receipt.case_id)
    if ($definition.Count -ne 1 -or $definition[0].tiers -notcontains $Receipt.requested_tier -or
        @(Compare-Object @($definition[0].tiers) @($Receipt.required_tiers)).Count -ne 0 -or
        $definition[0].scenario -cne $Receipt.scenario) {
        throw (New-IzHarnessContractError 'CASE_RECEIPT_DEFINITION_MISMATCH')
    }
    Assert-IzHarnessExactKeys $Receipt.inputs $script:InputKeys 'CASE_INPUT_KEYS_INVALID'
    Assert-IzHarnessExactKeys $Receipt.execution $script:ExecutionKeys 'CASE_EXECUTION_KEYS_INVALID'
    Assert-IzHarnessExactKeys $Receipt.safety $script:SafetyKeys 'CASE_SAFETY_KEYS_INVALID'
    Assert-IzHarnessExactKeys $Receipt.cleanup $script:CleanupKeys 'CASE_CLEANUP_KEYS_INVALID'
    foreach ($name in $script:ExecutionKeys | Where-Object { $_ -ne 'executor' }) {
        if ($Receipt.execution.$name -isnot [bool]) { throw (New-IzHarnessContractError 'CASE_EXECUTION_VALUE_INVALID') }
    }
    if ([string]::IsNullOrWhiteSpace($Receipt.execution.executor)) {
        throw (New-IzHarnessContractError 'CASE_EXECUTION_VALUE_INVALID')
    }
    if ($Receipt.execution.synthetic_data_only -ne $true) {
        throw (New-IzHarnessContractError 'CASE_EXECUTION_VALUE_INVALID')
    }
    if ($Receipt.status -ceq 'passed') {
        if ($Receipt.requested_tier -ceq 'Component' -and
            ($Receipt.execution.actual_default_profile -or $Receipt.execution.actual_home_edition -or $Receipt.execution.actual_power_loss)) {
            throw (New-IzHarnessContractError 'COMPONENT_TIER_OVERCLAIM')
        }
        if ($Receipt.requested_tier -in @('Package', 'Home') -and
            (-not $Receipt.execution.actual_installer -or -not $Receipt.execution.actual_default_profile)) {
            throw (New-IzHarnessContractError 'PACKAGE_TIER_UNDERPROVEN')
        }
        if ($Receipt.requested_tier -ceq 'Home' -and -not $Receipt.execution.actual_home_edition) {
            throw (New-IzHarnessContractError 'HOME_TIER_UNDERPROVEN')
        }
        if ($Receipt.requested_tier -ceq 'PowerLoss' -and -not $Receipt.execution.actual_power_loss) {
            throw (New-IzHarnessContractError 'POWERLOSS_TIER_UNDERPROVEN')
        }
        if ($Receipt.requested_tier -ceq 'PowerLoss' -and
            (-not $Receipt.execution.actual_installer -or -not $Receipt.execution.actual_executable -or
             -not $Receipt.execution.actual_default_profile -or -not $Receipt.execution.actual_home_edition)) {
            throw (New-IzHarnessContractError 'POWERLOSS_TIER_UNDERPROVEN')
        }
    }
    $observations = @($Receipt.observations)
    $artifacts = @($Receipt.artifacts)
    if ($observations.Count -lt 1 -or $artifacts.Count -lt 1) {
        throw (New-IzHarnessContractError 'CASE_EVIDENCE_REQUIRED')
    }
    foreach ($observation in $observations) {
        Assert-IzHarnessExactKeys $observation $script:ObservationKeys 'CASE_OBSERVATION_KEYS_INVALID'
        if ($observation.status -notin $script:TerminalStatuses -or [string]::IsNullOrWhiteSpace($observation.invocation) -or
            [string]::IsNullOrWhiteSpace($observation.observable) -or [string]::IsNullOrWhiteSpace($observation.artifact)) {
            throw (New-IzHarnessContractError 'CASE_OBSERVATION_VALUE_INVALID')
        }
    }
    if ($Receipt.status -ceq 'passed' -and @($observations | Where-Object status -cne passed).Count -ne 0) {
        throw (New-IzHarnessContractError 'CASE_PASSED_WITH_NONPASSING_OBSERVATION')
    }
    foreach ($artifact in $artifacts) {
        Assert-IzHarnessExactKeys $artifact $script:ArtifactKeys 'CASE_ARTIFACT_KEYS_INVALID'
        if ($artifact.length -le 0 -or $artifact.sha256 -cnotmatch '^[a-f0-9]{64}$' -or
            -not (Test-Path -LiteralPath $artifact.path -PathType Leaf)) {
            throw (New-IzHarnessContractError 'CASE_ARTIFACT_VALUE_INVALID')
        }
        $item = Get-Item -LiteralPath $artifact.path
        if ($item.Length -ne $artifact.length -or
            (Get-FileHash -Algorithm SHA256 -LiteralPath $artifact.path).Hash.ToLowerInvariant() -cne $artifact.sha256) {
            throw (New-IzHarnessContractError 'CASE_ARTIFACT_DIGEST_MISMATCH')
        }
    }
    $artifactPaths = @($artifacts.path | ForEach-Object { [IO.Path]::GetFullPath([string]$_) })
    foreach ($observation in $observations) {
        if ([IO.Path]::GetFullPath([string]$observation.artifact) -notin $artifactPaths) {
            throw (New-IzHarnessContractError 'CASE_OBSERVATION_ARTIFACT_UNBOUND')
        }
    }
    if ($Receipt.status -ceq 'passed' -and
        (-not $Receipt.safety.owned_root_verified -or -not $Receipt.safety.current_user_scope -or
         -not $Receipt.safety.reparse_free -or -not $Receipt.safety.input_hashes_rechecked -or
         $Receipt.safety.redaction_scan -cne 'passed')) {
        throw (New-IzHarnessContractError 'CASE_PASSED_WITH_FAILED_SAFETY')
    }
    if ($Receipt.status -ceq 'passed' -and
        ($Receipt.cleanup.status -cne 'passed' -or [int]$Receipt.cleanup.owned_processes_remaining -ne 0 -or
         [int]$Receipt.cleanup.owned_listeners_remaining -ne 0)) {
        throw (New-IzHarnessContractError 'CASE_PASSED_WITH_FAILED_CLEANUP')
    }
    foreach ($timestamp in @($Receipt.started_utc, $Receipt.completed_utc)) {
        $parsed = [DateTimeOffset]::MinValue
        if (-not [DateTimeOffset]::TryParseExact($timestamp, 'o', [Globalization.CultureInfo]::InvariantCulture,
                [Globalization.DateTimeStyles]::RoundtripKind, [ref]$parsed)) {
            throw (New-IzHarnessContractError 'CASE_TIMESTAMP_INVALID')
        }
    }
    return $true
}

function New-IzMaintenanceCaseReceipt {
    param(
        [Parameter(Mandatory)][string]$RunId,
        [Parameter(Mandatory)][object]$CaseDefinition,
        [Parameter(Mandatory)][string]$RequestedTier,
        [Parameter(Mandatory)][string]$Status,
        [Parameter(Mandatory)][string]$Reason,
        [Parameter(Mandatory)][string]$SourceRevision,
        [Parameter(Mandatory)][object]$Inputs,
        [Parameter(Mandatory)][object]$Execution,
        [Parameter(Mandatory)][object[]]$Observations,
        [Parameter(Mandatory)][object[]]$Artifacts,
        [Parameter(Mandatory)][object]$Safety,
        [Parameter(Mandatory)][object]$Cleanup,
        [string]$StartedUtc = ([DateTime]::UtcNow.ToString('o'))
    )
    if ($CaseDefinition.tiers -notcontains $RequestedTier) {
        throw (New-IzHarnessContractError 'CASE_TIER_MISMATCH')
    }
    $receipt = [pscustomobject][ordered]@{
        schema = 'iz-cna-maintenance-case-receipt-v1'
        run_id = $RunId
        case_id = $CaseDefinition.id
        requested_tier = $RequestedTier
        required_tiers = @($CaseDefinition.tiers)
        status = $Status
        reason = $Reason
        source_revision = $SourceRevision
        scenario = $CaseDefinition.scenario
        inputs = $Inputs
        execution = $Execution
        observations = @($Observations)
        artifacts = @($Artifacts)
        safety = $Safety
        cleanup = $Cleanup
        started_utc = $StartedUtc
        completed_utc = [DateTime]::UtcNow.ToString('o')
    }
    $null = Test-IzMaintenanceCaseReceipt -Receipt $receipt
    return $receipt
}

function Get-IzMaintenanceRunExitCode {
    param([Parameter(Mandatory)][object[]]$Receipts)
    if (@($Receipts | Where-Object status -eq failed).Count -gt 0) { return 1 }
    if (@($Receipts | Where-Object status -eq blocked).Count -gt 0) { return 2 }
    return 0
}

function Test-IzMaintenanceRunReceipt {
    param(
        [Parameter(Mandatory)][object]$Receipt,
        [Parameter(Mandatory)][string]$ReceiptPath
    )
    Assert-IzHarnessExactKeys $Receipt $script:RunReceiptKeys 'RUN_RECEIPT_KEYS_INVALID'
    if ($Receipt.schema -cne 'iz-cna-maintenance-run-receipt-v1' -or
        $Receipt.run_id -cnotmatch '^cmd-[a-f0-9]{12}$' -or
        $Receipt.requested_tier -notin $script:Tiers -or
        $Receipt.source_revision -cnotmatch '^[a-f0-9]{40}$' -or
        $Receipt.status -notin $script:TerminalStatuses) {
        throw (New-IzHarnessContractError 'RUN_RECEIPT_VALUE_INVALID')
    }
    $selection = @(Get-IzMaintenanceCaseSelection -Case ([string]$Receipt.requested_case) -Tier ([string]$Receipt.requested_tier))
    $expectedIds = @($selection.id)
    $requiredIds = @($Receipt.required_case_ids)
    if (($requiredIds -join "`n") -cne ($expectedIds -join "`n")) {
        throw (New-IzHarnessContractError 'RUN_REQUIRED_CASE_SET_INVALID')
    }
    Assert-IzHarnessExactKeys $Receipt.counts $script:RunCountKeys 'RUN_COUNTS_INVALID'
    $indices = @($Receipt.case_receipts)
    if ($indices.Count -ne $expectedIds.Count) { throw (New-IzHarnessContractError 'RUN_CASE_INDEX_INVALID') }
    $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $runRoot = [IO.Path]::GetFullPath((Split-Path ([IO.Path]::GetFullPath($ReceiptPath)) -Parent)).TrimEnd('\')
    for ($index = 0; $index -lt $indices.Count; $index++) {
        $entry = $indices[$index]
        Assert-IzHarnessExactKeys $entry $script:RunCaseIndexKeys 'RUN_CASE_INDEX_KEYS_INVALID'
        $caseId = [string]$entry.case_id
        $expectedRelative = 'cases/' + $caseId.ToLowerInvariant() + '.json'
        if ($caseId -cne $expectedIds[$index] -or -not $seen.Add($caseId) -or
            $entry.status -notin $script:TerminalStatuses -or $entry.path -cne $expectedRelative -or
            [long]$entry.length -le 0 -or $entry.sha256 -cnotmatch '^[a-f0-9]{64}$') {
            throw (New-IzHarnessContractError 'RUN_CASE_INDEX_INVALID')
        }
        $casePath = [IO.Path]::GetFullPath((Join-Path $runRoot $entry.path.Replace('/', '\')))
        if (-not $casePath.StartsWith($runRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or
            -not (Test-Path -LiteralPath $casePath -PathType Leaf)) {
            throw (New-IzHarnessContractError 'RUN_CASE_FILE_INVALID')
        }
        $caseItem = Get-Item -LiteralPath $casePath -Force
        if (($caseItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            [long]$caseItem.Length -ne [long]$entry.length -or
            (Get-FileHash -LiteralPath $casePath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.sha256) {
            throw (New-IzHarnessContractError 'RUN_CASE_FILE_INVALID')
        }
        try { $caseReceipt = Get-Content -LiteralPath $casePath -Raw | ConvertFrom-Json }
        catch { throw (New-IzHarnessContractError 'RUN_CASE_FILE_INVALID') }
        [void](Test-IzMaintenanceCaseReceipt -Receipt $caseReceipt)
        if ($caseReceipt.run_id -cne $Receipt.run_id -or $caseReceipt.case_id -cne $caseId -or
            $caseReceipt.requested_tier -cne $Receipt.requested_tier -or
            $caseReceipt.source_revision -cne $Receipt.source_revision -or
            $caseReceipt.status -cne $entry.status) {
            throw (New-IzHarnessContractError 'RUN_CASE_BODY_MISMATCH')
        }
        foreach ($artifact in @($caseReceipt.artifacts)) {
            $artifactPath = [IO.Path]::GetFullPath([string]$artifact.path)
            if (-not $artifactPath.StartsWith($runRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
                throw (New-IzHarnessContractError 'RUN_CASE_ARTIFACT_OUTSIDE_ROOT')
            }
        }
    }
    $actualCounts = [ordered]@{
        total = $indices.Count
        passed = @($indices | Where-Object status -ceq passed).Count
        failed = @($indices | Where-Object status -ceq failed).Count
        blocked = @($indices | Where-Object status -ceq blocked).Count
    }
    foreach ($name in $script:RunCountKeys) {
        $recorded = $Receipt.counts.PSObject.Properties[$name].Value
        if ([int]$recorded -ne [int]$actualCounts[$name]) {
            throw (New-IzHarnessContractError 'RUN_COUNTS_INVALID')
        }
    }
    $expectedStatus = if ($actualCounts.failed -gt 0) { 'failed' } elseif ($actualCounts.blocked -gt 0) { 'blocked' } else { 'passed' }
    $expectedReason = if ($expectedStatus -ceq 'passed') { 'CASES_PASSED' } elseif ($expectedStatus -ceq 'failed') { 'CASES_FAILED' } else { 'CASES_BLOCKED' }
    if ($Receipt.status -cne $expectedStatus -or $Receipt.reason -cne $expectedReason) {
        throw (New-IzHarnessContractError 'RUN_STATUS_INVALID')
    }
    foreach ($timestamp in @($Receipt.started_utc, $Receipt.completed_utc)) {
        $parsed = [DateTimeOffset]::MinValue
        if (-not [DateTimeOffset]::TryParseExact($timestamp, 'o', [Globalization.CultureInfo]::InvariantCulture,
                [Globalization.DateTimeStyles]::RoundtripKind, [ref]$parsed)) {
            throw (New-IzHarnessContractError 'RUN_TIMESTAMP_INVALID')
        }
    }
    return $true
}

function New-IzMaintenanceRunReceipt {
    param(
        [Parameter(Mandatory)][string]$RunId,
        [Parameter(Mandatory)][string]$RequestedCase,
        [Parameter(Mandatory)][string]$RequestedTier,
        [Parameter(Mandatory)][string]$SourceRevision,
        [Parameter(Mandatory)][object[]]$CaseReceipts,
        [Parameter(Mandatory)][object[]]$CaseDescriptors,
        [Parameter(Mandatory)][string]$ReceiptPath,
        [string]$StartedUtc = ([DateTime]::UtcNow.ToString('o'))
    )
    $selection = @(Get-IzMaintenanceCaseSelection -Case $RequestedCase -Tier $RequestedTier)
    $status = if (@($CaseReceipts | Where-Object status -ceq failed).Count) { 'failed' } `
        elseif (@($CaseReceipts | Where-Object status -ceq blocked).Count) { 'blocked' } else { 'passed' }
    $receipt = [pscustomobject][ordered]@{
        schema = 'iz-cna-maintenance-run-receipt-v1'
        run_id = $RunId
        requested_case = $RequestedCase
        requested_tier = $RequestedTier
        source_revision = $SourceRevision
        required_case_ids = @($selection.id)
        case_receipts = @($CaseDescriptors)
        counts = [pscustomobject][ordered]@{
            total = $CaseReceipts.Count
            passed = @($CaseReceipts | Where-Object status -ceq passed).Count
            failed = @($CaseReceipts | Where-Object status -ceq failed).Count
            blocked = @($CaseReceipts | Where-Object status -ceq blocked).Count
        }
        status = $status
        reason = if ($status -ceq 'passed') { 'CASES_PASSED' } elseif ($status -ceq 'failed') { 'CASES_FAILED' } else { 'CASES_BLOCKED' }
        started_utc = $StartedUtc
        completed_utc = [DateTime]::UtcNow.ToString('o')
    }
    [void](Test-IzMaintenanceRunReceipt -Receipt $receipt -ReceiptPath $ReceiptPath)
    return $receipt
}

function New-IzMaintenanceTerminalFailureReceipt {
    param(
        [Parameter(Mandatory)][string]$RequestedCase,
        [Parameter(Mandatory)][string]$RequestedTier,
        [Parameter(Mandatory)][string]$Reason,
        [AllowNull()][string]$SourceRevision,
        [bool]$ProductWriteAttempted = $false,
        [string]$StartedUtc = ([DateTime]::UtcNow.ToString('o'))
    )
    return [pscustomobject][ordered]@{
        schema = 'iz-cna-maintenance-terminal-failure-v1'
        requested_case = $RequestedCase
        requested_tier = $RequestedTier
        status = 'failed'
        reason = $Reason
        source_revision = $SourceRevision
        product_write_attempted = $ProductWriteAttempted
        started_utc = $StartedUtc
        completed_utc = [DateTime]::UtcNow.ToString('o')
    }
}

function Write-IzHarnessJson {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][object]$Value)
    $fullPath = [IO.Path]::GetFullPath($Path)
    if (Test-Path -LiteralPath $fullPath) { throw (New-IzHarnessContractError 'EVIDENCE_ALREADY_EXISTS') }
    $json = $Value | ConvertTo-Json -Depth 30
    $privateValues = @(Get-ChildItem Env: | Where-Object {
        $_.Name -match '(?i)(PASSWORD|SECRET|TOKEN|API.?KEY|CREDENTIAL)' -and $_.Value.Length -ge 8
    } | ForEach-Object { $_.Value })
    if (@($privateValues | Where-Object { $json.Contains($_) }).Count -gt 0 -or
        $json -match '"(access_token|password_hash|current_password|new_password|client_secret|api_key)"\s*:') {
        throw (New-IzHarnessContractError 'PRIVATE_VALUE_IN_EVIDENCE')
    }
    $parent = Split-Path -Parent $fullPath
    if (-not (Test-Path -LiteralPath $parent)) { $null = New-Item -ItemType Directory -Path $parent -Force }
    $temporary = Join-Path $parent ('.' + [IO.Path]::GetFileName($fullPath) + '.' + [Guid]::NewGuid().ToString('N') + '.tmp')
    [IO.File]::WriteAllText($temporary, $json, [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $fullPath
    return $fullPath
}

Export-ModuleMember -Function @(
    'Get-IzMaintenanceCaseCatalog', 'Get-IzMaintenanceCaseSelection', 'New-IzHarnessInputs',
    'New-IzHarnessObservation', 'New-IzHarnessArtifact', 'New-IzMaintenanceCaseReceipt',
    'Test-IzMaintenanceCaseReceipt', 'New-IzMaintenanceRunReceipt', 'Test-IzMaintenanceRunReceipt',
    'New-IzMaintenanceTerminalFailureReceipt', 'Get-IzMaintenanceRunExitCode', 'Write-IzHarnessJson'
)
