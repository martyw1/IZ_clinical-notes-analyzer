[CmdletBinding()]
param(
    [string]$RepositoryRoot = "",
    [string]$ExpectedHead = "",
    [switch]$AllowDirty,
    [switch]$SelfTestOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Stop-Safe {
    param(
        [Parameter(Mandatory)]
        [string]$Reason,
        [int]$ExitCode = 2
    )

    Write-Output "result=FAIL"
    Write-Output "reason=$Reason"
    exit $ExitCode
}

function Assert-GitResult {
    param(
        [Parameter(Mandatory)]
        [int]$ExitCode,
        [AllowEmptyCollection()]
        [string[]]$Output = @()
    )

    if ($ExitCode -ne 0) {
        throw "git_metadata_command_failed"
    }

    return @($Output)
}

function Invoke-GitMetadata {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $commandOutput = @(& git -C $script:ResolvedRepositoryRoot @Arguments 2>$null)
    $commandExitCode = $LASTEXITCODE
    return @(Assert-GitResult -ExitCode $commandExitCode -Output $commandOutput)
}

function ConvertFrom-TreeMetadata {
    param(
        [Parameter(Mandatory)]
        [string]$Record
    )

    if ($Record -notmatch "^(?<mode>[0-9]{6})\s+blob\s+(?<oid>[0-9a-f]{40})\s+(?<size>[0-9]+)\t(?<path>.+)$") {
        throw "malformed_tree_metadata"
    }

    $extension = [System.IO.Path]::GetExtension($Matches.path).TrimStart(".").ToLowerInvariant()
    $category = switch ($extension) {
        "csv" { "clinical-export.csv" }
        "json" { "clinical-export.json" }
        default { "clinical-export.other" }
    }

    return [pscustomobject]@{
        Category = $category
        ObjectId = $Matches.oid
        Size = [int64]$Matches.size
    }
}

function Test-MalformedInputSuppression {
    try {
        $null = ConvertFrom-TreeMetadata -Record "not-git-tree-metadata"
        return $false
    }
    catch {
        return $_.Exception.Message -eq "malformed_tree_metadata"
    }
}

function Test-MisleadingSuccessSuppression {
    try {
        $null = Assert-GitResult -ExitCode 23 -Output @("result=PASS")
        return $false
    }
    catch {
        return $_.Exception.Message -eq "git_metadata_command_failed"
    }
}

function Test-PrivacyCanarySuppression {
    $syntheticSecretCanary = "SYNTHETIC_SECRET_CANARY_73A19"
    $syntheticPhiCanary = "SYNTHETIC_PHI_CANARY_46B27"
    $syntheticRecord = "100644 blob 0000000000000000000000000000000000000000 128`t" +
        "diag-build-tools/exports/$syntheticPhiCanary-$syntheticSecretCanary.csv"
    $safeRecord = ConvertFrom-TreeMetadata -Record $syntheticRecord
    $safeOutput = "category=$($safeRecord.Category) count=1 blob=$($safeRecord.ObjectId) size=$($safeRecord.Size)"

    return -not (
        $safeOutput.IndexOf($syntheticSecretCanary, [System.StringComparison]::Ordinal) -ge 0 -or
        $safeOutput.IndexOf($syntheticPhiCanary, [System.StringComparison]::Ordinal) -ge 0 -or
        $safeOutput.IndexOf("diag-build-tools/exports/", [System.StringComparison]::Ordinal) -ge 0
    )
}

try {
    if (-not $RepositoryRoot) {
        $RepositoryRoot = Join-Path $PSScriptRoot "..\.."
    }
    $script:ResolvedRepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path

    if (-not (Test-MalformedInputSuppression)) {
        Stop-Safe -Reason "malformed_input_self_test_failed"
    }
    if (-not (Test-MisleadingSuccessSuppression)) {
        Stop-Safe -Reason "misleading_success_self_test_failed"
    }
    if (-not (Test-PrivacyCanarySuppression)) {
        Stop-Safe -Reason "privacy_canary_failed"
    }

    if ($SelfTestOnly) {
        Write-Output "malformed_input_canary=PASS"
        Write-Output "misleading_success_canary=PASS"
        Write-Output "privacy_canary=PASS"
        Write-Output "result=PASS"
        exit 0
    }

    $gitRoot = @(Invoke-GitMetadata -Arguments @("rev-parse", "--show-toplevel"))
    if ($gitRoot.Count -ne 1 -or (Resolve-Path -LiteralPath $gitRoot[0]).Path -ne $script:ResolvedRepositoryRoot) {
        Stop-Safe -Reason "repository_root_mismatch"
    }

    $head = @(Invoke-GitMetadata -Arguments @("rev-parse", "HEAD"))[0]
    if ($head -notmatch "^[0-9a-f]{40}$") {
        Stop-Safe -Reason "malformed_head_metadata"
    }

    if ($ExpectedHead) {
        if ($ExpectedHead -notmatch "^[0-9a-f]{40}$") {
            Stop-Safe -Reason "malformed_expected_head"
        }
        if ($ExpectedHead -ne $head) {
            Stop-Safe -Reason "stale_repository_state"
        }
    }

    $dirtyEntries = @(Invoke-GitMetadata -Arguments @("status", "--porcelain=v1", "-uno"))
    if (-not $AllowDirty -and $dirtyEntries.Count -ne 0) {
        Stop-Safe -Reason "dirty_worktree"
    }

    $treeRecords = @(Invoke-GitMetadata -Arguments @(
        "ls-tree", "-r", "--long", "HEAD", "--", "diag-build-tools/exports"
    ))
    $inventory = @($treeRecords | ForEach-Object { ConvertFrom-TreeMetadata -Record $_ })

    $credentialCommits = @(
        "7f9553fb854a17e19ea1174cf4e1878cc7707d41",
        "47762456c7003baf598dd0bad86f2089a6cec629"
    )
    foreach ($commit in $credentialCommits) {
        $resolvedCommit = @(Invoke-GitMetadata -Arguments @("rev-parse", "$commit^{commit}"))[0]
        if ($resolvedCommit -ne $commit) {
            Stop-Safe -Reason "credential_commit_metadata_mismatch"
        }
    }

    Write-Output "schema=s0-metadata-only-v1"
    Write-Output "head_commit=$head"
    Write-Output "repository_state=$(if ($dirtyEntries.Count -eq 0) { 'clean' } else { 'dirty' })"
    Write-Output "dirty_entry_count=$($dirtyEntries.Count)"
    Write-Output "tracked_export_count=$($inventory.Count)"
    foreach ($group in @($inventory | Group-Object -Property Category | Sort-Object -Property Name)) {
        Write-Output "category=$($group.Name) count=$($group.Count)"
    }
    foreach ($item in @($inventory | Sort-Object -Property ObjectId)) {
        Write-Output "blob=$($item.ObjectId) size=$($item.Size)"
    }
    foreach ($commit in @($credentialCommits | Sort-Object)) {
        Write-Output "credential_commit=$commit"
    }
    Write-Output "malformed_input_canary=PASS"
    Write-Output "misleading_success_canary=PASS"
    Write-Output "privacy_canary=PASS"
    Write-Output "result=PASS"
}
catch {
    Stop-Safe -Reason "metadata_verification_failed"
}
