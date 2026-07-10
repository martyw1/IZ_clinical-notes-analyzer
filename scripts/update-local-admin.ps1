[CmdletBinding()]
param(
    [string]$Value = '',
    [string]$AppDataRoot = (Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer')
)

$ErrorActionPreference = 'Stop'
$EnvFile = Join-Path $AppDataRoot '.env'
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$PythonExe = Join-Path $RootDir 'backend\.venv\Scripts\python.exe'

if (!(Test-Path $EnvFile)) {
    throw "Local settings file was not found at $EnvFile. Start the app once to create local settings, then run this utility again."
}

if (!$Value) {
    $secureValue = Read-Host 'Enter a temporary administrator password' -AsSecureString
    $credential = [System.Net.NetworkCredential]::new('', $secureValue)
    $Value = $credential.Password
}
if (!(Test-Path $PythonExe)) {
    throw "Backend runtime was not found at $PythonExe."
}
$env:IZ_CNA_ENV_FILE = $EnvFile
$env:IZ_CNA_LOCAL_APP_DATA_DIR = $AppDataRoot
$env:PYTHONPATH = Join-Path $RootDir 'backend'
$Value | & $PythonExe -m app.v2.local_admin_recovery
if ($LASTEXITCODE -ne 0) {
    throw 'Local administrator recovery failed.'
}

Write-Host ''
Write-Host 'Local administrator recovery completed and audited.' -ForegroundColor Green
Write-Host 'Username: admin'
Write-Host ''
Write-Host 'Sign in with the temporary password, then complete the required password change.'
