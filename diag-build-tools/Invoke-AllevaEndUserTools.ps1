<#
.SYNOPSIS
  End-user friendly Alleva EMR terminal tool for R3 patient roster and treatment-plan pulls.

.DESCRIPTION
  This script is intentionally separate from Invoke-AllevaRemoteDiagnostics.ps1.
  Keep the existing diagnostic script for technical testing. Use this script when a
  non-technical user needs a guided PowerShell menu to:

    - Pull the most recent active patient roster.
    - Pull treatment plans and map them to associated patients.
    - Pick a patient, see available treatment plans, and pull full detail for one or more plans.
    - View patient record details.
    - Export roster, patient records, plan indexes, and full treatment-plan fields to CSV.
    - Keep detailed local logs for every session, menu action, API call, export, error, start, and exit.

  It calls Alleva directly. It does not log into the IZ Clinical Notes Analyzer app.
  It reuses the same local settings file as the current diagnostic script:

    alleva-remote-diagnostics.local.json

.PHI WARNING
  Logs and exports can contain patient data. Keep the diag-build-tools folder local,
  access-controlled, and out of Git, tickets, email, and chat.
#>

[CmdletBinding()]
param(
    [string]$SettingsPath = '',
    [string]$LogDirectory = '',
    [string]$ExportDirectory = ''
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

$script:ScriptVersion = '2026-07-09-r3-alleva-end-user-tools-2'
$script:RunStartedAt = Get-Date
$script:Root = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }

if ([string]::IsNullOrWhiteSpace($SettingsPath)) {
    $SettingsPath = Join-Path $script:Root 'alleva-remote-diagnostics.local.json'
}
if ([string]::IsNullOrWhiteSpace($LogDirectory)) {
    $LogDirectory = Join-Path $script:Root 'logs'
}
if ([string]::IsNullOrWhiteSpace($ExportDirectory)) {
    $ExportDirectory = Join-Path $script:Root 'exports'
}

$script:Settings = $null
$script:AccessToken = ''
$script:TokenExpiresAtUtc = [datetime]::MinValue
$script:SessionDirectory = ''
$script:EventLogPath = ''
$script:TranscriptPath = ''
$script:TranscriptActive = $false
$script:LastActivePatients = @()
$script:LastAllPatients = @()
$script:LastTreatmentPlans = @()
$script:ClientsPath = '/clients'
$script:TreatmentPlansPath = '/treatment-plans'
$script:ActiveStatusId = '1049'
$script:DischargedStatusId = '1356'

function New-TimestampText {
    return (Get-Date).ToString('yyyyMMdd-HHmmss')
}

function New-IsoTimestampText {
    return (Get-Date).ToString('o')
}

function Ensure-Directory {
    param([Parameter(Mandatory=$true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Get-SafeCount {
    param($Value)
    if ($null -eq $Value) { return 0 }
    if ($Value -is [System.Array]) { return $Value.Length }
    if ($Value -is [System.Collections.ICollection]) { return $Value.Count }
    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string]) -and -not ($Value -is [System.Collections.IDictionary])) {
        $count = 0
        foreach ($item in $Value) { $count++ }
        return $count
    }
    return 1
}

function Write-AppLog {
    param(
        [ValidateSet('DEBUG','INFO','WARN','ERROR')][string]$Level = 'INFO',
        [string]$Event = 'event',
        [string]$Message = '',
        [AllowNull()]$Data = $null
    )

    if ([string]::IsNullOrWhiteSpace($script:EventLogPath)) { return }

    $entry = [ordered]@{
        timestamp = New-IsoTimestampText
        level = $Level
        event = $Event
        message = $Message
        data = $Data
    }

    try {
        ($entry | ConvertTo-Json -Depth 80 -Compress) | Add-Content -LiteralPath $script:EventLogPath -Encoding UTF8
    } catch {
        # Logging must never break the user workflow.
    }
}

function Write-Ui {
    param(
        [string]$Message = '',
        [ConsoleColor]$Color = [ConsoleColor]::Gray,
        [string]$Event = 'ui.message',
        [ValidateSet('DEBUG','INFO','WARN','ERROR')][string]$Level = 'INFO'
    )

    if ($Message -eq '') {
        Write-Host ''
        return
    }

    Write-Host $Message -ForegroundColor $Color
    Write-AppLog -Level $Level -Event $Event -Message $Message -Data $null
}

function Initialize-Logging {
    Ensure-Directory -Path $LogDirectory
    Ensure-Directory -Path $ExportDirectory

    $stamp = New-TimestampText
    $script:SessionDirectory = Join-Path $LogDirectory "end-user-session-$stamp"
    Ensure-Directory -Path $script:SessionDirectory

    $script:EventLogPath = Join-Path $script:SessionDirectory 'events.ndjson'
    $script:TranscriptPath = Join-Path $script:SessionDirectory 'terminal-transcript.txt'
    New-Item -ItemType File -Path $script:EventLogPath -Force | Out-Null

    Write-AppLog -Level INFO -Event 'app.started' -Message 'Alleva end-user tool started.' -Data ([ordered]@{
        version = $script:ScriptVersion
        root = $script:Root
        settings_path = $SettingsPath
        log_directory = $LogDirectory
        export_directory = $ExportDirectory
        user = [Environment]::UserName
        machine = [Environment]::MachineName
        powershell_version = $PSVersionTable.PSVersion.ToString()
    })

    try {
        Start-Transcript -Path $script:TranscriptPath -Force | Out-Null
        $script:TranscriptActive = $true
        Write-AppLog -Level INFO -Event 'logging.transcript_started' -Message 'Terminal transcript started.' -Data @{ path = $script:TranscriptPath }
    } catch {
        Write-AppLog -Level WARN -Event 'logging.transcript_failed' -Message $_.Exception.Message -Data $null
    }
}

function Stop-Logging {
    Write-AppLog -Level INFO -Event 'app.exited' -Message 'Alleva end-user tool exited.' -Data ([ordered]@{
        started_at = $script:RunStartedAt.ToString('o')
        exited_at = (Get-Date).ToString('o')
        session_directory = $script:SessionDirectory
    })

    if ($script:TranscriptActive) {
        try { Stop-Transcript | Out-Null } catch { }
        $script:TranscriptActive = $false
    }
}

function Write-Section {
    param([string]$Title)
    Write-Host ''
    Write-Host ('=' * 96) -ForegroundColor DarkGray
    Write-Host $Title -ForegroundColor Cyan
    Write-Host ('=' * 96) -ForegroundColor DarkGray
    Write-AppLog -Level INFO -Event 'ui.section' -Message $Title -Data $null
}

function Write-Subsection {
    param([string]$Title)
    Write-Host ''
    Write-Host $Title -ForegroundColor Yellow
    Write-Host ('-' * [Math]::Min(96, [Math]::Max(1, $Title.Length))) -ForegroundColor DarkGray
    Write-AppLog -Level INFO -Event 'ui.subsection' -Message $Title -Data $null
}

function Write-PhiReminder {
    Write-Ui 'PHI / credential reminder:' DarkYellow 'phi.reminder'
    Write-Ui '  This tool calls Alleva directly. Logs and exports may contain patient data.' DarkYellow 'phi.reminder'
    Write-Ui '  Keep generated files local, access-controlled, and out of Git, tickets, email, and chat.' DarkYellow 'phi.reminder'
}

function Read-PlainSecret {
    param([string]$Prompt)
    Write-AppLog -Level INFO -Event 'credential.prompt' -Message $Prompt -Data @{ secret = $true }
    $secure = Read-Host -Prompt $Prompt -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    } finally {
        if ($bstr -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
    }
}

function ConvertTo-ProtectedString {
    param([AllowNull()][string]$PlainText)
    if ([string]::IsNullOrEmpty($PlainText)) { return '' }
    $secure = ConvertTo-SecureString -String $PlainText -AsPlainText -Force
    return ConvertFrom-SecureString -SecureString $secure
}

function ConvertFrom-ProtectedString {
    param([AllowNull()][string]$ProtectedText)
    if ([string]::IsNullOrWhiteSpace($ProtectedText)) { return '' }
    try {
        $secure = ConvertTo-SecureString -String $ProtectedText
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try {
            return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        } finally {
            if ($bstr -ne [IntPtr]::Zero) {
                [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
            }
        }
    } catch {
        Write-Ui 'Could not decrypt a saved secret. It may have been saved by a different Windows user or machine.' DarkYellow 'settings.secret_decrypt_failed' WARN
        return ''
    }
}

function Get-DefaultSettings {
    return [ordered]@{
        AllevaApiBaseUrl = 'https://api.allevasoft.com'
        AllevaTokenUrl = 'https://authorization.allevasoft.com/connect/token'
        AllevaOpenApiUrl = 'https://api.allevasoft.com/swagger/v1/swagger.json'
        AllevaSwaggerUiUrl = 'https://api.allevasoft.com/swagger/index.html'
        ClientId = ''
        ClientSecretProtected = ''
        Scope = ''
        TokenAuthStyle = 'body'
        ApiVersion = '1.0'
        Limit = 500
        Cursor = 0
        StartDate = '2000-01-01T16:03'
        MaxPages = 10
        TimeoutSeconds = 60
        ConsoleRowLimit = 100
        WriteRawJsonCompanion = $true
    }
}

function ConvertTo-HashtableDeep {
    param($InputObject)

    if ($null -eq $InputObject) { return $null }

    if ($InputObject -is [System.Collections.IDictionary]) {
        $h = [ordered]@{}
        foreach ($key in $InputObject.Keys) {
            $h[$key] = ConvertTo-HashtableDeep $InputObject[$key]
        }
        return $h
    }

    if ($InputObject -is [System.Collections.IEnumerable] -and -not ($InputObject -is [string])) {
        $list = New-Object System.Collections.Generic.List[object]
        foreach ($item in $InputObject) {
            $list.Add((ConvertTo-HashtableDeep $item))
        }
        return $list.ToArray()
    }

    try {
        if ($InputObject.PSObject -and (Get-SafeCount ($InputObject.PSObject.Properties)) -gt 0 -and -not ($InputObject -is [string]) -and -not ($InputObject -is [ValueType])) {
            $h = [ordered]@{}
            foreach ($prop in $InputObject.PSObject.Properties) {
                $h[$prop.Name] = ConvertTo-HashtableDeep $prop.Value
            }
            return $h
        }
    } catch { }

    return $InputObject
}

function Import-Settings {
    $defaults = Get-DefaultSettings
    $settings = [ordered]@{}
    foreach ($key in $defaults.Keys) {
        $settings[$key] = $defaults[$key]
    }

    if (Test-Path -LiteralPath $SettingsPath) {
        try {
            $json = Get-Content -LiteralPath $SettingsPath -Raw -ErrorAction Stop
            if (-not [string]::IsNullOrWhiteSpace($json)) {
                $loaded = ConvertTo-HashtableDeep ($json | ConvertFrom-Json)
                foreach ($key in $loaded.Keys) {
                    if ($settings.Contains($key)) {
                        $settings[$key] = $loaded[$key]
                    }
                }
                Write-AppLog -Level INFO -Event 'settings.loaded' -Message 'Settings loaded.' -Data @{ path = $SettingsPath }
            }
        } catch {
            Write-Ui "Could not load settings from $SettingsPath : $($_.Exception.Message)" Red 'settings.load_failed' ERROR
        }
    } else {
        Write-AppLog -Level WARN -Event 'settings.not_found' -Message 'Settings file not found yet.' -Data @{ path = $SettingsPath }
    }

    $script:Settings = $settings
}

function Save-Settings {
    $parent = Split-Path -Parent $SettingsPath
    Ensure-Directory -Path $parent
    ($script:Settings | ConvertTo-Json -Depth 40) | Set-Content -LiteralPath $SettingsPath -Encoding UTF8
    Write-Ui "Saved settings: $SettingsPath" Green 'settings.saved'
}

function Read-SettingValue {
    param(
        [string]$Label,
        [AllowNull()][string]$CurrentValue,
        [switch]$Secret
    )

    if ($null -eq $CurrentValue) { $CurrentValue = '' }

    if ($Secret) {
        $hint = if ([string]::IsNullOrWhiteSpace($CurrentValue)) { '<not set>' } else { '<currently saved>' }
        $value = Read-PlainSecret "$Label [$hint; Enter keeps current]"
        if ([string]::IsNullOrWhiteSpace($value)) { return $CurrentValue }
        return $value
    }

    Write-AppLog -Level INFO -Event 'settings.prompt' -Message $Label -Data @{ secret = $false }
    $value = Read-Host "$Label [$CurrentValue]"
    if ([string]::IsNullOrWhiteSpace($value)) { return $CurrentValue }
    return $value.Trim()
}

function Read-IntegerSetting {
    param([string]$Label, [int]$CurrentValue, [int]$Minimum, [int]$Maximum)
    Write-AppLog -Level INFO -Event 'settings.prompt' -Message $Label -Data @{ current = $CurrentValue }
    $raw = Read-Host "$Label [$CurrentValue]"
    if ([string]::IsNullOrWhiteSpace($raw)) { return $CurrentValue }

    $out = 0
    if ([int]::TryParse($raw, [ref]$out)) {
        return [Math]::Max($Minimum, [Math]::Min($Maximum, $out))
    }

    Write-Ui 'Invalid number; keeping existing value.' DarkYellow 'settings.invalid_number' WARN
    return $CurrentValue
}

function Show-Settings {
    Import-Settings
    Write-Section 'Current Alleva end-user tool settings'
    Write-Host "Script version:             $script:ScriptVersion"
    Write-Host "Working directory:          $script:Root"
    Write-Host "Settings file:              $SettingsPath"
    Write-Host "Log directory:              $LogDirectory"
    Write-Host "Export directory:           $ExportDirectory"
    Write-Host "AllevaApiBaseUrl:           $($script:Settings['AllevaApiBaseUrl'])"
    Write-Host "AllevaTokenUrl:             $($script:Settings['AllevaTokenUrl'])"
    Write-Host "ClientId configured:        $([bool]([string]$script:Settings['ClientId']))"
    Write-Host "ClientSecret configured:    $([bool]([string]$script:Settings['ClientSecretProtected']))"
    Write-Host "Scope configured:           $([bool]([string]$script:Settings['Scope']))"
    Write-Host "TokenAuthStyle:             $($script:Settings['TokenAuthStyle'])"
    Write-Host "ApiVersion:                 $($script:Settings['ApiVersion'])"
    Write-Host "Limit / Cursor / MaxPages:  $($script:Settings['Limit']) / $($script:Settings['Cursor']) / $($script:Settings['MaxPages'])"
    Write-Host "StartDate:                  $($script:Settings['StartDate'])"
    Write-Host "TimeoutSeconds:             $($script:Settings['TimeoutSeconds'])"
    Write-Host "ConsoleRowLimit:            $($script:Settings['ConsoleRowLimit'])"
    Write-Host "WriteRawJsonCompanion:      $($script:Settings['WriteRawJsonCompanion'])"
}

function Edit-SettingsMenu {
    Import-Settings
    Write-Section 'Configure Alleva API credentials and limits'
    Write-Ui 'Enter keeps the current value. The client secret is protected by Windows for this Windows user.' DarkGray 'settings.edit_help'

    $script:Settings['AllevaApiBaseUrl'] = Read-SettingValue 'Alleva REST API base URL' ([string]$script:Settings['AllevaApiBaseUrl'])
    $script:Settings['AllevaTokenUrl'] = Read-SettingValue 'Alleva OAuth token URL' ([string]$script:Settings['AllevaTokenUrl'])
    $script:Settings['ClientId'] = Read-SettingValue 'Alleva client ID' ([string]$script:Settings['ClientId'])

    $currentSecret = ConvertFrom-ProtectedString ([string]$script:Settings['ClientSecretProtected'])
    $newSecret = Read-SettingValue 'Alleva client secret' $currentSecret -Secret
    $script:Settings['ClientSecretProtected'] = ConvertTo-ProtectedString $newSecret

    $script:Settings['Scope'] = Read-SettingValue 'OAuth scope, often blank' ([string]$script:Settings['Scope'])
    $style = Read-SettingValue 'Token auth style: body/basic/basic_urlencoded/both/all' ([string]$script:Settings['TokenAuthStyle'])
    $style = $style.ToLowerInvariant().Replace('-', '_')
    if (@('body','basic','basic_urlencoded','both','all') -notcontains $style) { $style = 'body' }
    $script:Settings['TokenAuthStyle'] = $style

    $script:Settings['ApiVersion'] = Read-SettingValue 'Alleva api-version / X-Version' ([string]$script:Settings['ApiVersion'])
    $script:Settings['Limit'] = Read-IntegerSetting 'Page size / Limit' ([int]$script:Settings['Limit']) 1 5000
    $script:Settings['Cursor'] = Read-IntegerSetting 'Initial Cursor' ([int]$script:Settings['Cursor']) 0 2147483647
    $script:Settings['StartDate'] = Read-SettingValue 'Treatment-plan StartDate' ([string]$script:Settings['StartDate'])
    $script:Settings['MaxPages'] = Read-IntegerSetting 'Max pages per pull' ([int]$script:Settings['MaxPages']) 1 10000
    $script:Settings['TimeoutSeconds'] = Read-IntegerSetting 'HTTP timeout seconds' ([int]$script:Settings['TimeoutSeconds']) 1 300
    $script:Settings['ConsoleRowLimit'] = Read-IntegerSetting 'Console row preview limit' ([int]$script:Settings['ConsoleRowLimit']) 10 2000

    $raw = Read-Host "Write raw JSON companion files next to CSV exports? [Y/n] current=$($script:Settings['WriteRawJsonCompanion'])"
    if ($raw -match '^[nN]') {
        $script:Settings['WriteRawJsonCompanion'] = $false
    } else {
        $script:Settings['WriteRawJsonCompanion'] = $true
    }

    Save-Settings
}

function Format-Cell {
    param([AllowNull()]$Value, [int]$Width)
    $s = ConvertTo-ShortText $Value $Width
    if ($s.Length -lt $Width) { return $s.PadRight($Width) }
    return $s
}

function Show-AsciiTable {
    param(
        [AllowNull()]$Rows,
        [string[]]$Columns,
        [hashtable]$Widths = @{},
        [int]$MaxRows = 0
    )

    $rowArray = @(ConvertTo-ObjectArraySafe $Rows)
    if ((Get-SafeCount $rowArray) -eq 0) {
        Write-Ui '(no rows to display)' DarkYellow 'table.empty' WARN
        return
    }

    if ($MaxRows -le 0) { $MaxRows = [int]$script:Settings['ConsoleRowLimit'] }

    $widthMap = @{}
    foreach ($col in $Columns) {
        $base = [Math]::Max(4, $col.Length)
        if ($Widths.ContainsKey($col)) {
            $desired = [int]$Widths[$col]
        } else {
            $desired = [Math]::Min(30, [Math]::Max($base, 18))
        }
        $widthMap[$col] = [Math]::Max($base, $desired)
    }

    $border = '+'
    foreach ($col in $Columns) { $border += ('-' * ($widthMap[$col] + 2)) + '+' }
    Write-Host $border -ForegroundColor DarkGray

    $header = '|'
    foreach ($col in $Columns) { $header += ' ' + (Format-Cell $col $widthMap[$col]) + ' |' }
    Write-Host $header -ForegroundColor Cyan
    Write-Host $border -ForegroundColor DarkGray

    $shown = 0
    foreach ($row in $rowArray) {
        if ($shown -ge $MaxRows) { break }
        $line = '|'
        foreach ($col in $Columns) {
            $value = Get-PropValue $row @($col)
            $line += ' ' + (Format-Cell $value $widthMap[$col]) + ' |'
        }
        Write-Host $line
        $shown++
    }

    Write-Host $border -ForegroundColor DarkGray
    if ((Get-SafeCount $rowArray) -gt $shown) {
        Write-Ui "Showing $shown of $(Get-SafeCount $rowArray) rows. Export CSV to see everything." DarkYellow 'table.truncated' WARN
    }
}

function Test-Prerequisites {
    Write-Section 'Preflight check'
    $ok = $true
    $checks = New-Object System.Collections.Generic.List[object]

    $psVersion = $PSVersionTable.PSVersion
    $psOk = ($psVersion.Major -gt 5 -or ($psVersion.Major -eq 5 -and $psVersion.Minor -ge 1))
    if (-not $psOk) { $ok = $false }
    if ($psOk) { $psStatus = 'OK' } else { $psStatus = 'FAILED' }
    $checks.Add([pscustomobject]@{ Check='PowerShell 5.1 or newer'; Status=$psStatus; Detail=$psVersion.ToString() })

    foreach ($cmdName in @('Invoke-WebRequest','ConvertFrom-Json','ConvertTo-Json','Export-Csv','Start-Transcript')) {
        $cmd = Get-Command $cmdName -ErrorAction SilentlyContinue
        $hasIt = ($null -ne $cmd)
        if (-not $hasIt) { $ok = $false }
        if ($hasIt) { $cmdStatus = 'OK' } else { $cmdStatus = 'FAILED' }
        if ($hasIt) { $detail = $cmd.Source } else { $detail = 'Missing' }
        $checks.Add([pscustomobject]@{ Check="Command: $cmdName"; Status=$cmdStatus; Detail=$detail })
    }

    $canWrite = $true
    try {
        Ensure-Directory -Path $LogDirectory
        Ensure-Directory -Path $ExportDirectory
    } catch {
        $canWrite = $false
    }
    if (-not $canWrite) { $ok = $false }
    if ($canWrite) { $folderStatus = 'OK' } else { $folderStatus = 'FAILED' }
    $checks.Add([pscustomobject]@{ Check='Log/export folders writable'; Status=$folderStatus; Detail="$LogDirectory ; $ExportDirectory" })

    Show-AsciiTable -Rows $checks.ToArray() -Columns @('Check','Status','Detail') -Widths @{ Check=34; Status=8; Detail=48 }
    Write-AppLog -Level INFO -Event 'preflight.completed' -Message 'Preflight completed.' -Data @{ ok = $ok; checks = $checks.ToArray() }

    if ($ok) {
        Write-Ui 'Preflight passed. No extra PowerShell modules are required.' Green 'preflight.passed'
    } else {
        Write-Ui 'One or more required PowerShell features are missing. This script uses only built-in Windows PowerShell features.' Red 'preflight.failed' ERROR
        Write-Ui 'Run it from Windows PowerShell 5.1+ or PowerShell 7+, then try again.' Yellow 'preflight.failed_help' WARN
    }

    return $ok
}

function Get-TokenStylesToTry {
    param([string]$TokenAuthStyle)
    $normalized = if ([string]::IsNullOrWhiteSpace($TokenAuthStyle)) { 'body' } else { $TokenAuthStyle.Trim().ToLowerInvariant().Replace('-', '_') }
    switch ($normalized) {
        'both' { return @('body','basic') }
        'all' { return @('body','basic','basic_urlencoded') }
        'basic' { return @('basic') }
        'basic_urlencoded' { return @('basic_urlencoded') }
        default { return @('body') }
    }
}

function ConvertTo-FormUrlEncoded {
    param([Parameter(Mandatory=$true)]$Form)
    $pairs = New-Object System.Collections.Generic.List[string]
    foreach ($key in $Form.Keys) {
        $value = $Form[$key]
        if ($null -ne $value -and "${value}" -ne '') {
            $pairs.Add(("{0}={1}" -f [uri]::EscapeDataString([string]$key), [uri]::EscapeDataString([string]$value)))
        }
    }
    return ($pairs -join '&')
}

function Get-SecretClientCredentials {
    Import-Settings
    $clientId = ([string]$script:Settings['ClientId']).Trim()
    $clientSecret = ConvertFrom-ProtectedString ([string]$script:Settings['ClientSecretProtected'])

    if ([string]::IsNullOrWhiteSpace($clientId)) { $clientId = Read-Host 'Alleva client ID' }
    if ([string]::IsNullOrWhiteSpace($clientSecret)) { $clientSecret = Read-PlainSecret 'Alleva client secret' }

    return [pscustomobject]@{ ClientId=$clientId; ClientSecret=$clientSecret }
}

function Get-RedactedHeaders {
    param([hashtable]$Headers)
    $out = [ordered]@{}
    if ($null -eq $Headers) { return $out }
    foreach ($key in $Headers.Keys) {
        if ([string]$key -match '(?i)authorization|token|secret|key') {
            $out[$key] = '[redacted]'
        } else {
            $out[$key] = $Headers[$key]
        }
    }
    return $out
}

function Invoke-HttpRaw {
    param(
        [Parameter(Mandatory=$true)][ValidateSet('GET','POST')][string]$Method,
        [Parameter(Mandatory=$true)][string]$Url,
        [hashtable]$Headers = @{},
        [AllowNull()][string]$Body = $null,
        [string]$ContentType = '',
        [string]$Purpose = 'request'
    )

    $params = @{
        Uri = $Url
        Method = $Method
        Headers = $Headers
        TimeoutSec = [int]$script:Settings['TimeoutSeconds']
        ErrorAction = 'Stop'
    }

    $cmd = Get-Command Invoke-WebRequest -ErrorAction Stop
    if ($cmd.Parameters.ContainsKey('SkipHttpErrorCheck')) { $params['SkipHttpErrorCheck'] = $true }
    if ($cmd.Parameters.ContainsKey('UseBasicParsing')) { $params['UseBasicParsing'] = $true }
    if ($null -ne $Body -and [string]$Body -ne '') {
        $params['Body'] = $Body
        if ($ContentType) { $params['ContentType'] = $ContentType }
    }

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $resp = Invoke-WebRequest @params
        $sw.Stop()
        $content = ''
        try { $content = [string]$resp.Content } catch { }

        return [pscustomobject]@{
            Ok = ([int]$resp.StatusCode -ge 200 -and [int]$resp.StatusCode -lt 300)
            StatusCode = [int]$resp.StatusCode
            StatusDescription = [string]$resp.StatusDescription
            Content = $content
            Headers = $resp.Headers
            DurationMs = $sw.ElapsedMilliseconds
            Error = ''
            Purpose = $Purpose
            Url = $Url
        }
    } catch {
        $sw.Stop()
        $status = 0
        $statusDescription = ''
        $content = ''
        $headers = @{}

        try {
            $response = $_.Exception.Response
            if ($response) {
                try { $status = [int]$response.StatusCode } catch { }
                try { $statusDescription = [string]$response.StatusDescription } catch { }
                try { $headers = $response.Headers } catch { }
                try {
                    if ($response.Content) {
                        $content = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
                    }
                } catch { }
                if ([string]::IsNullOrWhiteSpace($content)) {
                    try {
                        $stream = $response.GetResponseStream()
                        if ($stream) {
                            $reader = New-Object System.IO.StreamReader($stream)
                            $content = $reader.ReadToEnd()
                            $reader.Close()
                        }
                    } catch { }
                }
            }
        } catch { }

        if ([string]::IsNullOrWhiteSpace($content) -and $_.ErrorDetails -and $_.ErrorDetails.Message) {
            $content = [string]$_.ErrorDetails.Message
        }

        return [pscustomobject]@{
            Ok = $false
            StatusCode = $status
            StatusDescription = $statusDescription
            Content = $content
            Headers = $headers
            DurationMs = $sw.ElapsedMilliseconds
            Error = $_.Exception.Message
            Purpose = $Purpose
            Url = $Url
        }
    }
}

function Request-TokenOnce {
    param([string]$Style, [string]$ClientId, [string]$ClientSecret)

    $headers = @{ Accept = 'application/json' }
    $form = [ordered]@{ grant_type = 'client_credentials' }
    $scope = ([string]$script:Settings['Scope']).Trim()
    if ($scope) { $form['scope'] = $scope }

    if ($Style -eq 'body') {
        $form['client_id'] = $ClientId
        $form['client_secret'] = $ClientSecret
    } else {
        if ($Style -eq 'basic_urlencoded') {
            $pair = ('{0}:{1}' -f [uri]::EscapeDataString($ClientId), [uri]::EscapeDataString($ClientSecret))
        } else {
            $pair = ('{0}:{1}' -f $ClientId, $ClientSecret)
        }
        $basic = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($pair))
        $headers['Authorization'] = "Basic $basic"
    }

    $body = ConvertTo-FormUrlEncoded $form
    return Invoke-HttpRaw -Method POST -Url ([string]$script:Settings['AllevaTokenUrl']) -Headers $headers -Body $body -ContentType 'application/x-www-form-urlencoded' -Purpose "token-$Style"
}

function Ensure-AccessToken {
    Import-Settings
    $now = (Get-Date).ToUniversalTime()
    if ($script:AccessToken -and $script:TokenExpiresAtUtc -gt $now.AddSeconds(120)) { return $true }

    $creds = Get-SecretClientCredentials
    $styles = Get-TokenStylesToTry ([string]$script:Settings['TokenAuthStyle'])

    Write-Subsection 'Requesting Alleva OAuth token'
    foreach ($style in $styles) {
        Write-Ui "Trying token auth style: $style" DarkGray 'token.try'
        $resp = Request-TokenOnce -Style $style -ClientId $creds.ClientId -ClientSecret $creds.ClientSecret

        Write-AppLog -Level INFO -Event 'api.token_response' -Message "Token attempt with $style completed." -Data ([ordered]@{
            style = $style
            ok = $resp.Ok
            status_code = $resp.StatusCode
            duration_ms = $resp.DurationMs
            url = $resp.Url
        })

        if ($resp.Ok) {
            try { $parsed = $resp.Content | ConvertFrom-Json } catch { $parsed = $null }
            if ($parsed -and $parsed.access_token) {
                $script:AccessToken = [string]$parsed.access_token
                $expiresIn = 3600
                try { if ($parsed.expires_in) { $expiresIn = [int]$parsed.expires_in } } catch { }
                $script:TokenExpiresAtUtc = (Get-Date).ToUniversalTime().AddSeconds($expiresIn)
                Write-Ui "Token acquired with $style. Expires in about $expiresIn seconds." Green 'token.acquired'
                return $true
            }
        }

        Write-Ui "Token attempt failed. HTTP $($resp.StatusCode). $($resp.Error)" DarkYellow 'token.failed' WARN
        if ($resp.Content) {
            Write-AppLog -Level WARN -Event 'api.token_failure_body' -Message 'Token failure body redacted.' -Data @{ content = (($resp.Content -replace $creds.ClientSecret, '[redacted]') -replace $creds.ClientId, '[client-id-redacted]') }
        }
    }

    Write-Ui 'Could not acquire an Alleva bearer token.' Red 'token.unavailable' ERROR
    return $false
}

function Join-UrlPath {
    param([string]$BaseUrl, [string]$Path)
    $base = $BaseUrl.TrimEnd('/')
    if (-not $Path.StartsWith('/')) { $Path = "/$Path" }
    return "$base$Path"
}

function Add-QueryString {
    param([string]$Url, [hashtable]$Query)
    $pairs = New-Object System.Collections.Generic.List[string]
    foreach ($key in $Query.Keys) {
        $value = $Query[$key]
        if ($null -eq $value -or [string]$value -eq '') { continue }
        if ($value -is [System.Array]) {
            foreach ($item in $value) {
                $pairs.Add(("{0}={1}" -f [uri]::EscapeDataString([string]$key), [uri]::EscapeDataString([string]$item)))
            }
        } else {
            $pairs.Add(("{0}={1}" -f [uri]::EscapeDataString([string]$key), [uri]::EscapeDataString([string]$value)))
        }
    }
    if ($pairs.Count -eq 0) { return $Url }
    $sep = if ($Url.Contains('?')) { '&' } else { '?' }
    return "$Url$sep$($pairs -join '&')"
}

function Get-ApiHeaders {
    $apiVersion = ([string]$script:Settings['ApiVersion']).Trim()
    return @{ Accept='application/json'; Authorization="Bearer $script:AccessToken"; 'X-Version'=$apiVersion }
}

function ConvertFrom-JsonSafe {
    param([AllowNull()][string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $null }
    try { return $Text | ConvertFrom-Json } catch { return $null }
}

function Get-PropertyNamesSafe {
    param($Value)
    if ($null -eq $Value) { return @() }
    try {
        $names = New-Object System.Collections.Generic.List[string]
        foreach ($prop in $Value.PSObject.Properties) {
            if ($prop -and $prop.Name) { $names.Add([string]$prop.Name) }
        }
        return $names.ToArray()
    } catch {
        return @()
    }
}

function Test-IsScalarLike {
    param($Value)
    if ($null -eq $Value) { return $true }
    if ($Value -is [string]) { return $true }
    if ($Value -is [ValueType]) { return $true }
    return $false
}

function Test-IsRecordObject {
    param($Value)
    if (Test-IsScalarLike $Value) { return $false }
    if ($Value -is [System.Collections.IDictionary]) { return $true }
    return ((Get-SafeCount (Get-PropertyNamesSafe $Value)) -gt 0)
}

function Test-IsEnumerableCollection {
    param($Value)
    if ($null -eq $Value) { return $false }
    if ($Value -is [string]) { return $false }
    if ($Value -is [System.Collections.IDictionary]) { return $false }
    return ($Value -is [System.Collections.IEnumerable])
}

function ConvertTo-ObjectArraySafe {
    param($Value)
    if ($null -eq $Value) { return @() }
    $items = New-Object System.Collections.Generic.List[object]
    if (Test-IsEnumerableCollection $Value) {
        foreach ($item in $Value) { $items.Add($item) }
    } else {
        $items.Add($Value)
    }
    return $items.ToArray()
}

function Get-RecordsFromPayload {
    param($Payload)
    $records = New-Object System.Collections.Generic.List[object]
    if ($null -eq $Payload) { return @() }

    if (Test-IsEnumerableCollection $Payload) {
        foreach ($item in (ConvertTo-ObjectArraySafe $Payload)) {
            if (Test-IsRecordObject $item) { $records.Add($item) }
        }
        return $records.ToArray()
    }

    $payloadPropertyNames = Get-PropertyNamesSafe $Payload
    foreach ($key in @('items','data','results','value','records')) {
        if ($payloadPropertyNames -contains $key) {
            $value = Get-PropValue $Payload @($key)
            foreach ($item in (ConvertTo-ObjectArraySafe $value)) {
                if (Test-IsRecordObject $item) { $records.Add($item) }
            }
            return $records.ToArray()
        }
    }

    if (Test-IsRecordObject $Payload) { $records.Add($Payload) }
    return $records.ToArray()
}

function Get-BaseQuery {
    param([switch]$ForTreatmentPlans)
    $apiVersion = ([string]$script:Settings['ApiVersion']).Trim()
    $q = @{
        Limit = [int]$script:Settings['Limit']
        Cursor = [int]$script:Settings['Cursor']
        'api-version' = $apiVersion
    }
    if ($ForTreatmentPlans) { $q['StartDate'] = [string]$script:Settings['StartDate'] }
    return $q
}

function Invoke-AllevaGet {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [hashtable]$Query = @{},
        [string]$Label = ''
    )

    if (-not (Ensure-AccessToken)) { throw 'No Alleva access token available.' }

    $baseUrl = Join-UrlPath ([string]$script:Settings['AllevaApiBaseUrl']) $Path
    $url = Add-QueryString $baseUrl $Query
    $headers = Get-ApiHeaders

    Write-Ui "GET $Path" DarkGray 'api.get'
    $resp = Invoke-HttpRaw -Method GET -Url $url -Headers $headers -Purpose $Label

    Write-AppLog -Level INFO -Event 'api.get_response' -Message "GET $Path completed." -Data ([ordered]@{
        label = $Label
        path = $Path
        url = $url
        query = $Query
        headers = (Get-RedactedHeaders $headers)
        ok = $resp.Ok
        status_code = $resp.StatusCode
        duration_ms = $resp.DurationMs
        error = $resp.Error
    })

    if (-not $resp.Ok) { throw "GET $Path failed. HTTP $($resp.StatusCode). $($resp.Error)" }

    $payload = ConvertFrom-JsonSafe $resp.Content
    if ($null -eq $payload) { throw "GET $Path responded, but the response was not parseable JSON." }
    return $payload
}

function Invoke-AllevaCollection {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [hashtable]$Query = @{},
        [int]$MaxPages = 0,
        [string]$Label = ''
    )

    if ($MaxPages -le 0) { $MaxPages = [int]$script:Settings['MaxPages'] }
    $records = New-Object System.Collections.Generic.List[object]

    $limit = 500
    try { $limit = [Math]::Max(1, [Math]::Min(5000, [int]$Query['Limit'])) } catch { $limit = 500 }

    $cursor = 0
    try { $cursor = [Math]::Max(0, [int]$Query['Cursor']) } catch { $cursor = 0 }

    for ($pageIndex = 0; $pageIndex -lt $MaxPages; $pageIndex++) {
        $pageQuery = @{}
        foreach ($key in $Query.Keys) { $pageQuery[$key] = $Query[$key] }
        $pageQuery['Limit'] = $limit
        $pageQuery['Cursor'] = $cursor

        Write-Ui ("Pulling {0} page {1}/{2}" -f $Path, ($pageIndex + 1), $MaxPages) DarkGray 'api.collection_page'
        $payload = Invoke-AllevaGet -Path $Path -Query $pageQuery -Label "$Label-page-$pageIndex"
        $pageRecords = @(Get-RecordsFromPayload $payload)
        foreach ($record in $pageRecords) { $records.Add($record) }

        Write-AppLog -Level INFO -Event 'api.collection_page_records' -Message 'Collection page processed.' -Data @{ path=$Path; page=($pageIndex+1); record_count=(Get-SafeCount $pageRecords); cursor=$cursor; limit=$limit }

        if ((Get-SafeCount $pageRecords) -lt $limit) { break }
        $cursor += $limit
    }

    return $records.ToArray()
}

function Get-PropValue {
    param([AllowNull()]$Object, [string[]]$Names)
    if ($null -eq $Object) { return $null }

    if ($Object -is [System.Collections.IDictionary]) {
        foreach ($wanted in $Names) {
            foreach ($key in $Object.Keys) {
                if ([string]::Equals([string]$key, [string]$wanted, [System.StringComparison]::OrdinalIgnoreCase)) {
                    return $Object[$key]
                }
            }
        }
    }

    try {
        foreach ($wanted in $Names) {
            foreach ($prop in $Object.PSObject.Properties) {
                if ([string]::Equals([string]$prop.Name, [string]$wanted, [System.StringComparison]::OrdinalIgnoreCase)) {
                    return $prop.Value
                }
            }
        }
    } catch { }

    return $null
}

function Get-NestedPropValue {
    param([AllowNull()]$Object, [string[]]$Path)
    $current = $Object
    foreach ($name in $Path) {
        $current = Get-PropValue $current @($name)
        if ($null -eq $current) { return $null }
    }
    return $current
}

function ConvertTo-ShortText {
    param([AllowNull()]$Value, [int]$MaxLength = 80)
    if ($null -eq $Value) { return '' }

    if (Test-IsScalarLike $Value) {
        $s = [string]$Value
    } else {
        try { $s = ($Value | ConvertTo-Json -Depth 12 -Compress) } catch { $s = [string]$Value }
    }

    $s = ($s -replace "`r", ' ' -replace "`n", ' ' -replace "\s+", ' ').Trim()
    if ($s.Length -gt $MaxLength) { return ($s.Substring(0, [Math]::Max(0, $MaxLength - 3)) + '...') }
    return $s
}

function Get-PatientId {
    param($Patient)
    return ConvertTo-ShortText (Get-PropValue $Patient @('id','Id','clientId','ClientId','patientId','PatientId')) 60
}

function Get-PatientName {
    param($Patient)
    $direct = Get-PropValue $Patient @('displayName','DisplayName','fullName','FullName','name','Name')
    if ($direct) { return ConvertTo-ShortText $direct 80 }

    $first = ConvertTo-ShortText (Get-PropValue $Patient @('firstName','FirstName','first_name')) 40
    $last = ConvertTo-ShortText (Get-PropValue $Patient @('lastName','LastName','last_name')) 40
    $name = ("$first $last").Trim()
    if ($name) { return $name }
    return '(name not shown)'
}

function Get-StatusText {
    param($Record)
    $status = Get-PropValue $Record @('status','Status')
    if ($null -eq $status) {
        return ConvertTo-ShortText (Get-PropValue $Record @('statusLabel','StatusLabel','statusName','StatusName')) 80
    }

    if (Test-IsScalarLike $status) { return ConvertTo-ShortText $status 80 }

    $sid = ConvertTo-ShortText (Get-PropValue $status @('id','Id','statusId','StatusId')) 30
    $label = ConvertTo-ShortText (Get-PropValue $status @('label','Label','name','Name','description','Description','displayName','DisplayName')) 50
    if ($sid -and $label) { return "$label ($sid)" }
    if ($label) { return $label }
    if ($sid) { return $sid }
    return ConvertTo-ShortText $status 80
}

function Test-IsActivePatient {
    param($Patient)
    $status = Get-PropValue $Patient @('status','Status')
    $sid = ConvertTo-ShortText (Get-PropValue $status @('id','Id','statusId','StatusId')) 50
    $text = (Get-StatusText $Patient).ToLowerInvariant()

    if ($sid -eq $script:ActiveStatusId) { return $true }
    if ($text -match '\bactive\b') { return $true }
    if ($sid -eq $script:DischargedStatusId) { return $false }
    if ($text -match 'discharg|inactive|closed|deceased') { return $false }
    return $false
}

function Get-PlanId {
    param($Plan)
    return ConvertTo-ShortText (Get-PropValue $Plan @('id','Id','treatmentPlanId','TreatmentPlanId','treatment_plan_id')) 80
}

function Get-PlanPatientId {
    param($Plan)
    $direct = Get-PropValue $Plan @('ClientId','clientId','patientId','PatientId','client_id','patient_id')
    if ($direct) { return ConvertTo-ShortText $direct 80 }

    $clientId = Get-NestedPropValue $Plan @('client','id')
    if ($clientId) { return ConvertTo-ShortText $clientId 80 }

    $patientNested = Get-NestedPropValue $Plan @('patient','id')
    if ($patientNested) { return ConvertTo-ShortText $patientNested 80 }
    return ''
}

function Get-UpdatedDateText {
    param($Record)
    return ConvertTo-ShortText (Get-PropValue $Record @('updatedAt','UpdatedAt','lastUpdated','LastUpdated','lastUpdatedDate','LastUpdatedDate','modifiedAt','ModifiedAt','modifiedDate','ModifiedDate','dateUpdated','DateUpdated','createdAt','CreatedAt')) 40
}

function Get-PlanTitle {
    param($Plan)
    $title = Get-PropValue $Plan @('name','Name','title','Title','type','Type','planName','PlanName')
    if ($title) { return ConvertTo-ShortText $title 70 }
    return ConvertTo-ShortText (Get-StatusText $Plan) 70
}

function Get-PatientSummaryRow {
    param($Patient, [int]$Index)
    return [pscustomobject]@{
        '#' = $Index
        PatientId = Get-PatientId $Patient
        Name = Get-PatientName $Patient
        Status = Get-StatusText $Patient
        DOB = ConvertTo-ShortText (Get-PropValue $Patient @('dateOfBirth','DateOfBirth','dob','DOB','birthDate','BirthDate')) 24
        Updated = Get-UpdatedDateText $Patient
    }
}

function Get-PlanSummaryRow {
    param($Plan, [hashtable]$PatientMap, [int]$Index)
    $patientId = Get-PlanPatientId $Plan
    $patientName = ''
    if ($patientId -and $PatientMap.ContainsKey($patientId)) { $patientName = Get-PatientName $PatientMap[$patientId] }

    return [pscustomobject]@{
        '#' = $Index
        PlanId = Get-PlanId $Plan
        PatientId = $patientId
        PatientName = $patientName
        Updated = Get-UpdatedDateText $Plan
        Status = Get-StatusText $Plan
        Title = Get-PlanTitle $Plan
    }
}

function Add-FlattenedValue {
    param(
        [System.Collections.IDictionary]$Output,
        [string]$Prefix,
        [AllowNull()]$Value,
        [int]$Depth = 0
    )

    if ([string]::IsNullOrWhiteSpace($Prefix)) { $Prefix = 'value' }
    if ($Depth -gt 20) {
        $Output[$Prefix] = ConvertTo-ShortText $Value 32000
        return
    }

    if ($null -eq $Value) {
        $Output[$Prefix] = ''
        return
    }

    if (Test-IsScalarLike $Value) {
        $Output[$Prefix] = [string]$Value
        return
    }

    if ($Value -is [System.Collections.IDictionary]) {
        foreach ($key in $Value.Keys) {
            Add-FlattenedValue -Output $Output -Prefix ("$Prefix.$key") -Value $Value[$key] -Depth ($Depth + 1)
        }
        return
    }

    if (Test-IsEnumerableCollection $Value) {
        $items = @(ConvertTo-ObjectArraySafe $Value)
        $allScalar = $true
        foreach ($item in $items) {
            if (-not (Test-IsScalarLike $item)) { $allScalar = $false; break }
        }

        if ($allScalar) {
            $Output[$Prefix] = (($items | ForEach-Object { [string]$_ }) -join '; ')
        } else {
            try { $Output[$Prefix] = ($Value | ConvertTo-Json -Depth 60 -Compress) } catch { $Output[$Prefix] = ConvertTo-ShortText $Value 32000 }
        }
        return
    }

    $names = Get-PropertyNamesSafe $Value
    if ((Get-SafeCount $names) -eq 0) {
        $Output[$Prefix] = ConvertTo-ShortText $Value 32000
        return
    }

    foreach ($name in $names) {
        Add-FlattenedValue -Output $Output -Prefix ("$Prefix.$name") -Value (Get-PropValue $Value @($name)) -Depth ($Depth + 1)
    }
}

function ConvertTo-FlattenedHashtable {
    param($Record)
    $flat = [ordered]@{}
    $names = Get-PropertyNamesSafe $Record

    if ((Get-SafeCount $names) -eq 0) {
        Add-FlattenedValue -Output $flat -Prefix 'value' -Value $Record
        return $flat
    }

    foreach ($name in $names) {
        Add-FlattenedValue -Output $flat -Prefix $name -Value (Get-PropValue $Record @($name))
    }
    return $flat
}

function Get-SafeFileSegment {
    param([AllowNull()][string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return 'unknown' }
    $s = $Text.Trim()
    $s = $s -replace '[\\/:*?"<>|\s]+', '_'
    $s = $s.Trim('_')
    if ($s.Length -gt 80) { $s = $s.Substring(0,80) }
    if ([string]::IsNullOrWhiteSpace($s)) { return 'unknown' }
    return $s
}

function Export-FlattenedCsv {
    param(
        [AllowNull()]$Records,
        [Parameter(Mandatory=$true)][string]$BaseName
    )

    Ensure-Directory -Path $ExportDirectory
    $recordArray = @(ConvertTo-ObjectArraySafe $Records)
    if ((Get-SafeCount $recordArray) -eq 0) {
        Write-Ui 'Nothing to export.' DarkYellow 'export.empty' WARN
        return ''
    }

    $stamp = New-TimestampText
    $safeBase = Get-SafeFileSegment $BaseName
    $csvPath = Join-Path $ExportDirectory "$stamp-$safeBase.csv"
    $jsonPath = Join-Path $ExportDirectory "$stamp-$safeBase.raw.json"

    $allKeys = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    $flattenedRows = New-Object System.Collections.Generic.List[object]

    foreach ($record in $recordArray) {
        $flat = ConvertTo-FlattenedHashtable $record
        foreach ($key in $flat.Keys) {
            if (-not $seen.ContainsKey($key)) {
                $seen[$key] = $true
                $allKeys.Add($key)
            }
        }
        $flattenedRows.Add($flat)
    }

    $objects = New-Object System.Collections.Generic.List[object]
    foreach ($flat in $flattenedRows) {
        $ordered = [ordered]@{}
        foreach ($key in $allKeys) {
            if ($flat.Contains($key)) { $ordered[$key] = $flat[$key] } else { $ordered[$key] = '' }
        }
        $objects.Add([pscustomobject]$ordered)
    }

    $objects.ToArray() | Export-Csv -LiteralPath $csvPath -NoTypeInformation -Encoding UTF8

    try {
        if ($script:Settings -and [System.Convert]::ToBoolean($script:Settings['WriteRawJsonCompanion'])) {
            ($recordArray | ConvertTo-Json -Depth 100) | Set-Content -LiteralPath $jsonPath -Encoding UTF8
        }
    } catch { }

    Write-Ui "Exported CSV: $csvPath" Green 'export.csv'
    Write-AppLog -Level INFO -Event 'export.completed' -Message 'CSV export completed.' -Data @{ csv_path=$csvPath; json_path=$jsonPath; base_name=$BaseName; row_count=(Get-SafeCount $recordArray); column_count=$allKeys.Count }
    return $csvPath
}

function Show-ObjectDetails {
    param($Record, [string]$Title = 'Record details')
    Write-Section $Title
    $flat = ConvertTo-FlattenedHashtable $Record
    $rows = New-Object System.Collections.Generic.List[object]
    foreach ($key in $flat.Keys) {
        $rows.Add([pscustomobject]@{ Field=$key; Value=ConvertTo-ShortText $flat[$key] 120 })
    }
    Show-AsciiTable -Rows $rows.ToArray() -Columns @('Field','Value') -Widths @{ Field=42; Value=120 } -MaxRows ([int]$script:Settings['ConsoleRowLimit'])
    Write-Ui "Flattened field count: $($flat.Keys.Count). CSV export includes all fields." DarkGray 'details.field_count'
}

function Confirm-YesNo {
    param([string]$Prompt, [bool]$DefaultYes = $true)
    $suffix = if ($DefaultYes) { '[Y/n]' } else { '[y/N]' }
    $raw = Read-Host "$Prompt $suffix"
    Write-AppLog -Level INFO -Event 'user.confirm' -Message $Prompt -Data @{ response=$raw; default_yes=$DefaultYes }
    if ([string]::IsNullOrWhiteSpace($raw)) { return $DefaultYes }
    return ($raw -match '^[yY]')
}

function Pause-ForUser {
    [void](Read-Host 'Press Enter to continue')
}

function Get-ActivePatients {
    Write-Section 'Pull most recent active patient roster'
    $query = Get-BaseQuery
    $patients = @(Invoke-AllevaCollection -Path $script:ClientsPath -Query $query -Label 'active-patient-roster')
    $active = @($patients | Where-Object { Test-IsActivePatient $_ })
    $script:LastAllPatients = $patients
    $script:LastActivePatients = $active

    Write-Ui "Pulled $(Get-SafeCount $patients) patient records; active roster has $(Get-SafeCount $active) records." Green 'patients.active_count'
    Write-AppLog -Level INFO -Event 'patients.active_roster_pulled' -Message 'Active patients pulled.' -Data @{ total=(Get-SafeCount $patients); active=(Get-SafeCount $active) }
    return $active
}

function Show-ActivePatientRosterWorkflow {
    $active = @(Get-ActivePatients)
    $rows = New-Object System.Collections.Generic.List[object]
    $i = 1
    foreach ($patient in $active) {
        $rows.Add((Get-PatientSummaryRow -Patient $patient -Index $i))
        $i++
    }

    Show-AsciiTable -Rows $rows.ToArray() -Columns @('#','PatientId','Name','Status','DOB','Updated') -Widths @{ '#'=4; PatientId=18; Name=34; Status=28; DOB=14; Updated=24 }
    if (Confirm-YesNo 'Export the active patient roster to CSV?' $true) {
        [void](Export-FlattenedCsv -Records $active -BaseName 'active_patient_roster')
    }
}

function Get-PatientMapById {
    param([AllowNull()]$Patients)
    $map = @{}
    foreach ($patient in @(ConvertTo-ObjectArraySafe $Patients)) {
        $id = Get-PatientId $patient
        if ($id -and -not $map.ContainsKey($id)) { $map[$id] = $patient }
    }
    return $map
}

function Pull-TreatmentPlansMappedWorkflow {
    Write-Section 'Pull treatment plans mapped to associated patients'

    $active = $script:LastActivePatients
    if ((Get-SafeCount $active) -eq 0 -or (Confirm-YesNo 'Refresh active patient roster first?' $true)) {
        $active = @(Get-ActivePatients)
    }

    $patientMap = Get-PatientMapById $active
    $query = Get-BaseQuery -ForTreatmentPlans
    $plans = @(Invoke-AllevaCollection -Path $script:TreatmentPlansPath -Query $query -Label 'treatment-plans-mapped')
    $script:LastTreatmentPlans = $plans

    $rows = New-Object System.Collections.Generic.List[object]
    $i = 1
    foreach ($plan in $plans) {
        $rows.Add((Get-PlanSummaryRow -Plan $plan -PatientMap $patientMap -Index $i))
        $i++
    }

    Write-Ui "Pulled $(Get-SafeCount $plans) treatment-plan records." Green 'plans.count'
    Show-AsciiTable -Rows $rows.ToArray() -Columns @('#','PlanId','PatientId','PatientName','Updated','Status','Title') -Widths @{ '#'=4; PlanId=18; PatientId=18; PatientName=28; Updated=24; Status=22; Title=32 }

    if (Confirm-YesNo 'Export treatment-plan mapping/index to CSV?' $true) {
        [void](Export-FlattenedCsv -Records $rows.ToArray() -BaseName 'treatment_plans_mapped_to_patients_index')
    }
    if (Confirm-YesNo 'Export raw treatment-plan records to CSV too?' $false) {
        [void](Export-FlattenedCsv -Records $plans -BaseName 'treatment_plans_raw_list')
    }
}

function Select-Patient {
    $active = $script:LastActivePatients
    if ((Get-SafeCount $active) -eq 0) { $active = @(Get-ActivePatients) }

    $rows = New-Object System.Collections.Generic.List[object]
    $i = 1
    foreach ($patient in $active) {
        $rows.Add((Get-PatientSummaryRow -Patient $patient -Index $i))
        $i++
    }

    Write-Section 'Select a patient'
    Show-AsciiTable -Rows $rows.ToArray() -Columns @('#','PatientId','Name','Status','DOB','Updated') -Widths @{ '#'=4; PatientId=18; Name=34; Status=28; DOB=14; Updated=24 } -MaxRows 500

    while ($true) {
        $choice = Read-Host 'Enter row # or patient ID, or B to go back'
        Write-AppLog -Level INFO -Event 'user.patient_select' -Message 'Patient selection entered.' -Data @{ choice=$choice }
        if ($choice -match '^[bB]$') { return $null }

        $idx = 0
        if ([int]::TryParse($choice, [ref]$idx)) {
            if ($idx -ge 1 -and $idx -le (Get-SafeCount $active)) { return $active[$idx - 1] }
        }

        foreach ($patient in $active) {
            if ((Get-PatientId $patient) -eq $choice.Trim()) { return $patient }
        }

        Write-Ui 'Selection not found. Try again.' DarkYellow 'user.selection_not_found' WARN
    }
}

function Get-TreatmentPlansForPatient {
    param([Parameter(Mandatory=$true)][string]$PatientId)
    $query = Get-BaseQuery -ForTreatmentPlans
    $query['ClientId'] = $PatientId
    $plans = @(Invoke-AllevaCollection -Path $script:TreatmentPlansPath -Query $query -Label "patient-$PatientId-treatment-plans")
    Write-AppLog -Level INFO -Event 'plans.patient_index_pulled' -Message 'Treatment plans for patient pulled.' -Data @{ patient_id=$PatientId; count=(Get-SafeCount $plans) }
    return $plans
}

function Invoke-FullTreatmentPlanPull {
    param($Plan)
    $planId = Get-PlanId $Plan
    if ([string]::IsNullOrWhiteSpace($planId)) { throw 'Selected treatment plan does not have a recognizable ID.' }

    try {
        $detail = Invoke-AllevaGet -Path ("/treatment-plans/$planId") -Query @{ 'api-version' = ([string]$script:Settings['ApiVersion']).Trim() } -Label "treatment-plan-$planId-detail"
        Write-AppLog -Level INFO -Event 'plans.detail_pulled' -Message 'Full treatment-plan detail pulled.' -Data @{ plan_id=$planId; source='detail_endpoint' }
        return $detail
    } catch {
        Write-Ui "Detail endpoint failed for treatment plan $planId. Falling back to the list record. Error: $($_.Exception.Message)" DarkYellow 'plans.detail_fallback' WARN
        Write-AppLog -Level WARN -Event 'plans.detail_fallback' -Message $_.Exception.Message -Data @{ plan_id=$planId }
        return $Plan
    }
}

function Pull-PatientTreatmentPlansWorkflow {
    $patient = Select-Patient
    if ($null -eq $patient) { return }

    $patientId = Get-PatientId $patient
    $patientName = Get-PatientName $patient
    Write-Section "Treatment plans for $patientName ($patientId)"

    $plans = @(Get-TreatmentPlansForPatient -PatientId $patientId)
    if ((Get-SafeCount $plans) -eq 0) {
        Write-Ui 'No treatment plans were returned for this patient.' DarkYellow 'plans.none_for_patient' WARN
        return
    }

    $patientMap = @{ $patientId = $patient }
    $rows = New-Object System.Collections.Generic.List[object]
    $i = 1
    foreach ($plan in $plans) {
        $rows.Add((Get-PlanSummaryRow -Plan $plan -PatientMap $patientMap -Index $i))
        $i++
    }

    Show-AsciiTable -Rows $rows.ToArray() -Columns @('#','PlanId','PatientId','PatientName','Updated','Status','Title') -Widths @{ '#'=4; PlanId=18; PatientId=18; PatientName=28; Updated=24; Status=22; Title=32 } -MaxRows 500

    if (Confirm-YesNo 'Export this patient treatment-plan index to CSV?' $true) {
        [void](Export-FlattenedCsv -Records $rows.ToArray() -BaseName "patient_${patientId}_treatment_plans_index")
    }

    $choice = Read-Host 'Enter treatment-plan row # to pull full details, A for all, or B to go back'
    Write-AppLog -Level INFO -Event 'user.plan_select' -Message 'Treatment plan selection entered.' -Data @{ patient_id=$patientId; choice=$choice }
    if ($choice -match '^[bB]$') { return }

    $selected = New-Object System.Collections.Generic.List[object]
    if ($choice -match '^[aA]$') {
        foreach ($plan in $plans) { $selected.Add($plan) }
    } else {
        $idx = 0
        if ([int]::TryParse($choice, [ref]$idx) -and $idx -ge 1 -and $idx -le (Get-SafeCount $plans)) {
            $selected.Add($plans[$idx - 1])
        } else {
            Write-Ui 'Selection not found.' DarkYellow 'user.selection_not_found' WARN
            return
        }
    }

    $details = New-Object System.Collections.Generic.List[object]
    foreach ($plan in $selected) {
        $detail = Invoke-FullTreatmentPlanPull -Plan $plan
        $details.Add($detail)
        Show-ObjectDetails -Record $detail -Title ("Full treatment-plan fields: plan $(Get-PlanId $plan), patient $patientId")
        if (Confirm-YesNo 'Export this full treatment plan to CSV?' $true) {
            [void](Export-FlattenedCsv -Records @($detail) -BaseName "patient_${patientId}_treatment_plan_$(Get-PlanId $plan)_full_fields")
        }
    }

    if ((Get-SafeCount $details.ToArray()) -gt 1) {
        if (Confirm-YesNo 'Export all pulled treatment plans for this patient into one CSV?' $true) {
            [void](Export-FlattenedCsv -Records $details.ToArray() -BaseName "patient_${patientId}_multiple_treatment_plans_full_fields")
        }
    }
}

function PatientRecordWorkflow {
    $patient = Select-Patient
    if ($null -eq $patient) { return }
    $patientId = Get-PatientId $patient
    $patientName = Get-PatientName $patient

    Show-ObjectDetails -Record $patient -Title "Patient record details: $patientName ($patientId)"
    if (Confirm-YesNo 'Export this patient record to CSV?' $true) {
        [void](Export-FlattenedCsv -Records @($patient) -BaseName "patient_${patientId}_record")
    }
}

function Open-OutputFoldersWorkflow {
    Write-Section 'Output folders'
    Write-Ui "Logs for this run: $script:SessionDirectory" Green 'folders.logs'
    Write-Ui "Exports:           $ExportDirectory" Green 'folders.exports'

    if (Confirm-YesNo 'Open the export folder in File Explorer?' $true) {
        try { Invoke-Item -LiteralPath $ExportDirectory } catch { Write-Ui "Could not open export folder: $($_.Exception.Message)" DarkYellow 'folders.open_failed' WARN }
    }
}

function Show-Header {
    Clear-Host
    Write-Host ''
    Write-Host 'R3 / Alleva End-User Data Pull Tool' -ForegroundColor Cyan
    Write-Host "Version: $script:ScriptVersion" -ForegroundColor DarkGray
    Write-Host "Session log: $script:SessionDirectory" -ForegroundColor DarkGray
    Write-Host ''
    Write-PhiReminder
}

function Show-MainMenu {
    Write-Section 'Main menu'
    Write-Host '  1. Pull active patient roster'
    Write-Host '  2. Pull treatment plans mapped to patients'
    Write-Host '  3. Select patient and pull full treatment plan details'
    Write-Host '  4. Select patient and view/export patient record'
    Write-Host '  5. Configure Alleva API settings / credentials'
    Write-Host '  6. Show current settings'
    Write-Host '  7. Run preflight check'
    Write-Host '  8. Show/open log and export folders'
    Write-Host '  0. Exit'
    Write-Host ''
}

function Run-MainMenu {
    Import-Settings
    [void](Test-Prerequisites)

    while ($true) {
        Show-MainMenu
        $choice = Read-Host 'Choose an option'
        Write-AppLog -Level INFO -Event 'menu.choice' -Message 'User selected a menu option.' -Data @{ choice=$choice }

        try {
            switch ($choice) {
                '1' { Show-ActivePatientRosterWorkflow; Pause-ForUser }
                '2' { Pull-TreatmentPlansMappedWorkflow; Pause-ForUser }
                '3' { Pull-PatientTreatmentPlansWorkflow; Pause-ForUser }
                '4' { PatientRecordWorkflow; Pause-ForUser }
                '5' { Edit-SettingsMenu; Pause-ForUser }
                '6' { Show-Settings; Pause-ForUser }
                '7' { [void](Test-Prerequisites); Pause-ForUser }
                '8' { Open-OutputFoldersWorkflow; Pause-ForUser }
                '0' { Write-Ui 'Exiting.' Green 'app.exit_requested'; return }
                default { Write-Ui 'Invalid option. Choose 0 through 8.' DarkYellow 'menu.invalid' WARN; Pause-ForUser }
            }
        } catch {
            Write-Ui "Error: $($_.Exception.Message)" Red 'workflow.error' ERROR
            Write-AppLog -Level ERROR -Event 'workflow.exception' -Message $_.Exception.Message -Data ([ordered]@{
                script_stack_trace = $_.ScriptStackTrace
                category = $_.CategoryInfo.ToString()
            })
            Pause-ForUser
        }
    }
}

try {
    Initialize-Logging
    Show-Header
    Run-MainMenu
} finally {
    Stop-Logging
}