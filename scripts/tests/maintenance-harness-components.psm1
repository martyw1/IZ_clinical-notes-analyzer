Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-IzComponentSuitePlan {
    param([Parameter(Mandatory)][string]$CaseId)
    $plans = @{
        I04 = @(
            @('maintenance-contracts.Tests.ps1', 'contracts-negative', 'iz-cna-maintenance-contract-test-v1'),
            @('maintenance-transaction.Tests.ps1', 'install-negative', 'iz-cna-maintenance-component-suite-v1')
        )
        I10 = @(
            @('maintenance-contracts.Tests.ps1', 'contracts-negative', 'iz-cna-maintenance-contract-test-v1'),
            @('maintenance-transaction.Tests.ps1', 'install-negative', 'iz-cna-maintenance-component-suite-v1')
        )
        U06 = @(
            @('maintenance-contracts.Tests.ps1', 'version', 'iz-cna-maintenance-contract-test-v1'),
            @('maintenance-transaction.Tests.ps1', 'install-negative', 'iz-cna-maintenance-component-suite-v1')
        )
        R01 = @(
            @('maintenance-contracts.Tests.ps1', 'journal', 'iz-cna-maintenance-contract-test-v1'),
            @('maintenance-transaction.Tests.ps1', 'transaction-transitions', 'iz-cna-maintenance-component-suite-v1'),
            @('maintenance-transaction.Tests.ps1', 'transaction-recovery', 'iz-cna-maintenance-component-suite-v1')
        )
        R05 = @(
            @('maintenance-contracts.Tests.ps1', 'contracts-negative', 'iz-cna-maintenance-contract-test-v1'),
            @('maintenance-transaction.Tests.ps1', 'transaction-recovery', 'iz-cna-maintenance-component-suite-v1')
        )
        R08 = @(,@('maintenance-backup.Tests.ps1', 'backup-negative', 'iz-cna-backup-test-evidence-v1'))
        D08 = @(
            @('maintenance-contracts.Tests.ps1', 'paths', 'iz-cna-maintenance-contract-test-v1'),
            @('maintenance-removal.Tests.ps1', 'All', 'iz-cna-maintenance-removal-test-v1')
        )
        P04 = @(
            @('maintenance-contracts.Tests.ps1', 'paths', 'iz-cna-maintenance-contract-test-v1'),
            @('maintenance-backup.Tests.ps1', 'backup-negative', 'iz-cna-backup-test-evidence-v1')
        )
    }
    if (-not $plans.ContainsKey($CaseId)) { return @() }
    return @($plans[$CaseId] | ForEach-Object {
        [pscustomobject][ordered]@{ script = $_[0]; case = $_[1]; schema = $_[2] }
    })
}

function Get-IzSafeSuiteStatus {
    param([Parameter(Mandatory)][object]$Receipt)
    if ($Receipt.PSObject.Properties.Name -notcontains 'status') { return 'failed' }
    $status = [string]$Receipt.status
    if ($status -notin @('passed', 'failed', 'blocked')) { return 'failed' }
    return $status
}

function Test-IzSuiteReceiptEvidence {
    param([Parameter(Mandatory)][object]$Receipt, [Parameter(Mandatory)][string]$Schema)
    if ([string]$Receipt.schema -cne $Schema -or (Get-IzSafeSuiteStatus $Receipt) -cne 'passed') { return $false }
    if ($Schema -ceq 'iz-cna-maintenance-component-suite-v1') {
        $rows = @($Receipt.results)
        return $Receipt.tier -ceq 'Component' -and $rows.Count -gt 0 -and
            @($rows | Where-Object status -ne passed).Count -eq 0 -and
            @($rows | Where-Object { $null -eq $_.binary_observables }).Count -eq 0
    }
    if ($Schema -ceq 'iz-cna-maintenance-contract-test-v1') {
        $rows = @($Receipt.assertions)
        return $rows.Count -gt 0 -and @($rows | Where-Object passed -ne $true).Count -eq 0
    }
    if ($Schema -ceq 'iz-cna-maintenance-removal-test-v1') {
        return $Receipt.synthetic_only -eq $true -and $Receipt.actual_default_profile -eq $false -and
            @($Receipt.scenarios).Count -gt 0 -and @($Receipt.assertions).Count -gt 0 -and
            @($Receipt.assertions | Where-Object passed -ne $true).Count -eq 0
    }
    if ($Schema -ceq 'iz-cna-backup-test-evidence-v1') {
        return $Receipt.tier -ceq 'Component' -and [int]$Receipt.assertion_count -gt 0 -and
            [int]$Receipt.assertion_count -eq [int]$Receipt.passed_count -and @($Receipt.scenarios).Count -gt 0
    }
    return $false
}

function Invoke-IzComponentSuite {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [Parameter(Mandatory)][object]$Fixture,
        [Parameter(Mandatory)][object]$Spec,
        [Parameter(Mandatory)][string]$PublicCaseRoot
    )
    $scriptPath = Join-Path (Join-Path $RepositoryRoot 'scripts\tests') ([string]$Spec.script)
    $safeStem = ([IO.Path]::GetFileNameWithoutExtension([string]$Spec.script) + '-' + [string]$Spec.case).ToLowerInvariant()
    $suiteRoot = Join-Path ([string]$Fixture.suite_root) ($safeStem + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
    $null = New-Item -ItemType Directory -Path $suiteRoot
    $privateLog = Join-Path ([string]$Fixture.private_root) ($safeStem + '.txt')
    $invocation = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File scripts\tests\$($Spec.script) -Case $($Spec.case) -EvidenceRoot <owned-case-root>"
    $exitCode = 2
    $launchError = $null
    if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
        [IO.File]::WriteAllText($privateLog, 'COMPONENT_SUITE_UNAVAILABLE', [Text.UTF8Encoding]::new($false))
    }
    else {
        try {
            $previousModuleCachePath = $env:PSModuleAnalysisCachePath
            $env:PSModuleAnalysisCachePath = Join-Path ([string]$Fixture.private_root) ($safeStem + '.module-analysis.cache')
            $arguments = @(
                '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $scriptPath,
                '-Case', [string]$Spec.case, '-EvidenceRoot', $suiteRoot
            )
            $output = @(& powershell.exe @arguments 2>&1)
            $exitCode = [int]$LASTEXITCODE
            $safeOutput = if ($output.Count) { $output -join "`r`n" } else { '<no-output>' }
            [IO.File]::WriteAllText($privateLog, $safeOutput, [Text.UTF8Encoding]::new($false))
        }
        catch {
            $launchError = 'COMPONENT_SUITE_PROCESS_ERROR'
            [IO.File]::WriteAllText($privateLog, $launchError, [Text.UTF8Encoding]::new($false))
            $exitCode = 1
        }
        finally {
            $env:PSModuleAnalysisCachePath = $previousModuleCachePath
        }
    }
    $descriptors = [Collections.Generic.List[object]]::new()
    $receiptObjects = [Collections.Generic.List[object]]::new()
    foreach ($path in @(Get-ChildItem -LiteralPath $suiteRoot -File -Recurse -Filter '*.json' -ErrorAction SilentlyContinue | Sort-Object FullName)) {
        try { $receipt = Get-Content -LiteralPath $path.FullName -Raw | ConvertFrom-Json }
        catch { continue }
        if ([string]$receipt.schema -cne [string]$Spec.schema) { continue }
        $receiptObjects.Add($receipt)
        $descriptors.Add([pscustomobject][ordered]@{
            name = $path.Name
            schema = [string]$receipt.schema
            status = Get-IzSafeSuiteStatus -Receipt $receipt
            length = [long]$path.Length
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $path.FullName).Hash.ToLowerInvariant()
        })
    }
    $privateText = [IO.File]::ReadAllText($privateLog)
    $notImplemented = $privateText -match 'BACKUP_BEHAVIOR_TESTS_NOT_IMPLEMENTED|NOT_IMPLEMENTED'
    $allReceiptsPassed = $receiptObjects.Count -gt 0 -and
        @($receiptObjects | Where-Object { -not (Test-IzSuiteReceiptEvidence -Receipt $_ -Schema ([string]$Spec.schema)) }).Count -eq 0
    $status = if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf) -or $notImplemented) {
        'blocked'
    } elseif ($exitCode -eq 2 -or @($receiptObjects | Where-Object { (Get-IzSafeSuiteStatus $_) -eq 'blocked' }).Count -gt 0) {
        'blocked'
    } elseif ($exitCode -eq 0 -and $allReceiptsPassed -and -not $launchError) {
        'passed'
    } else {
        'failed'
    }
    $reason = if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
        'COMPONENT_SUITE_UNAVAILABLE'
    } elseif ($notImplemented) {
        'COMPONENT_SUITE_NOT_IMPLEMENTED'
    } elseif ($status -ceq 'blocked') {
        'COMPONENT_SUITE_BLOCKED'
    } elseif ($status -ceq 'failed') {
        'COMPONENT_SUITE_FAILED'
    } else {
        'COMPONENT_SUITE_PASSED'
    }
    $summaryPath = Join-Path $PublicCaseRoot ($safeStem + '.json')
    $summary = [ordered]@{
        schema = 'iz-cna-maintenance-suite-observation-v1'
        suite = [IO.Path]::GetFileNameWithoutExtension([string]$Spec.script)
        selected_case = [string]$Spec.case
        status = $status
        reason = $reason
        exit_code = $exitCode
        receipt_count = $receiptObjects.Count
        receipts = @($descriptors)
        private_log_length = (Get-Item -LiteralPath $privateLog).Length
        private_log_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $privateLog).Hash.ToLowerInvariant()
        completed_utc = [DateTime]::UtcNow.ToString('o')
    }
    $null = Write-IzHarnessJson -Path $summaryPath -Value $summary
    return [pscustomobject][ordered]@{
        status = $status
        reason = $reason
        invocation = $invocation
        observable = "exit_code=$exitCode;receipt_count=$($receiptObjects.Count);typed_evidence=$allReceiptsPassed"
        artifact_path = $summaryPath
    }
}

Export-ModuleMember -Function @('Get-IzComponentSuitePlan', 'Invoke-IzComponentSuite')
