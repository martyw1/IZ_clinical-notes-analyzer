[CmdletBinding()]
param(
    [string]$EvidenceRoot = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$qaParent = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'IZ-CNA-QA'
[IO.Directory]::CreateDirectory($qaParent) | Out-Null
if (-not $EvidenceRoot) {
    $EvidenceRoot = Join-Path $qaParent ('process-exit-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
}
$evidence = [IO.Path]::GetFullPath($EvidenceRoot).TrimEnd('\')
$qa = [IO.Path]::GetFullPath($qaParent).TrimEnd('\')
if (-not $evidence.StartsWith($qa + '\process-exit-', [StringComparison]::OrdinalIgnoreCase) -or
    (Test-Path -LiteralPath $evidence)) {
    throw 'PROCESS_EXIT_EVIDENCE_ROOT_INVALID'
}
[IO.Directory]::CreateDirectory($evidence) | Out-Null
$env:PSModuleAnalysisCachePath = Join-Path $evidence 'module-analysis.cache'

$privateRoot = Join-Path $evidence 'private'
$componentRoot = Join-Path $evidence 'component'
$packageRoot = Join-Path $evidence 'package'
$installerRoot = Join-Path $packageRoot 'installer'
foreach ($path in @($privateRoot, $componentRoot, $installerRoot)) {
    [IO.Directory]::CreateDirectory($path) | Out-Null
}

$dispatcherPath = Join-Path $installerRoot 'maintenance-windows.ps1'
$dispatcher = @'
[CmdletBinding()]
param([switch]$NoRun)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-IzMaintenanceContext {
    param([string]$PackageRoot,[string]$ComponentTestRoot)
    return [pscustomobject]@{ maintenance_root = Join-Path $ComponentTestRoot 'maintenance' }
}

function Invoke-IzMaintenanceAction {
    param(
        [string]$Action,[string]$PackageRoot,[switch]$NoPause,[switch]$NonInteractive,
        [string]$ResultPath,[object]$Context
    )
    $started = [DateTime]::UtcNow.ToString('o')
    Start-Sleep -Milliseconds 1200
    $result = [pscustomobject][ordered]@{
        schema = 'iz-cna-maintenance-result-v1'
        product_id = 'r3.iz-clinical-notes-analyzer.desktop'
        action = [string]$Action
        status = 'ROLLED_BACK'
        version = $null
        build = $null
        installer_revision = $null
        transaction_id = $null
        stage = 'FINISHED'
        code = 30
        reason = 'SYNTHETIC_TYPED_ROLLBACK'
        evidence = @()
        started_utc = $started
        completed_utc = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText($ResultPath, ($result | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    $process = Get-Process -Id $PID
    $observation = [ordered]@{
        process_id = [int]$PID
        process_started_utc = $process.StartTime.ToUniversalTime().ToString('o')
        in_memory_result_code = [int]$result.code
        in_memory_result_status = [string]$result.status
    }
    [IO.File]::WriteAllText((Join-Path (Split-Path $ResultPath -Parent) 'process-observation.json'), ($observation | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    return $result
}
'@
[IO.File]::WriteAllText($dispatcherPath, $dispatcher, [Text.UTF8Encoding]::new($true))

$modulePath = Join-Path $PSScriptRoot 'maintenance-harness-lifecycle.psm1'
$module = Import-Module $modulePath -Force -PassThru
$receiptPath = Join-Path $evidence 'process-exit-regression.json'
try {
    $fixture = [pscustomobject]@{ private_root = $privateRoot; component_root = $componentRoot }
    $context = [pscustomobject]@{}
    $binding = [pscustomobject]@{ package_root = $packageRoot }
    $actionResult = & $module {
        param($FixtureValue,$ContextValue,$BindingValue)
        Invoke-IzLifecycleAction -Action AutoInstall -Fixture $FixtureValue -Context $ContextValue -Binding $BindingValue -Environment ([ordered]@{})
    } $fixture $context $binding
    $processObservationPath = Join-Path $privateRoot 'process-observation.json'
    if (-not (Test-Path -LiteralPath $processObservationPath -PathType Leaf)) {
        throw 'PROCESS_OBSERVATION_MISSING'
    }
    $processObservation = Get-Content -LiteralPath $processObservationPath -Raw | ConvertFrom-Json
    $childRemaining = $null -ne (Get-Process -Id ([int]$processObservation.process_id) -ErrorAction SilentlyContinue)
    if ([int]$actionResult.exit_code -ne 30 -or [int]$actionResult.result.code -ne 30 -or
        [int]$processObservation.in_memory_result_code -ne 30 -or $childRemaining) {
        throw 'PROCESS_EXIT_REGRESSION_FAILED'
    }
    $resultItem = Get-Item -LiteralPath ([string]$actionResult.result_path)
    $receipt = [ordered]@{
        schema = 'iz-cna-lifecycle-process-exit-regression-v1'
        status = 'passed'
        scenario = 'Windows PowerShell 5.1 redirected and polled component action preserves typed native exit 30'
        invocation = 'Invoke-IzLifecycleAction -> maintenance-component-action.ps1 -> synthetic typed rollback'
        powershell_version = $PSVersionTable.PSVersion.ToString()
        child = [ordered]@{
            process_id = [int]$processObservation.process_id
            process_started_utc = [string]$processObservation.process_started_utc
            in_memory_result_code = [int]$processObservation.in_memory_result_code
            in_memory_result_status = [string]$processObservation.in_memory_result_status
            remaining_after_wait = $childRemaining
        }
        observed = [ordered]@{
            raw_exit_was_available = $true
            process_exit_code = [int]$actionResult.exit_code
            persisted_result_code = [int]$actionResult.result.code
            persisted_result_status = [string]$actionResult.result.status
            result_path = [string]$actionResult.result_path
            result_length = [long]$resultItem.Length
            result_sha256 = (Get-FileHash -LiteralPath $resultItem.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            stderr_length = [long](Get-Item -LiteralPath ([string]$actionResult.stderr_path)).Length
        }
        source = [ordered]@{
            lifecycle_module_path = $modulePath
            lifecycle_module_sha256 = (Get-FileHash -LiteralPath $modulePath -Algorithm SHA256).Hash.ToLowerInvariant()
            component_helper_path = (Join-Path $PSScriptRoot 'maintenance-component-action.ps1')
            component_helper_sha256 = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'maintenance-component-action.ps1') -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        completed_utc = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText($receiptPath, ($receipt | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    Write-Host '[pass] lifecycle redirected process exit code=30'
    exit 0
}
catch {
    $reason = if ($_.Exception.Data['iz_reason']) { [string]$_.Exception.Data['iz_reason'] } else { [string]$_.Exception.Message }
    $receipt = [ordered]@{
        schema = 'iz-cna-lifecycle-process-exit-regression-v1'
        status = 'failed'
        reason = $reason
        powershell_version = $PSVersionTable.PSVersion.ToString()
        completed_utc = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText($receiptPath, ($receipt | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
    Write-Error "lifecycle redirected process regression failed: $reason"
    exit 1
}
finally {
    if ($module) { Remove-Module $module -Force -ErrorAction SilentlyContinue }
}
