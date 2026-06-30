[CmdletBinding()]
param(
    [string]$OutputRoot = '',
    [switch]$NoStop,
    [switch]$AssumeYes
)

$ErrorActionPreference = 'Stop'
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$LocalDataDir = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer'
$DocumentsDir = [Environment]::GetFolderPath('MyDocuments')
if (-not $OutputRoot) {
    if ([string]::IsNullOrWhiteSpace($DocumentsDir)) {
        $DocumentsDir = Join-Path $env:USERPROFILE 'Documents'
    }
    $OutputRoot = Join-Path $DocumentsDir 'IZ Clinical Notes Analyzer Backups'
}

function Get-NormalizedPath {
    param([string]$Path)
    $trimChars = [char[]]@([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
    return [System.IO.Path]::GetFullPath($Path).TrimEnd($trimChars)
}

function Assert-PathInside {
    param(
        [string]$Path,
        [string]$Parent,
        [string]$Label
    )
    $normalizedPath = Get-NormalizedPath -Path $Path
    $normalizedParent = Get-NormalizedPath -Path $Parent
    $comparison = [System.StringComparison]::OrdinalIgnoreCase
    $separator = [System.IO.Path]::DirectorySeparatorChar
    if (-not $normalizedPath.StartsWith("$normalizedParent$separator", $comparison)) {
        throw "$Label must be inside $normalizedParent; resolved to $normalizedPath"
    }
}

function Confirm-Backup {
    if ($AssumeYes) { return $true }
    Write-Host ''
    Write-Host 'This backup can contain clinical data, app settings, saved API configuration, audit logs, and encryption material.' -ForegroundColor Yellow
    Write-Host 'Keep the backup zip encrypted and access-controlled according to R3 policy.'
    Write-Host ''
    $answer = Read-Host 'Type BACKUP to create the backup'
    return ($answer.Trim() -eq 'BACKUP')
}

if (-not (Test-Path -LiteralPath $LocalDataDir)) {
    throw "Local app data was not found at $LocalDataDir. Start the app once before creating a backup."
}

if (-not (Confirm-Backup)) {
    Write-Host 'Backup cancelled.'
    exit 1
}

if (-not $NoStop) {
    $stopScript = Join-Path $PSScriptRoot 'stop-windows-local.ps1'
    if (Test-Path -LiteralPath $stopScript) {
        Write-Host 'Stopping any running local app process before backup...'
        & $stopScript -NoRestartPrompt -NoPause
    }
}

New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$zipPath = Join-Path $OutputRoot "IZ-Clinical-Notes-Analyzer-backup-$stamp.zip"
$tempParent = [System.IO.Path]::GetTempPath()
$tempRoot = Join-Path $tempParent "iz-cna-backup-$stamp"
Assert-PathInside -Path $tempRoot -Parent $tempParent -Label 'Temporary backup folder'

if (Test-Path -LiteralPath $tempRoot) {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force
}

try {
    $stageDir = Join-Path $tempRoot 'IZ Clinical Notes Analyzer'
    New-Item -ItemType Directory -Path $stageDir -Force | Out-Null

    robocopy $LocalDataDir $stageDir /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "Backup copy failed with robocopy exit code $LASTEXITCODE"
    }

@"
IZ Clinical Notes Analyzer backup

Created: $((Get-Date).ToString('u'))
Source local data folder: $LocalDataDir
App folder at backup time: $RootDir

This backup can contain clinical data, local SQLite data, encrypted uploads,
audit logs, app settings, saved API configuration, and encryption material.
Keep it encrypted and access-controlled. The .env file, SQLite database, and
encrypted uploads must stay together for restore.
"@ | Set-Content -LiteralPath (Join-Path $tempRoot 'README-BACKUP.txt') -Encoding UTF8

    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    Compress-Archive -Path (Join-Path $tempRoot '*') -DestinationPath $zipPath
}
finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Assert-PathInside -Path $tempRoot -Parent $tempParent -Label 'Temporary backup folder'
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}

Write-Host ''
Write-Host "Backup created: $zipPath" -ForegroundColor Green
Write-Host 'Store this file securely. It may contain regulated clinical data and local access material.'
