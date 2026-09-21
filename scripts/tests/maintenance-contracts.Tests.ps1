[CmdletBinding()]
param(
    [ValidateSet('All', 'contracts', 'contracts-negative', 'identity', 'version', 'paths', 'dispatcher', 'manifest', 'receipt', 'lock', 'journal', 'backup-roundtrip', 'backup-negative')]
    [string]$Case = 'All',
    [string]$EvidenceRoot = ''
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$script:Assertions = [Collections.Generic.List[object]]::new()
$script:StartedUtc = [DateTime]::UtcNow.ToString('o')
$script:CurrentStage = 'STARTING'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$modulePath = Join-Path $repoRoot 'scripts\installer\maintenance-common.psm1'
$backupTests = Join-Path $PSScriptRoot 'maintenance-backup.Tests.ps1'
if (-not $EvidenceRoot) {
    $EvidenceRoot = Join-Path $repoRoot '.omo\evidence\windows-cmd-maintenance\contracts'
}
[IO.Directory]::CreateDirectory($EvidenceRoot) | Out-Null
$env:PSModuleAnalysisCachePath = Join-Path $EvidenceRoot ("psmodule-analysis-$PID.cache")

function Assert-Contract {
    param([bool]$Condition, [string]$Name)
    $script:Assertions.Add([ordered]@{ name = $Name; passed = $Condition })
    if (-not $Condition) { throw "CONTRACT_ASSERTION_FAILED:$Name" }
}

function Assert-ContractError {
    param([scriptblock]$Action, [string]$Reason, [string]$Name)
    $actual = ''
    try { & $Action; throw "EXPECTED_CONTRACT_ERROR:$Name" }
    catch {
        if ($_.Exception.Data.Contains('iz_reason')) {
            $actual = [string]$_.Exception.Data['iz_reason']
        } elseif ($_.Exception.Message -like 'EXPECTED_CONTRACT_ERROR:*') {
            throw
        }
    }
    Assert-Contract -Condition ($actual -eq $Reason) -Name $Name
}

function Get-TestTextSha256 {
    param([string]$Value)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes($Value)
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    } finally { $sha.Dispose() }
}

function Get-TestFileSha256 {
    param([string]$Path)
    $stream = [IO.File]::OpenRead($Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose(); $stream.Dispose() }
}

function Write-TestReceipt {
    param([string]$Status, [string]$Reason)
    [IO.Directory]::CreateDirectory($EvidenceRoot) | Out-Null
    $fileName = if ($Case -eq 'contracts-negative') { 'task-02-negative.json' } elseif ($Case -eq 'contracts') { 'task-02-contracts.json' } else { "task-02-$Case.json" }
    $receipt = [ordered]@{
        schema = 'iz-cna-maintenance-contract-test-v1'
        case = $Case
        status = $Status
        reason = $Reason
        powershell_version = $PSVersionTable.PSVersion.ToString()
        assertions = @($script:Assertions)
        started_utc = $script:StartedUtc
        completed_utc = [DateTime]::UtcNow.ToString('o')
    }
    $json = $receipt | ConvertTo-Json -Depth 6
    [IO.File]::WriteAllText((Join-Path $EvidenceRoot $fileName), $json, [Text.UTF8Encoding]::new($false))
}

function New-TestRoot {
    $qaParent = Join-Path ([IO.Path]::GetTempPath()) ('IZ-CNA-QA & ' + [char]0x00DC)
    [IO.Directory]::CreateDirectory($qaParent) | Out-Null
    $component = Join-Path $qaParent ('iz-cna-component-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
    $runRoot = $component
    [IO.Directory]::CreateDirectory($component) | Out-Null
    return [pscustomobject]@{ qa_parent = $qaParent; run_root = $runRoot; component_root = $component }
}

function Remove-TestRoot {
    param([string]$Path, [string]$QaParent)
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    $parent = [IO.Path]::GetFullPath($QaParent).TrimEnd('\')
    if (-not $full.StartsWith($parent + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'TEST_CLEANUP_SCOPE_INVALID'
    }
    if (Test-Path -LiteralPath $full) { Remove-Item -LiteralPath $full -Recurse -Force }
}

function Invoke-IdentityAndVersionTests {
    # Given: synthetic Unicode path inputs shared with the Python runtime.
    Import-Module (Join-Path $repoRoot 'scripts\installer\maintenance-paths.psm1') -Force
    # When: the path key and domain-separated hash are computed.
    $input = "C:/QA/Stra$([char]0x00DF)e/$([char]0x0130)Z/Cafe$([char]0x0301)"
    $key = ConvertTo-IzPathKey -Path $input
    $hash = Get-IzRootPathHash -Path $input
    # Then: NFC and ASCII-only folding match the frozen cross-language vector.
    $expectedKey = "c:\qa\stra$([char]0x00DF)e\$([char]0x0130)z\caf$([char]0x00E9)"
    Assert-Contract ($key -eq $expectedKey) 'identity_unicode_path_key'
    Assert-Contract ($hash -eq 'd616ba2ee0e935582ca98fee6fac12c45d82f508a842902c5db4c09defc4a090') 'identity_unicode_root_hash'
    $beta3 = New-IzReleaseIdentity -Version '2.0.0-beta.3' -Build '2026.09.03.1' -InstallerRevision 0 -PayloadIdentity ('3' * 64)
    $beta4 = New-IzReleaseIdentity -Version '2.0.0-beta.4' -Build '2026.09.10.2' -InstallerRevision 0 -PayloadIdentity ('4' * 64)
    $beta10 = New-IzReleaseIdentity -Version '2.0.0-beta.10' -Build '2026.09.10.2' -InstallerRevision 0 -PayloadIdentity ('a' * 64)
    Assert-Contract ((Compare-IzReleaseIdentity $beta3 $beta4) -lt 0) 'version_beta3_before_beta4'
    Assert-Contract ((Compare-IzReleaseIdentity $beta4 $beta10) -lt 0) 'version_beta4_before_beta10'
    $newBuild = New-IzReleaseIdentity -Version '2.0.0-beta.4' -Build '2026.09.14.10' -InstallerRevision 1 -PayloadIdentity ('b' * 64)
    Assert-Contract ((Compare-IzReleaseIdentity $beta4 $newBuild) -lt 0) 'version_numeric_build_order'
    $collision = New-IzReleaseIdentity -Version $newBuild.version -Build $newBuild.build -InstallerRevision 1 -PayloadIdentity ('c' * 64)
    Assert-ContractError { Compare-IzReleaseIdentity $newBuild $collision | Out-Null } 'ARTIFACT_COLLISION' 'version_equal_tuple_collision'
    $compatibility = [pscustomobject]@{
        source_version_minimum='2.0.0-beta.3';source_version_maximum='2.0.0-beta.4'
        source_build_minimum='2026.09.03.1';source_build_maximum='2026.09.10.2';source_schema_minimum=12;source_schema_maximum=12
    }
    Assert-Contract (Test-IzReleaseCompatibility -SourceRelease $beta3 -SourceSchema 12 -Manifest ([pscustomobject]@{compatibility=$compatibility})) 'version_boundary_does_not_compare_payload_hash'
    $repairManifest=[pscustomobject]@{version=$newBuild.version;build=$newBuild.build;installer_revision=$newBuild.installer_revision;payload_identity=$newBuild.payload_identity;compatibility=$compatibility}
    Assert-Contract (Test-IzReleaseCompatibility -SourceRelease $newBuild -SourceSchema 12 -Manifest $repairManifest -Repair) 'same_build_repair_bypasses_source_bounds'
    $production = [pscustomobject]@{version='1.0.0';build='2026.09.21.1';installer_revision=1;release_channel='stable-local-desktop'}
    Assert-Contract (Test-IzProductionVersionTransition $beta3 $production) 'production_bridge_accepts_beta3'
    Assert-Contract (Test-IzProductionVersionTransition $beta4 $production) 'production_bridge_accepts_beta4'
    $lastBeta=New-IzReleaseIdentity -Version '2.0.0-beta.4' -Build '2026.09.15.2' -InstallerRevision 1 -PayloadIdentity ('d'*64)
    Assert-Contract (Test-IzProductionVersionTransition $lastBeta $production) 'production_bridge_accepts_last_supported_beta'
    Assert-Contract (-not(Test-IzProductionVersionTransition $beta10 $production)) 'production_bridge_rejects_future_beta'
    $laterBeta=New-IzReleaseIdentity -Version '2.0.0-beta.4' -Build '2026.09.21.2' -InstallerRevision 1 -PayloadIdentity ('e'*64)
    Assert-Contract (-not(Test-IzProductionVersionTransition $laterBeta $production)) 'production_bridge_rejects_newer_beta_build'
    $stable=New-IzReleaseIdentity -Version '1.0.0' -Build '2026.09.21.1' -InstallerRevision 1 -PayloadIdentity ('f'*64)
    Assert-Contract (-not(Test-IzProductionVersionTransition $stable $production)) 'production_bridge_does_not_override_same_version'
    Assert-Contract ((Compare-IzReleaseIdentity $lastBeta $stable) -gt 0) 'production_bridge_keeps_semver_ordering'
    foreach($field in @('version','build','release_channel','installer_revision')) {
        $wrong=$production.PSObject.Copy()
        $wrong.$field=if($field -eq 'installer_revision'){2}else{'unexpected'}
        Assert-Contract (-not(Test-IzProductionVersionTransition $lastBeta $wrong)) ('production_bridge_rejects_target_'+$field)
    }
    $stableCompatibility=[pscustomobject]@{source_version_minimum='1.0.0';source_version_maximum='2.0.0-beta.4';source_build_minimum='2026.09.03.1';source_build_maximum='2026.09.21.1';source_schema_minimum=12;source_schema_maximum=12}
    $production | Add-Member compatibility $stableCompatibility
    Assert-Contract (Test-IzReleaseCompatibility $lastBeta 12 $production) 'production_bridge_retains_schema_compatibility'
    Assert-ContractError { Test-IzReleaseCompatibility $lastBeta 13 $production | Out-Null } 'SOURCE_NOT_COMPATIBLE' 'production_bridge_rejects_wrong_schema'

}

function Invoke-SystemOwnedProfileTests {
    param([object]$Fixture)
    $pathsModule = Get-Module maintenance-paths
    $profile = [Environment]::GetFolderPath(
        [Environment+SpecialFolder]::UserProfile,
        [Environment+SpecialFolderOption]::DoNotVerify
    )
    $result = & $pathsModule {
        param($ExpectedProfile, $ArbitraryPath)
        $originalOwner = (Get-Item Function:Get-IzExistingOwnerSid).ScriptBlock
        $script:IzTestProfilePath = Get-IzCanonicalPath $ExpectedProfile
        try {
            Set-Item Function:Get-IzExistingOwnerSid -Value {
                param([string]$Path)
                $canonical = Get-IzCanonicalPath -Path $Path -AllowMissingLeaf
                if ($canonical.Equals($script:IzTestProfilePath, [StringComparison]::OrdinalIgnoreCase)) {
                    return 'S-1-5-18'
                }
                return Get-IzCurrentUserSid
            }
            $context = Get-IzMaintenanceContext
            $genericReason = try {
                Assert-IzCurrentUserOwner -Path $ExpectedProfile
                ''
            } catch { [string]$_.Exception.Data['iz_reason'] }
            $arbitraryReason = try {
                Assert-IzCurrentUserProfileRoot -Path $ArbitraryPath
                ''
            } catch { [string]$_.Exception.Data['iz_reason'] }
            return [pscustomobject]@{
                context_owner_sid = [string]$context.owner_sid
                generic_reason = $genericReason
                arbitrary_reason = $arbitraryReason
            }
        } finally {
            Set-Item Function:Get-IzExistingOwnerSid -Value $originalOwner
            Remove-Variable IzTestProfilePath -Scope Script -ErrorAction SilentlyContinue
        }
    } $profile $Fixture.run_root
    Assert-Contract ($result.context_owner_sid -eq (Get-IzCurrentUserSid)) 'system_owned_mapped_profile_is_accepted'
    Assert-Contract ($result.generic_reason -eq 'PATH_OWNER_MISMATCH') 'generic_owner_check_stays_current_user_only'
    Assert-Contract ($result.arbitrary_reason -eq 'PATH_OWNER_MISMATCH') 'system_owned_arbitrary_path_is_rejected'
}

function Invoke-DispatcherArgumentTests {
    param([object]$Fixture)
    . (Join-Path $repoRoot 'scripts\installer\maintenance-windows.ps1') -NoRun
    $absent = Invoke-IzMaintenanceAction -Action Invalid -NoPause -NonInteractive -RemainingArguments $null
    Assert-Contract ($absent.code -eq 20 -and $absent.reason -eq 'UNKNOWN_ACTION') 'dispatcher_absent_trailing_arguments_are_empty'
    $unknown = Invoke-IzMaintenanceAction -Action Invalid -NoPause -NonInteractive -RemainingArguments @('--unknown')
    Assert-Contract ($unknown.code -eq 20 -and $unknown.reason -eq 'UNKNOWN_ARGUMENT') 'dispatcher_unknown_trailing_argument_rejected'

    . (Join-Path $repoRoot 'scripts\installer\templates\Remove-IZ-Clinical-Notes-Analyzer.bootstrap.ps1') -NoRun -SourceRoot $repoRoot
    $transactionId = [Guid]::NewGuid()
    $transactionContext = Get-IzMaintenanceContext -ComponentTestRoot $Fixture.component_root -TransactionId $transactionId
    Initialize-IzMaintenanceStorage -Context $transactionContext | Out-Null
    Assert-Contract (Remove-IzBootstrapTransactionScaffold -Context $transactionContext -TransactionId $transactionId) 'bootstrap_owned_empty_transaction_scaffold_removed'
    Initialize-IzMaintenanceStorage -Context $transactionContext | Out-Null
    $unknownPath = Join-Path $transactionContext.transaction_root 'unknown.txt'
    [IO.File]::WriteAllText($unknownPath, 'unowned', [Text.UTF8Encoding]::new($false))
    $rejected = $false
    try { [void](Remove-IzBootstrapTransactionScaffold -Context $transactionContext -TransactionId $transactionId) }
    catch { $rejected = $_.Exception.Message -eq 'TEMP_TRANSACTION_INVALID' }
    Assert-Contract ($rejected -and (Test-Path -LiteralPath $unknownPath -PathType Leaf)) 'bootstrap_transaction_scaffold_preserves_unknown_file'
}

function Invoke-ContextReceiptAndResultTests {
    param([object]$Fixture)
    $transactionId = [Guid]::NewGuid()
    $context = Get-IzMaintenanceContext -TransactionId $transactionId -ComponentTestRoot $Fixture.component_root
    Assert-Contract (-not (Test-Path -LiteralPath $context.maintenance_root)) 'context_has_no_creation_effect'
    Initialize-IzMaintenanceStorage -Context $context | Out-Null
    Assert-Contract (Test-Path -LiteralPath $context.state_root) 'storage_initializes_state_root'
    $marker = Read-IzOwnedRootMarker -Path (Join-Path $context.maintenance_root '.iz-cna-owned-root.json')
    Assert-Contract ($marker.owner_sid -eq $context.owner_sid) 'marker_binds_current_sid'

    [IO.Directory]::CreateDirectory($context.data_root) | Out-Null
    $databaseDirectory = Join-Path $context.data_root 'database'
    [IO.Directory]::CreateDirectory($databaseDirectory) | Out-Null
    $database = Join-Path $databaseDirectory 'custom-synthetic.sqlite3'
    [IO.File]::WriteAllText($database, 'synthetic', [Text.UTF8Encoding]::new($false))
    $dataIdentity = New-IzDataIdentity -Context $context -SelectedDatabasePath $database
    $expectedDataIdentity = Get-TestTextSha256 ("iz-cna-data-identity-v1`n$($context.product_id)`n$($context.owner_sid)`n$(ConvertTo-IzPathKey $context.data_root)`ndatabase\custom-synthetic.sqlite3")
    Assert-Contract ($dataIdentity.data_identity -eq $expectedDataIdentity) 'data_identity_uses_backslash_relative_key'
    $missingDatabase=Join-Path $context.data_root 'database\fresh-missing.sqlite3'
    $freshIdentity=New-IzDataIdentity -Context $context -SelectedDatabasePath $missingDatabase
    Assert-Contract ($freshIdentity.database_relative_path -eq 'database\fresh-missing.sqlite3') 'fresh_database_identity_allows_missing_contained_leaf'
    $release = New-IzReleaseIdentity -Version '2.0.0-beta.4' -Build '2026.09.14.1' -InstallerRevision 1 -PayloadIdentity ('d' * 64)
    $ownedFiles = @([pscustomobject]@{ path = 'runtime/IZClinicalNotesAnalyzer.exe'; length = [long]9; sha256 = ('e' * 64) })
    foreach($relativePath in @(
        'scripts/launch-packaged-runtime.cmd',
        'scripts/Stop-IZ-Clinical-Notes-Analyzer.cmd',
        'scripts/Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd',
        'scripts/Backup-IZ-Clinical-Notes-Analyzer.cmd',
        'scripts/Restore-IZ-Clinical-Notes-Analyzer.cmd',
        'installer/Remove-IZ-Clinical-Notes-Analyzer.bootstrap.ps1'
    )){
        $targetPath=Join-Path $context.install_root $relativePath
        [IO.Directory]::CreateDirectory((Split-Path $targetPath -Parent))|Out-Null
        [IO.File]::WriteAllText($targetPath, 'synthetic shortcut target', [Text.UTF8Encoding]::new($false))
    }
    $bootstrapRelativePath='installer/Remove-IZ-Clinical-Notes-Analyzer.bootstrap.ps1'
    $bootstrapPath=Join-Path $context.install_root $bootstrapRelativePath
    $shortcutManifest=[pscustomobject]@{files=@([pscustomobject]@{
        path=$bootstrapRelativePath
        length=[long](Get-Item -LiteralPath $bootstrapPath).Length
        sha256=Get-TestFileSha256 $bootstrapPath
    })}
    $installModule=New-Module -ArgumentList (Join-Path $repoRoot 'scripts\installer\install-windows-release.ps1') -ScriptBlock {
        param($ControllerPath)
        . $ControllerPath -NoRun
    }
    try{
        $shortcuts=@(& $installModule {
            param($ContextValue,$ManifestValue)
            New-IzInstalledShortcuts -Context $ContextValue -Manifest $ManifestValue -PriorReceipt $null
        } $context $shortcutManifest)
    }finally{Remove-Module $installModule -Force}
    Assert-Contract ($shortcuts.Count -eq 8) 'full_installed_shortcut_set_emitted'
    $shell=New-Object -ComObject WScript.Shell
    try{
        $shortcutIndex=0
        foreach($record in $shortcuts){
            $base=if($record.location -ceq 'start_menu'){$context.start_menu_root}else{$context.desktop_root}
            $shortcutPath=Join-Path $base $record.name
            Assert-Contract (Test-Path -LiteralPath $shortcutPath -PathType Leaf) "installed_shortcut_${shortcutIndex}_exists"
            $actual=$shell.CreateShortcut($shortcutPath)
            $expectedTarget=if($record.target_kind -ceq 'installed_relative'){
                Join-Path $context.install_root $record.target_relative_path
            }else{Join-Path $env:SystemRoot $record.target_relative_path}
            $targetMatches=(Get-IzCanonicalPath $actual.TargetPath -AllowMissingLeaf) -ieq (Get-IzCanonicalPath $expectedTarget -AllowMissingLeaf)
            $argumentsMatch=(Get-TestTextSha256 ([string]$actual.Arguments)) -ceq $record.arguments_sha256
            $workingDirectoryMatches=(Get-IzCanonicalPath $actual.WorkingDirectory) -ieq (Get-IzCanonicalPath $context.install_root)
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($actual)
            Assert-Contract $targetMatches "installed_shortcut_${shortcutIndex}_target_matches"
            Assert-Contract $argumentsMatch "installed_shortcut_${shortcutIndex}_arguments_match"
            Assert-Contract $workingDirectoryMatches "installed_shortcut_${shortcutIndex}_working_directory_matches"
            $shortcutIndex+=1
        }
    }finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}
    Assert-Contract (@($shortcuts|Where-Object{
        $_.target_kind -ceq 'installed_relative' -and ([string]$_.target_relative_path).Contains('\')
    }).Count -eq 0) 'installed_shortcut_targets_use_canonical_separators'
    $receipt = New-IzInstallReceipt -Context $context -DataIdentity $dataIdentity.data_identity -ReleaseIdentity $release -OwnedFiles $ownedFiles -OwnedShortcuts $shortcuts -LastCommittedTransaction ([Guid]::NewGuid())
    Write-IzInstallReceipt -Context $context -Receipt $receipt -ExpectedPreviousSha256 $null | Out-Null
    $readReceipt = Read-IzInstallReceipt -Context $context
    Assert-Contract ($readReceipt.payload_identity -eq $release.payload_identity) 'receipt_roundtrip_payload_identity'
    Assert-Contract (
        $readReceipt.owned_shortcuts.Count -eq 8 -and
        ($readReceipt.owned_shortcuts|ConvertTo-Json -Depth 5 -Compress) -ceq ($shortcuts|ConvertTo-Json -Depth 5 -Compress)
    ) 'full_installed_shortcut_records_roundtrip'
    $tamperedReceipt = $readReceipt | ConvertTo-Json -Depth 8 | ConvertFrom-Json
    $tamperedReceipt.owned_shortcuts[0].target_relative_path = '../outside.cmd'
    [IO.File]::WriteAllText($context.install_receipt_path, ($tamperedReceipt | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    Assert-ContractError { Read-IzInstallReceipt -Context $context | Out-Null } 'SHORTCUT_RECORD_INVALID' 'receipt_tampered_shortcut_rejected'
    [IO.File]::WriteAllText($context.install_receipt_path, ($receipt | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))

    $result = New-IzMaintenanceResult -Action Repair -Status SUCCEEDED -ReleaseIdentity $release -TransactionId $transactionId -Stage FINISHED -Code 0 -Reason COMPLETED -Evidence @('task-02-contracts.json') -StartedUtc $script:StartedUtc
    $resultPath = Join-Path $Fixture.run_root 'result.json'
    Write-IzMaintenanceResult -ResultPath $resultPath -Result $result | Out-Null
    $readResult = Read-IzMaintenanceResult -Path $resultPath
    Assert-Contract ($readResult.code -eq 0 -and $readResult.status -eq 'SUCCEEDED') 'result_roundtrip_exact_status_code'
    $codeMap=[ordered]@{SUCCEEDED=0;NO_OP=0;CANCELLED=10;PREFLIGHT_FAILED=20;BUSY=21;ROLLED_BACK=30;RECOVERY_REQUIRED=31;REMOVAL_INCOMPLETE=40;REMOVED_CLEANUP_PENDING=41}
    $mapValid=$true
    foreach($entry in $codeMap.GetEnumerator()){
        $mapped=New-IzMaintenanceResult -Action Status -Status $entry.Key -ReleaseIdentity $null -TransactionId $transactionId -Stage FINISHED -Code $entry.Value -Reason TEST_OUTCOME
        if($mapped.code -ne $entry.Value){$mapValid=$false}
    }
    Assert-Contract $mapValid 'result_status_code_map_including_41'
    Assert-ContractError { New-IzMaintenanceResult -Action Status -Status REMOVED_CLEANUP_PENDING -ReleaseIdentity $null -TransactionId $transactionId -Stage FINISHED -Code 0 -Reason TEST_OUTCOME | Out-Null } 'RESULT_INVALID' 'result_false_success_code_rejected'
    return $context
}

function Invoke-ManifestTests {
    param([object]$Fixture, [object]$Context, [switch]$Positive, [switch]$Negative)
    $package = Join-Path $Fixture.run_root 'candidate-package'
    $relativeFiles=[string[]]@(
        'Backup-IZ-Clinical-Notes-Analyzer.cmd','Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd','Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd','Install-IZ-Clinical-Notes-Analyzer.cmd',
        'Launch-IZ-Clinical-Notes-Analyzer.cmd','Restore-IZ-Clinical-Notes-Analyzer.cmd','Stop-IZ-Clinical-Notes-Analyzer.cmd','Uninstall-IZ-Clinical-Notes-Analyzer.cmd',
        'app/VERSION','app/VERSION.json','app/config/checklists/treatment-plan-v1.json','app/config/rules/synthetic.yaml','app/frontend/dist/assets/app.js','app/frontend/dist/index.html','app/runtime/IZClinicalNotesAnalyzer.exe',
        'installer/Remove-IZ-Clinical-Notes-Analyzer.bootstrap.ps1','installer/backup-verification.psm1','installer/install-windows-release.ps1','installer/maintenance-bundle-manifest.json','installer/legacy-program-inventory.json',
        'installer/maintenance-common.psm1','installer/maintenance-contracts.psm1','installer/maintenance-journal.psm1','installer/maintenance-lock.psm1','installer/maintenance-paths.psm1',
        'installer/maintenance-runtime.psm1','installer/maintenance-transaction.psm1','installer/maintenance-version.psm1','installer/maintenance-windows.ps1','installer/uninstall-windows-release.ps1'
    )
    [Array]::Sort($relativeFiles,[StringComparer]::Ordinal)
    $files=@()
    foreach($relative in $relativeFiles){
        $content=switch($relative){
            'app/VERSION' {'2.0.0-beta.4'}
            'app/VERSION.json' {'{"version":"2.0.0-beta.4","build":"2026.09.14.1"}'}
            'app/config/checklists/treatment-plan-v1.json' {'{"synthetic":true}'}
            'app/config/rules/synthetic.yaml' {'synthetic: true'}
            'app/frontend/dist/assets/app.js' {'console.log("synthetic")'}
            'app/frontend/dist/index.html' {'<html>synthetic</html>'}
            'app/runtime/IZClinicalNotesAnalyzer.exe' {'synthetic-runtime'}
            default {'synthetic-maintenance-file'}
        }
        $path=Join-Path $package $relative.Replace('/','\');[IO.Directory]::CreateDirectory((Split-Path $path -Parent))|Out-Null
        [IO.File]::WriteAllText($path,$content,[Text.UTF8Encoding]::new($false))
        $files += [pscustomobject][ordered]@{path=$relative;length=(Get-Item $path).Length;sha256=(Get-TestFileSha256 $path)}
    }
    $runtimePath=Join-Path $package 'app\runtime\IZClinicalNotesAnalyzer.exe'
    $records = @($files | ForEach-Object { "$($_.path)`t$($_.length)`t$($_.sha256)`n" }) -join ''
    $manifest = [pscustomobject][ordered]@{
        schema='iz-cna-release-manifest-v1'; product_id='r3.iz-clinical-notes-analyzer.desktop'
        version='2.0.0-beta.4'; build='2026.09.14.1'; installer_revision=1
        release_channel='beta-local-desktop-v2'
        compatibility=[pscustomobject][ordered]@{
            source_version_minimum='2.0.0-beta.3'; source_version_maximum='2.0.0-beta.4'
            source_build_minimum='2026.09.03.1'; source_build_maximum='2026.09.10.2'
            source_schema_minimum=12; source_schema_maximum=12; target_schema=12
        }
        payload_identity=(Get-TestTextSha256 $records); files=$files
    }
    $manifestPath = Join-Path $package 'release-manifest.json'
    [IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    if ($Positive) {
        $read = Read-IzReleaseManifest -PackageRoot $package
        Assert-Contract ($read.payload_identity -eq $manifest.payload_identity) 'manifest_roundtrip_payload_identity'
        Assert-Contract (Test-IzReleasePayload -PackageRoot $package -Manifest $read) 'manifest_exact_payload_files'
        $commandContext = Get-IzMaintenanceContext -PackageRoot $package -TransactionId ([Guid]$Context.transaction_id) -ComponentTestRoot (Split-Path $Context.local_app_data_root -Parent)
        $requestPath = Join-Path $commandContext.requests_root 'snapshot-request.json'
        [IO.File]::WriteAllText($requestPath, '{}', [Text.UTF8Encoding]::new($false))
        $spec = Get-IzRuntimeCommandSpec -Context $commandContext -RuntimeRole Package -Operation SnapshotDatabase -RequestPath $requestPath -ResultPath (Join-Path $commandContext.results_root 'snapshot-result.json') -Manifest $read
        Assert-Contract ($spec.file_path -eq $runtimePath -and $spec.arguments[1] -eq 'snapshot-database') 'package_runtime_command_maps_app_manifest'
    }
    if ($Negative) {
        $missing = $manifest | ConvertTo-Json -Depth 8 | ConvertFrom-Json
        $missing.files = @($missing.files | Where-Object { $_.path -ne 'Install-IZ-Clinical-Notes-Analyzer.cmd' })
        $missingRecords = @($missing.files | ForEach-Object { "$($_.path)`t$($_.length)`t$($_.sha256)`n" }) -join ''
        $missing.payload_identity = Get-TestTextSha256 $missingRecords
        Assert-ContractError { Test-IzReleasePayload -PackageRoot $package -Manifest $missing | Out-Null } 'PAYLOAD_REQUIRED_FILE_MISSING' 'manifest_root_command_required'
        $extra = $manifest | ConvertTo-Json -Depth 8 | ConvertFrom-Json
        $extra | Add-Member -NotePropertyName unexpected -NotePropertyValue $true
        [IO.File]::WriteAllText($manifestPath, ($extra | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
        Assert-ContractError { Read-IzReleaseManifest -PackageRoot $package | Out-Null } 'MANIFEST_INVALID' 'manifest_unknown_field_rejected'
        $invalid = $manifest | ConvertTo-Json -Depth 8 | ConvertFrom-Json
        $invalid.version = '2.0.0-beta.04'
        [IO.File]::WriteAllText($manifestPath, ($invalid | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
        Assert-ContractError { Read-IzReleaseManifest -PackageRoot $package | Out-Null } 'VERSION_INVALID' 'manifest_invalid_semver_rejected'
    }
}

function Invoke-LockAndJournalTests {
    param([object]$Context)
    $script:CurrentStage = 'LOCK_ACQUIRE'
    $lock = Enter-IzMaintenanceLock -Context $Context -Action Repair -TransactionId ([Guid]$Context.transaction_id)
    try {
        $script:CurrentStage = 'LOCK_CONTENTION'
        $command = @"
`$ErrorActionPreference='Stop'
Import-Module '$($modulePath.Replace("'", "''"))' -Force
try {
  `$c=Get-IzMaintenanceContext -TransactionId '$($Context.transaction_id)' -ComponentTestRoot '$($Context.local_app_data_root | Split-Path -Parent)'
  Enter-IzMaintenanceLock -Context `$c -Action Repair -TransactionId '$($Context.transaction_id)' | Out-Null
  exit 99
} catch {
  if (`$_.Exception.Data['iz_exit_code'] -eq 21) { exit 21 }
  exit 98
}
"@
        $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
        $process = Start-Process powershell.exe -ArgumentList @('-NoProfile', '-EncodedCommand', $encoded) -Wait -PassThru -WindowStyle Hidden
        Assert-Contract ($process.ExitCode -eq 21) 'lock_excludes_second_process'
    } finally { Exit-IzMaintenanceLock -LockHandle $lock }

    $staleOwner = [pscustomobject][ordered]@{
        schema='iz-cna-lock-owner-v1'; product_id=$Context.product_id; owner_sid=$Context.owner_sid
        scope_id=$Context.scope_id; transaction_id=$Context.transaction_id; action='Repair'
        process_id=2147480000; process_started_utc='2000-01-01T00:00:00.0000000Z'
        lock_token=('1' * 32); acquired_utc='2000-01-01T00:00:00.0000000Z'
    }
    [IO.File]::WriteAllText($Context.lock_owner_path, ($staleOwner | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
    $recoveredLock = Enter-IzMaintenanceLock -Context $Context -Action Repair -TransactionId ([Guid]$Context.transaction_id)
    try { Assert-Contract ($recoveredLock.lock_token -ne $staleOwner.lock_token) 'stale_pid_record_does_not_block_os_lock' }
    finally { Exit-IzMaintenanceLock -LockHandle $recoveredLock }

    $script:CurrentStage = 'JOURNAL_NEW'
    $source = New-IzReleaseIdentity -Version '2.0.0-beta.3' -Build '2026.09.03.1' -InstallerRevision 0 -PayloadIdentity ('3' * 64)
    $target = New-IzReleaseIdentity -Version '2.0.0-beta.4' -Build '2026.09.14.1' -InstallerRevision 1 -PayloadIdentity ('d' * 64)
    $oldRuntime=Join-Path $Context.install_root 'runtime\IZClinicalNotesAnalyzer.exe'
    [IO.Directory]::CreateDirectory((Split-Path $oldRuntime -Parent))|Out-Null
    [IO.File]::WriteAllText($oldRuntime,'synthetic-old-runtime',[Text.UTF8Encoding]::new($false))
    Protect-IzMaintenancePath $Context.install_root|Out-Null
    $database=Join-Path $Context.data_root 'database\custom-synthetic.sqlite3'
    [IO.Directory]::CreateDirectory((Split-Path $database -Parent))|Out-Null
    [IO.File]::WriteAllText($database,'synthetic',[Text.UTF8Encoding]::new($false))
    Protect-IzMaintenancePath $Context.data_root|Out-Null
    $dataIdentity=(New-IzDataIdentity $Context $database).data_identity
    $sourceOwned=@([pscustomobject][ordered]@{path='runtime/IZClinicalNotesAnalyzer.exe';length=[long](Get-Item $oldRuntime).Length;sha256=(Get-TestFileSha256 $oldRuntime)})
    $sourceReceipt=New-IzInstallReceipt $Context $dataIdentity $source $sourceOwned @() ([Guid]::NewGuid())
    $existingReceiptHash=if(Test-Path $Context.install_receipt_path){Get-TestFileSha256 $Context.install_receipt_path}else{$null}
    Write-IzInstallReceipt $Context $sourceReceipt $existingReceiptHash|Out-Null
    $priorReceiptHash=Get-TestFileSha256 $Context.install_receipt_path

    $snapshotPath=$Context.snapshot_path
    [IO.Directory]::CreateDirectory((Split-Path $snapshotPath -Parent))|Out-Null
    [IO.File]::WriteAllText($snapshotPath,'synthetic-verified-snapshot',[Text.UTF8Encoding]::new($false))
    Protect-IzMaintenancePath $snapshotPath|Out-Null
    $snapshot=[pscustomobject][ordered]@{
        format='IZCNABK2';relative_path='snapshot/pre-change.izcnabackup';length=[long](Get-Item $snapshotPath).Length
        sha256=(Get-TestFileSha256 $snapshotPath);data_identity=$dataIdentity;source_identity_hash=('6' * 64)
        profile_snapshot_identity=('7' * 64);verified=$true
    }

    $journal = New-IzMaintenanceJournal -Context $Context -Action AutoInstall -SourceRelease $source -TargetRelease $target -DataIdentity $dataIdentity -PayloadIdentity $target.payload_identity -PriorReceiptSha256 $priorReceiptHash
    $script:CurrentStage = 'JOURNAL_INITIAL_WRITE'
    Write-IzMaintenanceJournal -Context $Context -Journal $journal -ExpectedSequence -1 | Out-Null
    $next = New-IzMaintenanceTransition -Journal $journal -NextState PAYLOAD_VERIFIED -CompletedSteps @('PAYLOAD_STAGED', 'PAYLOAD_VERIFIED')
    $script:CurrentStage = 'JOURNAL_TRANSITION_WRITE'
    Write-IzMaintenanceJournal -Context $Context -Journal $next -ExpectedSequence 0 | Out-Null
    $read = Read-IzMaintenanceJournal -Context $Context
    Assert-Contract ($read.sequence -eq 1 -and $read.state -eq 'PAYLOAD_VERIFIED') 'journal_monotonic_transition_roundtrip'
    Assert-ContractError { Write-IzMaintenanceJournal -Context $Context -Journal $next -ExpectedSequence 0 } 'JOURNAL_SEQUENCE_CONFLICT' 'journal_stale_writer_rejected'

    $interrupted = New-IzMaintenanceTransition -Journal $next -NextState QUIESCED -CompletedSteps @('RUNTIME_QUIESCED')
    $script:CurrentStage = 'JOURNAL_INTERRUPTION_INJECT'
    $commonModule = Get-Module maintenance-common
    $journalModule = & $commonModule { Get-Module maintenance-journal }
    $contractsModule = & $journalModule { Get-Module maintenance-contracts }
    & $contractsModule { $script:AtomicWriteInterruption = {
        $errorValue = [IO.IOException]::new('INJECTED_INTERRUPTION')
        $errorValue.Data['iz_reason'] = 'INJECTED_INTERRUPTION'
        $errorValue.Data['iz_exit_code'] = 31
        throw $errorValue
    } }
    try { Assert-ContractError { Write-IzMaintenanceJournal -Context $Context -Journal $interrupted -ExpectedSequence 1 } 'INJECTED_INTERRUPTION' 'journal_interruption_is_observable' }
    finally { & $contractsModule { $script:AtomicWriteInterruption = $null } }
    $afterInterruption = Read-IzMaintenanceJournal -Context $Context
    Assert-Contract ($afterInterruption.sequence -eq 1 -and $afterInterruption.state -eq 'PAYLOAD_VERIFIED') 'journal_interruption_preserves_primary_authority'

    $rollbackIntent=New-IzMaintenanceTransition $afterInterruption ROLLBACK_INTENT @('ROLLBACK_INTENT_RECORDED','PROGRAM_RESTORE_INTENT_RECORDED') ([pscustomobject]@{program=[pscustomobject]@{active_payload_identity=$source.payload_identity}})
    $rolledBack=New-IzMaintenanceTransition $rollbackIntent ROLLED_BACK @('OLD_PROGRAM_RESTORED','OLD_RECEIPT_RESTORED','ROLLBACK_VALIDATED')
    $authority=Get-IzMaintenanceAuthority -Context $Context -Journal $rolledBack -InstallReceipt $sourceReceipt
    Assert-Contract ($authority.launch_policy -eq 'source' -and -not $authority.recovery_required) 'validated_rollback_allows_source_launch'
    $unsafe=$rolledBack|ConvertTo-Json -Depth 16|ConvertFrom-Json
    $unsafe.program.active_payload_identity=$null
    $unsafeAuthority=Get-IzMaintenanceAuthority $Context $unsafe $sourceReceipt
    Assert-Contract ($unsafeAuthority.launch_policy -eq 'blocked' -and $unsafeAuthority.recovery_required) 'rollback_missing_active_payload_blocked'
    $hiddenInstall=$Context.install_root+'.authority-check'
    [IO.Directory]::Move($Context.install_root,$hiddenInstall)
    try {
        $missingProgramAuthority=Get-IzMaintenanceAuthority $Context $rolledBack $sourceReceipt
        Assert-Contract ($missingProgramAuthority.launch_policy -eq 'blocked') 'rollback_missing_program_root_blocked'
    } finally { [IO.Directory]::Move($hiddenInstall,$Context.install_root) }
    $hiddenData=$Context.data_root+'.authority-check'
    [IO.Directory]::Move($Context.data_root,$hiddenData)
    try {
        $missingDataAuthority=Get-IzMaintenanceAuthority $Context $rolledBack $sourceReceipt
        Assert-Contract ($missingDataAuthority.launch_policy -eq 'blocked') 'rollback_missing_data_root_blocked'
    } finally { [IO.Directory]::Move($hiddenData,$Context.data_root) }

    $previousRuntime=Join-Path $Context.previous_root 'runtime\old.exe'
    [IO.Directory]::CreateDirectory((Split-Path $previousRuntime -Parent))|Out-Null
    [IO.File]::WriteAllText($previousRuntime,'synthetic-old-runtime',[Text.UTF8Encoding]::new($false))
    Protect-IzMaintenancePath $Context.previous_root|Out-Null
    Write-IzOwnedRootMarker -Context $Context -Path $Context.previous_root -Role previous -TransactionId ([Guid]$Context.transaction_id)|Out-Null
    $oldFiles=@([pscustomobject][ordered]@{path='runtime/old.exe';length=(Get-Item $previousRuntime).Length;sha256=(Get-TestFileSha256 $previousRuntime);owned=$true})
    $inventory=New-IzProgramInventory -Context $Context -RootPath $Context.previous_root -Role previous -PayloadIdentity $source.payload_identity -Files $oldFiles -TransactionId ([Guid]$Context.transaction_id)
    $inventoryRelative='program-previous.json';$inventoryPath=Join-Path $Context.transaction_root $inventoryRelative
    [IO.File]::WriteAllText($inventoryPath,($inventory|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false));Protect-IzMaintenancePath $inventoryPath|Out-Null
    $programPatch=[pscustomobject]@{program=[pscustomobject]@{
        previous_payload_identity=$source.payload_identity;previous_inventory_relative_path=$inventoryRelative
        previous_inventory_sha256=(Get-TestFileSha256 $inventoryPath);previous_marker_sha256=(Get-TestFileSha256 (Join-Path $Context.previous_root '.iz-cna-owned-root.json'))
    }}
    $current=New-IzMaintenanceTransition $afterInterruption QUIESCED @('RUNTIME_QUIESCED')
    Write-IzMaintenanceJournal $Context $current $afterInterruption.sequence|Out-Null
    $prior=$current;$current=New-IzMaintenanceTransition $current SNAPSHOT_VERIFIED @('SNAPSHOT_CREATED','SNAPSHOT_VERIFIED') ([pscustomobject]@{snapshot=$snapshot})
    Write-IzMaintenanceJournal $Context $current $prior.sequence|Out-Null
    $prior=$current;$current=New-IzMaintenanceTransition $current SWAP_INTENT @('OLD_MOVE_INTENT_RECORDED') $programPatch
    Write-IzMaintenanceJournal $Context $current $prior.sequence|Out-Null
    $prior=$current;$current=New-IzMaintenanceTransition $current OLD_MOVED @('OLD_PROGRAM_MOVED')
    Write-IzMaintenanceJournal $Context $current $prior.sequence|Out-Null
    $prior=$current;$current=New-IzMaintenanceTransition $current OLD_MOVED @('NEW_MOVE_INTENT_RECORDED')
    Write-IzMaintenanceJournal $Context $current $prior.sequence|Out-Null
    $prior=$current;$current=New-IzMaintenanceTransition $current NEW_MOVED @('NEW_PROGRAM_MOVED') ([pscustomobject]@{program=[pscustomobject]@{active_payload_identity=$target.payload_identity}})
    Write-IzMaintenanceJournal $Context $current $prior.sequence|Out-Null
    $prior=$current;$current=New-IzMaintenanceTransition $current VALIDATING @('CANDIDATE_STARTED','CANDIDATE_VALIDATED','INSTALL_RECEIPT_WRITTEN')
    Write-IzMaintenanceJournal $Context $current $prior.sequence|Out-Null
    $prior=$current;$committed=New-IzMaintenanceTransition $current COMMITTED @('COMMIT_RECORDED')
    Write-IzMaintenanceJournal $Context $committed $prior.sequence|Out-Null
    Assert-ContractError { New-IzMaintenanceTransition $committed ROLLED_BACK @('OLD_PROGRAM_RESTORED','OLD_RECEIPT_RESTORED','ROLLBACK_VALIDATED') | Out-Null } 'JOURNAL_TRANSITION_INVALID' 'committed_is_terminal'

    $baseContext=Get-IzMaintenanceContext -ComponentTestRoot (Split-Path $Context.local_app_data_root -Parent)
    $pending=Get-IzPendingMaintenanceStatus -Context $baseContext
    Assert-Contract ($pending.status -eq 'COMMITTED' -and $pending.auxiliary_program_roots.Count -eq 1) 'committed_previous_root_descriptor_returned'
    $descriptor=$pending.auxiliary_program_roots[0]
    Assert-Contract ($descriptor.role -eq 'previous' -and $descriptor.owned_files.Count -eq 1 -and $descriptor.owned_files[0].path -eq 'runtime/old.exe') 'auxiliary_descriptor_contains_only_inventory_owned_files'
    [IO.File]::WriteAllText($previousRuntime,'tampered-old-runtime',[Text.UTF8Encoding]::new($false))
    $tamperedPayload=Get-IzPendingMaintenanceStatus -Context $baseContext
    Assert-Contract ($tamperedPayload.status -eq 'RECOVERY_REQUIRED' -and $tamperedPayload.auxiliary_program_roots.Count -eq 0) 'tampered_auxiliary_payload_fails_closed'
    [IO.File]::WriteAllText($previousRuntime,'synthetic-old-runtime',[Text.UTF8Encoding]::new($false))
    [IO.File]::AppendAllText($inventoryPath,"`n",[Text.UTF8Encoding]::new($false))
    $tamperedPending=Get-IzPendingMaintenanceStatus -Context $baseContext
    Assert-Contract ($tamperedPending.status -eq 'RECOVERY_REQUIRED' -and $tamperedPending.auxiliary_program_roots.Count -eq 0) 'tampered_auxiliary_inventory_fails_closed'
}
function Invoke-NegativeTests {
    param([object]$Fixture)
    $context = Get-IzMaintenanceContext -TransactionId ([Guid]::NewGuid()) -ComponentTestRoot $Fixture.component_root
    Initialize-IzMaintenanceStorage -Context $context | Out-Null
    $badResult = Join-Path $Fixture.run_root 'bad-result.json'
    [IO.File]::WriteAllText($badResult, '{"schema":"iz-cna-maintenance-result-v99"}', [Text.UTF8Encoding]::new($false))
    Assert-ContractError { Read-IzMaintenanceResult -Path $badResult | Out-Null } 'UNSUPPORTED_SCHEMA' 'result_unknown_schema_rejected'

    $outside = Join-Path $Fixture.run_root 'outside.txt'
    [IO.File]::WriteAllText($outside, 'safe', [Text.UTF8Encoding]::new($false))
    Assert-ContractError { Assert-IzContainedPath -Path $outside -Parent $context.data_root | Out-Null } 'PATH_OUTSIDE_SCOPE' 'outside_path_rejected'
    Assert-ContractError { Get-IzCanonicalPath -Path (Join-Path $context.data_root '..\escape') | Out-Null } 'PATH_TRAVERSAL' 'dot_traversal_rejected'

    $overlap = $context | Select-Object *
    $overlap.maintenance_root = $overlap.data_root
    Assert-ContractError { Assert-IzMaintenanceContext -Context $overlap | Out-Null } 'CONTEXT_PATH_MISMATCH' 'derived_root_tamper_rejected'
    $redirected = $context | Select-Object *
    $redirected.journal_path = Join-Path $Fixture.run_root 'redirected-journal.json'
    Assert-ContractError { Assert-IzMaintenanceContext -Context $redirected | Out-Null } 'CONTEXT_PATH_MISMATCH' 'hand_built_context_path_rejected'
    $redirectedReceipt = $context | Select-Object *
    $redirectedReceipt.install_receipt_path = Join-Path $Fixture.run_root 'outside-receipt.json'
    $release = New-IzReleaseIdentity '2.0.0-beta.4' '2026.09.14.1' 1 ('d' * 64)
    $receipt = New-IzInstallReceipt $context ('9' * 64) $release @() @() ([Guid]::NewGuid())
    Assert-ContractError { Write-IzInstallReceipt $redirectedReceipt $receipt $null | Out-Null } 'CONTEXT_PATH_MISMATCH' 'receipt_writer_revalidates_context_path'
    Assert-Contract (-not (Test-Path $redirectedReceipt.install_receipt_path)) 'receipt_writer_does_not_create_redirected_path'

    $priorLocalAppData = $env:LOCALAPPDATA
    try {
        $env:LOCALAPPDATA = Join-Path $Fixture.run_root 'inherited-localappdata-conflict'
        Assert-ContractError { Get-IzMaintenanceContext | Out-Null } 'KNOWN_FOLDER_OVERRIDE_CONFLICT' 'inherited_known_folder_override_rejected'
    } finally {
        if ($null -eq $priorLocalAppData) { Remove-Item Env:LOCALAPPDATA -ErrorAction SilentlyContinue }
        else { $env:LOCALAPPDATA = $priorLocalAppData }
    }

    $target = Join-Path $Fixture.run_root 'junction-target'
    $junction = Join-Path $Fixture.component_root 'junction'
    [IO.Directory]::CreateDirectory($target) | Out-Null
    New-Item -ItemType Junction -Path $junction -Target $target | Out-Null
    Assert-ContractError { Get-IzCanonicalPath -Path (Join-Path $junction 'child') -AllowMissingLeaf | Out-Null } 'PATH_REPARSE_POINT' 'reparse_ancestor_rejected'

    $markerPath = Join-Path $context.maintenance_root '.iz-cna-owned-root.json'
    $wrongSidMarker = Read-IzOwnedRootMarker -Path $markerPath
    $wrongSidMarker.owner_sid = 'S-1-5-18'
    [IO.File]::WriteAllText($markerPath, ($wrongSidMarker | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
    Assert-ContractError { Test-IzOwnedRootMarker -Context $context -Path $context.maintenance_root -Role maintenance | Out-Null } 'OWNED_ROOT_MARKER_MISMATCH' 'wrong_sid_marker_rejected'
    Write-IzOwnedRootMarker -Context $context -Path $context.maintenance_root -Role maintenance | Out-Null

    [IO.File]::WriteAllText($context.journal_path, '{broken', [Text.UTF8Encoding]::new($false))
    Assert-ContractError { Read-IzMaintenanceJournal -Context $context | Out-Null } 'JOURNAL_CORRUPT' 'corrupt_journal_rejected'
}

$fixture = $null
try {
    if ($Case -in @('backup-roundtrip', 'backup-negative')) {
        if (-not (Test-Path -LiteralPath $backupTests)) { throw 'BACKUP_CONTRACT_TESTS_UNAVAILABLE' }
        & powershell.exe -NoProfile -File $backupTests -Case $Case -EvidenceRoot $EvidenceRoot
        if ($LASTEXITCODE -ne 0) { throw "BACKUP_CONTRACT_TEST_FAILED:$LASTEXITCODE" }
        Write-TestReceipt -Status 'passed' -Reason 'COMPLETED'
        exit 0
    }
    if (-not (Test-Path -LiteralPath $modulePath)) { throw 'MAINTENANCE_COMMON_MODULE_MISSING' }
    $fixture = New-TestRoot
    $childProcessesBefore = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$PID" | ForEach-Object ProcessId)
    Import-Module $modulePath -Force
    Import-Module (Join-Path $repoRoot 'scripts\installer\maintenance-paths.psm1') -Force
    Assert-Contract (@(Get-ChildItem -LiteralPath $fixture.component_root -Force).Count -eq 0) 'import_has_no_disk_effect'
    $childProcessesAfter = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$PID" | ForEach-Object ProcessId)
    Assert-Contract (@($childProcessesAfter | Where-Object { $_ -notin $childProcessesBefore }).Count -eq 0) 'import_starts_no_child_process'
    if ($Case -in @('All', 'contracts', 'identity', 'version')) { Invoke-IdentityAndVersionTests }
    if ($Case -in @('All', 'contracts', 'paths')) { Invoke-SystemOwnedProfileTests -Fixture $fixture }
    if ($Case -in @('All', 'contracts', 'dispatcher')) { Invoke-DispatcherArgumentTests -Fixture $fixture }
    if ($Case -in @('All', 'contracts', 'paths', 'receipt')) {
        $context = Invoke-ContextReceiptAndResultTests -Fixture $fixture
    } else {
        $context = Get-IzMaintenanceContext -TransactionId ([Guid]::NewGuid()) -ComponentTestRoot $fixture.component_root
        Initialize-IzMaintenanceStorage -Context $context | Out-Null
    }
    if ($Case -in @('All', 'contracts', 'manifest')) { Invoke-ManifestTests -Fixture $fixture -Context $context -Positive -Negative:($Case -in @('All','manifest')) }
    if ($Case -in @('All', 'contracts', 'lock', 'journal')) { Invoke-LockAndJournalTests -Context $context }
    if ($Case -in @('All', 'contracts-negative', 'manifest')) {
        if ($Case -eq 'contracts-negative') { Invoke-ManifestTests -Fixture $fixture -Context $context -Negative }
        Invoke-NegativeTests -Fixture $fixture
    }
    if ($Case -eq 'All') {
        foreach ($backupCase in @('backup-roundtrip', 'backup-negative')) {
            if (-not (Test-Path -LiteralPath $backupTests)) { throw 'BACKUP_CONTRACT_TESTS_UNAVAILABLE' }
            & powershell.exe -NoProfile -File $backupTests -Case $backupCase -EvidenceRoot $EvidenceRoot
            if ($LASTEXITCODE -ne 0) { throw "BACKUP_CONTRACT_TEST_FAILED:$backupCase`:$LASTEXITCODE" }
        }
    }
    Write-TestReceipt -Status 'passed' -Reason 'COMPLETED'
    Write-Host "[pass] maintenance contracts case=$Case assertions=$($script:Assertions.Count)"
    exit 0
} catch {
    $reason = if ($_.Exception.Data['iz_reason']) { [string]$_.Exception.Data['iz_reason'] } elseif ($_.Exception.Message -match '^[A-Z][A-Z0-9_:.-]+$') { $_.Exception.Message } else { 'CONTRACT_TEST_FAILED_' + $script:CurrentStage }
    Write-TestReceipt -Status 'failed' -Reason $reason
    Write-Error "maintenance contracts case=$Case failed: $reason"
    exit 1
} finally {
    if ($fixture) { Remove-TestRoot -Path $fixture.run_root -QaParent $fixture.qa_parent }
}
