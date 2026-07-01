[CmdletBinding()]
param(
    [Alias('OutputRoot')]
    [string]$OutputDir = '',
    [string]$AppUrl = 'http://127.0.0.1:8000',
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$LocalDataDir = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer'
if (-not $OutputDir) {
    $OutputDir = Join-Path $LocalDataDir 'diagnostics'
}

function Redact-Text {
    param([AllowNull()][object]$Value)
    if ($null -eq $Value) { return '' }
    $text = [string]$Value
    if ($env:USERPROFILE) {
        $text = $text.Replace($env:USERPROFILE, '%USERPROFILE%')
    }
    if ($env:LOCALAPPDATA) {
        $text = $text.Replace($env:LOCALAPPDATA, '%LOCALAPPDATA%')
    }
    if ($env:APPDATA) {
        $text = $text.Replace($env:APPDATA, '%APPDATA%')
    }
    $text = $text -replace '(?im)^(\s*[^=\r\n]*(password|secret|token|api[_-]?key|client[_-]?id|credential|connection|string|dsn)[^=\r\n]*\s*=\s*).+$', '$1[redacted]'
    $text = $text -replace '(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]+', '$1[redacted]'
    $text = $text -replace '(?i)("?(password|secret|token|api_key|client_secret|client_id)"?\s*[:=]\s*)("[^"]*"|''[^'']*''|[^,}\s]+)', '$1[redacted]'
    $text = $text -replace '(?im)^\s*(patient|client)\s+name\s*[:=].+$', 'Patient name: [redacted]'
    $text = $text -replace '(?im)^\s*(street|address|city|state|zip|postal|phone|email|dob|ssn)\b.*$', '[direct identifier redacted]'
    $text = $text -replace '\b\d{3}-\d{2}-\d{4}\b', '[ssn redacted]'
    $text = $text -replace '\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', '[email redacted]'
    return $text
}

function Write-RedactedFile {
    param(
        [string]$Path,
        [AllowNull()][object]$Content
    )
    Redact-Text $Content | Set-Content -LiteralPath $Path -Encoding UTF8
}

function New-SafeBundleName {
    param([string]$Path)
    $redactedPath = Redact-Text $Path
    $safe = $redactedPath -replace '%USERPROFILE%', 'USERPROFILE'
    $safe = $safe -replace '%LOCALAPPDATA%', 'LOCALAPPDATA'
    $safe = $safe -replace '%APPDATA%', 'APPDATA'
    $safe = $safe -replace '[^A-Za-z0-9_.-]+', '_'
    $safe = $safe.Trim('_')
    if ([string]::IsNullOrWhiteSpace($safe)) { $safe = 'item' }

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($redactedPath)
        $hash = ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').Substring(0, 12).ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }

    if ($safe.Length -gt 72) {
        $safe = $safe.Substring(0, 72).Trim('_', '.', '-')
    }
    return "$safe-$hash"
}

function Invoke-LocalJson {
    param([string]$Path)
    try {
        $response = Invoke-RestMethod -Method Get -Uri "$AppUrl$Path" -TimeoutSec 4
        return $response | ConvertTo-Json -Depth 12
    } catch {
        return "Unavailable: $($_.Exception.Message)"
    }
}

function Get-DirectorySummary {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return [ordered]@{ exists = $false; path = (Redact-Text $Path) }
    }
    $files = Get-ChildItem -LiteralPath $Path -File -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object {
            $_.FullName -notmatch '\\uploads(\\|$)' -and
            $_.Extension -notin @('.sqlite', '.sqlite3', '.db') -and
            $_.Name -ne '.env'
        }
    $topLevel = Get-ChildItem -LiteralPath $Path -Force -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty Name
    return [ordered]@{
        exists = $true
        path = (Redact-Text $Path)
        top_level_entries = @($topLevel)
        non_upload_file_count = @($files).Count
        non_upload_total_bytes = (@($files) | Measure-Object -Property Length -Sum).Sum
        uploads_excluded = $true
        databases_excluded = $true
        env_values_redacted = $true
    }
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$BundleDir = Join-Path $OutputDir "iz-cna-diagnostics-$Stamp"
$LogOutDir = Join-Path $BundleDir 'logs'
New-Item -ItemType Directory -Path $BundleDir, $LogOutDir -Force | Out-Null

$versionFile = Join-Path $RootDir 'VERSION.json'
$versionText = if (Test-Path -LiteralPath $versionFile) { Get-Content -LiteralPath $versionFile -Raw } else { 'VERSION.json not found.' }
Write-RedactedFile -Path (Join-Path $BundleDir 'version-file.json') -Content $versionText
Write-RedactedFile -Path (Join-Path $BundleDir 'api-version.json') -Content (Invoke-LocalJson '/api/version')
Write-RedactedFile -Path (Join-Path $BundleDir 'api-health.json') -Content (Invoke-LocalJson '/api/health')
Write-RedactedFile -Path (Join-Path $BundleDir 'api-readiness.json') -Content (Invoke-LocalJson '/api/readiness')

$systemInfo = [ordered]@{
    generated_at = (Get-Date).ToUniversalTime().ToString('o')
    app_url = $AppUrl
    repo_path = (Redact-Text $RootDir)
    local_data_dir = (Redact-Text $LocalDataDir)
    powershell = $PSVersionTable.PSVersion.ToString()
    dotnet_os = [System.Runtime.InteropServices.RuntimeInformation]::OSDescription
    process_architecture = [System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString()
}
try {
    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
    $systemInfo.windows_caption = $os.Caption
    $systemInfo.windows_version = $os.Version
    $systemInfo.windows_build = $os.BuildNumber
} catch {
    $systemInfo.windows_info = "Unavailable: $($_.Exception.Message)"
}
Write-RedactedFile -Path (Join-Path $BundleDir 'system.json') -Content ($systemInfo | ConvertTo-Json -Depth 4)

$envSummary = Get-ChildItem Env: |
    Where-Object { $_.Name -match '^(IZ_CNA|DATABASE|SECRET|DATA_ENCRYPTION|BOOTSTRAP|RESET_BOOTSTRAP|LOCALAPPDATA|APPDATA|PYTHON|NODE|PATH)' } |
    Sort-Object Name |
    ForEach-Object {
        [ordered]@{
            name = $_.Name
            configured = -not [string]::IsNullOrWhiteSpace($_.Value)
            value = if ($_.Name -match '(PATH|LOCALAPPDATA|APPDATA|PYTHON|NODE)') { Redact-Text $_.Value } else { '[redacted]' }
        }
    }
Write-RedactedFile -Path (Join-Path $BundleDir 'environment-summary.json') -Content ($envSummary | ConvertTo-Json -Depth 5)

$directorySummary = [ordered]@{
    repo = Get-DirectorySummary -Path $RootDir
    local_data = Get-DirectorySummary -Path $LocalDataDir
}
Write-RedactedFile -Path (Join-Path $BundleDir 'directory-summary.json') -Content ($directorySummary | ConvertTo-Json -Depth 6)

$envFiles = @(
    (Join-Path $RootDir '.env'),
    (Join-Path $LocalDataDir '.env')
) | Select-Object -Unique
foreach ($envFile in $envFiles) {
    if (Test-Path -LiteralPath $envFile) {
        $safeName = New-SafeBundleName -Path $envFile
        Write-RedactedFile -Path (Join-Path $BundleDir "$safeName.redacted.txt") -Content (Get-Content -LiteralPath $envFile -Raw)
    }
}

$logDirs = @(
    (Join-Path $LocalDataDir 'logs'),
    (Join-Path $RootDir 'logs')
) | Select-Object -Unique
foreach ($logDir in $logDirs) {
    if (-not (Test-Path -LiteralPath $logDir)) { continue }
    Get-ChildItem -LiteralPath $logDir -File -Force -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 10 |
        ForEach-Object {
            $safeName = New-SafeBundleName -Path $_.FullName
            $tail = Get-Content -LiteralPath $_.FullName -Tail 200 -ErrorAction SilentlyContinue
            Write-RedactedFile -Path (Join-Path $LogOutDir "$safeName.txt") -Content ($tail -join [Environment]::NewLine)
        }
}

@"
IZ Clinical Notes Analyzer diagnostics bundle

This bundle is intended for R3/internal support triage. It excludes uploaded clinical documents, SQLite databases, generated reports, and raw .env values. Any included log and environment text is passed through redaction before packaging.

Bundle generated: $((Get-Date).ToString('u'))
Local app URL checked: $AppUrl
"@ | Set-Content -LiteralPath (Join-Path $BundleDir 'README.txt') -Encoding UTF8

$ZipPath = Join-Path $OutputDir "iz-cna-diagnostics-$Stamp.zip"
if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Compress-Archive -Path (Join-Path $BundleDir '*') -DestinationPath $ZipPath
Write-Host "Diagnostics bundle created: $ZipPath"
