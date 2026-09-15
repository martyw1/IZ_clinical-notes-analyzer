[CmdletBinding()]
param(
    [ValidateSet('launch-stop', 'launch-negative', 'All')]
    [string]$Case = 'All',
    [string]$EvidenceRoot = ''
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $EvidenceRoot) {
    $EvidenceRoot = Join-Path $repoRoot '.omo\evidence\windows-cmd-maintenance\install\component'
}
$runRoot = Join-Path $EvidenceRoot ('launch-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
$env:PSModuleAnalysisCachePath = Join-Path $runRoot 'PSModuleAnalysisCache'
$results = New-Object System.Collections.Generic.List[object]
$componentRoots = New-Object System.Collections.Generic.List[string]

function Add-Result {
    param([string]$Name, [string]$Status, [hashtable]$Observable)
    $results.Add([ordered]@{
        name = $Name
        tier = 'Component'
        status = $Status
        binary_observables = $Observable
    }) | Out-Null
}

function Invoke-WrapperDelegationCase {
    $caseRoot = Join-Path $runRoot 'path with spaces & bang!'
    $scriptsRoot = Join-Path $caseRoot 'scripts'
    New-Item -ItemType Directory -Path $scriptsRoot -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $repoRoot 'scripts\launch-packaged-runtime.cmd') -Destination $scriptsRoot
    @'
[CmdletBinding()]
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$RemainingArguments)
exit 37
'@ | Set-Content -LiteralPath (Join-Path $scriptsRoot 'launch-packaged-runtime.ps1') -Encoding UTF8
    $cmdPath = Join-Path $scriptsRoot 'launch-packaged-runtime.cmd'
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'SilentlyContinue'
        $output = @(& $env:ComSpec /d /c call "`"$cmdPath`"" 2>&1)
        $actual = [int]$LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previousPreference }
    $passed = $actual -eq 37
    Add-Result -Name 'cmd_delegates_and_preserves_exit' -Status $(if ($passed) { 'passed' } else { 'failed' }) -Observable @{
        expected_exit = 37
        actual_exit = $actual
        output_line_count = $output.Count
    }
}

function Invoke-RuntimeModuleSurfaceCase {
    $modulePath = Join-Path $repoRoot 'scripts\installer\maintenance-runtime.psm1'
    $loaded = $false
    $exports = @()
    if (Test-Path -LiteralPath $modulePath) {
        $module = Import-Module $modulePath -Force -PassThru
        $exports = @($module.ExportedFunctions.Keys)
        $loaded = $true
    }
    $required = @(
        'Get-IzConfiguredRuntimePort',
        'Invoke-IzRuntimeControl',
        'Start-IzOwnedRuntime',
        'Stop-IzOwnedRuntime',
        'Test-IzRuntimeHttpSurface'
    )
    $missing = @($required | Where-Object { $exports -notcontains $_ })
    Add-Result -Name 'runtime_control_module_exports_frozen_surface' -Status $(if ($loaded -and $missing.Count -eq 0) { 'passed' } else { 'failed' }) -Observable @{
        module_loaded = $loaded
        missing_export_count = $missing.Count
    }
}

function New-EmptyComponentRoot {
    $path = Join-Path ([IO.Path]::GetTempPath()) ('iz-cna-component-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
    New-Item -ItemType Directory -Path $path | Out-Null
    $componentRoots.Add($path) | Out-Null
    return $path
}

function Invoke-RuntimeControlRoundTripCase {
    $commonPath = Join-Path $repoRoot 'scripts\installer\maintenance-common.psm1'
    $runtimePath = Join-Path $repoRoot 'scripts\installer\maintenance-runtime.psm1'
    if (-not (Test-Path -LiteralPath $commonPath) -or -not (Test-Path -LiteralPath $runtimePath)) {
        Add-Result -Name 'named_pipe_status_round_trip_validates_identity' -Status 'failed' -Observable @{ modules_loaded = $false }
        return
    }
    Import-Module $commonPath -Force
    Import-Module $runtimePath -Force
    $context = Get-IzMaintenanceContext -ComponentTestRoot (New-EmptyComponentRoot)
    New-Item -ItemType Directory -Path $context.data_root -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $context.data_root '.env'), 'BACKEND_PORT=48123', [Text.UTF8Encoding]::new($false))
    $configuredPort = Get-IzConfiguredRuntimePort -Context $context
    $identity = [pscustomobject][ordered]@{
        schema = 'iz-cna-runtime-identity-v1'; product_id = $context.product_id; owner_sid = $context.owner_sid
        scope_id = $context.scope_id; data_identity = ('d' * 64); instance_id = [Guid]::NewGuid().ToString('N')
        transaction_id = $null; process_id = $PID; process_started_utc = [DateTime]::UtcNow.ToString('o')
        executable_path = (Get-Process -Id $PID).Path; executable_sha256 = (Get-FileHash (Get-Process -Id $PID).Path -Algorithm SHA256).Hash.ToLowerInvariant()
        version = '2.0.0-beta.4'; build = '2026.09.10.2'; installer_revision = 0; port = $configuredPort
        pipe_name = $context.pipe_name; gate = 'open'; draining = $false; created_utc = [DateTime]::UtcNow.ToString('o')
    }
    $response = [ordered]@{
        schema = 'iz-cna-runtime-control-v1'; request_id = ''; operation = 'status'; status = 'ok'; reason = 'status'
        product_id = $identity.product_id; owner_sid = $identity.owner_sid; scope_id = $identity.scope_id
        data_identity = $identity.data_identity; instance_id = $identity.instance_id; transaction_id = $null
        process_id = $identity.process_id; process_started_utc = $identity.process_started_utc
        version = $identity.version; build = $identity.build; installer_revision = $identity.installer_revision
        port = $identity.port; gate = 'open'; draining = $false; active_business_requests = 0
    }
    $responseBase64 = [Convert]::ToBase64String([Text.UTF8Encoding]::new($false).GetBytes(($response | ConvertTo-Json -Compress)))
    $serverSource = @"
`$PipeName = '$($context.pipe_name)'
`$ResponseJson = [Text.UTF8Encoding]::new(`$false).GetString([Convert]::FromBase64String('$responseBase64'))
`$pipe = [IO.Pipes.NamedPipeServerStream]::new(`$PipeName, [IO.Pipes.PipeDirection]::InOut, 1, [IO.Pipes.PipeTransmissionMode]::Message, [IO.Pipes.PipeOptions]::None)
try {
    `$pipe.WaitForConnection()
    `$reader = [IO.StreamReader]::new(`$pipe, [Text.UTF8Encoding]::new(`$false), `$false, 1024, `$true)
    `$writer = [IO.StreamWriter]::new(`$pipe, [Text.UTF8Encoding]::new(`$false), 1024, `$true)
    `$writer.NewLine = "`n"; `$writer.AutoFlush = `$true
    `$request = `$reader.ReadLine() | ConvertFrom-Json
    `$reply = `$ResponseJson | ConvertFrom-Json
    `$reply.request_id = `$request.request_id
    `$writer.WriteLine((`$reply | ConvertTo-Json -Compress))
} finally { if (`$pipe) { `$pipe.Dispose() } }
"@
    $encodedServer = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($serverSource))
    $serverProcess = Start-Process powershell.exe -ArgumentList @('-NoProfile','-EncodedCommand',$encodedServer) -PassThru -WindowStyle Hidden
    try {
        Start-Sleep -Milliseconds 500
        $actual = Invoke-IzRuntimeControl -Context $context -Operation status -RuntimeIdentity $identity -TimeoutSeconds 5
        $passed = $actual.status -ceq 'ok' -and [int]$actual.active_business_requests -eq 0 -and $actual.instance_id -ceq $identity.instance_id
        Add-Result -Name 'named_pipe_status_round_trip_validates_identity' -Status $(if ($passed) { 'passed' } else { 'failed' }) -Observable @{
            modules_loaded = $true; status = [string]$actual.status; active_business_requests = [int]$actual.active_business_requests
            identity_matched = ($actual.instance_id -ceq $identity.instance_id)
        }
        $configuredPassed = $configuredPort -eq 48123 -and [int]$actual.port -eq $configuredPort -and $actual.status -ceq 'ok'
        Add-Result -Name 'configured_port_runtime_readiness' -Status $(if ($configuredPassed) { 'passed' } else { 'failed' }) -Observable @{
            configured_port = [int]$configuredPort
            runtime_identity_port = [int]$actual.port
            control_status = [string]$actual.status
        }
    } finally {
        if (-not $serverProcess.WaitForExit(10000)) { Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue }
    }
}

function Invoke-RuntimeIdentityTimeoutCase {
    Import-Module (Join-Path $repoRoot 'scripts\installer\maintenance-common.psm1') -Force
    Import-Module (Join-Path $repoRoot 'scripts\installer\maintenance-runtime.psm1') -Force
    $context = Get-IzMaintenanceContext -ComponentTestRoot (New-EmptyComponentRoot)
    Initialize-IzMaintenanceStorage -Context $context | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $context.install_root 'runtime'), $context.data_root -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $context.data_root '.env'), 'BACKEND_PORT=48124', [Text.UTF8Encoding]::new($false))
    $source = 'using System.Threading; public static class Program { public static void Main() { Thread.Sleep(30000); } }'
    $executable = Join-Path $context.install_root 'runtime\IZClinicalNotesAnalyzer.exe'
    Add-Type -TypeDefinition $source -Language CSharp -OutputAssembly $executable -OutputType ConsoleApplication
    $runtimeRecord = [pscustomobject][ordered]@{
        path='app/runtime/IZClinicalNotesAnalyzer.exe'; length=[long](Get-Item $executable).Length
        sha256=(Get-FileHash $executable -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $canonical = "$($runtimeRecord.path)`t$($runtimeRecord.length)`t$($runtimeRecord.sha256)`n"
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $payloadIdentity = ([BitConverter]::ToString($sha.ComputeHash([Text.UTF8Encoding]::new($false).GetBytes($canonical)))).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose() }
    $manifest = [pscustomobject][ordered]@{
        schema='iz-cna-release-manifest-v1'; product_id=$context.product_id; version='2.0.0-beta.4'; build='2026.09.10.2'
        installer_revision=1; release_channel='beta-local-desktop-v2'; compatibility=[pscustomobject][ordered]@{
            source_version_minimum='2.0.0-beta.3'; source_version_maximum='2.0.0-beta.4'; source_build_minimum='2026.09.03.1'
            source_build_maximum='2026.09.10.2'; source_schema_minimum=12; source_schema_maximum=12; target_schema=12
        }; payload_identity=$payloadIdentity; files=@($runtimeRecord)
    }
    $manifestPath = Join-Path $context.install_root 'release-manifest.json'
    [IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    $owned = @(
        [pscustomobject][ordered]@{path='runtime/IZClinicalNotesAnalyzer.exe';length=$runtimeRecord.length;sha256=$runtimeRecord.sha256},
        [pscustomobject][ordered]@{path='release-manifest.json';length=[long](Get-Item $manifestPath).Length;sha256=(Get-FileHash $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()}
    )
    $release = New-IzReleaseIdentity $manifest.version $manifest.build $manifest.installer_revision $manifest.payload_identity
    $receipt = New-IzInstallReceipt $context ('d' * 64) $release $owned @() ([Guid]::NewGuid())
    Write-IzInstallReceipt $context $receipt $null | Out-Null
    $reason = ''
    try { Start-IzOwnedRuntime -Context $context -RuntimeRole Installed -TimeoutSeconds 1 -NoBrowser | Out-Null }
    catch { $reason = if ($_.Exception.Data.Contains('iz_reason')) { [string]$_.Exception.Data['iz_reason'] } else { [string]$_.Exception.Message } }
    $remaining = @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.Equals($executable, [StringComparison]::OrdinalIgnoreCase) })
    $passed = $reason -ceq 'RUNTIME_IDENTITY_TIMEOUT' -and $remaining.Count -eq 0
    Add-Result -Name 'runtime_identity_timeout_fails' -Status $(if ($passed) { 'passed' } else { 'failed' }) -Observable @{
        reason = $reason
        expected_reason = 'RUNTIME_IDENTITY_TIMEOUT'
        processes_remaining = $remaining.Count
    }
}

function Invoke-StopIdentityGuardCase {
    $commonPath = Join-Path $repoRoot 'scripts\installer\maintenance-common.psm1'
    $runtimePath = Join-Path $repoRoot 'scripts\installer\maintenance-runtime.psm1'
    if (-not (Test-Path -LiteralPath $commonPath) -or -not (Test-Path -LiteralPath $runtimePath)) {
        Add-Result -Name 'stop_blocks_mismatched_runtime_identity' -Status 'failed' -Observable @{ modules_loaded = $false }
        return
    }
    Import-Module $commonPath -Force
    Import-Module $runtimePath -Force
    $componentRoot = New-EmptyComponentRoot
    $context = Get-IzMaintenanceContext -ComponentTestRoot $componentRoot
    Initialize-IzMaintenanceStorage -Context $context | Out-Null
    $badIdentity = [ordered]@{
        schema = 'iz-cna-runtime-identity-v1'; product_id = $context.product_id; owner_sid = $context.owner_sid
        scope_id = $context.scope_id; data_identity = ('d' * 64); instance_id = [Guid]::NewGuid().ToString('N')
        transaction_id = $null; process_id = $PID; process_started_utc = [DateTime]::UtcNow.ToString('o')
        executable_path = 'C:\mismatched\IZClinicalNotesAnalyzer.exe'; executable_sha256 = ('e' * 64)
        version = '2.0.0-beta.4'; build = '2026.09.10.2'; installer_revision = 0; port = 8123
        pipe_name = $context.pipe_name; gate = 'open'; draining = $false; created_utc = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText($context.runtime_identity_path, ($badIdentity | ConvertTo-Json -Compress), [Text.UTF8Encoding]::new($false))
    $actual = Stop-IzOwnedRuntime -Context $context -TimeoutSeconds 1
    $passed = $actual.status -ceq 'failure' -and -not (Get-Process -Id $PID).HasExited
    Add-Result -Name 'stop_blocks_mismatched_runtime_identity' -Status $(if ($passed) { 'passed' } else { 'failed' }) -Observable @{
        status = [string]$actual.status; caller_process_survived = (-not (Get-Process -Id $PID).HasExited)
    }

    $runtimeDirectory = Join-Path $context.install_root 'runtime'
    New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null
    $staleExecutable = Join-Path $runtimeDirectory 'IZClinicalNotesAnalyzer.exe'
    $source = 'namespace IzStaleStop { using System.Threading; public static class Program { public static void Main() { Thread.Sleep(30000); } } }'
    Add-Type -TypeDefinition $source -Language CSharp -OutputAssembly $staleExecutable -OutputType ConsoleApplication
    $staleProcess = Start-Process -FilePath $staleExecutable -PassThru -WindowStyle Hidden
    $staleHandle = $staleProcess.Handle
    try {
        $staleTransaction = [Guid]::NewGuid()
        $wrongContext = Get-IzMaintenanceContext -ComponentTestRoot $componentRoot -TransactionId ([Guid]::NewGuid())
        $staleIdentity = [ordered]@{
            schema = 'iz-cna-runtime-identity-v1'; product_id = $context.product_id; owner_sid = $context.owner_sid
            scope_id = $context.scope_id; data_identity = ('d' * 64); instance_id = [Guid]::NewGuid().ToString('N')
            transaction_id = $staleTransaction.ToString('N'); process_id = [int]$staleProcess.Id
            process_started_utc = $staleProcess.StartTime.ToUniversalTime().ToString('o')
            executable_path = $staleExecutable
            executable_sha256 = (Get-FileHash -LiteralPath $staleExecutable -Algorithm SHA256).Hash.ToLowerInvariant()
            version = '2.0.0-beta.4'; build = '2026.09.10.2'; installer_revision = 1; port = 8124
            pipe_name = $context.pipe_name; gate = 'open'; draining = $false; created_utc = [DateTime]::UtcNow.ToString('o')
        }
        [IO.File]::WriteAllText($context.runtime_identity_path, ($staleIdentity | ConvertTo-Json -Compress), [Text.UTF8Encoding]::new($false))
        $wrong = Stop-IzOwnedRuntime -Context $wrongContext -TimeoutSeconds 1
        $unbound = Stop-IzOwnedRuntime -Context $context -TimeoutSeconds 1
        $stalePassed = $wrong.status -ceq 'failure' -and $wrong.reason -ceq 'RUNTIME_TRANSACTION_MISMATCH' -and
            $unbound.status -ceq 'failure' -and $unbound.reason -ceq 'RUNTIME_TRANSACTION_MISMATCH' -and
            -not $staleProcess.HasExited
        Add-Result -Name 'stop_rejects_wrong_and_unbound_transaction_identity' -Status $(if ($stalePassed) { 'passed' } else { 'failed' }) -Observable @{
            wrong_transaction_reason = [string]$wrong.reason
            unbound_transaction_reason = [string]$unbound.reason
            process_survived_both_refusals = (-not $staleProcess.HasExited)
        }
    }
    finally {
        if (-not $staleProcess.HasExited) { Stop-Process -Id $staleProcess.Id -Force -ErrorAction SilentlyContinue }
        $staleProcess.WaitForExit()
        $staleProcess.Dispose()
    }
}

if ($Case -in @('launch-stop', 'All')) {
    Invoke-WrapperDelegationCase
    Invoke-RuntimeModuleSurfaceCase
    Invoke-RuntimeControlRoundTripCase
    Invoke-RuntimeIdentityTimeoutCase
}
if ($Case -in @('launch-negative', 'All')) {
    $launcherText = Get-Content -LiteralPath (Join-Path $repoRoot 'scripts\launch-packaged-runtime.cmd') -Raw
    $safe = (
        $launcherText -match 'DisableDelayedExpansion' -and
        $launcherText -notmatch 'for /f' -and
        $launcherText -match 'launch-packaged-runtime\.ps1'
    )
    Add-Result -Name 'cmd_does_not_parse_environment_or_enable_delayed_expansion' -Status $(if ($safe) { 'passed' } else { 'failed' }) -Observable @{
        delegated = ($launcherText -match 'launch-packaged-runtime\.ps1')
        inline_env_parser_absent = ($launcherText -notmatch 'for /f')
        delayed_expansion_disabled = ($launcherText -match 'DisableDelayedExpansion')
    }
    Invoke-StopIdentityGuardCase
}

$failed = @($results | Where-Object { $_.status -eq 'failed' })
$blocked = @($results | Where-Object { $_.status -eq 'blocked' })
$receipt = [ordered]@{
    schema = 'iz-cna-maintenance-component-suite-v1'
    suite = 'maintenance-launch-stop'
    requested_case = $Case
    tier = 'Component'
    status = if ($failed.Count) { 'failed' } elseif ($blocked.Count) { 'blocked' } else { 'passed' }
    invocation = "powershell.exe -NoProfile -File scripts\\tests\\maintenance-launch-stop.Tests.ps1 -Case $Case"
    results = $results
    artifacts = @('task-08-launch.json', 'task-08-stop.json')
    cleanup = @{ processes_remaining = 0; retained_owned_evidence = $true }
}
$receiptPath = Join-Path $runRoot 'task-08-launch.json'
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $runRoot 'task-08-stop.json') -Encoding UTF8
foreach ($componentRoot in @($componentRoots)) {
    if (Test-Path -LiteralPath $componentRoot) { Remove-Item -LiteralPath $componentRoot -Recurse -Force }
}
Write-Host "Evidence: $receiptPath"
if ($failed.Count) { exit 1 }
if ($blocked.Count) { exit 2 }
exit 0
