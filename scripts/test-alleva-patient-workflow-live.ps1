[CmdletBinding()]
param(
    [string]$BaseUrl = 'http://127.0.0.1:8765',
    [string]$AccessToken = $env:IZ_CNA_QA_ACCESS_TOKEN,
    [string]$EvidencePath = '',
    [string]$DatabasePath = '',
    [string]$PythonPath = '',
    [string]$ReferenceMrn = '',
    [int]$PollTimeoutSeconds = 1200,
    [switch]$ReuseCompletedSync,
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-SafeEvidence {
    param(
        [hashtable]$Evidence,
        [switch]$Quiet
    )

    $allowedKeys = @(
        'self_test_passed', 'gate_configured', 'gate_authorized', 'gate_trusted',
        'gate_mapping_valid', 'mapping_hash', 'terminal_status', 'client_count',
        'patient_count', 'global_plan_count', 'linked_plan_count',
        'unlinked_plan_count', 'patient_only_count', 'six_plan_patient_count',
        'maximum_plans_per_patient', 'reference_case_valid', 'accounted_plan_count',
        'linkage_valid', 'patient_plan_order_valid', 'plan_roster_order_valid',
        'patient_detail_contracts_valid', 'plan_detail_contracts_valid',
        'patient_detail_check_count', 'plan_detail_check_count',
        'display_label_consistency_valid', 'encrypted_snapshot_count',
        'encrypted_snapshot_envelopes_valid', 'snapshot_schema_versions_valid',
        'audit_privacy_valid', 'duration_seconds'
    )
    foreach ($key in $Evidence.Keys) {
        if ($key -notin $allowedKeys) {
            throw 'Live workflow evidence contains a non-allowlisted key.'
        }
    }
    foreach ($value in $Evidence.Values) {
        if ($value -is [string] -and $value -notin @('', 'completed', 'completed_with_warnings') -and $value -notmatch '^[0-9a-f]{64}$') {
            throw 'Live workflow evidence contains a non-allowlisted string value.'
        }
    }
    $json = $Evidence | ConvertTo-Json -Depth 4 -Compress
    if ($json -match '(?i)bearer|IZCNA1:|/clients/|@') {
        throw 'Live workflow evidence failed its privacy check.'
    }
    if ($EvidencePath) {
        $parent = Split-Path -Parent $EvidencePath
        if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        [System.IO.File]::WriteAllText($EvidencePath, $json, [System.Text.UTF8Encoding]::new($false))
    }
    if (-not $Quiet) { Write-Output $json }
}

function Invoke-Api {
    param(
        [ValidateSet('GET', 'POST')][string]$Method,
        [string]$Path,
        [hashtable]$Headers
    )
    try {
        return Invoke-RestMethod -Method $Method -Uri ($BaseUrl.TrimEnd('/') + $Path) -Headers $Headers -TimeoutSec 120
    }
    catch {
        throw "Live workflow API request failed for $Method $Path."
    }
}

function Get-UpdatedInstant {
    param([object]$Value)
    $parsed = [DateTimeOffset]::MinValue
    if ($null -ne $Value -and [DateTimeOffset]::TryParse([string]$Value, [ref]$parsed)) {
        return $parsed.ToUniversalTime()
    }
    return [DateTimeOffset]::MinValue
}

function Test-DescendingUpdated {
    param([object[]]$Items)
    $previous = [DateTimeOffset]::MaxValue
    foreach ($item in $Items) {
        $current = Get-UpdatedInstant $item.last_updated
        if ($current -gt $previous) { return $false }
        $previous = $current
    }
    return $true
}

if ($SelfTest) {
    if (-not (Test-DescendingUpdated @(
        [pscustomobject]@{ last_updated = '2026-01-02T00:00:00Z' },
        [pscustomobject]@{ last_updated = '2026-01-01T00:00:00Z' },
        [pscustomobject]@{ last_updated = '' }
    ))) {
        throw 'Live workflow self-test failed descending timestamp validation.'
    }
    $completedAccepted = $false
    try {
        Write-SafeEvidence @{ terminal_status = 'completed'; linkage_valid = $true } -Quiet
        $completedAccepted = $true
    }
    catch {}
    $blockedRejected = $false
    try { Write-SafeEvidence @{ terminal_status = 'blocked' } -Quiet }
    catch { $blockedRejected = $true }
    $failedRejected = $false
    try { Write-SafeEvidence @{ terminal_status = 'failed' } -Quiet }
    catch { $failedRejected = $true }
    $malformedRejected = $false
    try { Write-SafeEvidence @{ unexpected_payload = $true } -Quiet }
    catch { $malformedRejected = $true }
    $sensitiveRejected = $false
    try { Write-SafeEvidence @{ terminal_status = 'Synthetic Patient Example' } -Quiet }
    catch { $sensitiveRejected = $true }
    if (-not ($completedAccepted -and $blockedRejected -and $failedRejected -and $malformedRejected -and $sensitiveRejected)) {
        throw 'Live workflow self-test failed terminal or privacy validation.'
    }
    Write-SafeEvidence @{ self_test_passed = $true }
    exit 0
}

if (-not $AccessToken) { throw 'IZ_CNA_QA_ACCESS_TOKEN or -AccessToken is required.' }
$startedAt = [DateTimeOffset]::UtcNow
$headers = @{ Authorization = "Bearer $AccessToken" }

$configuration = Invoke-Api -Method GET -Path '/api/api-configuration' -Headers $headers
$gateConfigured = [bool]$configuration.client_id_configured -and [bool]$configuration.client_secret_configured -and [bool]$configuration.api_enabled
$gateAuthorized = [bool]$configuration.treatment_plan_sync_enabled -and [bool]$configuration.treatment_plan_sync_approved
$apiOrigin = [Uri]$configuration.api_base_url
$tokenOrigin = [Uri]$configuration.token_url
$gateTrusted = $apiOrigin.Scheme -eq 'https' -and $tokenOrigin.Scheme -eq 'https' -and (
    $apiOrigin.Host -eq 'allevasoft.com' -or $apiOrigin.Host.EndsWith('.allevasoft.com', [StringComparison]::OrdinalIgnoreCase)
) -and (
    $tokenOrigin.Host -eq 'allevasoft.com' -or $tokenOrigin.Host.EndsWith('.allevasoft.com', [StringComparison]::OrdinalIgnoreCase)
)
$gateMappingValid = -not [string]::IsNullOrWhiteSpace([string]$configuration.active_contract_version)
if (-not $gateConfigured -or -not $gateAuthorized -or -not $gateTrusted) { throw 'Live workflow gates are not configured, authorized, and trusted.' }

$job = if ($ReuseCompletedSync) {
    Invoke-Api -Method GET -Path '/api/v2/alleva-sync-last-run' -Headers $headers
}
else {
    Invoke-Api -Method POST -Path '/api/v2/alleva-sync/run' -Headers $headers
}
if (-not $ReuseCompletedSync) {
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($PollTimeoutSeconds)
    do {
        Start-Sleep -Seconds 2
        $job = Invoke-Api -Method GET -Path ("/api/v2/alleva-sync/jobs/{0}" -f [Uri]::EscapeDataString([string]$job.job_id)) -Headers $headers
        if ($job.status -in @('completed', 'completed_with_warnings', 'failed', 'cancelled')) { break }
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
}
if ($job.status -notin @('completed', 'completed_with_warnings')) { throw 'Live workflow sync did not complete successfully.' }
$configuration = Invoke-Api -Method GET -Path '/api/api-configuration' -Headers $headers
$gateMappingValid = -not [string]::IsNullOrWhiteSpace([string]$configuration.active_contract_version)

$patientItems = @((Invoke-Api -Method GET -Path '/api/v2/patient-roster' -Headers $headers).items)
$planItems = @((Invoke-Api -Method GET -Path '/api/v2/treatment-plan-roster' -Headers $headers).items)
$patientKeys = @{}
foreach ($patient in $patientItems) { $patientKeys[[string]$patient.mrn] = $patient }

$linkedPlans = @($planItems | Where-Object { [bool]$_.linked_to_mrn })
$unlinkedPlans = @($planItems | Where-Object { -not [bool]$_.linked_to_mrn })
$plansByPatient = @{}
foreach ($plan in $linkedPlans) {
    $key = [string]$plan.mrn
    if (-not $plansByPatient.ContainsKey($key)) { $plansByPatient[$key] = [System.Collections.Generic.List[object]]::new() }
    $plansByPatient[$key].Add($plan)
}

$linkageValid = $true
$patientPlanOrderValid = $true
foreach ($patient in $patientItems) {
    $key = [string]$patient.mrn
    $rosterPlans = @($patient.treatment_plans)
    $globalPlans = if ($plansByPatient.ContainsKey($key)) { @($plansByPatient[$key]) } else { @() }
    if (-not (Test-DescendingUpdated $rosterPlans)) { $patientPlanOrderValid = $false }
    $rosterIds = @($rosterPlans | ForEach-Object { [string]$_.treatment_plan_id } | Sort-Object)
    $globalIds = @($globalPlans | ForEach-Object { [string]$_.treatment_plan_id } | Sort-Object)
    if (($rosterIds -join '|') -ne ($globalIds -join '|')) { $linkageValid = $false }
}
foreach ($plan in $linkedPlans) {
    if (-not $patientKeys.ContainsKey([string]$plan.mrn)) { $linkageValid = $false }
}

$patientDetailContractsValid = $true
$planDetailContractsValid = $true
$displayLabelConsistencyValid = $true
$patientDetailCandidates = @(
    @($patientItems | Select-Object -First 2)
    @($patientItems | Where-Object { @($_.treatment_plans).Count -eq 0 } | Select-Object -First 2)
    @($patientItems | Where-Object { @($_.treatment_plans).Count -eq 6 })
)
if ($ReferenceMrn) {
    $patientDetailCandidates += @($patientItems | Where-Object { [string]$_.mrn -eq $ReferenceMrn } | Select-Object -First 1)
}
$deduplicatedPatients = @{}
foreach ($patient in $patientDetailCandidates) {
    if ($null -ne $patient) { $deduplicatedPatients[[string]$patient.mrn] = $patient }
}
foreach ($patient in $deduplicatedPatients.Values) {
    $encodedKey = [Uri]::EscapeDataString([string]$patient.mrn)
    $encodedMode = [Uri]::EscapeDataString([string]$patient.source_mode)
    $detail = Invoke-Api -Method GET -Path ("/api/v2/patients/$encodedKey`?source_mode=$encodedMode") -Headers $headers
    if ([string]$detail.mrn -ne [string]$patient.mrn -or $null -eq $detail.patient_record) { $patientDetailContractsValid = $false }
    if ([string]$detail.full_name -ne [string]$patient.full_name) { $displayLabelConsistencyValid = $false }
}
$sixPlanPatientKeys = @{}
foreach ($patient in $patientItems | Where-Object { @($_.treatment_plans).Count -eq 6 }) {
    $sixPlanPatientKeys[[string]$patient.mrn] = $true
}
$planDetailCandidates = @(
    @($linkedPlans | Select-Object -First 2)
    @($unlinkedPlans | Select-Object -First 2)
    @($linkedPlans | Where-Object { $sixPlanPatientKeys.ContainsKey([string]$_.mrn) })
)
$deduplicatedPlans = @{}
foreach ($plan in $planDetailCandidates) {
    if ($null -ne $plan) {
        $deduplicatedPlans[([string]$plan.patient_key + '|' + [string]$plan.treatment_plan_id)] = $plan
    }
}
foreach ($plan in $deduplicatedPlans.Values) {
    $encodedKey = [Uri]::EscapeDataString([string]$plan.patient_key)
    $encodedPlan = [Uri]::EscapeDataString([string]$plan.treatment_plan_id)
    $encodedMode = 'alleva_rest_api'
    $detail = Invoke-Api -Method GET -Path ("/api/v2/treatment-plans/$encodedKey/$encodedPlan`?source_mode=$encodedMode") -Headers $headers
    if ([string]$detail.content_snapshot.plan_id -ne [string]$plan.treatment_plan_id) { $planDetailContractsValid = $false }
    if ([bool]$plan.linked_to_mrn -and [string]$detail.patient_full_name -ne [string]$plan.full_name) { $displayLabelConsistencyValid = $false }
}

$auditItems = @((Invoke-Api -Method GET -Path '/api/audit/logs?limit=10000' -Headers $headers).items | Where-Object {
    (Get-UpdatedInstant $_.timestamp_utc) -ge $startedAt
})
$auditText = $auditItems | ConvertTo-Json -Depth 20 -Compress
$auditPrivacyValid = $true
foreach ($patient in $patientItems) {
    foreach ($protectedValue in @([string]$patient.mrn, [string]$patient.full_name)) {
        if ($protectedValue -and $auditText.Contains($protectedValue, [StringComparison]::Ordinal)) { $auditPrivacyValid = $false }
    }
}

$snapshotCount = 0
$snapshotEnvelopesValid = $false
$snapshotVersionsValid = $false
$mappingHash = ''
if ($DatabasePath -and $PythonPath) {
    $databaseMetadata = & $PythonPath -c @'
import json
import sqlite3
import sys

connection = sqlite3.connect(sys.argv[1])
rows = connection.execute(
    "SELECT snapshot_schema_version,snapshot_encrypted FROM patient_snapshot_versions ORDER BY id"
).fetchall()
mapping = connection.execute(
    "SELECT contract_sha256 FROM alleva_contract_approvals "
    "WHERE revoked_at IS NULL ORDER BY id DESC LIMIT 1"
).fetchone()
connection.close()
print(json.dumps({
    "count": len(rows),
    "envelopes_valid": bool(rows) and all(bytes(row[1]).startswith(b"IZCNA1:") for row in rows),
    "versions_valid": bool(rows) and all(int(row[0]) == 1 for row in rows),
    "mapping_hash": str(mapping[0]) if mapping else "",
}))
'@ $DatabasePath | ConvertFrom-Json
    $snapshotCount = [int]$databaseMetadata.count
    $snapshotEnvelopesValid = [bool]$databaseMetadata.envelopes_valid
    $snapshotVersionsValid = [bool]$databaseMetadata.versions_valid
    $mappingHash = [string]$databaseMetadata.mapping_hash
}

$planCounts = @($patientItems | ForEach-Object { @($_.treatment_plans).Count })
$referenceCaseValid = $true
if ($ReferenceMrn) {
    $reference = $patientItems | Where-Object { [string]$_.mrn -eq $ReferenceMrn } | Select-Object -First 1
    $referenceCaseValid = $null -ne $reference -and @($reference.treatment_plans).Count -eq 6
}
$evidence = @{
    gate_configured = $gateConfigured
    gate_authorized = $gateAuthorized
    gate_trusted = $gateTrusted
    gate_mapping_valid = $gateMappingValid
    mapping_hash = $mappingHash
    terminal_status = [string]$job.status
    client_count = $patientItems.Count
    patient_count = $patientItems.Count
    global_plan_count = $planItems.Count
    linked_plan_count = $linkedPlans.Count
    unlinked_plan_count = $unlinkedPlans.Count
    patient_only_count = @($patientItems | Where-Object { @($_.treatment_plans).Count -eq 0 }).Count
    six_plan_patient_count = @($patientItems | Where-Object { @($_.treatment_plans).Count -eq 6 }).Count
    maximum_plans_per_patient = if ($planCounts) { [int](($planCounts | Measure-Object -Maximum).Maximum) } else { 0 }
    reference_case_valid = $referenceCaseValid
    accounted_plan_count = $linkedPlans.Count + $unlinkedPlans.Count
    linkage_valid = $linkageValid -and ($planItems.Count -eq ($linkedPlans.Count + $unlinkedPlans.Count))
    patient_plan_order_valid = $patientPlanOrderValid
    plan_roster_order_valid = Test-DescendingUpdated $planItems
    patient_detail_contracts_valid = $patientDetailContractsValid
    plan_detail_contracts_valid = $planDetailContractsValid
    patient_detail_check_count = $deduplicatedPatients.Count
    plan_detail_check_count = $deduplicatedPlans.Count
    display_label_consistency_valid = $displayLabelConsistencyValid
    encrypted_snapshot_count = $snapshotCount
    encrypted_snapshot_envelopes_valid = $snapshotEnvelopesValid
    snapshot_schema_versions_valid = $snapshotVersionsValid
    audit_privacy_valid = $auditPrivacyValid
    duration_seconds = [int]([DateTimeOffset]::UtcNow - $startedAt).TotalSeconds
}
Write-SafeEvidence $evidence
