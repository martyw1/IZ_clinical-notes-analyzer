Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-IzVerificationSha256 {
    param([Parameter(Mandatory)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Write-IzVerificationJson {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][object]$Value)
    if (Test-Path -LiteralPath $Path) { throw 'VERIFICATION_ARTIFACT_EXISTS' }
    $parent = Split-Path -Parent ([IO.Path]::GetFullPath($Path))
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        $null = New-Item -ItemType Directory -Path $parent -Force
    }
    $json = $Value | ConvertTo-Json -Depth 12
    if ($json -match '"(access_token|password|password_hash|current_password|new_password|client_secret|api_key)"\s*:') {
        throw 'PRIVATE_VALUE_IN_VERIFICATION_ARTIFACT'
    }
    [IO.File]::WriteAllText([IO.Path]::GetFullPath($Path), $json, [Text.UTF8Encoding]::new($false))
    return [IO.Path]::GetFullPath($Path)
}

function Invoke-IzVerificationPowerShell {
    param(
        [Parameter(Mandatory)][string]$ScriptPath,
        [Parameter(Mandatory)][string[]]$Arguments,
        [Parameter(Mandatory)][string]$LogPath,
        [Parameter(Mandatory)][string]$ModuleCachePath
    )
    if (-not (Test-Path -LiteralPath $ScriptPath -PathType Leaf)) {
        return [pscustomobject][ordered]@{ exit_code = 1; log_length = 0; log_sha256 = $null; missing = $true }
    }
    $previousCache = $env:PSModuleAnalysisCachePath
    try {
        $env:PSModuleAnalysisCachePath = $ModuleCachePath
        $output = @(& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $ScriptPath @Arguments 2>&1)
        $exitCode = [int]$LASTEXITCODE
        $text = if ($output.Count) { $output -join "`r`n" } else { '<no-output>' }
        [IO.File]::WriteAllText($LogPath, $text, [Text.UTF8Encoding]::new($false))
    }
    catch {
        $exitCode = 1
        [IO.File]::WriteAllText($LogPath, 'VERIFICATION_PROCESS_ERROR', [Text.UTF8Encoding]::new($false))
    }
    finally {
        if ($null -eq $previousCache) { Remove-Item Env:\PSModuleAnalysisCachePath -ErrorAction SilentlyContinue }
        else { $env:PSModuleAnalysisCachePath = $previousCache }
    }
    $item = Get-Item -LiteralPath $LogPath
    return [pscustomobject][ordered]@{
        exit_code = $exitCode
        log_length = [long]$item.Length
        log_sha256 = Get-IzVerificationSha256 -Path $LogPath
        missing = $false
    }
}

function Get-IzCandidateGateStatus {
    param([Parameter(Mandatory)][object]$CandidateReceipt)
    $required = @('backend_tests', 'frontend_tests', 'frontend_build')
    $gates = @($CandidateReceipt.receipt.gates)
    return @($required | ForEach-Object {
        $name = $_
        $gate = @($gates | Where-Object { $_.name -ceq $name })
        [pscustomobject][ordered]@{
            name = $name
            passed = $gate.Count -eq 1 -and $gate[0].status -ceq 'passed' -and [int]$gate[0].exit_code -eq 0
        }
    })
}

function Invoke-IzHarnessSourceVerification {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [Parameter(Mandatory)][object]$Fixture,
        [Parameter(Mandatory)][string]$PublicCaseRoot,
        [Parameter(Mandatory)][object]$CandidateReceipt
    )
    $gateStatus = @(Get-IzCandidateGateStatus -CandidateReceipt $CandidateReceipt)
    $commands = @(
        [pscustomobject]@{ name = 'lifecycle'; script = 'scripts\test-windows-lifecycle.ps1'; arguments = @(); http = $false; port = 0 },
        [pscustomobject]@{ name = 'stop'; script = 'scripts\test-windows-stop.ps1'; arguments = @(); http = $false; port = 0 },
        [pscustomobject]@{ name = 'local_stack'; script = 'scripts\test-local-app-stack.ps1'; arguments = @('-Port', '0', '-SkipDependencyInstall'); http = $true; port = 0 },
        [pscustomobject]@{ name = 'api_configuration'; script = 'scripts\test-api-configuration-local.ps1'; arguments = @('-Port', '0', '-SkipDependencyInstall'); http = $true; port = 0 }
    )
    foreach ($command in $commands | Where-Object http) {
        $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
        try { $listener.Start(); $command.port = [int]$listener.LocalEndpoint.Port }
        finally { $listener.Stop() }
        $command.arguments[1] = [string]$command.port
    }
    $results = [Collections.Generic.List[object]]::new()
    foreach ($command in $commands) {
        $logPath = Join-Path ([string]$Fixture.private_root) ($command.name + '.txt')
        $moduleCache = Join-Path ([string]$Fixture.private_root) ($command.name + '.module-analysis.cache')
        $result = Invoke-IzVerificationPowerShell -ScriptPath (Join-Path $RepositoryRoot $command.script) `
            -Arguments $command.arguments -LogPath $logPath -ModuleCachePath $moduleCache
        $listenerReleased = if ($command.port) {
            @(Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort $command.port -State Listen -ErrorAction SilentlyContinue).Count -eq 0
        }
        else { $true }
        $results.Add([pscustomobject][ordered]@{
            name = $command.name
            invocation = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $($command.script)" + $(if ($command.http) { ' -Port <owned-free-port> -SkipDependencyInstall' } else { '' })
            exit_code = [int]$result.exit_code
            actual_local_http = [bool]$command.http
            listener_released = [bool]$listenerReleased
            private_log_length = [long]$result.log_length
            private_log_sha256 = $result.log_sha256
        })
    }
    $passed = @($gateStatus | Where-Object { -not $_.passed }).Count -eq 0 -and
        @($results | Where-Object { $_.exit_code -ne 0 -or -not $_.listener_released }).Count -eq 0
    $summaryPath = Join-Path $PublicCaseRoot 'source-verification.json'
    $summary = [ordered]@{
        schema = 'iz-cna-maintenance-source-verification-v1'
        status = if ($passed) { 'passed' } else { 'failed' }
        source_revision = [string]$CandidateReceipt.receipt.source_revision
        build_gates = $gateStatus
        commands = @($results)
        completed_utc = [DateTime]::UtcNow.ToString('o')
    }
    $null = Write-IzVerificationJson -Path $summaryPath -Value $summary
    return [pscustomobject][ordered]@{
        status = [string]$summary.status
        reason = if ($passed) { 'SOURCE_AND_BUILD_GATES_PASSED' } else { 'SOURCE_OR_BUILD_GATE_FAILED' }
        invocation = 'candidate backend/frontend/build gates; lifecycle; stop; local-stack live HTTP; API-configuration live HTTP'
        observable = "build_gates=3;source_commands=$($results.Count);live_http_commands=$(@($results | Where-Object actual_local_http).Count);all_exit_zero=$passed"
        artifact_path = $summaryPath
        actual_executable = $false
    }
}

function Invoke-IzHarnessPackagingVerification {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [Parameter(Mandatory)][object]$Fixture,
        [Parameter(Mandatory)][string]$PublicCaseRoot,
        [Parameter(Mandatory)][object]$CandidateReceipt
    )
    $qaParent = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'IZ-CNA-QA'
    $probeRoot = Join-Path $qaParent ('pkg-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
    $reportPath = Join-Path ([string]$Fixture.private_root) 'packaging-report.json'
    $logPath = Join-Path ([string]$Fixture.private_root) 'packaging-probe.txt'
    $moduleCache = Join-Path ([string]$Fixture.private_root) 'packaging-probe.module-analysis.cache'
    $result = Invoke-IzVerificationPowerShell -ScriptPath (Join-Path $RepositoryRoot 'scripts\test-windows-installer-packaging.ps1') `
        -Arguments @('-EvidenceRoot', $probeRoot, '-ReportPath', $reportPath) -LogPath $logPath -ModuleCachePath $moduleCache
    $report = $null
    try { if (Test-Path -LiteralPath $reportPath -PathType Leaf) { $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json } }
    catch { $report = $null }
    $valid = $result.exit_code -eq 0 -and $null -ne $report -and
        $report.schema -ceq 'iz-cna-installer-packaging-test-v1' -and
        $report.source_revision -ceq [string]$CandidateReceipt.receipt.source_revision -and
        @($report.wrapper.variants).Count -eq 7 -and $report.wrapper.success_exit_code -eq 0 -and
        $null -ne $report.maintenance_bundle -and $null -ne $report.release_manifest -and
        $null -ne $report.build_receipt -and $report.collision.reason -ceq 'ARTIFACT_COLLISION' -and
        $report.negative_cases.'missing-member' -ceq 'REQUIRED_PACKAGE_MEMBER_MISSING:installer/maintenance-lock.psm1' -and
        $report.negative_cases.'unsafe-canary' -ceq 'FORBIDDEN_PACKAGE_DEVELOPER_MEMBER' -and
        $report.negative_cases.'bundle-tamper' -ceq 'MAINTENANCE_BUNDLE_FILE_MISMATCH' -and
        -not (Test-Path -LiteralPath $probeRoot)
    $summaryPath = Join-Path $PublicCaseRoot 'rendered-source-verification.json'
    $summary = [ordered]@{
        schema = 'iz-cna-maintenance-rendered-source-verification-v1'
        status = if ($valid) { 'passed' } else { 'failed' }
        source_revision = [string]$CandidateReceipt.receipt.source_revision
        process_exit_code = [int]$result.exit_code
        rendered_variant_count = if ($report) { @($report.wrapper.variants).Count } else { 0 }
        bundle_file_count = if ($report) { @($report.maintenance_bundle.files).Count } else { 0 }
        collision_preserved = [bool]($report -and $report.collision.reason -ceq 'ARTIFACT_COLLISION')
        negative_boundaries_passed = [bool]($valid)
        private_report_length = if (Test-Path -LiteralPath $reportPath) { [long](Get-Item $reportPath).Length } else { 0 }
        private_report_sha256 = if (Test-Path -LiteralPath $reportPath) { Get-IzVerificationSha256 $reportPath } else { $null }
        completed_utc = [DateTime]::UtcNow.ToString('o')
    }
    $null = Write-IzVerificationJson -Path $summaryPath -Value $summary
    return [pscustomobject][ordered]@{
        status = [string]$summary.status
        reason = if ($valid) { 'RENDERED_SOURCE_VERIFIED' } else { 'RENDERED_SOURCE_VERIFICATION_FAILED' }
        invocation = 'scripts/test-windows-installer-packaging.ps1 -EvidenceRoot <fresh-owned-root> -ReportPath <private-report>'
        observable = "exit_code=$($result.exit_code);rendered_variants=$($summary.rendered_variant_count);negative_boundaries=$($summary.negative_boundaries_passed);probe_cleaned=$(-not (Test-Path -LiteralPath $probeRoot))"
        artifact_path = $summaryPath
        actual_executable = $false
    }
}

function Invoke-IzHarnessReleaseSafetyVerification {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [Parameter(Mandatory)][object]$Fixture,
        [Parameter(Mandatory)][string]$PublicCaseRoot,
        [Parameter(Mandatory)][object]$CandidateReceipt
    )
    $qaParent = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'IZ-CNA-QA'
    $probeRoot = Join-Path $qaParent ('prs-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
    $logPath = Join-Path ([string]$Fixture.private_root) 'release-safety.txt'
    $result = Invoke-IzVerificationPowerShell -ScriptPath (Join-Path $RepositoryRoot 'scripts\test-release-safety.ps1') `
        -Arguments @('-EvidenceDir', $probeRoot) -LogPath $logPath `
        -ModuleCachePath (Join-Path ([string]$Fixture.private_root) 'release-safety.module-analysis.cache')
    $reportPath = Join-Path $probeRoot 'private-report-result.json'
    $report = $null
    try { if (Test-Path -LiteralPath $reportPath -PathType Leaf) { $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json } }
    catch { $report = $null }
    $checks = if ($report) { @($report.checks.PSObject.Properties.Value) } else { @() }
    $valid = $result.exit_code -eq 0 -and $report -and $report.status -ceq 'passed' -and
        $checks.Count -gt 0 -and @($checks | Where-Object { $_ -ne $true }).Count -eq 0
    $summaryPath = Join-Path $PublicCaseRoot 'release-safety-verification.json'
    $summary = [ordered]@{
        schema = 'iz-cna-maintenance-release-safety-verification-v1'
        status = if ($valid) { 'passed' } else { 'failed' }
        candidate_zip_sha256 = [string]$CandidateReceipt.receipt.zip_sha256
        process_exit_code = [int]$result.exit_code
        negative_check_count = $checks.Count
        all_negative_checks_passed = [bool]$valid
        private_report_length = if (Test-Path -LiteralPath $reportPath) { [long](Get-Item $reportPath).Length } else { 0 }
        private_report_sha256 = if (Test-Path -LiteralPath $reportPath) { Get-IzVerificationSha256 $reportPath } else { $null }
        completed_utc = [DateTime]::UtcNow.ToString('o')
    }
    $null = Write-IzVerificationJson -Path $summaryPath -Value $summary
    return [pscustomobject][ordered]@{
        status = [string]$summary.status
        reason = if ($valid) { 'RELEASE_SAFETY_NEGATIVES_PASSED' } else { 'RELEASE_SAFETY_NEGATIVES_FAILED' }
        invocation = 'scripts/test-release-safety.ps1 -EvidenceDir <fresh-owned-root>; candidate build receipt ZIP/directory/frozen gates'
        observable = "exit_code=$($result.exit_code);negative_checks=$($checks.Count);candidate_zip_sha256=$($CandidateReceipt.receipt.zip_sha256)"
        artifact_path = $summaryPath
        actual_executable = $false
    }
}

function Invoke-IzHarnessArchiveVerification {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [Parameter(Mandatory)][object]$Fixture,
        [Parameter(Mandatory)][string]$PublicCaseRoot,
        [Parameter(Mandatory)][object]$CandidateReceipt
    )
    $qaParent = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'IZ-CNA-QA'
    $probeRoot = Join-Path $qaParent ('zlp-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
    $logPath = Join-Path ([string]$Fixture.private_root) 'archive-regression.txt'
    $result = Invoke-IzVerificationPowerShell -ScriptPath (Join-Path $RepositoryRoot 'scripts\test-windows-release-archive.ps1') `
        -Arguments @('-EvidenceRoot', $probeRoot, '-PreservedPackage', [string]$CandidateReceipt.receipt.package_directory) `
        -LogPath $logPath -ModuleCachePath (Join-Path ([string]$Fixture.private_root) 'archive-regression.module-analysis.cache')
    $reportPath = Join-Path $probeRoot 'result.json'
    $report = $null
    try { if (Test-Path -LiteralPath $reportPath -PathType Leaf) { $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json } }
    catch { $report = $null }
    $valid = $result.exit_code -eq 0 -and $report -and $report.status -ceq 'passed' -and
        [int]$report.native_exit_code -eq 0 -and [int]$report.synthetic_long_path_length -gt 260 -and
        $report.fixture_entry_hashes_equal -eq $true -and $report.package_entry_hashes_equal -eq $true -and
        $report.zip_forbidden_scan_passed -eq $true -and $report.preserved_package_unchanged -eq $true
    $summaryPath = Join-Path $PublicCaseRoot 'archive-regression-verification.json'
    $summary = [ordered]@{
        schema = 'iz-cna-maintenance-archive-regression-verification-v1'
        status = if ($valid) { 'passed' } else { 'failed' }
        powershell = if ($report) { [string]$report.powershell } else { $null }
        process_exit_code = [int]$result.exit_code
        synthetic_long_path_length = if ($report) { [int]$report.synthetic_long_path_length } else { 0 }
        package_file_count = if ($report) { [int]$report.package_file_count } else { 0 }
        package_entry_hashes_equal = [bool]($report -and $report.package_entry_hashes_equal)
        candidate_zip_sha256 = [string]$CandidateReceipt.receipt.zip_sha256
        private_report_length = if (Test-Path -LiteralPath $reportPath) { [long](Get-Item $reportPath).Length } else { 0 }
        private_report_sha256 = if (Test-Path -LiteralPath $reportPath) { Get-IzVerificationSha256 $reportPath } else { $null }
        completed_utc = [DateTime]::UtcNow.ToString('o')
    }
    $null = Write-IzVerificationJson -Path $summaryPath -Value $summary
    return [pscustomobject][ordered]@{
        status = [string]$summary.status
        reason = if ($valid) { 'PS51_ARCHIVE_REGRESSION_PASSED' } else { 'PS51_ARCHIVE_REGRESSION_FAILED' }
        invocation = 'powershell.exe -NoProfile -File scripts/test-windows-release-archive.ps1 -EvidenceRoot <fresh-owned-root> -PreservedPackage <exact-candidate-package>'
        observable = "exit_code=$($result.exit_code);long_path_length=$($summary.synthetic_long_path_length);package_hashes_equal=$($summary.package_entry_hashes_equal)"
        artifact_path = $summaryPath
        actual_executable = $false
    }
}

Export-ModuleMember -Function @(
    'Invoke-IzHarnessSourceVerification', 'Invoke-IzHarnessPackagingVerification',
    'Invoke-IzHarnessReleaseSafetyVerification', 'Invoke-IzHarnessArchiveVerification'
)
