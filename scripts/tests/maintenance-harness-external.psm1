Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:ProductId = 'r3.iz-clinical-notes-analyzer.desktop'
$script:ExecutionKeys = @('executor','actual_installer','actual_executable','actual_browser','actual_default_profile','actual_home_edition','actual_power_loss','synthetic_data_only')
$script:SafetyKeys = @('owned_root_verified','current_user_scope','reparse_free','input_hashes_rechecked','redaction_scan')
$script:CleanupKeys = @('status','owned_processes_remaining','owned_listeners_remaining','retained_private_artifacts')

function New-IzExternalHarnessError {
    param([Parameter(Mandatory)][string]$Reason)
    $exception = [IO.InvalidDataException]::new($Reason)
    $exception.Data['iz_reason'] = $Reason
    return $exception
}

function Assert-IzExternalExactKeys {
    param([object]$Value, [string[]]$Keys, [string]$Reason)
    if ($null -eq $Value -or
        @(Compare-Object @($Value.PSObject.Properties.Name | Sort-Object) @($Keys | Sort-Object)).Count -ne 0) {
        throw (New-IzExternalHarnessError $Reason)
    }
}

function Get-IzExternalPathHash {
    param([Parameter(Mandatory)][string]$Path)
    $canonical = [IO.Path]::GetFullPath($Path).TrimEnd('\').Normalize([Text.NormalizationForm]::FormC)
    $builder = [Text.StringBuilder]::new()
    foreach ($character in $canonical.ToCharArray()) {
        if ($character -ge 'A' -and $character -le 'Z') { $null = $builder.Append([char]([int]$character + 32)) }
        else { $null = $builder.Append($character) }
    }
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes($builder.ToString())
        return ([BitConverter]::ToString($algorithm.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    }
    finally { $algorithm.Dispose() }
}

function Assert-IzExternalLocalFile {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Reason)
    if ($Path -cnotmatch '^[A-Za-z]:[\\/]' -or $Path.StartsWith('\\?\') -or $Path.StartsWith('\\.\') -or
        $Path.Substring(2) -match ':' -or @($Path -split '[\\/]' | Where-Object { $_ -in @('.', '..') }).Count) {
        throw (New-IzExternalHarnessError $Reason)
    }
    $fullPath = [IO.Path]::GetFullPath($Path)
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) { throw (New-IzExternalHarnessError $Reason) }
    $cursor = $fullPath
    while ($cursor) {
        if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw (New-IzExternalHarnessError $Reason)
        }
        $parent = Split-Path -Parent $cursor
        if (-not $parent -or $parent -eq $cursor) { break }
        $cursor = $parent
    }
    return $fullPath
}

function Read-IzExternalTierRunner {
    param(
        [Parameter(Mandatory)][ValidateSet('Package','Home','PowerLoss')][string]$Tier,
        [string]$VmControlManifest = ''
    )
    if ($Tier -ceq 'PowerLoss') {
        if (-not $VmControlManifest) { throw (New-IzExternalHarnessError 'VM_CONTROL_MANIFEST_REQUIRED') }
        $manifestPath = Assert-IzExternalLocalFile -Path $VmControlManifest -Reason 'VM_CONTROL_MANIFEST_INVALID'
        try { $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json }
        catch { throw (New-IzExternalHarnessError 'VM_CONTROL_MANIFEST_INVALID') }
        Assert-IzExternalExactKeys $manifest @(
            'schema','product_id','owner_sid','vm_id','vm_owner_marker','runner_path','runner_sha256',
            'supported_os','operations','created_utc'
        ) 'VM_CONTROL_MANIFEST_INVALID'
        if ($manifest.schema -cne 'iz-cna-powerloss-runner-v1' -or $manifest.product_id -cne $script:ProductId -or
            $manifest.owner_sid -cne [Security.Principal.WindowsIdentity]::GetCurrent().User.Value -or
            $manifest.vm_id -cnotmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{2,80}$' -or
            @(Compare-Object @($manifest.supported_os | Sort-Object) @('Windows 10 Home','Windows 11 Home')).Count -ne 0 -or
            @(Compare-Object @($manifest.operations | Sort-Object) @('power_off','revert','snapshot','start','wait')).Count -ne 0) {
            throw (New-IzExternalHarnessError 'VM_CONTROL_MANIFEST_INVALID')
        }
        $ownerPath = Assert-IzExternalLocalFile -Path ([string]$manifest.vm_owner_marker) -Reason 'VM_OWNER_MARKER_INVALID'
        try { $owner = Get-Content -LiteralPath $ownerPath -Raw | ConvertFrom-Json }
        catch { throw (New-IzExternalHarnessError 'VM_OWNER_MARKER_INVALID') }
        Assert-IzExternalExactKeys $owner @('schema','product_id','vm_id','created_utc') 'VM_OWNER_MARKER_INVALID'
        if ($owner.schema -cne 'iz-cna-powerloss-vm-owner-v1' -or $owner.product_id -cne $script:ProductId -or
            $owner.vm_id -cne $manifest.vm_id) { throw (New-IzExternalHarnessError 'VM_OWNER_MARKER_INVALID') }
    }
    else {
        $qaParent = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'IZ-CNA-QA'
        $manifestPath = Join-Path $qaParent '.iz-cna-maintenance-tier-runner.json'
        if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
            throw (New-IzExternalHarnessError 'TIER_RUNNER_NOT_PROVISIONED')
        }
        try { $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json }
        catch { throw (New-IzExternalHarnessError 'TIER_RUNNER_MANIFEST_INVALID') }
        Assert-IzExternalExactKeys $manifest @(
            'schema','product_id','owner_sid','profile_path_hash','runner_path','runner_sha256',
            'supported_tiers','created_utc'
        ) 'TIER_RUNNER_MANIFEST_INVALID'
        $profile = [Environment]::GetFolderPath('UserProfile')
        if ($manifest.schema -cne 'iz-cna-maintenance-tier-runner-v1' -or $manifest.product_id -cne $script:ProductId -or
            $manifest.owner_sid -cne [Security.Principal.WindowsIdentity]::GetCurrent().User.Value -or
            $manifest.profile_path_hash -cne (Get-IzExternalPathHash -Path $profile) -or
            $manifest.supported_tiers -notcontains $Tier) {
            throw (New-IzExternalHarnessError 'TIER_RUNNER_MANIFEST_INVALID')
        }
    }
    $runnerPath = Assert-IzExternalLocalFile -Path ([string]$manifest.runner_path) -Reason 'TIER_RUNNER_BINARY_INVALID'
    if ([IO.Path]::GetExtension($runnerPath) -notin @('.ps1','.exe') -or
        $manifest.runner_sha256 -cnotmatch '^[a-f0-9]{64}$' -or
        (Get-FileHash -LiteralPath $runnerPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $manifest.runner_sha256) {
        throw (New-IzExternalHarnessError 'TIER_RUNNER_BINARY_INVALID')
    }
    return [pscustomobject][ordered]@{
        manifest_path = [IO.Path]::GetFullPath($manifestPath)
        runner_path = $runnerPath
        runner_sha256 = [string]$manifest.runner_sha256
        tier = $Tier
    }
}

function Test-IzExternalTierResult {
    param(
        [Parameter(Mandatory)][object]$Result,
        [Parameter(Mandatory)][object]$Definition,
        [Parameter(Mandatory)][string]$Tier,
        [Parameter(Mandatory)][string]$SourceRevision,
        [Parameter(Mandatory)][string]$CandidateSha256,
        [Parameter(Mandatory)][string]$EvidenceRoot,
        [Parameter(Mandatory)][int]$ExitCode
    )
    Assert-IzExternalExactKeys $Result @(
        'schema','case_id','tier','status','reason','source_revision','candidate_zip_sha256','scenario',
        'execution','observations','artifacts','safety','cleanup','completed_utc'
    ) 'TIER_RESULT_INVALID'
    if ($Result.schema -cne 'iz-cna-maintenance-tier-case-result-v1' -or $Result.case_id -cne $Definition.id -or
        $Result.tier -cne $Tier -or $Result.status -notin @('passed','failed','blocked') -or
        $Result.reason -cnotmatch '^[A-Z][A-Z0-9_]{0,63}$' -or $Result.source_revision -cne $SourceRevision -or
        $Result.candidate_zip_sha256 -cne $CandidateSha256 -or $Result.scenario -cne $Definition.scenario -or
        $Result.completed_utc -cnotmatch '^20[0-9]{2}-') {
        throw (New-IzExternalHarnessError 'TIER_RESULT_INVALID')
    }
    if (($Result.status -ceq 'passed' -and $ExitCode -ne 0) -or
        ($Result.status -ceq 'blocked' -and $ExitCode -ne 2) -or
        ($Result.status -ceq 'failed' -and $ExitCode -eq 0)) {
        throw (New-IzExternalHarnessError 'TIER_RESULT_EXIT_MISMATCH')
    }
    Assert-IzExternalExactKeys $Result.execution $script:ExecutionKeys 'TIER_RESULT_EXECUTION_INVALID'
    Assert-IzExternalExactKeys $Result.safety $script:SafetyKeys 'TIER_RESULT_SAFETY_INVALID'
    Assert-IzExternalExactKeys $Result.cleanup $script:CleanupKeys 'TIER_RESULT_CLEANUP_INVALID'
    foreach ($name in $script:ExecutionKeys | Where-Object { $_ -ne 'executor' }) {
        if ($Result.execution.$name -isnot [bool]) { throw (New-IzExternalHarnessError 'TIER_RESULT_EXECUTION_INVALID') }
    }
    if ($Result.execution.synthetic_data_only -ne $true -or [string]::IsNullOrWhiteSpace($Result.execution.executor)) {
        throw (New-IzExternalHarnessError 'TIER_RESULT_EXECUTION_INVALID')
    }
    $observations = @($Result.observations)
    $artifacts = @($Result.artifacts)
    if ($observations.Count -eq 0 -or $artifacts.Count -eq 0) { throw (New-IzExternalHarnessError 'TIER_RESULT_EVIDENCE_REQUIRED') }
    $artifactPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($artifact in $artifacts) {
        Assert-IzExternalExactKeys $artifact @('kind','path','length','sha256') 'TIER_RESULT_ARTIFACT_INVALID'
        if ([IO.Path]::IsPathRooted([string]$artifact.path) -or
            @([string]$artifact.path -split '[\\/]' | Where-Object { $_ -in @('', '.', '..') }).Count -gt 0 -or
            $artifact.length -le 0 -or $artifact.sha256 -cnotmatch '^[a-f0-9]{64}$') {
            throw (New-IzExternalHarnessError 'TIER_RESULT_ARTIFACT_INVALID')
        }
        $path = [IO.Path]::GetFullPath((Join-Path $EvidenceRoot ([string]$artifact.path).Replace('/', '\')))
        if (-not $path.StartsWith(([IO.Path]::GetFullPath($EvidenceRoot).TrimEnd('\') + '\'), [StringComparison]::OrdinalIgnoreCase) -or
            -not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item $path).Length -ne [long]$artifact.length -or
            (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne [string]$artifact.sha256) {
            throw (New-IzExternalHarnessError 'TIER_RESULT_ARTIFACT_INVALID')
        }
        $null = $artifactPaths.Add(([string]$artifact.path).Replace('\','/'))
    }
    foreach ($observation in $observations) {
        Assert-IzExternalExactKeys $observation @('variant','status','invocation','observable','artifact') 'TIER_RESULT_OBSERVATION_INVALID'
        $text = [string]$observation.invocation + "`n" + [string]$observation.observable
        if ($observation.status -notin @('passed','failed','blocked') -or [string]::IsNullOrWhiteSpace($observation.variant) -or
            [string]::IsNullOrWhiteSpace($observation.invocation) -or [string]::IsNullOrWhiteSpace($observation.observable) -or
            -not $artifactPaths.Contains(([string]$observation.artifact).Replace('\','/')) -or $text.Length -gt 2000 -or
            $text -match '(?i)(bearer\s+[A-Za-z0-9._-]+|password\s*[:=]|secret\s*[:=]|token\s*[:=]|[A-Za-z]:\\|\\\\)') {
            throw (New-IzExternalHarnessError 'TIER_RESULT_OBSERVATION_INVALID')
        }
    }
    if ($Result.status -ceq 'passed') {
        if (@($observations | Where-Object status -cne passed).Count -ne 0 -or
            -not $Result.execution.actual_installer -or -not $Result.execution.actual_default_profile -or
            -not $Result.safety.owned_root_verified -or -not $Result.safety.current_user_scope -or
            -not $Result.safety.reparse_free -or -not $Result.safety.input_hashes_rechecked -or
            $Result.safety.redaction_scan -cne 'passed' -or $Result.cleanup.status -cne 'passed' -or
            [int]$Result.cleanup.owned_processes_remaining -ne 0 -or [int]$Result.cleanup.owned_listeners_remaining -ne 0) {
            throw (New-IzExternalHarnessError 'TIER_RESULT_PASS_UNDERPROVEN')
        }
        if ($Tier -ceq 'Home' -and -not $Result.execution.actual_home_edition) {
            throw (New-IzExternalHarnessError 'TIER_RESULT_PASS_UNDERPROVEN')
        }
        if ($Tier -ceq 'PowerLoss' -and
            (-not $Result.execution.actual_executable -or -not $Result.execution.actual_home_edition -or -not $Result.execution.actual_power_loss)) {
            throw (New-IzExternalHarnessError 'TIER_RESULT_PASS_UNDERPROVEN')
        }
    }
    return $true
}

function Invoke-IzExternalTierCase {
    param(
        [Parameter(Mandatory)][object]$Definition,
        [Parameter(Mandatory)][ValidateSet('Package','Home','PowerLoss')][string]$Tier,
        [Parameter(Mandatory)][object]$Fixture,
        [Parameter(Mandatory)][string]$PublicCaseRoot,
        [Parameter(Mandatory)][string]$SourceRevision,
        [Parameter(Mandatory)][object]$BaselineDescriptor,
        [Parameter(Mandatory)][object]$OriginalDescriptor,
        [Parameter(Mandatory)][object]$CandidateDescriptor,
        [Parameter(Mandatory)][object]$CandidateReceipt,
        [Parameter(Mandatory)][ValidateSet('msedge','chrome')][string]$BrowserChannel,
        [Parameter(Mandatory)][object]$Runner
    )
    $adapterRoot = Join-Path ([string]$Fixture.private_root) 'external-tier-result'
    $resultPath = Join-Path $adapterRoot 'result.json'
    $logPath = Join-Path ([string]$Fixture.private_root) 'external-tier-runner.txt'
    if (Test-Path -LiteralPath $adapterRoot) { throw (New-IzExternalHarnessError 'TIER_RESULT_ROOT_EXISTS') }
    $arguments = @(
        '-Case', [string]$Definition.id,
        '-Tier', $Tier,
        '-BaselineZip', [string]$BaselineDescriptor.path,
        '-OriginalBeta4Zip', [string]$OriginalDescriptor.path,
        '-CandidateZip', [string]$CandidateDescriptor.path,
        '-CandidateBuildReceipt', [string]$CandidateReceipt.path,
        '-ExpectedSourceRevision', $SourceRevision,
        '-EvidenceRoot', $adapterRoot,
        '-BrowserChannel', $BrowserChannel,
        '-RunnerManifest', [string]$Runner.manifest_path,
        '-ResultPath', $resultPath
    )
    $previousCache = $env:PSModuleAnalysisCachePath
    try {
        $env:PSModuleAnalysisCachePath = Join-Path ([string]$Fixture.private_root) 'external-tier.module-analysis.cache'
        if ([IO.Path]::GetExtension([string]$Runner.runner_path) -ceq '.ps1') {
            $output = @(& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $Runner.runner_path @arguments 2>&1)
        }
        else { $output = @(& $Runner.runner_path @arguments 2>&1) }
        $exitCode = [int]$LASTEXITCODE
        [IO.File]::WriteAllText($logPath, $(if ($output.Count) { $output -join "`r`n" } else { '<no-output>' }), [Text.UTF8Encoding]::new($false))
    }
    catch {
        $exitCode = 1
        [IO.File]::WriteAllText($logPath, 'EXTERNAL_TIER_RUNNER_PROCESS_ERROR', [Text.UTF8Encoding]::new($false))
    }
    finally {
        if ($null -eq $previousCache) { Remove-Item Env:\PSModuleAnalysisCachePath -ErrorAction SilentlyContinue }
        else { $env:PSModuleAnalysisCachePath = $previousCache }
    }
    if (-not (Test-Path -LiteralPath $resultPath -PathType Leaf)) {
        throw (New-IzExternalHarnessError 'TIER_RESULT_MISSING')
    }
    try { $result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json }
    catch { throw (New-IzExternalHarnessError 'TIER_RESULT_INVALID') }
    [void](Test-IzExternalTierResult -Result $result -Definition $Definition -Tier $Tier -SourceRevision $SourceRevision `
        -CandidateSha256 ([string]$CandidateDescriptor.sha256) -EvidenceRoot $adapterRoot -ExitCode $exitCode)
    $summaryPath = Join-Path $PublicCaseRoot 'external-tier-verification.json'
    $summary = [ordered]@{
        schema = 'iz-cna-maintenance-external-tier-verification-v1'
        case_id = [string]$Definition.id
        tier = $Tier
        status = [string]$result.status
        reason = [string]$result.reason
        source_revision = $SourceRevision
        candidate_zip_sha256 = [string]$CandidateDescriptor.sha256
        runner_sha256 = [string]$Runner.runner_sha256
        process_exit_code = $exitCode
        execution = $result.execution
        observations = @($result.observations | ForEach-Object {
            [ordered]@{ variant = $_.variant; status = $_.status; invocation = $_.invocation; observable = $_.observable }
        })
        artifact_descriptors = @($result.artifacts | ForEach-Object {
            [ordered]@{ kind = $_.kind; length = [long]$_.length; sha256 = $_.sha256 }
        })
        safety = $result.safety
        cleanup = $result.cleanup
        completed_utc = [string]$result.completed_utc
    }
    $json = $summary | ConvertTo-Json -Depth 12
    if ($json -match '(?i)(bearer\s+[A-Za-z0-9._-]+|"(password|secret|token|credential)"\s*:)') {
        throw (New-IzExternalHarnessError 'TIER_RESULT_REDACTION_FAILED')
    }
    [IO.File]::WriteAllText($summaryPath, $json, [Text.UTF8Encoding]::new($false))
    return [pscustomobject][ordered]@{
        status = [string]$result.status
        reason = [string]$result.reason
        execution = $result.execution
        safety = $result.safety
        cleanup = $result.cleanup
        invocation = "external tier runner -Case $($Definition.id) -Tier $Tier -CandidateZip <exact-candidate>"
        observable = "adapter_exit=$exitCode;typed_result=true;observations=$(@($result.observations).Count);artifacts=$(@($result.artifacts).Count)"
        artifact_path = $summaryPath
    }
}

Export-ModuleMember -Function @('Read-IzExternalTierRunner','Test-IzExternalTierResult','Invoke-IzExternalTierCase')
