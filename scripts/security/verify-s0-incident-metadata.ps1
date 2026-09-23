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

function Get-ApprovedBaselineCommit {
    return "2f2b656d2d13fca48c56ea6f33d63b83c2cd9d21"
}

function Get-ApprovedBaselineInventory {
    return @(
        [pscustomobject]@{ Category = "clinical-export.json"; ObjectId = "31a3e84f84e24403faa9b8b602c421831fb02cf3"; Size = [int64]22180 },
        [pscustomobject]@{ Category = "clinical-export.csv"; ObjectId = "3d9421c09e105ffa390ff928c6a754b9b7bf8a18"; Size = [int64]17221041 },
        [pscustomobject]@{ Category = "clinical-export.json"; ObjectId = "8256a4a96ab456dc7fec031102e1eefa0d0a3aa6"; Size = [int64]25276811 },
        [pscustomobject]@{ Category = "clinical-export.csv"; ObjectId = "8330c56c5787f6f03ef4014e138e7a0466dd82ff"; Size = [int64]17017 },
        [pscustomobject]@{ Category = "clinical-export.json"; ObjectId = "834487cd94a8b1f55826435915433ca998cafe32"; Size = [int64]155287 },
        [pscustomobject]@{ Category = "clinical-export.csv"; ObjectId = "857bc65d3bb244c4811a118dc07f2e64d06b5304"; Size = [int64]24382 }
    )
}

function Test-ExactBaselineInventory {
    param(
        [AllowEmptyCollection()]
        [object[]]$ActualInventory = @()
    )

    $expectedKeys = @(Get-ApprovedBaselineInventory | ForEach-Object {
        "$($_.Category)|$($_.ObjectId)|$($_.Size)"
    } | Sort-Object)
    $actualKeys = @($ActualInventory | ForEach-Object {
        "$($_.Category)|$($_.ObjectId)|$($_.Size)"
    } | Sort-Object)

    if ($actualKeys.Count -ne $expectedKeys.Count) {
        return $false
    }

    return [string]::Equals(
        ($actualKeys -join "`n"),
        ($expectedKeys -join "`n"),
        [System.StringComparison]::Ordinal
    )
}

function Test-BaselineInventoryRegressions {
    $approved = @(Get-ApprovedBaselineInventory)
    $incomplete = @($approved | Select-Object -First ($approved.Count - 1))
    $extra = @($approved) + @(
        [pscustomobject]@{ Category = "clinical-export.csv"; ObjectId = "ffffffffffffffffffffffffffffffffffffffff"; Size = [int64]64 }
    )
    $substituted = @($approved | ForEach-Object {
        [pscustomobject]@{ Category = $_.Category; ObjectId = $_.ObjectId; Size = $_.Size }
    })
    $substituted[0].ObjectId = "1111111111111111111111111111111111111111"

    return (
        (Test-ExactBaselineInventory -ActualInventory $approved) -and
        -not (Test-ExactBaselineInventory -ActualInventory @()) -and
        -not (Test-ExactBaselineInventory -ActualInventory $incomplete) -and
        -not (Test-ExactBaselineInventory -ActualInventory $extra) -and
        -not (Test-ExactBaselineInventory -ActualInventory $substituted)
    )
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
    if (-not (Test-BaselineInventoryRegressions)) {
        Stop-Safe -Reason "baseline_inventory_self_test_failed"
    }

    if ($SelfTestOnly) {
        Write-Output "malformed_input_canary=PASS"
        Write-Output "misleading_success_canary=PASS"
        Write-Output "privacy_canary=PASS"
        Write-Output "baseline_inventory_canary=PASS"
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

    $baselineCommit = Get-ApprovedBaselineCommit
    $resolvedBaselineCommit = @(Invoke-GitMetadata -Arguments @("rev-parse", "$baselineCommit^{commit}"))[0]
    if ($resolvedBaselineCommit -ne $baselineCommit) {
        Stop-Safe -Reason "baseline_commit_metadata_mismatch"
    }

    $treeRecords = @(Invoke-GitMetadata -Arguments @(
        "ls-tree", "-r", "--long", $baselineCommit, "--", "diag-build-tools/exports"
    ))
    $inventory = @($treeRecords | ForEach-Object { ConvertFrom-TreeMetadata -Record $_ })
    if (-not (Test-ExactBaselineInventory -ActualInventory $inventory)) {
        Stop-Safe -Reason "baseline_inventory_mismatch"
    }

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
    Write-Output "baseline_commit=$baselineCommit"
    Write-Output "repository_state=$(if ($dirtyEntries.Count -eq 0) { 'clean' } else { 'dirty' })"
    Write-Output "dirty_entry_count=$($dirtyEntries.Count)"
    Write-Output "baseline_export_count=$($inventory.Count)"
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
    Write-Output "baseline_inventory_canary=PASS"
    Write-Output "result=PASS"
}
catch {
    Stop-Safe -Reason "metadata_verification_failed"
}
