[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$BackupScript = Join-Path $RepositoryRoot 'scripts\backup-local-data.ps1'
$RestoreScript = Join-Path $RepositoryRoot 'scripts\restore-local-data.ps1'
$BuildScript = Join-Path $RepositoryRoot 'scripts\build-windows-installer.ps1'
$PreflightScript = Join-Path $RepositoryRoot 'scripts\preflight-windows.ps1'
$StopScript = Join-Path $RepositoryRoot 'scripts\stop-windows-local.ps1'
$LocalStackSmokeScript = Join-Path $RepositoryRoot 'scripts\tests\test-local-app-stack.ps1'
$ApiConfigurationSmokeScript = Join-Path $RepositoryRoot 'scripts\tests\test-api-configuration-local.ps1'
$PythonPath = Join-Path $RepositoryRoot 'backend\.venv\Scripts\python.exe'
$PasslibHook = Join-Path $RepositoryRoot 'scripts\installer\pyinstaller-hooks\hook-passlib.py'
$CommonModule = Join-Path $RepositoryRoot 'scripts\installer\maintenance-common.psm1'
$BackupModule = Join-Path $RepositoryRoot 'scripts\installer\backup-verification.psm1'

function Assert-True {
    param([bool]$Condition, [string]$Label)
    if (-not $Condition) { throw "Assertion failed: $Label" }
    Write-Host "[pass] $Label"
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("iz-cna-component-" + [Guid]::NewGuid().ToString('N').Substring(0, 12))
$savedEnvironment = @{}
$environmentNames = @('LOCALAPPDATA','APPDATA','USERPROFILE','IZ_CNA_ENV_FILE','IZ_CNA_LOCAL_APP_DATA_DIR','IZ_CNA_LOCAL_SQLITE_DB_PATH','IZ_CNA_DATA_ENCRYPTION_KEY','LOCAL_SQLITE_DB_PATH','DATA_ENCRYPTION_KEY','SECRET_KEY','PSModuleAnalysisCachePath')
foreach ($name in $environmentNames) { $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    foreach ($name in $environmentNames) { [Environment]::SetEnvironmentVariable($name, $null, 'Process') }
    $componentRoot = $tempRoot
    $env:LOCALAPPDATA = Join-Path $componentRoot 'LocalAppData'
    $env:APPDATA = Join-Path $componentRoot 'AppData'
    $env:USERPROFILE = Join-Path $componentRoot 'UserProfile'
    $env:PSModuleAnalysisCachePath = Join-Path $tempRoot 'module-analysis-cache'
    New-Item -ItemType Directory -Path $env:LOCALAPPDATA, $env:APPDATA, $env:USERPROFILE -Force | Out-Null
    $localData = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer'
    $preflightOutput = @(& $PreflightScript -AssumeYes -InitializePackagedRuntime -ReportPath (Join-Path $tempRoot 'preflight.json') 2>&1)
    $preflightExit = $LASTEXITCODE
    $preflightOutput = @()
    Assert-True -Condition ($preflightExit -eq 0) -Label 'packaged_preflight_generates_profile'
    $environmentPath = Join-Path $localData '.env'
    $databaseDirectory = Join-Path $localData 'database'
    $databasePath = Join-Path $databaseDirectory 'custom-lifecycle.sqlite3'
    $encryptedDirectory = Join-Path $localData 'encrypted-uploads'
    $encryptedPath = Join-Path $encryptedDirectory 'synthetic-envelope.bin'
    $keysDirectory = Join-Path $localData 'keys'
    New-Item -ItemType Directory -Path $databaseDirectory, $encryptedDirectory, $keysDirectory -Force | Out-Null
    $environmentLines = Get-Content -LiteralPath $environmentPath
    $secretLine = @($environmentLines | Where-Object { $_ -like 'DATA_ENCRYPTION_KEY=*' })
    Assert-True -Condition ($secretLine.Count -eq 1) -Label 'packaged_preflight_generated_encryption_key'
    $syntheticSecret = ([string]$secretLine[0]).Substring('DATA_ENCRYPTION_KEY='.Length)
    $absoluteAliases = "IZ_CNA_ENV_FILE=`"$environmentPath`"`r`nIZ_CNA_LOCAL_APP_DATA_DIR=`"$localData`"`r`nIZ_CNA_LOCAL_SQLITE_DB_PATH=`"$databasePath`"`r`n"
    [IO.File]::AppendAllText($environmentPath, $absoluteAliases, [Text.UTF8Encoding]::new($false))
    $environmentHash = (Get-FileHash -LiteralPath $environmentPath -Algorithm SHA256).Hash
    $fixtureCode = @'
import base64, hashlib, os, sqlite3, sys
from pathlib import Path
from cryptography.fernet import Fernet
database, encrypted, secret = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
cipher = Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode('utf-8')).digest()))
payload = b'IZCNA1:' + cipher.encrypt(b'{"fixture":"lifecycle-synthetic-only"}')
encrypted.write_bytes(payload)
connection = sqlite3.connect(database)
connection.execute('PRAGMA journal_mode=WAL')
connection.execute('PRAGMA wal_autocheckpoint=0')
connection.executescript('CREATE TABLE schema_migrations(version INTEGER NOT NULL); INSERT INTO schema_migrations VALUES(12); CREATE TABLE patients(id INTEGER PRIMARY KEY, synthetic_code TEXT NOT NULL); CREATE TABLE treatment_plan_imports(id INTEGER PRIMARY KEY, encrypted_payload BLOB NOT NULL); CREATE TABLE source_documents(id INTEGER PRIMARY KEY, encrypted_relative_path TEXT NOT NULL);')
connection.execute('INSERT INTO patients(synthetic_code) VALUES(?)', ('SYNTHETIC-0001',))
connection.execute('INSERT INTO treatment_plan_imports(encrypted_payload) VALUES(?)', (payload,))
connection.execute('INSERT INTO source_documents(encrypted_relative_path) VALUES(?)', ('encrypted-uploads/synthetic-envelope.bin',))
connection.execute('INSERT INTO patients(synthetic_code) VALUES(?)', ('SYNTHETIC-WAL-0002',))
connection.commit()
os._exit(0)
'@
    & $PythonPath -c $fixtureCode $databasePath $encryptedPath $syntheticSecret
    Assert-True -Condition ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath ($databasePath + '-wal') -PathType Leaf)) -Label 'lifecycle_fixture_contains_committed_wal'
    $syntheticSecret = $null
    [IO.File]::WriteAllText((Join-Path $keysDirectory 'synthetic.key'), 'synthetic-key-only', [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $localData 'synthetic-state.txt'), 'before-upgrade-synthetic-state', [Text.UTF8Encoding]::new($false))
    $backupOutput = Join-Path $tempRoot 'backup & () ! % Ü'
    Assert-True -Condition ((Get-Content -LiteralPath $environmentPath -Raw) -match [regex]::Escape($databasePath)) -Label 'profile_uses_absolute_custom_database_alias'
    Import-Module $CommonModule -Force
    Import-Module $BackupModule -Force
    New-Item -ItemType Directory -Path $backupOutput -Force | Out-Null
    $backupPath = Join-Path $backupOutput 'lifecycle & () ! % Ü.izcnabackup'
    $backupTransaction = [Guid]::NewGuid()
    $backupContext = Get-IzMaintenanceContext -PackageRoot $RepositoryRoot -TransactionId $backupTransaction -ComponentTestRoot $componentRoot
    Initialize-IzMaintenanceStorage -Context $backupContext | Out-Null
    $dataIdentity = New-IzDataIdentity -Context $backupContext -SelectedDatabasePath $databasePath
    $backupLock = Enter-IzMaintenanceLock -Context $backupContext -Action Backup -TransactionId $backupTransaction
    try {
        $backup = New-IzFullBackup -Context $backupContext -DataIdentity $dataIdentity -RuntimeRole SourceTest -Manifest $null -BackupPath $backupPath
    }
    finally {
        Exit-IzMaintenanceLock -LockHandle $backupLock
    }
    Assert-True -Condition ($backup.status -eq 'success' -and $backup.verified) -Label 'encrypted_backup_command_succeeds'
    Assert-True -Condition ($backup -and (Test-Path -LiteralPath $backup.Path)) -Label 'encrypted_backup_file_created'
    Assert-True -Condition ([IO.Path]::GetExtension([string]$backup.Path) -eq '.izcnabackup') -Label 'encrypted_backup_extension'
    $backupMagic = [Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes($backup.Path), 0, 8)
    Assert-True -Condition ($backupMagic -eq 'IZCNABK2') -Label 'encrypted_backup_magic'
    Assert-True -Condition ($backup.profile_snapshot_identity -match '^[0-9a-f]{64}$' -and [int]$backup.safe_counts.patients -eq 2) -Label 'backup_verifies_wal_aware_profile_snapshot'

    Set-Content -LiteralPath (Join-Path $localData 'synthetic-state.txt') -Value 'mutated-synthetic-state' -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $localData 'post-backup-only.txt') -Value 'remove-on-restore' -Encoding UTF8
    $restoreTransaction = [Guid]::NewGuid()
    $restoreContext = Get-IzMaintenanceContext -PackageRoot $RepositoryRoot -TransactionId $restoreTransaction -ComponentTestRoot $componentRoot
    Initialize-IzMaintenanceStorage -Context $restoreContext | Out-Null
    $restoreLock = Enter-IzMaintenanceLock -Context $restoreContext -Action Restore -TransactionId $restoreTransaction
    try {
        $restore = Restore-IzFullBackup -Context $restoreContext -BackupPath $backup.Path -RuntimeRole SourceTest -Manifest $null -ExpectedProfileSnapshotIdentity $backup.profile_snapshot_identity -Confirmed
    }
    finally {
        Exit-IzMaintenanceLock -LockHandle $restoreLock
    }
    Assert-True -Condition ($restore.status -eq 'success' -and $restore.verified -and $restore.profile_snapshot_identity -eq $backup.profile_snapshot_identity) -Label 'encrypted_restore_command_succeeds'
    Assert-True -Condition ((Get-Content -LiteralPath (Join-Path $localData 'synthetic-state.txt') -Raw).Trim() -eq 'before-upgrade-synthetic-state') -Label 'restore_replaces_mutated_data'
    Assert-True -Condition ((Get-FileHash -LiteralPath $environmentPath -Algorithm SHA256).Hash -eq $environmentHash) -Label 'restore_preserves_environment_bytes'
    Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $localData 'post-backup-only.txt'))) -Label 'restore_replaces_full_data_tree'
    $countCode = "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute('select count(*) from patients').fetchone()[0]); c.close()"
    $patientCount = & $PythonPath -c $countCode $databasePath
    Assert-True -Condition ($LASTEXITCODE -eq 0 -and $patientCount -eq '2') -Label 'restore_contains_committed_wal_rows'

    foreach ($scriptPath in @($BackupScript, $RestoreScript)) {
        $parseErrors = $null
        [void][Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$null, [ref]$parseErrors)
        Assert-True -Condition ($parseErrors.Count -eq 0) -Label ("public_script_parses_" + [IO.Path]::GetFileNameWithoutExtension($scriptPath))
    }
    $backupScriptText = Get-Content -LiteralPath $BackupScript -Raw
    $restoreScriptText = Get-Content -LiteralPath $RestoreScript -Raw
    Assert-True -Condition ($backupScriptText -match "'SourceTest'" -and $restoreScriptText -match "'SourceTest'") -Label 'public_scripts_use_validated_source_runtime_role'
    Assert-True -Condition ($backupScriptText -match 'backup-verification\.psm1' -and $restoreScriptText -match 'backup-verification\.psm1') -Label 'public_scripts_import_shared_backup_implementation'
    Assert-True -Condition ($backupScriptText -match 'Enter-IzMaintenanceLock' -and $restoreScriptText -match 'Enter-IzMaintenanceLock') -Label 'public_scripts_hold_shared_maintenance_lock'
    Assert-True -Condition ($backupScriptText -notmatch 'ComponentTestRoot' -and $restoreScriptText -notmatch 'ComponentTestRoot') -Label 'public_scripts_expose_no_test_root_override'
    Assert-True -Condition ($backupScriptText -match 'Documents\\IZ Clinical Notes Analyzer Backups') -Label 'public_backup_keeps_documents_default'

    $buildText = Get-Content -LiteralPath $BuildScript -Raw
    Assert-True -Condition ($buildText -match 'Restore-IZ-Clinical-Notes-Analyzer\.cmd') -Label 'release_contains_restore_command'
    Assert-True -Condition ($buildText -match 'Copy-ApplicationMaintenanceHelpers' -and $buildText -match 'backup-verification\.psm1') -Label 'release_copies_shared_backup_verification'
    Assert-True -Condition ($buildText -match 'app\\runtime') -Label 'release_requires_runtime_payload'
    Assert-True -Condition ($buildText -match '--additional-hooks-dir \$passlibHookDirectory') -Label 'runtime_uses_filtered_passlib_hook_directory'
    $passlibHookText = Get-Content -LiteralPath $PasslibHook -Raw
    Assert-True -Condition ($passlibHookText -match 'collect_all\(\s*["'']passlib["'']') -Label 'passlib_hook_collects_dynamic_runtime_handlers'
    Assert-True -Condition ($passlibHookText -match 'exclude_datas\s*=\s*\[["'']tests["'']\]') -Label 'passlib_hook_excludes_test_data'
    Assert-True -Condition ($passlibHookText -match 'is_module_or_submodule\(name,\s*["'']passlib\.tests["'']\)') -Label 'passlib_hook_excludes_test_submodules'
    Assert-True -Condition ($buildText -match 'Import-Module' -and $buildText -match 'build-windows-package\.psm1') -Label 'builder_imports_versioned_packaging_module'
    Assert-True -Condition ($buildText -match 'Write-IzReleaseManifest' -and $buildText -match 'Assert-ZipMatchesManifest') -Label 'builder_validates_directory_and_zip_manifest'
    Assert-True -Condition ($buildText -match 'Remove-Item Env:\\IZ_CNA_ENV_FILE') -Label 'backend_tests_isolate_preflight_environment'
    $stopText = Get-Content -LiteralPath $StopScript -Raw
    Assert-True -Condition ($stopText -match 'Test-IsBundledRuntime') -Label 'stop_recognizes_bundled_runtime'
    Assert-True -Condition ($stopText -match 'runtime\\IZClinicalNotesAnalyzer\.exe') -Label 'stop_validates_bundled_runtime_path'
    $localStackSmokeText = Get-Content -LiteralPath $LocalStackSmokeScript -Raw
    Assert-True -Condition ($localStackSmokeText -match 'Remove-Item Env:\\IZ_CNA_ENV_FILE -ErrorAction SilentlyContinue') -Label 'local_stack_tests_clear_smoke_environment'
    Assert-True -Condition ($localStackSmokeText -match 'IZ_CNA_LOCAL_APP_DATA_DIR=\$AppDataRoot') -Label 'local_stack_server_root_matches_synthetic_database'
    Assert-True -Condition ($localStackSmokeText -match 'Reset-SmokeDatabase -DatabasePath \$DatabasePath') -Label 'local_stack_resets_stale_synthetic_database'
    Assert-True -Condition ($localStackSmokeText -match '/api/users/me/change-password') -Label 'local_stack_completes_bootstrap_password_change'
    $apiConfigurationSmokeText = Get-Content -LiteralPath $ApiConfigurationSmokeScript -Raw
    Assert-True -Condition ($apiConfigurationSmokeText -match 'Remove-Item Env:\\IZ_CNA_ENV_FILE -ErrorAction SilentlyContinue') -Label 'api_configuration_tests_clear_smoke_environment'
    Assert-True -Condition ($apiConfigurationSmokeText -match 'IZ_CNA_LOCAL_APP_DATA_DIR=\$AppDataRoot') -Label 'api_configuration_server_root_matches_synthetic_database'
    Assert-True -Condition ($apiConfigurationSmokeText -match 'Reset-SmokeDatabase -DatabasePath \$DatabasePath') -Label 'api_configuration_resets_stale_synthetic_database'
    Assert-True -Condition ($apiConfigurationSmokeText -notmatch 'test_v2_runtime\.py') -Label 'api_configuration_avoids_removed_runtime_test'
    Assert-True -Condition ($apiConfigurationSmokeText -match 'test_v2_runtime_readiness\.py') -Label 'api_configuration_targets_active_runtime_test'
    Assert-True -Condition ($apiConfigurationSmokeText -match 'test_v2_openapi_pull\.py') -Label 'api_configuration_targets_active_openapi_test'
    Assert-True -Condition ($apiConfigurationSmokeText -match 'test_v2_harness_job_persistence\.py') -Label 'api_configuration_targets_active_harness_test'
    Assert-True -Condition ($apiConfigurationSmokeText -match '/api/users/me/change-password') -Label 'api_configuration_completes_bootstrap_password_change'
    Assert-True -Condition ($apiConfigurationSmokeText -match 'openapi_url = \"\$BaseUrl/api/api-configuration/sample-openapi\.json\"') -Label 'api_configuration_saves_local_sample_openapi_url'
    Assert-True -Condition ($apiConfigurationSmokeText -notmatch 'request_keys') -Label 'api_configuration_uses_current_openapi_response_contract'
    Assert-True -Condition ($apiConfigurationSmokeText -notmatch '\$BaseUrl/api/v2/api-harness/jobs') -Label 'api_configuration_keeps_live_harness_job_gated'
}
finally {
    foreach ($name in $environmentNames) { [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process') }
    if (Test-Path -LiteralPath $tempRoot) {
        $resolvedTemp = [IO.Path]::GetFullPath($tempRoot).TrimEnd('\')
        $systemTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
        if (-not $resolvedTemp.StartsWith($systemTemp + '\', [StringComparison]::OrdinalIgnoreCase) -or (Split-Path $resolvedTemp -Leaf) -notmatch '^iz-cna-component-[0-9a-f]{12}$') {
            throw 'LIFECYCLE_CLEANUP_SCOPE_INVALID'
        }
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
    }
}
