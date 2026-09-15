Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$commonPath = Join-Path $PSScriptRoot 'maintenance-common.psm1'
if (-not (Test-Path -LiteralPath $commonPath -PathType Leaf)) { throw 'MAINTENANCE_COMMON_MODULE_MISSING' }
Import-Module $commonPath -ErrorAction Stop

$script:RuntimeIdentityFields = @(
    'schema','product_id','owner_sid','scope_id','data_identity','instance_id','transaction_id','process_id',
    'process_started_utc','executable_path','executable_sha256','version','build','installer_revision','port',
    'pipe_name','gate','draining','created_utc'
)
$script:ControlResponseFields = @(
    'schema','request_id','operation','status','reason','product_id','owner_sid','scope_id','data_identity',
    'instance_id','transaction_id','process_id','process_started_utc','version','build','installer_revision',
    'port','gate','draining','active_business_requests'
)

function New-IzRuntimeError {
    param([string]$Reason, [int]$Code = 20)
    $exception = [IO.InvalidDataException]::new($Reason)
    $exception.Data['iz_reason'] = $Reason
    $exception.Data['iz_exit_code'] = $Code
    return $exception
}

function Assert-IzExactProperties {
    param([object]$Value, [string[]]$Expected, [string]$Reason)
    if (-not $Value) { throw (New-IzRuntimeError $Reason) }
    $actual = @($Value.PSObject.Properties.Name)
    if ($actual.Count -ne $Expected.Count -or @($Expected | Where-Object { $_ -notin $actual }).Count) {
        throw (New-IzRuntimeError $Reason)
    }
}

function Read-IzRuntimeIdentity {
    param([Parameter(Mandatory)][object]$Context)
    Assert-IzMaintenanceContext $Context | Out-Null
    if (-not (Test-Path -LiteralPath $Context.runtime_identity_path -PathType Leaf)) { return $null }
    $path = Get-IzCanonicalPath -Path $Context.runtime_identity_path
    if ((Get-Item -LiteralPath $path).Length -gt 65536) { throw (New-IzRuntimeError 'RUNTIME_IDENTITY_INVALID') }
    try { $identity = [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8) | ConvertFrom-Json }
    catch { throw (New-IzRuntimeError 'RUNTIME_IDENTITY_INVALID') }
    Assert-IzExactProperties $identity $script:RuntimeIdentityFields 'RUNTIME_IDENTITY_INVALID'
    if ($identity.schema -cne 'iz-cna-runtime-identity-v1' -or $identity.product_id -cne $Context.product_id -or
        $identity.owner_sid -cne $Context.owner_sid -or $identity.scope_id -cne $Context.scope_id -or
        $identity.pipe_name -cne $Context.pipe_name -or [string]$identity.data_identity -notmatch '^[0-9a-f]{64}$' -or
        [string]$identity.instance_id -notmatch '^[0-9a-f]{32}$' -or [string]$identity.executable_sha256 -notmatch '^[0-9a-f]{64}$' -or
        [int64]$identity.process_id -lt 1 -or [int]$identity.port -lt 1 -or [int]$identity.port -gt 65535) {
        throw (New-IzRuntimeError 'RUNTIME_IDENTITY_MISMATCH')
    }
    if ($null -ne $identity.transaction_id -and [string]$identity.transaction_id -notmatch '^[0-9a-f]{32}$') {
        throw (New-IzRuntimeError 'RUNTIME_IDENTITY_MISMATCH')
    }
    return $identity
}

function Get-IzProcessRecord {
    param([Parameter(Mandatory)][int]$ProcessId)
    $record = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if (-not $record) { return $null }
    try { $owner = (Invoke-CimMethod -InputObject $record -MethodName GetOwnerSid -ErrorAction Stop).Sid }
    catch { throw (New-IzRuntimeError 'PROCESS_OWNER_UNAVAILABLE') }
    try { $path = Get-IzCanonicalPath -Path ([string]$record.ExecutablePath) }
    catch { throw (New-IzRuntimeError 'PROCESS_EXECUTABLE_UNAVAILABLE') }
    $started = (Get-Process -Id $ProcessId -ErrorAction Stop).StartTime.ToUniversalTime()
    return [pscustomobject]@{ process_id=$ProcessId; parent_process_id=[int]$record.ParentProcessId; owner_sid=[string]$owner; executable_path=$path; started_utc=$started }
}

function Test-IzProcessIdentity {
    param([object]$Context, [object]$Identity, [string]$ExpectedExecutablePath)
    $record = Get-IzProcessRecord -ProcessId ([int]$Identity.process_id)
    if (-not $record) { return $null }
    $identityStart = [DateTime]::Parse([string]$Identity.process_started_utc, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
    $startDelta = [Math]::Abs(($record.started_utc - $identityStart).TotalSeconds)
    $identityPath = Get-IzCanonicalPath -Path ([string]$Identity.executable_path)
    $expectedPath = Get-IzCanonicalPath -Path $ExpectedExecutablePath
    if ($record.owner_sid -cne $Context.owner_sid -or $identityPath -ine $expectedPath -or
        $record.executable_path -ine $expectedPath -or $startDelta -gt 1.0) {
        throw (New-IzRuntimeError 'RUNTIME_PROCESS_IDENTITY_MISMATCH')
    }
    $hash = (Get-FileHash -LiteralPath $expectedPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -cne [string]$Identity.executable_sha256) { throw (New-IzRuntimeError 'RUNTIME_EXECUTABLE_HASH_MISMATCH') }
    return $record
}

function Get-IzConfiguredRuntimePort {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Context)
    Assert-IzMaintenanceContext $Context | Out-Null
    $values = [Collections.Generic.List[int]]::new()
    foreach ($name in @('IZ_CNA_PORT','BACKEND_PORT')) {
        $raw = [Environment]::GetEnvironmentVariable($name, 'Process')
        if ([string]::IsNullOrWhiteSpace($raw)) { continue }
        $port = 0
        if (-not [int]::TryParse($raw.Trim(), [ref]$port) -or $port -lt 1 -or $port -gt 65535) {
            throw (New-IzRuntimeError 'RUNTIME_PORT_INVALID')
        }
        $values.Add($port)
    }
    $environmentPath = Join-Path $Context.data_root '.env'
    if (Test-Path -LiteralPath $environmentPath -PathType Leaf) {
        if ((Get-Item -LiteralPath $environmentPath).Length -gt 1048576) { throw (New-IzRuntimeError 'ENVIRONMENT_FILE_TOO_LARGE') }
        foreach ($line in [IO.File]::ReadAllLines((Get-IzCanonicalPath $environmentPath), [Text.Encoding]::UTF8)) {
            if ($line -notmatch '^\s*(IZ_CNA_PORT|BACKEND_PORT)\s*=\s*(.*?)\s*$') { continue }
            $port = 0; $raw = $Matches[2].Trim().Trim('"').Trim("'")
            if (-not [int]::TryParse($raw, [ref]$port) -or $port -lt 1 -or $port -gt 65535) {
                throw (New-IzRuntimeError 'RUNTIME_PORT_INVALID')
            }
            $values.Add($port)
        }
    }
    $distinct = @($values | Select-Object -Unique)
    if ($distinct.Count -gt 1) { throw (New-IzRuntimeError 'RUNTIME_PORT_AMBIGUOUS') }
    if ($distinct.Count -eq 1) { return [int]$distinct[0] }
    return 8000
}

function Test-IzInstalledRuntimeAuthority {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Context)
    Assert-IzMaintenanceContext $Context | Out-Null
    $receipt = Read-IzInstallReceipt -Context $Context
    $manifest = Read-IzReleaseManifest -PackageRoot $Context.install_root
    if ($receipt.version -cne $manifest.version -or $receipt.build -cne $manifest.build -or
        [int]$receipt.installer_revision -ne [int]$manifest.installer_revision -or
        $receipt.payload_identity -cne $manifest.payload_identity) {
        throw (New-IzRuntimeError 'INSTALLED_RELEASE_IDENTITY_MISMATCH')
    }
    $expected = @{}
    foreach ($record in @($manifest.files)) {
        $source = [string]$record.path
        $relative = if ($source.StartsWith('app/', [StringComparison]::Ordinal)) { $source.Substring(4) }
            elseif ($source.StartsWith('installer/', [StringComparison]::Ordinal)) { $source }
            else { $null }
        if (-not $relative) { continue }
        if ($expected.ContainsKey($relative.ToUpperInvariant())) { throw (New-IzRuntimeError 'INSTALLED_FILE_SET_INVALID') }
        $expected[$relative.ToUpperInvariant()] = [pscustomobject]@{ path=$relative; length=[long]$record.length; sha256=[string]$record.sha256 }
    }
    $manifestPath = Join-Path $Context.install_root 'release-manifest.json'
    $expected['RELEASE-MANIFEST.JSON'] = [pscustomobject]@{
        path='release-manifest.json'; length=[long](Get-Item -LiteralPath $manifestPath).Length; sha256=(Get-IzFileSha256 $manifestPath)
    }
    if (@($receipt.owned_files).Count -ne $expected.Count) { throw (New-IzRuntimeError 'INSTALLED_FILE_SET_INVALID') }
    foreach ($record in @($receipt.owned_files)) {
        $key = ([string]$record.path).ToUpperInvariant()
        if (-not $expected.ContainsKey($key)) { throw (New-IzRuntimeError 'INSTALLED_FILE_SET_INVALID') }
        $manifestRecord = $expected[$key]
        if ([long]$record.length -ne $manifestRecord.length -or [string]$record.sha256 -cne $manifestRecord.sha256) {
            throw (New-IzRuntimeError 'INSTALLED_FILE_RECEIPT_MISMATCH')
        }
        $path = Assert-IzContainedPath (Join-Path $Context.install_root ([string]$record.path).Replace('/','\')) $Context.install_root
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or [long](Get-Item -LiteralPath $path).Length -ne [long]$record.length -or
            (Get-IzFileSha256 $path) -cne [string]$record.sha256) { throw (New-IzRuntimeError 'INSTALLED_FILE_MISMATCH') }
    }
    $actual = @(Get-ChildItem -LiteralPath $Context.install_root -File -Recurse -Force | ForEach-Object {
        $_.FullName.Substring($Context.install_root.Length + 1).Replace('\','/')
    } | Where-Object { $_ -cne '.iz-cna-owned-root.json' })
    if ($actual.Count -ne $expected.Count -or @($actual | Where-Object { -not $expected.ContainsKey($_.ToUpperInvariant()) }).Count) {
        throw (New-IzRuntimeError 'INSTALLED_FILE_SET_INVALID')
    }
    return [pscustomobject][ordered]@{ schema='iz-cna-installed-runtime-authority-v1'; status='verified'; receipt=$receipt; manifest=$manifest }
}

function Invoke-IzRuntimeControl {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][object]$Context,
        [Parameter(Mandatory)][ValidateSet('status','drain','shutdown','commit')][string]$Operation,
        [AllowNull()][object]$TransactionId,
        [object]$RuntimeIdentity,
        [ValidateRange(1,60)][int]$TimeoutSeconds = 5
    )
    Assert-IzMaintenanceContext $Context | Out-Null
    $identity = if ($RuntimeIdentity) { $RuntimeIdentity } else { Read-IzRuntimeIdentity -Context $Context }
    Assert-IzExactProperties $identity $script:RuntimeIdentityFields 'RUNTIME_IDENTITY_INVALID'
    if (-not $PSBoundParameters.ContainsKey('TransactionId')) { $TransactionId = $identity.transaction_id }
    if ([string]::IsNullOrEmpty([string]$TransactionId)) { $TransactionId = $null }
    else {
        try { $TransactionId = ([Guid]$TransactionId).ToString('N') }
        catch { throw (New-IzRuntimeError 'TRANSACTION_ID_INVALID') }
    }
    $request = [ordered]@{
        schema='iz-cna-runtime-control-v1'; request_id=[Guid]::NewGuid().ToString('N'); operation=$Operation; transaction_id=$TransactionId
    }
    $requestJson = $request | ConvertTo-Json -Compress
    $encoding = [Text.UTF8Encoding]::new($false)
    if ($encoding.GetByteCount($requestJson) -gt 16384 -or $requestJson.Contains("`n")) { throw (New-IzRuntimeError 'RUNTIME_CONTROL_REQUEST_INVALID') }
    $pipe = [IO.Pipes.NamedPipeClientStream]::new('.', [string]$Context.pipe_name, [IO.Pipes.PipeDirection]::InOut, [IO.Pipes.PipeOptions]::Asynchronous)
    try {
        try { $pipe.Connect($TimeoutSeconds * 1000) }
        catch { throw (New-IzRuntimeError 'RUNTIME_CONTROL_UNAVAILABLE') }
        try { $pipe.ReadMode = [IO.Pipes.PipeTransmissionMode]::Message } catch { }
        $writer = [IO.StreamWriter]::new($pipe, $encoding, 1024, $true)
        $reader = [IO.StreamReader]::new($pipe, $encoding, $false, 1024, $true)
        $writer.NewLine = "`n"; $writer.AutoFlush = $true; $writer.WriteLine($requestJson)
        $readTask = $reader.ReadLineAsync()
        if (-not $readTask.Wait($TimeoutSeconds * 1000)) { throw (New-IzRuntimeError 'RUNTIME_CONTROL_TIMEOUT') }
        $line = $readTask.Result
        if ([string]::IsNullOrEmpty($line) -or $encoding.GetByteCount($line) -gt 65536) { throw (New-IzRuntimeError 'RUNTIME_CONTROL_RESPONSE_INVALID') }
        try { $response = $line | ConvertFrom-Json }
        catch { throw (New-IzRuntimeError 'RUNTIME_CONTROL_RESPONSE_INVALID') }
    } finally { $pipe.Dispose() }
    Assert-IzExactProperties $response $script:ControlResponseFields 'RUNTIME_CONTROL_RESPONSE_INVALID'
    if ($response.schema -cne 'iz-cna-runtime-control-v1' -or $response.request_id -cne $request.request_id -or
        $response.operation -cne $Operation -or $response.product_id -cne $Context.product_id -or
        $response.owner_sid -cne $Context.owner_sid -or $response.scope_id -cne $Context.scope_id) {
        throw (New-IzRuntimeError 'RUNTIME_CONTROL_RESPONSE_MISMATCH')
    }
    foreach ($name in @('data_identity','instance_id','process_id','process_started_utc','version','build','installer_revision','port')) {
        if ([string]$response.$name -cne [string]$identity.$name) { throw (New-IzRuntimeError 'RUNTIME_CONTROL_RESPONSE_MISMATCH') }
    }
    if ([string]$response.transaction_id -cne [string]$identity.transaction_id -or [int]$response.active_business_requests -lt 0) {
        throw (New-IzRuntimeError 'RUNTIME_CONTROL_RESPONSE_MISMATCH')
    }
    return $response
}

function Get-IzProcessesAtPath {
    param([object]$Context, [string]$ExecutablePath)
    $expected = Get-IzCanonicalPath -Path $ExecutablePath -AllowMissingLeaf
    $matches = @()
    foreach ($record in @(Get-CimInstance Win32_Process -ErrorAction Stop)) {
        if (-not $record.ExecutablePath) { continue }
        try { $path = Get-IzCanonicalPath -Path ([string]$record.ExecutablePath) } catch { continue }
        if ($path -ine $expected) { continue }
        $owner = (Invoke-CimMethod -InputObject $record -MethodName GetOwnerSid -ErrorAction Stop).Sid
        if ($owner -cne $Context.owner_sid) { throw (New-IzRuntimeError 'RUNTIME_PROCESS_OWNER_MISMATCH') }
        $matches += [int]$record.ProcessId
    }
    return @($matches)
}

function Wait-IzProcessExit {
    param([int[]]$ProcessIds, [int]$TimeoutSeconds)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $remaining = @($ProcessIds | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
        if (-not $remaining.Count) { return $true }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    return $false
}

function Stop-IzExactProcessTree {
    param([object]$Context, [int]$RootProcessId, [int]$TimeoutSeconds)
    $all = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    $ids = [Collections.Generic.List[int]]::new(); $ids.Add($RootProcessId)
    do {
        $added = $false
        foreach ($record in $all) {
            if ($ids.Contains([int]$record.ProcessId) -or -not $ids.Contains([int]$record.ParentProcessId)) { continue }
            $owner = (Invoke-CimMethod -InputObject $record -MethodName GetOwnerSid -ErrorAction Stop).Sid
            if ($owner -cne $Context.owner_sid) { throw (New-IzRuntimeError 'RUNTIME_TREE_OWNER_MISMATCH') }
            $ids.Add([int]$record.ProcessId); $added = $true
        }
    } while ($added)
    $started=@{}
    foreach($id in $ids.ToArray()){
        $process=Get-Process -Id $id -ErrorAction SilentlyContinue
        if($process){$started[$id]=$process.StartTime.ToUniversalTime()}
    }
    foreach ($id in @($ids.ToArray() | Sort-Object -Descending)) {
        $process=Get-Process -Id $id -ErrorAction SilentlyContinue
        if(-not $process){continue}
        if(-not $started.ContainsKey($id) -or [Math]::Abs(($process.StartTime.ToUniversalTime()-$started[$id]).TotalSeconds) -gt 1){
            throw (New-IzRuntimeError 'RUNTIME_PROCESS_IDENTITY_CHANGED')
        }
        Stop-Process -Id $id -Force
    }
    if (-not (Wait-IzProcessExit -ProcessIds $ids.ToArray() -TimeoutSeconds $TimeoutSeconds)) { throw (New-IzRuntimeError 'RUNTIME_PROCESS_DID_NOT_EXIT') }
    return $ids.ToArray()
}

function New-IzStopResult {
    param([string]$Status,[string]$Reason,[bool]$Graceful,[bool]$Legacy,[int[]]$ProcessIds)
    return [pscustomobject][ordered]@{ schema='iz-cna-runtime-stop-v1'; status=$Status; reason=$Reason; graceful=$Graceful; legacy=$Legacy; process_ids=@($ProcessIds) }
}

function Test-IzPriorCommittedRuntimeHandoff {
    param([object]$Context,[object]$Identity)
    if (-not $Context.transaction_id -or -not $Identity.transaction_id -or
        [string]$Context.transaction_id -ceq [string]$Identity.transaction_id) {
        throw (New-IzRuntimeError 'RUNTIME_TRANSACTION_MISMATCH')
    }
    [void](Test-IzOwnedRootMarker -Context $Context -Path $Context.transaction_root -Role transaction -TransactionId ([Guid]$Context.transaction_id))
    $journal = Read-IzMaintenanceJournal -Context $Context
    $steps = @($journal.completed_steps)
    if ($journal.action -notin @('AutoInstall','Repair') -or $journal.state -cne 'PAYLOAD_VERIFIED' -or
        'PAYLOAD_STAGED' -notin $steps -or 'PAYLOAD_VERIFIED' -notin $steps -or 'RUNTIME_QUIESCED' -in $steps -or
        -not $journal.source_release -or -not $journal.target_release -or
        [string]$journal.payload_identity -cne [string]$journal.target_release.payload_identity) {
        throw (New-IzRuntimeError 'RUNTIME_TRANSACTION_MISMATCH')
    }
    $installed = Test-IzInstalledRuntimeAuthority -Context $Context
    $receipt = $installed.receipt
    $source = $journal.source_release
    $actualReceiptSha256 = Get-IzFileSha256 -Path $Context.install_receipt_path
    if ([string]$journal.prior_receipt_sha256 -cne $actualReceiptSha256 -or
        [string]$receipt.last_committed_transaction -cne [string]$Identity.transaction_id -or
        [string]$journal.data_identity -cne [string]$receipt.data_identity -or
        [string]$receipt.data_identity -cne [string]$Identity.data_identity -or
        [string]$source.version -cne [string]$receipt.version -or
        [string]$source.build -cne [string]$receipt.build -or
        [int]$source.installer_revision -ne [int]$receipt.installer_revision -or
        [string]$source.payload_identity -cne [string]$receipt.payload_identity -or
        [string]$receipt.version -cne [string]$Identity.version -or
        [string]$receipt.build -cne [string]$Identity.build -or
        [int]$receipt.installer_revision -ne [int]$Identity.installer_revision) {
        throw (New-IzRuntimeError 'RUNTIME_TRANSACTION_MISMATCH')
    }
    return $true
}

function Test-IzLegacyRelease {
    param([object]$Context)
    $metadataPath = Join-Path $Context.install_root 'VERSION.json'
    if (-not (Test-Path -LiteralPath $metadataPath -PathType Leaf)) { return $false }
    try { $metadata = [IO.File]::ReadAllText((Get-IzCanonicalPath $metadataPath), [Text.Encoding]::UTF8) | ConvertFrom-Json }
    catch { return $false }
    return (($metadata.version -ceq '2.0.0-beta.3' -and $metadata.build -ceq '2026.09.03.1') -or
        ($metadata.version -ceq '2.0.0-beta.4' -and $metadata.build -ceq '2026.09.10.2'))
}

function Start-IzLegacyRuntime {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][object]$Context,
        [Parameter(Mandatory)][object]$ExpectedRelease,
        [ValidateRange(1,120)][int]$TimeoutSeconds=120
    )
    Assert-IzMaintenanceContext $Context|Out-Null
    if(-not(Test-IzLegacyRelease $Context)){throw(New-IzRuntimeError 'LEGACY_RELEASE_INVALID')}
    $receipt=Read-IzInstallReceipt $Context
    if($receipt.version -cne $ExpectedRelease.version -or $receipt.build -cne $ExpectedRelease.build -or
       [int]$receipt.installer_revision -ne [int]$ExpectedRelease.installer_revision -or
       $receipt.payload_identity -cne $ExpectedRelease.payload_identity){throw(New-IzRuntimeError 'LEGACY_RECEIPT_MISMATCH')}
    foreach($file in @($receipt.owned_files)){
        $path=Assert-IzContainedPath (Join-Path $Context.install_root ([string]$file.path).Replace('/','\')) $Context.install_root
        if(-not(Test-Path $path -PathType Leaf)-or[long](Get-Item $path).Length-ne[long]$file.length-or(Get-IzFileSha256 $path)-cne$file.sha256){
            throw(New-IzRuntimeError 'LEGACY_PROGRAM_MISMATCH')
        }
    }
    $executable=Get-IzCanonicalPath (Join-Path $Context.install_root 'runtime\IZClinicalNotesAnalyzer.exe')
    if(@(Get-IzProcessesAtPath $Context $executable).Count){throw(New-IzRuntimeError 'LEGACY_RUNTIME_ALREADY_RUNNING')}
    $port=Get-IzConfiguredRuntimePort $Context
    $probe=[Net.Sockets.TcpClient]::new()
    try{
        $connect=$probe.BeginConnect('127.0.0.1',$port,$null,$null)
        if($connect.AsyncWaitHandle.WaitOne(250)){try{$probe.EndConnect($connect);throw(New-IzRuntimeError 'RUNTIME_PORT_IN_USE')}catch [IO.InvalidDataException]{throw}catch{}}
    }finally{$probe.Dispose()}
    $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$executable;$start.WorkingDirectory=$Context.install_root
    $start.UseShellExecute=$false;$start.CreateNoWindow=$true
    $start.EnvironmentVariables['IZ_CNA_PORT']=[string]$port
    $start.EnvironmentVariables['IZ_CNA_ENV_FILE']=Join-Path $Context.data_root '.env'
    $start.EnvironmentVariables['IZ_CNA_LOCAL_APP_DATA_DIR']=$Context.data_root
    foreach($name in @('IZ_CNA_MAINTENANCE_MODE','IZ_CNA_MAINTENANCE_JOURNAL','IZ_CNA_MAINTENANCE_TRANSACTION_ID','IZ_CNA_MAINTENANCE_OWNER_PID','IZ_CNA_MAINTENANCE_OWNER_STARTED_UTC')){
        if($start.EnvironmentVariables.ContainsKey($name)){$start.EnvironmentVariables.Remove($name)}
    }
    $process=[Diagnostics.Process]::Start($start);$deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    try{
        do{
            try{
                $health=Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:$port/api/health") -TimeoutSec 2
                $version=Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:$port/api/version") -TimeoutSec 2
                $metadata=$version.Content|ConvertFrom-Json
                $owned=@(Get-IzProcessesAtPath $Context $executable)
                if([int]$health.StatusCode-eq 200-and[int]$version.StatusCode-eq 200-and$owned.Count-and
                   $metadata.version-ceq$ExpectedRelease.version-and$metadata.build-ceq$ExpectedRelease.build){
                    return [pscustomobject][ordered]@{schema='iz-cna-legacy-runtime-start-v1';status='started';port=$port;process_ids=$owned}
                }
            }catch{}
            Start-Sleep -Milliseconds 250
        }while([DateTime]::UtcNow-lt$deadline)
        throw(New-IzRuntimeError 'LEGACY_RUNTIME_READINESS_TIMEOUT')
    }catch{
        [void](Stop-IzOwnedRuntime $Context -TimeoutSeconds 30 -AllowLegacyFallback)
        throw
    }
}

function Stop-IzOwnedRuntime {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][object]$Context,
        [ValidateRange(1,120)][int]$TimeoutSeconds = 30,
        [switch]$AllowLegacyFallback
    )
    try {
        Assert-IzMaintenanceContext $Context | Out-Null
        $executable = Join-Path $Context.install_root 'runtime\IZClinicalNotesAnalyzer.exe'
        $identity = Read-IzRuntimeIdentity -Context $Context
          if (-not $identity) {
              $processes = @(if (Test-Path -LiteralPath $executable -PathType Leaf) { Get-IzProcessesAtPath $Context $executable })
              if (-not $processes.Count) { return New-IzStopResult 'already_stopped' 'NOT_RUNNING' $true $false @() }
              if (-not $AllowLegacyFallback -or -not (Test-IzLegacyRelease $Context)) {
                  return New-IzStopResult 'failure' 'RUNTIME_IDENTITY_MISSING' $false $false $processes
              }
              $processSet=@{};foreach($id in $processes){$processSet[[int]$id]=$true}
              $roots=@(foreach($id in $processes){
                  $record=Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction Stop
                  if(-not $processSet.ContainsKey([int]$record.ParentProcessId)){[int]$id}
              })
              if($roots.Count -ne 1){return New-IzStopResult 'failure' 'LEGACY_RUNTIME_AMBIGUOUS' $false $false $processes}
              $stopped = @(Stop-IzExactProcessTree -Context $Context -RootProcessId $roots[0] -TimeoutSeconds $TimeoutSeconds)
            return New-IzStopResult 'stopped' 'LEGACY_TREE_STOPPED' $false $true $stopped
        }
        $record = Test-IzProcessIdentity -Context $Context -Identity $identity -ExpectedExecutablePath $executable
        if (-not $record) { return New-IzStopResult 'already_stopped' 'PROCESS_EXITED' $true $false @() }
        if ($null -eq $identity.transaction_id) {
            $receipt = Read-IzInstallReceipt -Context $Context
            if (-not $receipt -or $receipt.data_identity -cne $identity.data_identity -or $receipt.version -cne $identity.version -or
                $receipt.build -cne $identity.build -or [int]$receipt.installer_revision -ne [int]$identity.installer_revision) {
                throw (New-IzRuntimeError 'RUNTIME_RECEIPT_MISMATCH')
            }
        } elseif ($Context.transaction_id -cne [string]$identity.transaction_id) {
            if ($Context.transaction_id) {
                try { [void](Test-IzPriorCommittedRuntimeHandoff -Context $Context -Identity $identity) }
                catch { throw (New-IzRuntimeError 'RUNTIME_TRANSACTION_MISMATCH') }
            } else { try {
                $receipt = Read-IzInstallReceipt -Context $Context
                $pending = Get-IzPendingMaintenanceStatus -Context $Context
                if ($pending.status -cne 'COMMITTED' -or -not $pending.journal -or -not $pending.authority -or
                    [string]$pending.journal.transaction_id -cne [string]$identity.transaction_id -or
                    [string]$receipt.last_committed_transaction -cne [string]$identity.transaction_id -or
                    [string]$pending.journal.data_identity -cne [string]$identity.data_identity -or
                    [string]$receipt.data_identity -cne [string]$identity.data_identity -or
                    [string]$receipt.version -cne [string]$identity.version -or
                    [string]$receipt.build -cne [string]$identity.build -or
                    [int]$receipt.installer_revision -ne [int]$identity.installer_revision -or
                    [string]$pending.journal.target_release.payload_identity -cne [string]$receipt.payload_identity -or
                    [string]$pending.authority.program_authority -cne 'candidate' -or
                    [string]$pending.authority.data_authority -cne 'current' -or
                    [string]$pending.authority.launch_policy -cne 'candidate' -or
                    [bool]$pending.authority.recovery_required) {
                    throw (New-IzRuntimeError 'RUNTIME_TRANSACTION_MISMATCH')
                }
                [void](Test-IzInstalledRuntimeAuthority -Context $Context)
            }
            catch { throw (New-IzRuntimeError 'RUNTIME_TRANSACTION_MISMATCH') }
            }
        }
        try {
            $drain = Invoke-IzRuntimeControl -Context $Context -Operation drain -RuntimeIdentity $identity -TimeoutSeconds ([Math]::Min(30,$TimeoutSeconds))
            if ($drain.status -cne 'ok' -or $drain.reason -cne 'drained' -or $drain.gate -cne 'maintenance' -or
                -not [bool]$drain.draining -or [int]$drain.active_business_requests -ne 0) { throw (New-IzRuntimeError 'RUNTIME_DRAIN_BLOCKED') }
            $shutdown = Invoke-IzRuntimeControl -Context $Context -Operation shutdown -RuntimeIdentity $identity -TimeoutSeconds ([Math]::Min(30,$TimeoutSeconds))
            if ($shutdown.status -cne 'ok' -or $shutdown.reason -cne 'shutdown_requested' -or $shutdown.gate -cne 'maintenance' -or
                [int]$shutdown.active_business_requests -ne 0) { throw (New-IzRuntimeError 'RUNTIME_SHUTDOWN_BLOCKED') }
            if (-not (Wait-IzProcessExit -ProcessIds @([int]$identity.process_id) -TimeoutSeconds $TimeoutSeconds)) {
                throw (New-IzRuntimeError 'RUNTIME_PROCESS_DID_NOT_EXIT')
            }
            return New-IzStopResult 'stopped' 'GRACEFUL_SHUTDOWN' $true $false @([int]$identity.process_id)
        } catch {
            if (-not $AllowLegacyFallback) { throw }
            $stopped = @(Stop-IzExactProcessTree -Context $Context -RootProcessId ([int]$identity.process_id) -TimeoutSeconds $TimeoutSeconds)
            return New-IzStopResult 'stopped' 'OWNED_TREE_FORCED' $false $false $stopped
        }
    } catch {
        $reason = if ($_.Exception.Data.Contains('iz_reason')) { [string]$_.Exception.Data['iz_reason'] } else { 'RUNTIME_STOP_FAILED' }
        return New-IzStopResult 'failure' $reason $false $false @()
    }
}

function Test-IzLaunchedProcessDescendant {
    param([object]$Context,[object]$CandidateRecord,[object]$LaunchRecord,[string]$ExpectedExecutablePath)
    $expected=Get-IzCanonicalPath $ExpectedExecutablePath
    if(-not $CandidateRecord -or -not $LaunchRecord -or $LaunchRecord.owner_sid -cne $Context.owner_sid -or
       $LaunchRecord.executable_path -ine $expected){return $false}
    if($CandidateRecord.started_utc -lt $LaunchRecord.started_utc.AddSeconds(-1)){return $false}
    $seen=[Collections.Generic.HashSet[int]]::new()
    $current=$CandidateRecord
    for($depth=0;$depth -lt 8;$depth++){
        if(-not $seen.Add([int]$current.process_id)){return $false}
        if([int]$current.process_id -eq [int]$LaunchRecord.process_id){
            return ([Math]::Abs(($current.started_utc-$LaunchRecord.started_utc).TotalSeconds) -le 1)
        }
        if([int]$current.parent_process_id -le 0){return $false}
        if([int]$current.parent_process_id -eq [int]$LaunchRecord.process_id){return $true}
        $current=Get-IzProcessRecord -ProcessId ([int]$current.parent_process_id)
        if(-not $current -or $current.owner_sid -cne $Context.owner_sid -or $current.executable_path -ine $expected){return $false}
    }
    return $false
}

function Start-IzOwnedRuntime {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][object]$Context,
        [Parameter(Mandatory)][ValidateSet('Installed','Candidate')][string]$RuntimeRole,
        [Guid]$TransactionId = [Guid]::Empty,
        [ValidateRange(1,120)][int]$TimeoutSeconds = 30,
        [switch]$NoBrowser
      )
      Assert-IzMaintenanceContext $Context | Out-Null
      if ($RuntimeRole -eq 'Installed') { [void](Test-IzInstalledRuntimeAuthority -Context $Context) }
      $executable = Get-IzCanonicalPath -Path (Join-Path $Context.install_root 'runtime\IZClinicalNotesAnalyzer.exe')
    $port = Get-IzConfiguredRuntimePort -Context $Context
    $existingIdentity = Read-IzRuntimeIdentity -Context $Context
    if ($existingIdentity) {
        $existingProcess = Test-IzProcessIdentity -Context $Context -Identity $existingIdentity -ExpectedExecutablePath $executable
        if ($existingProcess) {
            $existingStatus = Invoke-IzRuntimeControl -Context $Context -Operation status -RuntimeIdentity $existingIdentity -TimeoutSeconds ([Math]::Min(5,$TimeoutSeconds))
            if ($existingStatus.status -cne 'ok') { throw (New-IzRuntimeError 'RUNTIME_STATUS_INVALID') }
            if (-not $NoBrowser -and $RuntimeRole -eq 'Installed') { Start-Process ("http://127.0.0.1:{0}/" -f [int]$existingIdentity.port) | Out-Null }
            return [pscustomobject][ordered]@{schema='iz-cna-runtime-start-v1';status='already_running';process_id=[int]$existingIdentity.process_id;identity=$existingIdentity;control=$existingStatus}
        }
        Remove-Item -LiteralPath $Context.runtime_identity_path -Force
    }
    if (@(Get-IzProcessesAtPath $Context $executable).Count) { throw (New-IzRuntimeError 'RUNTIME_ALREADY_RUNNING_WITHOUT_VALID_IDENTITY') }
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $executable; $startInfo.WorkingDirectory = $Context.install_root
    $startInfo.UseShellExecute = $false; $startInfo.CreateNoWindow = $true
    $startInfo.EnvironmentVariables['IZ_CNA_PORT'] = [string]$port
    $startInfo.EnvironmentVariables['IZ_CNA_ENV_FILE'] = Join-Path $Context.data_root '.env'
    $startInfo.EnvironmentVariables['IZ_CNA_LOCAL_APP_DATA_DIR'] = $Context.data_root
    foreach ($name in @('IZ_CNA_MAINTENANCE_MODE','IZ_CNA_MAINTENANCE_JOURNAL','IZ_CNA_MAINTENANCE_TRANSACTION_ID','IZ_CNA_MAINTENANCE_OWNER_PID','IZ_CNA_MAINTENANCE_OWNER_STARTED_UTC')) {
        if ($startInfo.EnvironmentVariables.ContainsKey($name)) { $startInfo.EnvironmentVariables.Remove($name) }
    }
    if ($RuntimeRole -eq 'Candidate') {
        if ($TransactionId -eq [Guid]::Empty -or $Context.transaction_id -cne $TransactionId.ToString('N')) { throw (New-IzRuntimeError 'TRANSACTION_ID_INVALID') }
        $startInfo.EnvironmentVariables['IZ_CNA_MAINTENANCE_MODE'] = 'candidate'
        $startInfo.EnvironmentVariables['IZ_CNA_MAINTENANCE_JOURNAL'] = $Context.journal_path
        $startInfo.EnvironmentVariables['IZ_CNA_MAINTENANCE_TRANSACTION_ID'] = $TransactionId.ToString('N')
        $startInfo.EnvironmentVariables['IZ_CNA_MAINTENANCE_OWNER_PID'] = [string]$PID
        $startInfo.EnvironmentVariables['IZ_CNA_MAINTENANCE_OWNER_STARTED_UTC'] = (Get-Process -Id $PID).StartTime.ToUniversalTime().ToString('o')
    }
    $process = [Diagnostics.Process]::new(); $process.StartInfo = $startInfo
    if (-not $process.Start()) { throw (New-IzRuntimeError 'RUNTIME_START_FAILED') }
    $launchRecord=Get-IzProcessRecord -ProcessId $process.Id
    $expectedHash=Get-IzFileSha256 $executable
    if(-not $launchRecord -or $launchRecord.owner_sid -cne $Context.owner_sid -or
       $launchRecord.executable_path -ine $executable -or
       [Math]::Abs(($launchRecord.started_utc-$process.StartTime.ToUniversalTime()).TotalSeconds) -gt 1){
        try{$process.Kill();$process.WaitForExit()}catch{}
        $process.Dispose()
        throw(New-IzRuntimeError 'RUNTIME_LAUNCH_IDENTITY_MISMATCH')
    }
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds); $identity = $null
    do {
        if ($process.HasExited) { throw (New-IzRuntimeError 'RUNTIME_EXITED_DURING_START') }
        try {
            $candidate = Read-IzRuntimeIdentity -Context $Context
            if($candidate){
                $candidateRecord=Test-IzProcessIdentity -Context $Context -Identity $candidate -ExpectedExecutablePath $executable
                if($candidateRecord -and [string]$candidate.executable_sha256 -ceq $expectedHash -and
                   (Test-IzLaunchedProcessDescendant $Context $candidateRecord $launchRecord $executable)){
                    $identity=$candidate;break
                }
            }
        } catch { }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    if(-not $identity){
        try{[void](Stop-IzExactProcessTree -Context $Context -RootProcessId $process.Id -TimeoutSeconds ([Math]::Min(30,$TimeoutSeconds)))}catch{try{$process.Kill();$process.WaitForExit()}catch{}}
        $process.Dispose()
        throw(New-IzRuntimeError 'RUNTIME_IDENTITY_TIMEOUT')
    }
    [void](Test-IzProcessIdentity -Context $Context -Identity $identity -ExpectedExecutablePath $executable)
    $status = Invoke-IzRuntimeControl -Context $Context -Operation status -RuntimeIdentity $identity -TimeoutSeconds ([Math]::Min(5,$TimeoutSeconds))
    $expectedGate = if ($RuntimeRole -eq 'Candidate') { 'maintenance' } else { 'open' }
    if ($status.status -cne 'ok' -or $status.gate -cne $expectedGate) { throw (New-IzRuntimeError 'RUNTIME_STATUS_INVALID') }
    if (-not $NoBrowser -and $RuntimeRole -eq 'Installed') { Start-Process ("http://127.0.0.1:{0}/" -f [int]$identity.port) | Out-Null }
    $process.Dispose()
    return [pscustomobject][ordered]@{ schema='iz-cna-runtime-start-v1'; status='started'; process_id=[int]$identity.process_id; identity=$identity; control=$status }
}

function Test-IzRuntimeHttpSurface {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Context,[Parameter(Mandatory)][object]$RuntimeIdentity,[Parameter(Mandatory)][object]$ExpectedRelease,[object]$Manifest)
    Assert-IzMaintenanceContext $Context | Out-Null
    $base = 'http://127.0.0.1:' + [int]$RuntimeIdentity.port
    $observed = [ordered]@{}
      foreach ($route in @('/','/api/health','/api/readiness','/api/version')) {
        try { $response = Invoke-WebRequest -UseBasicParsing -Uri ($base + $route) -TimeoutSec 5 }
        catch { throw (New-IzRuntimeError 'RUNTIME_HTTP_VALIDATION_FAILED') }
        if ([int]$response.StatusCode -ne 200) { throw (New-IzRuntimeError 'RUNTIME_HTTP_VALIDATION_FAILED') }
        $observed[$route] = 200
        if ($route -eq '/api/version') {
            try { $version = $response.Content | ConvertFrom-Json } catch { throw (New-IzRuntimeError 'RUNTIME_VERSION_RESPONSE_INVALID') }
            if ($version.version -cne $ExpectedRelease.version -or $version.build -cne $ExpectedRelease.build) { throw (New-IzRuntimeError 'RUNTIME_VERSION_MISMATCH') }
          }
      }
      $businessRoute = '/api/v2/navigation'
      try {
          $businessResponse = Invoke-WebRequest -UseBasicParsing -Uri ($base + $businessRoute) -TimeoutSec 5
          $businessStatus = [int]$businessResponse.StatusCode
      } catch {
          $businessStatus = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
      }
      if ($businessStatus -ne 503) { throw (New-IzRuntimeError 'RUNTIME_MAINTENANCE_GATE_INVALID') }
      $observed[$businessRoute] = 503
      if ($Manifest) {
        $asset = @($Manifest.files | Where-Object { $_.path -like 'app/frontend/dist/assets/*' } | Select-Object -First 1)
        if ($asset.Count) {
            $relative = ([string]$asset[0].path).Substring('app/frontend/dist/assets/'.Length).Replace('\','/')
            $response = Invoke-WebRequest -UseBasicParsing -Uri ($base + '/assets/' + $relative) -TimeoutSec 5
            if ([int]$response.StatusCode -ne 200) { throw (New-IzRuntimeError 'RUNTIME_ASSET_VALIDATION_FAILED') }
            $observed['/assets/' + $relative] = 200
        }
    }
    return [pscustomobject][ordered]@{ schema='iz-cna-runtime-http-validation-v1'; status='success'; observed=$observed }
}

  Export-ModuleMember -Function Get-IzConfiguredRuntimePort,Test-IzInstalledRuntimeAuthority,Invoke-IzRuntimeControl,Start-IzOwnedRuntime,Start-IzLegacyRuntime,Stop-IzOwnedRuntime,Test-IzRuntimeHttpSurface
