[CmdletBinding()]
param(
    [Alias('OutputDir')]
    [string]$OutputRoot = '',
    [switch]$NoStop,
    [switch]$AssumeYes,
    [switch]$NoPause,
    [switch]$PassThru
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
$LocalDataDir = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer'
$DocumentsDir = [Environment]::GetFolderPath('MyDocuments')
if (-not $OutputRoot) {
    if ([string]::IsNullOrWhiteSpace($DocumentsDir)) { $DocumentsDir = Join-Path $env:USERPROFILE 'Documents' }
    $OutputRoot = Join-Path $DocumentsDir 'IZ Clinical Notes Analyzer Backups'
}

function Assert-PathInside {
    param([string]$Path, [string]$Parent, [string]$Label)
    $normalizedPath = [IO.Path]::GetFullPath($Path).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    $normalizedParent = [IO.Path]::GetFullPath($Parent).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    if (-not $normalizedPath.StartsWith("$normalizedParent$([IO.Path]::DirectorySeparatorChar)", [StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label must stay inside $normalizedParent."
    }
}

function Confirm-Backup {
    if ($AssumeYes) { return $true }
    Write-Host ''
    Write-Host 'This creates an encrypted backup of local clinical data, configuration, and encryption material.' -ForegroundColor Yellow
    Write-Host 'It can be restored only by this Windows user account. Store it according to R3 policy.'
    return ((Read-Host 'Type BACKUP to create the encrypted backup').Trim() -eq 'BACKUP')
}

function New-RandomBytes([int]$Length) {
    $bytes = New-Object byte[] $Length
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return $bytes
}

function Write-UInt32BigEndian([IO.Stream]$Stream, [uint32]$Value) {
    $bytes = [BitConverter]::GetBytes($Value)
    if ([BitConverter]::IsLittleEndian) { [Array]::Reverse($bytes) }
    $Stream.Write($bytes, 0, $bytes.Length)
}

if (-not (Test-Path -LiteralPath $LocalDataDir)) { throw "Local app data was not found at $LocalDataDir. Start the app once before creating a backup." }
if (-not (Confirm-Backup)) { Write-Host 'Backup cancelled.'; exit 1 }

if (-not $NoStop) {
    $stopScript = Join-Path $PSScriptRoot 'stop-windows-local.ps1'
    if (Test-Path -LiteralPath $stopScript) { & $stopScript -NoRestartPrompt -NoPause }
}

New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupPath = Join-Path $OutputRoot "IZ-Clinical-Notes-Analyzer-backup-$stamp.izcnabackup"
$tempParent = [IO.Path]::GetTempPath()
$tempRoot = Join-Path $tempParent "iz-cna-backup-$([Guid]::NewGuid().ToString('N'))"
Assert-PathInside -Path $tempRoot -Parent $tempParent -Label 'Temporary backup folder'

try {
    $stageRoot = Join-Path $tempRoot 'stage'
    $stageData = Join-Path $stageRoot 'IZ Clinical Notes Analyzer'
    $plainZip = Join-Path $tempRoot 'payload.zip'
    New-Item -ItemType Directory -Path $stageData -Force | Out-Null
    robocopy $LocalDataDir $stageData /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "Backup copy failed with robocopy exit code $LASTEXITCODE." }
    [ordered]@{
        format = 'iz-cna-local-data-v2'
        created_at = (Get-Date).ToUniversalTime().ToString('o')
        source = 'local-app-data'
        restore_scope = 'same-windows-user'
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stageRoot 'backup-manifest.json') -Encoding UTF8
    Compress-Archive -Path (Join-Path $stageRoot '*') -DestinationPath $plainZip -CompressionLevel Optimal

    $protectedKey = [Security.Cryptography.ProtectedData]::Protect((New-RandomBytes 64), $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
    $rawKey = [Security.Cryptography.ProtectedData]::Unprotect($protectedKey, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
    $encKey = New-Object byte[] 32
    $macKey = New-Object byte[] 32
    [Array]::Copy($rawKey, 0, $encKey, 0, 32)
    [Array]::Copy($rawKey, 32, $macKey, 0, 32)
    $iv = New-RandomBytes 16
    $plainHash = (Get-FileHash -LiteralPath $plainZip -Algorithm SHA256).Hash.ToLowerInvariant()
    $header = [ordered]@{
        format = 'IZCNABK2'
        version = 2
        created_at = (Get-Date).ToUniversalTime().ToString('o')
        encryption = 'aes-256-cbc-hmac-sha256-dpapi-current-user-v1'
        protected_key = [Convert]::ToBase64String($protectedKey)
        iv = [Convert]::ToBase64String($iv)
        plaintext_sha256 = $plainHash
        plaintext_bytes = (Get-Item -LiteralPath $plainZip).Length
    }
    $headerBytes = [Text.Encoding]::UTF8.GetBytes(($header | ConvertTo-Json -Compress))
    $magic = [Text.Encoding]::ASCII.GetBytes('IZCNABK2')
    $output = [IO.File]::Open($backupPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $output.Write($magic, 0, $magic.Length)
        Write-UInt32BigEndian -Stream $output -Value $headerBytes.Length
        $output.Write($headerBytes, 0, $headerBytes.Length)
        $aes = New-Object Security.Cryptography.AesManaged
        $aes.KeySize = 256; $aes.Mode = [Security.Cryptography.CipherMode]::CBC; $aes.Padding = [Security.Cryptography.PaddingMode]::PKCS7
        $aes.Key = $encKey; $aes.IV = $iv
        $encryptor = $aes.CreateEncryptor()
        $crypto = New-Object Security.Cryptography.CryptoStream($output, $encryptor, [Security.Cryptography.CryptoStreamMode]::Write, $true)
        $input = [IO.File]::OpenRead($plainZip)
        try { $input.CopyTo($crypto) } finally { $input.Dispose(); $crypto.FlushFinalBlock(); $crypto.Dispose(); $encryptor.Dispose(); $aes.Dispose() }
    } finally { $output.Dispose() }
    $hmac = [Security.Cryptography.HMACSHA256]::new([byte[]]$macKey)
    try { $tag = $hmac.ComputeHash([IO.File]::ReadAllBytes($backupPath)) } finally { $hmac.Dispose() }
    $append = [IO.File]::Open($backupPath, [IO.FileMode]::Append, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $append.Write($tag, 0, $tag.Length) } finally { $append.Dispose() }
} finally {
    if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
}

$result = [pscustomobject]@{ Path = $backupPath; Encryption = 'DPAPI current-user + AES-256-CBC + HMAC-SHA-256'; RestoreScope = 'same Windows user' }
Write-Host "Encrypted backup created: $backupPath" -ForegroundColor Green
Write-Host 'The backup is encrypted for this Windows user account and must be restored with Restore IZ Clinical Notes Analyzer.'
if ($PassThru) { Write-Output $result }
exit 0
