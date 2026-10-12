[CmdletBinding()]
param([string]$BackupPath = '')
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$python = Join-Path $repo 'backend\.venv\Scripts\python.exe'
if (-not $BackupPath) {
    Add-Type -AssemblyName System.Windows.Forms
    $picker = New-Object Windows.Forms.OpenFileDialog
    $picker.Filter = 'IZ portable ZIP backups (*.zip)|*.zip'
    $picker.Title = 'Choose the complete IZ local-data backup'
    if ($picker.ShowDialog() -ne 'OK') { exit 0 }
    $BackupPath = $picker.FileName
}
$profileRoot = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer'
Write-Host 'This restores the entire profile, including accounts, passwords, settings and records, to the backup date.'
Write-Host 'The current profile will be preserved alongside it. Close the app and wait for imports/uploads to finish.'
if ((Read-Host 'Type RESTORE to continue') -cne 'RESTORE') { exit 0 }
$statusRoot = Join-Path $env:LOCALAPPDATA 'IZ Backup Status'
New-Item -ItemType Directory -Path $statusRoot -Force | Out-Null
$lock = [IO.File]::Open((Join-Path $statusRoot 'backup.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
try {
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'stop-windows-local.ps1') -NoRestartPrompt -NoPause
if ($LASTEXITCODE -ne 0) { throw 'App stop failed' }
if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { throw 'App still running' }
$preserved = $profileRoot + '-before-restore-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$staged = $profileRoot + '-restored-' + [guid]::NewGuid().ToString('N')
& $python (Join-Path $PSScriptRoot 'portable_data_zip.py') restore --archive $BackupPath --root $staged --app-check
if ($LASTEXITCODE -ne 0) { throw 'Archive validation failed; current data was not replaced' }
# All move targets are explicit siblings under current-user LocalAppData, never cloud paths.
foreach ($path in @($profileRoot,$preserved,$staged)) {
    if ((Split-Path ([IO.Path]::GetFullPath($path)) -Parent) -ne [IO.Path]::GetFullPath($env:LOCALAPPDATA)) { throw 'Unexpected restore path' }
}
if (Test-Path -LiteralPath $preserved) { throw 'Preservation destination exists' }
if (Test-Path -LiteralPath $profileRoot) { Move-Item -LiteralPath $profileRoot -Destination $preserved }
try { Move-Item -LiteralPath $staged -Destination $profileRoot }
catch {
    if (-not (Test-Path -LiteralPath $profileRoot) -and (Test-Path -LiteralPath $preserved)) { Move-Item -LiteralPath $preserved -Destination $profileRoot }
    throw
}
Write-Host 'Restore completed. Start the app, use the password valid at the backup date, and check your records and uploads.'
} finally { $lock.Dispose() }
[void](Read-Host 'Press Enter to close')
