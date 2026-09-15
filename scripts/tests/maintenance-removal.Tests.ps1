[CmdletBinding()]
param(
    [ValidateSet('normal-removal', 'purge-confirmation', 'All')]
    [string]$Case = 'All',
    [string]$EvidenceRoot = ''
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$script:Assertions = [Collections.Generic.List[object]]::new()
$script:Scenarios = [Collections.Generic.List[object]]::new()
$script:Fixtures = [Collections.Generic.List[object]]::new()
$script:Processes = [Collections.Generic.List[object]]::new()
$script:Cleanup = [Collections.Generic.List[object]]::new()
$script:TemporaryHelpers = [Collections.Generic.List[object]]::new()
$script:Failure = $null
$script:StartedUtc = [DateTime]::UtcNow.ToString('o')
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$commonModule = Join-Path $repositoryRoot 'scripts\installer\maintenance-common.psm1'
$contractsModule = Join-Path $repositoryRoot 'scripts\installer\maintenance-contracts.psm1'
$controllerPath = Join-Path $repositoryRoot 'scripts\installer\uninstall-windows-release.ps1'
$dispatcherPath = Join-Path $repositoryRoot 'scripts\installer\maintenance-windows.ps1'
$bootstrapTemplatePath = Join-Path $repositoryRoot 'scripts\installer\templates\Remove-IZ-Clinical-Notes-Analyzer.bootstrap.ps1'
if (-not $EvidenceRoot) {
    $EvidenceRoot = Join-Path $repositoryRoot '.omo\evidence\windows-cmd-maintenance\removal'
}
$qaParent = Join-Path ([IO.Path]::GetTempPath()) 'IZ-CNA-QA'
[IO.Directory]::CreateDirectory($qaParent) | Out-Null
$script:ModuleAnalysisCachePath = Join-Path $qaParent ("removal-module-cache-$PID-$([Guid]::NewGuid().ToString('N')).bin")
$env:PSModuleAnalysisCachePath = $script:ModuleAnalysisCachePath

function Assert-Removal {
    param([bool]$Condition, [string]$Name, [string]$Scenario)
    $script:Assertions.Add([ordered]@{ name = $Name; scenario = $Scenario; passed = $Condition })
    if (-not $Condition) { throw "REMOVAL_ASSERTION_FAILED:$Scenario`:$Name" }
}

function Get-Sha256Text {
    param([string]$Value)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)))).Replace('-', '').ToLowerInvariant()
    } finally { $sha.Dispose() }
}

function Get-TreeState {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return [pscustomobject]@{ exists = $false; count = 0; sha256 = Get-Sha256Text '<absent>' }
    }
    $root = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    $rows = [Collections.Generic.List[string]]::new()
    foreach ($item in @(Get-ChildItem -LiteralPath $root -Force -Recurse | Sort-Object FullName)) {
        $relative = $item.FullName.Substring($root.Length).TrimStart('\').Replace('\', '/')
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            $rows.Add("reparse|$relative")
        } elseif ($item.PSIsContainer) {
            $rows.Add("directory|$relative")
        } else {
            $hash = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            $rows.Add("file|$relative|$($item.Length)|$hash")
        }
    }
    return [pscustomobject]@{
        exists = $true
        count = $rows.Count
        sha256 = Get-Sha256Text ($rows -join "`n")
    }
}

function Get-FileInventoryEntry {
    param([string]$Root, [string]$RelativePath)
    $path = Join-Path $Root $RelativePath
    $item = Get-Item -LiteralPath $path
    return [pscustomobject]@{
        path = $RelativePath.Replace('\', '/')
        length = [long]$item.Length
        sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

function Get-AppDataEnvironment {
    param([object]$Context, [string]$TemporaryRoot)
    return [ordered]@{
        PSModuleAnalysisCachePath = (Join-Path $TemporaryRoot 'PowerShell-ModuleAnalysisCache.bin')
    }
}

function New-RemovalFixture {
    param([string]$Name)
    $qaParent = Join-Path ([IO.Path]::GetTempPath()) 'IZ-CNA-QA'
    [IO.Directory]::CreateDirectory($qaParent) | Out-Null
    $nameToken = (Get-Sha256Text $Name).Substring(0, 8)
    $runRoot = Join-Path $qaParent ("removal-$nameToken-" + [Guid]::NewGuid().ToString('N').Substring(0, 12))
    $componentRoot = Join-Path $runRoot ('iz-cna-component-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
    $tempRoot = Join-Path $runRoot 'Temp'
    [IO.Directory]::CreateDirectory($componentRoot) | Out-Null
    [IO.Directory]::CreateDirectory($tempRoot) | Out-Null

    $context = Get-IzMaintenanceContext -ComponentTestRoot $componentRoot
    $environment = Get-AppDataEnvironment -Context $context -TemporaryRoot $tempRoot
    foreach ($directory in @($context.local_app_data_root, (Split-Path -Parent $context.start_menu_root), (Split-Path -Parent $context.desktop_root), $context.desktop_root)) {
        [IO.Directory]::CreateDirectory($directory) | Out-Null
    }
    Initialize-IzMaintenanceStorage -Context $context | Out-Null
    [IO.Directory]::CreateDirectory($context.install_root) | Out-Null
    [IO.Directory]::CreateDirectory((Join-Path $context.install_root 'runtime')) | Out-Null
    [IO.Directory]::CreateDirectory((Join-Path $context.install_root 'docs')) | Out-Null
    [IO.Directory]::CreateDirectory($context.data_root) | Out-Null
    [IO.Directory]::CreateDirectory((Join-Path $context.data_root 'uploads')) | Out-Null
    [IO.Directory]::CreateDirectory((Join-Path $context.data_root 'logs')) | Out-Null

    [IO.File]::WriteAllText((Join-Path $context.install_root 'runtime\IZClinicalNotesAnalyzer.exe'), 'synthetic-runtime-binary', [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $context.install_root 'Launch-IZ-Clinical-Notes-Analyzer.cmd'), "@echo off`r`nexit /b 0`r`n", [Text.ASCIIEncoding]::new())
    [IO.File]::WriteAllText((Join-Path $context.install_root 'docs\owned.txt'), 'synthetic-owned-program-file', [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $context.data_root '.env'), "LOCAL_SQLITE_DB_PATH=clinical-notes-analyzer.sqlite3`r`n", [Text.UTF8Encoding]::new($false))
    $database = Join-Path $context.data_root 'clinical-notes-analyzer.sqlite3'
    [IO.File]::WriteAllText($database, 'synthetic-sqlite-bytes', [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $context.data_root 'uploads\synthetic-upload.izcna1'), 'synthetic-encrypted-upload', [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $context.data_root 'logs\synthetic.log'), 'synthetic-log', [Text.UTF8Encoding]::new($false))

    $externalRoot = Join-Path $runRoot 'External Backups'
    [IO.Directory]::CreateDirectory($externalRoot) | Out-Null
    $externalBackup = Join-Path $externalRoot 'synthetic.izcnabackup'
    [IO.File]::WriteAllBytes($externalBackup, [Text.Encoding]::ASCII.GetBytes('IZCNABK2synthetic-external-backup'))

    $shortcutDirectory = $context.start_menu_root
    [IO.Directory]::CreateDirectory($shortcutDirectory) | Out-Null
    $shortcutPath = Join-Path $shortcutDirectory 'IZ Clinical Notes Analyzer.lnk'
    $shortcutArguments = '--synthetic-launch'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $context.install_root 'Launch-IZ-Clinical-Notes-Analyzer.cmd'
    $shortcut.Arguments = $shortcutArguments
    $shortcut.WorkingDirectory = $context.install_root
    $shortcut.Save()

    $ownedFiles = @(
        Get-FileInventoryEntry -Root $context.install_root -RelativePath 'runtime\IZClinicalNotesAnalyzer.exe'
        Get-FileInventoryEntry -Root $context.install_root -RelativePath 'Launch-IZ-Clinical-Notes-Analyzer.cmd'
        Get-FileInventoryEntry -Root $context.install_root -RelativePath 'docs\owned.txt'
    )
    $ownedShortcuts = @([pscustomobject]@{
        location = 'start_menu'
        name = 'IZ Clinical Notes Analyzer.lnk'
        target_kind = 'installed_relative'
        target_relative_path = 'Launch-IZ-Clinical-Notes-Analyzer.cmd'
        arguments_sha256 = Get-Sha256Text $shortcutArguments
    })
    $dataIdentity = New-IzDataIdentity -Context $context -SelectedDatabasePath $database
    $release = New-IzReleaseIdentity -Version '2.0.0-beta.4' -Build '2026.09.14.1' -InstallerRevision 1 -PayloadIdentity ('d' * 64)
    $lastCommittedTransaction = [Guid]::NewGuid()
    $receipt = New-IzInstallReceipt -Context $context -DataIdentity $dataIdentity.data_identity -ReleaseIdentity $release -OwnedFiles $ownedFiles -OwnedShortcuts $ownedShortcuts -LastCommittedTransaction $lastCommittedTransaction
    Write-IzInstallReceipt -Context $context -Receipt $receipt -ExpectedPreviousSha256 $null | Out-Null
    $transactionContext = Get-IzMaintenanceContext -ComponentTestRoot $componentRoot -TransactionId $lastCommittedTransaction
    [IO.Directory]::CreateDirectory((Split-Path -Parent $transactionContext.snapshot_path)) | Out-Null
    Write-IzOwnedRootMarker -Context $transactionContext -Path $transactionContext.transaction_root -Role transaction -TransactionId $lastCommittedTransaction | Out-Null
    $snapshotSentinel = $transactionContext.snapshot_path
    [IO.File]::WriteAllBytes($snapshotSentinel, [Text.Encoding]::ASCII.GetBytes('IZCNABK2synthetic-maintenance-snapshot'))

    $fixture = [pscustomobject]@{
        name = $Name
        qa_parent = $qaParent
        run_root = $runRoot
        component_root = $componentRoot
        temp_root = $tempRoot
        context = $context
        environment = $environment
        database = $database
        shortcut_path = $shortcutPath
        snapshot_sentinel = $snapshotSentinel
        external_backup = $externalBackup
        release = $release
        receipt = $receipt
        transaction_context = $transactionContext
    }
    $script:Fixtures.Add($fixture)
    return $fixture
}

function Add-CommittedPreviousTree {
    param([object]$Fixture)
    $context = $Fixture.transaction_context
    [IO.Directory]::CreateDirectory((Join-Path $context.previous_root 'legacy')) | Out-Null
    Write-IzOwnedRootMarker -Context $context -Path $context.previous_root -Role previous -TransactionId ([Guid]$context.transaction_id) | Out-Null
    $ownedPath = Join-Path $context.previous_root 'legacy\previous-owned.bin'
    [IO.File]::WriteAllText($ownedPath, 'synthetic-previous-program', [Text.UTF8Encoding]::new($false))
    $previousPayload = 'e' * 64
    $inventoryFiles = @([pscustomobject]@{
        path = 'legacy/previous-owned.bin'
        length = [long](Get-Item -LiteralPath $ownedPath).Length
        sha256 = (Get-FileHash -LiteralPath $ownedPath -Algorithm SHA256).Hash.ToLowerInvariant()
        owned = $true
    })
    $inventory = New-IzProgramInventory -Context $context -RootPath $context.previous_root -Role previous -PayloadIdentity $previousPayload -Files $inventoryFiles -TransactionId ([Guid]$context.transaction_id)
    $inventoryRelative = 'inventories/previous.json'
    $inventoryPath = Join-Path $context.transaction_root 'inventories\previous.json'
    [IO.Directory]::CreateDirectory((Split-Path -Parent $inventoryPath)) | Out-Null
    Write-IzAtomicJson -Path $inventoryPath -Value $inventory -PreviousPath $null | Out-Null
    $journal = New-IzMaintenanceJournal -Context $context -Action AutoInstall -SourceRelease $Fixture.release -TargetRelease $Fixture.release -DataIdentity $Fixture.receipt.data_identity -PayloadIdentity $Fixture.receipt.payload_identity -PriorReceiptSha256 (Get-IzFileSha256 $Fixture.context.install_receipt_path)
    Write-IzMaintenanceJournal -Context $context -Journal $journal -ExpectedSequence -1 | Out-Null
    $programPatch = [pscustomobject]@{
        previous_payload_identity = $previousPayload
        previous_inventory_relative_path = $inventoryRelative
        previous_inventory_sha256 = Get-IzFileSha256 $inventoryPath
        previous_marker_sha256 = Get-IzFileSha256 (Join-Path $context.previous_root '.iz-cna-owned-root.json')
        active_payload_identity = [string]$Fixture.receipt.payload_identity
    }
    $transitions = @(
        [pscustomobject]@{ state = 'PAYLOAD_VERIFIED'; steps = @('PAYLOAD_STAGED', 'PAYLOAD_VERIFIED'); patch = $null },
        [pscustomobject]@{ state = 'QUIESCED'; steps = @('RUNTIME_QUIESCED'); patch = $null },
        [pscustomobject]@{ state = 'SNAPSHOT_VERIFIED'; steps = @('SNAPSHOT_CREATED', 'SNAPSHOT_VERIFIED'); patch = $null },
        [pscustomobject]@{ state = 'SWAP_INTENT'; steps = @('OLD_MOVE_INTENT_RECORDED'); patch = $null },
        [pscustomobject]@{ state = 'OLD_MOVED'; steps = @('OLD_PROGRAM_MOVED'); patch = [pscustomobject]@{ program = $programPatch } },
        [pscustomobject]@{ state = 'NEW_MOVED'; steps = @('NEW_MOVE_INTENT_RECORDED', 'NEW_PROGRAM_MOVED'); patch = $null },
        [pscustomobject]@{ state = 'VALIDATING'; steps = @('CANDIDATE_STARTED', 'CANDIDATE_VALIDATED'); patch = [pscustomobject]@{ program = [pscustomobject]@{ active_payload_identity = [string]$Fixture.receipt.payload_identity } } },
        [pscustomobject]@{ state = 'COMMITTED'; steps = @('INSTALL_RECEIPT_WRITTEN', 'COMMIT_RECORDED'); patch = $null }
    )
    $expectedSequence = 0
    foreach ($transition in $transitions) {
        $journal = New-IzMaintenanceTransition -Journal $journal -NextState $transition.state -CompletedSteps $transition.steps -Patch $transition.patch
        Write-IzMaintenanceJournal -Context $context -Journal $journal -ExpectedSequence $expectedSequence | Out-Null
        $expectedSequence++
    }
    return [pscustomobject]@{ root = $context.previous_root; owned_file = $ownedPath; inventory_path = $inventoryPath }
}

function Invoke-RemovalControllerProcess {
    param(
        [object]$Fixture,
        [ValidateSet('Uninstall', 'RemoveData')][string]$Action,
        [AllowNull()][string]$InputText,
        [string]$ResultName
    )
    $resultPath = Join-Path $Fixture.run_root $ResultName
    $commonLiteral = $commonModule.Replace("'", "''")
    $controllerLiteral = $controllerPath.Replace("'", "''")
    $componentLiteral = ([string]$Fixture.component_root).Replace("'", "''")
    $shimPath = Join-Path $Fixture.run_root 'invoke-removal-component.ps1'
    $shim = @"
[CmdletBinding()]
param([ValidateSet('Uninstall','RemoveData')][string]`$Action,[string]`$ResultPath)
Set-StrictMode -Version 2.0
`$ErrorActionPreference = 'Stop'
Import-Module '$commonLiteral' -Force
`$context = Get-IzMaintenanceContext -ComponentTestRoot '$componentLiteral'
`$requestedAction = `$Action
`$requestedResultPath = `$ResultPath
. '$controllerLiteral' -NoRun
`$result = Invoke-IzWindowsRemoval -Action `$requestedAction -NoPause -NonInteractive -ResultPath `$requestedResultPath -Context `$context
Write-Host (`$result | ConvertTo-Json -Depth 8 -Compress)
exit [int]`$result.code
"@
    [IO.File]::WriteAllText($shimPath, $shim, [Text.UTF8Encoding]::new($true))
    $arguments = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $shimPath + '"'),
        '-Action', $Action, '-ResultPath', ('"' + $resultPath + '"')
    ) -join ' '
    $startInfo = New-Object Diagnostics.ProcessStartInfo
    $startInfo.FileName = 'powershell.exe'
    $startInfo.Arguments = $arguments
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    foreach ($entry in $Fixture.environment.GetEnumerator()) {
        $startInfo.EnvironmentVariables[[string]$entry.Key] = [string]$entry.Value
    }
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $startInfo
    $started = [DateTime]::UtcNow
    if (-not $process.Start()) { throw 'REMOVAL_CHILD_START_FAILED' }
    if ($null -ne $InputText) { $process.StandardInput.WriteLine($InputText) }
    $process.StandardInput.Close()
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(90000)) {
        try { $process.Kill() } catch { }
        throw 'REMOVAL_CHILD_TIMEOUT'
    }
    $stdoutText = $stdout.Result
    $stderrText = $stderr.Result
    $completed = [DateTime]::UtcNow
    [IO.Directory]::CreateDirectory($EvidenceRoot) | Out-Null
    $diagnosticStem = [IO.Path]::GetFileNameWithoutExtension($ResultName)
    $stdoutPath = Join-Path $EvidenceRoot ($diagnosticStem + '.stdout.txt')
    $stderrPath = Join-Path $EvidenceRoot ($diagnosticStem + '.stderr.txt')
    [IO.File]::WriteAllText($stdoutPath, $stdoutText, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($stderrPath, $stderrText, [Text.UTF8Encoding]::new($false))
    $result = if (Test-Path -LiteralPath $resultPath) { Read-IzMaintenanceResult -Path $resultPath } else { $null }
    $artifactPath = Join-Path $EvidenceRoot $ResultName
    if ($result) {
        [IO.Directory]::CreateDirectory($EvidenceRoot) | Out-Null
        [IO.File]::WriteAllText($artifactPath, ($result | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    }
    return [pscustomobject]@{
        exit_code = [int]$process.ExitCode
        result_path = $artifactPath
        controller_result_path = $resultPath
        result = $result
        elapsed_ms = [long]($completed - $started).TotalMilliseconds
        wait_completed = $true
        stdout_length = $stdoutText.Length
        stderr_length = $stderrText.Length
        stdout_path = $stdoutPath
        stderr_path = $stderrPath
    }
}

function New-RemovalBootstrapBundle {
    param([object]$Fixture)
    $bundleFiles = [string[]]@(
        'maintenance-common.psm1',
        'maintenance-contracts.psm1',
        'maintenance-journal.psm1',
        'maintenance-lock.psm1',
        'maintenance-paths.psm1',
        'maintenance-runtime.psm1',
        'maintenance-version.psm1',
        'maintenance-windows.ps1',
        'uninstall-windows-release.ps1'
    )
    [Array]::Sort($bundleFiles, [StringComparer]::Ordinal)
    $sourceRoot = Join-Path $Fixture.run_root 'Prepared Package\installer'
    [IO.Directory]::CreateDirectory($sourceRoot) | Out-Null
    $records = [Collections.Generic.List[object]]::new()
    foreach ($leaf in $bundleFiles) {
        $source = Join-Path (Join-Path $repositoryRoot 'scripts\installer') $leaf
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "BOOTSTRAP_TEST_SOURCE_MISSING:$leaf" }
        $destination = Join-Path $sourceRoot $leaf
        Copy-Item -LiteralPath $source -Destination $destination
        $item = Get-Item -LiteralPath $destination
        $records.Add([ordered]@{
            path = $leaf
            length = [long]$item.Length
            sha256 = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
        })
    }
    $manifest = [ordered]@{
        schema = 'iz-cna-maintenance-bundle-v1'
        product_id = 'r3.iz-clinical-notes-analyzer.desktop'
        files = @($records)
    }
    $manifestPath = Join-Path $sourceRoot 'maintenance-bundle-manifest.json'
    [IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))
    $manifestHash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $template = [IO.File]::ReadAllText($bootstrapTemplatePath)
    $rendered = $template.Replace('@@MAINTENANCE_BUNDLE_MANIFEST_SHA256@@', $manifestHash)
    if ($rendered -match '@@[A-Z0-9_]+@@') { throw 'BOOTSTRAP_TEST_PLACEHOLDER_REMAINS' }
    $bootstrapPath = Join-Path $sourceRoot 'Remove-IZ-Clinical-Notes-Analyzer.bootstrap.ps1'
    [IO.File]::WriteAllText($bootstrapPath, $rendered, [Text.UTF8Encoding]::new($true))
    return [pscustomobject]@{
        source_root = $sourceRoot
        bootstrap_path = $bootstrapPath
        manifest_path = $manifestPath
        manifest_sha256 = $manifestHash
    }
}

function Invoke-RemovalBootstrapProcess {
    param(
        [object]$Fixture,
        [object]$Bundle,
        [ValidateSet('Uninstall', 'RemoveData')][string]$Action,
        [AllowNull()][string]$InputText,
        [string]$ResultName,
        [switch]$AssumeYes
    )
    [IO.Directory]::CreateDirectory($EvidenceRoot) | Out-Null
    $resultPath = Join-Path $EvidenceRoot $ResultName
    $commonLiteral = $commonModule.Replace("'", "''")
    $bootstrapLiteral = ([string]$Bundle.bootstrap_path).Replace("'", "''")
    $sourceLiteral = ([string]$Bundle.source_root).Replace("'", "''")
    $componentLiteral = ([string]$Fixture.component_root).Replace("'", "''")
    $shimPath = Join-Path $Fixture.run_root ("invoke-bootstrap-component-$Action.ps1")
    $shim = @"
[CmdletBinding()]
param([ValidateSet('Uninstall','RemoveData')][string]`$Action,[string]`$ResultPath,[switch]`$AssumeYes)
Set-StrictMode -Version 2.0
`$ErrorActionPreference = 'Stop'
Import-Module '$commonLiteral' -Force
`$context = Get-IzMaintenanceContext -ComponentTestRoot '$componentLiteral'
`$requestedAction = `$Action
`$requestedResultPath = `$ResultPath
`$requestedAssumeYes = `$AssumeYes
. '$bootstrapLiteral' -NoRun -SourceRoot '$sourceLiteral'
`$exitCode = Invoke-IzRemovalBootstrap -Action `$requestedAction -SourceRoot '$sourceLiteral' -SourceKind Package -NoPause -NonInteractive -ResultPath `$requestedResultPath -AssumeYes:`$requestedAssumeYes -RemainingArguments `$null -Context `$context
exit [int]`$exitCode
"@
    [IO.File]::WriteAllText($shimPath, $shim, [Text.UTF8Encoding]::new($true))
    $argumentParts = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $shimPath + '"'),
        '-Action', $Action, '-ResultPath', ('"' + $resultPath + '"')
    )
    if ($AssumeYes) { $argumentParts += '-AssumeYes' }
    $startInfo = New-Object Diagnostics.ProcessStartInfo
    $startInfo.FileName = 'powershell.exe'
    $startInfo.Arguments = $argumentParts -join ' '
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    foreach ($entry in $Fixture.environment.GetEnumerator()) {
        $startInfo.EnvironmentVariables[[string]$entry.Key] = [string]$entry.Value
    }
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $startInfo
    $started = [DateTime]::UtcNow
    if (-not $process.Start()) { throw 'BOOTSTRAP_CHILD_START_FAILED' }
    if ($null -ne $InputText) { $process.StandardInput.WriteLine($InputText) }
    $process.StandardInput.Close()
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(120000)) {
        try { $process.Kill() } catch { }
        throw 'BOOTSTRAP_CHILD_TIMEOUT'
    }
    $completed = [DateTime]::UtcNow
    $stdoutText = $stdout.Result
    $stderrText = $stderr.Result
    $diagnosticStem = [IO.Path]::GetFileNameWithoutExtension($ResultName)
    $stdoutPath = Join-Path $EvidenceRoot ($diagnosticStem + '.stdout.txt')
    $stderrPath = Join-Path $EvidenceRoot ($diagnosticStem + '.stderr.txt')
    [IO.File]::WriteAllText($stdoutPath, $stdoutText, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($stderrPath, $stderrText, [Text.UTF8Encoding]::new($false))
    $result = if (Test-Path -LiteralPath $resultPath) { Read-IzMaintenanceResult -Path $resultPath } else { $null }
    $helperFilter = 'IZ-CNA-Maintenance-' + ([string]$Fixture.context.scope_id).Substring(0, 16) + '-*'
    $helpersAfter = @(Get-ChildItem -LiteralPath ([IO.Path]::GetTempPath()) -Directory -Filter $helperFilter -ErrorAction SilentlyContinue)
    foreach ($helper in $helpersAfter) {
        $script:TemporaryHelpers.Add([pscustomobject]@{ fixture = $Fixture; path = $helper.FullName })
    }
    return [pscustomobject]@{
        exit_code = [int]$process.ExitCode
        result_path = $resultPath
        result = $result
        elapsed_ms = [long]($completed - $started).TotalMilliseconds
        wait_completed = $true
        stdout_length = $stdoutText.Length
        stderr_length = $stderrText.Length
        stdout_path = $stdoutPath
        stderr_path = $stderrPath
        temp_helpers_after = $helpersAfter.Count
    }
}

function Start-TempCleanupFaultInjector {
    param([object]$Fixture)
    $readyPath = Join-Path $Fixture.run_root 'cleanup-fault-injected.ready'
    $tempLiteral = ([IO.Path]::GetTempPath()).Replace("'", "''")
    $helperFilter = ('IZ-CNA-Maintenance-' + ([string]$Fixture.context.scope_id).Substring(0, 16) + '-*').Replace("'", "''")
    $readyLiteral = $readyPath.Replace("'", "''")
    $source = @"
`$deadline = [DateTime]::UtcNow.AddSeconds(90)
while ([DateTime]::UtcNow -lt `$deadline) {
    `$helper = Get-ChildItem -LiteralPath '$tempLiteral' -Directory -Filter '$helperFilter' -ErrorAction SilentlyContinue | Select-Object -First 1
    if (`$helper -and (Test-Path -LiteralPath (Join-Path `$helper.FullName '.iz-cna-owned-root.json') -PathType Leaf)) {
        [IO.File]::WriteAllText((Join-Path `$helper.FullName 'fault-injected-unknown.tmp'), 'synthetic-cleanup-fault', [Text.UTF8Encoding]::new(`$false))
        [IO.File]::WriteAllText('$readyLiteral', 'ready', [Text.ASCIIEncoding]::new())
        exit 0
    }
    Start-Sleep -Milliseconds 25
}
exit 2
"@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($source))
    $startInfo = New-Object Diagnostics.ProcessStartInfo
    $startInfo.FileName = 'powershell.exe'
    $startInfo.Arguments = '-NoProfile -ExecutionPolicy Bypass -EncodedCommand ' + $encoded
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.EnvironmentVariables['PSModuleAnalysisCachePath'] = Join-Path $Fixture.temp_root 'fault-injector-module-cache.bin'
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $startInfo
    if (-not $process.Start()) { throw 'CLEANUP_FAULT_INJECTOR_START_FAILED' }
    $script:Processes.Add($process)
    return [pscustomobject]@{ process = $process; ready_path = $readyPath }
}

function Add-ScenarioResult {
    param([string]$Id, [string]$Invocation, [string]$Observable, [object]$Process)
    $script:Scenarios.Add([ordered]@{
        id = $Id
        invocation = $Invocation
        binary_observable = $Observable
        exit_code = if ($Process) { [int]$Process.exit_code } else { $null }
        result_code = if ($Process -and $Process.result) { [int]$Process.result.code } else { $null }
        elapsed_ms = if ($Process) { [long]$Process.elapsed_ms } else { $null }
        synchronous_wait_completed = if ($Process -and $Process.PSObject.Properties['wait_completed']) { [bool]$Process.wait_completed } else { $true }
        result_artifact = if ($Process) { Split-Path -Leaf $Process.result_path } else { $null }
    })
}

function Invoke-NormalRemovalTests {
    $scenario = 'normal_preserves_data_and_waits'
    $fixture = New-RemovalFixture -Name 'normal'
    $previous = Add-CommittedPreviousTree -Fixture $fixture
    $dataBefore = Get-TreeState $fixture.context.data_root
    $snapshotHash = (Get-FileHash -LiteralPath $fixture.snapshot_sentinel -Algorithm SHA256).Hash
    $externalHash = (Get-FileHash -LiteralPath $fixture.external_backup -Algorithm SHA256).Hash
    $run = Invoke-RemovalControllerProcess -Fixture $fixture -Action Uninstall -InputText $null -ResultName 'normal-result.json'
    Add-ScenarioResult -Id $scenario -Invocation 'uninstall-windows-release.ps1 -Action Uninstall -NoPause -NonInteractive' -Observable 'exit 0 only after owned program files and shortcut are absent while data/snapshot/external backup hashes match' -Process $run
    Assert-Removal ($run.exit_code -eq 0) 'exit_zero' $scenario
    Assert-Removal ($run.result -and $run.result.code -eq 0) 'receipt_zero' $scenario
    Assert-Removal (-not (Test-Path -LiteralPath $fixture.context.install_root)) 'program_root_absent' $scenario
    Assert-Removal (-not (Test-Path -LiteralPath $previous.root)) 'committed_previous_root_absent' $scenario
    Assert-Removal (-not (Test-Path -LiteralPath $fixture.shortcut_path)) 'owned_shortcut_absent' $scenario
    $dataAfter = Get-TreeState $fixture.context.data_root
    Assert-Removal ($dataAfter.exists -and $dataAfter.sha256 -eq $dataBefore.sha256) 'data_byte_inventory_preserved' $scenario
    Assert-Removal ((Get-FileHash -LiteralPath $fixture.snapshot_sentinel -Algorithm SHA256).Hash -eq $snapshotHash) 'maintenance_snapshot_preserved' $scenario
    Assert-Removal ((Get-FileHash -LiteralPath $fixture.external_backup -Algorithm SHA256).Hash -eq $externalHash) 'external_backup_preserved' $scenario

    $repeat = Invoke-RemovalControllerProcess -Fixture $fixture -Action Uninstall -InputText $null -ResultName 'normal-repeat-result.json'
    Add-ScenarioResult -Id 'normal_idempotent_repeat' -Invocation 'repeat the same Uninstall action' -Observable 'verified no-op exit 0 and retained data hash unchanged' -Process $repeat
    Assert-Removal ($repeat.exit_code -eq 0 -and $repeat.result.code -eq 0) 'repeat_verified_noop' 'normal_idempotent_repeat'
    Assert-Removal ((Get-TreeState $fixture.context.data_root).sha256 -eq $dataBefore.sha256) 'repeat_data_preserved' 'normal_idempotent_repeat'

    $partialScenario = 'normal_preserves_modified_owned_name'
    $partial = New-RemovalFixture -Name 'partial'
    $modifiedFile = Join-Path $partial.context.install_root 'docs\owned.txt'
    $unrelatedFile = Join-Path $partial.context.install_root 'unrelated-support-file.txt'
    [IO.File]::WriteAllText($modifiedFile, 'unrelated-modified-content', [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($unrelatedFile, 'unrelated-unowned-content', [Text.UTF8Encoding]::new($false))
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($partial.shortcut_path)
    $shortcut.Arguments = '--modified-unrelated-arguments'
    $shortcut.Save()
    $partialDataBefore = Get-TreeState $partial.context.data_root
    $partialRun = Invoke-RemovalControllerProcess -Fixture $partial -Action Uninstall -InputText $null -ResultName 'partial-result.json'
    Add-ScenarioResult -Id $partialScenario -Invocation 'Uninstall with a receipt-named file and shortcut modified after receipt creation' -Observable 'exit 40; modified items remain; other verified owned files are removed; data hash matches' -Process $partialRun
    Assert-Removal ($partialRun.exit_code -eq 40 -and $partialRun.result.code -eq 40) 'partial_exit_40' $partialScenario
    Assert-Removal (Test-Path -LiteralPath $modifiedFile) 'modified_file_preserved' $partialScenario
    Assert-Removal (Test-Path -LiteralPath $unrelatedFile) 'unrelated_file_preserved' $partialScenario
    Assert-Removal (Test-Path -LiteralPath $partial.shortcut_path) 'modified_shortcut_preserved' $partialScenario
    Assert-Removal (-not (Test-Path -LiteralPath (Join-Path $partial.context.install_root 'runtime\IZClinicalNotesAnalyzer.exe'))) 'verified_owned_file_removed' $partialScenario
    Assert-Removal ((Get-TreeState $partial.context.data_root).sha256 -eq $partialDataBefore.sha256) 'partial_data_preserved' $partialScenario

    $bootstrapScenario = 'package_bootstrap_waits_for_final_result'
    $bootstrap = New-RemovalFixture -Name 'bootstrap-normal'
    $bootstrapDataBefore = Get-TreeState $bootstrap.context.data_root
    $bootstrapSnapshotHash = (Get-FileHash -LiteralPath $bootstrap.snapshot_sentinel -Algorithm SHA256).Hash
    $bootstrapBundle = New-RemovalBootstrapBundle -Fixture $bootstrap
    $bootstrapRun = Invoke-RemovalBootstrapProcess -Fixture $bootstrap -Bundle $bootstrapBundle -Action Uninstall -InputText $null -ResultName 'bootstrap-normal-result.json'
    Add-ScenarioResult -Id $bootstrapScenario -Invocation 'rendered package bootstrap -> verified TEMP bundle -> dispatcher Uninstall, synchronously waited' -Observable 'process handle exits 0 only after controller receipt, program deletion, retention verification, and TEMP helper cleanup' -Process $bootstrapRun
    Assert-Removal ($bootstrapRun.exit_code -eq 0 -and $bootstrapRun.result.code -eq 0 -and $bootstrapRun.wait_completed) 'bootstrap_final_exit_observed' $bootstrapScenario
    Assert-Removal (-not (Test-Path -LiteralPath $bootstrap.context.install_root)) 'bootstrap_program_absent' $bootstrapScenario
    Assert-Removal ((Get-TreeState $bootstrap.context.data_root).sha256 -eq $bootstrapDataBefore.sha256) 'bootstrap_data_preserved' $bootstrapScenario
    Assert-Removal ((Get-FileHash -LiteralPath $bootstrap.snapshot_sentinel -Algorithm SHA256).Hash -eq $bootstrapSnapshotHash) 'bootstrap_snapshot_preserved' $bootstrapScenario
    Assert-Removal ($bootstrapRun.temp_helpers_after -eq 0) 'bootstrap_temp_cleaned_before_exit' $bootstrapScenario

    $cleanupScenario = 'bootstrap_reports_cleanup_pending'
    $cleanup = New-RemovalFixture -Name 'bootstrap-cleanup-fault'
    $cleanupDataBefore = Get-TreeState $cleanup.context.data_root
    $cleanupBundle = New-RemovalBootstrapBundle -Fixture $cleanup
    $injector = Start-TempCleanupFaultInjector -Fixture $cleanup
    $cleanupRun = Invoke-RemovalBootstrapProcess -Fixture $cleanup -Bundle $cleanupBundle -Action Uninstall -InputText $null -ResultName 'bootstrap-cleanup-pending-result.json'
    [void]$injector.process.WaitForExit(5000)
    Add-ScenarioResult -Id $cleanupScenario -Invocation 'rendered package bootstrap Uninstall with a same-user unknown TEMP-helper entry injected after marker validation' -Observable 'application removal finishes, helper cleanup remains, and final process/receipt report exact code 41' -Process $cleanupRun
    Assert-Removal ($injector.process.HasExited -and $injector.process.ExitCode -eq 0 -and (Test-Path -LiteralPath $injector.ready_path)) 'cleanup_fault_injected' $cleanupScenario
    Assert-Removal ($cleanupRun.exit_code -eq 41 -and $cleanupRun.result.code -eq 41 -and $cleanupRun.result.status -eq 'REMOVED_CLEANUP_PENDING') 'cleanup_pending_exit_41' $cleanupScenario
    Assert-Removal (-not (Test-Path -LiteralPath $cleanup.context.install_root)) 'cleanup_pending_program_removed' $cleanupScenario
    Assert-Removal ((Get-TreeState $cleanup.context.data_root).sha256 -eq $cleanupDataBefore.sha256) 'cleanup_pending_data_preserved' $cleanupScenario
    Assert-Removal ($cleanupRun.temp_helpers_after -eq 1) 'cleanup_pending_helper_retained' $cleanupScenario
}

function Invoke-PurgeConfirmationTests {
    $assumeYesScenario = 'purge_assume_yes_is_not_consent'
    $assumeYes = New-RemovalFixture -Name 'purge-assume-yes'
    $assumeYesProgram = Get-TreeState $assumeYes.context.install_root
    $assumeYesData = Get-TreeState $assumeYes.context.data_root
    $assumeYesMaintenance = Get-TreeState $assumeYes.context.maintenance_root
    $assumeYesBundle = New-RemovalBootstrapBundle -Fixture $assumeYes
    $assumeYesRun = Invoke-RemovalBootstrapProcess -Fixture $assumeYes -Bundle $assumeYesBundle -Action RemoveData -InputText $null -ResultName 'purge-assume-yes-result.json' -AssumeYes
    Add-ScenarioResult -Id $assumeYesScenario -Invocation 'rendered package bootstrap RemoveData -AssumeYes -NoPause with empty confirmation stdin' -Observable 'exit 10; generic flag supplies no consent; all in-scope tree hashes remain identical; TEMP helper is gone' -Process $assumeYesRun
    Assert-Removal ($assumeYesRun.exit_code -eq 10 -and $assumeYesRun.result.code -eq 10) 'assume_yes_cancel_exit_10' $assumeYesScenario
    Assert-Removal ((Get-TreeState $assumeYes.context.install_root).sha256 -eq $assumeYesProgram.sha256) 'assume_yes_program_unchanged' $assumeYesScenario
    Assert-Removal ((Get-TreeState $assumeYes.context.data_root).sha256 -eq $assumeYesData.sha256) 'assume_yes_data_unchanged' $assumeYesScenario
    Assert-Removal ((Get-TreeState $assumeYes.context.maintenance_root).sha256 -eq $assumeYesMaintenance.sha256) 'assume_yes_maintenance_unchanged' $assumeYesScenario
    Assert-Removal ($assumeYesRun.temp_helpers_after -eq 0) 'assume_yes_temp_cleaned' $assumeYesScenario

    foreach ($refusal in @(
        [pscustomobject]@{ id = 'purge_empty_confirmation'; input = $null },
        [pscustomobject]@{ id = 'purge_wrong_confirmation'; input = 'YES' }
    )) {
        $fixture = New-RemovalFixture -Name $refusal.id
        $programBefore = Get-TreeState $fixture.context.install_root
        $dataBefore = Get-TreeState $fixture.context.data_root
        $maintenanceBefore = Get-TreeState $fixture.context.maintenance_root
        $run = Invoke-RemovalControllerProcess -Fixture $fixture -Action RemoveData -InputText $refusal.input -ResultName ($refusal.id + '-result.json')
        Add-ScenarioResult -Id $refusal.id -Invocation 'RemoveData -NoPause -NonInteractive with absent or wrong stdin confirmation' -Observable 'exit 10 and byte-inventory hashes of program/data/maintenance trees remain identical' -Process $run
        Assert-Removal ($run.exit_code -eq 10 -and $run.result.code -eq 10) 'cancel_exit_10' $refusal.id
        Assert-Removal ((Get-TreeState $fixture.context.install_root).sha256 -eq $programBefore.sha256) 'program_unchanged' $refusal.id
        Assert-Removal ((Get-TreeState $fixture.context.data_root).sha256 -eq $dataBefore.sha256) 'data_unchanged' $refusal.id
        Assert-Removal ((Get-TreeState $fixture.context.maintenance_root).sha256 -eq $maintenanceBefore.sha256) 'maintenance_unchanged' $refusal.id
    }

    $successScenario = 'purge_exact_phrase'
    $success = New-RemovalFixture -Name 'purge-success'
    $successPrevious = Add-CommittedPreviousTree -Fixture $success
    $externalHash = (Get-FileHash -LiteralPath $success.external_backup -Algorithm SHA256).Hash
    $successRun = Invoke-RemovalControllerProcess -Fixture $success -Action RemoveData -InputText 'REMOVE IZ DATA' -ResultName 'purge-success-result.json'
    Add-ScenarioResult -Id $successScenario -Invocation 'RemoveData with exact `REMOVE IZ DATA` supplied through stdin' -Observable 'exit 0 after program/data/maintenance roots are absent and external backup hash matches' -Process $successRun
    Assert-Removal ($successRun.exit_code -eq 0 -and $successRun.result.code -eq 0) 'purge_exit_zero' $successScenario
    Assert-Removal (-not (Test-Path -LiteralPath $success.context.install_root)) 'program_removed' $successScenario
    Assert-Removal (-not (Test-Path -LiteralPath $successPrevious.root)) 'committed_previous_removed' $successScenario
    Assert-Removal (-not (Test-Path -LiteralPath $success.context.data_root)) 'data_removed' $successScenario
    Assert-Removal (-not (Test-Path -LiteralPath $success.context.maintenance_root)) 'maintenance_removed' $successScenario
    Assert-Removal ((Get-FileHash -LiteralPath $success.external_backup -Algorithm SHA256).Hash -eq $externalHash) 'external_backup_preserved' $successScenario

    $unknownMaintenanceScenario = 'purge_preserves_unknown_maintenance_file'
    $unknownMaintenance = New-RemovalFixture -Name 'purge-unknown-maintenance'
    [void](Add-CommittedPreviousTree -Fixture $unknownMaintenance)
    $unknownMaintenanceFile = Join-Path $unknownMaintenance.transaction_context.transaction_root 'operator-unknown.txt'
    [IO.File]::WriteAllText($unknownMaintenanceFile, 'unrelated-maintenance-data', [Text.UTF8Encoding]::new($false))
    $unknownMaintenanceHash = (Get-FileHash -LiteralPath $unknownMaintenanceFile -Algorithm SHA256).Hash
    $unknownMaintenanceRun = Invoke-RemovalControllerProcess -Fixture $unknownMaintenance -Action RemoveData -InputText 'REMOVE IZ DATA' -ResultName 'purge-unknown-maintenance-result.json'
    Add-ScenarioResult -Id $unknownMaintenanceScenario -Invocation 'RemoveData exact phrase with an unknown file beside journal-bound transaction artifacts' -Observable 'exit 40; unknown file and transaction marker remain byte-identical while verified program and classified data are removed' -Process $unknownMaintenanceRun
    Assert-Removal ($unknownMaintenanceRun.exit_code -eq 40 -and $unknownMaintenanceRun.result.code -eq 40) 'unknown_maintenance_exit_40' $unknownMaintenanceScenario
    Assert-Removal ((Test-Path -LiteralPath $unknownMaintenanceFile) -and (Get-FileHash -LiteralPath $unknownMaintenanceFile -Algorithm SHA256).Hash -eq $unknownMaintenanceHash) 'unknown_maintenance_file_preserved' $unknownMaintenanceScenario
    Assert-Removal (Test-Path -LiteralPath (Join-Path $unknownMaintenance.transaction_context.transaction_root '.iz-cna-owned-root.json')) 'unknown_maintenance_transaction_marker_preserved' $unknownMaintenanceScenario
    Assert-Removal (-not (Test-Path -LiteralPath $unknownMaintenance.context.install_root)) 'unknown_maintenance_program_removed' $unknownMaintenanceScenario
    Assert-Removal (-not (Test-Path -LiteralPath $unknownMaintenance.context.data_root)) 'unknown_maintenance_data_removed' $unknownMaintenanceScenario

    $tamperedResolvedScenario = 'purge_preserves_tampered_resolved_journal'
    $tamperedResolved = New-RemovalFixture -Name 'purge-tampered-resolved-journal'
    $tamperedResolvedPath = Join-Path $tamperedResolved.transaction_context.transaction_root 'resolved-maintenance-journal.json'
    [IO.File]::WriteAllText($tamperedResolvedPath, '{corrupt-resolved-journal', [Text.UTF8Encoding]::new($false))
    $tamperedResolvedHash = (Get-FileHash -LiteralPath $tamperedResolvedPath -Algorithm SHA256).Hash
    $tamperedResolvedRun = Invoke-RemovalControllerProcess -Fixture $tamperedResolved -Action RemoveData -InputText 'REMOVE IZ DATA' -ResultName 'purge-tampered-resolved-result.json'
    Add-ScenarioResult -Id $tamperedResolvedScenario -Invocation 'RemoveData exact phrase with a corrupt resolved transaction journal' -Observable 'exit 40; corrupt journal and transaction marker remain byte-identical while verified program and classified data are removed' -Process $tamperedResolvedRun
    Assert-Removal ($tamperedResolvedRun.exit_code -eq 40 -and $tamperedResolvedRun.result.code -eq 40) 'tampered_resolved_exit_40' $tamperedResolvedScenario
    Assert-Removal ((Test-Path -LiteralPath $tamperedResolvedPath) -and (Get-FileHash -LiteralPath $tamperedResolvedPath -Algorithm SHA256).Hash -eq $tamperedResolvedHash) 'tampered_resolved_journal_preserved' $tamperedResolvedScenario
    Assert-Removal (Test-Path -LiteralPath (Join-Path $tamperedResolved.transaction_context.transaction_root '.iz-cna-owned-root.json')) 'tampered_resolved_transaction_marker_preserved' $tamperedResolvedScenario
    Assert-Removal (-not (Test-Path -LiteralPath $tamperedResolved.context.install_root)) 'tampered_resolved_program_removed' $tamperedResolvedScenario
    Assert-Removal (-not (Test-Path -LiteralPath $tamperedResolved.context.data_root)) 'tampered_resolved_data_removed' $tamperedResolvedScenario

    $unclassifiedScenario = 'purge_preserves_unclassified_data'
    $unclassified = New-RemovalFixture -Name 'purge-unclassified'
    $unclassifiedFile = Join-Path $unclassified.context.data_root 'operator-unclassified.txt'
    [IO.File]::WriteAllText($unclassifiedFile, 'unrelated-unclassified-data', [Text.UTF8Encoding]::new($false))
    $unclassifiedHash = (Get-FileHash -LiteralPath $unclassifiedFile -Algorithm SHA256).Hash
    $unclassifiedRun = Invoke-RemovalControllerProcess -Fixture $unclassified -Action RemoveData -InputText 'REMOVE IZ DATA' -ResultName 'purge-unclassified-result.json'
    Add-ScenarioResult -Id $unclassifiedScenario -Invocation 'RemoveData exact phrase with an unclassified file at the data root' -Observable 'exit 40; unclassified file and maintenance authority remain; verified program and classified data are removed' -Process $unclassifiedRun
    Assert-Removal ($unclassifiedRun.exit_code -eq 40 -and $unclassifiedRun.result.code -eq 40) 'unclassified_exit_40' $unclassifiedScenario
    Assert-Removal ((Test-Path -LiteralPath $unclassifiedFile) -and (Get-FileHash -LiteralPath $unclassifiedFile -Algorithm SHA256).Hash -eq $unclassifiedHash) 'unclassified_file_preserved' $unclassifiedScenario
    Assert-Removal (-not (Test-Path -LiteralPath $unclassified.context.install_root)) 'unclassified_program_removed' $unclassifiedScenario
    Assert-Removal (-not (Test-Path -LiteralPath (Join-Path $unclassified.context.data_root 'logs\synthetic.log'))) 'classified_data_removed' $unclassifiedScenario
    Assert-Removal (Test-Path -LiteralPath (Join-Path $unclassified.context.maintenance_root '.iz-cna-owned-root.json')) 'maintenance_authority_preserved' $unclassifiedScenario

    $fakeBackupScenario = 'purge_preserves_unowned_valid_backup_magic'
    $fakeBackup = New-RemovalFixture -Name 'purge-unowned-valid-backup-magic'
    $fakeBackupFile = Join-Path $fakeBackup.context.data_root 'operator-unowned.izcnabackup'
    [IO.File]::WriteAllBytes($fakeBackupFile, [Text.Encoding]::ASCII.GetBytes('IZCNABK2synthetic-unowned-root-file'))
    $fakeBackupHash = (Get-FileHash -LiteralPath $fakeBackupFile -Algorithm SHA256).Hash
    $fakeBackupRun = Invoke-RemovalControllerProcess -Fixture $fakeBackup -Action RemoveData -InputText 'REMOVE IZ DATA' -ResultName 'purge-unowned-valid-backup-magic-result.json'
    Add-ScenarioResult -Id $fakeBackupScenario -Invocation 'RemoveData exact phrase with an unowned data-root file beginning with the valid IZCNABK2 magic' -Observable 'exit 40; unowned magic-prefixed file remains byte-identical while verified program and classified data are removed' -Process $fakeBackupRun
    Assert-Removal ((Test-Path -LiteralPath $fakeBackupFile) -and (Get-FileHash -LiteralPath $fakeBackupFile -Algorithm SHA256).Hash -eq $fakeBackupHash) 'unowned_valid_backup_magic_preserved' $fakeBackupScenario
    Assert-Removal ($fakeBackupRun.exit_code -eq 40 -and $fakeBackupRun.result.code -eq 40) 'unowned_valid_backup_magic_exit_40' $fakeBackupScenario
    Assert-Removal (-not (Test-Path -LiteralPath $fakeBackup.context.install_root)) 'unowned_valid_backup_magic_program_removed' $fakeBackupScenario
    Assert-Removal (-not (Test-Path -LiteralPath (Join-Path $fakeBackup.context.data_root 'logs\synthetic.log'))) 'unowned_valid_backup_magic_classified_data_removed' $fakeBackupScenario
    Assert-Removal (Test-Path -LiteralPath (Join-Path $fakeBackup.context.maintenance_root '.iz-cna-owned-root.json')) 'unowned_valid_backup_magic_authority_preserved' $fakeBackupScenario

    $pendingScenario = 'purge_recovery_required_blocks_mutation'
    $pending = New-RemovalFixture -Name 'purge-pending'
    [IO.File]::WriteAllText($pending.context.journal_path, '{corrupt', [Text.UTF8Encoding]::new($false))
    $pendingProgram = Get-TreeState $pending.context.install_root
    $pendingData = Get-TreeState $pending.context.data_root
    $pendingMaintenance = Get-TreeState $pending.context.maintenance_root
    $pendingRun = Invoke-RemovalControllerProcess -Fixture $pending -Action RemoveData -InputText 'REMOVE IZ DATA' -ResultName 'purge-pending-result.json'
    Add-ScenarioResult -Id $pendingScenario -Invocation 'RemoveData with exact phrase and a corrupt pending journal' -Observable 'exit 31 before deletion and all three in-scope tree hashes match' -Process $pendingRun
    Assert-Removal ($pendingRun.exit_code -eq 31 -and $pendingRun.result.code -eq 31) 'pending_exit_31' $pendingScenario
    Assert-Removal ((Get-TreeState $pending.context.install_root).sha256 -eq $pendingProgram.sha256) 'pending_program_unchanged' $pendingScenario
    Assert-Removal ((Get-TreeState $pending.context.data_root).sha256 -eq $pendingData.sha256) 'pending_data_unchanged' $pendingScenario
    Assert-Removal ((Get-TreeState $pending.context.maintenance_root).sha256 -eq $pendingMaintenance.sha256) 'pending_maintenance_unchanged' $pendingScenario

    $reparseScenario = 'purge_reparse_guard'
    $reparse = New-RemovalFixture -Name 'purge-reparse'
    $outside = Join-Path $reparse.run_root 'outside-junction-target'
    [IO.Directory]::CreateDirectory($outside) | Out-Null
    $outsideSentinel = Join-Path $outside 'must-survive.txt'
    [IO.File]::WriteAllText($outsideSentinel, 'outside-safe', [Text.UTF8Encoding]::new($false))
    Remove-Item -LiteralPath (Join-Path $reparse.context.data_root 'uploads') -Recurse -Force
    New-Item -ItemType Junction -Path (Join-Path $reparse.context.data_root 'uploads') -Target $outside | Out-Null
    $programBefore = Get-TreeState $reparse.context.install_root
    $reparseRun = Invoke-RemovalControllerProcess -Fixture $reparse -Action RemoveData -InputText 'REMOVE IZ DATA' -ResultName 'purge-reparse-result.json'
    Add-ScenarioResult -Id $reparseScenario -Invocation 'RemoveData exact phrase with a junction under a known data directory' -Observable 'preflight nonzero before program deletion; outside sentinel remains byte-identical' -Process $reparseRun
    Assert-Removal ($reparseRun.exit_code -in @(20, 31)) 'reparse_preflight_nonzero' $reparseScenario
    Assert-Removal ((Get-TreeState $reparse.context.install_root).sha256 -eq $programBefore.sha256) 'reparse_program_unchanged' $reparseScenario
    Assert-Removal ((Get-FileHash -LiteralPath $outsideSentinel -Algorithm SHA256).Hash -eq (Get-Sha256Text 'outside-safe')) 'reparse_outside_preserved' $reparseScenario
}

function Write-RemovalReceipt {
    param([string]$Status, [string]$Reason)
    [IO.Directory]::CreateDirectory($EvidenceRoot) | Out-Null
    $receipt = [ordered]@{
        schema = 'iz-cna-maintenance-removal-test-v1'
        case = $Case
        status = $Status
        reason = $Reason
        powershell_version = $PSVersionTable.PSVersion.ToString()
        synthetic_only = $true
        actual_default_profile = $false
        live_profile_accessed = $false
        phi_recorded = $false
        cleanup = [ordered]@{
            attempted = $true
            status = if (@($script:Cleanup | Where-Object { $_.status -ne 'passed' }).Count -eq 0) { 'passed' } else { 'failed' }
            owned_paths_only = $true
            artifact_path = 'cleanup.json'
        }
        scenarios = @($script:Scenarios)
        assertions = @($script:Assertions)
        failure = $script:Failure
        started_utc = $script:StartedUtc
        completed_utc = [DateTime]::UtcNow.ToString('o')
    }
    $names = if ($Case -eq 'normal-removal') {
        @('task-11-removal.json', 'task-11-retention.json')
    } elseif ($Case -eq 'purge-confirmation') {
        @('task-12-purge.json', 'task-12-refusals.json')
    } else {
        @('task-11-removal.json', 'task-11-retention.json', 'task-12-purge.json', 'task-12-refusals.json')
    }
    $json = $receipt | ConvertTo-Json -Depth 8
    foreach ($name in $names) {
        [IO.File]::WriteAllText((Join-Path $EvidenceRoot $name), $json, [Text.UTF8Encoding]::new($false))
    }
}

function Write-CleanupReceipt {
    [IO.Directory]::CreateDirectory($EvidenceRoot) | Out-Null
    $receipt = [ordered]@{
        schema = 'iz-cna-maintenance-removal-cleanup-v1'
        status = if (@($script:Cleanup | Where-Object { $_.status -ne 'passed' }).Count -eq 0) { 'passed' } else { 'failed' }
        synthetic_only = $true
        owned_paths_only = $true
        fixtures = @($script:Cleanup)
        completed_utc = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText((Join-Path $EvidenceRoot 'cleanup.json'), ($receipt | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))
}

function Remove-RemovalFixture {
    param([object]$Fixture)
    $full = [IO.Path]::GetFullPath([string]$Fixture.run_root).TrimEnd('\')
    $parent = [IO.Path]::GetFullPath([string]$Fixture.qa_parent).TrimEnd('\')
    if (-not $full.StartsWith($parent + '\removal-', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'TEST_CLEANUP_SCOPE_INVALID'
    }
    if (Test-Path -LiteralPath $full) { Remove-Item -LiteralPath $full -Recurse -Force }
}

function Remove-RemovalTemporaryHelper {
    param([object]$Record)
    $fixture = $Record.fixture
    $full = [IO.Path]::GetFullPath([string]$Record.path).TrimEnd('\')
    $temporaryParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
    $leaf = Split-Path -Leaf $full
    $prefix = 'IZ-CNA-Maintenance-' + ([string]$fixture.context.scope_id).Substring(0, 16) + '-'
    if (-not (Split-Path -Parent $full).Equals($temporaryParent, [StringComparison]::OrdinalIgnoreCase) -or
        -not $leaf.StartsWith($prefix, [StringComparison]::Ordinal) -or
        $leaf.Substring($prefix.Length) -notmatch '^[0-9a-f]{32}$') {
        throw 'TEST_TEMP_CLEANUP_SCOPE_INVALID'
    }
    $transactionId = [Guid]::ParseExact($leaf.Substring($prefix.Length), 'N')
    $context = Get-IzMaintenanceContext -ComponentTestRoot $fixture.component_root -TransactionId $transactionId
    [void](Test-IzOwnedRootMarker -Context $context -Path $full -Role temp_helper -TransactionId $transactionId)
    foreach ($item in @((Get-Item -LiteralPath $full -Force)) + @(Get-ChildItem -LiteralPath $full -Force -Recurse)) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'TEST_TEMP_CLEANUP_REPARSE' }
    }
    Remove-Item -LiteralPath $full -Recurse -Force
    if (Test-Path -LiteralPath $full) { throw 'TEST_TEMP_CLEANUP_FAILED' }
}

$testExitCode = 0
$finalStatus = 'passed'
$finalReason = 'COMPLETED'
try {
    if (-not (Test-Path -LiteralPath $commonModule -PathType Leaf)) { throw 'MAINTENANCE_COMMON_MODULE_MISSING' }
    if (-not (Test-Path -LiteralPath $contractsModule -PathType Leaf)) { throw 'MAINTENANCE_CONTRACTS_MODULE_MISSING' }
    if (-not (Test-Path -LiteralPath $controllerPath -PathType Leaf)) { throw 'REMOVAL_CONTROLLER_MISSING' }
    if (-not (Test-Path -LiteralPath $dispatcherPath -PathType Leaf)) { throw 'MAINTENANCE_DISPATCHER_MISSING' }
    if (-not (Test-Path -LiteralPath $bootstrapTemplatePath -PathType Leaf)) { throw 'REMOVAL_BOOTSTRAP_TEMPLATE_MISSING' }
    Import-Module -Name $commonModule -Force -ErrorAction Stop
    Import-Module -Name $contractsModule -Force -ErrorAction Stop
    if ($Case -in @('normal-removal', 'All')) { Invoke-NormalRemovalTests }
    if ($Case -in @('purge-confirmation', 'All')) { Invoke-PurgeConfirmationTests }
} catch {
    $script:Failure = [ordered]@{
        exception_type = $_.Exception.GetType().FullName
        message = [string]$_.Exception.Message
        error_id = [string]$_.FullyQualifiedErrorId
        script_stack_trace = [string]$_.ScriptStackTrace
    }
    $finalStatus = 'failed'
    $finalReason = if ($_.Exception.Message -match '^[A-Z][A-Z0-9_:.-]+$') { $_.Exception.Message } else { 'REMOVAL_TEST_FAILED' }
    $testExitCode = 1
} finally {
    foreach ($ownedProcess in @($script:Processes)) {
        if (-not $ownedProcess.HasExited) {
            try { $ownedProcess.Kill(); [void]$ownedProcess.WaitForExit(5000) } catch { }
        }
    }
    foreach ($temporaryHelper in @($script:TemporaryHelpers)) {
        $cleanupStatus = 'passed'
        try { Remove-RemovalTemporaryHelper -Record $temporaryHelper } catch { $cleanupStatus = 'failed' }
        $script:Cleanup.Add([ordered]@{
            fixture_id = ([string]$temporaryHelper.fixture.name + '-temp-helper')
            owned_path_hash = Get-Sha256Text ([IO.Path]::GetFullPath([string]$temporaryHelper.path).ToLowerInvariant())
            status = $cleanupStatus
        })
        if ($cleanupStatus -ne 'passed') {
            $finalStatus = 'failed'
            $finalReason = 'TEST_CLEANUP_FAILED'
            $testExitCode = 1
        }
    }
    foreach ($fixture in @($script:Fixtures)) {
        $cleanupStatus = 'passed'
        try {
            Remove-RemovalFixture -Fixture $fixture
            if (Test-Path -LiteralPath $fixture.run_root) { $cleanupStatus = 'failed' }
        } catch { $cleanupStatus = 'failed' }
        $script:Cleanup.Add([ordered]@{
            fixture_id = [string]$fixture.name
            owned_path_hash = Get-Sha256Text ([IO.Path]::GetFullPath([string]$fixture.run_root).ToLowerInvariant())
            status = $cleanupStatus
        })
        if ($cleanupStatus -ne 'passed') {
            $finalStatus = 'failed'
            $finalReason = 'TEST_CLEANUP_FAILED'
            $testExitCode = 1
        }
    }
    if (Test-Path -LiteralPath $script:ModuleAnalysisCachePath -PathType Leaf) {
        try { [IO.File]::Delete($script:ModuleAnalysisCachePath) } catch { }
    }
}
Write-CleanupReceipt
Write-RemovalReceipt -Status $finalStatus -Reason $finalReason
if ($testExitCode -eq 0) {
    Write-Host "[pass] maintenance removal case=$Case assertions=$($script:Assertions.Count)"
} else {
    Write-Error "maintenance removal case=$Case failed: $finalReason" -ErrorAction Continue
}
exit $testExitCode
