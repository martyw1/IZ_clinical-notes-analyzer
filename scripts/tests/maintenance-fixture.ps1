Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function New-IzFixtureError {
    param([Parameter(Mandatory)][string]$Reason)
    $exception = [IO.InvalidDataException]::new($Reason)
    $exception.Data['iz_reason'] = $Reason
    return $exception
}

function Get-IzFixtureSha256 {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw (New-IzFixtureError 'FIXTURE_FILE_MISSING') }
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Assert-IzFixturePlainPath {
    param([Parameter(Mandatory)][string]$Path)
    $cursor = [IO.Path]::GetFullPath($Path)
    while ($cursor -and -not (Test-Path -LiteralPath $cursor)) { $cursor = Split-Path -Parent $cursor }
    while ($cursor) {
        if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw (New-IzFixtureError 'FIXTURE_REPARSE_PATH_REFUSED')
        }
        $parent = Split-Path -Parent $cursor
        if (-not $parent -or $parent -eq $cursor) { break }
        $cursor = $parent
    }
}

function New-IzMaintenanceFixture {
    param(
        [Parameter(Mandatory)][object]$HarnessRoot,
        [Parameter(Mandatory)][ValidatePattern('^(?:[BIURDAP][0-9]{2}|V00)$')][string]$CaseId,
        [switch]$ShortComponentRoot
    )
    $root = [IO.Path]::GetFullPath([string]$HarnessRoot.path)
    if ([string]$HarnessRoot.run_id -cne (Split-Path $root -Leaf) -or
        -not (Test-Path -LiteralPath ([string]$HarnessRoot.marker_path) -PathType Leaf)) {
        throw (New-IzFixtureError 'HARNESS_ROOT_NOT_VERIFIED')
    }
    Assert-IzFixturePlainPath -Path $root
    $caseRoot = Join-Path (Join-Path $root 'raw') $CaseId.ToLowerInvariant()
    if (Test-Path -LiteralPath $caseRoot) { throw (New-IzFixtureError 'FIXTURE_ALREADY_EXISTS') }
    $componentLeaf = 'iz-cna-component-' + [Guid]::NewGuid().ToString('N').Substring(0, 12)
    $componentParent = if ($ShortComponentRoot) {
        [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile, [Environment+SpecialFolderOption]::DoNotVerify)
    } else { $caseRoot }
    if ([string]::IsNullOrWhiteSpace($componentParent)) { throw (New-IzFixtureError 'FIXTURE_COMPONENT_PARENT_INVALID') }
    $componentParent = [IO.Path]::GetFullPath($componentParent).TrimEnd('\')
    Assert-IzFixturePlainPath -Path $componentParent
    $componentRoot = Join-Path $componentParent $componentLeaf
    if (Test-Path -LiteralPath $componentRoot) { throw (New-IzFixtureError 'FIXTURE_ALREADY_EXISTS') }
    $privateRoot = Join-Path $caseRoot 'private'
    $suiteRoot = Join-Path $caseRoot 'suite-evidence'
    foreach ($path in @($componentRoot, $privateRoot, $suiteRoot)) {
        $null = New-Item -ItemType Directory -Path $path -Force
    }
    $markerPath = Join-Path $caseRoot '.iz-cna-fixture-owned.json'
    $marker = [ordered]@{
        schema = 'iz-cna-maintenance-fixture-v1'
        run_id = [string]$HarnessRoot.run_id
        case_id = $CaseId
        owner_sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        case_root = $caseRoot
        component_root = $componentRoot
        created_utc = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText($markerPath, ($marker | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    return [pscustomobject][ordered]@{
        case_root = $caseRoot
        component_root = $componentRoot
        private_root = $privateRoot
        suite_root = $suiteRoot
        marker_path = $markerPath
    }
}

function Get-IzFixtureTreeSummary {
    param([Parameter(Mandatory)][string]$Path)
    $root = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    Assert-IzFixturePlainPath -Path $root
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw (New-IzFixtureError 'FIXTURE_TREE_MISSING') }
    $records = [Collections.Generic.List[string]]::new()
    [long]$length = 0
    foreach ($file in @(Get-ChildItem -LiteralPath $root -File -Force -Recurse | Sort-Object FullName)) {
        if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw (New-IzFixtureError 'FIXTURE_REPARSE_PATH_REFUSED')
        }
        $relative = $file.FullName.Substring($root.Length).TrimStart('\').Replace('\', '/')
        $records.Add("$relative`t$($file.Length)`t$(Get-IzFixtureSha256 $file.FullName)")
        $length += [long]$file.Length
    }
    $hash = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($records -join "`n"))
        $digest = ([BitConverter]::ToString($hash.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    }
    finally { $hash.Dispose() }
    return [pscustomobject][ordered]@{ file_count = $records.Count; total_length = $length; tree_sha256 = $digest }
}

function Expand-IzFixtureArchive {
    param(
        [Parameter(Mandatory)][string]$ArchivePath,
        [Parameter(Mandatory)][string]$Destination,
        [Parameter(Mandatory)][scriptblock]$ArchiveGuard
    )
    if (Test-Path -LiteralPath $Destination) { throw (New-IzFixtureError 'FIXTURE_ARCHIVE_DESTINATION_EXISTS') }
    & $ArchiveGuard $ArchivePath | Out-Null
    $null = New-Item -ItemType Directory -Path $Destination
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::ExtractToDirectory([IO.Path]::GetFullPath($ArchivePath), [IO.Path]::GetFullPath($Destination))
    }
    catch {
        if (Test-Path -LiteralPath $Destination) { Remove-Item -LiteralPath $Destination -Force -Recurse }
        throw
    }
    $packageRoots = @(Get-ChildItem -LiteralPath $Destination -Directory | Where-Object {
        (Test-Path -LiteralPath (Join-Path $_.FullName 'release-manifest.json') -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $_.FullName 'app\runtime\IZClinicalNotesAnalyzer.exe') -PathType Leaf)
    })
    if ($packageRoots.Count -eq 0 -and
        (Test-Path -LiteralPath (Join-Path $Destination 'release-manifest.json') -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $Destination 'app\runtime\IZClinicalNotesAnalyzer.exe') -PathType Leaf)) {
        return [IO.Path]::GetFullPath($Destination)
    }
    if ($packageRoots.Count -ne 1) { throw (New-IzFixtureError 'FIXTURE_PACKAGE_ROOT_AMBIGUOUS') }
    return [IO.Path]::GetFullPath($packageRoots[0].FullName)
}

function Copy-IzFixtureTree {
    param(
        [Parameter(Mandatory)][string]$Source,
        [Parameter(Mandatory)][string]$Destination
    )
    $sourceRoot = [IO.Path]::GetFullPath($Source)
    Assert-IzFixturePlainPath -Path $sourceRoot
    if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) { throw (New-IzFixtureError 'FIXTURE_TREE_MISSING') }
    if (Test-Path -LiteralPath $Destination) { throw (New-IzFixtureError 'FIXTURE_COPY_DESTINATION_EXISTS') }
    $null = New-Item -ItemType Directory -Path $Destination
    foreach ($child in @(Get-ChildItem -LiteralPath $sourceRoot -Force)) {
        if ($child.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw (New-IzFixtureError 'FIXTURE_REPARSE_PATH_REFUSED')
        }
        Copy-Item -LiteralPath $child.FullName -Destination $Destination -Recurse
    }
    return Get-IzFixtureTreeSummary -Path $Destination
}

function New-IzFixtureRuntimeEnvironment {
    param(
        [Parameter(Mandatory)][string]$ComponentRoot,
        [Parameter(Mandatory)][string]$DataRoot,
        [Parameter(Mandatory)][int]$Port
    )
    $profile = Join-Path $ComponentRoot 'UserProfile'
    $local = Join-Path $ComponentRoot 'LocalAppData'
    $roaming = Join-Path $ComponentRoot 'AppData'
    $temporary = Join-Path $ComponentRoot 'Temp'
    foreach ($path in @($profile, $local, $roaming, $temporary, $DataRoot)) {
        if (-not (Test-Path -LiteralPath $path)) { $null = New-Item -ItemType Directory -Path $path -Force }
    }
    return [ordered]@{
        USERPROFILE = $profile
        HOME = $profile
        LOCALAPPDATA = $local
        APPDATA = $roaming
        TMP = $temporary
        TEMP = $temporary
        IZ_CNA_LOCAL_APP_DATA_DIR = $DataRoot
        IZ_CNA_ENV_FILE = (Join-Path $DataRoot '.env')
        IZ_CNA_PORT = [string]$Port
    }
}

function Get-IzFixtureFreePort {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    try {
        $listener.Start()
        return [int]$listener.LocalEndpoint.Port
    }
    finally { $listener.Stop() }
}

function New-IzBeta3ComponentFixture {
    param(
        [Parameter(Mandatory)][string]$ArchivePath,
        [Parameter(Mandatory)][object]$Fixture,
        [Parameter(Mandatory)][scriptblock]$ArchiveGuard
    )
    $archiveRoot = Join-Path ([string]$Fixture.private_root) 'baseline-archive'
    $packageRoot = Expand-IzFixtureArchive -ArchivePath $ArchivePath -Destination $archiveRoot -ArchiveGuard $ArchiveGuard
    $localAppData = Join-Path ([string]$Fixture.component_root) 'LocalAppData'
    $installRoot = Join-Path $localAppData 'Programs\IZ Clinical Notes Analyzer'
    $dataRoot = Join-Path $localAppData 'IZ Clinical Notes Analyzer'
    $null = New-Item -ItemType Directory -Path (Split-Path $installRoot -Parent), $dataRoot -Force
    $programSummary = Copy-IzFixtureTree -Source (Join-Path $packageRoot 'app') -Destination $installRoot
    Copy-Item -LiteralPath (Join-Path $packageRoot 'release-manifest.json') -Destination (Join-Path $installRoot 'release-manifest.json')
    Copy-Item -LiteralPath (Join-Path $packageRoot 'installer') -Destination (Join-Path $installRoot 'installer') -Recurse
    $secrets = New-IzFixtureSecrets
    $port = Get-IzFixtureFreePort
    $environmentPath = Write-IzBeta3FixtureEnvironment -DataRoot $dataRoot -Port $port -Secrets $secrets
    $environment = New-IzFixtureRuntimeEnvironment -ComponentRoot ([string]$Fixture.component_root) -DataRoot $dataRoot -Port $port
    $executable = Join-Path $installRoot 'runtime\IZClinicalNotesAnalyzer.exe'
    return [pscustomobject]@{
        package_root = $packageRoot
        install_root = $installRoot
        data_root = $dataRoot
        executable = $executable
        executable_sha256 = Get-IzFixtureSha256 -Path $executable
        environment_path = $environmentPath
        environment = $environment
        secrets = $secrets
        port = $port
        program_summary = $programSummary
    }
}

function Start-IzFixtureRuntime {
    param(
        [Parameter(Mandatory)][string]$Executable,
        [Parameter(Mandatory)][string]$WorkingDirectory,
        [Parameter(Mandatory)][Collections.IDictionary]$Environment,
        [Parameter(Mandatory)][string]$PrivateRoot,
        [Parameter(Mandatory)][int]$Port,
        [int]$TimeoutSeconds = 90
    )
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { throw (New-IzFixtureError 'FIXTURE_EXECUTABLE_MISSING') }
    $stdoutPath = Join-Path $PrivateRoot ('runtime-' + [Guid]::NewGuid().ToString('N') + '.stdout.txt')
    $stderrPath = Join-Path $PrivateRoot ('runtime-' + [Guid]::NewGuid().ToString('N') + '.stderr.txt')
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = [IO.Path]::GetFullPath($Executable)
    $info.WorkingDirectory = [IO.Path]::GetFullPath($WorkingDirectory)
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($entry in $Environment.GetEnumerator()) { $info.EnvironmentVariables[$entry.Key] = [string]$entry.Value }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $info
    if (-not $process.Start()) { throw (New-IzFixtureError 'FIXTURE_RUNTIME_START_FAILED') }
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $health = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($process.HasExited) { throw (New-IzFixtureError 'FIXTURE_RUNTIME_EARLY_EXIT') }
        try {
            $health = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
            if ($health.status -ceq 'ok') { break }
        }
        catch { Start-Sleep -Milliseconds 400 }
    }
    if ($null -eq $health -or $health.status -cne 'ok') { throw (New-IzFixtureError 'FIXTURE_RUNTIME_TIMEOUT') }
    $listener = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort $Port -State Listen -ErrorAction Stop | Select-Object -First 1
    $listenerProcess = Get-Process -Id $listener.OwningProcess -ErrorAction Stop
    if (-not [IO.Path]::GetFullPath($listenerProcess.Path).Equals([IO.Path]::GetFullPath($Executable), [StringComparison]::OrdinalIgnoreCase)) {
        throw (New-IzFixtureError 'FIXTURE_LISTENER_IDENTITY_MISMATCH')
    }
    return [pscustomobject][ordered]@{
        process = $process
        listener_pid = [int]$listenerProcess.Id
        listener_started_utc = $listenerProcess.StartTime.ToUniversalTime().ToString('o')
        executable_sha256 = Get-IzFixtureSha256 -Path $Executable
        stdout_task = $stdoutTask
        stderr_task = $stderrTask
        stdout_path = $stdoutPath
        stderr_path = $stderrPath
        port = $Port
    }
}

function Stop-IzFixtureRuntime {
    param([Parameter(Mandatory)][object]$Runtime, [Parameter(Mandatory)][string]$ExpectedExecutable)
    $stopped = [Collections.Generic.List[int]]::new()
    foreach ($processId in @([int]$Runtime.listener_pid, [int]$Runtime.process.Id) | Sort-Object -Unique) {
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($null -eq $process) { continue }
        if (-not [IO.Path]::GetFullPath($process.Path).Equals([IO.Path]::GetFullPath($ExpectedExecutable), [StringComparison]::OrdinalIgnoreCase)) {
            throw (New-IzFixtureError 'FIXTURE_PROCESS_IDENTITY_MISMATCH')
        }
        Stop-Process -Id $processId -Force
        $null = $process.WaitForExit(10000)
        $stopped.Add($processId)
    }
    try { [IO.File]::WriteAllText($Runtime.stdout_path, [string]$Runtime.stdout_task.Result, [Text.UTF8Encoding]::new($false)) } catch { }
    try { [IO.File]::WriteAllText($Runtime.stderr_path, [string]$Runtime.stderr_task.Result, [Text.UTF8Encoding]::new($false)) } catch { }
    $remaining = @(Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort $Runtime.port -State Listen -ErrorAction SilentlyContinue)
    if ($remaining.Count -ne 0) { throw (New-IzFixtureError 'FIXTURE_LISTENER_REMAINS') }
    return @($stopped)
}

function Assert-IzFixtureCondition {
    param([bool]$Condition, [Parameter(Mandatory)][string]$Reason)
    if (-not $Condition) { throw (New-IzFixtureError $Reason) }
}

function Get-IzFixtureSha256Bytes {
    param([Parameter(Mandatory)][byte[]]$Bytes)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $algorithm.Dispose() }
}

function New-IzFixtureSecrets {
    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $applicationBytes = New-Object byte[] 48
        $encryptionBytes = New-Object byte[] 48
        $random.GetBytes($applicationBytes)
        $random.GetBytes($encryptionBytes)
    }
    finally { $random.Dispose() }
    function New-Password([string]$Suffix) { return 'QaB3!' + [Guid]::NewGuid().ToString('N') + $Suffix }
    return [pscustomobject]@{
        application_secret = [Convert]::ToBase64String($applicationBytes)
        encryption_secret = [Convert]::ToBase64String($encryptionBytes)
        bootstrap_password = New-Password '7'
        admin_password = New-Password '8'
        office_password = New-Password '9'
        counselor_password = New-Password '6'
        active_counselor_password = New-Password '5'
        viewer_password = New-Password '4'
        api_secret = New-Password '3'
        candidate_admin_password = New-Password '2'
        recovered_admin_password = New-Password '1'
    }
}

function Set-IzFixtureEnvironmentValues {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][Collections.IDictionary]$Values
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw (New-IzFixtureError 'FIXTURE_ENVIRONMENT_MISSING') }
    $lines = [Collections.Generic.List[string]]::new()
    $replaced = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($line in [IO.File]::ReadAllLines($Path)) {
        if ($line -match '^\s*([^#=\s]+)=(.*)$' -and $Values.Contains($Matches[1])) {
            if ($replaced.Add($Matches[1])) { $lines.Add("$($Matches[1])=$($Values[$Matches[1]])") }
            continue
        }
        $lines.Add($line)
    }
    foreach ($key in $Values.Keys) {
        if ($replaced.Add([string]$key)) { $lines.Add("$key=$($Values[$key])") }
    }
    [IO.File]::WriteAllText($Path, (($lines -join "`r`n") + "`r`n"), [Text.UTF8Encoding]::new($false))
    return $Path
}

function Set-IzInstalledBeta3FixtureEnvironment {
    param(
        [Parameter(Mandatory)][string]$DataRoot,
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][object]$Secrets
    )
    $path = Join-Path $DataRoot '.env'
    $original = [IO.File]::ReadAllText($path)
    if ($original -notmatch '(?m)^(IZ_CNA_)?SECRET_KEY=.+' -or
        $original -notmatch '(?m)^(IZ_CNA_)?DATA_ENCRYPTION_KEY=.+') {
        throw (New-IzFixtureError 'FIXTURE_GENERATED_KEYS_MISSING')
    }
    $values = [ordered]@{
        BACKEND_PORT = [string]$Port
        LOCAL_SQLITE_DB_PATH = 'qa-beta3-custom.sqlite3'
        BOOTSTRAP_ADMIN_USERNAME = 'qa-beta3-admin'
        BOOTSTRAP_ADMIN_PASSWORD = [string]$Secrets.bootstrap_password
        RESET_BOOTSTRAP_ADMIN_ON_STARTUP = 'false'
        LLM_ENABLED = 'false'
        EMR_API_ENABLED = 'false'
    }
    return Set-IzFixtureEnvironmentValues -Path $path -Values $values
}

function Write-IzBeta3FixtureEnvironment {
    param(
        [Parameter(Mandatory)][string]$DataRoot,
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][object]$Secrets
    )
    $path = Join-Path $DataRoot '.env'
    if (Test-Path -LiteralPath $path) { throw (New-IzFixtureError 'FIXTURE_ENVIRONMENT_EXISTS') }
    $baseUrl = "http://127.0.0.1:$Port"
    @(
        'ENVIRONMENT=local-client'
        "IZ_CNA_SECRET_KEY=$($Secrets.application_secret)"
        "IZ_CNA_DATA_ENCRYPTION_KEY=$($Secrets.encryption_secret)"
        'IZ_CNA_BOOTSTRAP_ADMIN_USERNAME=qa-beta3-admin'
        "IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD=$($Secrets.bootstrap_password)"
        'IZ_CNA_LOCAL_SQLITE_DB_PATH=qa-beta3-custom.sqlite3'
        "BACKEND_PORT=$Port"
        'ALLOWED_HOSTS=localhost,127.0.0.1'
        "FRONTEND_ORIGINS=$baseUrl"
    ) | Set-Content -LiteralPath $path -Encoding ASCII
    return $path
}

function Invoke-IzFixtureJson {
    param(
        [Parameter(Mandatory)][ValidateSet('Get', 'Post', 'Patch', 'Put')][string]$Method,
        [Parameter(Mandatory)][string]$Uri,
        [AllowNull()][object]$Body,
        [string]$Token = '',
        [int]$ExpectedStatus = 200
    )
    $parameters = @{ Method = $Method; Uri = $Uri; UseBasicParsing = $true; TimeoutSec = 20 }
    if ($Token) { $parameters.Headers = @{ Authorization = "Bearer $Token" } }
    if ($null -ne $Body) {
        $parameters.ContentType = 'application/json'
        $parameters.Body = $Body | ConvertTo-Json -Depth 20 -Compress
    }
    $response = Invoke-WebRequest @parameters
    Assert-IzFixtureCondition ([int]$response.StatusCode -eq $ExpectedStatus) 'FIXTURE_API_STATUS_MISMATCH'
    if ([string]::IsNullOrWhiteSpace($response.Content)) { return $null }
    return ($response.Content | ConvertFrom-Json)
}

function Invoke-IzFixtureExpectedStatus {
    param([string]$Method, [string]$Uri, [AllowNull()][object]$Body, [string]$Token, [int]$ExpectedStatus)
    try {
        $null = Invoke-IzFixtureJson -Method $Method -Uri $Uri -Body $Body -Token $Token -ExpectedStatus $ExpectedStatus
        return $ExpectedStatus
    }
    catch {
        $response = $_.Exception.Response
        if ($null -ne $response -and [int]$response.StatusCode -eq $ExpectedStatus) { return $ExpectedStatus }
        throw
    }
}

function Invoke-IzFixtureUpload {
    param([string]$BaseUrl, [string]$Token, [string]$PatientId, [string]$FileName, [string]$Text)
    Add-Type -AssemblyName System.Net.Http
    $client = [Net.Http.HttpClient]::new()
    $content = [Net.Http.MultipartFormDataContent]::new()
    try {
        $client.Timeout = [TimeSpan]::FromSeconds(30)
        $client.DefaultRequestHeaders.Authorization = [Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', $Token)
        $content.Add([Net.Http.StringContent]::new($PatientId), 'patient_id')
        $content.Add([Net.Http.StringContent]::new('false'), 'confirm_patient_id_correction')
        $fileContent = [Net.Http.ByteArrayContent]::new([Text.Encoding]::UTF8.GetBytes($Text))
        $fileContent.Headers.ContentType = [Net.Http.Headers.MediaTypeHeaderValue]::new('text/plain')
        $content.Add($fileContent, 'file', $FileName)
        $response = $client.PostAsync("$BaseUrl/api/v2/manual-uploads/treatment-plan-file", $content).GetAwaiter().GetResult()
        $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        Assert-IzFixtureCondition ([int]$response.StatusCode -eq 201) 'FIXTURE_UPLOAD_FAILED'
        $value = $body | ConvertFrom-Json
        $value | Add-Member -MemberType NoteProperty -Name http_status -Value ([int]$response.StatusCode) -Force
        return $value
    }
    finally { $content.Dispose(); $client.Dispose() }
}

function Get-IzFixtureSemanticDigest {
    param(
        [Parameter(Mandatory)][object[]]$Users,
        [Parameter(Mandatory)][object[]]$Plans
    )
    $userRows = @($Users | Sort-Object username | ForEach-Object {
        [ordered]@{
            username = [string]$_.username
            role = [string]$_.role
            must_reset_password = [bool]$_.must_reset_password
            is_active = [bool]$_.is_active
        }
    })
    $planRows = @($Plans | Sort-Object plan_version_id | ForEach-Object {
        [ordered]@{
            patient_id = [string]$_.patient_id
            patient_record_id = [int]$_.patient_record_id
            plan_version_id = [int]$_.plan_version_id
            treatment_plan_id = [string]$_.treatment_plan_id
            source_mode = [string]$_.source_mode
        }
    })
    $json = [ordered]@{ users = $userRows; plans = $planRows } | ConvertTo-Json -Depth 8 -Compress
    return Get-IzFixtureSha256Bytes ([Text.UTF8Encoding]::new($false).GetBytes($json))
}

function Initialize-IzBeta3SemanticFixture {
    param(
        [Parameter(Mandatory)][string]$BaseUrl,
        [Parameter(Mandatory)][string]$DataRoot,
        [Parameter(Mandatory)][object]$Secrets
    )
    $bootstrap = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/auth/login" -Body @{
        username = 'qa-beta3-admin'; password = $Secrets.bootstrap_password
    }
    Assert-IzFixtureCondition ($bootstrap.must_reset_password -eq $true) 'FIXTURE_BOOTSTRAP_STATE_INVALID'
    $changed = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/users/me/change-password" -Token $bootstrap.access_token -Body @{
        current_password = $Secrets.bootstrap_password; new_password = $Secrets.admin_password
    }
    Assert-IzFixtureCondition ($changed.must_reset_password -eq $false) 'FIXTURE_ADMIN_ACTIVATION_FAILED'
    $admin = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/auth/login" -Body @{
        username = 'qa-beta3-admin'; password = $Secrets.admin_password
    }
    $adminToken = [string]$admin.access_token
    $office = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/users" -Token $adminToken -Body @{
        username = 'qa-beta3-office'; full_name = 'Synthetic Office Manager'; role = 'office_manager'; password = $Secrets.office_password
    }
    $counselor = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/users" -Token $adminToken -Body @{
        username = 'qa-beta3-counselor'; full_name = 'Synthetic Counselor'; role = 'counselor'; password = $Secrets.counselor_password
    }
    $viewer = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/users" -Token $adminToken -Body @{
        username = 'qa-beta3-viewer'; full_name = 'Synthetic Viewer'; role = 'viewer'; password = $Secrets.viewer_password
    }
    Assert-IzFixtureCondition ($office.must_reset_password -and $counselor.must_reset_password -and $viewer.must_reset_password) 'FIXTURE_STAFF_STATE_INVALID'
    $facilities = @(Invoke-IzFixtureJson -Method Get -Uri "$BaseUrl/api/facilities" -Token $adminToken -Body $null)
    Assert-IzFixtureCondition ($facilities.Count -gt 0) 'FIXTURE_FACILITY_MISSING'
    $facilityId = [int]$facilities[0].id
    $null = Invoke-IzFixtureJson -Method Put -Uri "$BaseUrl/api/users/$($counselor.id)/facilities/$facilityId" -Token $adminToken -Body $null
    $null = Invoke-IzFixtureJson -Method Put -Uri "$BaseUrl/api/users/$($viewer.id)/facilities/$facilityId" -Token $adminToken -Body $null
    $counselorLogin = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/auth/login" -Body @{
        username = 'qa-beta3-counselor'; password = $Secrets.counselor_password
    }
    $counselorChanged = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/users/me/change-password" -Token $counselorLogin.access_token -Body @{
        current_password = $Secrets.counselor_password; new_password = $Secrets.active_counselor_password
    }
    $counselorToken = [string]$counselorChanged.access_token
    $settings = Invoke-IzFixtureJson -Method Patch -Uri "$BaseUrl/api/settings" -Token $adminToken -Body @{
        organization_name = 'Synthetic QA Organization'; facility_timezone = 'America/New_York'
        treatment_plan_master_due_days = 10; treatment_plan_php_review_interval_days = 14
        treatment_plan_iop_op_review_interval_days = 30; treatment_plan_loc_change_window_days = 3
        treatment_plan_loc_change_window_validated = $false
    }
    $apiConfiguration = Invoke-IzFixtureJson -Method Patch -Uri "$BaseUrl/api/api-configuration" -Token $adminToken -Body @{
        vendor_name = 'Synthetic Disabled API'; api_base_url = 'https://synthetic.invalid'
        openapi_url = 'https://synthetic.invalid/openapi.json'; token_url = 'https://synthetic.invalid/token'
        client_id = 'synthetic-client-id'; client_secret = $Secrets.api_secret; token_auth_style = 'body'
        scopes = 'synthetic.read'; api_version = '1.0'; treatment_plan_start_date = '2026-08-01T00:00:00+00:00'
        pagination_limit = 25; sync_limit = 10; requests_per_minute = 30; timeout_seconds = 2
        api_enabled = $false; treatment_plan_sync_enabled = $false; treatment_plan_sync_approved = $false
    }
    Assert-IzFixtureCondition ($apiConfiguration.client_id_configured -and $apiConfiguration.client_secret_configured -and
        -not $apiConfiguration.api_enabled -and -not $apiConfiguration.treatment_plan_sync_enabled -and
        -not $apiConfiguration.treatment_plan_sync_approved) 'FIXTURE_API_GATE_INVALID'
    Assert-IzFixtureCondition ('client_secret' -notin @($apiConfiguration.PSObject.Properties.Name)) 'FIXTURE_API_SECRET_EXPOSED'
    $workflow = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/workflow-definitions" -Token $adminToken -ExpectedStatus 201 -Body @{
        workflow_key = 'qa-beta3-upgrade'; display_name = 'Synthetic Upgrade Workflow'; description = 'Synthetic upgrade baseline.'
    }
    $workflowVersion = @($workflow.versions)[0]
    $published = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/workflow-definitions/$($workflow.id)/versions/$($workflowVersion.id)/publish" -Token $adminToken -Body @{}
    Assert-IzFixtureCondition ($published.current_version.status -eq 'published') 'FIXTURE_WORKFLOW_PUBLISH_FAILED'
    $sources = @(
        (@('MRN: QA-BETA3-001', 'Current Level of Care: PHP', 'Admission Date: 2026-08-01', 'Service Date: 2026-08-05', 'Original Plan Reference: QA-REF-001', 'Intervention: Synthetic baseline evidence version one.') -join "`n"),
        (@('MRN: QA-BETA3-001', 'Current Level of Care: IOP', 'Admission Date: 2026-08-01', 'Service Date: 2026-08-20', 'Original Plan Reference: QA-REF-002', 'Intervention: Synthetic baseline evidence version two.') -join "`n"),
        (@('MRN: QA-BETA3-002', 'Admission Date: 2026-08-12', 'Original Plan Reference: QA-REF-003', 'Intervention: Synthetic incomplete evidence for deterministic review.') -join "`n")
    )
    $uploads = @(
        Invoke-IzFixtureUpload -BaseUrl $BaseUrl -Token $adminToken -PatientId 'QA-BETA3-001' -FileName 'synthetic-baseline-one.txt' -Text $sources[0]
        Invoke-IzFixtureUpload -BaseUrl $BaseUrl -Token $adminToken -PatientId 'QA-BETA3-001' -FileName 'synthetic-baseline-two.txt' -Text $sources[1]
        Invoke-IzFixtureUpload -BaseUrl $BaseUrl -Token $adminToken -PatientId 'QA-BETA3-002' -FileName 'synthetic-baseline-three.txt' -Text $sources[2]
    )
    foreach ($upload in $uploads) {
        Assert-IzFixtureCondition ($upload.encrypted_at_rest -and $upload.source_file_archived -and $upload.criteria_total -eq 42) 'FIXTURE_UPLOAD_CONTRACT_INVALID'
    }
    $selected = $uploads[1]
    $assignmentUri = "$BaseUrl/api/patient-assignments/QA-BETA3-001/qa-beta3-counselor?patient_record_id=$($selected.patient_record_id)&source_mode=manual_upload"
    $assignment = Invoke-IzFixtureJson -Method Put -Uri $assignmentUri -Token $adminToken -Body $null
    Assert-IzFixtureCondition ($assignment.is_active -eq $true) 'FIXTURE_ASSIGNMENT_FAILED'
    $actionBody = @{
        plan_version_id = [int]$selected.plan_version_id; patient_record_id = [int]$selected.patient_record_id
        source_mode = 'manual_upload'; treatment_plan_id = [string]$selected.treatment_plan_id
        criterion_id = 'confirm_current_loc'; action = 'return_for_correction'
        comment = 'Synthetic correction requested for upgrade baseline.'; override_reason = ''
        assigned_counselor_username = 'qa-beta3-counselor'
    }
    $action = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/v2/treatment-plans/QA-BETA3-001/manager-actions" -Token $adminToken -Body $actionBody
    Assert-IzFixtureCondition ($action.status -eq 'saved') 'FIXTURE_MANAGER_ACTION_FAILED'
    $corrections = Invoke-IzFixtureJson -Method Get -Uri "$BaseUrl/api/v2/corrections" -Token $counselorToken -Body $null
    Assert-IzFixtureCondition (@($corrections.items).Count -eq 1) 'FIXTURE_CORRECTION_QUEUE_INVALID'
    $deniedBody = @{} + $actionBody
    $deniedBody.action = 'override'
    $deniedBody.override_reason = 'Synthetic denied action'
    $denied = Invoke-IzFixtureExpectedStatus -Method Post -Uri "$BaseUrl/api/v2/treatment-plans/QA-BETA3-001/manager-actions" `
        -Token $counselorToken -ExpectedStatus 403 -Body $deniedBody
    Assert-IzFixtureCondition ($denied -eq 403) 'FIXTURE_ROLE_DENIAL_FAILED'
    $downloadUri = "$BaseUrl/api/v2/treatment-plans/QA-BETA3-001/source-documents/$($selected.source_file_id)/download?plan_version_id=$($selected.plan_version_id)&patient_record_id=$($selected.patient_record_id)&source_mode=manual_upload"
    $download = Invoke-WebRequest -Method Get -Uri $downloadUri -UseBasicParsing -Headers @{ Authorization = "Bearer $adminToken" } -TimeoutSec 20
    $downloadHash = Get-IzFixtureSha256Bytes ([Text.Encoding]::UTF8.GetBytes([string]$download.Content))
    $expectedDownloadHash = Get-IzFixtureSha256Bytes ([Text.Encoding]::UTF8.GetBytes($sources[1]))
    Assert-IzFixtureCondition ($downloadHash -ceq $expectedDownloadHash) 'FIXTURE_DECRYPTION_FAILED'
    $plans = Invoke-IzFixtureJson -Method Get -Uri "$BaseUrl/api/v2/treatment-plans" -Token $adminToken -Body $null
    $users = @(Invoke-IzFixtureJson -Method Get -Uri "$BaseUrl/api/users" -Token $adminToken -Body $null)
    $audit = Invoke-IzFixtureJson -Method Get -Uri "$BaseUrl/api/audit/verify" -Token $adminToken -Body $null
    $cipherFiles = @(Get-ChildItem -LiteralPath (Join-Path $DataRoot 'manual-uploads') -File -Filter '*.izcna1')
    Assert-IzFixtureCondition (@($plans.items).Count -eq 3 -and $users.Count -eq 4 -and $audit.valid -eq $true -and $cipherFiles.Count -eq 3) 'FIXTURE_SEMANTIC_COUNTS_INVALID'
    foreach ($file in $cipherFiles) {
        $cipherText = [Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes($file.FullName))
        Assert-IzFixtureCondition ($cipherText -notmatch 'QA-BETA3-00[12]|Synthetic baseline evidence') 'FIXTURE_PLAINTEXT_AT_REST'
    }
    Assert-IzFixtureCondition (Test-Path -LiteralPath (Join-Path $DataRoot 'qa-beta3-custom.sqlite3') -PathType Leaf) 'FIXTURE_CUSTOM_DATABASE_MISSING'
    Assert-IzFixtureCondition (-not (Test-Path -LiteralPath (Join-Path $DataRoot 'clinical-notes-analyzer-v2.sqlite3'))) 'FIXTURE_DEFAULT_DATABASE_CREATED'
    return [pscustomobject][ordered]@{
        schema = 'iz-cna-beta3-live-fixture-v1'
        account_count = $users.Count
        roles = @($users.role | Sort-Object)
        plan_version_count = @($plans.items).Count
        patient_count = @($plans.items.patient_id | Sort-Object -Unique).Count
        encrypted_source_count = $cipherFiles.Count
        decrypted_source_sha256 = $downloadHash
        correction_queue_count = @($corrections.items).Count
        counselor_denial_status = $denied
        workflow_key = [string]$published.workflow_key
        timezone = [string]$settings.facility_timezone
        loc_change_validated = [bool]$settings.treatment_plan_loc_change_window_validated
        audit_valid = [bool]$audit.valid
        audit_event_count = [int]$audit.event_count
        environment_sha256 = Get-IzFixtureSha256 -Path (Join-Path $DataRoot '.env')
        semantic_identity_sha256 = Get-IzFixtureSemanticDigest -Users $users -Plans @($plans.items)
        selected_database = 'qa-beta3-custom.sqlite3'
    }
}

function Test-IzUpgradedSemanticFixture {
    param(
        [Parameter(Mandatory)][string]$BaseUrl,
        [Parameter(Mandatory)][string]$DataRoot,
        [Parameter(Mandatory)][object]$Secrets,
        [Parameter(Mandatory)][object]$Baseline
    )
    $admin = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/auth/login" -Body @{
        username = 'qa-beta3-admin'; password = $Secrets.admin_password
    }
    Assert-IzFixtureCondition ($admin.must_reset_password -eq $false) 'UPGRADE_ADMIN_LOGIN_FAILED'
    $adminToken = [string]$admin.access_token
    $counselor = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/auth/login" -Body @{
        username = 'qa-beta3-counselor'; password = $Secrets.active_counselor_password
    }
    Assert-IzFixtureCondition ($counselor.must_reset_password -eq $false) 'UPGRADE_COUNSELOR_LOGIN_FAILED'
    $users = @(Invoke-IzFixtureJson -Method Get -Uri "$BaseUrl/api/users" -Token $adminToken -Body $null)
    $settings = Invoke-IzFixtureJson -Method Get -Uri "$BaseUrl/api/settings" -Token $adminToken -Body $null
    $apiConfiguration = Invoke-IzFixtureJson -Method Get -Uri "$BaseUrl/api/api-configuration" -Token $adminToken -Body $null
    $workflows = @(Invoke-IzFixtureJson -Method Get -Uri "$BaseUrl/api/workflow-definitions" -Token $adminToken -Body $null)
    $plans = Invoke-IzFixtureJson -Method Get -Uri "$BaseUrl/api/v2/treatment-plans" -Token $adminToken -Body $null
    $corrections = Invoke-IzFixtureJson -Method Get -Uri "$BaseUrl/api/v2/corrections" -Token $counselor.access_token -Body $null
    $audit = Invoke-IzFixtureJson -Method Get -Uri "$BaseUrl/api/audit/verify" -Token $adminToken -Body $null
    $cipherFiles = @(Get-ChildItem -LiteralPath (Join-Path $DataRoot 'manual-uploads') -File -Filter '*.izcna1')
    $roles = @($users.role | Sort-Object)
    $semanticIdentity = Get-IzFixtureSemanticDigest -Users $users -Plans @($plans.items)
    Assert-IzFixtureCondition ($users.Count -eq $Baseline.account_count -and @($plans.items).Count -eq $Baseline.plan_version_count -and
        @($plans.items.patient_id | Sort-Object -Unique).Count -eq $Baseline.patient_count -and
        $cipherFiles.Count -eq $Baseline.encrypted_source_count -and @($corrections.items).Count -eq $Baseline.correction_queue_count -and
        @(Compare-Object $roles @($Baseline.roles)).Count -eq 0 -and
        $semanticIdentity -ceq $Baseline.semantic_identity_sha256) 'UPGRADE_SEMANTIC_COUNTS_CHANGED'
    Assert-IzFixtureCondition ($settings.facility_timezone -ceq $Baseline.timezone -and
        $settings.treatment_plan_loc_change_window_validated -eq $false) 'UPGRADE_SETTINGS_CHANGED'
    Assert-IzFixtureCondition ($apiConfiguration.client_id_configured -and $apiConfiguration.client_secret_configured -and
        -not $apiConfiguration.api_enabled -and -not $apiConfiguration.treatment_plan_sync_enabled -and
        -not $apiConfiguration.treatment_plan_sync_approved -and
        'client_secret' -notin @($apiConfiguration.PSObject.Properties.Name)) 'UPGRADE_API_GATE_CHANGED'
    Assert-IzFixtureCondition (@($workflows | Where-Object workflow_key -eq $Baseline.workflow_key).Count -eq 1) 'UPGRADE_WORKFLOW_MISSING'
    Assert-IzFixtureCondition ($audit.valid -eq $true -and [int]$audit.event_count -ge [int]$Baseline.audit_event_count) 'UPGRADE_AUDIT_INVALID'
    Assert-IzFixtureCondition ((Get-IzFixtureSha256 -Path (Join-Path $DataRoot '.env')) -ceq $Baseline.environment_sha256) 'UPGRADE_ENVIRONMENT_CHANGED'
    Assert-IzFixtureCondition (Test-Path -LiteralPath (Join-Path $DataRoot $Baseline.selected_database) -PathType Leaf) 'UPGRADE_DATABASE_CHANGED'
    Assert-IzFixtureCondition (-not (Test-Path -LiteralPath (Join-Path $DataRoot 'clinical-notes-analyzer-v2.sqlite3'))) 'UPGRADE_DEFAULT_DATABASE_CREATED'
    return [pscustomobject][ordered]@{
        schema = 'iz-cna-upgraded-live-fixture-v1'
        admin_login = 'passed'; counselor_login = 'passed'; account_count = $users.Count
        plan_version_count = @($plans.items).Count; patient_count = @($plans.items.patient_id | Sort-Object -Unique).Count
        encrypted_source_count = $cipherFiles.Count; correction_queue_count = @($corrections.items).Count
        roles_unchanged = $true; settings_unchanged = $true; api_gates_closed = $true
        workflow_preserved = $true; audit_valid = $true; audit_event_count = [int]$audit.event_count
        environment_unchanged = $true; semantic_identity_unchanged = $true; custom_database_reused = $true
    }
}

function Test-IzCandidateLiveApiRoundTrip {
    param(
        [Parameter(Mandatory)][string]$BaseUrl,
        [Parameter(Mandatory)][string]$DataRoot,
        [Parameter(Mandatory)][object]$Secrets
    )
    $admin = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/auth/login" -Body @{
        username = 'qa-beta3-admin'; password = $Secrets.admin_password
    }
    $counselor = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/auth/login" -Body @{
        username = 'qa-beta3-counselor'; password = $Secrets.active_counselor_password
    }
    $source = @(
        'MRN: QA-CANDIDATE-003'
        'Current Level of Care: IOP'
        'Admission Date: 2026-09-01'
        'Service Date: 2026-09-10'
        'Original Plan Reference: QA-CANDIDATE-REF-004'
        'Intervention: Synthetic candidate runtime encrypted readback evidence.'
    ) -join "`n"
    $upload = Invoke-IzFixtureUpload -BaseUrl $BaseUrl -Token ([string]$admin.access_token) `
        -PatientId 'QA-CANDIDATE-003' -FileName 'synthetic-candidate-roundtrip.txt' -Text $source
    Assert-IzFixtureCondition ($upload.encrypted_at_rest -and $upload.source_file_archived -and
        [int]$upload.criteria_total -eq 42) 'CANDIDATE_UPLOAD_CONTRACT_INVALID'
    $downloadUri = "$BaseUrl/api/v2/treatment-plans/QA-CANDIDATE-003/source-documents/$($upload.source_file_id)/download?plan_version_id=$($upload.plan_version_id)&patient_record_id=$($upload.patient_record_id)&source_mode=manual_upload"
    $download = Invoke-WebRequest -Method Get -Uri $downloadUri -UseBasicParsing `
        -Headers @{ Authorization = "Bearer $($admin.access_token)" } -TimeoutSec 20
    $downloadHash = Get-IzFixtureSha256Bytes ([Text.Encoding]::UTF8.GetBytes([string]$download.Content))
    $expectedHash = Get-IzFixtureSha256Bytes ([Text.Encoding]::UTF8.GetBytes($source))
    Assert-IzFixtureCondition ($downloadHash -ceq $expectedHash) 'CANDIDATE_DECRYPTED_READBACK_MISMATCH'
    $plans = Invoke-IzFixtureJson -Method Get -Uri "$BaseUrl/api/v2/treatment-plans" -Token ([string]$admin.access_token) -Body $null
    $stored = @($plans.items | Where-Object {
        [int]$_.plan_version_id -eq [int]$upload.plan_version_id -and $_.patient_id -ceq 'QA-CANDIDATE-003'
    })
    Assert-IzFixtureCondition ($stored.Count -eq 1) 'CANDIDATE_TREATMENT_PLAN_NOT_STORED'
    $existing = @($plans.items | Where-Object patient_id -ceq 'QA-BETA3-001' | Select-Object -First 1)
    Assert-IzFixtureCondition ($existing.Count -eq 1) 'CANDIDATE_ROLE_FIXTURE_MISSING'
    $denied = Invoke-IzFixtureExpectedStatus -Method Post `
        -Uri "$BaseUrl/api/v2/treatment-plans/QA-BETA3-001/manager-actions" `
        -Token ([string]$counselor.access_token) -ExpectedStatus 403 -Body @{
            plan_version_id = [int]$existing[0].plan_version_id
            patient_record_id = [int]$existing[0].patient_record_id
            source_mode = [string]$existing[0].source_mode
            treatment_plan_id = [string]$existing[0].treatment_plan_id
            criterion_id = 'confirm_current_loc'
            action = 'override'
            comment = 'Synthetic candidate role denial probe.'
            override_reason = 'Synthetic denied candidate action.'
        }
    $workflows = @(Invoke-IzFixtureJson -Method Get -Uri "$BaseUrl/api/workflow-definitions" -Token ([string]$admin.access_token) -Body $null)
    $audit = Invoke-IzFixtureJson -Method Get -Uri "$BaseUrl/api/audit/verify" -Token ([string]$admin.access_token) -Body $null
    $cipherFiles = @(Get-ChildItem -LiteralPath (Join-Path $DataRoot 'manual-uploads') -File -Filter '*.izcna1')
    Assert-IzFixtureCondition ($denied -eq 403 -and
        @($workflows | Where-Object workflow_key -ceq 'qa-beta3-upgrade').Count -eq 1 -and
        $audit.valid -eq $true -and $cipherFiles.Count -eq 4) 'CANDIDATE_STORED_OUTCOME_INVALID'
    foreach ($file in $cipherFiles) {
        $cipherText = [Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes($file.FullName))
        Assert-IzFixtureCondition ($cipherText -notmatch 'QA-CANDIDATE-003|candidate runtime encrypted readback') 'CANDIDATE_PLAINTEXT_AT_REST'
    }
    return [pscustomobject][ordered]@{
        schema = 'iz-cna-candidate-live-api-roundtrip-v1'
        login = 'passed'
        upload_status = [int]$upload.http_status
        encrypted_at_rest = $true
        decrypted_readback_sha256 = $downloadHash
        treatment_plan_stored = $true
        plan_version_id = [int]$upload.plan_version_id
        patient_record_id = [int]$upload.patient_record_id
        source_file_id = [string]$upload.source_file_id
        criteria_total = [int]$upload.criteria_total
        workflow_preserved = $true
        counselor_denial_status = $denied
        encrypted_source_count = $cipherFiles.Count
        audit_valid = $true
    }
}

function Test-IzCandidateLiveApiPreserved {
    param(
        [Parameter(Mandatory)][string]$BaseUrl,
        [Parameter(Mandatory)][string]$DataRoot,
        [Parameter(Mandatory)][object]$Secrets,
        [Parameter(Mandatory)][object]$RoundTrip
    )
    $admin = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/auth/login" -Body @{
        username = 'qa-beta3-admin'; password = $Secrets.admin_password
    }
    $counselor = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/auth/login" -Body @{
        username = 'qa-beta3-counselor'; password = $Secrets.active_counselor_password
    }
    $plans = Invoke-IzFixtureJson -Method Get -Uri "$BaseUrl/api/v2/treatment-plans" -Token ([string]$admin.access_token) -Body $null
    $stored = @($plans.items | Where-Object {
        [int]$_.plan_version_id -eq [int]$RoundTrip.plan_version_id -and
        [int]$_.patient_record_id -eq [int]$RoundTrip.patient_record_id
    })
    Assert-IzFixtureCondition ($stored.Count -eq 1) 'REINSTALL_TREATMENT_PLAN_NOT_PRESERVED'
    $downloadUri = "$BaseUrl/api/v2/treatment-plans/QA-CANDIDATE-003/source-documents/$($RoundTrip.source_file_id)/download?plan_version_id=$($RoundTrip.plan_version_id)&patient_record_id=$($RoundTrip.patient_record_id)&source_mode=manual_upload"
    $download = Invoke-WebRequest -Method Get -Uri $downloadUri -UseBasicParsing `
        -Headers @{ Authorization = "Bearer $($admin.access_token)" } -TimeoutSec 20
    $downloadHash = Get-IzFixtureSha256Bytes ([Text.Encoding]::UTF8.GetBytes([string]$download.Content))
    Assert-IzFixtureCondition ($downloadHash -ceq [string]$RoundTrip.decrypted_readback_sha256) 'REINSTALL_DECRYPTED_READBACK_MISMATCH'
    $existing = @($plans.items | Where-Object patient_id -ceq 'QA-BETA3-001' | Select-Object -First 1)
    Assert-IzFixtureCondition ($existing.Count -eq 1) 'REINSTALL_ROLE_FIXTURE_MISSING'
    $denied = Invoke-IzFixtureExpectedStatus -Method Post `
        -Uri "$BaseUrl/api/v2/treatment-plans/QA-BETA3-001/manager-actions" `
        -Token ([string]$counselor.access_token) -ExpectedStatus 403 -Body @{
            plan_version_id = [int]$existing[0].plan_version_id
            patient_record_id = [int]$existing[0].patient_record_id
            source_mode = [string]$existing[0].source_mode
            treatment_plan_id = [string]$existing[0].treatment_plan_id
            criterion_id = 'confirm_current_loc'; action = 'override'
            comment = 'Synthetic reinstall role denial probe.'; override_reason = 'Synthetic denied reinstall action.'
        }
    $workflows = @(Invoke-IzFixtureJson -Method Get -Uri "$BaseUrl/api/workflow-definitions" -Token ([string]$admin.access_token) -Body $null)
    $audit = Invoke-IzFixtureJson -Method Get -Uri "$BaseUrl/api/audit/verify" -Token ([string]$admin.access_token) -Body $null
    $cipherFiles = @(Get-ChildItem -LiteralPath (Join-Path $DataRoot 'manual-uploads') -File -Filter '*.izcna1')
    Assert-IzFixtureCondition (@($plans.items).Count -eq 4 -and $cipherFiles.Count -eq 4 -and $denied -eq 403 -and
        @($workflows | Where-Object workflow_key -ceq 'qa-beta3-upgrade').Count -eq 1 -and $audit.valid -eq $true) `
        'REINSTALL_STORED_OUTCOME_INVALID'
    foreach ($file in $cipherFiles) {
        $cipherText = [Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes($file.FullName))
        Assert-IzFixtureCondition ($cipherText -notmatch 'QA-CANDIDATE-003|candidate runtime encrypted readback') 'REINSTALL_PLAINTEXT_AT_REST'
    }
    return [pscustomobject][ordered]@{
        schema = 'iz-cna-candidate-reinstall-live-api-v1'
        login = 'passed'; treatment_plan_count = @($plans.items).Count
        encrypted_source_count = $cipherFiles.Count; decrypted_readback_sha256 = $downloadHash
        workflow_preserved = $true; counselor_denial_status = $denied; audit_valid = $true
    }
}

function Invoke-IzCandidateCredentialRotation {
    param(
        [Parameter(Mandatory)][string]$BaseUrl,
        [Parameter(Mandatory)][object]$Secrets
    )
    $login = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/auth/login" -Body @{
        username = 'qa-beta3-admin'; password = $Secrets.admin_password
    }
    $changed = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/users/me/change-password" -Token $login.access_token -Body @{
        current_password = $Secrets.admin_password; new_password = $Secrets.candidate_admin_password
    }
    Assert-IzFixtureCondition ($changed.must_reset_password -eq $false) 'CANDIDATE_PASSWORD_CHANGE_FAILED'
    $relogin = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/auth/login" -Body @{
        username = 'qa-beta3-admin'; password = $Secrets.candidate_admin_password
    }
    Assert-IzFixtureCondition ($relogin.must_reset_password -eq $false) 'CANDIDATE_PASSWORD_RELOGIN_FAILED'
    return [pscustomobject][ordered]@{
        schema = 'iz-cna-candidate-credential-observation-v1'
        initial_login = 'passed'
        password_change = 'passed'
        replacement_login = 'passed'
    }
}

function New-IzBeta4RecoveryFixture {
    param(
        [Parameter(Mandatory)][string]$BaseUrl,
        [Parameter(Mandatory)][object]$Secrets
    )
    $login = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/auth/login" -Body @{
        username = 'qa-beta3-admin'; password = $Secrets.admin_password
    }
    $generated = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/users/me/recovery-code" -Token $login.access_token -Body @{
        current_password = $Secrets.admin_password
    }
    $status = Invoke-IzFixtureJson -Method Get -Uri "$BaseUrl/api/users/me/recovery-code" -Token $login.access_token -Body $null
    Assert-IzFixtureCondition ($status.configured -eq $true -and -not [string]::IsNullOrWhiteSpace($generated.recovery_code)) 'RECOVERY_FIXTURE_SETUP_FAILED'
    return [pscustomobject]@{ recovery_code = [string]$generated.recovery_code }
}

function Test-IzBeta4RecoveryPreserved {
    param(
        [Parameter(Mandatory)][string]$BaseUrl,
        [Parameter(Mandatory)][object]$Secrets,
        [Parameter(Mandatory)][object]$RecoveryFixture
    )
    $login = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/auth/login" -Body @{
        username = 'qa-beta3-admin'; password = $Secrets.admin_password
    }
    $status = Invoke-IzFixtureJson -Method Get -Uri "$BaseUrl/api/users/me/recovery-code" -Token $login.access_token -Body $null
    Assert-IzFixtureCondition ($status.configured -eq $true) 'RECOVERY_CONFIGURATION_NOT_PRESERVED'
    $null = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/auth/recover-password" -Body @{
        username = 'qa-beta3-admin'; recovery_code = $RecoveryFixture.recovery_code; new_password = $Secrets.recovered_admin_password
    }
    $reuse = Invoke-IzFixtureExpectedStatus -Method Post -Uri "$BaseUrl/api/auth/recover-password" -ExpectedStatus 400 -Body @{
        username = 'qa-beta3-admin'; recovery_code = $RecoveryFixture.recovery_code; new_password = $Secrets.candidate_admin_password
    }
    $relogin = Invoke-IzFixtureJson -Method Post -Uri "$BaseUrl/api/auth/login" -Body @{
        username = 'qa-beta3-admin'; password = $Secrets.recovered_admin_password
    }
    Assert-IzFixtureCondition ($reuse -eq 400 -and $relogin.must_reset_password -eq $false) 'RECOVERY_REUSE_BOUNDARY_FAILED'
    return [pscustomobject][ordered]@{
        schema = 'iz-cna-recovery-preservation-observation-v1'
        configured_after_upgrade = $true
        recovered_login = 'passed'
        one_time_reuse_status = $reuse
    }
}
