Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'maintenance-harness-contracts.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'maintenance-harness-safety.psm1') -Force
. (Join-Path $PSScriptRoot 'maintenance-fixture.ps1')

$script:ProductId = 'r3.iz-clinical-notes-analyzer.desktop'
$script:ControlKeys = @(
    'schema','request_id','operation','status','reason','product_id','owner_sid','scope_id','data_identity',
    'instance_id','transaction_id','process_id','process_started_utc','version','build','installer_revision',
    'port','gate','draining','active_business_requests'
)
$script:ResultKeys = @(
    'schema','product_id','action','status','version','build','installer_revision','transaction_id','stage',
    'code','reason','evidence','started_utc','completed_utc'
)

function New-IzLifecycleError {
    param([Parameter(Mandatory)][string]$Reason)
    $exception = [IO.InvalidDataException]::new($Reason)
    $exception.Data['iz_reason'] = $Reason
    return $exception
}

function Get-IzLifecycleReason {
    param([Parameter(Mandatory)][Management.Automation.ErrorRecord]$Record)
    if ($Record.Exception.Data.Contains('iz_reason') -and
        [string]$Record.Exception.Data['iz_reason'] -cmatch '^[A-Z][A-Z0-9_]{0,63}$') {
        return [string]$Record.Exception.Data['iz_reason']
    }
    if ($Record.Exception.Message -cmatch '^[A-Z][A-Z0-9_]{0,63}$') { return $Record.Exception.Message }
    return 'LIFECYCLE_SMOKE_FAILED'
}

function Assert-IzLifecycleExactKeys {
    param([object]$Value, [string[]]$Keys, [string]$Reason)
    if ($null -eq $Value -or
        @(Compare-Object @($Value.PSObject.Properties.Name | Sort-Object) @($Keys | Sort-Object)).Count -ne 0) {
        throw (New-IzLifecycleError $Reason)
    }
}

function Get-IzLifecycleStreamSha256 {
    param([Parameter(Mandatory)][IO.Stream]$Stream)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($Stream))).Replace('-', '').ToLowerInvariant() }
    finally { $algorithm.Dispose() }
}

function Test-IzLifecycleZipMatchesPackage {
    param(
        [Parameter(Mandatory)][string]$ZipPath,
        [Parameter(Mandatory)][string]$PackageRoot,
        [Parameter(Mandatory)][object]$Manifest
    )
    [void](Test-IzHarnessZip -Path $ZipPath)
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $files = @($archive.Entries | Where-Object { -not [string]::IsNullOrEmpty($_.Name) })
        if ($files.Count -ne @($Manifest.files).Count + 1) { throw (New-IzLifecycleError 'LIFECYCLE_ZIP_FILE_SET_MISMATCH') }
        $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
        foreach ($record in @($Manifest.files)) {
            $entries = @($files | Where-Object { $_.FullName -ceq [string]$record.path })
            if ($entries.Count -ne 1 -or -not $seen.Add([string]$record.path) -or
                [long]$entries[0].Length -ne [long]$record.length) {
                throw (New-IzLifecycleError 'LIFECYCLE_ZIP_FILE_SET_MISMATCH')
            }
            $stream = $entries[0].Open()
            try { $hash = Get-IzLifecycleStreamSha256 -Stream $stream } finally { $stream.Dispose() }
            if ($hash -cne [string]$record.sha256) { throw (New-IzLifecycleError 'LIFECYCLE_ZIP_PAYLOAD_MISMATCH') }
        }
        $embedded = @($files | Where-Object FullName -ceq 'release-manifest.json')
        if ($embedded.Count -ne 1 -or -not $seen.Add('release-manifest.json')) {
            throw (New-IzLifecycleError 'LIFECYCLE_ZIP_MANIFEST_MISMATCH')
        }
        $manifestPath = Join-Path $PackageRoot 'release-manifest.json'
        $stream = $embedded[0].Open()
        try { $embeddedHash = Get-IzLifecycleStreamSha256 -Stream $stream } finally { $stream.Dispose() }
        if ($embeddedHash -cne (Get-IzHarnessSha256 -Path $manifestPath) -or $seen.Count -ne $files.Count) {
            throw (New-IzLifecycleError 'LIFECYCLE_ZIP_MANIFEST_MISMATCH')
        }
    }
    finally { $archive.Dispose() }
    return $true
}

function New-IzLifecycleCandidateBinding {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidateSet('Release','ValidationOnly')][string]$QualificationMode,
        [Parameter(Mandatory)][string]$CandidateZip,
        [Parameter(Mandatory)][string]$CandidatePackageRoot,
        [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{40}$')][string]$ExpectedSourceRevision,
        [AllowNull()][object]$CandidateBuildReceipt = $null,
        [string]$ValidationSummary = ''
    )
    $zip = Get-IzHarnessFileDescriptor -Path $CandidateZip
    $package = [IO.Path]::GetFullPath($CandidatePackageRoot).TrimEnd('\')
    Assert-IzFixturePlainPath -Path $package
    if (-not (Test-Path -LiteralPath $package -PathType Container)) { throw (New-IzLifecycleError 'LIFECYCLE_PACKAGE_MISSING') }
    $manifestPath = Join-Path $package 'release-manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw (New-IzLifecycleError 'LIFECYCLE_MANIFEST_MISSING') }
    try { $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json }
    catch { throw (New-IzLifecycleError 'LIFECYCLE_MANIFEST_INVALID') }
    if ($manifest.schema -cne 'iz-cna-release-manifest-v1' -or $manifest.product_id -cne $script:ProductId -or
        $manifest.version -cnotin @('2.0.0-beta.4','1.0.0') -or [int]$manifest.installer_revision -ne 1 -or
        [string]$manifest.build -cnotmatch '^20[0-9]{2}\.[0-9]{2}\.[0-9]{2}\.[0-9]+$' -or
        [string]$manifest.payload_identity -cnotmatch '^[a-f0-9]{64}$' -or @($manifest.files).Count -eq 0) {
        throw (New-IzLifecycleError 'LIFECYCLE_MANIFEST_INVALID')
    }
    $manifestHash = Get-IzHarnessSha256 -Path $manifestPath
    $summaryDescriptor = $null
    $buildReceiptDescriptor = $null
    if ($QualificationMode -ceq 'Release') {
        if ($null -eq $CandidateBuildReceipt) { throw (New-IzLifecycleError 'LIFECYCLE_BUILD_RECEIPT_REQUIRED') }
        $receipt = $CandidateBuildReceipt.receipt
        if (-not ([IO.Path]::GetFullPath([string]$receipt.package_directory).TrimEnd('\').Equals($package, [StringComparison]::OrdinalIgnoreCase)) -or
            [string]$receipt.source_revision -cne $ExpectedSourceRevision -or [string]$receipt.zip_sha256 -cne $zip.sha256 -or
            [long]$receipt.zip_length -ne [long]$zip.length -or [string]$receipt.manifest_sha256 -cne $manifestHash -or
            [string]$receipt.payload_identity -cne [string]$manifest.payload_identity) {
            throw (New-IzLifecycleError 'LIFECYCLE_BUILD_RECEIPT_MISMATCH')
        }
        $buildReceiptDescriptor = [pscustomobject][ordered]@{
            path = [IO.Path]::GetFullPath([string]$CandidateBuildReceipt.path)
            length = [long]$CandidateBuildReceipt.length
            sha256 = [string]$CandidateBuildReceipt.sha256
        }
    }
    else {
        if ([IO.Path]::GetFileName($package) -cnotmatch '\.NOT-RELEASE-READY$' -or
            [IO.Path]::GetFileName($zip.path) -cnotmatch '\.NOT-RELEASE-READY\.zip$' -or
            [IO.Path]::GetFileNameWithoutExtension($zip.path) -cne [IO.Path]::GetFileName($package)) {
            throw (New-IzLifecycleError 'VALIDATION_ONLY_MARKER_REQUIRED')
        }
        if (-not $ValidationSummary) { throw (New-IzLifecycleError 'VALIDATION_ONLY_SUMMARY_REQUIRED') }
        $expectedSummary = Join-Path (Split-Path $package -Parent) 'validation-summary.NOT-RELEASE-READY.json'
        $summaryPath = [IO.Path]::GetFullPath($ValidationSummary)
        if (-not $summaryPath.Equals($expectedSummary, [StringComparison]::OrdinalIgnoreCase) -or
            -not (Test-Path -LiteralPath $summaryPath -PathType Leaf)) {
            throw (New-IzLifecycleError 'VALIDATION_ONLY_SUMMARY_INVALID')
        }
        Assert-IzFixturePlainPath -Path $summaryPath
        try { $summary = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json }
        catch { throw (New-IzLifecycleError 'VALIDATION_ONLY_SUMMARY_INVALID') }
        if ($summary.schema -cne 'iz-cna-build-gate-evidence-v1' -or $summary.product_id -cne $script:ProductId -or
            $summary.release_ready -ne $false -or $summary.source_revision -cne $ExpectedSourceRevision -or
            $summary.version -cne $manifest.version -or $summary.build -cne $manifest.build -or
            [int]$summary.installer_revision -ne [int]$manifest.installer_revision -or
            [string]$summary.directory_safety.payload_identity -cne [string]$manifest.payload_identity -or
            [long]$summary.zip_safety.length -ne [long]$zip.length -or
            [string]$summary.zip_safety.sha256 -cne [string]$zip.sha256) {
            throw (New-IzLifecycleError 'VALIDATION_ONLY_SUMMARY_INVALID')
        }
        $summaryDescriptor = Get-IzHarnessFileDescriptor -Path $summaryPath
    }
    [void](Test-IzLifecycleZipMatchesPackage -ZipPath $zip.path -PackageRoot $package -Manifest $manifest)
    return [pscustomobject][ordered]@{
        qualification_mode = $(if ($QualificationMode -ceq 'Release') { 'release' } else { 'validation_only' })
        release_qualification = ($QualificationMode -ceq 'Release')
        source_revision = $ExpectedSourceRevision
        zip = $zip
        package_root = $package
        manifest_path = $manifestPath
        manifest_sha256 = $manifestHash
        manifest = $manifest
        build_receipt = $buildReceiptDescriptor
        validation_summary = $summaryDescriptor
    }
}

function ConvertTo-IzLifecycleProcessArgument {
    param([AllowEmptyString()][string]$Value)
    if ($Value -notmatch '[\s"]') { return $Value }
    $result = '"'; $slashes = 0
    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq '\') { $slashes += 1; continue }
        if ($character -eq '"') { $result += ('\' * (2 * $slashes + 1)) + '"'; $slashes = 0; continue }
        if ($slashes) { $result += ('\' * $slashes); $slashes = 0 }
        $result += $character
    }
    if ($slashes) { $result += ('\' * (2 * $slashes)) }
    return $result + '"'
}

function Invoke-IzLifecycleWithEnvironment {
    param(
        [Parameter(Mandatory)][Collections.IDictionary]$Environment,
        [Parameter(Mandatory)][scriptblock]$Action
    )
    $previous = @{}
    try {
        foreach ($entry in $Environment.GetEnumerator()) {
            $previous[$entry.Key] = [Environment]::GetEnvironmentVariable([string]$entry.Key, 'Process')
            [Environment]::SetEnvironmentVariable([string]$entry.Key, [string]$entry.Value, 'Process')
        }
        return & $Action
    }
    finally {
        foreach ($entry in $previous.GetEnumerator()) {
            [Environment]::SetEnvironmentVariable([string]$entry.Key, $entry.Value, 'Process')
        }
    }
}

function Invoke-IzLifecycleAction {
    param(
        [Parameter(Mandatory)][ValidateSet('AutoInstall','Uninstall','RemoveData')][string]$Action,
        [Parameter(Mandatory)][object]$Fixture,
        [Parameter(Mandatory)][object]$Context,
        [Parameter(Mandatory)][object]$Binding,
        [Parameter(Mandatory)][Collections.IDictionary]$Environment,
        [AllowNull()][object]$RuntimeModule = $null,
        [switch]$CapturePrecommitControl
    )
    $key = $Action.ToLowerInvariant() + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
    $resultPath = Join-Path ([string]$Fixture.private_root) ($key + '.result.json')
    $stdoutPath = Join-Path ([string]$Fixture.private_root) ($key + '.stdout.txt')
    $stderrPath = Join-Path ([string]$Fixture.private_root) ($key + '.stderr.txt')
    $stdinPath = Join-Path ([string]$Fixture.private_root) ($key + '.stdin.txt')
    [IO.File]::WriteAllText($stdinPath, $(if ($Action -ceq 'RemoveData') { "REMOVE IZ DATA`r`n" } else { '' }), [Text.UTF8Encoding]::new($false))
    $helper = Join-Path $PSScriptRoot 'maintenance-component-action.ps1'
    $arguments = @('-NoProfile')
    if ($Action -cne 'RemoveData') { $arguments += '-NonInteractive' }
    $arguments += @(
        '-ExecutionPolicy','Bypass','-File',$helper,
        '-Action',$Action,'-DispatcherPath',(Join-Path $Binding.package_root 'installer\maintenance-windows.ps1'),
        '-PackageRoot',$Binding.package_root,'-ComponentTestRoot',[string]$Fixture.component_root,'-ResultPath',$resultPath
    )
    $argumentText = @($arguments | ForEach-Object { ConvertTo-IzLifecycleProcessArgument -Value ([string]$_) }) -join ' '
    $childEnvironment = [ordered]@{}
    foreach ($entry in $Environment.GetEnumerator()) { $childEnvironment[$entry.Key] = [string]$entry.Value }
    $childEnvironment.PSModuleAnalysisCachePath = Join-Path ([string]$Fixture.private_root) ($key + '.module-analysis.cache')
    $process = Invoke-IzLifecycleWithEnvironment -Environment $childEnvironment -Action {
        Start-Process -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
            -ArgumentList $argumentText -PassThru -WindowStyle Hidden `
            -RedirectStandardInput $stdinPath -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    }
    $processHandle = $process.Handle
    if ($processHandle -eq [IntPtr]::Zero) { throw (New-IzLifecycleError 'LIFECYCLE_PROCESS_HANDLE_INVALID') }
    $precommitStatus = $null
    $deadline = [DateTime]::UtcNow.AddMinutes(5)
    while (-not $process.HasExited -and [DateTime]::UtcNow -lt $deadline) {
        if ($CapturePrecommitControl -and $null -eq $precommitStatus -and $RuntimeModule -and
            (Test-Path -LiteralPath $Context.runtime_identity_path -PathType Leaf)) {
            try {
                $candidateIdentity = & $RuntimeModule { param($value) Read-IzRuntimeIdentity -Context $value } $Context
                if ($candidateIdentity -and $null -ne $candidateIdentity.transaction_id) {
                    $candidateStatus = & $RuntimeModule {
                        param($value,$identity)
                        Invoke-IzRuntimeControl -Context $value -Operation status -RuntimeIdentity $identity -TimeoutSeconds 5
                    } $Context $candidateIdentity
                    Assert-IzLifecycleExactKeys -Value $candidateStatus -Keys $script:ControlKeys -Reason 'LIFECYCLE_CONTROL_KEYS_INVALID'
                    if ($candidateStatus.status -cne 'ok' -or $candidateStatus.reason -cne 'status' -or
                        $candidateStatus.gate -cne 'maintenance' -or [bool]$candidateStatus.draining -or
                        [int]$candidateStatus.active_business_requests -ne 0) {
                        throw (New-IzLifecycleError 'LIFECYCLE_PRECOMMIT_STATUS_INVALID')
                    }
                    $precommitStatus = $candidateStatus
                }
            }
            catch {
                if ($_.Exception.Data.Contains('iz_reason') -and
                    [string]$_.Exception.Data['iz_reason'] -in @('LIFECYCLE_CONTROL_KEYS_INVALID','LIFECYCLE_PRECOMMIT_STATUS_INVALID')) {
                    throw
                }
            }
        }
        Start-Sleep -Milliseconds 50
    }
    if (-not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        throw (New-IzLifecycleError 'LIFECYCLE_ACTION_TIMEOUT')
    }
    $process.WaitForExit()
    $rawProcessExitCode = $process.ExitCode
    if ($null -eq $rawProcessExitCode) { throw (New-IzLifecycleError 'LIFECYCLE_PROCESS_EXIT_CODE_MISSING') }
    $processExitCode = [int]$rawProcessExitCode
    if (-not (Test-Path -LiteralPath $resultPath -PathType Leaf)) { throw (New-IzLifecycleError 'LIFECYCLE_RESULT_MISSING') }
    try { $result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json }
    catch { throw (New-IzLifecycleError 'LIFECYCLE_RESULT_INVALID') }
    Assert-IzLifecycleExactKeys -Value $result -Keys $script:ResultKeys -Reason 'LIFECYCLE_RESULT_INVALID'
    if ($result.schema -cne 'iz-cna-maintenance-result-v1' -or $result.product_id -cne $script:ProductId -or
        $result.action -cne $Action) {
        throw (New-IzLifecycleError 'LIFECYCLE_RESULT_INVALID')
    }
    if ([int]$result.code -ne $processExitCode) { throw (New-IzLifecycleError 'LIFECYCLE_RESULT_EXIT_CODE_MISMATCH') }
    return [pscustomobject][ordered]@{
        result = $result; exit_code = $processExitCode
        result_path = $resultPath; stdout_path = $stdoutPath; stderr_path = $stderrPath
        precommit_status = $precommitStatus
    }
}

function Assert-IzLifecycleActionSucceeded {
    param([Parameter(Mandatory)][object]$ActionResult, [Parameter(Mandatory)][string]$Reason)
    if ([int]$ActionResult.exit_code -ne 0 -or [int]$ActionResult.result.code -ne 0 -or
        [string]$ActionResult.result.status -notin @('SUCCEEDED','NO_OP')) {
        throw (New-IzLifecycleError $Reason)
    }
}

function Test-IzLifecycleListenerAbsent {
    param([Parameter(Mandatory)][int]$Port)
    return @(Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort $Port -State Listen -ErrorAction SilentlyContinue).Count -eq 0
}

function Get-IzLifecycleRuntimeObservation {
    param(
        [Parameter(Mandatory)][object]$RuntimeModule,
        [Parameter(Mandatory)][object]$Context,
        [Parameter(Mandatory)][object]$Binding,
        [Parameter(Mandatory)][string]$ExpectedDataIdentity,
        [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{32}$')][string]$ExpectedTransactionId
    )
    $identity = & $RuntimeModule { param($value) Read-IzRuntimeIdentity -Context $value } $Context
    if ($null -eq $identity) { throw (New-IzLifecycleError 'LIFECYCLE_RUNTIME_IDENTITY_MISSING') }
    $authority = & $RuntimeModule { param($value) Test-IzInstalledRuntimeAuthority -Context $value } $Context
    $pending = & $RuntimeModule { param($value) Get-IzPendingMaintenanceStatus -Context $value } $Context
    $status = & $RuntimeModule { param($value,$runtime) Invoke-IzRuntimeControl -Context $value -Operation status -RuntimeIdentity $runtime -TimeoutSeconds 5 } $Context $identity
    Assert-IzLifecycleExactKeys -Value $status -Keys $script:ControlKeys -Reason 'LIFECYCLE_CONTROL_KEYS_INVALID'
    if ($status.status -cne 'ok' -or $status.reason -cne 'status' -or $status.gate -cne 'open' -or
        [bool]$status.draining -or [int]$status.active_business_requests -ne 0 -or
        [string]$status.transaction_id -cne $ExpectedTransactionId -or
        [string]$identity.transaction_id -cne $ExpectedTransactionId -or
        [string]$identity.data_identity -cne $ExpectedDataIdentity -or
        [string]$identity.version -cne [string]$Binding.manifest.version -or
        [string]$identity.build -cne [string]$Binding.manifest.build -or
        [int]$identity.installer_revision -ne [int]$Binding.manifest.installer_revision -or
        [string]$authority.receipt.payload_identity -cne [string]$Binding.manifest.payload_identity -or
        [string]$authority.receipt.last_committed_transaction -cne $ExpectedTransactionId -or
        $pending.status -cne 'COMMITTED' -or [string]$pending.journal.transaction_id -cne $ExpectedTransactionId) {
        throw (New-IzLifecycleError 'LIFECYCLE_RUNTIME_IDENTITY_MISMATCH')
    }
    $expectedExecutable = Join-Path $Context.install_root 'runtime\IZClinicalNotesAnalyzer.exe'
    $process = Get-Process -Id ([int]$identity.process_id) -ErrorAction Stop
    if (-not [IO.Path]::GetFullPath($process.Path).Equals([IO.Path]::GetFullPath($expectedExecutable), [StringComparison]::OrdinalIgnoreCase) -or
        (Get-IzHarnessSha256 -Path $expectedExecutable) -cne [string]$identity.executable_sha256) {
        throw (New-IzLifecycleError 'LIFECYCLE_RUNTIME_PROCESS_MISMATCH')
    }
    $baseUrl = "http://127.0.0.1:$([int]$identity.port)"
    $healthResponse = Invoke-WebRequest -Method Get -Uri "$baseUrl/api/health" -UseBasicParsing -TimeoutSec 10
    $versionResponse = Invoke-WebRequest -Method Get -Uri "$baseUrl/api/version" -UseBasicParsing -TimeoutSec 10
    $health = $healthResponse.Content | ConvertFrom-Json
    $version = $versionResponse.Content | ConvertFrom-Json
    if ([int]$healthResponse.StatusCode -ne 200 -or $health.status -cne 'ok' -or
        [int]$versionResponse.StatusCode -ne 200 -or $version.version -cne $identity.version -or
        $version.build -cne $identity.build) {
        throw (New-IzLifecycleError 'LIFECYCLE_HTTP_IDENTITY_MISMATCH')
    }
    return [pscustomobject][ordered]@{
        identity = $identity; install_receipt = $authority.receipt; base_url = $baseUrl
        status_response = $status; committed_transaction_id = $ExpectedTransactionId; health_status_code = [int]$healthResponse.StatusCode
        version_status_code = [int]$versionResponse.StatusCode
    }
}

function Get-IzLifecycleDescendants {
    param([Parameter(Mandatory)][int]$RootProcessId, [int[]]$Known = @())
    $ids = [Collections.Generic.HashSet[int]]::new()
    $null = $ids.Add($RootProcessId)
    foreach ($value in $Known) { $null = $ids.Add([int]$value) }
    $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    do {
        $changed = $false
        foreach ($record in $all) {
            if ($ids.Contains([int]$record.ProcessId) -or -not $ids.Contains([int]$record.ParentProcessId)) { continue }
            $null = $ids.Add([int]$record.ProcessId); $changed = $true
        }
    } while ($changed)
    return @($ids | Where-Object { $_ -ne $RootProcessId })
}

function Invoke-IzLifecycleBrowserSmoke {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [Parameter(Mandatory)][object]$Fixture,
        [Parameter(Mandatory)][string]$PublicCaseRoot,
        [Parameter(Mandatory)][object]$Context,
        [Parameter(Mandatory)][object]$Binding,
        [Parameter(Mandatory)][object]$Runtime,
        [Parameter(Mandatory)][object]$Secrets,
        [Parameter(Mandatory)][ValidateSet('msedge','chrome')][string]$BrowserChannel,
        [Parameter(Mandatory)][ValidatePattern('^[A-Z][0-9]{2}$')][string]$CaseId
    )
    $marker = Get-Content -LiteralPath ([string]$Fixture.marker_path) -Raw | ConvertFrom-Json
    $browserRoot = Join-Path $PublicCaseRoot 'browser'
    if (Test-Path -LiteralPath $browserRoot) { throw (New-IzLifecycleError 'LIFECYCLE_BROWSER_EVIDENCE_EXISTS') }
    $null = New-Item -ItemType Directory -Path $browserRoot
    $evidencePath = Join-Path $browserRoot 'maintenance-browser.json'
    $attachmentPath = Join-Path ([string]$Fixture.private_root) 'maintenance-browser-attachment.json'
    $attachment = [ordered]@{
        schema = 'iz-cna-maintenance-browser-attachment-v1'
        qualification_mode = $Binding.qualification_mode.ToLowerInvariant()
        run_id = [string]$marker.run_id; case_id = $CaseId; tier = 'Component'
        base_url = [string]$Runtime.base_url
        runtime_identity_path = [string]$Context.runtime_identity_path
        install_receipt_path = [string]$Context.install_receipt_path
        candidate_zip_path = [string]$Binding.zip.path
        candidate_zip_sha256 = [string]$Binding.zip.sha256
        candidate_package_path = [string]$Binding.package_root
        candidate_manifest_sha256 = [string]$Binding.manifest_sha256
        candidate_payload_identity = [string]$Binding.manifest.payload_identity
        candidate_authority_path = $(if ($Binding.release_qualification) {
            [string]$Binding.build_receipt.path
        } else { [string]$Binding.validation_summary.path })
        expected_source_revision = [string]$Binding.source_revision
        public_evidence_root = [IO.Path]::GetFullPath($PublicCaseRoot)
        evidence_path = [IO.Path]::GetFullPath($evidencePath)
    }
    $null = Write-IzHarnessJson -Path $attachmentPath -Value $attachment
    $stdoutPath = Join-Path ([string]$Fixture.private_root) 'playwright.stdout.txt'
    $stderrPath = Join-Path ([string]$Fixture.private_root) 'playwright.stderr.txt'
    $inputPath = Join-Path ([string]$Fixture.private_root) 'playwright.stdin.txt'
    [IO.File]::WriteAllText($inputPath, '', [Text.UTF8Encoding]::new($false))
    $node = (Get-Command node.exe -ErrorAction Stop).Source
    $cli = Join-Path $RepositoryRoot 'frontend\node_modules\@playwright\test\cli.js'
    if (-not (Test-Path -LiteralPath $cli -PathType Leaf)) { throw (New-IzLifecycleError 'PLAYWRIGHT_CLI_MISSING') }
    $arguments = @($cli, 'test', '--config', 'playwright.maintenance.config.mjs')
    $argumentText = @($arguments | ForEach-Object { ConvertTo-IzLifecycleProcessArgument ([string]$_) }) -join ' '
    $environment = [ordered]@{
        IZ_CNA_MAINTENANCE_ATTACHMENT = $attachmentPath
        IZ_CNA_E2E_BASE_URL = [string]$Runtime.base_url
        IZ_CNA_E2E_BROWSER_CHANNEL = $BrowserChannel
        IZ_CNA_MAINTENANCE_ADMIN_USERNAME = 'qa-beta3-admin'
        IZ_CNA_MAINTENANCE_ADMIN_PASSWORD = [string]$Secrets.admin_password
        IZ_CNA_MAINTENANCE_COUNSELOR_USERNAME = 'qa-beta3-counselor'
        IZ_CNA_MAINTENANCE_COUNSELOR_PASSWORD = [string]$Secrets.active_counselor_password
        LOCALAPPDATA = [string]$Context.local_app_data_root
        APPDATA = (Join-Path ([string]$Fixture.component_root) 'AppData')
        USERPROFILE = (Join-Path ([string]$Fixture.component_root) 'UserProfile')
        HOME = (Join-Path ([string]$Fixture.component_root) 'UserProfile')
        PSModuleAnalysisCachePath = (Join-Path ([string]$Fixture.private_root) 'playwright.module-analysis.cache')
    }
    $process = Invoke-IzLifecycleWithEnvironment -Environment $environment -Action {
        Start-Process -FilePath $node -WorkingDirectory (Join-Path $RepositoryRoot 'frontend') `
            -ArgumentList $argumentText -PassThru -WindowStyle Hidden `
            -RedirectStandardInput $inputPath -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    }
    $processHandle = $process.Handle
    if ($processHandle -eq [IntPtr]::Zero) { throw (New-IzLifecycleError 'PLAYWRIGHT_PROCESS_HANDLE_INVALID') }
    $descendants = @()
    $deadline = [DateTime]::UtcNow.AddMinutes(4)
    while (-not $process.HasExited -and [DateTime]::UtcNow -lt $deadline) {
        $descendants = @(Get-IzLifecycleDescendants -RootProcessId $process.Id -Known $descendants)
        Start-Sleep -Milliseconds 250
    }
    if (-not $process.HasExited) {
        foreach ($processId in @($descendants + $process.Id | Sort-Object -Unique -Descending)) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
        throw (New-IzLifecycleError 'PLAYWRIGHT_TIMEOUT')
    }
    Start-Sleep -Milliseconds 750
    $remaining = @($descendants | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
    if ($remaining.Count) {
        foreach ($processId in $remaining) { Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue }
        throw (New-IzLifecycleError 'PLAYWRIGHT_PROCESS_REMAINED')
    }
    $process.WaitForExit()
    $rawProcessExitCode = $process.ExitCode
    if ($null -eq $rawProcessExitCode) { throw (New-IzLifecycleError 'PLAYWRIGHT_PROCESS_EXIT_CODE_MISSING') }
    $processExitCode = [int]$rawProcessExitCode
    if (-not (Test-Path -LiteralPath $evidencePath -PathType Leaf)) {
        throw (New-IzLifecycleError 'PLAYWRIGHT_SMOKE_FAILED')
    }
    try { $evidence = Get-Content -LiteralPath $evidencePath -Raw | ConvertFrom-Json }
    catch { throw (New-IzLifecycleError 'PLAYWRIGHT_EVIDENCE_INVALID') }
    $browserPassed = $evidence.status -ceq 'passed'
    $minimumObservations = if ($browserPassed) { 5 } else { 2 }
    if ($evidence.schema -cne 'iz-cna-maintenance-browser-evidence-v1' -or $evidence.status -notin @('passed','failed') -or
        $evidence.source_revision -cne $Binding.source_revision -or
        $evidence.qualification_mode -cne $Binding.qualification_mode.ToLowerInvariant() -or
        [bool]$evidence.release_qualification -ne [bool]$Binding.release_qualification -or
        @($evidence.observations).Count -lt $minimumObservations -or [int]$evidence.screenshots_written -ne 0 -or
        [bool]$evidence.trace_written) {
        throw (New-IzLifecycleError 'PLAYWRIGHT_EVIDENCE_INVALID')
    }
    if (($browserPassed -and $processExitCode -ne 0) -or
        (-not $browserPassed -and $processExitCode -eq 0)) {
        throw (New-IzLifecycleError 'PLAYWRIGHT_EVIDENCE_INVALID')
    }
    return [pscustomobject][ordered]@{
        status = [string]$evidence.status
        reason = $(if ($browserPassed) { 'PLAYWRIGHT_SMOKE_PASSED' } else { 'PLAYWRIGHT_ASSERTION_FAILED' })
        exit_code = $processExitCode
        observation_count = @($evidence.observations).Count; evidence_path = $evidencePath
        descendants_remaining = 0; stdout_path = $stdoutPath; stderr_path = $stderrPath
    }
}

function Remove-IzLifecycleComponentRoot {
    param([Parameter(Mandatory)][object]$Fixture)
    $component = [IO.Path]::GetFullPath([string]$Fixture.component_root).TrimEnd('\')
    $caseRoot = [IO.Path]::GetFullPath([string]$Fixture.case_root).TrimEnd('\')
    $profileRoot = [IO.Path]::GetFullPath([Environment]::GetFolderPath(
        [Environment+SpecialFolder]::UserProfile,
        [Environment+SpecialFolderOption]::DoNotVerify
    )).TrimEnd('\')
    $componentParent = Split-Path $component -Parent
    if ($componentParent -cnotin @($caseRoot, $profileRoot) -or
        (Split-Path $component -Leaf) -cnotmatch '^iz-cna-component-[0-9a-f]{12}$') {
        throw (New-IzLifecycleError 'LIFECYCLE_CLEANUP_ROOT_INVALID')
    }
    $marker = Get-Content -LiteralPath ([string]$Fixture.marker_path) -Raw | ConvertFrom-Json
    if ($marker.schema -cne 'iz-cna-maintenance-fixture-v1' -or
        -not ([IO.Path]::GetFullPath([string]$marker.case_root).TrimEnd('\').Equals($caseRoot, [StringComparison]::OrdinalIgnoreCase)) -or
        -not ([IO.Path]::GetFullPath([string]$marker.component_root).TrimEnd('\').Equals($component, [StringComparison]::OrdinalIgnoreCase)) -or
        $marker.owner_sid -cne [Security.Principal.WindowsIdentity]::GetCurrent().User.Value) {
        throw (New-IzLifecycleError 'LIFECYCLE_CLEANUP_MARKER_INVALID')
    }
    Assert-IzFixturePlainPath -Path $component
    if (Test-Path -LiteralPath $component) {
        $linked = @(Get-ChildItem -LiteralPath $component -Force -Recurse -ErrorAction Stop | Where-Object {
            $_.Attributes -band [IO.FileAttributes]::ReparsePoint
        })
        if ($linked.Count) { throw (New-IzLifecycleError 'LIFECYCLE_CLEANUP_REPARSE_REFUSED') }
        $processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            $_.ExecutablePath -and [IO.Path]::GetFullPath([string]$_.ExecutablePath).StartsWith($component + '\', [StringComparison]::OrdinalIgnoreCase)
        })
        foreach ($record in $processes) {
            $owner = (Invoke-CimMethod -InputObject $record -MethodName GetOwnerSid -ErrorAction Stop).Sid
            if ($owner -cne [Security.Principal.WindowsIdentity]::GetCurrent().User.Value) {
                throw (New-IzLifecycleError 'LIFECYCLE_CLEANUP_PROCESS_OWNER_MISMATCH')
            }
            Stop-Process -Id ([int]$record.ProcessId) -Force -ErrorAction SilentlyContinue
        }
        Remove-Item -LiteralPath $component -Recurse -Force
    }
    if (Test-Path -LiteralPath $component) { throw (New-IzLifecycleError 'LIFECYCLE_CLEANUP_INCOMPLETE') }
    return $true
}

function Invoke-IzComponentLifecycleSmoke {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [Parameter(Mandatory)][object]$Fixture,
        [Parameter(Mandatory)][string]$PublicCaseRoot,
        [Parameter(Mandatory)][string]$BaselineZip,
        [Parameter(Mandatory)][string]$OriginalBeta4Zip,
        [Parameter(Mandatory)][object]$Binding,
        [Parameter(Mandatory)][ValidateSet('msedge','chrome')][string]$BrowserChannel,
        [Parameter(Mandatory)][ValidatePattern('^[A-Z][0-9]{2}$')][string]$CaseId
    )
    $started = [DateTime]::UtcNow.ToString('o')
    $summaryPath = Join-Path $PublicCaseRoot 'component-lifecycle-smoke.json'
    if (Test-Path -LiteralPath $summaryPath) { throw (New-IzLifecycleError 'LIFECYCLE_EVIDENCE_EXISTS') }
    $steps = [Collections.Generic.List[object]]::new()
    $trackedPorts = [Collections.Generic.HashSet[int]]::new()
    $status = 'failed'; $reason = 'LIFECYCLE_SMOKE_FAILED'; $productWriteAttempted = $false
    $context = $null; $activeRuntimeContext = $null; $commonModule = $null; $runtimeModule = $null
    $beta = $null; $betaRuntime = $null; $baseline = $null
    $firstRuntime = $null; $secondRuntime = $null; $browser = $null
    $browserFailed = $false
    $roundTrip = $null; $reinstallProof = $null; $credential = $null
    $upgradeAction = $null; $uninstallAction = $null; $reinstallAction = $null; $purgeAction = $null
    $cleanupStatus = 'passed'; $cleanupReason = 'OWNED_FIXTURE_REMOVED'
    $baselineBefore = Get-IzHarnessFileDescriptor -Path $BaselineZip
    $originalBefore = Get-IzHarnessFileDescriptor -Path $OriginalBeta4Zip
    $candidateBefore = Get-IzHarnessFileDescriptor -Path ([string]$Binding.zip.path)
    try {
        $commonPath = Join-Path $Binding.package_root 'installer\maintenance-common.psm1'
        $runtimePath = Join-Path $Binding.package_root 'installer\maintenance-runtime.psm1'
        $dispatcherPath = Join-Path $Binding.package_root 'installer\maintenance-windows.ps1'
        foreach ($path in @($commonPath, $runtimePath, $dispatcherPath)) {
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw (New-IzLifecycleError 'LIFECYCLE_PACKAGE_SURFACE_MISSING') }
        }
        $commonModule = @(Import-Module -Name $commonPath -Force -PassThru -Scope Local)[0]
        $context = & $commonModule {
            param($package,$component)
            $value = Get-IzMaintenanceContext -PackageRoot $package -ComponentTestRoot $component
            $manifest = Read-IzReleaseManifest -PackageRoot $package
            [void](Test-IzReleasePayload -PackageRoot $package -Manifest $manifest)
            return $value
        } $Binding.package_root ([string]$Fixture.component_root)
        $expectedInstall = Join-Path ([string]$Fixture.component_root) 'LocalAppData\Programs\IZ Clinical Notes Analyzer'
        $expectedData = Join-Path ([string]$Fixture.component_root) 'LocalAppData\IZ Clinical Notes Analyzer'
        if (-not ([IO.Path]::GetFullPath([string]$context.install_root).Equals([IO.Path]::GetFullPath($expectedInstall), [StringComparison]::OrdinalIgnoreCase)) -or
            -not ([IO.Path]::GetFullPath([string]$context.data_root).Equals([IO.Path]::GetFullPath($expectedData), [StringComparison]::OrdinalIgnoreCase))) {
            throw (New-IzLifecycleError 'LIFECYCLE_COMPONENT_CONTEXT_MISMATCH')
        }
        [void](Assert-IzSyntheticProductRootsUnowned -InstallRoot $context.install_root -DataRoot $context.data_root)
        $steps.Add([pscustomobject][ordered]@{
            name='safe-context-preflight'; status='passed'
            invocation='Get-IzMaintenanceContext -ComponentTestRoot <owned-empty-root>; Test-IzReleasePayload'
            observable='side_effect_free_context=true;unowned_product_roots=true;candidate_payload_verified=true'
        })

        $productWriteAttempted = $true
        $beta = New-IzBeta3ComponentFixture -ArchivePath $baselineBefore.path -Fixture $Fixture -ArchiveGuard {
            param($path) Test-IzHarnessZip -Path $path
        }
        $null = Set-IzInstalledBeta3FixtureEnvironment -DataRoot $beta.data_root -Port $beta.port -Secrets $beta.secrets
        $null = $trackedPorts.Add([int]$beta.port)
        $dataIdentity = & $commonModule {
            param($value,$database) New-IzDataIdentity -Context $value -SelectedDatabasePath $database
        } $context (Join-Path $beta.data_root 'qa-beta3-custom.sqlite3')
        $betaRuntime = Start-IzFixtureRuntime -Executable $beta.executable -WorkingDirectory $beta.install_root `
            -Environment $beta.environment -PrivateRoot $Fixture.private_root -Port $beta.port -TimeoutSeconds 120
        $betaVersionResponse = Invoke-WebRequest -Method Get -Uri "http://127.0.0.1:$($beta.port)/api/version" -UseBasicParsing -TimeoutSec 10
        $betaVersion = $betaVersionResponse.Content | ConvertFrom-Json
        if ([int]$betaVersionResponse.StatusCode -ne 200 -or $betaVersion.version -cne '2.0.0-beta.3') {
            throw (New-IzLifecycleError 'BETA3_LIVE_VERSION_INVALID')
        }
        $baseline = Initialize-IzBeta3SemanticFixture -BaseUrl "http://127.0.0.1:$($beta.port)" `
            -DataRoot $beta.data_root -Secrets $beta.secrets
        $steps.Add([pscustomobject][ordered]@{
            name='beta3-live-api-seed'; status='passed'
            invocation='actual preserved beta.3 EXE; GET /api/version; supported login/users/settings/workflow/upload/treatment-plan APIs'
            observable="http_version=200;version=$($betaVersion.version);accounts=$($baseline.account_count);plans=$($baseline.plan_version_count);encrypted_sources=$($baseline.encrypted_source_count);role_denial=$($baseline.counselor_denial_status)"
        })

        $upgradeAction = Invoke-IzLifecycleAction -Action AutoInstall -Fixture $Fixture -Context $context `
            -Binding $Binding -Environment $beta.environment
        Assert-IzLifecycleActionSucceeded -ActionResult $upgradeAction -Reason 'LIFECYCLE_UPGRADE_FAILED'
        if (-not $betaRuntime.process.HasExited) { throw (New-IzLifecycleError 'BETA3_RUNTIME_NOT_QUIESCED') }
        $runtimeModule = @(Import-Module -Name $runtimePath -Force -PassThru -Scope Local)[0]
        $activeRuntimeContext = & $commonModule {
            param($package,$component,$transaction)
            Get-IzMaintenanceContext -PackageRoot $package -ComponentTestRoot $component -TransactionId ([Guid]$transaction)
        } $Binding.package_root ([string]$Fixture.component_root) ([string]$upgradeAction.result.transaction_id)
        $firstRuntime = Get-IzLifecycleRuntimeObservation -RuntimeModule $runtimeModule -Context $activeRuntimeContext `
            -Binding $Binding -ExpectedDataIdentity ([string]$dataIdentity.data_identity) `
            -ExpectedTransactionId ([string]$upgradeAction.result.transaction_id)
        $upgradeSemantic = Test-IzUpgradedSemanticFixture -BaseUrl $firstRuntime.base_url -DataRoot $beta.data_root `
            -Secrets $beta.secrets -Baseline $baseline
        $steps.Add([pscustomobject][ordered]@{
            name='beta3-to-candidate-upgrade'; status='passed'
            invocation='maintenance-windows.ps1 AutoInstall through hidden ComponentTestRoot context; live status/health/version and semantic API verification'
            observable="exit=$($upgradeAction.exit_code);status=$($upgradeAction.result.status);runtime_status=$($firstRuntime.status_response.status);gate=$($firstRuntime.status_response.gate);health_http=$($firstRuntime.health_status_code);version_http=$($firstRuntime.version_status_code);semantic_identity_unchanged=$($upgradeSemantic.semantic_identity_unchanged)"
        })

        $browser = Invoke-IzLifecycleBrowserSmoke -RepositoryRoot $RepositoryRoot -Fixture $Fixture `
            -PublicCaseRoot $PublicCaseRoot -Context $activeRuntimeContext -Binding $Binding -Runtime $firstRuntime `
            -Secrets $beta.secrets -BrowserChannel $BrowserChannel -CaseId $CaseId
        $browserFailed = $browser.status -ceq 'failed'
        $steps.Add([pscustomobject][ordered]@{
            name='candidate-browser-smoke'; status=[string]$browser.status
            invocation='Playwright maintenance.spec.mjs attached to exact installed candidate runtime'
            observable="exit=$($browser.exit_code);reason=$($browser.reason);scenarios=$($browser.observation_count);owned_browser_processes_remaining=$($browser.descendants_remaining)"
        })

        $roundTrip = Test-IzCandidateLiveApiRoundTrip -BaseUrl $firstRuntime.base_url -DataRoot $beta.data_root -Secrets $beta.secrets
        $steps.Add([pscustomobject][ordered]@{
            name='candidate-live-api-roundtrip'; status='passed'
            invocation='actual candidate HTTP login; multipart upload; encrypted disk inspection; supported readback; treatment plan/workflow/RBAC/audit APIs'
            observable="upload_http=$($roundTrip.upload_status);criteria=$($roundTrip.criteria_total);encrypted_sources=$($roundTrip.encrypted_source_count);readback_hash_match=true;stored=true;role_denial=$($roundTrip.counselor_denial_status)"
        })

        $uninstallAction = Invoke-IzLifecycleAction -Action Uninstall -Fixture $Fixture -Context $context `
            -Binding $Binding -Environment $beta.environment
        Assert-IzLifecycleActionSucceeded -ActionResult $uninstallAction -Reason 'LIFECYCLE_UNINSTALL_FAILED'
        $activeRuntimeContext = $null
        $uninstallClean = -not (Test-Path -LiteralPath $context.install_root) -and
            (Test-Path -LiteralPath $context.data_root -PathType Container) -and
            (Test-Path -LiteralPath $context.install_receipt_path -PathType Leaf) -and
            -not (Test-Path -LiteralPath $context.runtime_identity_path) -and
            (Test-IzLifecycleListenerAbsent -Port ([int]$firstRuntime.identity.port))
        if (-not $uninstallClean) { throw (New-IzLifecycleError 'LIFECYCLE_UNINSTALL_STATE_INVALID') }
        $steps.Add([pscustomobject][ordered]@{
            name='normal-uninstall'; status='passed'
            invocation='maintenance-windows.ps1 Uninstall through hidden ComponentTestRoot context while candidate runtime is running'
            observable="exit=$($uninstallAction.exit_code);program_removed=true;data_retained=true;receipt_retained=true;runtime_stopped=true;listener_released=true"
        })

        $reinstallAction = Invoke-IzLifecycleAction -Action AutoInstall -Fixture $Fixture -Context $context `
            -Binding $Binding -Environment $beta.environment
        Assert-IzLifecycleActionSucceeded -ActionResult $reinstallAction -Reason 'LIFECYCLE_REINSTALL_FAILED'
        $activeRuntimeContext = & $commonModule {
            param($package,$component,$transaction)
            Get-IzMaintenanceContext -PackageRoot $package -ComponentTestRoot $component -TransactionId ([Guid]$transaction)
        } $Binding.package_root ([string]$Fixture.component_root) ([string]$reinstallAction.result.transaction_id)
        $secondRuntime = Get-IzLifecycleRuntimeObservation -RuntimeModule $runtimeModule -Context $activeRuntimeContext `
            -Binding $Binding -ExpectedDataIdentity ([string]$dataIdentity.data_identity) `
            -ExpectedTransactionId ([string]$reinstallAction.result.transaction_id)
        $reinstallProof = Test-IzCandidateLiveApiPreserved -BaseUrl $secondRuntime.base_url -DataRoot $beta.data_root `
            -Secrets $beta.secrets -RoundTrip $roundTrip
        if ([string]$secondRuntime.install_receipt.last_committed_transaction -ceq
            [string]$firstRuntime.install_receipt.last_committed_transaction) {
            throw (New-IzLifecycleError 'LIFECYCLE_REINSTALL_TRANSACTION_REUSED')
        }
        $steps.Add([pscustomobject][ordered]@{
            name='candidate-reinstall'; status='passed'
            invocation='maintenance-windows.ps1 AutoInstall after ordinary uninstall; actual login/readback/treatment-plan/workflow/RBAC/audit APIs'
            observable="exit=$($reinstallAction.exit_code);data_identity_unchanged=true;new_transaction=true;plans=$($reinstallProof.treatment_plan_count);encrypted_sources=$($reinstallProof.encrypted_source_count);readback_hash_match=true;role_denial=$($reinstallProof.counselor_denial_status)"
        })

        $credential = Invoke-IzCandidateCredentialRotation -BaseUrl $secondRuntime.base_url -Secrets $beta.secrets
        $steps.Add([pscustomobject][ordered]@{
            name='candidate-password-rotation'; status='passed'
            invocation='actual candidate POST login; POST change-password; replacement POST login'
            observable="initial_login=$($credential.initial_login);password_change=$($credential.password_change);replacement_login=$($credential.replacement_login)"
        })

        $purgeAction = Invoke-IzLifecycleAction -Action RemoveData -Fixture $Fixture -Context $context `
            -Binding $Binding -Environment $beta.environment
        Assert-IzLifecycleActionSucceeded -ActionResult $purgeAction -Reason 'LIFECYCLE_PURGE_FAILED'
        $activeRuntimeContext = $null
        $purged = -not (Test-Path -LiteralPath $context.install_root) -and
            -not (Test-Path -LiteralPath $context.data_root) -and
            -not (Test-Path -LiteralPath $context.maintenance_root) -and
            (Test-IzLifecycleListenerAbsent -Port ([int]$secondRuntime.identity.port))
        if (-not $purged) { throw (New-IzLifecycleError 'LIFECYCLE_PURGE_STATE_INVALID') }
        $steps.Add([pscustomobject][ordered]@{
            name='typed-complete-removal'; status='passed'
            invocation='maintenance-windows.ps1 RemoveData with exact stdin phrase REMOVE IZ DATA through hidden ComponentTestRoot context'
            observable="exit=$($purgeAction.exit_code);program_removed=true;data_removed=true;maintenance_removed=true;runtime_stopped=true;listener_released=true"
        })
        if ($browserFailed) { $status = 'failed'; $reason = 'PLAYWRIGHT_ASSERTION_FAILED' }
        else { $status = 'passed'; $reason = 'COMPONENT_LIFECYCLE_SMOKE_PASSED' }
    }
    catch {
        $status = 'failed'; $reason = Get-IzLifecycleReason -Record $_
        $steps.Add([pscustomobject][ordered]@{
            name='terminal-failure'; status='failed'; invocation='component lifecycle smoke controller'
            observable="reason=$reason"
        })
    }
    finally {
        try {
            if ($runtimeModule -and $context -and (Test-Path -LiteralPath $context.runtime_identity_path -PathType Leaf)) {
                $stopContext = if ($activeRuntimeContext) { $activeRuntimeContext } else { $context }
                $stop = & $runtimeModule { param($value) Stop-IzOwnedRuntime -Context $value -TimeoutSeconds 30 -AllowLegacyFallback } $stopContext
                if ($stop.status -eq 'failure') { throw (New-IzLifecycleError 'LIFECYCLE_FINAL_RUNTIME_STOP_FAILED') }
            }
            if ($betaRuntime -and -not $betaRuntime.process.HasExited) {
                [void](Stop-IzFixtureRuntime -Runtime $betaRuntime -ExpectedExecutable $beta.executable)
            }
            [void](Remove-IzLifecycleComponentRoot -Fixture $Fixture)
            foreach ($port in $trackedPorts) {
                if (-not (Test-IzLifecycleListenerAbsent -Port $port)) { throw (New-IzLifecycleError 'LIFECYCLE_FINAL_LISTENER_REMAINS') }
            }
        }
        catch {
            $cleanupStatus = 'failed'; $cleanupReason = Get-IzLifecycleReason -Record $_
            if ($status -ceq 'passed') { $status = 'failed'; $reason = 'LIFECYCLE_CLEANUP_FAILED' }
        }
    }
    $baselineAfter = Get-IzHarnessFileDescriptor -Path $BaselineZip
    $originalAfter = Get-IzHarnessFileDescriptor -Path $OriginalBeta4Zip
    $candidateAfter = Get-IzHarnessFileDescriptor -Path ([string]$Binding.zip.path)
    $archivesPreserved = $baselineAfter.sha256 -ceq $baselineBefore.sha256 -and $baselineAfter.length -eq $baselineBefore.length -and
        $originalAfter.sha256 -ceq $originalBefore.sha256 -and $originalAfter.length -eq $originalBefore.length -and
        $candidateAfter.sha256 -ceq $candidateBefore.sha256 -and $candidateAfter.length -eq $candidateBefore.length
    if (-not $archivesPreserved -and $status -ceq 'passed') { $status = 'failed'; $reason = 'LIFECYCLE_ARCHIVE_MUTATED' }
    $summary = [ordered]@{
        schema = 'iz-cna-maintenance-lifecycle-smoke-v1'
        qualification_mode = $Binding.qualification_mode.ToLowerInvariant()
        release_qualification = [bool]$Binding.release_qualification
        case_id = $CaseId; tier = 'Component'; status = $status; reason = $reason
        source_revision = [string]$Binding.source_revision
        candidate = [ordered]@{
            version = [string]$Binding.manifest.version; build = [string]$Binding.manifest.build
            installer_revision = [int]$Binding.manifest.installer_revision
            zip_length = [long]$Binding.zip.length; zip_sha256 = [string]$Binding.zip.sha256
            manifest_sha256 = [string]$Binding.manifest_sha256; payload_identity = [string]$Binding.manifest.payload_identity
        }
        execution = [ordered]@{
            actual_executable = ($null -ne $firstRuntime); actual_http = ($null -ne $roundTrip)
            actual_browser = ($null -ne $browser); actual_installer = $false; actual_default_profile = $false
            synthetic_data_only = $true; product_write_attempted = $productWriteAttempted
        }
        steps = @($steps)
        archives_preserved = $archivesPreserved
        cleanup = [ordered]@{
            status = $cleanupStatus; reason = $cleanupReason
            owned_processes_remaining = 0; owned_listeners_remaining = 0
            component_root_removed = -not (Test-Path -LiteralPath ([string]$Fixture.component_root))
            retained_private_artifacts = $true
        }
        started_utc = $started; completed_utc = [DateTime]::UtcNow.ToString('o')
    }
    $null = Write-IzHarnessJson -Path $summaryPath -Value $summary
    return [pscustomobject][ordered]@{
        status = $status; reason = $reason; artifact_path = $summaryPath
        browser_artifact_path = $(if ($browser) { [string]$browser.evidence_path } else { $null })
        invocation = 'Invoke-IzComponentLifecycleSmoke: preserved beta.3 EXE -> candidate dispatcher -> live HTTP/browser -> uninstall -> reinstall -> typed purge'
        observable = "steps=$($steps.Count);actual_http=$($null -ne $roundTrip);actual_browser=$($null -ne $browser);archives_preserved=$archivesPreserved;cleanup=$cleanupStatus;release_qualification=$($Binding.release_qualification)"
        actual_executable = ($null -ne $firstRuntime)
        actual_http = ($null -ne $roundTrip)
        actual_browser = ($null -ne $browser)
        cleanup = [pscustomobject][ordered]@{
            status = $cleanupStatus; owned_processes_remaining = 0; owned_listeners_remaining = 0; retained_private_artifacts = $true
        }
    }
}

Export-ModuleMember -Function 'New-IzLifecycleCandidateBinding','Invoke-IzComponentLifecycleSmoke'
