[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Case,
    [Parameter(Mandatory)][ValidateSet('Component', 'Package', 'Home', 'PowerLoss')][string]$Tier,
    [Parameter(Mandatory)][string]$BaselineZip,
    [Parameter(Mandatory)][string]$OriginalBeta4Zip,
    [string]$CandidateZip = $env:IZ_CNA_QA_CANDIDATE_ZIP,
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{40}$')][string]$ExpectedSourceRevision,
    [string]$CandidateBuildReceipt = '',
    [Parameter(Mandatory)][string]$EvidenceRoot,
    [Parameter(Mandatory)][ValidateSet('msedge', 'chrome')][string]$BrowserChannel,
    [string]$VmControlManifest = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$previousModuleCachePath = $env:PSModuleAnalysisCachePath
$moduleCachePath = $null
$receiptPath = $null
$exitCode = 1
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$startedUtc = [DateTime]::UtcNow.ToString('o')
try {
    $qaParent = [IO.Path]::GetFullPath((Join-Path ([Environment]::GetFolderPath('UserProfile')) 'IZ-CNA-QA'))
    if (-not (Test-Path -LiteralPath $qaParent -PathType Container) -or
        ((Get-Item -LiteralPath $qaParent -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'QA_PARENT_INVALID'
    }
    $moduleCachePath = Join-Path $qaParent ('.iz-cna-module-analysis-' + $PID + '-' + [Guid]::NewGuid().ToString('N') + '.cache')
    $env:PSModuleAnalysisCachePath = $moduleCachePath
    $runnerModule = Join-Path $PSScriptRoot 'tests\maintenance-harness-runner.psm1'
    Import-Module -Name $runnerModule -Force -ErrorAction Stop

    $result = Invoke-IzMaintenanceHarness `
        -RepositoryRoot $repositoryRoot `
        -Case $Case `
        -Tier $Tier `
        -BaselineZip $BaselineZip `
        -OriginalBeta4Zip $OriginalBeta4Zip `
        -CandidateZip $CandidateZip `
        -ExpectedSourceRevision $ExpectedSourceRevision `
        -CandidateBuildReceipt $CandidateBuildReceipt `
        -EvidenceRoot $EvidenceRoot `
        -BrowserChannel $BrowserChannel `
        -VmControlManifest $VmControlManifest

    $receiptPath = [IO.Path]::GetFullPath([string]$result.receipt_path)
    $exitCode = [int]$result.exit_code
}
catch {
    $reason = if ($_.Exception.Data.Contains('iz_reason') -and
        [string]$_.Exception.Data['iz_reason'] -cmatch '^[A-Z][A-Z0-9_]{0,63}$') {
        [string]$_.Exception.Data['iz_reason']
    }
    elseif ($_.Exception.Message -cmatch '^[A-Z][A-Z0-9_]{0,63}$') { [string]$_.Exception.Message }
    else { 'HARNESS_ENTRYPOINT_FAILED' }
    $failureRoot = Join-Path $repositoryRoot ('.omo\evidence\windows-cmd-maintenance\cmd-failure-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
    $null = New-Item -ItemType Directory -Path $failureRoot
    $receiptPath = Join-Path $failureRoot 'maintenance-run-receipt.json'
    $safeCase = if ($Case -cmatch '^(All|[A-Za-z0-9_-]{1,32})$') { $Case } else { '<invalid>' }
    $terminal = [ordered]@{
        schema = 'iz-cna-maintenance-terminal-failure-v1'
        requested_case = $safeCase
        requested_tier = $Tier
        status = 'failed'
        reason = $reason
        source_revision = $ExpectedSourceRevision
        product_write_attempted = $false
        started_utc = $startedUtc
        completed_utc = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText($receiptPath, ($terminal | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    $exitCode = 1
}
finally {
    if ($null -eq $previousModuleCachePath) { Remove-Item Env:\PSModuleAnalysisCachePath -ErrorAction SilentlyContinue }
    else { $env:PSModuleAnalysisCachePath = $previousModuleCachePath }
    if ($moduleCachePath -and (Test-Path -LiteralPath $moduleCachePath -PathType Leaf)) {
        Remove-Item -LiteralPath $moduleCachePath -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "MAINTENANCE_RECEIPT_PATH=$receiptPath"
if ($env:GITHUB_OUTPUT) {
    try {
        [IO.File]::AppendAllText(
            [IO.Path]::GetFullPath($env:GITHUB_OUTPUT),
            "maintenance_receipt_path=$receiptPath`n",
            [Text.UTF8Encoding]::new($false)
        )
    }
    catch { Write-Warning 'GITHUB_OUTPUT_WRITE_FAILED' }
}
exit $exitCode
