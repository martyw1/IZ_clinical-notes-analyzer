[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$BackupScript = Join-Path $RepositoryRoot 'scripts\backup-local-data.ps1'
$RestoreScript = Join-Path $RepositoryRoot 'scripts\restore-local-data.ps1'
$BuildScript = Join-Path $RepositoryRoot 'scripts\build-windows-installer.ps1'

function Assert-True {
    param([bool]$Condition, [string]$Label)
    if (-not $Condition) { throw "Assertion failed: $Label" }
    Write-Host "[pass] $Label"
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "iz-cna-lifecycle-$([Guid]::NewGuid().ToString('N'))"
$previousLocalAppData = $env:LOCALAPPDATA
try {
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    $env:LOCALAPPDATA = Join-Path $tempRoot 'LocalAppData'
    $localData = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer'
    $backupOutput = Join-Path $tempRoot 'backup-output'
    New-Item -ItemType Directory -Path $localData -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $localData 'synthetic-state.txt') -Value 'before-upgrade-synthetic-state' -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $localData '.env') -Value 'SYNTHETIC_ONLY=true' -Encoding UTF8

    $backup = & $BackupScript -AssumeYes -NoStop -OutputDir $backupOutput -PassThru
    Assert-True -Condition ($LASTEXITCODE -eq 0) -Label 'encrypted_backup_command_succeeds'
    Assert-True -Condition ($backup -and (Test-Path -LiteralPath $backup.Path)) -Label 'encrypted_backup_file_created'
    Assert-True -Condition ([IO.Path]::GetExtension([string]$backup.Path) -eq '.izcnabackup') -Label 'encrypted_backup_extension'
    Assert-True -Condition ((Get-Content -LiteralPath $backup.Path -Encoding Byte -TotalCount 8 | ForEach-Object { [char]$_ }) -join '' -eq 'IZCNABK2') -Label 'encrypted_backup_magic'

    Set-Content -LiteralPath (Join-Path $localData 'synthetic-state.txt') -Value 'mutated-synthetic-state' -Encoding UTF8
    & $RestoreScript -BackupPath $backup.Path -AssumeYes -NoStop
    Assert-True -Condition ($LASTEXITCODE -eq 0) -Label 'encrypted_restore_command_succeeds'
    Assert-True -Condition ((Get-Content -LiteralPath (Join-Path $localData 'synthetic-state.txt') -Raw).Trim() -eq 'before-upgrade-synthetic-state') -Label 'restore_replaces_mutated_data'
    Assert-True -Condition ((Get-Content -LiteralPath (Join-Path $localData '.env') -Raw).Trim() -eq 'SYNTHETIC_ONLY=true') -Label 'restore_preserves_encryption_material'

    $buildText = Get-Content -LiteralPath $BuildScript -Raw
    Assert-True -Condition ($buildText -match 'Restore-IZ-Clinical-Notes-Analyzer\.cmd') -Label 'release_contains_restore_command'
    Assert-True -Condition ($buildText -match 'backup-local-data\.ps1' -and $buildText -match 'Pre-upgrade encrypted backup') -Label 'installer_performs_pre_upgrade_backup'
    Assert-True -Condition ($buildText -match 'app\\runtime') -Label 'release_requires_runtime_payload'
}
finally {
    $env:LOCALAPPDATA = $previousLocalAppData
    if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
}
