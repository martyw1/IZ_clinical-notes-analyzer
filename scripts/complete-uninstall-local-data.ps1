[CmdletBinding()]
param(
    [string]$InstalledAppRoot = '',
    [switch]$AssumeYes,
    [switch]$NoPause,
    [switch]$NonInteractive,
    [string]$ResultPath = '',
    [int]$DelaySeconds = 0
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Get-NormalizedCompatibilityPath {
    param([string]$Path)
    return [IO.Path]::GetFullPath($Path).TrimEnd('\')
}

$exitCode = 20
try {
    $expectedInstallRoot = Join-Path $env:LOCALAPPDATA 'Programs\IZ Clinical Notes Analyzer'
    if ($InstalledAppRoot) {
        $requested = Get-NormalizedCompatibilityPath $InstalledAppRoot
        $expected = Get-NormalizedCompatibilityPath $expectedInstallRoot
        if (-not $requested.Equals($expected, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'LEGACY_INSTALL_ROOT_REJECTED'
        }
    }
    if ($DelaySeconds -ne 0) { throw 'DETACHED_REMOVAL_NOT_SUPPORTED' }

    $dispatcher = Join-Path $PSScriptRoot 'installer\maintenance-windows.ps1'
    if (-not (Test-Path -LiteralPath $dispatcher -PathType Leaf)) {
        throw 'MAINTENANCE_DISPATCHER_MISSING'
    }
    $scriptPath = Get-NormalizedCompatibilityPath $PSCommandPath
    $installRoot = Get-NormalizedCompatibilityPath $expectedInstallRoot
    if ($scriptPath.StartsWith($installRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'INSTALLED_WAITER_NOT_SUPPORTED'
    }

    Write-Host ''
    Write-Host 'Complete uninstall removes app files and app-owned local data for this Windows user.' -ForegroundColor Yellow
    Write-Host 'External backups, downloaded packages, and other Windows profiles remain outside its scope.'
    if ($AssumeYes) {
        Write-Host 'The legacy AssumeYes flag does not authorize local-data deletion.' -ForegroundColor Yellow
    }

    $arguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $dispatcher, '-Action', 'RemoveData', '-NoPause')
    if ($NonInteractive) { $arguments += '-NonInteractive' }
    if ($ResultPath) { $arguments += @('-ResultPath', $ResultPath) }
    & powershell.exe @arguments
    $exitCode = [int]$LASTEXITCODE
} catch {
    Write-Host '[fail] Complete uninstall could not start safely.' -ForegroundColor Red
    $exitCode = 20
}

if (-not $NoPause) {
    Write-Host ''
    Read-Host 'Press Enter to close' | Out-Null
}
exit $exitCode
