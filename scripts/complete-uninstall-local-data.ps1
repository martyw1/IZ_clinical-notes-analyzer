[CmdletBinding()]
param(
    [string]$InstalledAppRoot = '',
    [switch]$AssumeYes,
    [switch]$NoPause,
    [int]$DelaySeconds = 0
)

$ErrorActionPreference = 'Stop'
if ($DelaySeconds -gt 0) {
    Start-Sleep -Seconds $DelaySeconds
}
$InstallRoot = if ($InstalledAppRoot) { $InstalledAppRoot } else { Join-Path $env:LOCALAPPDATA 'Programs\IZ Clinical Notes Analyzer' }
$ExpectedInstallRoot = Join-Path $env:LOCALAPPDATA 'Programs\IZ Clinical Notes Analyzer'
$LocalDataDir = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer'
$StartMenuDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\IZ Clinical Notes Analyzer'
$DesktopDir = [Environment]::GetFolderPath('Desktop')

function Get-NormalizedPath {
    param([string]$Path)
    $trimChars = [char[]]@([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
    return [System.IO.Path]::GetFullPath($Path).TrimEnd($trimChars)
}

function Assert-ExpectedPath {
    param(
        [string]$Path,
        [string]$Expected,
        [string]$Label
    )
    $normalizedPath = Get-NormalizedPath -Path $Path
    $normalizedExpected = Get-NormalizedPath -Path $Expected
    if (-not $normalizedPath.Equals($normalizedExpected, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label resolved to $normalizedPath, expected $normalizedExpected"
    }
}

function Confirm-Removal {
    if ($AssumeYes) { return $true }
    Write-Host ''
    Write-Host 'This will remove the app files, shortcuts, and ALL local IZ Clinical Notes Analyzer data for this Windows user.' -ForegroundColor Yellow
    Write-Host 'That includes the local database, encrypted uploads, app settings, saved API configuration, audit logs, backups in the app data folder, and local access material.'
    Write-Host 'Create a backup first unless R3 intentionally wants this laptop clean.'
    Write-Host ''
    $answer = Read-Host 'Type REMOVE IZ DATA to continue'
    return ($answer.Trim() -eq 'REMOVE IZ DATA')
}

Assert-ExpectedPath -Path $InstallRoot -Expected $ExpectedInstallRoot -Label 'Install folder'
Assert-ExpectedPath -Path $LocalDataDir -Expected (Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer') -Label 'Local data folder'
Assert-ExpectedPath -Path $StartMenuDir -Expected (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\IZ Clinical Notes Analyzer') -Label 'Start Menu folder'

if (-not (Confirm-Removal)) {
    Write-Host 'Complete uninstall cancelled.'
    exit 1
}

$normalizedInstallRoot = Get-NormalizedPath -Path $InstallRoot
if ($PSCommandPath) {
    $normalizedScriptPath = Get-NormalizedPath -Path $PSCommandPath
    $separator = [System.IO.Path]::DirectorySeparatorChar
    if ($normalizedScriptPath.StartsWith("$normalizedInstallRoot$separator", [System.StringComparison]::OrdinalIgnoreCase)) {
        $helperPath = Join-Path ([System.IO.Path]::GetTempPath()) "iz-cna-complete-uninstall-$([System.Guid]::NewGuid().ToString('N')).ps1"
        Copy-Item -LiteralPath $PSCommandPath -Destination $helperPath -Force
        $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$helperPath`" -InstalledAppRoot `"$InstallRoot`" -AssumeYes -NoPause -DelaySeconds 2"
        Start-Process -FilePath 'powershell.exe' -ArgumentList $argList -WindowStyle Hidden
        Write-Host 'Complete uninstall cleanup started. App files and local app data will be removed in a few seconds.'
        exit 0
    }
}

$stopScript = Join-Path $InstallRoot 'scripts\stop-windows-local.ps1'
if (Test-Path -LiteralPath $stopScript) {
    Write-Host 'Stopping any running local app process...'
    & $stopScript -NoRestartPrompt -NoPause
}
Set-Location ([System.IO.Path]::GetTempPath())

$desktopShortcuts = @(
    'IZ Clinical Notes Analyzer.lnk',
    'IZ Clinical Notes Analyzer Diagnostics.lnk',
    'IZ Clinical Notes Analyzer Backup.lnk'
) | ForEach-Object { Join-Path $DesktopDir $_ }

foreach ($shortcut in $desktopShortcuts) {
    if (Test-Path -LiteralPath $shortcut) {
        Remove-Item -LiteralPath $shortcut -Force
    }
}

if (Test-Path -LiteralPath $StartMenuDir) {
    Remove-Item -LiteralPath $StartMenuDir -Recurse -Force
}

if (Test-Path -LiteralPath $InstallRoot) {
    Remove-Item -LiteralPath $InstallRoot -Recurse -Force
}

if (Test-Path -LiteralPath $LocalDataDir) {
    Remove-Item -LiteralPath $LocalDataDir -Recurse -Force
}

Write-Host ''
Write-Host 'Complete uninstall finished. App files, shortcuts, and local app data were removed for this Windows user.' -ForegroundColor Green
