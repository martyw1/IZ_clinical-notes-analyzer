[CmdletBinding()]
param(
    [ValidateSet('transaction-transitions', 'transaction-recovery', 'transaction-long-path', 'install-routing', 'install-negative', 'All')]
    [string]$Case = 'All',
    [string]$EvidenceRoot = ''
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $EvidenceRoot) {
    $EvidenceRoot = Join-Path $repoRoot '.omo\evidence\windows-cmd-maintenance\install\component'
}
$runRoot = Join-Path $EvidenceRoot ('transaction-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
$env:PSModuleAnalysisCachePath = Join-Path $runRoot 'PSModuleAnalysisCache'
$results = New-Object System.Collections.Generic.List[object]
$componentRoots = New-Object System.Collections.Generic.List[string]
$dispatcherPath = Join-Path $repoRoot 'scripts\installer\maintenance-windows.ps1'
$script:DispatcherLoaded = $false
if (Test-Path -LiteralPath $dispatcherPath -PathType Leaf) {
    . $dispatcherPath -NoRun
    $script:DispatcherLoaded = $null -ne (Get-Command Invoke-IzMaintenanceAction -ErrorAction SilentlyContinue)
}

function Add-Result {
    param([string]$Name, [string]$Status, [hashtable]$Observable)
    $results.Add([ordered]@{
        name = $Name
        tier = 'Component'
        status = $Status
        binary_observables = $Observable
    }) | Out-Null
}

function New-EmptyComponentRoot {
    param([string]$Parent)
    $path = Join-Path ([IO.Path]::GetTempPath()) ('iz-cna-component-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
    New-Item -ItemType Directory -Path $path | Out-Null
    $componentRoots.Add($path) | Out-Null
    return $path
}

function Get-FileDigest {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Import-MaintenanceSurface {
    $commonPath = Join-Path $repoRoot 'scripts\installer\maintenance-common.psm1'
    if (-not (Test-Path -LiteralPath $commonPath) -or -not $script:DispatcherLoaded) {
        return $false
    }
    Import-Module $commonPath -Force
    return $script:DispatcherLoaded
}

function Invoke-InvalidPackageCase {
    $packageRoot = Join-Path $runRoot 'malformed package'
    New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $packageRoot 'release-manifest.json') -Value '{}' -Encoding UTF8
    $componentRoot = New-EmptyComponentRoot -Parent $runRoot
    $loaded = Import-MaintenanceSurface
    if (-not $loaded) {
        Add-Result -Name 'invalid_manifest_returns_code20_without_live_mutation' -Status 'failed' -Observable @{
            surface_loaded = $false
            expected_code = 20
        }
        return
    }
    $transactionId = [Guid]::NewGuid()
    $context = Get-IzMaintenanceContext -PackageRoot $packageRoot -TransactionId $transactionId -ComponentTestRoot $componentRoot
    New-Item -ItemType Directory -Path $context.install_root, $context.data_root -Force | Out-Null
    $programSentinel = Join-Path $context.install_root 'synthetic-program.txt'
    $dataSentinel = Join-Path $context.data_root 'synthetic-data.txt'
    Set-Content -LiteralPath $programSentinel -Value 'program-before' -Encoding UTF8
    Set-Content -LiteralPath $dataSentinel -Value 'data-before' -Encoding UTF8
    $programBefore = Get-FileDigest $programSentinel
    $dataBefore = Get-FileDigest $dataSentinel
    $result = Invoke-IzMaintenanceAction -Action AutoInstall -Context $context -PackageRoot $packageRoot -NonInteractive -NoPause
    $passed = (
        [int]$result.code -eq 20 -and
        $result.status -ceq 'PREFLIGHT_FAILED' -and
        (Get-FileDigest $programSentinel) -ceq $programBefore -and
        (Get-FileDigest $dataSentinel) -ceq $dataBefore
    )
    Add-Result -Name 'invalid_manifest_returns_code20_without_live_mutation' -Status $(if ($passed) { 'passed' } else { 'failed' }) -Observable @{
        surface_loaded = $true
        expected_code = 20
        actual_code = [int]$result.code
        program_unchanged = ((Get-FileDigest $programSentinel) -ceq $programBefore)
        data_unchanged = ((Get-FileDigest $dataSentinel) -ceq $dataBefore)
    }
}

function Invoke-StatusCase {
    $componentRoot = New-EmptyComponentRoot -Parent $runRoot
    $loaded = Import-MaintenanceSurface
    if (-not $loaded) {
        Add-Result -Name 'status_is_typed_and_does_not_initialize_profile' -Status 'failed' -Observable @{ surface_loaded = $false }
        return
    }
    $context = Get-IzMaintenanceContext -ComponentTestRoot $componentRoot
    $result = Invoke-IzMaintenanceAction -Action Status -Context $context -NonInteractive -NoPause
    $passed = (
        [int]$result.code -eq 0 -and
        $result.schema -ceq 'iz-cna-maintenance-result-v1' -and
        -not (Test-Path -LiteralPath $context.install_root) -and
        -not (Test-Path -LiteralPath $context.data_root)
    )
    Add-Result -Name 'status_is_typed_and_does_not_initialize_profile' -Status $(if ($passed) { 'passed' } else { 'failed' }) -Observable @{
        surface_loaded = $true
        actual_code = [int]$result.code
        install_root_absent = (-not (Test-Path -LiteralPath $context.install_root))
        data_root_absent = (-not (Test-Path -LiteralPath $context.data_root))
    }
}

function New-SyntheticManifest {
    param([string]$PackageRoot)
    $files = @()
    foreach ($file in @(Get-ChildItem -LiteralPath $PackageRoot -File -Recurse)) {
        $relative = $file.FullName.Substring($PackageRoot.Length + 1).Replace('\', '/')
        $files += [pscustomobject][ordered]@{ path = $relative; length = [long]$file.Length; sha256 = (Get-FileHash $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    }
    [Array]::Sort($files, [Comparison[object]]{ param($left,$right) [StringComparer]::Ordinal.Compare([string]$left.path,[string]$right.path) })
    $canonical = @($files | ForEach-Object { "$($_.path)`t$($_.length)`t$($_.sha256)`n" }) -join ''
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $identity = ([BitConverter]::ToString($sha.ComputeHash([Text.UTF8Encoding]::new($false).GetBytes($canonical)))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
    $manifest = [pscustomobject][ordered]@{
        schema = 'iz-cna-release-manifest-v1'; product_id = 'r3.iz-clinical-notes-analyzer.desktop'
        version = '2.0.0-beta.4'; build = '2026.09.10.2'; installer_revision = 1; release_channel = 'beta-local-desktop-v2'
        compatibility = [pscustomobject][ordered]@{
            source_version_minimum = '2.0.0-beta.3'; source_version_maximum = '2.0.0-beta.4'
            source_build_minimum = '2026.09.03.1'; source_build_maximum = '2026.09.10.2'
            source_schema_minimum = 12; source_schema_maximum = 12; target_schema = 12
        }
        payload_identity = $identity; files = $files
    }
    [IO.File]::WriteAllText((Join-Path $PackageRoot 'release-manifest.json'), ($manifest | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    return $manifest
}

function New-TransactionFixture {
    param([switch]$IncludeLongGuidePath)
    $modulePath = Join-Path $repoRoot 'scripts\installer\maintenance-transaction.psm1'
    Import-Module $modulePath -Force
    Import-Module (Join-Path $repoRoot 'scripts\installer\maintenance-common.psm1') -Force
    $component = New-EmptyComponentRoot -Parent $runRoot
    $package = Join-Path $component 'package with spaces & punctuation!'
    New-Item -ItemType Directory -Path `
        (Join-Path $package 'app\runtime'), `
        (Join-Path $package 'app\frontend\dist\assets'), `
        (Join-Path $package 'app\config\rules'), `
        (Join-Path $package 'app\config\checklists') -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $package 'app\runtime\IZClinicalNotesAnalyzer.exe'), 'synthetic-new-runtime', [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $package 'app\frontend\dist\index.html'), '<html>new</html>', [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $package 'app\frontend\dist\assets\application.js'), 'synthetic-asset', [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $package 'app\config\rules\synthetic.yml'), 'rules: []', [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $package 'app\config\checklists\treatment-plan-v1.json'), '{"schema":"synthetic"}', [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $package 'app\VERSION'), '2.0.0-beta.4', [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $package 'app\VERSION.json'), '{"version":"2.0.0-beta.4","build":"2026.09.10.2"}', [Text.UTF8Encoding]::new($false))
    if ($IncludeLongGuidePath) {
        $guide = Join-Path $package 'app\docs\guides\Version 2.0 Beta  2.0.0-beta.2  beta-local-desktop-v2\long-path-regression'
        [IO.Directory]::CreateDirectory($guide) | Out-Null
        [IO.File]::WriteAllText((Join-Path $guide '02. Start Up Screen.png'), 'synthetic-long-path-guide', [Text.UTF8Encoding]::new($false))
    }
    foreach($name in @(
        'Backup-IZ-Clinical-Notes-Analyzer.cmd','Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd',
        'Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd','Install-IZ-Clinical-Notes-Analyzer.cmd',
        'Launch-IZ-Clinical-Notes-Analyzer.cmd','Restore-IZ-Clinical-Notes-Analyzer.cmd',
        'Stop-IZ-Clinical-Notes-Analyzer.cmd','Uninstall-IZ-Clinical-Notes-Analyzer.cmd'
    )){[IO.File]::WriteAllText((Join-Path $package $name),'@exit /b 0',[Text.UTF8Encoding]::new($false))}
    [IO.Directory]::CreateDirectory((Join-Path $package 'installer'))|Out-Null
    foreach($name in @(
        'maintenance-windows.ps1','install-windows-release.ps1','uninstall-windows-release.ps1','maintenance-common.psm1',
        'maintenance-contracts.psm1','maintenance-paths.psm1','maintenance-version.psm1','maintenance-lock.psm1',
        'maintenance-journal.psm1','backup-verification.psm1','maintenance-runtime.psm1','maintenance-transaction.psm1',
        'Remove-IZ-Clinical-Notes-Analyzer.bootstrap.ps1','maintenance-bundle-manifest.json','legacy-program-inventory.json'
    )){[IO.File]::WriteAllText((Join-Path $package ('installer\'+$name)),('synthetic-'+$name),[Text.UTF8Encoding]::new($false))}
    $manifest = New-SyntheticManifest -PackageRoot $package
    $transactionId = [Guid]::NewGuid()
    $context = Get-IzMaintenanceContext -PackageRoot $package -TransactionId $transactionId -ComponentTestRoot $component
    Initialize-IzMaintenanceStorage -Context $context | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $context.install_root 'runtime'), (Join-Path $context.install_root 'frontend\dist'), $context.data_root -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $context.install_root 'runtime\IZClinicalNotesAnalyzer.exe'), 'synthetic-old-runtime', [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $context.install_root 'frontend\dist\index.html'), '<html>old</html>', [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $context.install_root 'VERSION.json'), '{"version":"2.0.0-beta.3","build":"2026.09.03.1"}', [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $context.install_root 'release-manifest.json'), '{"legacy_release":"2.0.0-beta.3"}', [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $context.data_root '.env'), 'LOCAL_SQLITE_DB_PATH=synthetic.sqlite3', [Text.UTF8Encoding]::new($false))
    $database = Join-Path $context.data_root 'synthetic.sqlite3'
    [IO.File]::WriteAllText($database, 'synthetic-data-before', [Text.UTF8Encoding]::new($false))
    $dataIdentity = New-IzDataIdentity -Context $context -SelectedDatabasePath $database
    $source = New-IzReleaseIdentity -Version '2.0.0-beta.3' -Build '2026.09.03.1' -InstallerRevision 0 -PayloadIdentity ('3' * 64)
    $owned = @(Get-ChildItem $context.install_root -File -Recurse | ForEach-Object {
        [pscustomobject][ordered]@{ path = $_.FullName.Substring($context.install_root.Length + 1).Replace('\','/'); length = [long]$_.Length; sha256 = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    })
    $receipt = New-IzInstallReceipt -Context $context -DataIdentity $dataIdentity.data_identity -ReleaseIdentity $source -OwnedFiles $owned -OwnedShortcuts @() -LastCommittedTransaction ([Guid]::NewGuid())
    if (Test-Path -LiteralPath $context.install_receipt_path) { throw 'TEST_RECEIPT_PREEXISTED' }
    Write-IzInstallReceipt -Context $context -Receipt $receipt -ExpectedPreviousSha256 $null | Out-Null
    $priorHash = (Get-FileHash $context.install_receipt_path -Algorithm SHA256).Hash.ToLowerInvariant()
    $target = New-IzReleaseIdentity -Version $manifest.version -Build $manifest.build -InstallerRevision $manifest.installer_revision -PayloadIdentity $manifest.payload_identity
    $journal = New-IzMaintenanceJournal -Context $context -Action AutoInstall -SourceRelease $source -TargetRelease $target -DataIdentity $dataIdentity.data_identity -PayloadIdentity $manifest.payload_identity -PriorReceiptSha256 $priorHash
    Write-IzMaintenanceJournal -Context $context -Journal $journal -ExpectedSequence -1 | Out-Null
    return [pscustomobject]@{ context=$context; manifest=$manifest; source=$source; target=$target; receipt=$receipt; journal=$journal; database=$database }
}

function Invoke-LongStagePathCase {
    $fixture = New-TransactionFixture -IncludeLongGuidePath
    $relative = 'docs\guides\Version 2.0 Beta  2.0.0-beta.2  beta-local-desktop-v2\long-path-regression\02. Start Up Screen.png'
    $target = Join-Path $fixture.context.stage_root $relative
    $stage = $null
    $errorReason = ''
    try {
        try { $stage = Copy-IzStagedProgram -Context $fixture.context -Manifest $fixture.manifest }
        catch { $errorReason = [string]$_.Exception.Message }
        $extendedTarget = '\\?\' + $target
        $targetPresent = Test-Path -LiteralPath $extendedTarget -PathType Leaf
        $targetHashMatches = $targetPresent -and
            (Get-FileHash -LiteralPath $extendedTarget -Algorithm SHA256).Hash.ToLowerInvariant() -ceq
            (Get-FileHash -LiteralPath (Join-Path $fixture.context.package_root ('app\' + $relative)) -Algorithm SHA256).Hash.ToLowerInvariant()
        $outside = Join-Path $fixture.context.local_app_data_root 'transaction-long-path-outside'
        [IO.Directory]::CreateDirectory($outside) | Out-Null
        $outsideSentinel = Join-Path $outside 'sentinel.txt'
        [IO.File]::WriteAllText($outsideSentinel, 'outside-safe', [Text.UTF8Encoding]::new($false))
        $junction = Join-Path $fixture.context.stage_root 'long-path-reparse-probe'
        New-Item -ItemType Junction -Path $junction -Target $outside | Out-Null
        $reparseReason = ''
        try {
            $transactionModule = Get-Module maintenance-transaction | Select-Object -Last 1
            & $transactionModule { param($root,$files) Test-IzProgramFiles $root $files -AllowMarker } $fixture.context.stage_root $stage.files | Out-Null
        } catch {
            $reparseReason = if ($_.Exception.Data.Contains('iz_reason')) { [string]$_.Exception.Data['iz_reason'] } else { [string]$_.Exception.Message }
        } finally {
            if ([IO.Directory]::Exists($junction)) { [IO.Directory]::Delete($junction, $false) }
        }
        $outsidePreserved = (Get-Content -LiteralPath $outsideSentinel -Raw) -ceq 'outside-safe'
        $passed = $target.Length -gt 259 -and $null -ne $stage -and $targetPresent -and $targetHashMatches -and
            $reparseReason -ceq 'PATH_REPARSE_POINT' -and $outsidePreserved
        Add-Result -Name 'staged_payload_copies_and_verifies_manifest_file_beyond_max_path' -Status $(if ($passed) { 'passed' } else { 'failed' }) -Observable @{
            target_length = $target.Length
            stage_binding_returned = ($null -ne $stage)
            target_present = $targetPresent
            target_hash_matches = $targetHashMatches
            reparse_reason = $reparseReason
            outside_sentinel_preserved = $outsidePreserved
            error_reason = $errorReason
        }
    } finally {
        if ([IO.Directory]::Exists('\\?\' + $fixture.context.stage_root)) {
            [IO.Directory]::Delete(('\\?\' + $fixture.context.stage_root), $true)
        }
    }
}

function Invoke-TransactionTransitionCase {
    $modulePath = Join-Path $repoRoot 'scripts\installer\maintenance-transaction.psm1'
    if (-not (Test-Path -LiteralPath $modulePath)) {
        Add-Result -Name 'transaction_swap_records_intents_and_moves_paired_trees' -Status 'failed' -Observable @{ module_loaded = $false }
        return
    }
    $fixture = New-TransactionFixture
    $stage = Copy-IzStagedProgram -Context $fixture.context -Manifest $fixture.manifest
    $verified = New-IzMaintenanceTransition -Journal $fixture.journal -NextState PAYLOAD_VERIFIED -CompletedSteps @('PAYLOAD_STAGED','PAYLOAD_VERIFIED') -Patch ([pscustomobject]@{ program=$stage.journal_patch })
    Write-IzMaintenanceJournal -Context $fixture.context -Journal $verified -ExpectedSequence $fixture.journal.sequence | Out-Null
    $quiesced = New-IzMaintenanceTransition $verified QUIESCED @('RUNTIME_QUIESCED')
    Write-IzMaintenanceJournal $fixture.context $quiesced $verified.sequence | Out-Null
    $protected = New-IzMaintenanceTransition $quiesced SNAPSHOT_VERIFIED
    Write-IzMaintenanceJournal $fixture.context $protected $quiesced.sequence | Out-Null
    $swapped = Invoke-IzProgramSwap -Context $fixture.context -Journal $protected -StageBinding $stage -PriorReceipt $fixture.receipt
    $oldMoved = Test-Path (Join-Path $fixture.context.previous_root 'runtime\IZClinicalNotesAnalyzer.exe')
    $newActive = (Get-Content (Join-Path $fixture.context.install_root 'runtime\IZClinicalNotesAnalyzer.exe') -Raw) -eq 'synthetic-new-runtime'
    $passed = $swapped.state -ceq 'NEW_MOVED' -and 'OLD_MOVE_INTENT_RECORDED' -in $swapped.completed_steps -and
        'OLD_PROGRAM_MOVED' -in $swapped.completed_steps -and 'NEW_MOVE_INTENT_RECORDED' -in $swapped.completed_steps -and
        'NEW_PROGRAM_MOVED' -in $swapped.completed_steps -and $oldMoved -and $newActive
    Add-Result -Name 'transaction_swap_records_intents_and_moves_paired_trees' -Status $(if ($passed) { 'passed' } else { 'failed' }) -Observable @{
        module_loaded = $true; final_state = [string]$swapped.state; old_tree_moved = $oldMoved; new_tree_active = $newActive
        sequence = [long]$swapped.sequence
    }
    return [pscustomobject]@{ fixture=$fixture; journal=$swapped }
}

function Invoke-TransactionRecoveryCase {
    $swap = Invoke-TransactionTransitionCase
    if (-not $swap) { return }
    $dataBefore = Get-FileDigest $swap.fixture.database
    $recovery = Invoke-IzInstallRecovery -Context $swap.fixture.context -Journal $swap.journal
    $oldRestored = (Get-Content (Join-Path $swap.fixture.context.install_root 'runtime\IZClinicalNotesAnalyzer.exe') -Raw) -eq 'synthetic-old-runtime'
    $dataSame = (Get-FileDigest $swap.fixture.database) -ceq $dataBefore
    $pending = Get-IzPendingMaintenanceStatus -Context $swap.fixture.context
    $restoredAuthority = $pending.status -ceq 'PENDING' -and $pending.journal.state -ceq 'ROLLED_BACK' -and
        $pending.authority.state -ceq 'ROLLED_BACK' -and $pending.authority.launch_policy -ceq 'source'
    . (Join-Path $repoRoot 'scripts\installer\install-windows-release.ps1') -NoRun
    $legacyStart = (Get-Command Start-IzLegacyRuntime -ErrorAction Stop).ScriptBlock
    $ownedStart = (Get-Command Start-IzOwnedRuntime -ErrorAction Stop).ScriptBlock
    $script:RestoredRuntimeRoute = ''
    $restoredRuntime = $null
    $restoredRuntimeRouteError = ''
    try {
        Set-Item Function:\Start-IzLegacyRuntime -Value {
            param($Context,$ExpectedRelease,$TimeoutSeconds)
            $script:RestoredRuntimeRoute = 'legacy'
            return [pscustomobject]@{status='started';version=[string]$ExpectedRelease.version}
        }
        Set-Item Function:\Start-IzOwnedRuntime -Value { throw 'MODERN_RUNTIME_SELECTED_FOR_LEGACY_SOURCE' }
        try { $restoredRuntime = Confirm-IzRestoredRuntime -Context $swap.fixture.context -Journal $recovery.journal }
        catch { $restoredRuntimeRouteError = [string]$_.Exception.Message }
    }
    finally {
        Set-Item Function:\Start-IzLegacyRuntime -Value $legacyStart
        Set-Item Function:\Start-IzOwnedRuntime -Value $ownedStart
    }
    $legacyManifestRouted = $script:RestoredRuntimeRoute -ceq 'legacy' -and $restoredRuntime.status -ceq 'started'
    $passed = $recovery.status -ceq 'rolled_back' -and $recovery.journal.state -ceq 'ROLLED_BACK' -and $oldRestored -and $dataSame -and $restoredAuthority -and $legacyManifestRouted
    Add-Result -Name 'precommit_recovery_restores_old_program_and_receipt' -Status $(if ($passed) { 'passed' } else { 'failed' }) -Observable @{
        recovery_status = [string]$recovery.status; final_state = [string]$recovery.journal.state
        old_program_restored = $oldRestored; unchanged_data_preserved = $dataSame; restored_authority_valid = $restoredAuthority
        trusted_legacy_manifest_routed_to_legacy_runtime = $legacyManifestRouted
        restored_runtime_route_error = $restoredRuntimeRouteError
    }

    $committedFixture = New-TransactionFixture
    $stage = Copy-IzStagedProgram -Context $committedFixture.context -Manifest $committedFixture.manifest
    $verified = New-IzMaintenanceTransition $committedFixture.journal PAYLOAD_VERIFIED @('PAYLOAD_STAGED','PAYLOAD_VERIFIED') ([pscustomobject]@{program=$stage.journal_patch})
    Write-IzMaintenanceJournal $committedFixture.context $verified $committedFixture.journal.sequence | Out-Null
    $quiesced = New-IzMaintenanceTransition $verified QUIESCED @('RUNTIME_QUIESCED')
    Write-IzMaintenanceJournal $committedFixture.context $quiesced $verified.sequence | Out-Null
    $protected = New-IzMaintenanceTransition $quiesced SNAPSHOT_VERIFIED
    Write-IzMaintenanceJournal $committedFixture.context $protected $quiesced.sequence | Out-Null
    $swapped = Invoke-IzProgramSwap $committedFixture.context $protected $stage $committedFixture.receipt
    $priorHash = (Get-FileHash $committedFixture.context.install_receipt_path -Algorithm SHA256).Hash.ToLowerInvariant()
    $target = New-IzReleaseIdentity $committedFixture.manifest.version $committedFixture.manifest.build $committedFixture.manifest.installer_revision $committedFixture.manifest.payload_identity
    $targetFiles = @(Get-ChildItem $committedFixture.context.install_root -File -Recurse | Where-Object Name -ne '.iz-cna-owned-root.json' | ForEach-Object {
        [pscustomobject][ordered]@{path=$_.FullName.Substring($committedFixture.context.install_root.Length+1).Replace('\','/');length=[long]$_.Length;sha256=(Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
    })
    $targetReceipt = New-IzInstallReceipt $committedFixture.context $committedFixture.journal.data_identity $target $targetFiles @() ([Guid]$committedFixture.context.transaction_id)
    Write-IzInstallReceipt $committedFixture.context $targetReceipt $priorHash | Out-Null
    $validating = New-IzMaintenanceTransition $swapped VALIDATING @('CANDIDATE_STARTED','CANDIDATE_VALIDATED')
    Write-IzMaintenanceJournal $committedFixture.context $validating $swapped.sequence | Out-Null
    $committed = New-IzMaintenanceTransition $validating COMMITTED @('INSTALL_RECEIPT_WRITTEN','COMMIT_RECORDED')
    Write-IzMaintenanceJournal $committedFixture.context $committed $validating.sequence | Out-Null
    [IO.File]::WriteAllText($committedFixture.database, 'new-data-after-commit', [Text.UTF8Encoding]::new($false))
    $committedProgram = Get-FileDigest (Join-Path $committedFixture.context.install_root 'runtime\IZClinicalNotesAnalyzer.exe')
    $noRollback = Invoke-IzInstallRecovery -Context $committedFixture.context -Journal $committed
    $postCommitSafe = $noRollback.status -ceq 'committed' -and (Get-Content $committedFixture.database -Raw) -eq 'new-data-after-commit' -and
        (Get-FileDigest (Join-Path $committedFixture.context.install_root 'runtime\IZClinicalNotesAnalyzer.exe')) -ceq $committedProgram
    Add-Result -Name 'committed_state_never_rolls_back_program_or_new_data' -Status $(if ($postCommitSafe) { 'passed' } else { 'failed' }) -Observable @{
        recovery_status = [string]$noRollback.status; data_after_commit_preserved = ((Get-Content $committedFixture.database -Raw) -eq 'new-data-after-commit')
        candidate_program_preserved = ((Get-FileDigest (Join-Path $committedFixture.context.install_root 'runtime\IZClinicalNotesAnalyzer.exe')) -ceq $committedProgram)
    }
}

if ($Case -eq 'transaction-transitions') { Invoke-TransactionTransitionCase | Out-Null }
if ($Case -in @('transaction-recovery', 'All')) { Invoke-TransactionRecoveryCase }
if ($Case -in @('transaction-long-path', 'All')) { Invoke-LongStagePathCase }
if ($Case -in @('install-routing', 'All')) {
    Invoke-StatusCase
}
if ($Case -in @('install-negative', 'All')) {
    Invoke-InvalidPackageCase
}

$failed = @($results | Where-Object { $_.status -eq 'failed' })
$blocked = @($results | Where-Object { $_.status -eq 'blocked' })
$receipt = [ordered]@{
    schema = 'iz-cna-maintenance-component-suite-v1'
    suite = 'maintenance-transaction'
    requested_case = $Case
    tier = 'Component'
    status = if ($failed.Count) { 'failed' } elseif ($blocked.Count) { 'blocked' } else { 'passed' }
    invocation = "powershell.exe -NoProfile -File scripts\\tests\\maintenance-transaction.Tests.ps1 -Case $Case"
    results = $results
    artifacts = @(
        'task-09-upgrade.json',
        'task-09-recovery.json',
        'task-10-routing.json',
        'task-10-negative.json'
    )
    cleanup = @{ processes_remaining = 0; retained_owned_evidence = $true }
}
$artifactMap = @(
    'task-09-upgrade.json',
    'task-09-recovery.json',
    'task-10-routing.json',
    'task-10-negative.json'
)
foreach ($artifactName in $artifactMap) {
    $receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $runRoot $artifactName) -Encoding UTF8
}
foreach ($componentRoot in @($componentRoots)) {
    if (Test-Path -LiteralPath $componentRoot) { Remove-Item -LiteralPath $componentRoot -Recurse -Force }
}
Write-Host "Evidence: $(Join-Path $runRoot 'task-09-upgrade.json')"
if ($failed.Count) { exit 1 }
if ($blocked.Count) { exit 2 }
exit 0
