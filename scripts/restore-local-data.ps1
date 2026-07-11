[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,
    [switch]$NoStop,
    [switch]$AssumeYes,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
$LocalDataDir = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer'

function Read-UInt32BigEndian([IO.Stream]$Stream) {
    $bytes = New-Object byte[] 4
    if ($Stream.Read($bytes, 0, 4) -ne 4) { throw 'Backup header is truncated.' }
    if ([BitConverter]::IsLittleEndian) { [Array]::Reverse($bytes) }
    return [BitConverter]::ToUInt32($bytes, 0)
}

function Confirm-Restore {
    if ($AssumeYes) { return $true }
    Write-Host ''
    Write-Host 'This will replace this Windows user''s current IZ Clinical Notes Analyzer local data with the encrypted backup.' -ForegroundColor Yellow
    return ((Read-Host 'Type RESTORE to continue').Trim() -eq 'RESTORE')
}

if (-not (Confirm-Restore)) { Write-Host 'Restore cancelled.'; exit 1 }
$resolvedBackup = (Resolve-Path -LiteralPath $BackupPath).Path
if (-not $NoStop) {
    $stopScript = Join-Path $PSScriptRoot 'stop-windows-local.ps1'
    if (Test-Path -LiteralPath $stopScript) { & $stopScript -NoRestartPrompt -NoPause }
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) "iz-cna-restore-$([Guid]::NewGuid().ToString('N'))"
$rollbackDir = "$LocalDataDir.restore-rollback-$([Guid]::NewGuid().ToString('N'))"
try {
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    $stream = [IO.File]::OpenRead($resolvedBackup)
    try {
        $magic = New-Object byte[] 8
        if ($stream.Read($magic, 0, 8) -ne 8 -or [Text.Encoding]::ASCII.GetString($magic) -ne 'IZCNABK2') { throw 'Backup is not an IZ Clinical Notes Analyzer encrypted backup.' }
        $headerLength = Read-UInt32BigEndian -Stream $stream
        if ($headerLength -lt 2 -or $headerLength -gt 65536) { throw 'Backup header length is invalid.' }
        $headerBytes = New-Object byte[] $headerLength
        if ($stream.Read($headerBytes, 0, $headerLength) -ne $headerLength) { throw 'Backup header is truncated.' }
        $header = [Text.Encoding]::UTF8.GetString($headerBytes) | ConvertFrom-Json
        if ($header.format -ne 'IZCNABK2' -or $header.version -ne 2) { throw 'Backup format is unsupported.' }
        $payloadLength = $stream.Length - 8 - 4 - $headerLength - 32
        if ($payloadLength -le 0) { throw 'Backup payload is truncated.' }
        $stream.Dispose()
        $allWithoutTag = [IO.File]::ReadAllBytes($resolvedBackup)
        $tag = New-Object byte[] 32
        [Array]::Copy($allWithoutTag, $allWithoutTag.Length - 32, $tag, 0, 32)
        $protectedKey = [Convert]::FromBase64String([string]$header.protected_key)
        $rawKey = [Security.Cryptography.ProtectedData]::Unprotect($protectedKey, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
        if ($rawKey.Length -ne 64) { throw 'Backup encryption key is invalid.' }
        $macKey = New-Object byte[] 32; [Array]::Copy($rawKey, 32, $macKey, 0, 32)
        $hmac = [Security.Cryptography.HMACSHA256]::new([byte[]]$macKey)
        try { $expectedTag = $hmac.ComputeHash($allWithoutTag, 0, $allWithoutTag.Length - 32) } finally { $hmac.Dispose() }
        $different = 0
        for ($index = 0; $index -lt $tag.Length; $index++) { $different = $different -bor ($tag[$index] -bxor $expectedTag[$index]) }
        if ($different -ne 0) { throw 'Backup authentication failed. Current local data was not changed.' }

        $cipherStream = [IO.File]::OpenRead($resolvedBackup)
        $cipherStream.Seek(8 + 4 + $headerLength, [IO.SeekOrigin]::Begin) | Out-Null
        $cipherOnly = Join-Path $tempRoot 'cipher.bin'
        $cipherOutput = [IO.File]::Open($cipherOnly, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try {
            $remaining = [int64]$payloadLength
            $buffer = New-Object byte[] 65536
            while ($remaining -gt 0) {
                $read = $cipherStream.Read($buffer, 0, [Math]::Min($buffer.Length, $remaining))
                if ($read -le 0) { throw 'Backup payload is truncated.' }
                $cipherOutput.Write($buffer, 0, $read)
                $remaining -= $read
            }
        } finally { $cipherOutput.Dispose(); $cipherStream.Dispose() }
        $encKey = New-Object byte[] 32; [Array]::Copy($rawKey, 0, $encKey, 0, 32)
        $aes = New-Object Security.Cryptography.AesManaged
        $aes.KeySize = 256; $aes.Mode = [Security.Cryptography.CipherMode]::CBC; $aes.Padding = [Security.Cryptography.PaddingMode]::PKCS7
        $aes.Key = $encKey; $aes.IV = [Convert]::FromBase64String([string]$header.iv)
        $plainZip = Join-Path $tempRoot 'payload.zip'
        $decryptor = $aes.CreateDecryptor()
        $cipherInput = [IO.File]::OpenRead($cipherOnly)
        $crypto = New-Object Security.Cryptography.CryptoStream($cipherInput, $decryptor, [Security.Cryptography.CryptoStreamMode]::Read)
        $output = [IO.File]::Open($plainZip, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try {
            $crypto.CopyTo($output)
        } finally { $output.Dispose(); $crypto.Dispose(); $cipherInput.Dispose(); $decryptor.Dispose(); $aes.Dispose() }
        if ((Get-FileHash -LiteralPath $plainZip -Algorithm SHA256).Hash.ToLowerInvariant() -ne [string]$header.plaintext_sha256) { throw 'Backup plaintext hash verification failed. Current local data was not changed.' }
    } finally { if ($stream) { $stream.Dispose() } }

    $extractRoot = Join-Path $tempRoot 'extract'
    Expand-Archive -LiteralPath (Join-Path $tempRoot 'payload.zip') -DestinationPath $extractRoot -Force
    $candidateData = Join-Path $extractRoot 'IZ Clinical Notes Analyzer'
    if (-not (Test-Path -LiteralPath $candidateData) -or -not (Test-Path -LiteralPath (Join-Path $extractRoot 'backup-manifest.json'))) { throw 'Backup contents are incomplete. Current local data was not changed.' }
    if (Test-Path -LiteralPath $LocalDataDir) { Move-Item -LiteralPath $LocalDataDir -Destination $rollbackDir }
    try {
        Move-Item -LiteralPath $candidateData -Destination $LocalDataDir
    } catch {
        if (Test-Path -LiteralPath $rollbackDir) { Move-Item -LiteralPath $rollbackDir -Destination $LocalDataDir }
        throw
    }
    if (Test-Path -LiteralPath $rollbackDir) { Remove-Item -LiteralPath $rollbackDir -Recurse -Force }
} finally {
    if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
}

Write-Host 'Encrypted backup restored. Start IZ Clinical Notes Analyzer and confirm the local version/readiness status.' -ForegroundColor Green
exit 0
