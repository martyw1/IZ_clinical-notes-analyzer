[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Destination,
    [switch]$InstallSchedule,
    [switch]$NoPause
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$python = Join-Path $repo 'backend\.venv\Scripts\python.exe'
$profileRoot = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer'
$statusRoot = Join-Path $env:LOCALAPPDATA 'IZ Backup Status'
New-Item -ItemType Directory -Path $statusRoot -Force | Out-Null
$statusPath = Join-Path $statusRoot 'last-result.json'
if ($InstallSchedule) {
    $ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -Destination "' + $Destination + '" -NoPause'
    $action = New-ScheduledTaskAction -Execute $ps -Argument $arguments -WorkingDirectory $repo
    $trigger = New-ScheduledTaskTrigger -Daily -DaysInterval 3 -At '6:00PM'
    $principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)
    Register-ScheduledTask -TaskName 'IZ Local Data ZIP Backup' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Every three days: verified unencrypted local profile ZIP copied to OneDrive. Runs only while this user is signed in.' -Force | Out-Null
    Write-Host 'Backup task installed: every 3 days at 6 PM, while this user is signed in.'
    exit 0
}
$lock = $null
$wasRunning = $false
$stopped = $false
$code = 1
try {
    $lock = [IO.File]::Open((Join-Path $statusRoot 'backup.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    if (-not (Test-Path -LiteralPath $python)) { throw 'Runtime unavailable' }
    & $python (Join-Path $PSScriptRoot 'portable_data_zip.py') idle --root $profileRoot
    if ($LASTEXITCODE -ne 0) { throw 'Profile is not idle' }
    # Never interrupt an import or use an unknown service on the expected port.
    try {
        $health = Invoke-WebRequest 'http://127.0.0.1:8000/api/health' -UseBasicParsing -TimeoutSec 3
        $wasRunning = $health.StatusCode -eq 200
    } catch { }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'stop-windows-local.ps1') -NoRestartPrompt -NoPause
    if ($LASTEXITCODE -ne 0) { throw 'Stop failed' }
    $stopped = $true
    if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { throw 'Service still running' }
    $version = (Get-Content -LiteralPath (Join-Path $repo 'VERSION') -Raw).Trim()
    & $python (Join-Path $PSScriptRoot 'portable_data_zip.py') backup --root $profileRoot --destination $Destination --version $version --app-check
    if ($LASTEXITCODE -ne 0) { throw 'Backup failed' }
    @{status='success';time_utc=[DateTime]::UtcNow.ToString('o');cloud_sync_verified=$false} | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
    Write-Host 'Verified ZIP copied to the OneDrive folder. Check OneDrive for completed cloud synchronization.'
    $code = 0
} catch {
    @{status='failed';time_utc=[DateTime]::UtcNow.ToString('o');cloud_sync_verified=$false} | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
    Write-Host 'Backup failed; do not rely on a new archive. Contact R3 support.' -ForegroundColor Red
} finally {
    if ($wasRunning -and $stopped) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'start-windows-local.ps1') -SkipFrontendBuild -NoBrowser -AssumeYes -NoPause
        if ($LASTEXITCODE -ne 0) { $code = 1; Write-Host 'App restart failed; use the Start desktop shortcut.' -ForegroundColor Red }
    }
    if ($lock) { $lock.Dispose() }
}
if (-not $NoPause) { [void](Read-Host 'Press Enter to close') }
exit $code
