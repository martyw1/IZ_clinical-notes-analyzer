[CmdletBinding()]
param(
    [ValidateSet('backup-roundtrip', 'backup-negative', 'All')]
    [string]$Case = 'All',
    [string]$EvidenceRoot = ''
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$script:Assertions = New-Object Collections.Generic.List[object]
$script:Scenarios = New-Object Collections.Generic.List[object]
$script:StartedUtc = [DateTime]::UtcNow.ToString('o')
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$backupModulePath = Join-Path $repositoryRoot 'scripts\installer\backup-verification.psm1'
$commonModulePath = Join-Path $repositoryRoot 'scripts\installer\maintenance-common.psm1'
$pythonPath = Join-Path $repositoryRoot 'backend\.venv\Scripts\python.exe'
if (-not $EvidenceRoot) { $EvidenceRoot = Join-Path $repositoryRoot '.omo\evidence\windows-cmd-maintenance\backup' }

function Assert-BackupTest {
    param([bool]$Condition, [string]$Name)
    $script:Assertions.Add([ordered]@{ name = $Name; passed = $Condition })
    if (-not $Condition) { throw "BACKUP_ASSERTION_FAILED:$Name" }
}

function Add-Scenario {
    param([string]$Id, [string]$Expected, [string]$Observed, [bool]$Passed, [string]$Artifact)
    $script:Scenarios.Add([ordered]@{ id = $Id; expected = $Expected; observed = $Observed; passed = $Passed; artifact = $Artifact })
    Assert-BackupTest -Condition $Passed -Name $Id
}

function Get-SafeReason {
    param([Management.Automation.ErrorRecord]$Record)
    if ($Record.Exception.Data.Contains('iz_reason')) { return [string]$Record.Exception.Data['iz_reason'] }
    if ($Record.Exception.Message -match '^[A-Z][A-Z0-9_:.-]+$') { return $Record.Exception.Message }
    return 'BACKUP_TEST_FAILED'
}

function Assert-BackupFailure {
    param([scriptblock]$Action, [string]$ScenarioId, [string[]]$AllowedReasons, [string]$Artifact)
    $reason = ''
    try { & $Action; throw "EXPECTED_BACKUP_FAILURE:$ScenarioId" }
    catch {
        if ($_.Exception.Message -like 'EXPECTED_BACKUP_FAILURE:*') { throw }
        $reason = Get-SafeReason $_
    }
    Add-Scenario -Id $ScenarioId -Expected 'safe_rejection_without_activation' -Observed $reason -Passed ($AllowedReasons.Count -eq 0 -or $reason -in $AllowedReasons) -Artifact $Artifact
}

function Write-Evidence {
    param([string]$Status, [string]$Reason)
    [IO.Directory]::CreateDirectory($EvidenceRoot) | Out-Null
    $names = if ($Case -eq 'All') { @('task-04-roundtrip.json', 'task-04-negative.json') } elseif ($Case -eq 'backup-roundtrip') { @('task-04-roundtrip.json') } else { @('task-04-negative.json') }
    foreach ($name in $names) {
        $kind = if ($name -like '*roundtrip*') { 'backup-roundtrip' } else { 'backup-negative' }
        $selectedScenarios = @($script:Scenarios.ToArray() | Where-Object { if ($kind -eq 'backup-roundtrip') { $_.id -like 'roundtrip_*' -or $_.id -like 'legacy_*' } else { $_.id -notlike 'roundtrip_*' -and $_.id -notlike 'legacy_*' } })
        $receipt = [ordered]@{
            schema = 'iz-cna-backup-test-evidence-v1'; case = $kind; tier = 'Component'; status = $Status; reason = $Reason
            invocation = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/tests/maintenance-backup.Tests.ps1 -Case $Case"
            binary_observable = if ($Status -eq 'passed') { 'process_exit_0' } else { 'process_exit_1' }
            scenarios = $selectedScenarios; assertion_count = $script:Assertions.Count
            powershell_version = $PSVersionTable.PSVersion.ToString(); started_utc = $script:StartedUtc; completed_utc = [DateTime]::UtcNow.ToString('o')
            blocked_external_scenarios = @('genuine_second_windows_account_dpapi', 'real_disk_full', 'Package_or_Home_tier')
        }
        [IO.File]::WriteAllText((Join-Path $EvidenceRoot $name), ($receipt | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    }
}

function New-TestFixture {
    $qaParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\\')
    [IO.Directory]::CreateDirectory($qaParent) | Out-Null
    $runRoot = Join-Path $qaParent ('q' + [Guid]::NewGuid().ToString('N').Substring(0, 4))
    $componentRoot = Join-Path $runRoot ('iz-cna-component-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
    [IO.Directory]::CreateDirectory($componentRoot) | Out-Null
    return [pscustomobject]@{ qa_parent = $qaParent; run_root = $runRoot; component_root = $componentRoot }
}

function Remove-TestFixture {
    param([object]$Fixture)
    $full = [IO.Path]::GetFullPath($Fixture.run_root).TrimEnd('\')
    $parent = [IO.Path]::GetFullPath($Fixture.qa_parent).TrimEnd('\')
    if (-not $full.StartsWith($parent + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'TEST_CLEANUP_SCOPE_INVALID' }
    if (Test-Path -LiteralPath $full) { Remove-Item -LiteralPath $full -Recurse -Force }
}

function New-SyntheticProfile {
    param([object]$Context)
    [IO.Directory]::CreateDirectory($Context.data_root) | Out-Null
    $databaseDirectory = Join-Path $Context.data_root 'database'; $encryptedDirectory = Join-Path $Context.data_root 'encrypted-uploads'; $keysDirectory = Join-Path $Context.data_root 'keys'
    [IO.Directory]::CreateDirectory($databaseDirectory) | Out-Null; [IO.Directory]::CreateDirectory($encryptedDirectory) | Out-Null; [IO.Directory]::CreateDirectory($keysDirectory) | Out-Null
    $databasePath = Join-Path $databaseDirectory 'custom-synthetic.sqlite3'; $encryptedPath = Join-Path $encryptedDirectory 'synthetic-envelope.bin'; $environmentPath = Join-Path $Context.data_root '.env'
    $secret = 'synthetic-maintenance-key-material-00000001'
    $python = @'
import base64, hashlib, os, sqlite3, sys
from pathlib import Path
from cryptography.fernet import Fernet
db, encrypted, secret = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
cipher = Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode('utf-8')).digest()))
payload = b'IZCNA1:' + cipher.encrypt(b'{"fixture":"synthetic-only"}')
encrypted.write_bytes(payload)
connection = sqlite3.connect(db)
connection.execute('PRAGMA journal_mode=WAL')
connection.execute('PRAGMA wal_autocheckpoint=0')
connection.executescript('CREATE TABLE schema_migrations(version INTEGER NOT NULL); INSERT INTO schema_migrations VALUES(12); CREATE TABLE patients(id INTEGER PRIMARY KEY, synthetic_code TEXT NOT NULL); CREATE TABLE treatment_plan_imports(id INTEGER PRIMARY KEY, encrypted_payload BLOB NOT NULL); CREATE TABLE source_documents(id INTEGER PRIMARY KEY, encrypted_relative_path TEXT NOT NULL);')
connection.execute('INSERT INTO patients(synthetic_code) VALUES(?)', ('SYNTHETIC-0001',))
connection.execute('INSERT INTO treatment_plan_imports(encrypted_payload) VALUES(?)', (payload,))
connection.execute('INSERT INTO source_documents(encrypted_relative_path) VALUES(?)', ('encrypted-uploads/synthetic-envelope.bin',))
connection.execute('INSERT INTO patients(synthetic_code) VALUES(?)', ('SYNTHETIC-WAL-0002',))
connection.commit()
os._exit(0)
'@
    & $pythonPath -c $python $databasePath $encryptedPath $secret
    if ($LASTEXITCODE -ne 0) { throw 'SYNTHETIC_DATABASE_CREATE_FAILED' }
    Assert-BackupTest (Test-Path -LiteralPath ($databasePath + '-wal') -PathType Leaf) 'fixture_committed_wal_exists'
    [IO.File]::WriteAllText((Join-Path $keysDirectory 'synthetic.key'), 'synthetic-key-file-only', [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $Context.data_root 'synthetic-state.txt'), 'before-backup', [Text.UTF8Encoding]::new($false))
    $environmentText = @("IZ_CNA_ENV_FILE=`"$environmentPath`"", "IZ_CNA_LOCAL_APP_DATA_DIR=`"$($Context.data_root)`"", "IZ_CNA_LOCAL_SQLITE_DB_PATH=`"$databasePath`"", "IZ_CNA_DATA_ENCRYPTION_KEY=$secret", 'SYNTHETIC_ONLY=true') -join "`n"
    [IO.File]::WriteAllText($environmentPath, $environmentText + "`n", [Text.UTF8Encoding]::new($false))
    return [pscustomobject]@{ database_path = $databasePath; environment_path = $environmentPath; environment_sha256 = (Get-FileHash $environmentPath -Algorithm SHA256).Hash.ToLowerInvariant() }
}

function New-TestZip {
    param([string]$Path, [object[]]$Entries)
    Add-Type -AssemblyName System.IO.Compression
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    $archive = New-Object IO.Compression.ZipArchive($stream, [IO.Compression.ZipArchiveMode]::Create, $true)
    try {
        foreach ($record in $Entries) {
            $entry = $archive.CreateEntry([string]$record.name, [IO.Compression.CompressionLevel]::Optimal)
            if ($record.PSObject.Properties.Name -contains 'external_attributes') { $entry.ExternalAttributes = [int]$record.external_attributes }
            if (-not [bool]$record.directory) { $bytes = [byte[]]$record.bytes; $target = $entry.Open(); try { $target.Write($bytes, 0, $bytes.Length) } finally { $target.Dispose() } }
        }
    } finally { $archive.Dispose(); $stream.Dispose() }
}

function Protect-TestZip {
    param([string]$ZipPath, [string]$BackupPath, [int64]$PlaintextBytesOverride = -1)
    Add-Type -AssemblyName System.Security
    $plainBytes = [IO.File]::ReadAllBytes($ZipPath); $rawKey = New-Object byte[] 64; $rng = [Security.Cryptography.RandomNumberGenerator]::Create(); try { $rng.GetBytes($rawKey) } finally { $rng.Dispose() }
    $protectedKey = [Security.Cryptography.ProtectedData]::Protect($rawKey, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
    $encKey = New-Object byte[] 32; $macKey = New-Object byte[] 32; [Array]::Copy($rawKey, 0, $encKey, 0, 32); [Array]::Copy($rawKey, 32, $macKey, 0, 32)
    $aes = [Security.Cryptography.Aes]::Create(); $aes.Key = $encKey; $aes.GenerateIV(); $encryptor = $aes.CreateEncryptor()
    try { $cipher = $encryptor.TransformFinalBlock($plainBytes, 0, $plainBytes.Length) } finally { $encryptor.Dispose() }
    $header = [ordered]@{format='IZCNABK2';version=2;created_at=[DateTime]::UtcNow.ToString('o');encryption='aes-256-cbc-hmac-sha256-dpapi-current-user-v1';protected_key=[Convert]::ToBase64String($protectedKey);iv=[Convert]::ToBase64String($aes.IV);plaintext_sha256=(Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant();plaintext_bytes=$(if($PlaintextBytesOverride -ge 0){$PlaintextBytesOverride}else{[int64]$plainBytes.Length})}
    $aes.Dispose(); $headerBytes = [Text.UTF8Encoding]::new($false).GetBytes(($header | ConvertTo-Json -Compress)); $lengthBytes = [BitConverter]::GetBytes([uint32]$headerBytes.Length); if ([BitConverter]::IsLittleEndian) { [Array]::Reverse($lengthBytes) }
    $authenticated = New-Object byte[] (8 + 4 + $headerBytes.Length + $cipher.Length); [Array]::Copy([Text.Encoding]::ASCII.GetBytes('IZCNABK2'),0,$authenticated,0,8); [Array]::Copy($lengthBytes,0,$authenticated,8,4); [Array]::Copy($headerBytes,0,$authenticated,12,$headerBytes.Length); [Array]::Copy($cipher,0,$authenticated,12+$headerBytes.Length,$cipher.Length)
    $hmac = [Security.Cryptography.HMACSHA256]::new([byte[]]$macKey); try { $tag=$hmac.ComputeHash($authenticated) } finally { $hmac.Dispose() }
    $output=[IO.File]::Open($BackupPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None); try{$output.Write($authenticated,0,$authenticated.Length);$output.Write($tag,0,$tag.Length)}finally{$output.Dispose()}
    [Array]::Clear($rawKey,0,$rawKey.Length);[Array]::Clear($encKey,0,$encKey.Length);[Array]::Clear($macKey,0,$macKey.Length)
}

function New-LegacyBackup {
    param([object]$Context,[string]$Destination,[switch]$MissingEnvironment,[switch]$CorruptDatabase)
    $token=[Guid]::NewGuid().ToString('N').Substring(0,4);$scratch=Join-Path $Context.transaction_root ('l'+$token);$data=Join-Path $scratch 'IZ Clinical Notes Analyzer';[IO.Directory]::CreateDirectory($data)|Out-Null
    foreach($item in Get-ChildItem -LiteralPath $Context.data_root -Force){if($MissingEnvironment-and$item.Name-eq'.env'){continue};Copy-Item -LiteralPath $item.FullName -Destination (Join-Path $data $item.Name) -Recurse -Force}
    $dbTarget=Join-Path $data 'database\custom-synthetic.sqlite3';if($CorruptDatabase){Remove-Item -LiteralPath ($dbTarget+'-wal'),($dbTarget+'-shm') -Force -ErrorAction SilentlyContinue;[IO.File]::WriteAllBytes($dbTarget,[Text.Encoding]::ASCII.GetBytes('not-a-database'))}
    $manifest=[ordered]@{format='iz-cna-local-data-v2';created_at=[DateTime]::UtcNow.ToString('o');source='local-app-data';restore_scope='same-windows-user'};[IO.File]::WriteAllText((Join-Path $scratch 'backup-manifest.json'),($manifest|ConvertTo-Json),[Text.UTF8Encoding]::new($true))
    $zip=Join-Path $Context.transaction_root ('z'+$token+'.zip');Compress-Archive -Path (Join-Path $scratch '*') -DestinationPath $zip -CompressionLevel Optimal;Protect-TestZip -ZipPath $zip -BackupPath $Destination;Remove-Item $scratch -Recurse -Force;Remove-Item $zip -Force
}

function Invoke-RoundtripTests {
    param([object]$Fixture,[object]$Context,[object]$Profile)
    $identity=New-IzDataIdentity -Context $Context -SelectedDatabasePath $Profile.database_path
    $backup=New-IzFullBackup -Context $Context -DataIdentity $identity -RuntimeRole SourceTest -Manifest $null -BackupPath $Context.snapshot_path
    Add-Scenario 'roundtrip_verified_backup' 'IZCNABK2_verified_true' "$($backup.format):$($backup.verified)" ($backup.format -eq 'IZCNABK2' -and $backup.verified -and (Test-Path $backup.Path)) 'task-04-roundtrip.json'
    Add-Scenario 'roundtrip_committed_wal_rows' 'two_committed_rows_in_snapshot' ([string]$backup.safe_counts.patients) ($backup.profile_snapshot_identity -match '^[0-9a-f]{64}$' -and [int]$backup.safe_counts.patients -eq 2) 'task-04-roundtrip.json'
    $header=[IO.File]::ReadAllBytes($backup.Path);Assert-BackupTest ([Text.Encoding]::ASCII.GetString($header,0,8)-eq'IZCNABK2') 'roundtrip_outer_magic'
    $environmentBefore=[IO.File]::ReadAllBytes($Profile.environment_path);[IO.File]::WriteAllText((Join-Path $Context.data_root 'synthetic-state.txt'),'mutated-after-backup',[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText((Join-Path $Context.data_root 'post-backup-only.txt'),'remove-me',[Text.UTF8Encoding]::new($false))
    $restored=Restore-IzFullBackup -Context $Context -BackupPath $backup.Path -RuntimeRole SourceTest -Manifest $null -ExpectedProfileSnapshotIdentity $backup.profile_snapshot_identity -Confirmed
    $environmentAfter=[IO.File]::ReadAllBytes($Profile.environment_path)
    Add-Scenario 'roundtrip_restore_activation' 'restored_verified_identity' "$($restored.status):$($restored.verified)" ($restored.status -eq 'success' -and $restored.verified -and $restored.profile_snapshot_identity -eq $backup.profile_snapshot_identity -and $restored.sqlite_integrity -eq 'ok' -and [int]$restored.foreign_key_violations -eq 0 -and [int]$restored.safe_counts.patients -eq 2 -and [int]$restored.encrypted_payloads_valid -eq [int]$restored.encrypted_payloads_checked) 'task-04-roundtrip.json'
    Add-Scenario 'roundtrip_environment_bytes' 'exact_env_bytes' 'sha256_equal' (([Convert]::ToBase64String($environmentBefore))-ceq([Convert]::ToBase64String($environmentAfter))) 'task-04-roundtrip.json'
    Add-Scenario 'roundtrip_full_tree_replaced' 'pre_backup_state_no_extra' 'tree_restored' (((Get-Content (Join-Path $Context.data_root 'synthetic-state.txt') -Raw)-eq'before-backup') -and -not(Test-Path(Join-Path $Context.data_root 'post-backup-only.txt'))) 'task-04-roundtrip.json'
    $legacyPath=Join-Path $Fixture.run_root 'legacy & () ! % Ü.izcnabackup';New-LegacyBackup -Context $Context -Destination $legacyPath;$legacy=Test-IzFullBackup -Context $Context -BackupPath $legacyPath -RuntimeRole SourceTest -Manifest $null
    Add-Scenario 'legacy_izcnabk2_reader' 'old_minimal_manifest_verified' "$($legacy.status):$($legacy.schema_version)" ($legacy.verified -and $legacy.schema_version -eq 12) 'task-04-roundtrip.json';Remove-Item $legacy.verification_work_root -Recurse -Force
    [IO.File]::WriteAllText((Join-Path $Context.data_root 'synthetic-state.txt'),'legacy-restore-mutation',[Text.UTF8Encoding]::new($false))
    $legacyRestored=Restore-IzFullBackup -Context $Context -BackupPath $legacyPath -RuntimeRole SourceTest -Manifest $null -ExpectedProfileSnapshotIdentity $legacy.profile_snapshot_identity -Confirmed
    Add-Scenario 'legacy_izcnabk2_restore' 'old_minimal_manifest_restored' "$($legacyRestored.status):$($legacyRestored.verified)" ($legacyRestored.verified -and $legacyRestored.profile_snapshot_identity -eq $legacy.profile_snapshot_identity -and (Get-Content (Join-Path $Context.data_root 'synthetic-state.txt') -Raw) -eq 'before-backup') 'task-04-roundtrip.json'
}

function Invoke-NegativeTests {
    param([object]$Fixture,[object]$Context,[object]$Profile)
    $identity=New-IzDataIdentity -Context $Context -SelectedDatabasePath $Profile.database_path;$validPath=Join-Path $Fixture.run_root 'valid-negative-seed.izcnabackup';$valid=New-IzFullBackup -Context $Context -DataIdentity $identity -RuntimeRole SourceTest -Manifest $null -BackupPath $validPath;$baseline=(Get-FileHash (Join-Path $Context.data_root 'synthetic-state.txt') -Algorithm SHA256).Hash
    foreach($mutation in @('header','cipher','tag','truncated')){$path=Join-Path $Fixture.run_root "$mutation.izcnabackup";Copy-Item $valid.Path $path;$bytes=[IO.File]::ReadAllBytes($path);$headerLengthBytes=$bytes[8..11];if([BitConverter]::IsLittleEndian){[Array]::Reverse($headerLengthBytes)};$headerLength=[BitConverter]::ToUInt32($headerLengthBytes,0);if($mutation-eq'header'){$bytes[20]=$bytes[20]-bxor 1}elseif($mutation-eq'cipher'){$index=12+$headerLength+8;$bytes[$index]=$bytes[$index]-bxor 1}elseif($mutation-eq'tag'){$bytes[$bytes.Length-1]=$bytes[$bytes.Length-1]-bxor 1}else{$bytes=$bytes[0..($bytes.Length-8)]};[IO.File]::WriteAllBytes($path,$bytes);Assert-BackupFailure {Test-IzFullBackup -Context $Context -BackupPath $path -RuntimeRole SourceTest -Manifest $null|Out-Null} "tamper_$mutation" @() 'task-04-negative.json'}
    Assert-BackupFailure {Restore-IzFullBackup -Context $Context -BackupPath $path -RuntimeRole SourceTest -Manifest $null -Confirmed|Out-Null} 'restore_tampered_before_activation' @() 'task-04-negative.json';Assert-BackupTest ((Get-FileHash (Join-Path $Context.data_root 'synthetic-state.txt') -Algorithm SHA256).Hash-eq$baseline) 'tampered_restore_active_data_unchanged'
    $protectedKeyPath=Join-Path $Fixture.run_root 'protected-key.izcnabackup';Copy-Item $valid.Path $protectedKeyPath;$protectedBytes=[IO.File]::ReadAllBytes($protectedKeyPath);$protectedLengthBytes=$protectedBytes[8..11];if([BitConverter]::IsLittleEndian){[Array]::Reverse($protectedLengthBytes)};$protectedHeaderLength=[BitConverter]::ToUInt32($protectedLengthBytes,0);$protectedHeaderText=[Text.UTF8Encoding]::new($false,$true).GetString($protectedBytes,12,$protectedHeaderLength);$protectedHeader=$protectedHeaderText|ConvertFrom-Json;$protectedValue=[string]$protectedHeader.protected_key;$protectedHeader.protected_key=$(if($protectedValue[0]-eq'A'){'B'+$protectedValue.Substring(1)}else{'A'+$protectedValue.Substring(1)});$replacement=[Text.UTF8Encoding]::new($false).GetBytes(($protectedHeader|ConvertTo-Json -Compress));Assert-BackupTest ($replacement.Length-eq$protectedHeaderLength) 'protected_key_fixture_preserves_header_length';[Array]::Copy($replacement,0,$protectedBytes,12,$replacement.Length);[IO.File]::WriteAllBytes($protectedKeyPath,$protectedBytes);Assert-BackupFailure {Test-IzFullBackup $Context $protectedKeyPath SourceTest $null|Out-Null} 'tamper_protected_key' @('BACKUP_KEY_UNAVAILABLE','BACKUP_AUTHENTICATION_FAILED') 'task-04-negative.json'
    $legacyMissing=Join-Path $Fixture.run_root 'missing-environment.izcnabackup';New-LegacyBackup $Context $legacyMissing -MissingEnvironment;Assert-BackupFailure {Test-IzFullBackup $Context $legacyMissing SourceTest $null|Out-Null} 'missing_environment' @('BACKUP_ENVIRONMENT_MISSING') 'task-04-negative.json'
    $legacyCorrupt=Join-Path $Fixture.run_root 'corrupt-database.izcnabackup';New-LegacyBackup $Context $legacyCorrupt -CorruptDatabase;Assert-BackupFailure {Test-IzFullBackup $Context $legacyCorrupt SourceTest $null|Out-Null} 'semantic_database_corruption' @('RUNTIME_DATABASE_INVALID','RUNTIME_DATABASE_INTEGRITY_FAILED') 'task-04-negative.json'
    $manifestBytes=[Text.UTF8Encoding]::new($false).GetBytes('{"format":"iz-cna-local-data-v2","created_at":"2026-09-14T00:00:00Z","source":"local-app-data","restore_scope":"same-windows-user"}')
    $traversalZip=Join-Path $Context.transaction_root 'traversal.zip';$traversalBackup=Join-Path $Fixture.run_root 'traversal.izcnabackup';New-TestZip $traversalZip @([pscustomobject]@{name='backup-manifest.json';bytes=$manifestBytes;directory=$false},[pscustomobject]@{name='IZ Clinical Notes Analyzer/';bytes=@();directory=$true},[pscustomobject]@{name='../escaped.txt';bytes=[byte[]](1,2,3);directory=$false});Protect-TestZip $traversalZip $traversalBackup
    Assert-BackupFailure {Test-IzFullBackup $Context $traversalBackup SourceTest $null|Out-Null} 'archive_traversal' @('BACKUP_ARCHIVE_PATH_INVALID','BACKUP_ARCHIVE_LAYOUT_INVALID') 'task-04-negative.json';Assert-BackupTest (-not(Get-ChildItem $Fixture.run_root -Recurse -Filter escaped.txt -ErrorAction SilentlyContinue)) 'traversal_created_no_file'
    $duplicateZip=Join-Path $Context.transaction_root 'duplicate.zip';$duplicateBackup=Join-Path $Fixture.run_root 'duplicate.izcnabackup';New-TestZip $duplicateZip @([pscustomobject]@{name='backup-manifest.json';bytes=$manifestBytes;directory=$false},[pscustomobject]@{name='IZ Clinical Notes Analyzer/';bytes=@();directory=$true},[pscustomobject]@{name='IZ Clinical Notes Analyzer/A.txt';bytes=[byte[]](1);directory=$false},[pscustomobject]@{name='IZ Clinical Notes Analyzer/a.txt';bytes=[byte[]](2);directory=$false});Protect-TestZip $duplicateZip $duplicateBackup
    Assert-BackupFailure {Test-IzFullBackup $Context $duplicateBackup SourceTest $null|Out-Null} 'archive_case_collision' @('BACKUP_ARCHIVE_DUPLICATE_ENTRY') 'task-04-negative.json'
    $unicodeZip=Join-Path $Context.transaction_root 'unicode-duplicate.zip';$unicodeBackup=Join-Path $Fixture.run_root 'unicode-duplicate.izcnabackup';New-TestZip $unicodeZip @([pscustomobject]@{name='backup-manifest.json';bytes=$manifestBytes;directory=$false},[pscustomobject]@{name='IZ Clinical Notes Analyzer/';bytes=@();directory=$true},[pscustomobject]@{name=('IZ Clinical Notes Analyzer/'+[char]0x00DC+'.txt');bytes=[byte[]](1);directory=$false},[pscustomobject]@{name=('IZ Clinical Notes Analyzer/'+[char]0x00FC+'.txt');bytes=[byte[]](2);directory=$false});Protect-TestZip $unicodeZip $unicodeBackup
    Assert-BackupFailure {Test-IzFullBackup $Context $unicodeBackup SourceTest $null|Out-Null} 'archive_unicode_case_collision' @('BACKUP_ARCHIVE_DUPLICATE_ENTRY') 'task-04-negative.json'
    $symlinkAttributes=[int]0xA0000000
    $unsafeEntries=@(
        [pscustomobject]@{id='archive_rooted_path';name='/rooted.txt';reason='BACKUP_ARCHIVE_PATH_INVALID';attributes=$null},
        [pscustomobject]@{id='archive_drive_path';name='C:/outside.txt';reason='BACKUP_ARCHIVE_PATH_INVALID';attributes=$null},
        [pscustomobject]@{id='archive_unc_path';name='\\server\share\outside.txt';reason='BACKUP_ARCHIVE_PATH_INVALID';attributes=$null},
        [pscustomobject]@{id='archive_ads_path';name='IZ Clinical Notes Analyzer/file.txt:stream';reason='BACKUP_ARCHIVE_PATH_INVALID';attributes=$null},
        [pscustomobject]@{id='archive_device_path';name='IZ Clinical Notes Analyzer/CON.txt';reason='BACKUP_ARCHIVE_DEVICE_NAME';attributes=$null},
        [pscustomobject]@{id='archive_long_path';name=('IZ Clinical Notes Analyzer/'+(('segment/'*150))+'file.txt');reason='BACKUP_ARCHIVE_PATH_TOO_LONG';attributes=$null},
        [pscustomobject]@{id='archive_reparse_entry';name='IZ Clinical Notes Analyzer/reparse.bin';reason='BACKUP_ARCHIVE_REPARSE_ENTRY';attributes=0x400},
        [pscustomobject]@{id='archive_symlink_entry';name='IZ Clinical Notes Analyzer/link.bin';reason='BACKUP_ARCHIVE_SPECIAL_ENTRY';attributes=$symlinkAttributes}
    )
    foreach($unsafe in $unsafeEntries){$unsafeZip=Join-Path $Context.transaction_root ($unsafe.id+'.zip');$unsafeBackup=Join-Path $Fixture.run_root ($unsafe.id+'.izcnabackup');$unsafeRecord=[pscustomobject]@{name=$unsafe.name;bytes=[Text.Encoding]::ASCII.GetBytes('synthetic');directory=$false};if($null-ne$unsafe.attributes){$unsafeRecord|Add-Member -NotePropertyName external_attributes -NotePropertyValue $unsafe.attributes};New-TestZip $unsafeZip @([pscustomobject]@{name='backup-manifest.json';bytes=$manifestBytes;directory=$false},[pscustomobject]@{name='IZ Clinical Notes Analyzer/';bytes=@();directory=$true},$unsafeRecord);Protect-TestZip $unsafeZip $unsafeBackup;Assert-BackupFailure {Test-IzFullBackup $Context $unsafeBackup SourceTest $null|Out-Null} $unsafe.id @($unsafe.reason) 'task-04-negative.json'}
    $oversize=Join-Path $Fixture.run_root 'declared-oversize.izcnabackup';Protect-TestZip $duplicateZip $oversize 68719476737;Assert-BackupFailure {Test-IzFullBackup $Context $oversize SourceTest $null|Out-Null} 'declared_size_limit' @('BACKUP_PLAINTEXT_SIZE_INVALID') 'task-04-negative.json'
    $databaseOnly=Join-Path $Fixture.run_root 'database-only.izcnabackup';[IO.File]::WriteAllBytes($databaseOnly,[Text.Encoding]::ASCII.GetBytes('IZCNABK1'));Assert-BackupFailure {Test-IzFullBackup $Context $databaseOnly SourceTest $null|Out-Null} 'izcnabk1_not_full_snapshot' @('LEGACY_DATABASE_ONLY_BACKUP') 'task-04-negative.json'
    $existingDestination=Join-Path $Fixture.run_root 'existing.izcnabackup';[IO.File]::WriteAllText($existingDestination,'sentinel',[Text.UTF8Encoding]::new($false));Assert-BackupFailure {New-IzFullBackup $Context $identity SourceTest $null $existingDestination|Out-Null} 'existing_destination_preflight' @('BACKUP_DESTINATION_EXISTS') 'task-04-negative.json';Assert-BackupTest ((Get-Content $existingDestination -Raw)-eq'sentinel') 'existing_destination_unchanged';Assert-BackupTest ((Get-FileHash (Join-Path $Context.data_root 'synthetic-state.txt') -Algorithm SHA256).Hash-eq$baseline) 'negative_active_data_unchanged'
    $overlapDestination=Join-Path $Context.data_root 'must-not-create.izcnabackup';Assert-BackupFailure {New-IzFullBackup $Context $identity SourceTest $null $overlapDestination|Out-Null} 'data_root_destination_preflight' @('BACKUP_DESTINATION_OVERLAP') 'task-04-negative.json';Assert-BackupTest (-not(Test-Path $overlapDestination)) 'overlap_destination_not_created'
}

$fixture=$null;$lock=$null;$savedEnvironment=@{}
try{
    foreach($name in @('IZ_CNA_ENV_FILE','IZ_CNA_LOCAL_APP_DATA_DIR','IZ_CNA_LOCAL_SQLITE_DB_PATH','IZ_CNA_DATA_ENCRYPTION_KEY','LOCAL_SQLITE_DB_PATH','DATA_ENCRYPTION_KEY','SECRET_KEY','PSModuleAnalysisCachePath')){$savedEnvironment[$name]=[Environment]::GetEnvironmentVariable($name,'Process');[Environment]::SetEnvironmentVariable($name,$null,'Process')}
    foreach($path in @($backupModulePath,$commonModulePath,$pythonPath)){if(-not(Test-Path $path -PathType Leaf)){throw'BACKUP_TEST_DEPENDENCY_MISSING'}}
    $fixture=New-TestFixture;[Environment]::SetEnvironmentVariable('PSModuleAnalysisCachePath',(Join-Path $fixture.run_root 'module-analysis-cache'),'Process');Import-Module $commonModulePath -Force;Import-Module $backupModulePath -Force;$transaction=[Guid]::NewGuid();$context=Get-IzMaintenanceContext -PackageRoot $repositoryRoot -TransactionId $transaction -ComponentTestRoot $fixture.component_root;Initialize-IzMaintenanceStorage $context|Out-Null;$profile=New-SyntheticProfile $context;$lock=Enter-IzMaintenanceLock -Context $context -Action Backup -TransactionId $transaction
    if($Case-in@('backup-roundtrip','All')){Invoke-RoundtripTests $fixture $context $profile}
    if($Case-in@('backup-negative','All')){Invoke-NegativeTests $fixture $context $profile}
    Write-Evidence 'passed' 'COMPLETED';Write-Host "[pass] maintenance backup case=$Case assertions=$($script:Assertions.Count)";exit 0
}catch{$reason=Get-SafeReason $_;Write-Evidence 'failed' $reason;Write-Error "maintenance backup case=$Case failed: $reason";exit 1}
finally{if($lock){Exit-IzMaintenanceLock $lock};foreach($name in $savedEnvironment.Keys){[Environment]::SetEnvironmentVariable($name,$savedEnvironment[$name],'Process')};if($fixture){Remove-TestFixture $fixture}}
