[CmdletBinding()]
param(
    [string]$Value = ''
)

$ErrorActionPreference = 'Stop'
$AppDataRoot = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer'
$EnvFile = Join-Path $AppDataRoot '.env'

function New-RandomValue {
    param([int]$Length = 24)
    $alphabet = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789-_!@#$%+=' 
    $bytes = New-Object byte[] $Length
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) }
    finally {
        if ($rng -and ($rng -is [System.IDisposable])) { $rng.Dispose() }
    }
    return -join ($bytes | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
}

if (!(Test-Path $EnvFile)) {
    throw "Local settings file was not found at $EnvFile. Start the app once to create local settings, then run this utility again."
}

if (!$Value) {
    $Value = New-RandomValue -Length 24
}

$lines = Get-Content -Path $EnvFile
$foundValue = $false
$foundReset = $false
$updated = foreach ($line in $lines) {
    if ($line -match '^BOOTSTRAP_ADMIN_PASSWORD=') {
        $foundValue = $true
        "BOOTSTRAP_ADMIN_PASSWORD=$Value"
    }
    elseif ($line -match '^RESET_BOOTSTRAP_ADMIN_ON_STARTUP=') {
        $foundReset = $true
        'RESET_BOOTSTRAP_ADMIN_ON_STARTUP=true'
    }
    else { $line }
}
if (-not $foundValue) { $updated += "BOOTSTRAP_ADMIN_PASSWORD=$Value" }
if (-not $foundReset) { $updated += 'RESET_BOOTSTRAP_ADMIN_ON_STARTUP=true' }

$backup = "$EnvFile.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
Copy-Item -Path $EnvFile -Destination $backup -Force
$updated | Set-Content -Path $EnvFile -Encoding UTF8

Write-Host ''
Write-Host 'Local admin access value updated.' -ForegroundColor Green
Write-Host 'Username: admin'
Write-Host "New value: $Value"
Write-Host ''
Write-Host 'Restart the app, then sign in locally as admin.'
Write-Host "Backup created: $backup"
