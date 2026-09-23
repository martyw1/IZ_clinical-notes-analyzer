<#
.SYNOPSIS
  End-user friendly Alleva EMR terminal tool for R3 patient roster and treatment-plan pulls.

.DESCRIPTION
  This is the supported Alleva diagnostic and export entry point. Use it when an
  operator needs a guided PowerShell menu to:

    - Pull the most recent active patient roster.
    - Pull treatment plans and map them to associated patients.
    - Pick a patient, see available treatment plans, and pull full detail for one or more plans.
    - View patient record details.
    - Export the complete roster and every treatment-plan list/detail field to one navigable XLSX.
    - Keep privacy-safe structured event counts without payloads, names, identifiers, URLs, or credentials.

  It calls Alleva directly. It does not log into the IZ Clinical Notes Analyzer app.
  It reuses the same local settings file as the current diagnostic script:

    alleva-remote-diagnostics.local.json

.PHI WARNING
  Exports contain patient data. Keep the diag-build-tools folder local,
  access-controlled, and out of Git, tickets, email, and chat.
#>

[CmdletBinding()]
param(
    [ValidateSet('Menu','ExportAll','SelfTest')]
    [string]$Action = 'Menu',
    [switch]$NoRun,
    [switch]$NoPause,
    [string]$SettingsPath = '',
    [string]$LogDirectory = '',
    [string]$ExportDirectory = '',
    [scriptblock]$PageProvider = $null,
    [scriptblock]$DetailProvider = $null,
    [scriptblock]$RetryDelayProvider = $null,
    [ValidateRange(2, 1048576)]
    [int]$WorksheetRowLimit = 1048576,
    [scriptblock]$FailureHook = $null
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

$script:ScriptVersion = '2026-07-15-r3-alleva-complete-export-6'
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
$script:LastActivePatients = @()
$script:LastAllPatients = @()
$script:LastTreatmentPlans = @()
$script:ClientsPath = '/clients'
$script:TreatmentPlansPath = '/treatment-plans'
$script:ActiveStatusId = '1049'
$script:DischargedStatusId = '1356'
$script:NoPause = [bool]$NoPause
$script:PageProvider = $PageProvider
$script:DetailProvider = $DetailProvider
$script:RetryDelayProvider = $RetryDelayProvider
$script:WorksheetRowLimit = $WorksheetRowLimit
$script:LongFormAuditRowLimit = 25000
$script:FailureHook = $FailureHook
$script:SettingsEnvelopeFormat = 'R3-ALLEVA-DPAPI-SETTINGS-V1'

function Invoke-InjectedFailureHook {
    param([Parameter(Mandatory=$true)][string]$Stage)
    if ($null -ne $script:FailureHook) {
        & $script:FailureHook $Stage
    }
}

function New-TimestampText {
    return (Get-Date).ToString('yyyyMMdd-HHmmss')
}

function New-AllevaExportFileName {
    param(
        [Parameter(Mandatory=$true)][ValidateSet('complete-export','focused-csv','focused-json')][string]$Kind,
        [Parameter(Mandatory=$true)][ValidateSet('.xlsx','.csv','.json')][string]$Extension,
        [AllowEmptyString()][string]$Status = ''
    )
    $stamp = (Get-Date).ToString('yyyyMMdd-HHmmss-fff')
    $nonce = [guid]::NewGuid().ToString('N').Substring(0, 8)
    $statusPart = if ([string]::IsNullOrWhiteSpace($Status)) { '' } else { '-' + $Status.ToUpperInvariant() }
    return "alleva-$Kind-$stamp-$nonce$statusPart$Extension"
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

    $safeEvent = if ($Event -match '^[A-Za-z0-9._-]{1,80}$') { $Event } else { 'event.invalid_name' }
    $entry = [ordered]@{
        timestamp = New-IsoTimestampText
        level = $Level
        event = $safeEvent
    }

    $allowedIntegerKeys = @(
        'duration_ms','page_count','raw_count','unique_count','duplicate_count','retry_count',
        'attempt_count','record_count','total_count','active_count','detail_success_count',
        'detail_failure_count','mapping_miss_count','worksheet_count','row_count'
    )
    $allowedTextKeys = @('action','status','error_class','termination_reason')
    $allowedBooleanKeys = @('complete')
    $allowedEndpointLabels = @('clients','treatment-plans','treatment-plan-detail','token','export','self-test','menu','preflight')
    if ($null -ne $Data) {
        $dataNames = if ($Data -is [System.Collections.IDictionary]) { @($Data.Keys) } else { @($Data.PSObject.Properties.Name) }
        foreach ($nameValue in $dataNames) {
            $name = ([string]$nameValue).ToLowerInvariant()
            $value = if ($Data -is [System.Collections.IDictionary]) { $Data[$nameValue] } else { (Get-PropValue $Data @([string]$nameValue)) }
            if ($allowedIntegerKeys -contains $name) {
                $number = [int64]0
                if ([int64]::TryParse([string]$value, [ref]$number) -and $number -ge 0) { $entry[$name] = $number }
                continue
            }
            if ($allowedBooleanKeys -contains $name) {
                if ($value -is [bool]) { $entry[$name] = [bool]$value }
                continue
            }
            if ($name -eq 'endpoint_label') {
                $endpointText = ([string]$value).ToLowerInvariant()
                if ($allowedEndpointLabels -contains $endpointText) { $entry[$name] = $endpointText }
                continue
            }
            if ($allowedTextKeys -contains $name) {
                $text = [string]$value
                if ($text -match '^[A-Za-z0-9._-]{1,80}$') { $entry[$name] = $text }
            }
        }
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
    New-Item -ItemType File -Path $script:EventLogPath -Force | Out-Null

    Write-AppLog -Level INFO -Event 'app.started' -Data ([ordered]@{ action = 'menu'; status = 'started' })
}

function Stop-Logging {
    Write-AppLog -Level INFO -Event 'app.exited' -Data ([ordered]@{ status = 'stopped' })
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
    Write-Ui '  This tool calls Alleva directly. Excel exports contain patient data.' DarkYellow 'phi.reminder'
    Write-Ui '  Structured event logs contain status and aggregate counts only.' DarkYellow 'phi.reminder'
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

function Write-EncryptedSettingsFile {
    param([Parameter(Mandatory=$true)][System.Collections.IDictionary]$Settings)

    $parent = Split-Path -Parent $SettingsPath
    Ensure-Directory -Path $parent
    $payload = $Settings | ConvertTo-Json -Depth 40 -Compress
    $envelope = [ordered]@{
        Format = $script:SettingsEnvelopeFormat
        ProtectedPayload = ConvertTo-ProtectedString $payload
    }
    $temporaryPath = Join-Path $parent ('.{0}.{1}.tmp' -f [IO.Path]::GetFileName($SettingsPath), [guid]::NewGuid().ToString('N'))
    try {
        ($envelope | ConvertTo-Json -Compress) | Set-Content -LiteralPath $temporaryPath -Encoding UTF8
        Invoke-InjectedFailureHook -Stage 'Settings.BeforePublish'
        if ([IO.File]::Exists($SettingsPath)) {
            if ($null -eq ('Alleva.NativeFileMethods' -as [type])) {
                Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace Alleva {
    public static class NativeFileMethods {
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool MoveFileEx(string existingName, string newName, int flags);
    }
}
'@
            }
            $moveReplaceExisting = 0x1
            $moveWriteThrough = 0x8
            if (-not [Alleva.NativeFileMethods]::MoveFileEx($temporaryPath, $SettingsPath, ($moveReplaceExisting -bor $moveWriteThrough))) {
                throw (New-Object ComponentModel.Win32Exception([Runtime.InteropServices.Marshal]::GetLastWin32Error()))
            }
        } else {
            [IO.File]::Move($temporaryPath, $SettingsPath)
        }
    } finally {
        if ([IO.File]::Exists($temporaryPath)) { [IO.File]::Delete($temporaryPath) }
    }
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
                $parsed = ConvertTo-HashtableDeep ($json | ConvertFrom-Json)
                $legacyPlaintext = $true
                $hasEnvelopeMarker = $parsed.Contains('Format') -or $parsed.Contains('ProtectedPayload')
                if ($hasEnvelopeMarker -and $parsed.Contains('Format') -and [string]$parsed['Format'] -eq $script:SettingsEnvelopeFormat) {
                    $protectedPayload = [string]$parsed['ProtectedPayload']
                    if ([string]::IsNullOrWhiteSpace($protectedPayload)) { throw 'Encrypted settings payload is missing.' }
                    $plainPayload = ConvertFrom-ProtectedString $protectedPayload
                    if ([string]::IsNullOrWhiteSpace($plainPayload)) { throw 'Encrypted settings payload could not be decrypted.' }
                    $loaded = ConvertTo-HashtableDeep ($plainPayload | ConvertFrom-Json)
                    $legacyPlaintext = $false
                } elseif ($hasEnvelopeMarker) {
                    throw 'Unsupported or malformed encrypted settings envelope.'
                } else {
                    $loaded = $parsed
                }
                foreach ($key in $loaded.Keys) {
                    if ($settings.Contains($key)) {
                        $settings[$key] = $loaded[$key]
                    }
                }
                if ($legacyPlaintext) { Write-EncryptedSettingsFile -Settings $settings }
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
    Write-EncryptedSettingsFile -Settings $script:Settings
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
    Write-Host "AllevaApiBaseUrl configured: $([bool]([string]$script:Settings['AllevaApiBaseUrl']))"
    Write-Host "AllevaTokenUrl configured:   $([bool]([string]$script:Settings['AllevaTokenUrl']))"
    Write-Host "ClientId configured:        $([bool]([string]$script:Settings['ClientId']))"
    Write-Host "ClientSecret configured:    $([bool]([string]$script:Settings['ClientSecretProtected']))"
    Write-Host "Scope configured:           $([bool]([string]$script:Settings['Scope']))"
    Write-Host "Connection options:         configured (values masked)"
    Write-Host "Limit / MaxPages:           $($script:Settings['Limit']) / $($script:Settings['MaxPages'])"
    Write-Host "StartDate configured:       $([bool]([string]$script:Settings['StartDate']))"
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

    foreach ($cmdName in @('Invoke-WebRequest','ConvertFrom-Json','ConvertTo-Json','Export-Csv')) {
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
            ErrorCategory = ''
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

        $errorCategory = $_.Exception.GetType().Name
        if ($_.Exception -is [System.TimeoutException] -or $_.Exception.InnerException -is [System.TimeoutException] -or $_.Exception.Message -match '(?i)timed?\s*out|timeout') { $errorCategory = 'Timeout' }
        try {
            if ($_.Exception -is [System.Net.WebException] -and $_.Exception.Status -eq [System.Net.WebExceptionStatus]::Timeout) { $errorCategory = 'Timeout' }
        } catch { }

        return [pscustomobject]@{
            Ok = $false
            StatusCode = $status
            StatusDescription = $statusDescription
            Content = $content
            Headers = $headers
            DurationMs = $sw.ElapsedMilliseconds
            Error = $_.Exception.Message
            ErrorCategory = $errorCategory
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

        Write-AppLog -Level INFO -Event 'api.token_response' -Data ([ordered]@{
            endpoint_label = 'token'
            status = if ($resp.Ok) { 'success' } else { 'failure' }
            duration_ms = $resp.DurationMs
            error_class = $resp.ErrorCategory
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

function Get-CompleteExportQuery {
    param([switch]$ForTreatmentPlans)
    $query = Get-BaseQuery -ForTreatmentPlans:$ForTreatmentPlans
    $query['Cursor'] = 0
    $query['Limit'] = 5000
    return $query
}

function Get-AllevaConfiguredPageCap {
    $pageCap = 10
    try { $pageCap = [int]$script:Settings['MaxPages'] } catch { }
    return [Math]::Max(1, [Math]::Min(10000, $pageCap))
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

    $endpointLabel = if ($Path -eq $script:ClientsPath) { 'clients' } elseif ($Path -eq $script:TreatmentPlansPath) { 'treatment-plans' } else { 'treatment-plan-detail' }
    Write-AppLog -Level INFO -Event 'api.get_response' -Data ([ordered]@{
        endpoint_label = $endpointLabel
        status = if ($resp.Ok) { 'success' } else { 'failure' }
        duration_ms = $resp.DurationMs
        error_class = $resp.ErrorCategory
    })

    if (-not $resp.Ok) {
        $exception = New-Object System.Exception(("Alleva request failed with HTTP status {0}." -f $resp.StatusCode))
        $exception.Data['StatusCode'] = [int]$resp.StatusCode
        $exception.Data['ErrorCategory'] = if ([string]::IsNullOrWhiteSpace([string]$resp.ErrorCategory)) { 'RequestFailure' } else { [string]$resp.ErrorCategory }
        try {
            $retryAfter = $resp.Headers['Retry-After']
            if ($null -ne $retryAfter) { $exception.Data['RetryAfter'] = [string]$retryAfter }
        } catch { }
        throw $exception
    }

    $payload = ConvertFrom-JsonSafe $resp.Content
    if ($null -eq $payload) { throw "GET $Path responded, but the response was not parseable JSON." }
    return $payload
}

function Get-PropertyState {
    param([AllowNull()]$Object, [string[]]$Names)
    if ($null -eq $Object) {
        return [pscustomobject]@{ Present = $false; Name = ''; Value = $null }
    }

    if ($Object -is [System.Collections.IDictionary]) {
        foreach ($wanted in $Names) {
            foreach ($key in $Object.Keys) {
                if ([string]::Equals([string]$key, [string]$wanted, [System.StringComparison]::OrdinalIgnoreCase)) {
                    return [pscustomobject]@{ Present = $true; Name = [string]$key; Value = $Object[$key] }
                }
            }
        }
    }

    try {
        foreach ($wanted in $Names) {
            foreach ($property in $Object.PSObject.Properties) {
                if ([string]::Equals([string]$property.Name, [string]$wanted, [System.StringComparison]::OrdinalIgnoreCase)) {
                    return [pscustomobject]@{ Present = $true; Name = [string]$property.Name; Value = $property.Value }
                }
            }
        }
    } catch { }

    return [pscustomobject]@{ Present = $false; Name = ''; Value = $null }
}

function ConvertTo-PaginationBoolean {
    param([AllowNull()]$Value)
    if ($Value -is [bool]) { return [pscustomobject]@{ Valid = $true; Value = [bool]$Value } }
    if ($null -ne $Value) {
        $text = ([string]$Value).Trim()
        if ([string]::Equals($text, 'true', [System.StringComparison]::OrdinalIgnoreCase)) {
            return [pscustomobject]@{ Valid = $true; Value = $true }
        }
        if ([string]::Equals($text, 'false', [System.StringComparison]::OrdinalIgnoreCase)) {
            return [pscustomobject]@{ Valid = $true; Value = $false }
        }
    }
    return [pscustomobject]@{ Valid = $false; Value = $false }
}

function ConvertTo-PaginationTotal {
    param([AllowNull()]$Value)
    $parsed = [int64]0
    if ($null -ne $Value -and [int64]::TryParse(([string]$Value).Trim(), [ref]$parsed) -and $parsed -ge 0) {
        return [pscustomobject]@{ Valid = $true; Value = $parsed }
    }
    return [pscustomobject]@{ Valid = $false; Value = [int64]0 }
}

function ConvertTo-PaginationToken {
    param([AllowNull()]$Value)
    if ($null -eq $Value) {
        return [pscustomobject]@{ Valid = $true; Value = ''; HasToken = $false }
    }
    if ($Value -is [string]) {
        $text = $Value.Trim()
        return [pscustomobject]@{ Valid = $true; Value = $text; HasToken = (-not [string]::IsNullOrWhiteSpace($text)) }
    }

    $isIntegral = (
        $Value -is [byte] -or $Value -is [sbyte] -or
        $Value -is [int16] -or $Value -is [uint16] -or
        $Value -is [int32] -or $Value -is [uint32] -or
        $Value -is [int64] -or $Value -is [uint64]
    )
    if ($isIntegral) {
        $text = ([System.IFormattable]$Value).ToString($null, [System.Globalization.CultureInfo]::InvariantCulture)
        return [pscustomobject]@{ Valid = $true; Value = $text; HasToken = $true }
    }

    return [pscustomobject]@{ Valid = $false; Value = ''; HasToken = $false }
}

function Get-PaginationMetadata {
    param([AllowNull()]$Payload)
    $nextStates = New-Object System.Collections.Generic.List[object]
    $hasMoreStates = New-Object System.Collections.Generic.List[object]
    $totalStates = New-Object System.Collections.Generic.List[object]
    $seenNames = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($name in @('nextCursor','next_cursor','continuationToken','continuation_token')) {
        $state = Get-PropertyState $Payload @($name)
        if ($state.Present -and $seenNames.Add($state.Name)) { $nextStates.Add($state) }
    }
    $seenNames.Clear()
    foreach ($name in @('hasMore','has_more')) {
        $state = Get-PropertyState $Payload @($name)
        if ($state.Present -and $seenNames.Add($state.Name)) { $hasMoreStates.Add($state) }
    }
    $seenNames.Clear()
    foreach ($name in @('total','totalCount','total_count')) {
        $state = Get-PropertyState $Payload @($name)
        if ($state.Present -and $seenNames.Add($state.Name)) { $totalStates.Add($state) }
    }

    $conflict = $false
    $valid = $true
    $nextToken = ''
    $hasNextToken = $false
    $normalizedNextTokens = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
    foreach ($state in $nextStates) {
        $parsedToken = ConvertTo-PaginationToken $state.Value
        if (-not $parsedToken.Valid) {
            $valid = $false
            continue
        }
        $normalized = $parsedToken.Value
        [void]$normalizedNextTokens.Add($normalized)
        if ([string]::IsNullOrWhiteSpace($nextToken) -and $parsedToken.HasToken) { $nextToken = $normalized }
    }
    if ($normalizedNextTokens.Count -gt 1) { $conflict = $true }
    $hasNextToken = -not [string]::IsNullOrWhiteSpace($nextToken)

    $hasMore = $false
    $normalizedHasMore = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
    foreach ($state in $hasMoreStates) {
        $parsedBoolean = ConvertTo-PaginationBoolean $state.Value
        if (-not $parsedBoolean.Valid) {
            $valid = $false
        } else {
            $hasMore = $parsedBoolean.Value
            [void]$normalizedHasMore.Add(([string]$parsedBoolean.Value).ToLowerInvariant())
        }
    }
    if ($normalizedHasMore.Count -gt 1) { $conflict = $true }

    $total = [int64]0
    $normalizedTotals = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
    foreach ($state in $totalStates) {
        $parsedTotal = ConvertTo-PaginationTotal $state.Value
        if (-not $parsedTotal.Valid) {
            $valid = $false
        } else {
            $total = $parsedTotal.Value
            [void]$normalizedTotals.Add([string]$parsedTotal.Value)
        }
    }
    if ($normalizedTotals.Count -gt 1) { $conflict = $true }

    return [pscustomobject]@{
        Valid = $valid
        Conflict = $conflict
        NextTokenPropertyPresent = ($nextStates.Count -gt 0)
        HasNextToken = $hasNextToken
        NextToken = $nextToken
        HasMorePresent = ($hasMoreStates.Count -gt 0)
        HasMore = $hasMore
        TotalPresent = ($totalStates.Count -gt 0)
        Total = $total
    }
}

function Get-StructuralFingerprint {
    param([AllowNull()]$Value)
    $builder = New-Object System.Text.StringBuilder
    $stack = New-Object System.Collections.ArrayList
    [void]$stack.Add([pscustomobject]@{ Path = '$'; Value = $Value })

    while ($stack.Count -gt 0) {
        $last = $stack.Count - 1
        $frame = $stack[$last]
        $stack.RemoveAt($last)
        $currentPath = [string]$frame.Path
        $currentValue = $frame.Value

        if ($null -eq $currentValue) {
            [void]$builder.Append($currentPath).Append("|null|")
            continue
        }
        if (Test-IsScalarLike $currentValue) {
            [void]$builder.Append($currentPath).Append('|scalar|').Append($currentValue.GetType().FullName).Append('|').Append([string]$currentValue).Append('|')
            continue
        }
        if ($currentValue -is [System.Collections.IDictionary]) {
            $keys = @($currentValue.Keys | ForEach-Object { [string]$_ } | Sort-Object)
            [void]$builder.Append($currentPath).Append('|object|').Append($keys.Count).Append('|')
            for ($index = $keys.Count - 1; $index -ge 0; $index--) {
                $key = $keys[$index]
                [void]$stack.Add([pscustomobject]@{ Path = "$currentPath.$key"; Value = $currentValue[$key] })
            }
            continue
        }
        if (Test-IsEnumerableCollection $currentValue) {
            $items = @(ConvertTo-ObjectArraySafe $currentValue)
            [void]$builder.Append($currentPath).Append('|array|').Append($items.Count).Append('|')
            for ($index = $items.Count - 1; $index -ge 0; $index--) {
                [void]$stack.Add([pscustomobject]@{ Path = ('{0}[{1}]' -f $currentPath, $index); Value = $items[$index] })
            }
            continue
        }

        $names = @(Get-PropertyNamesSafe $currentValue | Sort-Object)
        [void]$builder.Append($currentPath).Append('|object|').Append($names.Count).Append('|')
        for ($index = $names.Count - 1; $index -ge 0; $index--) {
            $name = [string]$names[$index]
            [void]$stack.Add([pscustomobject]@{ Path = "$currentPath.$name"; Value = (Get-PropValue $currentValue @($name)) })
        }
    }

    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($builder.ToString())
        return ([BitConverter]::ToString($algorithm.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    } finally {
        $algorithm.Dispose()
    }
}

function Get-CollectionRecordIdentity {
    param([AllowNull()]$Record)
    $identity = Get-PropValue $Record @('id','Id','clientId','ClientId','patientId','PatientId','treatmentPlanId','TreatmentPlanId')
    if ($null -ne $identity -and -not [string]::IsNullOrWhiteSpace(([string]$identity))) {
        return 'id:' + ([string]$identity).Trim()
    }
    return 'hash:' + (Get-StructuralFingerprint $Record)
}

function New-CollectionResult {
    param(
        [bool]$Complete,
        [string]$TerminationReason,
        [int]$PageCount,
        [int64]$RawRecordCount,
        [int64]$UniqueRecordCount,
        [int64]$DuplicateRecordCount,
        [int]$PeakPageRecordCount,
        [int64]$InitialOffset,
        [System.Collections.Generic.List[object]]$Records,
        [string]$ErrorCategory = ''
    )
    $recordArray = if ($null -eq $Records) { @() } else { $Records.ToArray() }
    return [pscustomobject]@{
        Status = if ($Complete) { 'COMPLETE' } else { 'INCOMPLETE' }
        Complete = $Complete
        TerminationReason = $TerminationReason
        PageCount = $PageCount
        RawRecordCount = $RawRecordCount
        UniqueRecordCount = $UniqueRecordCount
        DuplicateRecordCount = $DuplicateRecordCount
        PeakPageRecordCount = $PeakPageRecordCount
        InitialOffset = $InitialOffset
        RetainedRecordCount = (Get-SafeCount $recordArray)
        Records = $recordArray
        ErrorCategory = $ErrorCategory
    }
}

function Invoke-CompleteCollection {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [hashtable]$Query = @{},
        [string]$Label = '',
        [ValidateRange(1, 1000000)][int]$SafetyPageCap = 10000,
        [scriptblock]$OnRecord = $null,
        [scriptblock]$IdentitySelector = $null,
        [switch]$CollectRecords
    )

    $limit = 500
    try { $limit = [Math]::Max(1, [Math]::Min(5000, [int]$Query['Limit'])) } catch { $limit = 500 }

    $cursorKey = 'Cursor'
    foreach ($candidate in @('Cursor','cursor','Offset','offset')) {
        if ($Query.ContainsKey($candidate)) { $cursorKey = $candidate; break }
    }
    $currentCursor = if ($Query.ContainsKey($cursorKey)) { $Query[$cursorKey] } else { 0 }
    $numericCursor = [int64]0
    $cursorIsNumeric = [int64]::TryParse(([string]$currentCursor), [ref]$numericCursor) -and $numericCursor -ge 0
    $initialOffset = if ($cursorIsNumeric) { $numericCursor } else { [int64]0 }

    $retained = New-Object System.Collections.Generic.List[object]
    $seenRecordIds = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
    $seenPageFingerprints = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
    $seenRequestCursors = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
    $rawCount = [int64]0
    $uniqueCount = [int64]0
    $duplicateCount = [int64]0
    $peakPageCount = 0
    $pageCount = 0
    $knownTotal = $null

    while ($pageCount -lt $SafetyPageCap) {
        $requestCursorKey = if ($cursorIsNumeric) { 'number:' + [string]$numericCursor } else { 'token:' + [string]$currentCursor }
        if (-not $seenRequestCursors.Add($requestCursorKey)) {
            return New-CollectionResult $false 'repeated_cursor' $pageCount $rawCount $uniqueCount $duplicateCount $peakPageCount $initialOffset $retained
        }

        $pageQuery = @{}
        foreach ($key in $Query.Keys) { $pageQuery[$key] = $Query[$key] }
        $pageQuery['Limit'] = $limit
        $pageQuery[$cursorKey] = if ($cursorIsNumeric) { $numericCursor } else { $currentCursor }

        try {
            if ($null -ne $script:PageProvider) {
                $payload = & $script:PageProvider $Path $pageQuery "$Label-page-$pageCount" $pageCount
            } else {
                $payload = Invoke-AllevaGet -Path $Path -Query $pageQuery -Label "$Label-page-$pageCount"
            }
        } catch {
            return New-CollectionResult $false 'api_error' $pageCount $rawCount $uniqueCount $duplicateCount $peakPageCount $initialOffset $retained $_.Exception.GetType().Name
        }

        $pageCount++
        $pageRecords = @(Get-RecordsFromPayload $payload)
        $pageRecordCount = Get-SafeCount $pageRecords
        if ($pageRecordCount -gt $peakPageCount) { $peakPageCount = $pageRecordCount }
        $rawCount += $pageRecordCount

        $pageIdentityBuilder = New-Object System.Text.StringBuilder
        foreach ($record in $pageRecords) {
            $recordIdentity = if ($null -ne $IdentitySelector) { [string](& $IdentitySelector $record) } else { Get-CollectionRecordIdentity $record }
            if ([string]::IsNullOrWhiteSpace($recordIdentity)) { $recordIdentity = 'hash:' + (Get-StructuralFingerprint $record) }
            [void]$pageIdentityBuilder.Append($recordIdentity).Append('|')
            if ($seenRecordIds.Add($recordIdentity)) {
                $uniqueCount++
                if ($CollectRecords) { $retained.Add($record) }
                if ($null -ne $OnRecord) { [void](& $OnRecord $record) }
            } else {
                $duplicateCount++
            }
        }

        $pageFingerprint = Get-StructuralFingerprint ([ordered]@{ count = $pageRecordCount; identities = $pageIdentityBuilder.ToString() })
        if ($pageRecordCount -gt 0 -and -not $seenPageFingerprints.Add($pageFingerprint)) {
            return New-CollectionResult $false 'repeated_page' $pageCount $rawCount $uniqueCount $duplicateCount $peakPageCount $initialOffset $retained
        }

        $metadata = Get-PaginationMetadata $payload
        if ($metadata.Conflict) {
            return New-CollectionResult $false 'contradictory_metadata' $pageCount $rawCount $uniqueCount $duplicateCount $peakPageCount $initialOffset $retained
        }
        if (-not $metadata.Valid) {
            return New-CollectionResult $false 'unknown_pagination_metadata' $pageCount $rawCount $uniqueCount $duplicateCount $peakPageCount $initialOffset $retained
        }
        if ((Test-IsEnumerableCollection $payload) -and $limit -ge 5000 -and $pageRecordCount -lt $limit) {
            return New-CollectionResult $true 'unpaged_short_page' $pageCount $rawCount $uniqueCount $duplicateCount $peakPageCount $initialOffset $retained
        }
        if ($metadata.TotalPresent) {
            if ($null -ne $knownTotal -and [int64]$knownTotal -ne [int64]$metadata.Total) {
                return New-CollectionResult $false 'contradictory_metadata' $pageCount $rawCount $uniqueCount $duplicateCount $peakPageCount $initialOffset $retained
            }
            $knownTotal = [int64]$metadata.Total
            if ([int64]$knownTotal -lt $initialOffset -or $uniqueCount -gt ([int64]$knownTotal - $initialOffset)) {
                return New-CollectionResult $false 'contradictory_metadata' $pageCount $rawCount $uniqueCount $duplicateCount $peakPageCount $initialOffset $retained
            }
        }

        $totalReached = $false
        if ($null -ne $knownTotal) { $totalReached = ($uniqueCount -eq ([int64]$knownTotal - $initialOffset)) }

        if ($metadata.HasMorePresent -and -not $metadata.HasMore -and $metadata.HasNextToken) {
            return New-CollectionResult $false 'contradictory_metadata' $pageCount $rawCount $uniqueCount $duplicateCount $peakPageCount $initialOffset $retained
        }
        if ($pageRecordCount -eq 0) {
            if (($metadata.HasMorePresent -and $metadata.HasMore) -or $metadata.HasNextToken -or ($null -ne $knownTotal -and -not $totalReached)) {
                return New-CollectionResult $false 'contradictory_metadata' $pageCount $rawCount $uniqueCount $duplicateCount $peakPageCount $initialOffset $retained
            }
            return New-CollectionResult $true 'empty_page' $pageCount $rawCount $uniqueCount $duplicateCount $peakPageCount $initialOffset $retained
        }
        if ($metadata.HasMorePresent -and -not $metadata.HasMore) {
            if ($null -ne $knownTotal -and -not $totalReached) {
                return New-CollectionResult $false 'contradictory_metadata' $pageCount $rawCount $uniqueCount $duplicateCount $peakPageCount $initialOffset $retained
            }
            return New-CollectionResult $true 'has_more_false' $pageCount $rawCount $uniqueCount $duplicateCount $peakPageCount $initialOffset $retained
        }
        if ($metadata.HasNextToken) {
            if ($totalReached) {
                return New-CollectionResult $false 'contradictory_metadata' $pageCount $rawCount $uniqueCount $duplicateCount $peakPageCount $initialOffset $retained
            }
            $nextCursorKey = 'token:' + $metadata.NextToken
            if ($nextCursorKey -eq $requestCursorKey -or $seenRequestCursors.Contains($nextCursorKey)) {
                return New-CollectionResult $false 'repeated_cursor' $pageCount $rawCount $uniqueCount $duplicateCount $peakPageCount $initialOffset $retained
            }
            $currentCursor = $metadata.NextToken
            $cursorIsNumeric = $false
            continue
        }
        if ($totalReached) {
            if ($metadata.HasMorePresent -and $metadata.HasMore) {
                return New-CollectionResult $false 'contradictory_metadata' $pageCount $rawCount $uniqueCount $duplicateCount $peakPageCount $initialOffset $retained
            }
            return New-CollectionResult $true 'validated_total' $pageCount $rawCount $uniqueCount $duplicateCount $peakPageCount $initialOffset $retained
        }
        if (-not $cursorIsNumeric) {
            return New-CollectionResult $false 'unknown_pagination_metadata' $pageCount $rawCount $uniqueCount $duplicateCount $peakPageCount $initialOffset $retained
        }

        $numericCursor += [int64]$pageRecordCount
        $currentCursor = $numericCursor
    }

    return New-CollectionResult $false 'safety_page_cap' $pageCount $rawCount $uniqueCount $duplicateCount $peakPageCount $initialOffset $retained
}

function Invoke-AllevaCollection {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [hashtable]$Query = @{},
        [int]$MaxPages = 0,
        [string]$Label = ''
    )

    $pageCap = if ($MaxPages -gt 0) { [Math]::Min(10000, $MaxPages) } else { Get-AllevaConfiguredPageCap }
    $result = Invoke-CompleteCollection -Path $Path -Query $Query -Label $Label -SafetyPageCap $pageCap -CollectRecords
    if (-not $result.Complete) {
        throw ("Collection {0} is incomplete ({1}) after {2} page(s)." -f $Label, $result.TerminationReason, $result.PageCount)
    }
    return $result.Records
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
    $stack = New-Object System.Collections.ArrayList
    [void]$stack.Add([pscustomobject]@{ Path = $Prefix; Value = $Value })

    while ($stack.Count -gt 0) {
        $last = $stack.Count - 1
        $frame = $stack[$last]
        $stack.RemoveAt($last)
        $currentPath = [string]$frame.Path
        $currentValue = $frame.Value

        if ($null -eq $currentValue) {
            $Output[$currentPath] = ''
            continue
        }
        if (Test-IsScalarLike $currentValue) {
            $Output[$currentPath] = [string]$currentValue
            continue
        }
        if ($currentValue -is [System.Collections.IDictionary]) {
            $keys = @($currentValue.Keys)
            if ($keys.Count -eq 0) {
                $Output[$currentPath] = '{}'
                continue
            }
            for ($index = $keys.Count - 1; $index -ge 0; $index--) {
                $key = $keys[$index]
                [void]$stack.Add([pscustomobject]@{ Path = ("$currentPath.$key"); Value = $currentValue[$key] })
            }
            continue
        }
        if (Test-IsEnumerableCollection $currentValue) {
            $items = @(ConvertTo-ObjectArraySafe $currentValue)
            if ($items.Count -eq 0) {
                $Output[$currentPath] = '[]'
                continue
            }
            for ($index = $items.Count - 1; $index -ge 0; $index--) {
                [void]$stack.Add([pscustomobject]@{ Path = ('{0}[{1}]' -f $currentPath, $index); Value = $items[$index] })
            }
            continue
        }

        $names = @(Get-PropertyNamesSafe $currentValue)
        if ($names.Count -eq 0) {
            $Output[$currentPath] = ConvertTo-ShortText $currentValue 32000
            continue
        }
        for ($index = $names.Count - 1; $index -ge 0; $index--) {
            $name = [string]$names[$index]
            [void]$stack.Add([pscustomobject]@{ Path = ("$currentPath.$name"); Value = (Get-PropValue $currentValue @($name)) })
        }
    }
}

function ConvertTo-FlattenedHashtable {
    param($Record)
    $flat = [ordered]@{}

    if ($Record -is [System.Collections.IDictionary]) {
        foreach ($key in $Record.Keys) {
            Add-FlattenedValue -Output $flat -Prefix ([string]$key) -Value $Record[$key]
        }
        return $flat
    }

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

function Initialize-AllevaZipTypes {
    if ($null -eq ('System.IO.Compression.ZipArchive' -as [type])) {
        Add-Type -AssemblyName System.IO.Compression
    }
    if ($null -eq ('System.IO.Compression.ZipFile' -as [type])) {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
    }
}

function ConvertTo-AllevaCellText {
    param([AllowNull()]$Value)

    if ($null -eq $Value) { return '' }
    if ($Value -is [datetime]) { return $Value.ToString('o', [Globalization.CultureInfo]::InvariantCulture) }
    if ($Value -is [datetimeoffset]) { return $Value.ToString('o', [Globalization.CultureInfo]::InvariantCulture) }
    if ($Value -is [System.IFormattable] -and -not ($Value -is [string])) {
        return $Value.ToString($null, [Globalization.CultureInfo]::InvariantCulture)
    }
    return [string]$Value
}

function ConvertTo-AllevaXmlSafeText {
    param([AllowNull()]$Value)

    $text = ConvertTo-AllevaCellText $Value
    if ([string]::IsNullOrEmpty($text)) { return '' }

    $builder = New-Object System.Text.StringBuilder
    for ($index = 0; $index -lt $text.Length; $index++) {
        $code = [int][char]$text[$index]
        if ($code -eq 9 -or $code -eq 10 -or $code -eq 13 -or ($code -ge 32 -and $code -le 55295) -or ($code -ge 57344 -and $code -le 65533)) {
            [void]$builder.Append($text[$index])
            continue
        }
        if ($code -ge 55296 -and $code -le 56319 -and ($index + 1) -lt $text.Length) {
            $nextCode = [int][char]$text[$index + 1]
            if ($nextCode -ge 56320 -and $nextCode -le 57343) {
                [void]$builder.Append($text[$index])
                [void]$builder.Append($text[$index + 1])
                $index++
                continue
            }
        }
        [void]$builder.Append(('\u{0:X4}' -f $code))
    }
    return $builder.ToString()
}

function Get-AllevaExcelColumnName {
    param([Parameter(Mandatory=$true)][ValidateRange(1, 16384)][int]$Index)

    $name = ''
    [int]$value = $Index
    while ($value -gt 0) {
        $value--
        $name = ([char][int](65 + ($value % 26))).ToString() + $name
        $value = [int][Math]::Floor(([double]$value / 26.0))
    }
    return $name
}

function Get-AllevaExcelColumnIndex {
    param([Parameter(Mandatory=$true)][string]$Name)

    $index = 0
    foreach ($character in $Name.ToUpperInvariant().ToCharArray()) {
        if ($character -lt 'A' -or $character -gt 'Z') { throw 'Excel column name is invalid.' }
        $index = ($index * 26) + ([int]$character - [int][char]'A' + 1)
    }
    if ($index -lt 1 -or $index -gt 16384) { throw 'Excel column index is out of range.' }
    return $index
}

function Get-AllevaWorkbookRowValue {
    param([AllowNull()]$Row, [Parameter(Mandatory=$true)][string]$Column)

    if ($null -eq $Row) { return $null }
    if ($Row -is [System.Collections.IDictionary]) {
        if ($Row.Contains($Column)) { return $Row[$Column] }
        foreach ($key in $Row.Keys) {
            if ([string]::Equals([string]$key, $Column, [StringComparison]::OrdinalIgnoreCase)) { return $Row[$key] }
        }
        return $null
    }
    $property = $Row.PSObject.Properties[$Column]
    if ($null -eq $property) {
        foreach ($candidate in $Row.PSObject.Properties) {
            if ([string]::Equals($candidate.Name, $Column, [StringComparison]::OrdinalIgnoreCase)) { $property = $candidate; break }
        }
    }
    if ($null -eq $property) { return $null }
    return $property.Value
}

function Write-AllevaInlineStringCell {
    param(
        [Parameter(Mandatory=$true)][System.Xml.XmlWriter]$Writer,
        [Parameter(Mandatory=$true)][string]$Reference,
        [AllowNull()]$Value,
        [int]$StyleIndex = 2
    )

    $text = ConvertTo-AllevaXmlSafeText $Value
    if ($text.Length -gt 32000) {
        throw "Cell $Reference exceeds the 32,000-character safe cell limit. Use a field-value row so it can be chunked."
    }
    $namespace = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    $Writer.WriteStartElement('c', $namespace)
    $Writer.WriteAttributeString('r', $Reference)
    $Writer.WriteAttributeString('s', [string]$StyleIndex)
    $Writer.WriteAttributeString('t', 'inlineStr')
    $Writer.WriteStartElement('is', $namespace)
    $Writer.WriteStartElement('t', $namespace)
    $Writer.WriteAttributeString('xml', 'space', 'http://www.w3.org/XML/1998/namespace', 'preserve')
    $Writer.WriteString($text)
    $Writer.WriteEndElement()
    $Writer.WriteEndElement()
    $Writer.WriteEndElement()
}

function Get-AllevaUniqueSheetName {
    param(
        [Parameter(Mandatory=$true)][string]$BaseName,
        [Parameter(Mandatory=$true)][int]$PartNumber,
        [Parameter(Mandatory=$true)][bool]$AlwaysNumber,
        [Parameter(Mandatory=$true)][AllowEmptyCollection()][System.Collections.Generic.HashSet[string]]$UsedNames
    )

    $safeBase = $BaseName -replace '[\\/:*?\[\]]', '_'
    if ([string]::IsNullOrWhiteSpace($safeBase)) { $safeBase = 'Sheet' }
    $suffix = if ($AlwaysNumber -or $PartNumber -gt 1) { " $PartNumber" } else { '' }
    $maximumBaseLength = 31 - $suffix.Length
    if ($safeBase.Length -gt $maximumBaseLength) { $safeBase = $safeBase.Substring(0, $maximumBaseLength) }
    $candidate = "$safeBase$suffix"
    $collision = 2
    while ($UsedNames.Contains($candidate)) {
        $collisionSuffix = " $collision"
        $candidateBase = $safeBase
        if (($candidateBase.Length + $collisionSuffix.Length) -gt 31) { $candidateBase = $candidateBase.Substring(0, 31 - $collisionSuffix.Length) }
        $candidate = "$candidateBase$collisionSuffix"
        $collision++
    }
    [void]$UsedNames.Add($candidate)
    return $candidate
}

function Start-AllevaWorksheetPart {
    param([Parameter(Mandatory=$true)][hashtable]$State)

    $sheetId = $State.PackageState.NextSheetId
    $State.PackageState.NextSheetId++
    $State.PartNumber++
    $sheetName = Get-AllevaUniqueSheetName -BaseName $State.BaseName -PartNumber $State.PartNumber -AlwaysNumber $State.AlwaysNumber -UsedNames $State.PackageState.UsedSheetNames
    $entryName = "xl/worksheets/sheet$sheetId.xml"
    $entry = $State.PackageState.Archive.CreateEntry($entryName, [System.IO.Compression.CompressionLevel]::Fastest)
    $stream = $entry.Open()
    $settings = New-Object System.Xml.XmlWriterSettings
    $settings.Encoding = New-Object System.Text.UTF8Encoding($false)
    $settings.Indent = $false
    $settings.CloseOutput = $false
    $writer = [System.Xml.XmlWriter]::Create($stream, $settings)
    $namespace = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    $writer.WriteStartDocument()
    $writer.WriteStartElement('worksheet', $namespace)
    $writer.WriteStartElement('sheetViews', $namespace)
    $writer.WriteStartElement('sheetView', $namespace)
    $writer.WriteAttributeString('workbookViewId', '0')
    $writer.WriteStartElement('pane', $namespace)
    $writer.WriteAttributeString('ySplit', '1')
    $writer.WriteAttributeString('topLeftCell', 'A2')
    $writer.WriteAttributeString('activePane', 'bottomLeft')
    $writer.WriteAttributeString('state', 'frozen')
    $writer.WriteEndElement()
    $writer.WriteEndElement()
    $writer.WriteEndElement()
    $writer.WriteStartElement('cols', $namespace)
    for ($columnIndex = 0; $columnIndex -lt $State.Columns.Count; $columnIndex++) {
        $headerLength = ([string]$State.Columns[$columnIndex]).Length
        $width = [Math]::Min(40, [Math]::Max(12, $headerLength + 2))
        $writer.WriteStartElement('col', $namespace)
        $writer.WriteAttributeString('min', [string]($columnIndex + 1))
        $writer.WriteAttributeString('max', [string]($columnIndex + 1))
        $writer.WriteAttributeString('width', $width.ToString([Globalization.CultureInfo]::InvariantCulture))
        $writer.WriteAttributeString('customWidth', '1')
        $writer.WriteEndElement()
    }
    $writer.WriteEndElement()
    $writer.WriteStartElement('sheetData', $namespace)
    $writer.WriteStartElement('row', $namespace)
    $writer.WriteAttributeString('r', '1')
    for ($columnIndex = 0; $columnIndex -lt $State.Columns.Count; $columnIndex++) {
        $reference = (Get-AllevaExcelColumnName ($columnIndex + 1)) + '1'
        Write-AllevaInlineStringCell -Writer $writer -Reference $reference -Value $State.Columns[$columnIndex] -StyleIndex 1
    }
    $writer.WriteEndElement()

    $metadata = [pscustomobject]@{
        Name = $sheetName
        SheetId = $sheetId
        RelationshipId = "rId$sheetId"
        EntryName = $entryName
        DataRowCount = 0
        TotalRowCount = 1
        ColumnCount = $State.Columns.Count
        Columns = @($State.Columns)
        FirstDataCell = $null
    }
    $State.PackageState.Sheets.Add($metadata)
    $State.Current = @{
        Writer = $writer
        Stream = $stream
        Metadata = $metadata
    }
}

function Stop-AllevaWorksheetPart {
    param([Parameter(Mandatory=$true)][hashtable]$State)

    if ($null -eq $State.Current) { return }
    $writer = $State.Current.Writer
    $metadata = $State.Current.Metadata
    $namespace = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    try {
        $writer.WriteEndElement()
        $writer.WriteStartElement('autoFilter', $namespace)
        $lastColumn = Get-AllevaExcelColumnName $metadata.ColumnCount
        $writer.WriteAttributeString('ref', ("A1:{0}{1}" -f $lastColumn, $metadata.TotalRowCount))
        $writer.WriteEndElement()
        $writer.WriteEndElement()
        $writer.WriteEndDocument()
        $writer.Flush()
    } finally {
        $writer.Dispose()
        $State.Current.Stream.Dispose()
        $State.Current = $null
    }
}

function Write-AllevaWorksheetDataRow {
    param(
        [Parameter(Mandatory=$true)][hashtable]$State,
        [Parameter(Mandatory=$true)][System.Collections.IDictionary]$Values
    )

    if ($null -eq $State.Current) { Start-AllevaWorksheetPart -State $State }
    if ($State.Current.Metadata.TotalRowCount -ge $State.RowLimit) {
        Stop-AllevaWorksheetPart -State $State
        Start-AllevaWorksheetPart -State $State
    }
    $metadata = $State.Current.Metadata
    $rowNumber = $metadata.TotalRowCount + 1
    $writer = $State.Current.Writer
    $namespace = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    $writer.WriteStartElement('row', $namespace)
    $writer.WriteAttributeString('r', [string]$rowNumber)
    if ($State.SparseRows) {
        $columnIndexes = New-Object System.Collections.Generic.List[int]
        for ($columnIndex = 0; $columnIndex -lt $State.DenseColumnCount; $columnIndex++) { $columnIndexes.Add($columnIndex) }
        foreach ($column in $Values.Keys) {
            if ($State.ColumnIndexes.ContainsKey([string]$column)) {
                $columnIndex = [int]$State.ColumnIndexes[[string]$column]
                if ($columnIndex -ge $State.DenseColumnCount) { $columnIndexes.Add($columnIndex) }
            }
        }
        $indexesToWrite = @($columnIndexes | Sort-Object -Unique)
    } else {
        $indexesToWrite = @(0..($State.Columns.Count - 1))
    }
    foreach ($columnIndex in $indexesToWrite) {
        $column = [string]$State.Columns[$columnIndex]
        $value = $Values[$column]
        $safeText = ConvertTo-AllevaXmlSafeText (ConvertTo-AllevaCellText $value)
        if ($rowNumber -eq 2 -and $columnIndex -eq 0) { $metadata.FirstDataCell = $safeText }
        if ($safeText.Length -eq 0 -and $columnIndex -ge $State.DenseColumnCount) { continue }
        $reference = (Get-AllevaExcelColumnName ($columnIndex + 1)) + $rowNumber
        Write-AllevaInlineStringCell -Writer $writer -Reference $reference -Value $safeText -StyleIndex 2
    }
    $writer.WriteEndElement()
    $metadata.DataRowCount++
    $metadata.TotalRowCount++
    $State.PackageState.TotalDataRowCount++
}

function Write-AllevaLogicalWorkbookRow {
    param(
        [Parameter(Mandatory=$true)][hashtable]$State,
        [AllowNull()]$Row
    )

    $values = [ordered]@{}
    if ($State.SparseRows) {
        for ($columnIndex = 0; $columnIndex -lt $State.DenseColumnCount; $columnIndex++) {
            $column = [string]$State.Columns[$columnIndex]
            $values[$column] = Get-AllevaWorkbookRowValue -Row $Row -Column $column
        }
        $rowColumns = if ($Row -is [System.Collections.IDictionary]) { @($Row.Keys) } else { @(Get-PropertyNamesSafe $Row) }
        foreach ($rowColumn in $rowColumns) {
            $name = [string]$rowColumn
            if ($State.ColumnIndexes.ContainsKey($name) -and [int]$State.ColumnIndexes[$name] -ge $State.DenseColumnCount) {
                $canonicalName = [string]$State.Columns[[int]$State.ColumnIndexes[$name]]
                $values[$canonicalName] = Get-AllevaWorkbookRowValue -Row $Row -Column $name
            }
        }
    } else {
        foreach ($column in $State.Columns) { $values[$column] = Get-AllevaWorkbookRowValue -Row $Row -Column $column }
    }
    if (-not [string]::IsNullOrWhiteSpace([string]$State.ForcedStatus) -and $State.BaseName -eq 'Summary') {
        $metric = [string]$values['Metric']
        if ($metric -match '^(?i:status|exportstatus|export_status)$') { $values['Value'] = $State.ForcedStatus }
    }
    if (-not $State.IsFieldSheet) {
        Write-AllevaWorksheetDataRow -State $State -Values $values
        return
    }

    $safeValue = ConvertTo-AllevaXmlSafeText $values['Value']
    $segments = New-Object System.Collections.Generic.List[object]
    if ($safeValue.Length -eq 0) {
        $segments.Add([pscustomobject]@{ Start = 0; Length = 0 })
    } else {
        $segmentStart = 0
        while ($segmentStart -lt $safeValue.Length) {
            $segmentLength = [Math]::Min(32000, $safeValue.Length - $segmentStart)
            if (($segmentStart + $segmentLength) -lt $safeValue.Length -and [char]::IsHighSurrogate($safeValue[$segmentStart + $segmentLength - 1])) {
                $segmentLength--
            }
            $segments.Add([pscustomobject]@{ Start = $segmentStart; Length = $segmentLength })
            $segmentStart += $segmentLength
        }
    }
    $chunkCount = $segments.Count
    for ($chunkIndex = 1; $chunkIndex -le $chunkCount; $chunkIndex++) {
        $segment = $segments[$chunkIndex - 1]
        $chunk = if ($segment.Length -eq 0) { '' } else { $safeValue.Substring($segment.Start, $segment.Length) }
        $chunkValues = [ordered]@{}
        foreach ($column in $State.Columns) { $chunkValues[$column] = $values[$column] }
        $chunkValues['Value'] = $chunk
        $chunkValues['ChunkIndex'] = $chunkIndex
        $chunkValues['ChunkCount'] = $chunkCount
        Write-AllevaWorksheetDataRow -State $State -Values $chunkValues
    }
}

function Write-AllevaZipTextEntry {
    param(
        [Parameter(Mandatory=$true)][System.IO.Compression.ZipArchive]$Archive,
        [Parameter(Mandatory=$true)][string]$Name,
        [Parameter(Mandatory=$true)][string]$Content
    )

    $entry = $Archive.CreateEntry($Name, [System.IO.Compression.CompressionLevel]::Optimal)
    $stream = $entry.Open()
    $writer = New-Object System.IO.StreamWriter($stream, (New-Object System.Text.UTF8Encoding($false)))
    try { $writer.Write($Content) } finally { $writer.Dispose(); $stream.Dispose() }
}

function Write-AllevaWorkbookPackageParts {
    param([Parameter(Mandatory=$true)][hashtable]$PackageState)

    $sheetOverrides = New-Object System.Text.StringBuilder
    $workbookSheets = New-Object System.Text.StringBuilder
    $workbookRelationships = New-Object System.Text.StringBuilder
    foreach ($sheet in $PackageState.Sheets) {
        [void]$sheetOverrides.Append(('<Override PartName="/{0}" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' -f $sheet.EntryName))
        [void]$workbookSheets.Append(('<sheet name="{0}" sheetId="{1}" r:id="{2}"/>' -f [Security.SecurityElement]::Escape($sheet.Name), $sheet.SheetId, $sheet.RelationshipId))
        [void]$workbookRelationships.Append(('<Relationship Id="{0}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{1}.xml"/>' -f $sheet.RelationshipId, $sheet.SheetId))
    }

    $contentTypes = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' + $sheetOverrides.ToString() + '</Types>'
    $rootRelationships = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    $workbook = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView/></bookViews><sheets>' + $workbookSheets.ToString() + '</sheets></workbook>'
    $relationships = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + $workbookRelationships.ToString() + ('<Relationship Id="rId{0}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>' -f ($PackageState.Sheets.Count + 1))
    $styles = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/><family val="2"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/><family val="2"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="49" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyNumberFormat="1"/><xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'

    Write-AllevaZipTextEntry -Archive $PackageState.Archive -Name '[Content_Types].xml' -Content $contentTypes
    Write-AllevaZipTextEntry -Archive $PackageState.Archive -Name '_rels/.rels' -Content $rootRelationships
    Write-AllevaZipTextEntry -Archive $PackageState.Archive -Name 'xl/workbook.xml' -Content $workbook
    Write-AllevaZipTextEntry -Archive $PackageState.Archive -Name 'xl/_rels/workbook.xml.rels' -Content $relationships
    Write-AllevaZipTextEntry -Archive $PackageState.Archive -Name 'xl/styles.xml' -Content $styles
}

function Read-AllevaZipXmlEntry {
    param(
        [Parameter(Mandatory=$true)][System.IO.Compression.ZipArchive]$Archive,
        [Parameter(Mandatory=$true)][string]$Name
    )

    $entry = $Archive.GetEntry($Name)
    if ($null -eq $entry) { throw "Workbook package is missing required part: $Name" }
    $stream = $entry.Open()
    $document = New-Object System.Xml.XmlDocument
    $document.PreserveWhitespace = $true
    try { $document.Load($stream) } finally { $stream.Dispose() }
    return $document
}

function Test-AllevaWorksheetEntryStreaming {
    param(
        [Parameter(Mandatory=$true)][System.IO.Compression.ZipArchive]$Archive,
        [Parameter(Mandatory=$true)]$Expected
    )

    $entry = $Archive.GetEntry([string]$Expected.EntryName)
    if ($null -eq $entry) { throw "Workbook package is missing required part: $($Expected.EntryName)" }
    $stream = $entry.Open()
    $settings = New-Object System.Xml.XmlReaderSettings
    $settings.DtdProcessing = [System.Xml.DtdProcessing]::Prohibit
    $settings.XmlResolver = $null
    $reader = [System.Xml.XmlReader]::Create($stream, $settings)
    $rowCount = 0
    $currentRow = 0
    $cellCount = 0
    $currentCell = 0
    $lastCell = 0
    $paneValid = $false
    $filterReference = ''
    $firstDataCell = ''
    try {
        while ($reader.Read()) {
            if ($reader.NodeType -eq [System.Xml.XmlNodeType]::Element) {
                switch ($reader.LocalName) {
                    'pane' {
                        $paneValid = ($reader.GetAttribute('state') -eq 'frozen' -and $reader.GetAttribute('ySplit') -eq '1' -and $reader.GetAttribute('topLeftCell') -eq 'A2')
                    }
                    'autoFilter' { $filterReference = [string]$reader.GetAttribute('ref') }
                    'row' {
                        $rowCount++
                        $currentRow = $rowCount
                        $cellCount = 0
                        $lastCell = 0
                        if ([string]$reader.GetAttribute('r') -ne [string]$currentRow) { throw "Worksheet row reference is not contiguous for $($Expected.Name)." }
                    }
                    'c' {
                        $cellCount++
                        $reference = [string]$reader.GetAttribute('r')
                        if ($reference -notmatch '^([A-Z]+)([0-9]+)$' -or [int]$Matches[2] -ne $currentRow) { throw "Worksheet cell reference is invalid for $($Expected.Name)." }
                        $currentCell = Get-AllevaExcelColumnIndex $Matches[1]
                        if ($currentCell -le $lastCell -or $currentCell -gt [int]$Expected.ColumnCount) { throw "Worksheet cell reference is invalid for $($Expected.Name)." }
                        $lastCell = $currentCell
                        if ([string]$reader.GetAttribute('t') -ne 'inlineStr') { throw "Worksheet cell type is invalid for $($Expected.Name)." }
                    }
                    'f' { throw "Worksheet formula cells are not allowed for $($Expected.Name)." }
                    't' {
                        $textValue = $reader.ReadElementContentAsString()
                        if ($currentRow -eq 1) {
                            if ($currentCell -gt $Expected.Columns.Count -or $textValue -ne [string]$Expected.Columns[$currentCell - 1]) { throw "Worksheet header mismatch for $($Expected.Name)." }
                        } elseif ($currentRow -eq 2 -and $currentCell -eq 1) {
                            $firstDataCell = $textValue
                        }
                    }
                }
            } elseif ($reader.NodeType -eq [System.Xml.XmlNodeType]::EndElement -and $reader.LocalName -eq 'row') {
                if ($currentRow -eq 1 -and $cellCount -ne [int]$Expected.ColumnCount) { throw "Worksheet cell count mismatch for $($Expected.Name)." }
            }
        }
    } finally {
        $reader.Dispose()
        $stream.Dispose()
    }
    if ($rowCount -ne [long]$Expected.TotalRowCount) { throw "Worksheet row count mismatch for $($Expected.Name)." }
    if (-not $paneValid) { throw "Worksheet freeze pane is missing or invalid for $($Expected.Name)." }
    $expectedFilter = 'A1:{0}{1}' -f (Get-AllevaExcelColumnName ([int]$Expected.ColumnCount)), $Expected.TotalRowCount
    if ($filterReference -ne $expectedFilter) { throw "Worksheet auto-filter is missing or invalid for $($Expected.Name)." }
    if ([long]$Expected.DataRowCount -gt 0 -and $firstDataCell -ne [string]$Expected.FirstDataCell) { throw "Worksheet key-cell validation failed for $($Expected.Name)." }
    return $true
}

function Test-AllevaWorkbookPackage {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)]$ExpectedSheets,
        [Parameter(Mandatory=$true)][long]$ExpectedTotalDataRows
    )

    Initialize-AllevaZipTypes
    $archive = [System.IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $contentTypes = Read-AllevaZipXmlEntry -Archive $archive -Name '[Content_Types].xml'
        $rootRelationships = Read-AllevaZipXmlEntry -Archive $archive -Name '_rels/.rels'
        $workbook = Read-AllevaZipXmlEntry -Archive $archive -Name 'xl/workbook.xml'
        $relationships = Read-AllevaZipXmlEntry -Archive $archive -Name 'xl/_rels/workbook.xml.rels'
        [void](Read-AllevaZipXmlEntry -Archive $archive -Name 'xl/styles.xml')

        $contentNamespace = New-Object System.Xml.XmlNamespaceManager($contentTypes.NameTable)
        $contentNamespace.AddNamespace('c', 'http://schemas.openxmlformats.org/package/2006/content-types')
        if ($null -eq $contentTypes.SelectSingleNode('/c:Types/c:Override[@PartName="/xl/workbook.xml"]', $contentNamespace)) { throw 'Workbook content type is missing.' }
        if ($null -eq $contentTypes.SelectSingleNode('/c:Types/c:Override[@PartName="/xl/styles.xml"]', $contentNamespace)) { throw 'Workbook styles content type is missing.' }
        $rootRelationshipNamespace = New-Object System.Xml.XmlNamespaceManager($rootRelationships.NameTable)
        $rootRelationshipNamespace.AddNamespace('p', 'http://schemas.openxmlformats.org/package/2006/relationships')
        $rootOfficeRelationship = $rootRelationships.SelectSingleNode('/p:Relationships/p:Relationship[@Target="xl/workbook.xml"]', $rootRelationshipNamespace)
        if ($null -eq $rootOfficeRelationship -or $rootOfficeRelationship.GetAttribute('Type') -ne 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument') { throw 'Root workbook relationship is missing or invalid.' }

        $workbookNamespace = New-Object System.Xml.XmlNamespaceManager($workbook.NameTable)
        $workbookNamespace.AddNamespace('x', 'http://schemas.openxmlformats.org/spreadsheetml/2006/main')
        $workbookNamespace.AddNamespace('r', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships')
        $sheetNodes = @($workbook.SelectNodes('/x:workbook/x:sheets/x:sheet', $workbookNamespace))
        if ($sheetNodes.Count -ne $ExpectedSheets.Count) { throw 'Workbook sheet count does not reconcile with generated parts.' }

        $relationshipNamespace = New-Object System.Xml.XmlNamespaceManager($relationships.NameTable)
        $relationshipNamespace.AddNamespace('p', 'http://schemas.openxmlformats.org/package/2006/relationships')
        $totalRows = [long]0
        for ($index = 0; $index -lt $ExpectedSheets.Count; $index++) {
            $expected = $ExpectedSheets[$index]
            $sheetNode = $sheetNodes[$index]
            if ($sheetNode.GetAttribute('name') -ne $expected.Name) { throw "Workbook sheet name mismatch at index $index." }
            if ($expected.Name.Length -gt 31) { throw "Workbook sheet name exceeds 31 characters: $($expected.Name)" }
            $relationshipId = $sheetNode.GetAttribute('id', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships')
            $relationshipNode = $relationships.SelectSingleNode(("/p:Relationships/p:Relationship[@Id='{0}']" -f $relationshipId), $relationshipNamespace)
            if ($null -eq $relationshipNode) { throw "Workbook relationship is missing for $($expected.Name)." }
            if ($relationshipNode.GetAttribute('Target') -ne ("worksheets/sheet{0}.xml" -f $expected.SheetId)) { throw "Workbook relationship target is invalid for $($expected.Name)." }
            if ($null -eq $contentTypes.SelectSingleNode(("/c:Types/c:Override[@PartName='/{0}']" -f $expected.EntryName), $contentNamespace)) { throw "Worksheet content type is missing for $($expected.Name)." }

            [void](Test-AllevaWorksheetEntryStreaming -Archive $archive -Expected $expected)
            $totalRows += $expected.DataRowCount
        }
        $stylesRelationship = $relationships.SelectSingleNode('/p:Relationships/p:Relationship[@Target="styles.xml"]', $relationshipNamespace)
        if ($null -eq $stylesRelationship -or $stylesRelationship.GetAttribute('Type') -ne 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles') { throw 'Workbook styles relationship is missing or invalid.' }
        if ($totalRows -ne $ExpectedTotalDataRows) { throw 'Workbook total data-row count does not reconcile.' }
    } finally {
        $archive.Dispose()
    }
    return $true
}

function Invoke-AllevaWorkbookRowSource {
    param(
        [AllowNull()]$Source,
        [Parameter(Mandatory=$true)][hashtable]$State
    )

    if ($null -eq $Source) { return }
    if ($Source -is [scriptblock]) {
        $writeCommand = Get-Command Write-AllevaLogicalWorkbookRow -CommandType Function
        $emit = { param($Row) & $writeCommand -State $State -Row $Row }.GetNewClosure()
        & $Source $emit | Out-Null
        return
    }
    foreach ($row in $Source) { Write-AllevaLogicalWorkbookRow -State $State -Row $row }
}

function Get-AllevaWorkbookColumns {
    param([AllowNull()]$Source, [string[]]$RequiredColumns)

    $columns = New-Object System.Collections.Generic.List[string]
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($column in $RequiredColumns) { if ($seen.Add($column)) { $columns.Add($column) } }
    if ($null -eq $Source -or $Source -is [scriptblock]) { return $columns.ToArray() }
    foreach ($row in @(ConvertTo-ObjectArraySafe $Source)) {
        $names = if ($row -is [System.Collections.IDictionary]) { @($row.Keys) } else { @(Get-PropertyNamesSafe $row) }
        foreach ($name in $names) {
            $column = [string]$name
            if (-not [string]::IsNullOrWhiteSpace($column) -and $seen.Add($column)) { $columns.Add($column) }
        }
    }
    return $columns.ToArray()
}

function New-AllevaWorkbook {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [AllowNull()]$SummaryRows = @(),
        [AllowNull()]$PatientRosterRows = @(),
        [AllowNull()]$PatientFieldRows = @(),
        [AllowNull()]$TreatmentPlanRows = @(),
        [AllowNull()]$TreatmentPlanFieldRows = @(),
        [string[]]$PatientRosterColumns = @(),
        [string[]]$TreatmentPlanColumns = @(),
        [Parameter(Mandatory=$true)][bool]$RetrievalComplete,
        [bool]$IncludeFieldAuditSheets = $true,
        [ValidateRange(2, 1048576)][int]$WorksheetRowLimit = $script:WorksheetRowLimit
    )

    $publicationStatus = if ($RetrievalComplete) { 'COMPLETE' } else { 'INCOMPLETE' }
    $fullPath = [IO.Path]::GetFullPath($Path)
    if ([IO.Path]::GetExtension($fullPath) -ne '.xlsx') { throw 'Workbook path must use the .xlsx extension.' }
    $directory = [IO.Path]::GetDirectoryName($fullPath)
    if ([string]::IsNullOrWhiteSpace($directory)) { throw 'Workbook path must include a valid parent directory.' }
    Ensure-Directory -Path $directory
    Initialize-AllevaZipTypes

    $temporaryPath = Join-Path $directory ('.{0}.{1}.tmp' -f [IO.Path]::GetFileName($fullPath), [guid]::NewGuid().ToString('N'))
    $backupPath = Join-Path $directory ('.{0}.{1}.bak' -f [IO.Path]::GetFileName($fullPath), [guid]::NewGuid().ToString('N'))
    $fileStream = $null
    $archive = $null
    $published = $false
    $packageState = @{
        Archive = $null
        Sheets = New-Object System.Collections.Generic.List[object]
        UsedSheetNames = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        NextSheetId = 1
        TotalDataRowCount = [long]0
    }
    try {
        Invoke-InjectedFailureHook -Stage 'Workbook.BeforeCreate'
        $fileStream = New-Object System.IO.FileStream($temporaryPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        $archive = New-Object System.IO.Compression.ZipArchive($fileStream, [IO.Compression.ZipArchiveMode]::Create, $true)
        $packageState.Archive = $archive

        if ((Get-SafeCount $PatientRosterColumns) -eq 0) {
            $PatientRosterColumns = Get-AllevaWorkbookColumns -Source $PatientRosterRows -RequiredColumns @('PatientId','ClientFullName','LegalFirstName','LegalMiddleName','LegalLastName','PreferredName','Status','DateOfBirth')
        }
        if ((Get-SafeCount $TreatmentPlanColumns) -eq 0) {
            $TreatmentPlanColumns = Get-AllevaWorkbookColumns -Source $TreatmentPlanRows -RequiredColumns @('TreatmentPlanId','PatientId','PatientReferenceId','DetailPatientReferenceId','PatientMappingStatus','ClientFullName','LegalFirstName','LegalMiddleName','LegalLastName','PreferredName','Status','PlanDate')
        }
        $definitions = New-Object System.Collections.Generic.List[object]
        $definitions.Add([pscustomobject]@{ BaseName='Summary'; AlwaysNumber=$false; IsField=$false; Columns=@('Metric','Value'); Source=$SummaryRows })
        $definitions.Add([pscustomobject]@{ BaseName='Patient Roster'; AlwaysNumber=$false; IsField=$false; Columns=$PatientRosterColumns; Source=$PatientRosterRows })
        if ($IncludeFieldAuditSheets) {
            $definitions.Add([pscustomobject]@{ BaseName='Patient Fields'; AlwaysNumber=$false; IsField=$true; Columns=@('PatientId','FieldPath','Value','ChunkIndex','ChunkCount'); Source=$PatientFieldRows })
        }
        $definitions.Add([pscustomobject]@{ BaseName='Treatment Plans'; AlwaysNumber=$false; IsField=$false; Columns=$TreatmentPlanColumns; Source=$TreatmentPlanRows })
        if ($IncludeFieldAuditSheets) {
            $definitions.Add([pscustomobject]@{ BaseName='Treatment Plan Fields'; AlwaysNumber=$true; IsField=$true; Columns=@('TreatmentPlanId','PatientId','PatientMappingStatus','ClientFullName','LegalFirstName','LegalMiddleName','LegalLastName','PreferredName','SourceScope','FieldPath','Value','ChunkIndex','ChunkCount'); Source=$TreatmentPlanFieldRows })
        }
        foreach ($definition in $definitions) {
            if ($definition.Columns.Count -gt 16384) { throw "Worksheet $($definition.BaseName) exceeds Excel's 16,384-column limit." }
            $sparseRows = $definition.BaseName -eq 'Patient Roster' -or $definition.BaseName -eq 'Treatment Plans'
            $denseColumnCount = if ($definition.BaseName -eq 'Patient Roster') { 8 } elseif ($definition.BaseName -eq 'Treatment Plans') { 12 } else { $definition.Columns.Count }
            $columnIndexes = @{}
            for ($columnIndex = 0; $columnIndex -lt $definition.Columns.Count; $columnIndex++) { $columnIndexes[[string]$definition.Columns[$columnIndex]] = $columnIndex }
            $state = @{
                PackageState = $packageState
                BaseName = $definition.BaseName
                AlwaysNumber = [bool]$definition.AlwaysNumber
                IsFieldSheet = [bool]$definition.IsField
                SparseRows = $sparseRows
                DenseColumnCount = $denseColumnCount
                ColumnIndexes = $columnIndexes
                Columns = @($definition.Columns)
                RowLimit = $WorksheetRowLimit
                PartNumber = 0
                Current = $null
                ForcedStatus = if ($RetrievalComplete) { $null } else { 'INCOMPLETE' }
            }
            try {
                if (-not $RetrievalComplete -and $definition.BaseName -eq 'Summary') {
                    Write-AllevaLogicalWorkbookRow -State $state -Row ([pscustomobject]@{ Metric = 'ExportStatus'; Value = 'INCOMPLETE' })
                }
                Invoke-AllevaWorkbookRowSource -Source $definition.Source -State $state
                if ($null -eq $state.Current) { Start-AllevaWorksheetPart -State $state }
            } finally {
                Stop-AllevaWorksheetPart -State $state
            }
        }
        Invoke-InjectedFailureHook -Stage 'Workbook.AfterWorksheets'
        Write-AllevaWorkbookPackageParts -PackageState $packageState
        Invoke-InjectedFailureHook -Stage 'Workbook.BeforeClose'
        $archive.Dispose()
        $archive = $null
        $fileStream.Dispose()
        $fileStream = $null

        Invoke-InjectedFailureHook -Stage 'Workbook.BeforeValidate'
        [void](Test-AllevaWorkbookPackage -Path $temporaryPath -ExpectedSheets $packageState.Sheets.ToArray() -ExpectedTotalDataRows $packageState.TotalDataRowCount)
        Invoke-InjectedFailureHook -Stage 'Workbook.AfterValidate'
        Invoke-InjectedFailureHook -Stage 'Workbook.BeforePublish'
        if ([IO.File]::Exists($fullPath)) {
            [IO.File]::Replace($temporaryPath, $fullPath, $backupPath, $true)
            $published = $true
            if ([IO.File]::Exists($backupPath)) { try { [IO.File]::Delete($backupPath) } catch { } }
        } else {
            [IO.File]::Move($temporaryPath, $fullPath)
            $published = $true
        }
    } finally {
        if ($null -ne $archive) { try { $archive.Dispose() } catch { } }
        if ($null -ne $fileStream) { try { $fileStream.Dispose() } catch { } }
        if ([IO.File]::Exists($temporaryPath)) { try { [IO.File]::Delete($temporaryPath) } catch { } }
        if ([IO.File]::Exists($backupPath)) { try { [IO.File]::Delete($backupPath) } catch { } }
    }
    if (-not $published -or -not [IO.File]::Exists($fullPath)) { throw 'Workbook publication did not produce a final file.' }

    return [pscustomobject]@{
        Status = $publicationStatus
        Path = $fullPath
        WorksheetCount = $packageState.Sheets.Count
        TotalDataRowCount = $packageState.TotalDataRowCount
        RetainedRowCount = 0
        Sheets = $packageState.Sheets.ToArray()
    }
}

function ConvertTo-AllevaExactText {
    param([AllowNull()]$Value)
    if ($null -eq $Value) { return '' }
    if ($Value -is [datetime]) { return $Value.ToString('o', [Globalization.CultureInfo]::InvariantCulture) }
    if ($Value -is [datetimeoffset]) { return $Value.ToString('o', [Globalization.CultureInfo]::InvariantCulture) }
    if ($Value -is [System.IFormattable] -and -not ($Value -is [string])) {
        return $Value.ToString($null, [Globalization.CultureInfo]::InvariantCulture)
    }
    return [string]$Value
}

function Get-AllevaExactCandidate {
    param([AllowNull()]$Record, [string[]]$Paths)
    foreach ($path in $Paths) {
        $value = Get-NestedPropValue -Object $Record -Path @($path -split '\.')
        $text = ConvertTo-AllevaExactText $value
        if (-not [string]::IsNullOrWhiteSpace($text)) { return $text }
    }
    return ''
}

function Get-AllevaPatientIdExact {
    param([AllowNull()]$Patient)
    return Get-AllevaExactCandidate -Record $Patient -Paths @('id','clientId','patientId')
}

function Get-AllevaPlanIdExact {
    param([AllowNull()]$Plan)
    return Get-AllevaExactCandidate -Record $Plan -Paths @('id','treatmentPlanId','treatment_plan_id')
}

function Get-AllevaClientReferenceId {
    param([AllowNull()]$Value)

    $text = ConvertTo-AllevaExactText $Value
    if ([string]::IsNullOrWhiteSpace($text)) { return '' }
    $path = ([Uri]::UnescapeDataString($text.Trim()) -split '[?#]', 2)[0].Trim('/')
    $segments = @($path -split '/')
    for ($index = 0; $index -lt ($segments.Count - 1); $index++) {
        if ([string]::Equals($segments[$index], 'clients', [StringComparison]::OrdinalIgnoreCase)) {
            return ([string]$segments[$index + 1]).Trim()
        }
    }
    return ''
}

function Get-AllevaPlanPatientIdExact {
    param([AllowNull()]$Plan)
    $direct = Get-AllevaExactCandidate -Record $Plan -Paths @('clientId','patientId','client_id','patient_id','client.id','patient.id')
    if (-not [string]::IsNullOrWhiteSpace($direct)) { return $direct }
    $reference = Get-AllevaExactCandidate -Record $Plan -Paths @('client','client.href','links.client','_links.client.href')
    return Get-AllevaClientReferenceId $reference
}

function Get-AllevaPatientNames {
    param([AllowNull()]$Patient)

    $first = Get-AllevaExactCandidate -Record $Patient -Paths @('name.legalFirstName','name.firstName','name.first','legalFirstName','firstName','first_name')
    $middle = Get-AllevaExactCandidate -Record $Patient -Paths @('name.legalMiddleName','name.middleName','name.middle','legalMiddleName','middleName','middle_name')
    $last = Get-AllevaExactCandidate -Record $Patient -Paths @('name.legalLastName','name.lastName','name.last','legalLastName','lastName','last_name')
    $preferred = Get-AllevaExactCandidate -Record $Patient -Paths @('name.preferredName','name.preferred','name.nickname','preferredName','preferred','nickname')
    $full = Get-AllevaExactCandidate -Record $Patient -Paths @('name.clientFullName','name.fullName','clientFullName','fullName','displayName')
    if ([string]::IsNullOrWhiteSpace($full)) {
        $scalarName = Get-PropValue $Patient @('name','Name')
        if ($scalarName -is [string]) { $full = [string]$scalarName }
    }
    if ([string]::IsNullOrWhiteSpace($full)) { $full = (@($first,$middle,$last) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join ' ' }
    if ([string]::IsNullOrWhiteSpace($full)) { $full = $preferred }

    return [pscustomobject]@{
        ClientFullName = $full
        LegalFirstName = $first
        LegalMiddleName = $middle
        LegalLastName = $last
        PreferredName = $preferred
    }
}

function New-AllevaEncryptedRowSpool {
    param([Parameter(Mandatory=$true)][string]$Directory)

    Ensure-Directory -Path $Directory
    if ($null -eq ('System.Security.Cryptography.ProtectedData' -as [type])) { Add-Type -AssemblyName System.Security }
    $path = Join-Path $Directory ('.alleva-export-{0}.spool' -f [guid]::NewGuid().ToString('N'))
    $entropy = New-Object byte[] 32
    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $random.GetBytes($entropy) } finally { $random.Dispose() }
    $stream = New-Object IO.FileStream($path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    $writer = New-Object IO.StreamWriter($stream, (New-Object Text.UTF8Encoding($false)))
    return @{
        Path=$path; Entropy=$entropy; Writer=$writer; Closed=$false;
        LogicalRowCount=[long]0; EmittedRowCount=[long]0
    }
}

function Write-AllevaEncryptedRowSpool {
    param(
        [Parameter(Mandatory=$true)][hashtable]$Spool,
        [Parameter(Mandatory=$true)]$Row
    )

    if ($Spool.Closed) { throw 'Encrypted export spool is already closed.' }
    $json = $Row | ConvertTo-Json -Compress -Depth 30
    $plain = [Text.Encoding]::UTF8.GetBytes($json)
    try {
        $protected = [Security.Cryptography.ProtectedData]::Protect($plain, $Spool.Entropy, [Security.Cryptography.DataProtectionScope]::CurrentUser)
        $Spool.Writer.WriteLine([Convert]::ToBase64String($protected))
    } finally {
        if ($null -ne $plain) { [Array]::Clear($plain, 0, $plain.Length) }
    }
    $Spool.LogicalRowCount++
    $value = ConvertTo-AllevaXmlSafeText (Get-AllevaWorkbookRowValue -Row $Row -Column 'Value')
    $Spool.EmittedRowCount += [Math]::Max(1, [int][Math]::Ceiling(([double]$value.Length / 32000.0)))
}

function Close-AllevaEncryptedRowSpool {
    param([AllowNull()]$Spool)
    if ($null -eq $Spool -or $Spool.Closed) { return }
    try { $Spool.Writer.Flush() } finally { $Spool.Writer.Dispose(); $Spool.Closed = $true }
}

function Get-AllevaEncryptedRowSource {
    param([Parameter(Mandatory=$true)][hashtable]$Spool)

    if (-not $Spool.Closed) { throw 'Encrypted export spool must be closed before it can be read.' }
    $spoolPath = [string]$Spool.Path
    $entropy = $Spool.Entropy
    return {
        param($Emit)
        $enumerator = [IO.File]::ReadLines($spoolPath).GetEnumerator()
        try {
            while ($enumerator.MoveNext()) {
                $line = $enumerator.Current
                if ([string]::IsNullOrWhiteSpace($line)) { continue }
                $protected = [Convert]::FromBase64String($line)
                $plain = $null
                try {
                    $plain = [Security.Cryptography.ProtectedData]::Unprotect($protected, $entropy, [Security.Cryptography.DataProtectionScope]::CurrentUser)
                    $json = [Text.Encoding]::UTF8.GetString($plain)
                    $row = $json | ConvertFrom-Json
                    & $Emit $row
                } finally {
                    if ($null -ne $plain) { [Array]::Clear($plain, 0, $plain.Length) }
                    if ($null -ne $protected) { [Array]::Clear($protected, 0, $protected.Length) }
                }
            }
        } finally {
            $enumerator.Dispose()
        }
    }.GetNewClosure()
}

function Remove-AllevaEncryptedRowSpool {
    param([AllowNull()]$Spool)
    if ($null -eq $Spool) { return }
    try {
        Close-AllevaEncryptedRowSpool $Spool
        if ([IO.File]::Exists([string]$Spool.Path)) { [IO.File]::Delete([string]$Spool.Path) }
    } finally {
        if ($null -ne $Spool.Entropy) { [Array]::Clear($Spool.Entropy, 0, $Spool.Entropy.Length) }
    }
}

function New-AllevaEncryptedPatientIndex {
    param([Parameter(Mandatory=$true)][string]$Directory)

    $root = [IO.Path]::GetFullPath($Directory).TrimEnd([IO.Path]::DirectorySeparatorChar)
    Ensure-Directory -Path $root
    if ($null -eq ('System.Security.Cryptography.ProtectedData' -as [type])) { Add-Type -AssemblyName System.Security }
    $path = Join-Path $root ('.alleva-patient-index-{0}' -f [guid]::NewGuid().ToString('N'))
    [void][IO.Directory]::CreateDirectory($path)
    $entropy = New-Object byte[] 32
    $key = New-Object byte[] 32
    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $random.GetBytes($entropy); $random.GetBytes($key) } finally { $random.Dispose() }
    return @{ Root=$root; Path=$path; Entropy=$entropy; Key=$key }
}

function Ensure-AllevaPatientIndexDirectory {
    param([Parameter(Mandatory=$true)][hashtable]$Index)

    $root = [IO.Path]::GetFullPath([string]$Index.Root).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $path = [IO.Path]::GetFullPath([string]$Index.Path).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $parent = [IO.Path]::GetDirectoryName($path).TrimEnd([IO.Path]::DirectorySeparatorChar)
    if (-not [string]::Equals($parent, $root, [StringComparison]::OrdinalIgnoreCase) -or -not [IO.Path]::GetFileName($path).StartsWith('.alleva-patient-index-', [StringComparison]::Ordinal)) {
        throw 'Refusing to create a patient index outside its owned export directory.'
    }
    if (-not [IO.Directory]::Exists($root)) { throw 'The owned export directory is no longer available.' }
    if ([IO.Directory]::Exists($path)) {
        if (([IO.File]::GetAttributes($path) -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Refusing to use a reparse-point patient index.' }
        return
    }
    [void][IO.Directory]::CreateDirectory($path)
}

function Get-AllevaPatientIndexPath {
    param([Parameter(Mandatory=$true)][hashtable]$Index, [Parameter(Mandatory=$true)][string]$PatientId)
    $hmac = New-Object Security.Cryptography.HMACSHA256(,$Index.Key)
    $bytes = [Text.Encoding]::UTF8.GetBytes($PatientId)
    try {
        $hash = $hmac.ComputeHash($bytes)
        $name = ([BitConverter]::ToString($hash) -replace '-', '').ToLowerInvariant() + '.idx'
        return Join-Path ([string]$Index.Path) $name
    } finally {
        $hmac.Dispose()
        [Array]::Clear($bytes, 0, $bytes.Length)
        if ($null -ne $hash) { [Array]::Clear($hash, 0, $hash.Length) }
    }
}

function Add-AllevaPatientIndexEntry {
    param(
        [Parameter(Mandatory=$true)][hashtable]$Index,
        [Parameter(Mandatory=$true)][string]$PatientId,
        [Parameter(Mandatory=$true)]$Names
    )
    Ensure-AllevaPatientIndexDirectory -Index $Index
    $path = Get-AllevaPatientIndexPath -Index $Index -PatientId $PatientId
    if ([IO.File]::Exists($path)) { return }
    $payload = [pscustomobject]@{ PatientId=$PatientId; Names=$Names } | ConvertTo-Json -Compress -Depth 8
    $plain = [Text.Encoding]::UTF8.GetBytes($payload)
    try {
        $protected = [Security.Cryptography.ProtectedData]::Protect($plain, $Index.Entropy, [Security.Cryptography.DataProtectionScope]::CurrentUser)
        $stream = New-Object IO.FileStream($path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $stream.Write($protected, 0, $protected.Length) } finally { $stream.Dispose() }
    } finally {
        if ($null -ne $plain) { [Array]::Clear($plain, 0, $plain.Length) }
        if ($null -ne $protected) { [Array]::Clear($protected, 0, $protected.Length) }
    }
}

function Get-AllevaPatientIndexEntry {
    param([Parameter(Mandatory=$true)][hashtable]$Index, [AllowEmptyString()][string]$PatientId)
    if ([string]::IsNullOrWhiteSpace($PatientId)) { return $null }
    $path = Get-AllevaPatientIndexPath -Index $Index -PatientId $PatientId
    if (-not [IO.File]::Exists($path)) { return $null }
    $protected = [IO.File]::ReadAllBytes($path)
    $plain = $null
    try {
        $plain = [Security.Cryptography.ProtectedData]::Unprotect($protected, $Index.Entropy, [Security.Cryptography.DataProtectionScope]::CurrentUser)
        $entry = ([Text.Encoding]::UTF8.GetString($plain) | ConvertFrom-Json)
        if (-not [StringComparer]::Ordinal.Equals([string]$entry.PatientId, $PatientId)) { throw 'Patient index identity mismatch.' }
        return $entry.Names
    } finally {
        if ($null -ne $plain) { [Array]::Clear($plain, 0, $plain.Length) }
        if ($null -ne $protected) { [Array]::Clear($protected, 0, $protected.Length) }
    }
}

function Remove-AllevaEncryptedPatientIndex {
    param([AllowNull()]$Index)
    if ($null -eq $Index) { return }
    try {
        $fullPath = [IO.Path]::GetFullPath([string]$Index.Path).TrimEnd([IO.Path]::DirectorySeparatorChar)
        $exportRoot = [IO.Path]::GetFullPath([string]$Index.Root).TrimEnd([IO.Path]::DirectorySeparatorChar)
        $parent = [IO.Path]::GetDirectoryName($fullPath).TrimEnd([IO.Path]::DirectorySeparatorChar)
        if (-not [string]::Equals($parent, $exportRoot, [StringComparison]::OrdinalIgnoreCase) -or -not [IO.Path]::GetFileName($fullPath).StartsWith('.alleva-patient-index-', [StringComparison]::Ordinal)) {
            throw 'Refusing to remove patient index outside the export directory.'
        }
        if ([IO.Directory]::Exists($fullPath)) {
            $attributes = [IO.File]::GetAttributes($fullPath)
            if (($attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Refusing to remove a reparse-point patient index.' }
            [IO.Directory]::Delete($fullPath, $true)
        }
    } finally {
        if ($null -ne $Index.Entropy) { [Array]::Clear($Index.Entropy, 0, $Index.Entropy.Length) }
        if ($null -ne $Index.Key) { [Array]::Clear($Index.Key, 0, $Index.Key.Length) }
    }
}

function Invoke-AllevaExportArtifactCleanup {
    param(
        [AllowNull()][object[]]$Spools,
        [AllowNull()]$PatientIndex
    )
    $firstError = $null
    foreach ($spool in @($Spools)) {
        try { Remove-AllevaEncryptedRowSpool $spool } catch { if ($null -eq $firstError) { $firstError = $_ } }
    }
    try { Remove-AllevaEncryptedPatientIndex $PatientIndex } catch { if ($null -eq $firstError) { $firstError = $_ } }
    if ($null -ne $firstError) { throw $firstError }
}

function Add-AllevaPatientExportRows {
    param(
        [Parameter(Mandatory=$true)]$Patient,
        [Parameter(Mandatory=$true)][hashtable]$RosterSpool,
        [Parameter(Mandatory=$true)][hashtable]$FieldSpool,
        [Parameter(Mandatory=$true)][hashtable]$PatientIndex,
        [Parameter(Mandatory=$true)][AllowEmptyCollection()][System.Collections.Generic.HashSet[string]]$WideColumns
    )

    $patientId = Get-AllevaPatientIdExact $Patient
    $names = Get-AllevaPatientNames $Patient
    $indexNames = [pscustomobject]@{
        PatientId = $patientId
        ClientFullName = $names.ClientFullName
        LegalFirstName = $names.LegalFirstName
        LegalMiddleName = $names.LegalMiddleName
        LegalLastName = $names.LegalLastName
        PreferredName = $names.PreferredName
    }
    $wideRow = [ordered]@{
        PatientId = $patientId
        ClientFullName = $names.ClientFullName
        LegalFirstName = $names.LegalFirstName
        LegalMiddleName = $names.LegalMiddleName
        LegalLastName = $names.LegalLastName
        PreferredName = $names.PreferredName
        Status = Get-StatusText $Patient
        DateOfBirth = Get-AllevaExactCandidate -Record $Patient -Paths @('dateOfBirth','dob','birthDate')
    }
    $flat = ConvertTo-FlattenedHashtable $Patient
    foreach ($path in $flat.Keys) {
        $column = "patient.$path"
        Add-AllevaWideValue -Row $wideRow -Columns $WideColumns -Column $column -Value $flat[$path]
    }
    Write-AllevaEncryptedRowSpool -Spool $RosterSpool -Row ([pscustomobject]$wideRow)
    foreach ($path in $flat.Keys) {
        Write-AllevaEncryptedRowSpool -Spool $FieldSpool -Row ([pscustomobject]@{ PatientId=$patientId; FieldPath=[string]$path; Value=[string]$flat[$path]; ChunkIndex=1; ChunkCount=1 })
    }
    if (-not [string]::IsNullOrWhiteSpace($patientId)) {
        Add-AllevaPatientIndexEntry -Index $PatientIndex -PatientId $patientId -Names $indexNames
        foreach ($aliasPath in @('clientId','patientId')) {
            $alias = Get-AllevaExactCandidate -Record $Patient -Paths @($aliasPath)
            if (-not [string]::IsNullOrWhiteSpace($alias) -and -not [StringComparer]::Ordinal.Equals($alias, $patientId)) {
                Add-AllevaPatientIndexEntry -Index $PatientIndex -PatientId ("${aliasPath}:$alias") -Names $indexNames
            }
        }
    }
    return $patientId
}

function Get-AllevaPatientNameMapping {
    param(
        [Parameter(Mandatory=$true)][hashtable]$PatientIndex,
        [AllowEmptyString()][string]$PatientId
    )

    $names = Get-AllevaPatientIndexEntry -Index $PatientIndex -PatientId $PatientId
    if ($null -eq $names -and -not [string]::IsNullOrWhiteSpace($PatientId)) { $names = Get-AllevaPatientIndexEntry -Index $PatientIndex -PatientId ("clientId:$PatientId") }
    if ($null -eq $names -and -not [string]::IsNullOrWhiteSpace($PatientId)) { $names = Get-AllevaPatientIndexEntry -Index $PatientIndex -PatientId ("patientId:$PatientId") }
    $resolvedPatientId = if ($null -eq $names) { '' } elseif ($names.PSObject.Properties['PatientId']) { [string]$names.PatientId } else { $PatientId }
    return [pscustomobject]@{
        PatientId = $resolvedPatientId
        PatientMappingStatus = if ($null -eq $names) { 'UNMAPPED' } else { 'MAPPED' }
        ClientFullName = if ($null -eq $names) { '' } else { [string]$names.ClientFullName }
        LegalFirstName = if ($null -eq $names) { '' } else { [string]$names.LegalFirstName }
        LegalMiddleName = if ($null -eq $names) { '' } else { [string]$names.LegalMiddleName }
        LegalLastName = if ($null -eq $names) { '' } else { [string]$names.LegalLastName }
        PreferredName = if ($null -eq $names) { '' } else { [string]$names.PreferredName }
    }
}

function Add-AllevaTreatmentPlanFieldRows {
    param(
        [Parameter(Mandatory=$true)]$Record,
        [AllowEmptyString()][string]$PlanId,
        [AllowEmptyString()][string]$PatientId,
        [Parameter(Mandatory=$true)]$PatientNameMapping,
        [Parameter(Mandatory=$true)][ValidateSet('list','detail')][string]$SourceScope,
        [Parameter(Mandatory=$true)][hashtable]$FieldSpool
    )

    $flat = ConvertTo-FlattenedHashtable $Record
    foreach ($path in $flat.Keys) {
        Write-AllevaEncryptedRowSpool -Spool $FieldSpool -Row ([pscustomobject]@{
            TreatmentPlanId=$PlanId; PatientId=$PatientId;
            PatientMappingStatus=$PatientNameMapping.PatientMappingStatus;
            ClientFullName=$PatientNameMapping.ClientFullName; LegalFirstName=$PatientNameMapping.LegalFirstName;
            LegalMiddleName=$PatientNameMapping.LegalMiddleName; LegalLastName=$PatientNameMapping.LegalLastName;
            PreferredName=$PatientNameMapping.PreferredName; SourceScope=$SourceScope;
            FieldPath=[string]$path; Value=[string]$flat[$path]; ChunkIndex=1; ChunkCount=1
        })
    }
    return $flat.Keys.Count
}

function Add-AllevaWideValue {
    param(
        [Parameter(Mandatory=$true)][System.Collections.IDictionary]$Row,
        [Parameter(Mandatory=$true)][AllowEmptyCollection()][System.Collections.Generic.HashSet[string]]$Columns,
        [Parameter(Mandatory=$true)][string]$Column,
        [AllowNull()]$Value
    )

    $text = ConvertTo-AllevaXmlSafeText (ConvertTo-AllevaCellText $Value)
    if ($text.Length -le 32000) {
        $Row[$Column] = $text
        [void]$Columns.Add($Column)
        return
    }
    $start = 0
    $chunkIndex = 1
    while ($start -lt $text.Length) {
        $length = [Math]::Min(32000, $text.Length - $start)
        if (($start + $length) -lt $text.Length -and [char]::IsHighSurrogate($text[$start + $length - 1])) { $length-- }
        $chunkColumn = if ($chunkIndex -eq 1) { $Column } else { "$Column [chunk $chunkIndex]" }
        $Row[$chunkColumn] = $text.Substring($start, $length)
        [void]$Columns.Add($chunkColumn)
        $start += $length
        $chunkIndex++
    }
}

function Add-AllevaTreatmentPlanExportRow {
    param(
        [Parameter(Mandatory=$true)]$ListRecord,
        [AllowNull()]$DetailRecord,
        [AllowEmptyString()][string]$PlanId,
        [AllowEmptyString()][string]$ListPatientReferenceId,
        [AllowEmptyString()][string]$DetailPatientReferenceId,
        [Parameter(Mandatory=$true)]$PatientMapping,
        [Parameter(Mandatory=$true)][string]$Status,
        [Parameter(Mandatory=$true)][hashtable]$Spool,
        [Parameter(Mandatory=$true)][AllowEmptyCollection()][System.Collections.Generic.HashSet[string]]$WideColumns
    )

    $resolvedPatientId = if ($PatientMapping.PatientMappingStatus -eq 'MAPPED') { $PatientMapping.PatientId } elseif ($PatientMapping.PatientMappingStatus -eq 'UNMAPPED') { if (-not [string]::IsNullOrWhiteSpace($ListPatientReferenceId)) { $ListPatientReferenceId } else { $DetailPatientReferenceId } } else { '' }
    $row = [ordered]@{
        TreatmentPlanId=$PlanId; PatientId=$resolvedPatientId;
        PatientReferenceId=$ListPatientReferenceId; DetailPatientReferenceId=$DetailPatientReferenceId;
        PatientMappingStatus=$PatientMapping.PatientMappingStatus;
        ClientFullName=$PatientMapping.ClientFullName; LegalFirstName=$PatientMapping.LegalFirstName;
        LegalMiddleName=$PatientMapping.LegalMiddleName; LegalLastName=$PatientMapping.LegalLastName;
        PreferredName=$PatientMapping.PreferredName; Status=$Status;
        PlanDate=Get-AllevaExactCandidate -Record $ListRecord -Paths @('planDate','treatmentPlanDate','startDate','date','createdAt','createdDate')
    }
    $listFlat = ConvertTo-FlattenedHashtable $ListRecord
    foreach ($path in $listFlat.Keys) {
        $column = "list.$path"
        Add-AllevaWideValue -Row $row -Columns $WideColumns -Column $column -Value $listFlat[$path]
    }
    if ($null -ne $DetailRecord) {
        $detailFlat = ConvertTo-FlattenedHashtable $DetailRecord
        foreach ($path in $detailFlat.Keys) {
            $column = "detail.$path"
            Add-AllevaWideValue -Row $row -Columns $WideColumns -Column $column -Value $detailFlat[$path]
        }
    }
    Write-AllevaEncryptedRowSpool -Spool $Spool -Row ([pscustomobject]$row)
}

function Get-AllevaRetryAfterSeconds {
    param([AllowNull()]$Value)
    if ($null -eq $Value) { return $null }
    $text = ([string]$Value).Trim()
    if ($text -match '^\d+$') {
        if ($text.Length -gt 2) { return 60 }
        $seconds = [int]0
        if ([int]::TryParse($text, [ref]$seconds)) { return [Math]::Min(60, $seconds) }
    }
    $date = [datetimeoffset]::MinValue
    if ([datetimeoffset]::TryParse($text, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeUniversal, [ref]$date)) {
        $delta = ($date.ToUniversalTime() - [datetimeoffset]::UtcNow).TotalSeconds
        if ($delta -le 0) { return 0 }
        if ($delta -ge 60) { return 60 }
        return [int][Math]::Ceiling($delta)
    }
    return $null
}

function Get-AllevaDetailFailureInfo {
    param([Parameter(Mandatory=$true)]$ErrorRecord)

    $exception = $ErrorRecord.Exception
    $statusCode = 0
    $retryAfter = $null
    $errorCategory = if ($null -ne $exception) { $exception.GetType().Name } else { 'RequestFailure' }
    try { if ($exception.Data.Contains('StatusCode')) { $statusCode = [int]$exception.Data['StatusCode'] } } catch { }
    try { if ($exception.Data.Contains('RetryAfter')) { $retryAfter = Get-AllevaRetryAfterSeconds $exception.Data['RetryAfter'] } } catch { }
    try { if ($exception.Data.Contains('ErrorCategory')) { $errorCategory = [string]$exception.Data['ErrorCategory'] } } catch { }
    $isTimeout = ($exception -is [System.TimeoutException]) -or ($exception.InnerException -is [System.TimeoutException]) -or $errorCategory -match '(?i)timeout' -or $exception.Message -match '(?i)timed?\s*out|timeout'
    try {
        if ($exception -is [System.Net.WebException] -and $exception.Status -eq [System.Net.WebExceptionStatus]::Timeout) { $isTimeout = $true }
    } catch { }
    $retryable = $isTimeout -or $statusCode -eq 429 -or ($statusCode -ge 500 -and $statusCode -le 599)
    return [pscustomobject]@{
        StatusCode = $statusCode
        RetryAfterSeconds = $retryAfter
        ErrorCategory = if ($isTimeout) { 'Timeout' } else { $errorCategory }
        Retryable = $retryable
    }
}

function Invoke-TreatmentPlanDetailWithRetry {
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)][string]$PlanId)

    $totalDelay = 0
    $retryCount = 0
    $lastFailure = $null
    for ($attempt = 1; $attempt -le 4; $attempt++) {
        try {
            $escapedPlanId = [Uri]::EscapeDataString($PlanId)
            $detailPath = "/treatment-plans/$escapedPlanId"
            $detailQuery = @{ 'api-version' = ([string]$script:Settings['ApiVersion']).Trim() }
            $stopwatch = [Diagnostics.Stopwatch]::StartNew()
            if ($null -ne $script:DetailProvider) {
                $detail = & $script:DetailProvider $detailPath $detailQuery 'treatment-plan-detail' $PlanId $attempt
            } else {
                $detail = Invoke-AllevaGet -Path $detailPath -Query $detailQuery -Label 'treatment-plan-detail'
            }
            $stopwatch.Stop()
            if ($null -eq $detail -or -not (Test-IsRecordObject $detail)) {
                return [pscustomobject]@{ Success=$false; Detail=$null; AttemptCount=$attempt; RetryCount=$retryCount; DelaySeconds=$totalDelay; StatusCode=0; ErrorCategory='SchemaFailure' }
            }
            Write-AppLog -Level INFO -Event 'detail.completed' -Data @{ endpoint_label='treatment-plan-detail'; status='success'; duration_ms=$stopwatch.ElapsedMilliseconds; attempt_count=$attempt; retry_count=$retryCount }
            return [pscustomobject]@{ Success=$true; Detail=$detail; AttemptCount=$attempt; RetryCount=$retryCount; DelaySeconds=$totalDelay; StatusCode=200; ErrorCategory='' }
        } catch {
            $lastFailure = Get-AllevaDetailFailureInfo $_
            Write-AppLog -Level WARN -Event 'detail.failed' -Data @{ endpoint_label='treatment-plan-detail'; status='failure'; attempt_count=$attempt; retry_count=$retryCount; error_class=$lastFailure.ErrorCategory }
            if (-not $lastFailure.Retryable -or $attempt -ge 4) { break }
            $requestedDelay = if ($null -ne $lastFailure.RetryAfterSeconds) { [int]$lastFailure.RetryAfterSeconds } else { [int][Math]::Pow(2, $attempt - 1) }
            $delay = [Math]::Min(60, [Math]::Max(0, $requestedDelay))
            $delay = [Math]::Min($delay, [Math]::Max(0, 180 - $totalDelay))
            if ($null -ne $script:RetryDelayProvider) {
                & $script:RetryDelayProvider $delay $lastFailure.ErrorCategory $attempt
            } elseif ($delay -gt 0) {
                Start-Sleep -Seconds $delay
            }
            $totalDelay += $delay
            $retryCount++
        }
    }
    if ($null -eq $lastFailure) { $lastFailure = [pscustomobject]@{ StatusCode=0; ErrorCategory='RequestFailure' } }
    return [pscustomobject]@{
        Success=$false; Detail=$null; AttemptCount=([Math]::Min(4, $retryCount + 1)); RetryCount=$retryCount;
        DelaySeconds=$totalDelay; StatusCode=$lastFailure.StatusCode; ErrorCategory=$lastFailure.ErrorCategory
    }
}

function Invoke-CompleteAllevaExport {
    [CmdletBinding()]
    param()

    Import-Settings
    Ensure-Directory -Path $ExportDirectory
    $patientRosterSpool = $null
    $patientFieldSpool = $null
    $treatmentPlanSpool = $null
    $treatmentPlanFieldSpool = $null
    $patientIndex = $null
    try {
    $patientRosterSpool = New-AllevaEncryptedRowSpool -Directory $ExportDirectory
    $patientFieldSpool = New-AllevaEncryptedRowSpool -Directory $ExportDirectory
    $treatmentPlanSpool = New-AllevaEncryptedRowSpool -Directory $ExportDirectory
    $treatmentPlanFieldSpool = New-AllevaEncryptedRowSpool -Directory $ExportDirectory
    $patientIndex = New-AllevaEncryptedPatientIndex -Directory ([IO.Path]::GetTempPath())
    $exportState = @{
        PatientMissingIdCount = 0
        MissingPlanIdCount = 0
        MappingMissCount = 0
        IdentityConflictCount = 0
        DetailSuccessCount = 0
        DetailFailureCount = 0
        DetailRetryCount = 0
        ListLeafCount = [long]0
        DetailLeafCount = [long]0
    }
    $patientWideColumns = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $treatmentPlanWideColumns = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)

    $patientConsumer = {
        param($patient)
        $patientId = Add-AllevaPatientExportRows -Patient $patient -RosterSpool $patientRosterSpool -FieldSpool $patientFieldSpool -PatientIndex $patientIndex -WideColumns $patientWideColumns
        if ([string]::IsNullOrWhiteSpace($patientId)) { $exportState.PatientMissingIdCount++ }
    }
    $pageCap = Get-AllevaConfiguredPageCap
    $patientCollection = Invoke-CompleteCollection -Path $script:ClientsPath -Query (Get-CompleteExportQuery) -Label 'clients' -SafetyPageCap $pageCap -OnRecord $patientConsumer

    $planConsumer = {
        param($plan)
        $planId = Get-AllevaPlanIdExact $plan
        $listPatientReferenceId = Get-AllevaPlanPatientIdExact $plan
        $listNameMapping = Get-AllevaPatientNameMapping -PatientIndex $patientIndex -PatientId $listPatientReferenceId
        $listAssociationId = if ($listNameMapping.PatientMappingStatus -eq 'MAPPED') { $listNameMapping.PatientId } else { $listPatientReferenceId }
        $exportState.ListLeafCount += Add-AllevaTreatmentPlanFieldRows -Record $plan -PlanId $planId -PatientId $listAssociationId -PatientNameMapping $listNameMapping -SourceScope 'list' -FieldSpool $treatmentPlanFieldSpool
        if ([string]::IsNullOrWhiteSpace($planId)) {
            $exportState.MissingPlanIdCount++
            if ($listNameMapping.PatientMappingStatus -ne 'MAPPED') { $exportState.MappingMissCount++ }
            Add-AllevaTreatmentPlanExportRow -ListRecord $plan -DetailRecord $null -PlanId '' -ListPatientReferenceId $listPatientReferenceId -DetailPatientReferenceId '' -PatientMapping $listNameMapping -Status 'MISSING_ID' -Spool $treatmentPlanSpool -WideColumns $treatmentPlanWideColumns
            return
        }

        $detailResult = Invoke-TreatmentPlanDetailWithRetry -PlanId $planId
        $exportState.DetailRetryCount += $detailResult.RetryCount
        $summaryNameMapping = $listNameMapping
        $detailPatientReferenceId = ''
        $detailRecord = $null
        $planStatus = 'DETAIL_FAILED'
        if ($detailResult.Success) {
            $exportState.DetailSuccessCount++
            $detailRecord = $detailResult.Detail
            $detailPatientReferenceId = Get-AllevaPlanPatientIdExact $detailRecord
            $detailNameMapping = if ([string]::IsNullOrWhiteSpace($detailPatientReferenceId)) { $listNameMapping } else { Get-AllevaPatientNameMapping -PatientIndex $patientIndex -PatientId $detailPatientReferenceId }
            $detailPlanId = Get-AllevaPlanIdExact $detailRecord
            $listComparableId = if ($listNameMapping.PatientMappingStatus -eq 'MAPPED') { $listNameMapping.PatientId } else { $listPatientReferenceId }
            $detailComparableId = if ($detailNameMapping.PatientMappingStatus -eq 'MAPPED') { $detailNameMapping.PatientId } else { $detailPatientReferenceId }
            $patientConflict = (-not [string]::IsNullOrWhiteSpace($listComparableId) -and -not [string]::IsNullOrWhiteSpace($detailComparableId) -and -not [StringComparer]::Ordinal.Equals($listComparableId, $detailComparableId))
            $planConflict = (-not [string]::IsNullOrWhiteSpace($detailPlanId) -and -not [StringComparer]::Ordinal.Equals($detailPlanId, $planId))
            if ($patientConflict -or $planConflict) {
                $exportState.IdentityConflictCount++
                $summaryNameMapping = [pscustomobject]@{ PatientId=''; PatientMappingStatus='IDENTITY_CONFLICT'; ClientFullName=''; LegalFirstName=''; LegalMiddleName=''; LegalLastName=''; PreferredName='' }
                $detailNameMapping = $summaryNameMapping
                $detailAssociationId = ''
                $planStatus = 'IDENTITY_CONFLICT'
            } else {
                if ($summaryNameMapping.PatientMappingStatus -ne 'MAPPED' -and $detailNameMapping.PatientMappingStatus -eq 'MAPPED') { $summaryNameMapping = $detailNameMapping }
                $detailAssociationId = if ($detailNameMapping.PatientMappingStatus -eq 'MAPPED') { $detailNameMapping.PatientId } else { $detailPatientReferenceId }
                $planStatus = 'DETAIL_COMPLETE'
            }
            $exportState.DetailLeafCount += Add-AllevaTreatmentPlanFieldRows -Record $detailRecord -PlanId $planId -PatientId $detailAssociationId -PatientNameMapping $detailNameMapping -SourceScope 'detail' -FieldSpool $treatmentPlanFieldSpool
        } else {
            $exportState.DetailFailureCount++
        }
        if ($summaryNameMapping.PatientMappingStatus -ne 'MAPPED') { $exportState.MappingMissCount++ }
        Add-AllevaTreatmentPlanExportRow -ListRecord $plan -DetailRecord $detailRecord -PlanId $planId -ListPatientReferenceId $listPatientReferenceId -DetailPatientReferenceId $detailPatientReferenceId -PatientMapping $summaryNameMapping -Status $planStatus -Spool $treatmentPlanSpool -WideColumns $treatmentPlanWideColumns
    }
    $planCollection = Invoke-CompleteCollection -Path $script:TreatmentPlansPath -Query (Get-CompleteExportQuery -ForTreatmentPlans) -Label 'treatment-plans' -SafetyPageCap $pageCap -OnRecord $planConsumer
    Close-AllevaEncryptedRowSpool $patientRosterSpool
    Close-AllevaEncryptedRowSpool $patientFieldSpool
    Close-AllevaEncryptedRowSpool $treatmentPlanSpool
    Close-AllevaEncryptedRowSpool $treatmentPlanFieldSpool

    $complete = $patientCollection.Complete -and $planCollection.Complete -and $exportState.PatientMissingIdCount -eq 0 -and $exportState.MissingPlanIdCount -eq 0 -and $exportState.MappingMissCount -eq 0 -and $exportState.IdentityConflictCount -eq 0 -and $exportState.DetailFailureCount -eq 0
    $status = if ($complete) { 'COMPLETE' } else { 'INCOMPLETE' }
    $patientFieldEmitted = $patientFieldSpool.EmittedRowCount
    $planFieldEmitted = $treatmentPlanFieldSpool.EmittedRowCount
    $longFormRowCount = $patientFieldEmitted + $planFieldEmitted
    $includeFieldAuditSheets = $longFormRowCount -le $script:LongFormAuditRowLimit
    $summaryRows = New-Object System.Collections.Generic.List[object]
    $summaryValues = [ordered]@{
        ExportStatus=$status
        PatientPaginationStatus=$patientCollection.Status
        PatientPaginationTermination=$patientCollection.TerminationReason
        PatientPages=$patientCollection.PageCount
        PatientRawRecords=$patientCollection.RawRecordCount
        PatientUniqueRecords=$patientCollection.UniqueRecordCount
        PatientMissingIds=$exportState.PatientMissingIdCount
        PatientFieldLeaves=$patientFieldSpool.LogicalRowCount
        TreatmentPlanPaginationStatus=$planCollection.Status
        TreatmentPlanPaginationTermination=$planCollection.TerminationReason
        TreatmentPlanPages=$planCollection.PageCount
        TreatmentPlanRawRecords=$planCollection.RawRecordCount
        TreatmentPlanUniqueRecords=$planCollection.UniqueRecordCount
        TreatmentPlanMissingIds=$exportState.MissingPlanIdCount
        TreatmentPlanListFieldLeaves=$exportState.ListLeafCount
        TreatmentPlanDetailFieldLeaves=$exportState.DetailLeafCount
        DetailSuccesses=$exportState.DetailSuccessCount
        DetailFailures=$exportState.DetailFailureCount
        DetailRetries=$exportState.DetailRetryCount
        PatientMappingMisses=$exportState.MappingMissCount
        IdentityConflicts=$exportState.IdentityConflictCount
        PatientRosterColumns=(8 + $patientWideColumns.Count)
        TreatmentPlanColumns=(12 + $treatmentPlanWideColumns.Count)
        LongFormAuditSheetsIncluded=$includeFieldAuditSheets
        LongFormAuditRowsOmitted=$(if ($includeFieldAuditSheets) { 0 } else { $longFormRowCount })
    }
    foreach ($metric in $summaryValues.Keys) { $summaryRows.Add([pscustomobject]@{ Metric=$metric; Value=$summaryValues[$metric] }) }

    $rowsPerSheet = [Math]::Max(1, $script:WorksheetRowLimit - 1)
    $incompleteStatusRowCount = if ($complete) { 0 } else { 1 }
    $finalSummaryRowCount = $summaryRows.Count + 2 + $incompleteStatusRowCount
    $expectedWorksheetCount = 0
    $workbookLogicalRowCounts = New-Object System.Collections.Generic.List[long]
    $workbookLogicalRowCounts.Add($finalSummaryRowCount)
    $workbookLogicalRowCounts.Add($patientRosterSpool.LogicalRowCount)
    if ($includeFieldAuditSheets) { $workbookLogicalRowCounts.Add($patientFieldEmitted) }
    $workbookLogicalRowCounts.Add($treatmentPlanSpool.LogicalRowCount)
    if ($includeFieldAuditSheets) { $workbookLogicalRowCounts.Add($planFieldEmitted) }
    foreach ($logicalRowCount in $workbookLogicalRowCounts) {
        $expectedWorksheetCount += [Math]::Max(1, [int][Math]::Ceiling(([double]$logicalRowCount / $rowsPerSheet)))
    }
    $summaryRows.Add([pscustomobject]@{ Metric='WorkbookWorksheetCountExpected'; Value=$expectedWorksheetCount })
    $expectedDataRows = $finalSummaryRowCount + $patientRosterSpool.LogicalRowCount + $treatmentPlanSpool.LogicalRowCount
    if ($includeFieldAuditSheets) { $expectedDataRows += $patientFieldEmitted + $planFieldEmitted }
    $summaryRows.Add([pscustomobject]@{ Metric='WorkbookDataRowsExpected'; Value=$expectedDataRows })

    $filename = New-AllevaExportFileName -Kind 'complete-export' -Extension '.xlsx' -Status $status
    $workbookPath = Join-Path $ExportDirectory $filename
    $patientRosterSource = Get-AllevaEncryptedRowSource $patientRosterSpool
    $patientFieldSource = Get-AllevaEncryptedRowSource $patientFieldSpool
    $treatmentPlanSource = Get-AllevaEncryptedRowSource $treatmentPlanSpool
    $treatmentPlanFieldSource = Get-AllevaEncryptedRowSource $treatmentPlanFieldSpool
    $patientRosterColumns = @('PatientId','ClientFullName','LegalFirstName','LegalMiddleName','LegalLastName','PreferredName','Status','DateOfBirth') + @($patientWideColumns | Sort-Object)
    $treatmentPlanColumns = @('TreatmentPlanId','PatientId','PatientReferenceId','DetailPatientReferenceId','PatientMappingStatus','ClientFullName','LegalFirstName','LegalMiddleName','LegalLastName','PreferredName','Status','PlanDate') + @($treatmentPlanWideColumns | Sort-Object)
    Write-Ui "Finished API retrieval: $($patientCollection.UniqueRecordCount) patients and $($planCollection.UniqueRecordCount) treatment plans. Building the Excel workbook now." Cyan 'export.workbook_started'
    if (-not $includeFieldAuditSheets) {
        Write-Ui "Large export detected: omitting $longFormRowCount duplicate long-form audit rows. Every retrieved field remains in the Patient Roster and Treatment Plans columns." Yellow 'export.long_form_omitted' WARN
    }
    $workbook = New-AllevaWorkbook -Path $workbookPath -SummaryRows $summaryRows.ToArray() -PatientRosterRows $patientRosterSource -PatientFieldRows $patientFieldSource -TreatmentPlanRows $treatmentPlanSource -TreatmentPlanFieldRows $treatmentPlanFieldSource -PatientRosterColumns $patientRosterColumns -TreatmentPlanColumns $treatmentPlanColumns -RetrievalComplete $complete -IncludeFieldAuditSheets $includeFieldAuditSheets -WorksheetRowLimit $script:WorksheetRowLimit
    Write-Ui "Workbook built, validated, and published: $workbookPath" Green 'export.workbook_completed'

    Write-AppLog -Level INFO -Event 'export.completed' -Data @{
        action='export'; endpoint_label='export'; status=$status; page_count=($patientCollection.PageCount + $planCollection.PageCount);
        raw_count=($patientCollection.RawRecordCount + $planCollection.RawRecordCount); unique_count=($patientCollection.UniqueRecordCount + $planCollection.UniqueRecordCount);
        retry_count=$exportState.DetailRetryCount; detail_success_count=$exportState.DetailSuccessCount; detail_failure_count=$exportState.DetailFailureCount;
        mapping_miss_count=$exportState.MappingMissCount; worksheet_count=$workbook.WorksheetCount; row_count=$workbook.TotalDataRowCount; complete=$complete
    }

    return [pscustomobject]@{
        Status=$status; Complete=$complete; WorkbookPath=$workbook.Path; Workbook=$workbook;
        PatientCount=$patientCollection.UniqueRecordCount; PatientCollectionComplete=$patientCollection.Complete; PatientCollectionPageCount=$patientCollection.PageCount;
        PatientFieldLeafCount=$patientFieldSpool.LogicalRowCount; PatientMissingIdCount=$exportState.PatientMissingIdCount;
        TreatmentPlanCount=$planCollection.UniqueRecordCount; TreatmentPlanCollectionComplete=$planCollection.Complete; TreatmentPlanCollectionPageCount=$planCollection.PageCount;
        TreatmentPlanListFieldLeafCount=$exportState.ListLeafCount; TreatmentPlanDetailFieldLeafCount=$exportState.DetailLeafCount;
        DetailSuccessCount=$exportState.DetailSuccessCount; DetailFailureCount=$exportState.DetailFailureCount; DetailRetryCount=$exportState.DetailRetryCount;
        MissingPlanIdCount=$exportState.MissingPlanIdCount; MappingMissCount=$exportState.MappingMissCount;
        IdentityConflictCount=$exportState.IdentityConflictCount;
        LongFormAuditSheetsIncluded=$includeFieldAuditSheets; LongFormAuditRowsOmitted=$(if ($includeFieldAuditSheets) { 0 } else { $longFormRowCount });
        WorkbookWorksheetCountExpected=$expectedWorksheetCount; WorkbookDataRowCountExpected=$expectedDataRows
    }
    } finally {
        Invoke-AllevaExportArtifactCleanup -Spools @($patientRosterSpool,$patientFieldSpool,$treatmentPlanSpool,$treatmentPlanFieldSpool) -PatientIndex $patientIndex
    }
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

    $csvPath = Join-Path $ExportDirectory (New-AllevaExportFileName -Kind 'focused-csv' -Extension '.csv')
    $jsonPath = Join-Path $ExportDirectory (New-AllevaExportFileName -Kind 'focused-json' -Extension '.json')

    $allKeys = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    $safeHeaders = @{}
    $usedHeaders = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $flattenedRows = New-Object System.Collections.Generic.List[object]

    foreach ($record in $recordArray) {
        $flat = ConvertTo-FlattenedHashtable $record
        foreach ($key in $flat.Keys) {
            if (-not $seen.ContainsKey($key)) {
                $seen[$key] = $true
                $allKeys.Add($key)
                $header = [string]$key
                if ($header -match '^[=+\-@]') { $header = "'$header" }
                $headerBase = $header
                $suffix = 2
                while (-not $usedHeaders.Add($header)) {
                    $header = '{0} ({1})' -f $headerBase, $suffix
                    $suffix++
                }
                $safeHeaders[$key] = $header
            }
        }
        $flattenedRows.Add($flat)
    }

    $objects = New-Object System.Collections.Generic.List[object]
    foreach ($flat in $flattenedRows) {
        $ordered = [ordered]@{}
        foreach ($key in $allKeys) {
            $header = [string]$safeHeaders[$key]
            if ($flat.Contains($key)) {
                $value = ConvertTo-AllevaExactText $flat[$key]
                if ($value -match '^[=+\-@]') { $value = "'$value" }
                $ordered[$header] = $value
            } else { $ordered[$header] = '' }
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
    Write-AppLog -Level INFO -Event 'export.completed' -Message 'CSV export completed.' -Data @{ action='focused_csv'; row_count=(Get-SafeCount $recordArray); column_count=$allKeys.Count }
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
    if ($script:NoPause) { return }
    [void](Read-Host 'Press Enter to continue')
}

function Get-ActivePatients {
    Write-Section 'Pull most recent active patient roster'
    $query = Get-CompleteExportQuery
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
    foreach ($patient in @(ConvertTo-ObjectArraySafe $Patients)) {
        foreach ($aliasPath in @('clientId','patientId')) {
            $alias = Get-AllevaExactCandidate -Record $patient -Paths @($aliasPath)
            if (-not [string]::IsNullOrWhiteSpace($alias) -and -not $map.ContainsKey($alias)) { $map[$alias] = $patient }
        }
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
    $query = Get-CompleteExportQuery -ForTreatmentPlans
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
    param([Parameter(Mandatory=$true)][string]$PatientId, [string[]]$PatientAliases = @())
    $query = Get-CompleteExportQuery -ForTreatmentPlans
    $query['ClientId'] = $PatientId
    $allPlans = @(Invoke-AllevaCollection -Path $script:TreatmentPlansPath -Query $query -Label 'patient-treatment-plans')
    $acceptedIds = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    [void]$acceptedIds.Add($PatientId)
    foreach ($alias in $PatientAliases) { if (-not [string]::IsNullOrWhiteSpace($alias)) { [void]$acceptedIds.Add($alias) } }
    $plans = @($allPlans | Where-Object { $acceptedIds.Contains((Get-AllevaPlanPatientIdExact $_)) })
    Write-AppLog -Level INFO -Event 'plans.patient_index_pulled' -Data @{ endpoint_label='treatment-plans'; status='success'; record_count=(Get-SafeCount $plans) }
    return $plans
}

function Invoke-FullTreatmentPlanPull {
    param($Plan)
    $planId = Get-PlanId $Plan
    if ([string]::IsNullOrWhiteSpace($planId)) { throw 'Selected treatment plan does not have a recognizable ID.' }

    try {
        $detailPath = "/treatment-plans/$([Uri]::EscapeDataString($planId))"
        $detailQuery = @{ 'api-version' = ([string]$script:Settings['ApiVersion']).Trim() }
        if ($null -ne $script:DetailProvider) {
            $detail = & $script:DetailProvider $detailPath $detailQuery "treatment-plan-$planId-detail" $planId
        } else {
            $detail = Invoke-AllevaGet -Path $detailPath -Query $detailQuery -Label "treatment-plan-$planId-detail"
        }
        Write-AppLog -Level INFO -Event 'plans.detail_pulled' -Data @{ endpoint_label='treatment-plan-detail'; status='success'; record_count=1 }
        return $detail
    } catch {
        Write-Ui "Detail endpoint failed for treatment plan $planId. Falling back to the list record. Error: $($_.Exception.Message)" DarkYellow 'plans.detail_fallback' WARN
        Write-AppLog -Level WARN -Event 'plans.detail_fallback' -Data @{ endpoint_label='treatment-plan-detail'; status='failure'; error_class=$_.Exception.GetType().Name }
        return $Plan
    }
}

function Pull-PatientTreatmentPlansWorkflow {
    $patient = Select-Patient
    if ($null -eq $patient) { return }

    $patientId = Get-PatientId $patient
    $patientName = Get-PatientName $patient
    Write-Section "Treatment plans for $patientName ($patientId)"

    $patientAliases = @(
        Get-AllevaExactCandidate -Record $patient -Paths @('clientId')
        Get-AllevaExactCandidate -Record $patient -Paths @('patientId')
    )
    $plans = @(Get-TreatmentPlansForPatient -PatientId $patientId -PatientAliases $patientAliases)
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
    Write-AppLog -Level INFO -Event 'user.plan_select' -Data @{ action='select-plan'; status='received' }
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
    Write-Host '  1. Export complete patient roster and treatment plans to Excel'
    Write-Host '  2. Pull active patient roster'
    Write-Host '  3. Pull treatment plans mapped to patients'
    Write-Host '  4. Select patient and pull full treatment plan details'
    Write-Host '  5. Select patient and view/export patient record'
    Write-Host '  6. Configure Alleva API settings / credentials'
    Write-Host '  7. Show current settings'
    Write-Host '  8. Run preflight check'
    Write-Host '  9. Show/open log and export folders'
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
                '1' {
                    $result = Invoke-CompleteAllevaExport
                    if ($result.Complete) { Write-Ui "Complete Excel export: $($result.WorkbookPath)" Green 'export.complete' }
                    else { Write-Ui "Incomplete Excel export preserved for review: $($result.WorkbookPath)" DarkYellow 'export.incomplete' WARN }
                    Pause-ForUser
                }
                '2' { Show-ActivePatientRosterWorkflow; Pause-ForUser }
                '3' { Pull-TreatmentPlansMappedWorkflow; Pause-ForUser }
                '4' { Pull-PatientTreatmentPlansWorkflow; Pause-ForUser }
                '5' { PatientRecordWorkflow; Pause-ForUser }
                '6' { Edit-SettingsMenu; Pause-ForUser }
                '7' { Show-Settings; Pause-ForUser }
                '8' { [void](Test-Prerequisites); Pause-ForUser }
                '9' { Open-OutputFoldersWorkflow; Pause-ForUser }
                '0' { Write-Ui 'Exiting.' Green 'app.exit_requested'; return }
                default { Write-Ui 'Invalid option. Choose 0 through 9.' DarkYellow 'menu.invalid' WARN; Pause-ForUser }
            }
        } catch {
            Write-Ui "Error: $($_.Exception.Message)" Red 'workflow.error' ERROR
            Write-AppLog -Level ERROR -Event 'workflow.exception' -Data @{ status='failure'; error_class=$_.Exception.GetType().Name }
            Pause-ForUser
        }
    }
}

function Invoke-SyntheticSelfTest {
    Invoke-InjectedFailureHook -Stage 'SelfTest.BeforeValidation'

    if ($null -ne (ConvertFrom-JsonSafe '{malformed-synthetic-json')) {
        throw 'Malformed synthetic JSON was unexpectedly accepted.'
    }

    $fixture = [pscustomobject]@{
        items = @(
            [pscustomobject]@{ id = 'synthetic-1' },
            [pscustomobject]@{ id = 'synthetic-2' }
        )
    }
    if ((Get-SafeCount (Get-RecordsFromPayload $fixture)) -ne 2) {
        throw 'Synthetic collection normalization failed.'
    }

    Ensure-Directory -Path $ExportDirectory
    Invoke-InjectedFailureHook -Stage 'SelfTest.BeforeWrite'
    $previousPageProvider = $script:PageProvider
    $previousDetailProvider = $script:DetailProvider
    $previousDelayProvider = $script:RetryDelayProvider
    try {
        $script:PageProvider = { @([pscustomobject]@{ id='synthetic-unpaged-1' },[pscustomobject]@{ id='synthetic-unpaged-2' }) }
        $unpagedResult = Invoke-CompleteCollection -Path '/clients' -Query @{ Limit=5000; Cursor=0 } -Label 'synthetic-unpaged' -SafetyPageCap 3 -CollectRecords
        if (-not $unpagedResult.Complete -or $unpagedResult.TerminationReason -ne 'unpaged_short_page') { throw 'Synthetic unpaged collection did not terminate as complete.' }

        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            if ($Path -eq '/clients') {
                return [pscustomobject]@{ items=@([pscustomobject]@{
                    id='synthetic-self-test-patient'; clientId='synthetic-self-test-patient-alias';
                    name=[pscustomobject]@{ clientFullName='Synthetic Self Test'; first='Synthetic'; middle=''; last='Self Test'; preferred='Synthetic' };
                    status=[pscustomobject]@{ id='1049'; label='Active' }; dateOfBirth='2000-01-01'; syntheticUnknown='preserved'
                }); hasMore=$false }
            }
            return [pscustomobject]@{ items=@([pscustomobject]@{
                id='synthetic-self-test-plan'; client='/clients/synthetic-self-test-patient'; status='draft'; listOnly='preserved-list'
            }); hasMore=$false }
        }
        $script:DetailProvider = {
            param($Path, $Query, $Label, $PlanId, $Attempt)
            [pscustomobject]@{ id=$PlanId; client='/clients/synthetic-self-test-patient'; detailOnly='preserved-detail' }
        }
        $script:RetryDelayProvider = { param($Seconds, $Reason, $Attempt) }
        $exportResult = Invoke-CompleteAllevaExport
        if (-not $exportResult.Complete) { throw 'Synthetic complete export unexpectedly returned INCOMPLETE.' }
        $patientSheet = @($exportResult.Workbook.Sheets | Where-Object { $_.Name -eq 'Patient Roster' })[0]
        $planSheet = @($exportResult.Workbook.Sheets | Where-Object { $_.Name -eq 'Treatment Plans' })[0]
        if ($patientSheet.Columns -notcontains 'patient.syntheticUnknown') { throw 'Synthetic patient field was omitted from the wide patient sheet.' }
        if ($planSheet.Columns -notcontains 'list.listOnly' -or $planSheet.Columns -notcontains 'detail.detailOnly') { throw 'Synthetic treatment-plan fields were omitted from the wide treatment-plan sheet.' }
    } finally {
        $script:PageProvider = $previousPageProvider
        $script:DetailProvider = $previousDetailProvider
        $script:RetryDelayProvider = $previousDelayProvider
    }
    $resultPath = Join-Path $ExportDirectory ("alleva-end-user-self-test-{0}.json" -f ([guid]::NewGuid().ToString('N')))
    [ordered]@{
        status = 'PASS'
        action = 'SelfTest'
        synthetic = $true
        record_count = 2
        workbook_status = $exportResult.Status
    } | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
    Write-Host "Synthetic self-test passed: $resultPath" -ForegroundColor Green
    return $resultPath
}

function Invoke-RequestedAction {
    param([Parameter(Mandatory=$true)][ValidateSet('Menu','ExportAll','SelfTest')][string]$RequestedAction)

    switch ($RequestedAction) {
        'SelfTest' {
            [void](Invoke-SyntheticSelfTest)
            return
        }
        'ExportAll' {
            Initialize-Logging
            try {
                $result = Invoke-CompleteAllevaExport
                Write-Host ("Excel export {0}: {1}" -f $result.Status, $result.WorkbookPath) -ForegroundColor $(if ($result.Complete) { 'Green' } else { 'Yellow' })
                if (-not $result.Complete) { throw 'The export is INCOMPLETE. Review the workbook Summary sheet and event counts.' }
            } finally {
                Stop-Logging
            }
            return
        }
        'Menu' {
            Initialize-Logging
            try {
                Show-Header
                Run-MainMenu
            } finally {
                Stop-Logging
            }
            return
        }
    }
}

if (-not $NoRun) {
    try {
        Invoke-RequestedAction -RequestedAction $Action
    } catch {
        Write-Error $_
        exit 1
    }
}
