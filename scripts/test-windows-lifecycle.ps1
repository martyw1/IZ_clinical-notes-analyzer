[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$BackupScript = Join-Path $RepositoryRoot 'scripts\backup-local-data.ps1'
$RestoreScript = Join-Path $RepositoryRoot 'scripts\restore-local-data.ps1'
$BuildScript = Join-Path $RepositoryRoot 'scripts\build-windows-installer.ps1'
$StopScript = Join-Path $RepositoryRoot 'scripts\stop-windows-local.ps1'
$LocalStackSmokeScript = Join-Path $RepositoryRoot 'scripts\test-local-app-stack.ps1'
$ApiConfigurationSmokeScript = Join-Path $RepositoryRoot 'scripts\test-api-configuration-local.ps1'

function Assert-True {
    param([bool]$Condition, [string]$Label)
    if (-not $Condition) { throw "Assertion failed: $Label" }
    Write-Host "[pass] $Label"
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "iz-cna-lifecycle-$([Guid]::NewGuid().ToString('N'))"
$previousLocalAppData = $env:LOCALAPPDATA
$previousUserProfile = $env:USERPROFILE
$defaultBackup = $null
try {
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    $env:LOCALAPPDATA = Join-Path $tempRoot 'LocalAppData'
    $env:USERPROFILE = Join-Path $tempRoot 'UserProfile'
    $localData = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer'
    $backupOutput = Join-Path $tempRoot 'backup-output'
    New-Item -ItemType Directory -Path $localData -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $localData 'synthetic-state.txt') -Value 'before-upgrade-synthetic-state' -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $localData '.env') -Value 'SYNTHETIC_ONLY=true' -Encoding UTF8

    $backup = & $BackupScript -AssumeYes -NoStop -OutputDir $backupOutput -PassThru
    Assert-True -Condition ($LASTEXITCODE -eq 0) -Label 'encrypted_backup_command_succeeds'
    Assert-True -Condition ($backup -and (Test-Path -LiteralPath $backup.Path)) -Label 'encrypted_backup_file_created'
    Assert-True -Condition ([IO.Path]::GetExtension([string]$backup.Path) -eq '.izcnabackup') -Label 'encrypted_backup_extension'
    $backupMagic = [Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes($backup.Path), 0, 8)
    Assert-True -Condition ($backupMagic -eq 'IZCNABK2') -Label 'encrypted_backup_magic'

    Set-Content -LiteralPath (Join-Path $localData 'synthetic-state.txt') -Value 'mutated-synthetic-state' -Encoding UTF8
    & $RestoreScript -BackupPath $backup.Path -AssumeYes -NoStop
    Assert-True -Condition ($LASTEXITCODE -eq 0) -Label 'encrypted_restore_command_succeeds'
    Assert-True -Condition ((Get-Content -LiteralPath (Join-Path $localData 'synthetic-state.txt') -Raw).Trim() -eq 'before-upgrade-synthetic-state') -Label 'restore_replaces_mutated_data'
    Assert-True -Condition ((Get-Content -LiteralPath (Join-Path $localData '.env') -Raw).Trim() -eq 'SYNTHETIC_ONLY=true') -Label 'restore_preserves_encryption_material'

    $defaultBackup = & $BackupScript -AssumeYes -NoStop -PassThru
    $expectedBackupDirectory = Join-Path $env:USERPROFILE 'Documents\IZ Clinical Notes Analyzer Backups'
    Assert-True -Condition ($LASTEXITCODE -eq 0) -Label 'default_profile_backup_command_succeeds'
    Assert-True -Condition ($defaultBackup -and (Test-Path -LiteralPath $defaultBackup.Path)) -Label 'default_profile_backup_file_created'
    Assert-True -Condition ([IO.Path]::GetDirectoryName([string]$defaultBackup.Path).Equals($expectedBackupDirectory, [StringComparison]::OrdinalIgnoreCase)) -Label 'default_profile_backup_stays_inside_synthetic_documents'

    $buildText = Get-Content -LiteralPath $BuildScript -Raw
    Assert-True -Condition ($buildText -match 'Restore-IZ-Clinical-Notes-Analyzer\.cmd') -Label 'release_contains_restore_command'
    Assert-True -Condition ($buildText -match 'backup-local-data\.ps1' -and $buildText -match 'Pre-upgrade encrypted backup') -Label 'installer_performs_pre_upgrade_backup'
    Assert-True -Condition ($buildText -match 'app\\runtime') -Label 'release_requires_runtime_payload'
    Assert-True -Condition ($buildText -match '--collect-all passlib') -Label 'runtime_collects_dynamic_passlib_handlers'
    Assert-True -Condition ($buildText -match 'function Invoke-Robocopy') -Label 'installer_normalizes_robocopy_success_codes'
    Assert-True -Condition ($buildText -match '\$robocopyExitCode -gt 7') -Label 'installer_rejects_only_robocopy_failure_codes'
    Assert-True -Condition ($buildText -match '\$global:LASTEXITCODE = 0') -Label 'installer_returns_zero_after_robocopy_success'
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
    if ($defaultBackup -and (Test-Path -LiteralPath $defaultBackup.Path)) {
        Remove-Item -LiteralPath $defaultBackup.Path -Force
    }
    $env:LOCALAPPDATA = $previousLocalAppData
    $env:USERPROFILE = $previousUserProfile
    if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
}
