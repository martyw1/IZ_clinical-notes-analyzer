<#
.SYNOPSIS
  Standalone Alleva EMR remote API diagnostic menu for R3 treatment-plan data pulls.

.DESCRIPTION
  This script bypasses the IZ Clinical Notes Analyzer app completely.
  It does NOT call localhost, does NOT log in to the app, and does NOT depend on the backend.

  It calls the remote Alleva REST API directly using the same production assumptions used by
  the app's current Alleva logic:

    - OAuth2 client_credentials authentication against the Alleva token URL
    - token auth style support: body, basic, basic_urlencoded, both, all
    - /clients for patient roster pulls
    - /treatment-plans for treatment-plan pulls
    - /treatment-plans?ClientId={patient_id} for patient-centered treatment-plan pulls
    - active patient status logic: status.id 1049 or status label Active
    - discharged/inactive logic: status.id 1356 or discharge/closed/deceased-like labels

  The script is designed for Windows PowerShell 5.1 and PowerShell 7+.
  It stores local diagnostic settings next to the script in a DPAPI-protected JSON file.

  Generated logs and exports can contain PHI. Keep them local and access-controlled.

.RECOMMENDED LOCATION
  C:\Users\r3developer\OneDrive - R3 Recovery Services Inc\Development\IZ_clinical-notes-analyzer\diag-build-tools\Invoke-AllevaRemoteDiagnostics.ps1

.EXAMPLES
  .\Invoke-AllevaRemoteDiagnostics.ps1
  .\Invoke-AllevaRemoteDiagnostics.ps1 -Report active_patients
  .\Invoke-AllevaRemoteDiagnostics.ps1 -Report single_patient_treatment_plans -PatientId 12345
  .\Invoke-AllevaRemoteDiagnostics.ps1 -RunRecommendedBatch
#>

[CmdletBinding()]
param(
    [string]$SettingsPath = '',
    [string]$LogDirectory = '',
    [switch]$NoMenu,
    [ValidateSet(
        'all_patient_records',
        'active_patients',
        'inactive_patients',
        'all_treatment_plans',
        'active_treatment_plans',
        'inactive_treatment_plans',
        'single_treatment_plan',
        'patient_centered_treatment_plans',
        'active_patient_centered_treatment_plans',
        'inactive_patient_centered_treatment_plans',
        'single_patient_treatment_plans',
        'patient_treatment_plan_aggregates',
        'treatment_reviews',
        'all_treatment_plan_raw_fields',
        'counts_summary'
    )]
    [string]$Report = '',
    [string]$PatientId = '',
    [switch]$RunRecommendedBatch,
    [switch]$OpenLogsAfterRun
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

$script:ScriptVersion = '2026-07-06-r3-remote-alleva-diagnostics-7'
$script:Settings = $null
$script:AccessToken = ''
$script:TokenExpiresAtUtc = [datetime]::MinValue
$script:LastResult = $null
$script:RunStartedAt = Get-Date

$script:ClientsPath = '/clients'
$script:TreatmentPlansPath = '/treatment-plans'
$script:TreatmentReviewsPath = '/treatment-reviews'
$script:ActiveStatusId = '1049'
$script:DischargedStatusId = '1356'

function Get-ScriptRootSafe {
    if ($PSScriptRoot) { return $PSScriptRoot }
    return (Get-Location).Path
}

$script:Root = Get-ScriptRootSafe
if ([string]::IsNullOrWhiteSpace($SettingsPath)) { $SettingsPath = Join-Path $script:Root 'alleva-remote-diagnostics.local.json' }
if ([string]::IsNullOrWhiteSpace($LogDirectory)) { $LogDirectory = Join-Path $script:Root 'logs' }

function Write-Section {
    param([string]$Title)
    Write-Host ''
    Write-Host ('=' * 92) -ForegroundColor DarkGray
    Write-Host $Title -ForegroundColor Cyan
    Write-Host ('=' * 92) -ForegroundColor DarkGray
}

function Write-Subsection {
    param([string]$Title)
    Write-Host ''
    Write-Host $Title -ForegroundColor Yellow
    Write-Host ('-' * [Math]::Min(92, [Math]::Max(1, $Title.Length))) -ForegroundColor DarkGray
}

function Write-Reminder {
    Write-Host ''
    Write-Host 'PHI / credential reminder:' -ForegroundColor DarkYellow
    Write-Host '  This script calls Alleva directly. Output files may contain patient data.' -ForegroundColor DarkYellow
    Write-Host '  Keep logs local, access-controlled, and out of Git, tickets, email, and chat.' -ForegroundColor DarkYellow
}

function Read-PlainSecret {
    param([string]$Prompt)
    $secure = Read-Host -Prompt $Prompt -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { if ($bstr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) } }
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
        try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
        finally { if ($bstr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) } }
    } catch {
        Write-Host 'Could not decrypt a saved secret. It may have been saved by a different Windows user or machine.' -ForegroundColor DarkYellow
        return ''
    }
}

function Get-DefaultSettings {
    [ordered]@{
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
        RawFieldExportPageLimit = 25
        RawFieldExportMaxPages = 0
        TimeoutSeconds = 60
        ConsoleRowLimit = 100
        MaxPatientPlanFetches = 0
        IncludeTreatmentReviewAggregate = $true
        WriteFullJsonResults = $true
        WriteTsvExports = $true
        WriteRawCollectionJson = $false
    }
}

function ConvertTo-HashtableDeep {
    param($InputObject)
    if ($null -eq $InputObject) { return $null }
    if ($InputObject -is [System.Collections.IDictionary]) {
        $h = [ordered]@{}
        foreach ($key in $InputObject.Keys) { $h[$key] = ConvertTo-HashtableDeep $InputObject[$key] }
        return $h
    }
    if ($InputObject -is [System.Collections.IEnumerable] -and -not ($InputObject -is [string])) {
        $list = New-Object System.Collections.Generic.List[object]
        foreach ($item in $InputObject) { $list.Add((ConvertTo-HashtableDeep $item)) }
        return @($list)
    }
    if ($InputObject.PSObject -and (Get-SafeCount ($InputObject.PSObject.Properties)) -gt 0 -and -not ($InputObject -is [string]) -and -not ($InputObject -is [ValueType])) {
        $h = [ordered]@{}
        foreach ($prop in $InputObject.PSObject.Properties) { $h[$prop.Name] = ConvertTo-HashtableDeep $prop.Value }
        return $h
    }
    return $InputObject
}

function Import-Settings {
    $defaults = Get-DefaultSettings
    $settings = [ordered]@{}
    foreach ($key in $defaults.Keys) { $settings[$key] = $defaults[$key] }
    if (Test-Path -LiteralPath $SettingsPath) {
        try {
            $json = Get-Content -LiteralPath $SettingsPath -Raw -ErrorAction Stop
            if (-not [string]::IsNullOrWhiteSpace($json)) {
                $loaded = ConvertTo-HashtableDeep ($json | ConvertFrom-Json)
                foreach ($key in $loaded.Keys) {
                    if ($settings.Contains($key)) { $settings[$key] = $loaded[$key] }
                }
            }
        } catch {
            Write-Host "Could not load settings from $SettingsPath : $($_.Exception.Message)" -ForegroundColor Red
        }
    }
    $script:Settings = $settings
}

function Save-Settings {
    $parent = Split-Path -Parent $SettingsPath
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    ($script:Settings | ConvertTo-Json -Depth 20) | Set-Content -LiteralPath $SettingsPath -Encoding UTF8
    Write-Host "Saved settings: $SettingsPath" -ForegroundColor Green
}

function Get-SettingBool {
    param([string]$Name)
    try { return [System.Convert]::ToBoolean($script:Settings[$Name]) } catch { return $false }
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
    $value = Read-Host "$Label [$CurrentValue]"
    if ([string]::IsNullOrWhiteSpace($value)) { return $CurrentValue }
    return $value.Trim()
}

function Read-IntegerSetting {
    param([string]$Label, [int]$CurrentValue, [int]$Minimum, [int]$Maximum)
    $raw = Read-Host "$Label [$CurrentValue]"
    if ([string]::IsNullOrWhiteSpace($raw)) { return $CurrentValue }
    $out = 0
    if ([int]::TryParse($raw, [ref]$out)) { return [Math]::Max($Minimum, [Math]::Min($Maximum, $out)) }
    Write-Host 'Invalid number; keeping existing value.' -ForegroundColor DarkYellow
    return $CurrentValue
}

function Edit-SettingsMenu {
    Import-Settings
    Write-Section 'Persistent remote Alleva settings'
    Write-Host 'This does not configure or call the local app. It only stores settings for this standalone script.' -ForegroundColor DarkGray
    Write-Host 'Secrets are protected by Windows DPAPI for the current Windows user.' -ForegroundColor DarkGray

    $script:Settings['AllevaApiBaseUrl'] = Read-SettingValue 'Alleva REST API base URL' ([string]$script:Settings['AllevaApiBaseUrl'])
    $script:Settings['AllevaTokenUrl'] = Read-SettingValue 'Alleva OAuth token URL' ([string]$script:Settings['AllevaTokenUrl'])
    $script:Settings['AllevaOpenApiUrl'] = Read-SettingValue 'Alleva OpenAPI URL, reference only' ([string]$script:Settings['AllevaOpenApiUrl'])
    $script:Settings['ClientId'] = Read-SettingValue 'Alleva client ID' ([string]$script:Settings['ClientId'])

    $currentSecret = ConvertFrom-ProtectedString ([string]$script:Settings['ClientSecretProtected'])
    $newSecret = Read-SettingValue 'Alleva client secret' $currentSecret -Secret
    $script:Settings['ClientSecretProtected'] = ConvertTo-ProtectedString $newSecret

    $script:Settings['Scope'] = Read-SettingValue 'OAuth scope, often blank' ([string]$script:Settings['Scope'])
    $style = Read-SettingValue 'Token auth style: body/basic/basic_urlencoded/both/all' ([string]$script:Settings['TokenAuthStyle'])
    $style = $style.ToLowerInvariant().Replace('-', '_')
    if (@('body','basic','basic_urlencoded','both','all') -notcontains $style) {
        Write-Host 'Invalid token auth style; using body.' -ForegroundColor DarkYellow
        $style = 'body'
    }
    $script:Settings['TokenAuthStyle'] = $style
    $script:Settings['ApiVersion'] = Read-SettingValue 'Alleva api-version / X-Version' ([string]$script:Settings['ApiVersion'])
    $script:Settings['Limit'] = Read-IntegerSetting 'Page Limit' ([int]$script:Settings['Limit']) 1 5000
    $script:Settings['Cursor'] = Read-IntegerSetting 'Initial Cursor' ([int]$script:Settings['Cursor']) 0 2147483647
    $script:Settings['StartDate'] = Read-SettingValue 'Treatment-plan StartDate' ([string]$script:Settings['StartDate'])
    $script:Settings['MaxPages'] = Read-IntegerSetting 'Max pages per collection' ([int]$script:Settings['MaxPages']) 1 10000
    $script:Settings['RawFieldExportPageLimit'] = Read-IntegerSetting 'Raw treatment-plan field export page limit (lower uses less memory)' ([int]$script:Settings['RawFieldExportPageLimit']) 1 500
    $script:Settings['RawFieldExportMaxPages'] = Read-IntegerSetting 'Raw treatment-plan field export max pages, 0 means use MaxPages' ([int]$script:Settings['RawFieldExportMaxPages']) 0 1000000
    $script:Settings['TimeoutSeconds'] = Read-IntegerSetting 'HTTP timeout seconds' ([int]$script:Settings['TimeoutSeconds']) 1 300
    $script:Settings['ConsoleRowLimit'] = Read-IntegerSetting 'Console row preview limit' ([int]$script:Settings['ConsoleRowLimit']) 1 1000
    $script:Settings['MaxPatientPlanFetches'] = Read-IntegerSetting 'Max patient-centered plan fetches, 0 means all selected patients' ([int]$script:Settings['MaxPatientPlanFetches']) 0 1000000

    $includeReviews = Read-Host "Fetch /treatment-reviews for aggregate diagnostics? [Y/n] current=$($script:Settings['IncludeTreatmentReviewAggregate'])"
    if ($includeReviews -match '^[nN]') { $script:Settings['IncludeTreatmentReviewAggregate'] = $false } else { $script:Settings['IncludeTreatmentReviewAggregate'] = $true }

    $raw = Read-Host "Write raw collection JSON files? [y/N] current=$($script:Settings['WriteRawCollectionJson'])"
    if ($raw -match '^[yY]') { $script:Settings['WriteRawCollectionJson'] = $true } else { $script:Settings['WriteRawCollectionJson'] = $false }

    Save-Settings
}

function Show-Settings {
    Import-Settings
    Write-Section 'Current standalone remote settings'
    Write-Host "Script version:             $script:ScriptVersion"
    Write-Host "Working directory:          $script:Root"
    Write-Host "Settings file:              $SettingsPath"
    Write-Host "Log directory:              $LogDirectory"
    Write-Host "AllevaApiBaseUrl:           $($script:Settings['AllevaApiBaseUrl'])"
    Write-Host "AllevaTokenUrl:             $($script:Settings['AllevaTokenUrl'])"
    Write-Host "AllevaOpenApiUrl:           $($script:Settings['AllevaOpenApiUrl'])"
    Write-Host "ClientId configured:        $([bool]([string]$script:Settings['ClientId']))"
    Write-Host "ClientSecret configured:    $([bool]([string]$script:Settings['ClientSecretProtected']))"
    Write-Host "Scope configured:           $([bool]([string]$script:Settings['Scope']))"
    Write-Host "TokenAuthStyle:             $($script:Settings['TokenAuthStyle'])"
    Write-Host "ApiVersion:                 $($script:Settings['ApiVersion'])"
    Write-Host "Limit / Cursor / MaxPages:  $($script:Settings['Limit']) / $($script:Settings['Cursor']) / $($script:Settings['MaxPages'])"
    Write-Host "RawFieldExport Limit/Pages: $($script:Settings['RawFieldExportPageLimit']) / $($script:Settings['RawFieldExportMaxPages'])"
    Write-Host "StartDate:                  $($script:Settings['StartDate'])"
    Write-Host "TimeoutSeconds:             $($script:Settings['TimeoutSeconds'])"
    Write-Host "ConsoleRowLimit:            $($script:Settings['ConsoleRowLimit'])"
    Write-Host "MaxPatientPlanFetches:      $($script:Settings['MaxPatientPlanFetches'])"
    Write-Host "WriteRawCollectionJson:     $($script:Settings['WriteRawCollectionJson'])"
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
                    if ($response.Content) { $content = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult() }
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
        if ([string]::IsNullOrWhiteSpace($content) -and $_.ErrorDetails -and $_.ErrorDetails.Message) { $content = [string]$_.ErrorDetails.Message }
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
    param(
        [string]$Style,
        [string]$ClientId,
        [string]$ClientSecret
    )
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
    $now = (Get-Date).ToUniversalTime()
    if ($script:AccessToken -and $script:TokenExpiresAtUtc -gt $now.AddSeconds(120)) { return $true }

    $creds = Get-SecretClientCredentials
    $styles = Get-TokenStylesToTry ([string]$script:Settings['TokenAuthStyle'])
    Write-Subsection 'Requesting Alleva OAuth token'
    foreach ($style in $styles) {
        Write-Host "Trying token auth style: $style" -ForegroundColor DarkGray
        $resp = Request-TokenOnce -Style $style -ClientId $creds.ClientId -ClientSecret $creds.ClientSecret
        if ($resp.Ok) {
            try { $parsed = $resp.Content | ConvertFrom-Json } catch { $parsed = $null }
            if ($parsed -and $parsed.access_token) {
                $script:AccessToken = [string]$parsed.access_token
                $expiresIn = 3600
                try { if ($parsed.expires_in) { $expiresIn = [int]$parsed.expires_in } } catch { }
                $script:TokenExpiresAtUtc = (Get-Date).ToUniversalTime().AddSeconds($expiresIn)
                Write-Host "Token acquired with $style. Expires in about $expiresIn seconds." -ForegroundColor Green
                return $true
            }
        }
        Write-Host "Token attempt failed. HTTP $($resp.StatusCode). $($resp.Error)" -ForegroundColor DarkYellow
        if ($resp.Content) { Write-Host (($resp.Content -replace $creds.ClientSecret, '[redacted]') -replace $creds.ClientId, '[client-id-redacted]') -ForegroundColor DarkGray }
    }
    Write-Host 'Could not acquire an Alleva bearer token.' -ForegroundColor Red
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
            foreach ($item in $value) { $pairs.Add(("{0}={1}" -f [uri]::EscapeDataString([string]$key), [uri]::EscapeDataString([string]$item))) }
        } else {
            $pairs.Add(("{0}={1}" -f [uri]::EscapeDataString([string]$key), [uri]::EscapeDataString([string]$value)))
        }
    }
    if ($pairs.Count -eq 0) { return $Url }
    $sep = if ($Url.Contains('?')) { '&' } else { '?' }
    return "$Url$sep$($pairs -join '&')"
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

function Get-ApiHeaders {
    $apiVersion = ([string]$script:Settings['ApiVersion']).Trim()
    return @{ Accept='application/json'; Authorization="Bearer $script:AccessToken"; 'X-Version'=$apiVersion }
}


function Get-RedactedHeaders {
    param([hashtable]$Headers)
    $out = [ordered]@{}
    if ($null -eq $Headers) { return $out }
    foreach ($key in $Headers.Keys) {
        if ([string]$key -match '(?i)authorization|token|secret|key') { $out[$key] = '[redacted]' }
        else { $out[$key] = $Headers[$key] }
    }
    return $out
}

function ConvertTo-CompactJsonText {
    param($Value, [int]$Depth = 20)
    if ($null -eq $Value) { return 'null' }
    try { return ($Value | ConvertTo-Json -Depth $Depth -Compress) } catch { return [string]$Value }
}

function New-RemoteCallRecord {
    param(
        [string]$Method,
        [string]$Path,
        [string]$Uri,
        [hashtable]$Query = @{},
        [hashtable]$Headers = @{},
        [AllowNull()]$RequestJson = $null
    )
    return [pscustomobject]([ordered]@{
        method = $Method
        path = $Path
        uri = $Uri
        query = $Query
        headers = (Get-RedactedHeaders $Headers)
        request_json = $RequestJson
        request_json_text = (ConvertTo-CompactJsonText $RequestJson)
    })
}

function ConvertFrom-JsonSafe {
    param([AllowNull()][string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $null }
    try { return $Text | ConvertFrom-Json } catch { return $null }
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

function Get-PropertyNamesSafe {
    param($Value)
    if ($null -eq $Value) { return @() }
    try {
        $names = New-Object System.Collections.Generic.List[string]
        foreach ($prop in $Value.PSObject.Properties) {
            if ($prop -and $prop.Name) { $names.Add([string]$prop.Name) }
        }
        return $names.ToArray()
    } catch { return @() }
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

    # PowerShell 5.1 + StrictMode can throw when a JSON scalar or one-off object is
    # treated like an array and then counted. Normalize every recognized collection
    # shape into a real Object[] before callers count, filter, or export it.
    if (Test-IsEnumerableCollection $Payload) {
        foreach ($item in (ConvertTo-ObjectArraySafe $Payload)) {
            if (Test-IsRecordObject $item) { $records.Add($item) }
        }
        return $records.ToArray()
    }

    $payloadPropertyNames = Get-PropertyNamesSafe $Payload
    foreach ($key in @('items','data','results','value','records')) {
        if ($payloadPropertyNames -contains $key) {
            $value = $Payload.$key
            foreach ($item in (ConvertTo-ObjectArraySafe $value)) {
                if (Test-IsRecordObject $item) { $records.Add($item) }
            }
            return $records.ToArray()
        }
    }

    if (Test-IsRecordObject $Payload) { $records.Add($Payload) }
    return $records.ToArray()
}

function Invoke-AllevaCollection {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [hashtable]$Query = @{},
        [int]$MaxPages = 0,
        [string]$Label = ''
    )
    if (-not (Ensure-AccessToken)) { throw 'No Alleva access token available.' }
    if ($MaxPages -le 0) { $MaxPages = [int]$script:Settings['MaxPages'] }
    $baseUrl = Join-UrlPath ([string]$script:Settings['AllevaApiBaseUrl']) $Path
    $headers = Get-ApiHeaders
    $records = New-Object System.Collections.Generic.List[object]
    $pages = New-Object System.Collections.Generic.List[object]
    $fetchError = $null

    $limit = 500
    try { $limit = [Math]::Max(1, [Math]::Min(5000, [int]$Query['Limit'])) } catch { $limit = 500 }
    $cursor = 0
    try { $cursor = [Math]::Max(0, [int]$Query['Cursor']) } catch { $cursor = 0 }

    for ($pageIndex = 0; $pageIndex -lt $MaxPages; $pageIndex++) {
        $pageQuery = @{}
        foreach ($key in $Query.Keys) { $pageQuery[$key] = $Query[$key] }
        $pageQuery['Limit'] = $limit
        $pageQuery['Cursor'] = $cursor
        $url = Add-QueryString $baseUrl $pageQuery
        Write-Host ("GET {0} page {1}/{2}" -f $Path, ($pageIndex + 1), $MaxPages) -ForegroundColor DarkGray
        $resp = Invoke-HttpRaw -Method GET -Url $url -Headers $headers -Purpose "$Label-page-$pageIndex"
        $callRecord = New-RemoteCallRecord -Method 'GET' -Path $Path -Uri $url -Query $pageQuery -Headers $headers -RequestJson $null
        $pageInfo = [ordered]@{
            method = 'GET'
            path = $Path
            uri = $url
            url = $url
            query = $pageQuery
            headers = (Get-RedactedHeaders $headers)
            request_json = $null
            request_json_text = 'null'
            call = $callRecord
            status_code = $resp.StatusCode
            ok = $resp.Ok
            duration_ms = $resp.DurationMs
            record_count = 0
            error = $resp.Error
        }
        if (-not $resp.Ok) {
            $fetchError = [ordered]@{
                endpoint = $Path
                status_code = $resp.StatusCode
                category = (Get-HttpFailureCategory $resp.StatusCode)
                message = (Get-HttpFailureMessage $Path $resp.StatusCode)
                error = $resp.Error
                url = $url
            }
            $pages.Add([pscustomobject]$pageInfo)
            break
        }
        $payload = ConvertFrom-JsonSafe $resp.Content
        if ($null -eq $payload) {
            $fetchError = [ordered]@{
                endpoint = $Path
                status_code = $resp.StatusCode
                category = 'endpoint_non_json_response'
                message = "GET $Path responded but did not return parseable JSON."
                error = ''
                url = $url
            }
            $pages.Add([pscustomobject]$pageInfo)
            break
        }
        $pageRecords = @(Get-RecordsFromPayload $payload)
        foreach ($record in $pageRecords) { $records.Add($record) }
        $pageRecordCount = Get-SafeCount $pageRecords
        $pageInfo['record_count'] = $pageRecordCount
        $pages.Add([pscustomobject]$pageInfo)
        if ($pageRecordCount -lt $limit) { break }
        $cursor += $limit
    }

    return [pscustomobject]@{
        label = $Label
        path = $Path
        records = $records.ToArray()
        record_count = $records.Count
        pages = $pages.ToArray()
        calls = @($pages.ToArray() | ForEach-Object { if ($_.PSObject.Properties.Name -contains 'call') { $_.call } })
        fetch_error = $fetchError
    }
}

function Get-HttpFailureCategory {
    param([int]$StatusCode)
    switch ($StatusCode) {
        0 { return 'network_or_local_request_failure' }
        400 { return 'endpoint_mapping_or_version_failed' }
        401 { return 'endpoint_authorization_failed' }
        403 { return 'endpoint_permission_denied' }
        404 { return 'endpoint_mapping_or_version_failed' }
        405 { return 'endpoint_mapping_or_version_failed' }
        429 { return 'endpoint_rate_limited' }
        default {
            if ($StatusCode -ge 500) { return 'endpoint_vendor_unavailable' }
            return 'endpoint_request_failed'
        }
    }
}

function Get-HttpFailureMessage {
    param([string]$Path, [int]$StatusCode)
    switch ($StatusCode) {
        0 { return "No HTTP response from GET $Path. Check DNS, TLS, internet access, firewall, or proxy." }
        401 { return "Authentication reached Alleva, but GET $Path was rejected with HTTP 401. Confirm tenant access, token audience/scope, and API version." }
        403 { return "Authentication worked, but credentials are not permitted to read GET $Path." }
        400 { return "Alleva rejected GET $Path with HTTP 400. Confirm path, query parameters, X-Version, and api-version." }
        404 { return "Alleva rejected GET $Path with HTTP 404. Confirm the endpoint path and API version." }
        405 { return "Alleva rejected GET $Path with HTTP 405. Confirm the method/path mapping." }
        429 { return "Alleva rate-limited GET $Path." }
        default { return "Alleva returned HTTP $StatusCode for GET $Path." }
    }
}

function Text-Value {
    param($Value)
    if ($null -eq $Value) { return '' }
    if ($Value -is [string]) { return $Value.Trim() }
    if ($Value -is [bool]) { if ($Value) { return 'true' } else { return 'false' } }
    if ($Value -is [ValueType]) { return ([string]$Value).Trim() }
    return ''
}

function First-Text {
    param($Payload, [string[]]$Keys)
    if ($null -eq $Payload) { return '' }
    foreach ($key in $Keys) {
        if ($Payload.PSObject.Properties.Name -contains $key) {
            $value = $Payload.$key
            if ($null -eq $value) { continue }
            if (Test-IsRecordObject $value) {
                $nested = First-Text $value @('clientId','id','uniqueId','mrn','leadId','href','name','label','statusName','description','value')
                if ($nested) { return $nested }
                continue
            }
            $text = Text-Value $value
            if ($text) { return $text }
        }
    }
    return ''
}

function Date-Text {
    param($Value)
    $text = Text-Value $Value
    if (-not $text) { return '' }
    if ($text.Contains('T')) { return $text.Split('T')[0] }
    if ($text.Length -ge 10 -and $text.Substring(4,1) -eq '-' -and $text.Substring(7,1) -eq '-') { return $text.Substring(0,10) }
    return $text
}

function Parse-DateOrNull {
    param($Value)
    $text = Date-Text $Value
    if (-not $text -or $text.Length -lt 10) { return $null }
    try { return [datetime]::Parse($text.Substring(0,10)).Date } catch { return $null }
}

function Bool-Value {
    param($Value, [bool]$Default = $false)
    if ($Value -is [bool]) { return $Value }
    if ($null -eq $Value) { return $Default }
    $text = ([string]$Value).Trim().ToLowerInvariant()
    if (@('true','1','yes','y','active','complete','completed') -contains $text) { return $true }
    if (@('false','0','no','n','inactive','discharged','closed','deceased','incomplete') -contains $text) { return $false }
    return $Default
}

function Get-PatientStatus {
    param($Patient)
    $statusValue = $null
    if ($Patient.PSObject.Properties.Name -contains 'status') { $statusValue = $Patient.status }
    $statusId = ''
    $statusLabel = ''
    if (Test-IsRecordObject $statusValue) {
        $statusId = First-Text $statusValue @('id')
        $statusLabel = First-Text $statusValue @('name','label','statusName','description','value')
    } else {
        $statusId = First-Text $Patient @('statusId','status_id')
        $statusLabel = (Text-Value $statusValue)
        if (-not $statusLabel) { $statusLabel = First-Text $Patient @('statusName') }
    }
    $normalizedLabel = (($statusLabel.Trim().ToLowerInvariant() -replace '[\s_-]+',''))
    $scope = 'unknown'
    if ($statusId.Trim() -eq $script:ActiveStatusId -or $normalizedLabel -eq 'active') { $scope = 'active' }
    elseif ($statusId.Trim() -eq $script:DischargedStatusId -or $normalizedLabel -like '*discharg*' -or @('closed','deceased','inactive') -contains $normalizedLabel) { $scope = 'discharged' }
    elseif ($normalizedLabel) { $scope = 'other' }
    return [ordered]@{ status_id=$statusId; status_label=$statusLabel; status_scope=$scope }
}

function Get-PatientId {
    param($Patient)
    $value = $null
    if ($Patient.PSObject.Properties.Name -contains 'id') { $value = $Patient.id }
    return (Text-Value $value)
}

function Get-PatientRow {
    param($Patient)
    $status = Get-PatientStatus $Patient
    $patientId = Get-PatientId $Patient
    $sourceId = First-Text $Patient @('chartId','externalId','clientId','uniqueId','mrn')
    $admissionValue = $null
    if ($Patient.PSObject.Properties.Name -contains 'admissionDateTime') { $admissionValue = $Patient.admissionDateTime }
    elseif ($Patient.PSObject.Properties.Name -contains 'admissionDate') { $admissionValue = $Patient.admissionDate }
    $dischargeValue = $null
    if ($Patient.PSObject.Properties.Name -contains 'dischargeDate') { $dischargeValue = $Patient.dischargeDate }
    elseif ($Patient.PSObject.Properties.Name -contains 'dischargeDateTime') { $dischargeValue = $Patient.dischargeDateTime }
    $isClientValue = $true
    if ($Patient.PSObject.Properties.Name -contains 'isClient') { $isClientValue = $Patient.isClient }
    $firstContactValue = $null
    if ($Patient.PSObject.Properties.Name -contains 'firstContactDate') { $firstContactValue = $Patient.firstContactDate }
    return [ordered]@{
        patient_id = $patientId
        source_id = $sourceId
        admission_date = (Date-Text $admissionValue)
        status_id = $status.status_id
        status_label = $status.status_label
        status_scope = $status.status_scope
        is_client = (Bool-Value $isClientValue -Default $true)
        planned_discharge_date = (Date-Text $dischargeValue)
        level_of_care = (First-Text $Patient @('levelOfCare'))
        facility = (First-Text $Patient @('facilityName'))
        primary_clinician = (First-Text $Patient @('primaryClinician','primaryClinicians','medicalProviders'))
        first_contact_date = (Date-Text $firstContactValue)
    }
}

function Get-RawClientReference {
    param($Plan)
    if (-not ($Plan.PSObject.Properties.Name -contains 'client')) { return [pscustomobject]@{ reference=''; warning='client field is missing' } }
    $client = $Plan.client
    if ($client -is [string]) { return [pscustomobject]@{ reference=$client.Trim(); warning='' } }
    if (Test-IsRecordObject $client) {
        $href = First-Text $client @('href')
        if ($href) { return [pscustomobject]@{ reference=$href; warning='client field was an object; used client.href' } }
        $id = First-Text $client @('id','clientId')
        if ($id) { return [pscustomobject]@{ reference="/clients/$id"; warning='client field was an object; used client id' } }
        return [pscustomobject]@{ reference=''; warning='client field was an object without href/id' }
    }
    return [pscustomobject]@{ reference=''; warning='client field is not a usable string or object' }
}

function Get-PatientIdFromClientReference {
    param([string]$Reference)
    $value = if ($null -eq $Reference) { '' } else { ([string]$Reference).Trim() }
    if (-not $value) { return '' }
    try {
        if ($value -match '^https?://') { $path = ([uri]$value).AbsolutePath } else { $path = $value }
        $parts = @($path.Trim('/').Split('/') | Where-Object { $_ -ne '' })
        if ($parts.Count -ge 2 -and $parts[$parts.Count - 2].ToLowerInvariant() -eq 'clients') {
            return [uri]::UnescapeDataString($parts[$parts.Count - 1])
        }
    } catch { }
    return ''
}

function Count-PlanContent {
    param($Plan)
    $problems = @()
    if ($Plan.PSObject.Properties.Name -contains 'problems' -and $Plan.problems -is [System.Collections.IEnumerable]) { $problems = @($Plan.problems) }
    $goals = New-Object System.Collections.Generic.List[object]
    $objectives = New-Object System.Collections.Generic.List[object]
    $interventions = New-Object System.Collections.Generic.List[object]
    $diagnosisCount = 0
    foreach ($problem in $problems) {
        if ($problem.PSObject.Properties.Name -contains 'diagnoses' -and (Test-IsEnumerableCollection $problem.diagnoses)) { $diagnosisCount += (Get-SafeCount (ConvertTo-ObjectArraySafe $problem.diagnoses)) }
        if ($problem.PSObject.Properties.Name -contains 'goals' -and $problem.goals -is [System.Collections.IEnumerable]) {
            foreach ($goal in @($problem.goals)) {
                $goals.Add($goal)
                if ($goal.PSObject.Properties.Name -contains 'objectives' -and $goal.objectives -is [System.Collections.IEnumerable]) {
                    foreach ($objective in @($goal.objectives)) {
                        $objectives.Add($objective)
                        if ($objective.PSObject.Properties.Name -contains 'interventions' -and $objective.interventions -is [System.Collections.IEnumerable]) {
                            foreach ($intervention in @($objective.interventions)) { $interventions.Add($intervention) }
                        }
                    }
                }
            }
        }
    }
    if ($diagnosisCount -eq 0 -and $Plan.PSObject.Properties.Name -contains 'diagnoses' -and (Test-IsEnumerableCollection $Plan.diagnoses)) { $diagnosisCount = Get-SafeCount (ConvertTo-ObjectArraySafe $Plan.diagnoses) }
    return [ordered]@{
        problem_count = (Get-SafeCount $problems)
        diagnosis_count = $diagnosisCount
        goal_count = (Get-SafeCount $goals)
        objective_count = (Get-SafeCount $objectives)
        intervention_count = (Get-SafeCount $interventions)
    }
}

function Get-TreatmentPlanRow {
    param($Plan, [string]$ExpectedPatientId = '')
    $today = (Get-Date).Date
    $clientRef = Get-RawClientReference $Plan
    $planPatientId = Get-PatientIdFromClientReference $clientRef.reference
    if (-not $planPatientId) { $planPatientId = First-Text $Plan @('clientId','patientId','leadId') }

    $startValue = $null
    if ($Plan.PSObject.Properties.Name -contains 'startDate') { $startValue = $Plan.startDate }
    $endValue = $null
    if ($Plan.PSObject.Properties.Name -contains 'endDate') { $endValue = $Plan.endDate }
    $createdValue = $null
    if ($Plan.PSObject.Properties.Name -contains 'createdDate') { $createdValue = $Plan.createdDate }
    elseif ($Plan.PSObject.Properties.Name -contains 'createdDated') { $createdValue = $Plan.createdDated }
    $lastModifiedValue = $null
    if ($Plan.PSObject.Properties.Name -contains 'lastModified') { $lastModifiedValue = $Plan.lastModified }
    $isActiveValue = $true
    if ($Plan.PSObject.Properties.Name -contains 'isActive') { $isActiveValue = $Plan.isActive }
    $isCompleteValue = $false
    if ($Plan.PSObject.Properties.Name -contains 'isComplete') { $isCompleteValue = $Plan.isComplete }
    $isInitialValue = $false
    if ($Plan.PSObject.Properties.Name -contains 'isInitialTP') { $isInitialValue = $Plan.isInitialTP }
    $isWileyValue = $false
    if ($Plan.PSObject.Properties.Name -contains 'isWiley') { $isWileyValue = $Plan.isWiley }
    $reasonValue = $null
    if ($Plan.PSObject.Properties.Name -contains 'reasonForAdmission') { $reasonValue = $Plan.reasonForAdmission }
    $needsValue = $null
    if ($Plan.PSObject.Properties.Name -contains 'initialClientNeeds') { $needsValue = $Plan.initialClientNeeds }
    $familyValue = $null
    if ($Plan.PSObject.Properties.Name -contains 'familyEducationNeeds') { $familyValue = $Plan.familyEducationNeeds }

    $startDate = Date-Text $startValue
    $endDate = Date-Text $endValue
    $endDateParsed = Parse-DateOrNull $endDate
    $isActive = Bool-Value $isActiveValue -Default $true
    $isComplete = Bool-Value $isCompleteValue -Default $false
    $contentCounts = Count-PlanContent $Plan
    $warnings = New-Object System.Collections.Generic.List[string]
    if ($clientRef.warning) { $warnings.Add($clientRef.warning) }
    if ($ExpectedPatientId -and $planPatientId -and $planPatientId -ne $ExpectedPatientId) { $warnings.Add("client reference points to $planPatientId, expected $ExpectedPatientId") }
    if ($isActive -and $endDateParsed -and $endDateParsed -lt $today) { $warnings.Add("active plan endDate $($endDateParsed.ToString('yyyy-MM-dd')) is before $($today.ToString('yyyy-MM-dd'))") }
    if ($isActive -and -not $isComplete) { $warnings.Add('isComplete is false/missing on active plan; EMR submission state may differ from current-plan state') }
    $outPatientId = if ($ExpectedPatientId) { $ExpectedPatientId } else { $planPatientId }
    $joinValidated = if ($ExpectedPatientId) { [bool]($planPatientId -eq $ExpectedPatientId -and $clientRef.warning -eq '') } else { [bool]$planPatientId }

    return [ordered]@{
        treatment_plan_id = (First-Text $Plan @('TPId','id','treatmentPlanId'))
        patient_id = $outPatientId
        plan_client_id = $planPatientId
        raw_client_ref = $clientRef.reference
        join_validated = $joinValidated
        start_date = $startDate
        end_date = $endDate
        created_date = (Date-Text $createdValue)
        last_modified = (Date-Text $lastModifiedValue)
        is_active = $isActive
        is_complete = $isComplete
        is_initial_tp = (Bool-Value $isInitialValue -Default $false)
        is_wiley = (Bool-Value $isWileyValue -Default $false)
        has_reason_for_admission = [bool](Text-Value $reasonValue)
        has_initial_client_needs = [bool](Text-Value $needsValue)
        has_family_education_needs = [bool](Text-Value $familyValue)
        problem_count = $contentCounts.problem_count
        diagnosis_count = $contentCounts.diagnosis_count
        goal_count = $contentCounts.goal_count
        objective_count = $contentCounts.objective_count
        intervention_count = $contentCounts.intervention_count
        warnings = ($warnings -join '; ')
    }
}

function Get-LatestPlanSortValue {
    param($Row)
    $value = Text-Value $Row.treatment_plan_id
    $number = -1
    if ([int]::TryParse($value, [ref]$number)) { return $number }
    $matches = [regex]::Matches($value, '\d+')
    if ($matches.Count -gt 0) { return [int]$matches[$matches.Count - 1].Value }
    return -1
}

function New-PatientAggregate {
    param($Patient, [object[]]$Plans, [string[]]$EndpointUrls = @())
    $patientRow = Get-PatientRow $Patient
    $patientId = [string]$patientRow.patient_id
    $planRows = New-Object System.Collections.Generic.List[object]
    foreach ($plan in @($Plans)) { $planRows.Add([pscustomobject](Get-TreatmentPlanRow $plan $patientId)) }
    $activePlans = @($planRows | Where-Object { $_.is_active })
    $latestActive = $null
    if ((Get-SafeCount $activePlans) -gt 0) { $latestActive = $activePlans | Sort-Object @{ Expression = { Get-LatestPlanSortValue $_ }; Descending = $true } | Select-Object -First 1 }
    $warnings = New-Object System.Collections.Generic.List[string]
    foreach ($row in $planRows) { if ($row.warnings) { $warnings.Add($row.warnings) } }
    if ($patientRow.status_scope -eq 'unknown') { $warnings.Add('unknown_patient_status: Client status is missing or unknown; this patient is not treated as active') }
    if ($patientRow.status_scope -eq 'other') { $warnings.Add("other_patient_status: Client status '$($patientRow.status_label)' is not Active or Discharged") }
    $warnings.Add('review_data_unavailable: nextReviewDue requires a known treatmentPlanReviewId; treatment reviews cannot be listed/joined by patient via REST alone')
    return [ordered]@{
        patient_id = $patientId
        source_id = $patientRow.source_id
        status_id = $patientRow.status_id
        status_label = $patientRow.status_label
        status_scope = $patientRow.status_scope
        admission_date = $patientRow.admission_date
        planned_discharge_date = $patientRow.planned_discharge_date
        level_of_care = $patientRow.level_of_care
        facility = $patientRow.facility
        primary_clinician = $patientRow.primary_clinician
        total_plan_count = (Get-SafeCount $planRows)
        active_plan_count = (Get-SafeCount $activePlans)
        has_multiple_active_plans = [bool]((Get-SafeCount $activePlans) -gt 1)
        treatment_plan_ids = (@($planRows | ForEach-Object { $_.treatment_plan_id }) -join ',')
        active_treatment_plan_ids = (@($activePlans | ForEach-Object { $_.treatment_plan_id }) -join ',')
        latest_created_active_plan_id = $(if ($latestActive) { $latestActive.treatment_plan_id } else { '' })
        review_data_status = 'unavailable_via_rest_without_known_review_id'
        next_review_due_source = 'unavailable'
        warning_count = (Get-SafeCount $warnings)
        warnings = ($warnings -join '; ')
        treatment_plans = @($planRows)
    }
}

function Write-RowsTable {
    param([object[]]$Rows, [string[]]$Columns)
    $limit = [int]$script:Settings['ConsoleRowLimit']
    if ((Get-SafeCount $Rows) -eq 0) {
        Write-Host '<no rows>' -ForegroundColor DarkYellow
        return
    }
    $Rows | Select-Object -First $limit -Property $Columns | Format-Table -AutoSize
    if ((Get-SafeCount $Rows) -gt $limit) { Write-Host "Showing first $limit of $(Get-SafeCount $Rows) row(s). Full TSV/JSON written to logs." -ForegroundColor DarkYellow }
}

function ConvertTo-TsvValue {
    param($Value)
    if ($null -eq $Value) { return '' }
    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) { $text = ($Value -join ',') }
    elseif (Test-IsRecordObject $Value) { $text = ($Value | ConvertTo-Json -Depth 8 -Compress) }
    else { $text = [string]$Value }
    return ($text -replace "`r", ' ' -replace "`n", ' ' -replace "`t", ' ')
}

function ConvertTo-TsvLine {
    param($Row, [string[]]$Columns)
    $values = foreach ($column in $Columns) {
        if ($null -ne $Row -and $Row.PSObject.Properties.Name -contains $column) { ConvertTo-TsvValue $Row.$column } else { '' }
    }
    return ($values -join "`t")
}

function ConvertTo-Tsv {
    param([object[]]$Rows, [string[]]$Columns)
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add(($Columns -join "`t"))
    foreach ($row in $Rows) { $lines.Add((ConvertTo-TsvLine -Row $row -Columns $Columns)) }
    return ($lines -join [Environment]::NewLine)
}

function Ensure-LogDirectory {
    if (-not (Test-Path -LiteralPath $LogDirectory)) { New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null }
}

function Save-RunOutput {
    param(
        [Parameter(Mandatory=$true)][string]$ReportName,
        [Parameter(Mandatory=$true)]$Result,
        [object[]]$Rows,
        [string[]]$Columns
    )
    Ensure-LogDirectory
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $safeReport = $ReportName -replace '[^a-zA-Z0-9._-]', '_'
    $summaryPath = Join-Path $LogDirectory "$stamp-$safeReport-summary.txt"
    $jsonPath = Join-Path $LogDirectory "$stamp-$safeReport-result.json"
    $tsvPath = Join-Path $LogDirectory "$stamp-$safeReport-rows.tsv"
    $calls = @(Get-CallsFromResult $Result)
    $callsPath = Join-Path $LogDirectory "$stamp-$safeReport-calls.tsv"
    $callsJsonPath = Join-Path $LogDirectory "$stamp-$safeReport-calls.json"
    $callRows = foreach ($call in $calls) {
        [pscustomobject]([ordered]@{ method=$call.method; path=$call.path; uri=$call.uri; request_json=$call.request_json_text })
    }
    if ((Get-SafeCount $callRows) -gt 0) {
        ConvertTo-Tsv -Rows @($callRows) -Columns @('method','path','uri','request_json') | Set-Content -LiteralPath $callsPath -Encoding UTF8
        ($calls | ConvertTo-Json -Depth 40) | Set-Content -LiteralPath $callsJsonPath -Encoding UTF8
    }
    $callsSummaryJson = ConvertTo-CompactJsonText $calls 40
    $summary = @"
Report: $ReportName
ScriptVersion: $script:ScriptVersion
StartedAtLocal: $($script:RunStartedAt.ToString('s'))
FinishedAtLocal: $((Get-Date).ToString('s'))
Status: $($Result.status)
Message: $($Result.message)
ReturnedCount: $($Result.returned_count)
TotalRecordsSeen: $($Result.total_records_seen)
SourceOperation: $($Result.source_operation)
CallsJson: $callsSummaryJson
FetchError: $($Result.fetch_error | ConvertTo-Json -Depth 8 -Compress)
SettingsPath: $SettingsPath
LogDirectory: $LogDirectory
PHIWarning: These outputs may contain PHI. Keep local and access-controlled.
"@
    Set-Content -LiteralPath $summaryPath -Value $summary -Encoding UTF8
    if (Get-SettingBool 'WriteFullJsonResults') { ($Result | ConvertTo-Json -Depth 100) | Set-Content -LiteralPath $jsonPath -Encoding UTF8 }
    if ((Get-SettingBool 'WriteTsvExports') -and (Get-SafeCount $Columns) -gt 0) { ConvertTo-Tsv -Rows $Rows -Columns $Columns | Set-Content -LiteralPath $tsvPath -Encoding UTF8 }
    Write-Host "Saved summary: $summaryPath" -ForegroundColor Green
    if (Test-Path -LiteralPath $jsonPath) { Write-Host "Saved JSON:    $jsonPath" -ForegroundColor Green }
    if (Test-Path -LiteralPath $tsvPath) { Write-Host "Saved TSV:     $tsvPath" -ForegroundColor Green }
    if (Test-Path -LiteralPath $callsPath) { Write-Host "Saved calls:   $callsPath" -ForegroundColor Green }
}

function Get-PatientColumns { return @('patient_id','source_id','admission_date','status_id','status_label','status_scope','is_client','planned_discharge_date','level_of_care','facility','primary_clinician','first_contact_date') }
function Get-PlanColumns { return @('treatment_plan_id','patient_id','plan_client_id','join_validated','start_date','end_date','created_date','last_modified','is_active','is_complete','is_initial_tp','is_wiley','problem_count','diagnosis_count','goal_count','objective_count','intervention_count','warnings') }
function Get-AggregateColumns { return @('patient_id','source_id','status_id','status_label','status_scope','admission_date','planned_discharge_date','level_of_care','facility','primary_clinician','total_plan_count','active_plan_count','has_multiple_active_plans','treatment_plan_ids','active_treatment_plan_ids','latest_created_active_plan_id','review_data_status','next_review_due_source','warning_count','warnings') }
function Get-ReviewColumns { return @('id','treatmentPlanReviewId','treatmentPlanId','clientId','createdDate','lastModified','nextReviewDue','isComplete','isActive') }


function Get-RawPlanFieldColumns { return @('treatment_plan_id','patient_id','plan_client_id','raw_client_ref','field_path','value_type','value') }
function Get-CountSummaryColumns { return @('menu_option','report','count','count_basis','call_made','notes') }

function Get-ValueTypeNameSafe {
    param($Value)
    if ($null -eq $Value) { return 'null' }
    if ($Value -is [string]) { return 'string' }
    if ($Value -is [bool]) { return 'boolean' }
    if ($Value -is [int] -or $Value -is [long] -or $Value -is [decimal] -or $Value -is [double] -or $Value -is [float]) { return 'number' }
    if (Test-IsEnumerableCollection $Value) { return 'array' }
    if (Test-IsRecordObject $Value) { return 'object' }
    return $Value.GetType().Name
}

function Add-FlatFieldRows {
    param(
        [Parameter(Mandatory=$true)]$Rows,
        [string]$TreatmentPlanId,
        [string]$PatientId,
        [string]$PlanClientId,
        [string]$RawClientRef,
        [string]$Prefix,
        $Value
    )

    # Do not recurse here. Real Alleva treatment plans can contain nested
    # problems/goals/objectives/interventions/content trees deep enough to trip
    # Windows PowerShell's call-depth limit. Use an explicit stack so raw-field
    # export remains stable even for large or deeply nested treatment plans.
    $stack = New-Object System.Collections.ArrayList
    [void]$stack.Add([pscustomobject]([ordered]@{ path=$Prefix; value=$Value }))

    while ($stack.Count -gt 0) {
        $lastIndex = $stack.Count - 1
        $frame = $stack[$lastIndex]
        $stack.RemoveAt($lastIndex)

        $currentPath = [string]$frame.path
        $currentValue = $frame.value

        if ($null -eq $currentValue) {
            $Rows.Add([pscustomobject]([ordered]@{ treatment_plan_id=$TreatmentPlanId; patient_id=$PatientId; plan_client_id=$PlanClientId; raw_client_ref=$RawClientRef; field_path=$currentPath; value_type='null'; value='' }))
            continue
        }

        if ($currentValue -is [System.Collections.IDictionary]) {
            $keys = @()
            foreach ($key in $currentValue.Keys) { $keys += [string]$key }
            if ((Get-SafeCount $keys) -eq 0) {
                $Rows.Add([pscustomobject]([ordered]@{ treatment_plan_id=$TreatmentPlanId; patient_id=$PatientId; plan_client_id=$PlanClientId; raw_client_ref=$RawClientRef; field_path=$currentPath; value_type='object'; value=(ConvertTo-CompactJsonText $currentValue 30) }))
                continue
            }
            for ($idx = (Get-SafeCount $keys) - 1; $idx -ge 0; $idx--) {
                $name = [string]$keys[$idx]
                $childPath = if ([string]::IsNullOrWhiteSpace($currentPath)) { $name } else { "$currentPath.$name" }
                [void]$stack.Add([pscustomobject]([ordered]@{ path=$childPath; value=$currentValue[$name] }))
            }
            continue
        }

        if (Test-IsRecordObject $currentValue) {
            $names = @(Get-PropertyNamesSafe $currentValue)
            if ((Get-SafeCount $names) -eq 0) {
                $Rows.Add([pscustomobject]([ordered]@{ treatment_plan_id=$TreatmentPlanId; patient_id=$PatientId; plan_client_id=$PlanClientId; raw_client_ref=$RawClientRef; field_path=$currentPath; value_type='object'; value=(ConvertTo-CompactJsonText $currentValue 30) }))
                continue
            }
            for ($idx = (Get-SafeCount $names) - 1; $idx -ge 0; $idx--) {
                $name = [string]$names[$idx]
                $childPath = if ([string]::IsNullOrWhiteSpace($currentPath)) { $name } else { "$currentPath.$name" }
                $childValue = $null
                try { $childValue = $currentValue.PSObject.Properties[$name].Value } catch { $childValue = $null }
                [void]$stack.Add([pscustomobject]([ordered]@{ path=$childPath; value=$childValue }))
            }
            continue
        }

        if (Test-IsEnumerableCollection $currentValue) {
            $items = @(ConvertTo-ObjectArraySafe $currentValue)
            $itemCount = Get-SafeCount $items
            if ($itemCount -eq 0) {
                $Rows.Add([pscustomobject]([ordered]@{ treatment_plan_id=$TreatmentPlanId; patient_id=$PatientId; plan_client_id=$PlanClientId; raw_client_ref=$RawClientRef; field_path=$currentPath; value_type='array'; value='[]' }))
                continue
            }
            for ($idx = $itemCount - 1; $idx -ge 0; $idx--) {
                $childPath = if ([string]::IsNullOrWhiteSpace($currentPath)) { ('[{0}]' -f $idx) } else { ('{0}[{1}]' -f $currentPath, $idx) }
                [void]$stack.Add([pscustomobject]([ordered]@{ path=$childPath; value=$items[$idx] }))
            }
            continue
        }

        $Rows.Add([pscustomobject]([ordered]@{
            treatment_plan_id = $TreatmentPlanId
            patient_id = $PatientId
            plan_client_id = $PlanClientId
            raw_client_ref = $RawClientRef
            field_path = $currentPath
            value_type = (Get-ValueTypeNameSafe $currentValue)
            value = (Text-Value $currentValue)
        }))
    }
}


function Add-FlatFieldRowsToWriter {
    param(
        [Parameter(Mandatory=$true)]$Writer,
        [Parameter(Mandatory=$true)]$PreviewRows,
        [int]$PreviewLimit,
        [Parameter(Mandatory=$true)][ref]$FieldCountRef,
        [string]$TreatmentPlanId,
        [string]$PatientId,
        [string]$PlanClientId,
        [string]$RawClientRef,
        [string]$Prefix,
        $Value
    )

    $columns = Get-RawPlanFieldColumns
    $stack = New-Object System.Collections.ArrayList
    [void]$stack.Add([pscustomobject]([ordered]@{ path=$Prefix; value=$Value }))

    while ($stack.Count -gt 0) {
        $lastIndex = $stack.Count - 1
        $frame = $stack[$lastIndex]
        $stack.RemoveAt($lastIndex)

        $currentPath = [string]$frame.path
        $currentValue = $frame.value
        $emitRow = $null

        if ($null -eq $currentValue) {
            $emitRow = [pscustomobject]([ordered]@{ treatment_plan_id=$TreatmentPlanId; patient_id=$PatientId; plan_client_id=$PlanClientId; raw_client_ref=$RawClientRef; field_path=$currentPath; value_type='null'; value='' })
        } elseif ($currentValue -is [System.Collections.IDictionary]) {
            $keys = @()
            foreach ($key in $currentValue.Keys) { $keys += [string]$key }
            if ((Get-SafeCount $keys) -eq 0) {
                $emitRow = [pscustomobject]([ordered]@{ treatment_plan_id=$TreatmentPlanId; patient_id=$PatientId; plan_client_id=$PlanClientId; raw_client_ref=$RawClientRef; field_path=$currentPath; value_type='object'; value='{}' })
            } else {
                for ($idx = (Get-SafeCount $keys) - 1; $idx -ge 0; $idx--) {
                    $name = [string]$keys[$idx]
                    $childPath = if ([string]::IsNullOrWhiteSpace($currentPath)) { $name } else { "$currentPath.$name" }
                    [void]$stack.Add([pscustomobject]([ordered]@{ path=$childPath; value=$currentValue[$name] }))
                }
                continue
            }
        } elseif (Test-IsRecordObject $currentValue) {
            $names = @(Get-PropertyNamesSafe $currentValue)
            if ((Get-SafeCount $names) -eq 0) {
                $emitRow = [pscustomobject]([ordered]@{ treatment_plan_id=$TreatmentPlanId; patient_id=$PatientId; plan_client_id=$PlanClientId; raw_client_ref=$RawClientRef; field_path=$currentPath; value_type='object'; value='{}' })
            } else {
                for ($idx = (Get-SafeCount $names) - 1; $idx -ge 0; $idx--) {
                    $name = [string]$names[$idx]
                    $childPath = if ([string]::IsNullOrWhiteSpace($currentPath)) { $name } else { "$currentPath.$name" }
                    $childValue = $null
                    try { $childValue = $currentValue.PSObject.Properties[$name].Value } catch { $childValue = $null }
                    [void]$stack.Add([pscustomobject]([ordered]@{ path=$childPath; value=$childValue }))
                }
                continue
            }
        } elseif (Test-IsEnumerableCollection $currentValue) {
            $items = @(ConvertTo-ObjectArraySafe $currentValue)
            $itemCount = Get-SafeCount $items
            if ($itemCount -eq 0) {
                $emitRow = [pscustomobject]([ordered]@{ treatment_plan_id=$TreatmentPlanId; patient_id=$PatientId; plan_client_id=$PlanClientId; raw_client_ref=$RawClientRef; field_path=$currentPath; value_type='array'; value='[]' })
            } else {
                for ($idx = $itemCount - 1; $idx -ge 0; $idx--) {
                    $childPath = if ([string]::IsNullOrWhiteSpace($currentPath)) { ('[{0}]' -f $idx) } else { ('{0}[{1}]' -f $currentPath, $idx) }
                    [void]$stack.Add([pscustomobject]([ordered]@{ path=$childPath; value=$items[$idx] }))
                }
                continue
            }
        } else {
            $emitRow = [pscustomobject]([ordered]@{
                treatment_plan_id = $TreatmentPlanId
                patient_id = $PatientId
                plan_client_id = $PlanClientId
                raw_client_ref = $RawClientRef
                field_path = $currentPath
                value_type = (Get-ValueTypeNameSafe $currentValue)
                value = (Text-Value $currentValue)
            })
        }

        if ($null -ne $emitRow) {
            $Writer.WriteLine((ConvertTo-TsvLine -Row $emitRow -Columns $columns))
            if ($PreviewRows.Count -lt $PreviewLimit) { $PreviewRows.Add($emitRow) }
            $FieldCountRef.Value = ([int64]$FieldCountRef.Value + 1)
        }
    }
}


function Get-CollectionEntriesFromResult {
    param($Result)
    $entries = New-Object System.Collections.Generic.List[object]
    if ($null -eq $Result) { return @() }
    if (-not ($Result.PSObject.Properties.Name -contains 'collections')) { return @() }
    $collections = $Result.collections
    if ($null -eq $collections) { return @() }
    if ($collections -is [System.Collections.IDictionary]) {
        foreach ($key in $collections.Keys) {
            $entries.Add([pscustomobject]([ordered]@{ name=[string]$key; value=$collections[$key] }))
        }
        return $entries.ToArray()
    }
    foreach ($prop in $collections.PSObject.Properties) {
        $entries.Add([pscustomobject]([ordered]@{ name=[string]$prop.Name; value=$prop.Value }))
    }
    return $entries.ToArray()
}

function Get-CallsFromResult {
    param($Result)
    $calls = New-Object System.Collections.Generic.List[object]
    if ($null -eq $Result) { return @() }
    if ($Result.PSObject.Properties.Name -contains 'calls') {
        foreach ($call in (ConvertTo-ObjectArraySafe $Result.calls)) { if ($call) { $calls.Add($call) } }
    }
    foreach ($entry in (Get-CollectionEntriesFromResult $Result)) {
        $collection = $entry.value
        if ($null -eq $collection) { continue }
        if ($collection.PSObject.Properties.Name -contains 'calls') {
            foreach ($call in (ConvertTo-ObjectArraySafe $collection.calls)) { if ($call) { $calls.Add($call) } }
        } elseif ($collection.PSObject.Properties.Name -contains 'pages') {
            foreach ($page in (ConvertTo-ObjectArraySafe $collection.pages)) {
                if ($page.PSObject.Properties.Name -contains 'call') { $calls.Add($page.call) }
            }
        }
    }
    return $calls.ToArray()
}

function Get-CallMadeText {
    param($Calls)
    $parts = New-Object System.Collections.Generic.List[string]
    foreach ($call in (ConvertTo-ObjectArraySafe $Calls)) {
        if ($null -eq $call) { continue }
        $method = if ($call.PSObject.Properties.Name -contains 'method') { [string]$call.method } else { 'GET' }
        $uri = if ($call.PSObject.Properties.Name -contains 'uri') { [string]$call.uri } elseif ($call.PSObject.Properties.Name -contains 'url') { [string]$call.url } else { '' }
        if ($uri) { $parts.Add("$method $uri") }
    }
    return ($parts.ToArray() -join '; ')
}

function Add-CountRow {
    param($Rows, [string]$MenuOption, [string]$Report, [AllowNull()]$Count, [string]$CountBasis, [string]$CallMade, [string]$Notes = '')
    $countText = if ($null -eq $Count) { 'requires input' } else { [string]$Count }
    $Rows.Add([pscustomobject]([ordered]@{ menu_option=$MenuOption; report=$Report; count=$countText; count_basis=$CountBasis; call_made=$CallMade; notes=$Notes }))
}

function Invoke-RawTreatmentPlanFieldExport {
    # Streaming exporter: do not use Invoke-AllevaCollection here because that
    # accumulates all pages and all flattened rows in memory. This mode is meant
    # to produce a COMPLETE final output for all pulled treatment plans/all fields
    # while keeping memory flat: one page and one treatment plan are processed at
    # a time, rows are appended to disk, and page objects are released.
    if (-not (Ensure-AccessToken)) { throw 'No Alleva access token available.' }
    Ensure-LogDirectory

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $safeReport = 'all_treatment_plan_raw_fields'
    $fullFieldsPath = Join-Path $LogDirectory "$stamp-$safeReport-FULL-raw-fields.tsv"
    $rawPlansJsonlPath = Join-Path $LogDirectory "$stamp-$safeReport-FULL-raw-plans.jsonl"
    $streamSummaryPath = Join-Path $LogDirectory "$stamp-$safeReport-stream-summary.txt"
    $pageDir = Join-Path $LogDirectory "$stamp-$safeReport-page-cache"
    $writePageJson = Get-SettingBool 'WriteRawCollectionJson'
    if ($writePageJson -and -not (Test-Path -LiteralPath $pageDir)) { New-Item -ItemType Directory -Path $pageDir -Force | Out-Null }

    $columns = Get-RawPlanFieldColumns
    $previewRows = New-Object System.Collections.Generic.List[object]
    $calls = New-Object System.Collections.Generic.List[object]
    $pages = New-Object System.Collections.Generic.List[object]
    $fetchError = $null
    [int64]$fieldCount = 0
    [int64]$planCount = 0
    [int64]$recordsSeen = 0

    $query = Get-BaseQuery -ForTreatmentPlans
    $rawLimit = 25
    try { $rawLimit = [Math]::Max(1, [Math]::Min(500, [int]$script:Settings['RawFieldExportPageLimit'])) } catch { $rawLimit = 25 }
    $query['Limit'] = $rawLimit
    $maxPages = [int]$script:Settings['MaxPages']
    try { if ([int]$script:Settings['RawFieldExportMaxPages'] -gt 0) { $maxPages = [int]$script:Settings['RawFieldExportMaxPages'] } } catch { }

    $baseUrl = Join-UrlPath ([string]$script:Settings['AllevaApiBaseUrl']) $script:TreatmentPlansPath
    $headers = Get-ApiHeaders
    $cursor = 0
    try { $cursor = [Math]::Max(0, [int]$query['Cursor']) } catch { $cursor = 0 }
    $previewLimit = [Math]::Min(100, [int]$script:Settings['ConsoleRowLimit'])

    $utf8NoBom = New-Object System.Text.UTF8Encoding -ArgumentList $false
    $fieldWriter = New-Object System.IO.StreamWriter -ArgumentList $fullFieldsPath, $false, $utf8NoBom
    $jsonlWriter = New-Object System.IO.StreamWriter -ArgumentList $rawPlansJsonlPath, $false, $utf8NoBom
    try {
        $fieldWriter.WriteLine(($columns -join "`t"))
        for ($pageIndex = 0; $pageIndex -lt $maxPages; $pageIndex++) {
            $pageQuery = @{}
            foreach ($key in $query.Keys) { $pageQuery[$key] = $query[$key] }
            $pageQuery['Limit'] = $rawLimit
            $pageQuery['Cursor'] = $cursor
            $url = Add-QueryString $baseUrl $pageQuery
            Write-Host ("GET {0} page {1}/{2} (streaming raw export, Limit={3}, Cursor={4})" -f $script:TreatmentPlansPath, ($pageIndex + 1), $maxPages, $rawLimit, $cursor) -ForegroundColor DarkGray

            $resp = Invoke-HttpRaw -Method GET -Url $url -Headers $headers -Purpose "$safeReport-page-$pageIndex"
            $callRecord = New-RemoteCallRecord -Method 'GET' -Path $script:TreatmentPlansPath -Uri $url -Query $pageQuery -Headers $headers -RequestJson $null
            $calls.Add($callRecord)
            $pageInfo = [ordered]@{
                method = 'GET'
                path = $script:TreatmentPlansPath
                uri = $url
                query = $pageQuery
                request_json = $null
                status_code = $resp.StatusCode
                ok = $resp.Ok
                duration_ms = $resp.DurationMs
                record_count = 0
                call = $callRecord
            }

            if (-not $resp.Ok) {
                $fetchError = [ordered]@{
                    endpoint = $script:TreatmentPlansPath
                    status_code = $resp.StatusCode
                    category = (Get-HttpFailureCategory $resp.StatusCode)
                    message = (Get-HttpFailureMessage $script:TreatmentPlansPath $resp.StatusCode)
                    error = $resp.Error
                    url = $url
                }
                $pages.Add([pscustomobject]$pageInfo)
                break
            }

            $payload = ConvertFrom-JsonSafe $resp.Content
            if ($null -eq $payload) {
                $fetchError = [ordered]@{
                    endpoint = $script:TreatmentPlansPath
                    status_code = $resp.StatusCode
                    category = 'endpoint_non_json_response'
                    message = "GET $script:TreatmentPlansPath responded but did not return parseable JSON."
                    error = ''
                    url = $url
                }
                $pages.Add([pscustomobject]$pageInfo)
                break
            }

            if ($writePageJson) {
                $pagePath = Join-Path $pageDir ('page-{0:0000}.json' -f ($pageIndex + 1))
                try { $resp.Content | Set-Content -LiteralPath $pagePath -Encoding UTF8 } catch { Write-Host "Could not save page JSON $pagePath : $($_.Exception.Message)" -ForegroundColor DarkYellow }
            }

            $pageRecords = @(Get-RecordsFromPayload $payload)
            $pageRecordCount = Get-SafeCount $pageRecords
            $pageInfo['record_count'] = $pageRecordCount
            $pages.Add([pscustomobject]$pageInfo)
            $recordsSeen += $pageRecordCount

            foreach ($plan in $pageRecords) {
                $planCount++
                try { $jsonlWriter.WriteLine(($plan | ConvertTo-Json -Depth 100 -Compress)) } catch { $jsonlWriter.WriteLine((ConvertTo-CompactJsonText $plan 50)) }
                # Flush the JSONL writer after every plan so the raw-plan file visibly grows
                # even while the much larger TSV field flattening for that plan/page continues.
                # This is intentionally less buffered because the JSONL is the safety copy of
                # every raw treatment-plan object.
                $jsonlWriter.Flush()
                $planRow = Get-TreatmentPlanRow $plan
                Add-FlatFieldRowsToWriter -Writer $fieldWriter -PreviewRows $previewRows -PreviewLimit $previewLimit -FieldCountRef ([ref]$fieldCount) -TreatmentPlanId ([string]$planRow.treatment_plan_id) -PatientId ([string]$planRow.patient_id) -PlanClientId ([string]$planRow.plan_client_id) -RawClientRef ([string]$planRow.raw_client_ref) -Prefix '' -Value $plan
                if (($planCount % 5) -eq 0) {
                    Write-Host ("  streamed {0} plan(s), {1} field row(s) so far; JSONL is flushed after each plan..." -f $planCount, $fieldCount) -ForegroundColor DarkGray
                    $fieldWriter.Flush()
                }
            }

            $fieldWriter.Flush(); $jsonlWriter.Flush()
            $payload = $null; $pageRecords = $null; $resp = $null
            [System.GC]::Collect()
            [System.GC]::WaitForPendingFinalizers()

            if ($pageRecordCount -lt $rawLimit) { break }
            $cursor += $rawLimit
        }
    }
    finally {
        if ($fieldWriter) { $fieldWriter.Flush(); $fieldWriter.Close(); $fieldWriter.Dispose() }
        if ($jsonlWriter) { $jsonlWriter.Flush(); $jsonlWriter.Close(); $jsonlWriter.Dispose() }
    }

    $status = if ($fetchError -and $fieldCount -eq 0) { 'fail' } elseif ($fetchError) { 'warn' } elseif ($fieldCount -eq 0) { 'warn' } else { 'ok' }
    $message = "Remote Alleva raw treatment-plan field export streamed $fieldCount field row(s) from $planCount treatment-plan record(s). Full output is in $fullFieldsPath and $rawPlansJsonlPath."
    $summary = @"
Report: all_treatment_plan_raw_fields
ScriptVersion: $script:ScriptVersion
Status: $status
Message: $message
TreatmentPlanRecords: $planCount
FieldRows: $fieldCount
FullRawFieldsTsv: $fullFieldsPath
FullRawPlansJsonl: $rawPlansJsonlPath
PageJsonDirectory: $(if ($writePageJson) { $pageDir } else { '<disabled>' })
CallCount: $($calls.Count)
PHIWarning: These outputs may contain PHI. Keep local and access-controlled.
"@
    Set-Content -LiteralPath $streamSummaryPath -Value $summary -Encoding UTF8

    return [pscustomobject]@{
        status = $status
        message = $message
        report = 'all_treatment_plan_raw_fields'
        source_operation = 'GET /treatment-plans + streaming raw field flattening to disk'
        returned_count = $fieldCount
        total_records_seen = $recordsSeen
        treatment_plan_record_count = $planCount
        rows = @($previewRows.ToArray())
        columns = $columns
        fetch_error = $fetchError
        output_files = [ordered]@{
            full_raw_fields_tsv = $fullFieldsPath
            full_raw_plans_jsonl = $rawPlansJsonlPath
            stream_summary = $streamSummaryPath
            page_json_directory = $(if ($writePageJson) { $pageDir } else { '' })
        }
        calls = @($calls.ToArray())
        collections = @{ treatment_plans = [pscustomobject]@{ label='treatment-plans-raw-fields-stream'; path=$script:TreatmentPlansPath; record_count=$recordsSeen; pages=@($pages.ToArray()); calls=@($calls.ToArray()); fetch_error=$fetchError } }
    }
}

function Invoke-CountsSummary {
    param([string]$OptionalPatientId = '')
    if ([string]::IsNullOrWhiteSpace($OptionalPatientId)) {
        $OptionalPatientId = Read-Host 'Optional Patient / Client ID for single-patient counts (Enter to skip)'
    }
    $clientsCollection = Invoke-AllevaCollection -Path $script:ClientsPath -Query (Get-BaseQuery) -Label 'clients-counts'
    $plansCollection = Invoke-AllevaCollection -Path $script:TreatmentPlansPath -Query (Get-BaseQuery -ForTreatmentPlans) -Label 'treatment-plans-counts'
    $reviewsCollection = Invoke-AllevaCollection -Path $script:TreatmentReviewsPath -Query (Get-BaseQuery) -Label 'treatment-reviews-counts'

    $patientRows = @()
    foreach ($record in (ConvertTo-ObjectArraySafe $clientsCollection.records)) { $patientRows += [pscustomobject](Get-PatientRow $record) }
    $activePatients = @($patientRows | Where-Object { $_.status_scope -eq 'active' })
    $inactivePatients = @($patientRows | Where-Object { $_.status_scope -ne 'active' })

    $planRows = @()
    foreach ($record in (ConvertTo-ObjectArraySafe $plansCollection.records)) { $planRows += [pscustomobject](Get-TreatmentPlanRow $record) }
    $activePlans = @($planRows | Where-Object { $_.is_active })
    $inactivePlans = @($planRows | Where-Object { -not $_.is_active })

    $clientCallText = Get-CallMadeText $clientsCollection.calls
    $planCallText = Get-CallMadeText $plansCollection.calls
    $reviewCallText = Get-CallMadeText $reviewsCollection.calls

    $rows = New-Object System.Collections.Generic.List[object]
    Add-CountRow $rows '2' 'all_patient_records' (Get-SafeCount $patientRows) 'rows from GET /clients' $clientCallText
    Add-CountRow $rows '3' 'active_patients' (Get-SafeCount $activePatients) 'GET /clients filtered by active patient status' $clientCallText
    Add-CountRow $rows '4' 'inactive_patients' (Get-SafeCount $inactivePatients) 'GET /clients filtered to non-active patient status' $clientCallText
    Add-CountRow $rows '5' 'all_treatment_plans' (Get-SafeCount $planRows) 'rows from GET /treatment-plans' $planCallText
    Add-CountRow $rows '6' 'active_treatment_plans' (Get-SafeCount $activePlans) 'GET /treatment-plans filtered by plan.isActive' $planCallText
    Add-CountRow $rows '7' 'inactive_treatment_plans' (Get-SafeCount $inactivePlans) 'GET /treatment-plans filtered to not plan.isActive' $planCallText

    if ([string]::IsNullOrWhiteSpace($OptionalPatientId)) {
        Add-CountRow $rows '8' 'single_treatment_plan' $null 'requires Patient / Client ID' $planCallText 'Skipped because no Patient / Client ID was entered.'
    } else {
        $singleLegacy = @($planRows | Where-Object { $_.plan_client_id -eq $OptionalPatientId -or $_.patient_id -eq $OptionalPatientId -or $_.raw_client_ref -like "*/clients/$OptionalPatientId" })
        Add-CountRow $rows '8' 'single_treatment_plan' (Get-SafeCount $singleLegacy) 'GET /treatment-plans client-reference filter' $planCallText
    }

    Add-CountRow $rows '9' 'patient_centered_treatment_plans' (Get-SafeCount $patientRows) 'patient aggregate row count from GET /clients; full report also calls GET /treatment-plans?ClientId={id} per patient' $clientCallText
    Add-CountRow $rows '10' 'active_patient_centered_treatment_plans' (Get-SafeCount $activePatients) 'active patient aggregate row count from GET /clients; full report also calls GET /treatment-plans?ClientId={id} per active patient' $clientCallText
    Add-CountRow $rows '11' 'inactive_patient_centered_treatment_plans' (Get-SafeCount $inactivePatients) 'inactive patient aggregate row count from GET /clients; full report also calls GET /treatment-plans?ClientId={id} per inactive patient' $clientCallText

    $singleClientCollection = $null
    $singlePlanCollection = $null
    if ([string]::IsNullOrWhiteSpace($OptionalPatientId)) {
        Add-CountRow $rows '12' 'single_patient_treatment_plans' $null 'requires Patient / Client ID' '' 'Skipped because no Patient / Client ID was entered.'
    } else {
        $singlePath = "$script:ClientsPath/$([uri]::EscapeDataString($OptionalPatientId))"
        $singleClientCollection = Invoke-AllevaCollection -Path $singlePath -Query (Get-BaseQuery) -MaxPages 1 -Label 'single-client-counts'
        $singlePlanQuery = Get-BaseQuery -ForTreatmentPlans
        $singlePlanQuery['ClientId'] = $OptionalPatientId
        $singlePlanCollection = Invoke-AllevaCollection -Path $script:TreatmentPlansPath -Query $singlePlanQuery -Label 'single-patient-plans-counts'
        $singleCalls = @($singleClientCollection.calls) + @($singlePlanCollection.calls)
        Add-CountRow $rows '12' 'single_patient_treatment_plans' $singlePlanCollection.record_count 'GET /clients/{id} + GET /treatment-plans?ClientId=id; count is treatment-plan records returned for that patient' (Get-CallMadeText $singleCalls)
    }

    Add-CountRow $rows '13' 'patient_treatment_plan_aggregates' (Get-SafeCount $patientRows) 'patient aggregate row count from GET /clients joined locally to direct /treatment-plans and optional /treatment-reviews' (($clientCallText,$planCallText,$reviewCallText | Where-Object { $_ }) -join '; ')
    Add-CountRow $rows '14' 'treatment_reviews' $reviewsCollection.record_count 'rows from GET /treatment-reviews' $reviewCallText
    Add-CountRow $rows '15' 'all_treatment_plan_raw_fields' (Get-SafeCount $planRows) 'treatment-plan record count from GET /treatment-plans; raw field export creates one row per field path' $planCallText

    $allCollections = @{ clients=$clientsCollection; treatment_plans=$plansCollection; treatment_reviews=$reviewsCollection; single_client=$singleClientCollection; single_patient_treatment_plans=$singlePlanCollection }
    $fetchErrors = New-Object System.Collections.Generic.List[object]
    foreach ($c in $allCollections.Values) { if ($c -and $c.fetch_error) { $fetchErrors.Add($c.fetch_error) } }
    $status = if ($fetchErrors.Count -gt 0) { 'warn' } else { 'ok' }
    return [pscustomobject]@{
        status = $status
        message = "Remote Alleva counts summary produced $($rows.Count) count row(s)."
        report = 'counts_summary'
        source_operation = 'GET /clients + GET /treatment-plans + GET /treatment-reviews + optional single-patient calls'
        returned_count = $rows.Count
        total_records_seen = $clientsCollection.record_count + $plansCollection.record_count + $reviewsCollection.record_count
        rows = @($rows)
        columns = (Get-CountSummaryColumns)
        fetch_error = if ($fetchErrors.Count) { $fetchErrors[0] } else { $null }
        fetch_errors = @($fetchErrors)
        collections = $allCollections
    }
}

function Invoke-AllPatientRecords {
    param([switch]$ActiveOnly, [switch]$InactiveOnly)
    $query = Get-BaseQuery
    $collection = Invoke-AllevaCollection -Path $script:ClientsPath -Query $query -Label 'clients'
    $rows = foreach ($record in @($collection.records)) { [pscustomobject](Get-PatientRow $record) }
    if ($ActiveOnly) { $rows = @($rows | Where-Object { $_.status_scope -eq 'active' }) }
    if ($InactiveOnly) { $rows = @($rows | Where-Object { $_.status_scope -ne 'active' }) }
    $name = if ($ActiveOnly) { 'active_patients' } elseif ($InactiveOnly) { 'inactive_patients' } else { 'all_patient_records' }
    $messageSubject = if ($ActiveOnly) { 'active patient(s)' } elseif ($InactiveOnly) { 'inactive/non-active patient(s)' } else { 'patient record(s)' }
    $status = if ($collection.fetch_error -and @($rows).Count -eq 0) { 'fail' } elseif ($collection.fetch_error) { 'warn' } elseif (@($rows).Count -eq 0) { 'warn' } else { 'ok' }
    return [pscustomobject]@{
        status = $status
        message = "Remote Alleva $messageSubject pull returned $(@($rows).Count) row(s) from $($collection.record_count) fetched /clients record(s)."
        report = $name
        source_operation = 'GET /clients'
        returned_count = @($rows).Count
        total_records_seen = $collection.record_count
        rows = @($rows)
        columns = (Get-PatientColumns)
        fetch_error = $collection.fetch_error
        collections = @{ clients = $collection }
    }
}

function Invoke-DirectTreatmentPlans {
    param([switch]$ActiveOnly, [switch]$InactiveOnly, [string]$SinglePatientId = '')
    $query = Get-BaseQuery -ForTreatmentPlans
    $collection = Invoke-AllevaCollection -Path $script:TreatmentPlansPath -Query $query -Label 'treatment-plans'
    $rows = foreach ($record in @($collection.records)) { [pscustomobject](Get-TreatmentPlanRow $record) }
    if ($ActiveOnly) { $rows = @($rows | Where-Object { $_.is_active }) }
    if ($InactiveOnly) { $rows = @($rows | Where-Object { -not $_.is_active }) }
    if ($SinglePatientId) { $rows = @($rows | Where-Object { $_.plan_client_id -eq $SinglePatientId -or $_.patient_id -eq $SinglePatientId -or $_.raw_client_ref -like "*/clients/$SinglePatientId" }) }
    $name = if ($SinglePatientId) { 'single_treatment_plan' } elseif ($ActiveOnly) { 'active_treatment_plans' } elseif ($InactiveOnly) { 'inactive_treatment_plans' } else { 'all_treatment_plans' }
    $subject = if ($SinglePatientId) { "treatment plan(s) matching patient $SinglePatientId" } elseif ($ActiveOnly) { 'active treatment plan(s)' } elseif ($InactiveOnly) { 'inactive treatment plan(s)' } else { 'treatment plan(s)' }
    $status = if ($collection.fetch_error -and @($rows).Count -eq 0) { 'fail' } elseif ($collection.fetch_error) { 'warn' } elseif (@($rows).Count -eq 0) { 'warn' } else { 'ok' }
    $filteringMode = if ($SinglePatientId) { 'client_side_by_client_reference' } else { '' }
    return [pscustomobject]@{
        status = $status
        message = "Remote Alleva direct /treatment-plans pull returned $(@($rows).Count) $subject from $($collection.record_count) fetched record(s)."
        report = $name
        source_operation = 'GET /treatment-plans'
        returned_count = @($rows).Count
        total_records_seen = $collection.record_count
        rows = @($rows)
        columns = (Get-PlanColumns)
        fetch_error = $collection.fetch_error
        collections = @{ treatment_plans = $collection }
        filtering_mode = $filteringMode
    }
}

function Invoke-Reviews {
    $query = Get-BaseQuery
    $collection = Invoke-AllevaCollection -Path $script:TreatmentReviewsPath -Query $query -Label 'treatment-reviews'
    $rows = New-Object System.Collections.Generic.List[object]
    foreach ($record in @($collection.records)) {
        $createdValue = $null
        if ($record.PSObject.Properties.Name -contains 'createdDate') { $createdValue = $record.createdDate }
        $lastModifiedValue = $null
        if ($record.PSObject.Properties.Name -contains 'lastModified') { $lastModifiedValue = $record.lastModified }
        $nextReviewValue = $null
        if ($record.PSObject.Properties.Name -contains 'nextReviewDue') { $nextReviewValue = $record.nextReviewDue }
        elseif ($record.PSObject.Properties.Name -contains 'nextReviewDueDate') { $nextReviewValue = $record.nextReviewDueDate }
        $isCompleteValue = $false
        if ($record.PSObject.Properties.Name -contains 'isComplete') { $isCompleteValue = $record.isComplete }
        $isActiveValue = $false
        if ($record.PSObject.Properties.Name -contains 'isActive') { $isActiveValue = $record.isActive }
        $rows.Add([pscustomobject]([ordered]@{
            id = (First-Text $record @('id'))
            treatmentPlanReviewId = (First-Text $record @('treatmentPlanReviewId'))
            treatmentPlanId = (First-Text $record @('treatmentPlanId'))
            clientId = (First-Text $record @('clientId','patientId','leadId'))
            createdDate = (Date-Text $createdValue)
            lastModified = (Date-Text $lastModifiedValue)
            nextReviewDue = (Date-Text $nextReviewValue)
            isComplete = (Bool-Value $isCompleteValue -Default $false)
            isActive = (Bool-Value $isActiveValue -Default $false)
        }))
    }
    $status = if ($collection.fetch_error -and $rows.Count -eq 0) { 'fail' } elseif ($collection.fetch_error) { 'warn' } elseif ($rows.Count -eq 0) { 'warn' } else { 'ok' }
    return [pscustomobject]@{
        status = $status
        message = "Remote Alleva /treatment-reviews pull returned $($rows.Count) row(s) from $($collection.record_count) fetched record(s)."
        report = 'treatment_reviews'
        source_operation = 'GET /treatment-reviews'
        returned_count = $rows.Count
        total_records_seen = $collection.record_count
        rows = @($rows)
        columns = (Get-ReviewColumns)
        fetch_error = $collection.fetch_error
        collections = @{ treatment_reviews = $collection }
    }
}

function Invoke-PatientCenteredTreatmentPlans {
    param(
        [ValidateSet('all','active','inactive','single')][string]$Selection,
        [string]$SinglePatientId = ''
    )
    if ($Selection -eq 'single' -and [string]::IsNullOrWhiteSpace($SinglePatientId)) { throw 'Patient ID is required for single_patient_treatment_plans.' }
    $clientQuery = Get-BaseQuery
    $clientFetchError = $null
    if ($Selection -eq 'single') {
        $path = "$script:ClientsPath/$([uri]::EscapeDataString($SinglePatientId))"
        $clientCollection = Invoke-AllevaCollection -Path $path -Query $clientQuery -MaxPages 1 -Label 'client-detail'
        $clients = @(ConvertTo-ObjectArraySafe $clientCollection.records)
        if ((Get-SafeCount $clients) -eq 0) {
            $fallback = [pscustomobject]@{ id = $SinglePatientId; status = @{ id=''; name='' } }
            $clients = @($fallback)
        }
        $clientFetchError = $clientCollection.fetch_error
    } else {
        $clientCollection = Invoke-AllevaCollection -Path $script:ClientsPath -Query $clientQuery -Label 'clients'
        $clients = @(ConvertTo-ObjectArraySafe $clientCollection.records)
        $clientFetchError = $clientCollection.fetch_error
    }

    $selectedClients = @()
    foreach ($client in $clients) {
        $row = Get-PatientRow $client
        if ($Selection -eq 'active' -and $row.status_scope -ne 'active') { continue }
        if ($Selection -eq 'inactive' -and $row.status_scope -eq 'active') { continue }
        $selectedClients += $client
    }

    $maxFetches = [int]$script:Settings['MaxPatientPlanFetches']
    if ($maxFetches -gt 0 -and (Get-SafeCount $selectedClients) -gt $maxFetches) {
        Write-Host "Limiting patient-centered plan fetches to first $maxFetches selected patients by settings." -ForegroundColor DarkYellow
        $selectedClients = @($selectedClients | Select-Object -First $maxFetches)
    }

    $aggregates = New-Object System.Collections.Generic.List[object]
    $fetchErrors = New-Object System.Collections.Generic.List[object]
    if ($clientFetchError) { $fetchErrors.Add($clientFetchError) }
    $recordsSeen = Get-SafeCount $clients
    $index = 0
    foreach ($client in $selectedClients) {
        $index++
        $patientRow = Get-PatientRow $client
        $patientId = [string]$patientRow.patient_id
        if (-not $patientId) { continue }
        Write-Host ("Patient-centered plan fetch {0}/{1}: /treatment-plans?ClientId={2}" -f $index, (Get-SafeCount $selectedClients), $patientId) -ForegroundColor DarkGray
        $planQuery = Get-BaseQuery -ForTreatmentPlans
        $planQuery['ClientId'] = $patientId
        $planCollection = Invoke-AllevaCollection -Path $script:TreatmentPlansPath -Query $planQuery -Label "plans-$patientId"
        $recordsSeen += $planCollection.record_count
        if ($planCollection.fetch_error) { $fetchErrors.Add($planCollection.fetch_error) }
        $aggregates.Add([pscustomobject](New-PatientAggregate -Patient $client -Plans @($planCollection.records)))
    }

    $name = switch ($Selection) {
        'active' { 'active_patient_centered_treatment_plans' }
        'inactive' { 'inactive_patient_centered_treatment_plans' }
        'single' { 'single_patient_treatment_plans' }
        default { 'patient_centered_treatment_plans' }
    }
    $status = 'ok'
    if ($fetchErrors.Count -gt 0 -and $aggregates.Count -eq 0) { $status = 'fail' }
    elseif ($fetchErrors.Count -gt 0 -or $aggregates.Count -eq 0) { $status = 'warn' }

    $firstFetchError = if ($fetchErrors.Count) { $fetchErrors[0] } else { $null }
    return [pscustomobject]@{
        status = $status
        message = "Remote Alleva patient-centered treatment-plan pull built $($aggregates.Count) aggregate row(s) from $recordsSeen fetched record(s) using GET /clients + GET /treatment-plans?ClientId={patient_id}."
        report = $name
        source_operation = 'GET /clients + GET /treatment-plans?ClientId={patient_id}'
        returned_count = $aggregates.Count
        total_records_seen = $recordsSeen
        rows = @($aggregates)
        columns = (Get-AggregateColumns)
        fetch_error = $firstFetchError
        fetch_errors = @($fetchErrors)
        patient_selection = $Selection
        client_query_parameter = 'ClientId'
        filtering_mode = 'server_side_ClientId_query'
    }
}

function Invoke-AggregateDryRun {
    $clientsCollection = Invoke-AllevaCollection -Path $script:ClientsPath -Query (Get-BaseQuery) -Label 'clients'
    $plansCollection = Invoke-AllevaCollection -Path $script:TreatmentPlansPath -Query (Get-BaseQuery -ForTreatmentPlans) -Label 'treatment-plans'
    $reviewsCollection = $null
    if (Get-SettingBool 'IncludeTreatmentReviewAggregate') {
        $reviewsCollection = Invoke-AllevaCollection -Path $script:TreatmentReviewsPath -Query (Get-BaseQuery) -Label 'treatment-reviews'
    }
    $plansByPatient = @{}
    foreach ($plan in @($plansCollection.records)) {
        $row = Get-TreatmentPlanRow $plan
        $planPatientKey = [string]$row.plan_client_id
        if (-not $planPatientKey) { $planPatientKey = [string]$row.patient_id }
        if (-not $planPatientKey) { continue }
        if (-not $plansByPatient.ContainsKey($planPatientKey)) { $plansByPatient[$planPatientKey] = New-Object System.Collections.Generic.List[object] }
        $plansByPatient[$planPatientKey].Add($plan)
    }
    $aggregates = New-Object System.Collections.Generic.List[object]
    foreach ($client in @($clientsCollection.records)) {
        $patientId = Get-PatientId $client
        $plans = @()
        if ($patientId -and $plansByPatient.ContainsKey($patientId)) { $plans = @($plansByPatient[$patientId]) }
        $aggregates.Add([pscustomobject](New-PatientAggregate -Patient $client -Plans $plans))
    }
    $fetchErrors = New-Object System.Collections.Generic.List[object]
    foreach ($e in @($clientsCollection.fetch_error, $plansCollection.fetch_error)) { if ($e) { $fetchErrors.Add($e) } }
    if ($reviewsCollection -and $reviewsCollection.fetch_error) { $fetchErrors.Add($reviewsCollection.fetch_error) }
    $recordsSeen = $clientsCollection.record_count + $plansCollection.record_count
    if ($reviewsCollection) { $recordsSeen += $reviewsCollection.record_count }
    $status = if ($fetchErrors.Count -and $aggregates.Count -eq 0) { 'fail' } elseif ($fetchErrors.Count -or $aggregates.Count -eq 0) { 'warn' } else { 'ok' }
    $firstFetchError = if ($fetchErrors.Count) { $fetchErrors[0] } else { $null }
    return [pscustomobject]@{
        status = $status
        message = "Remote Alleva aggregate dry-run built $($aggregates.Count) patient aggregate row(s) from $recordsSeen fetched record(s)."
        report = 'patient_treatment_plan_aggregates'
        source_operation = 'GET /clients + GET /treatment-plans + optional GET /treatment-reviews'
        returned_count = $aggregates.Count
        total_records_seen = $recordsSeen
        rows = @($aggregates)
        columns = (Get-AggregateColumns)
        fetch_error = $firstFetchError
        fetch_errors = @($fetchErrors)
        collections = @{ clients=$clientsCollection; treatment_plans=$plansCollection; treatment_reviews=$reviewsCollection }
    }
}

function Save-RawCollectionsIfEnabled {
    param([string]$ReportName, $Result)
    if (-not (Get-SettingBool 'WriteRawCollectionJson')) { return }
    if (-not ($Result.PSObject.Properties.Name -contains 'collections')) { return }
    Ensure-LogDirectory
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    foreach ($entry in (Get-CollectionEntriesFromResult $Result)) {
        if ($null -eq $entry.value) { continue }
        $safeName = ([string]$entry.name) -replace '[^a-zA-Z0-9._-]', '_'
        $path = Join-Path $LogDirectory "$stamp-$ReportName-raw-$safeName.json"
        ($entry.value | ConvertTo-Json -Depth 100) | Set-Content -LiteralPath $path -Encoding UTF8
        Write-Host "Saved raw collection diagnostic: $path" -ForegroundColor DarkYellow
    }
}

function Invoke-Report {
    param([Parameter(Mandatory=$true)][string]$ReportName, [string]$ReportPatientId = '')
    Import-Settings
    Write-Section "Standalone remote Alleva report: $ReportName"
    Write-Reminder
    $result = $null
    switch ($ReportName) {
        'all_patient_records' { $result = Invoke-AllPatientRecords }
        'active_patients' { $result = Invoke-AllPatientRecords -ActiveOnly }
        'inactive_patients' { $result = Invoke-AllPatientRecords -InactiveOnly }
        'all_treatment_plans' { $result = Invoke-DirectTreatmentPlans }
        'active_treatment_plans' { $result = Invoke-DirectTreatmentPlans -ActiveOnly }
        'inactive_treatment_plans' { $result = Invoke-DirectTreatmentPlans -InactiveOnly }
        'single_treatment_plan' { if (-not $ReportPatientId) { $ReportPatientId = Read-Host 'Patient / Client ID' }; $result = Invoke-DirectTreatmentPlans -SinglePatientId $ReportPatientId }
        'patient_centered_treatment_plans' { $result = Invoke-PatientCenteredTreatmentPlans -Selection all }
        'active_patient_centered_treatment_plans' { $result = Invoke-PatientCenteredTreatmentPlans -Selection active }
        'inactive_patient_centered_treatment_plans' { $result = Invoke-PatientCenteredTreatmentPlans -Selection inactive }
        'single_patient_treatment_plans' { if (-not $ReportPatientId) { $ReportPatientId = Read-Host 'Patient / Client ID' }; $result = Invoke-PatientCenteredTreatmentPlans -Selection single -SinglePatientId $ReportPatientId }
        'patient_treatment_plan_aggregates' { $result = Invoke-AggregateDryRun }
        'treatment_reviews' { $result = Invoke-Reviews }
        'all_treatment_plan_raw_fields' { $result = Invoke-RawTreatmentPlanFieldExport }
        'counts_summary' { $result = Invoke-CountsSummary -OptionalPatientId $ReportPatientId }
        default { throw "Unsupported report: $ReportName" }
    }
    $script:LastResult = $result
    Write-Subsection 'Result summary'
    $color = if ($result.status -eq 'ok') { 'Green' } elseif ($result.status -eq 'warn') { 'DarkYellow' } else { 'Red' }
    Write-Host "Status:          $($result.status)" -ForegroundColor $color
    Write-Host "Message:         $($result.message)"
    Write-Host "SourceOperation: $($result.source_operation)"
    Write-Host "ReturnedCount:   $($result.returned_count)"
    Write-Host "RecordsSeen:     $($result.total_records_seen)"
    $resultCalls = @(Get-CallsFromResult $result)
    if ((Get-SafeCount $resultCalls) -gt 0) {
        Write-Host 'Call(s):' -ForegroundColor DarkGray
        foreach ($call in ($resultCalls | Select-Object -First 8)) { Write-Host ("  {0} {1} request_json={2}" -f $call.method, $call.uri, $call.request_json_text) -ForegroundColor DarkGray }
        if ((Get-SafeCount $resultCalls) -gt 8) { Write-Host ("  ... {0} more call(s) saved to output files" -f ((Get-SafeCount $resultCalls) - 8)) -ForegroundColor DarkGray }
    }
    if ($result.fetch_error) { Write-Host "FetchError:      $($result.fetch_error.message)" -ForegroundColor DarkYellow }
    Write-Subsection 'Delimited preview'
    Write-RowsTable -Rows @($result.rows) -Columns @($result.columns)
    Save-RunOutput -ReportName $ReportName -Result $result -Rows @($result.rows) -Columns @($result.columns)
    Save-RawCollectionsIfEnabled -ReportName $ReportName -Result $result
    return $result
}

function Invoke-RecommendedBatch {
    foreach ($name in @('all_patient_records','active_patients','all_treatment_plans','active_treatment_plans','inactive_treatment_plans','active_patient_centered_treatment_plans','inactive_patient_centered_treatment_plans')) {
        try { [void](Invoke-Report -ReportName $name) }
        catch { Write-Host "Batch report $name failed: $($_.Exception.Message)" -ForegroundColor Red }
    }
}

function Test-RemoteConnectivity {
    Import-Settings
    Write-Section 'Remote Alleva connectivity check'
    Write-Host 'Checking token flow and OpenAPI URL reference. This does not call the local app.' -ForegroundColor DarkGray
    [void](Ensure-AccessToken)
    $headers = @{ Accept='application/json' }
    $url = [string]$script:Settings['AllevaOpenApiUrl']
    if ($url) {
        $resp = Invoke-HttpRaw -Method GET -Url $url -Headers $headers -Purpose 'openapi-reference'
        Write-Host "OpenAPI reference: HTTP $($resp.StatusCode), $($resp.DurationMs) ms, $url"
    }
}

function Show-Help {
    Write-Section 'Standalone remote Alleva diagnostic help'
    Write-Host @'
Purpose:
  Bypass the IZ Clinical Notes Analyzer app and call Alleva directly, while preserving
  the same treatment-plan retrieval assumptions used by the app.

Core remote calls:
  GET /clients
  GET /treatment-plans
  GET /treatment-plans?ClientId={patient_id}
  Optional: GET /treatment-reviews

Important report distinction:
  active_treatment_plans / inactive_treatment_plans look at plan.isActive from GET /treatment-plans.
  active_patient_centered_treatment_plans / inactive_patient_centered_treatment_plans first classify
  patients from GET /clients, then pull each selected patient's plans with ClientId.

Patient status logic:
  Active: status.id == 1049 or status label == Active.
  Discharged/non-active: status.id == 1356 or status label looks discharged/closed/deceased/inactive.

Outputs:
  TSV is intended for Excel or readable command-line review.
  JSON keeps the nested diagnostic detail.
  Every report also writes a calls TSV/JSON showing method, full URI, headers with credentials redacted, and request_json.
  GET calls have request_json=null because no JSON body is sent.
  The raw treatment-plan field export writes one delimited row per treatment-plan field path.

Security:
  The saved Alleva client secret is protected with Windows DPAPI for the current Windows user.
  Output files may contain PHI and should stay local.
'@
}

function Start-Menu {
    Import-Settings
    while ($true) {
        Write-Section 'R3 Standalone Remote Alleva Diagnostics'
        Write-Host "Version: $script:ScriptVersion" -ForegroundColor DarkGray
        Write-Host 'This bypasses the app. It calls Alleva remote REST endpoints directly.' -ForegroundColor Green
        Write-Host ''
        Write-Host '1.  Remote connectivity/token check'
        Write-Host '2.  Pull ALL patient records              GET /clients'
        Write-Host '3.  Pull ACTIVE patients only             GET /clients + active status filter'
        Write-Host '4.  Pull INACTIVE/NON-ACTIVE patients     GET /clients + non-active status filter'
        Write-Host '5.  Pull ALL treatment plans              GET /treatment-plans'
        Write-Host '6.  Pull ACTIVE treatment plans           GET /treatment-plans + plan.isActive filter'
        Write-Host '7.  Pull INACTIVE treatment plans         GET /treatment-plans + not plan.isActive filter'
        Write-Host '8.  Pull SINGLE treatment plan legacy     GET /treatment-plans + client-reference filter'
        Write-Host '9.  Pull ALL patient-centered TPs         GET /clients + GET /treatment-plans?ClientId=id'
        Write-Host '10. Pull ACTIVE-patient treatment plans   patient-centered active patients'
        Write-Host '11. Pull INACTIVE-patient treatment plans patient-centered non-active patients'
        Write-Host '12. Pull SINGLE-patient production TPs    GET /clients/{id} + GET /treatment-plans?ClientId=id'
        Write-Host '13. Patient TP aggregate dry-run          GET /clients + /treatment-plans + optional /treatment-reviews'
        Write-Host '14. Pull treatment reviews                GET /treatment-reviews'
        Write-Host '15. Pull ALL treatment-plan raw fields  GET /treatment-plans + full field flattening'
        Write-Host '16. Show counts for every report        one-screen counts + exact calls'
        Write-Host '17. Run recommended batch'
        Write-Host '18. Show current settings'
        Write-Host '19. Edit persistent remote settings'
        Write-Host '20. Help / report differences'
        Write-Host '0.  Exit'
        $choice = Read-Host 'Choose an option'
        try {
            switch ($choice) {
                '1' { Test-RemoteConnectivity }
                '2' { [void](Invoke-Report -ReportName 'all_patient_records') }
                '3' { [void](Invoke-Report -ReportName 'active_patients') }
                '4' { [void](Invoke-Report -ReportName 'inactive_patients') }
                '5' { [void](Invoke-Report -ReportName 'all_treatment_plans') }
                '6' { [void](Invoke-Report -ReportName 'active_treatment_plans') }
                '7' { [void](Invoke-Report -ReportName 'inactive_treatment_plans') }
                '8' { $patientKey = Read-Host 'Patient / Client ID'; [void](Invoke-Report -ReportName 'single_treatment_plan' -ReportPatientId $patientKey) }
                '9' { [void](Invoke-Report -ReportName 'patient_centered_treatment_plans') }
                '10' { [void](Invoke-Report -ReportName 'active_patient_centered_treatment_plans') }
                '11' { [void](Invoke-Report -ReportName 'inactive_patient_centered_treatment_plans') }
                '12' { $patientKey = Read-Host 'Patient / Client ID'; [void](Invoke-Report -ReportName 'single_patient_treatment_plans' -ReportPatientId $patientKey) }
                '13' { [void](Invoke-Report -ReportName 'patient_treatment_plan_aggregates') }
                '14' { [void](Invoke-Report -ReportName 'treatment_reviews') }
                '15' { [void](Invoke-Report -ReportName 'all_treatment_plan_raw_fields') }
                '16' { $countPatientKey = Read-Host 'Optional Patient / Client ID for single-patient counts (Enter to skip)'; [void](Invoke-Report -ReportName 'counts_summary' -ReportPatientId $countPatientKey) }
                '17' { Invoke-RecommendedBatch }
                '18' { Show-Settings }
                '19' { Edit-SettingsMenu }
                '20' { Show-Help }
                '0' { return }
                default { Write-Host 'Choose 0 through 20.' -ForegroundColor DarkYellow }
            }
        } catch {
            Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
        }
        Write-Host ''
        $null = Read-Host 'Press Enter to continue'
    }
}

Import-Settings

if ($RunRecommendedBatch) {
    Invoke-RecommendedBatch
    if ($OpenLogsAfterRun -and (Test-Path -LiteralPath $LogDirectory)) { Invoke-Item $LogDirectory }
    return
}

if (-not [string]::IsNullOrWhiteSpace($Report)) {
    [void](Invoke-Report -ReportName $Report -ReportPatientId $PatientId)
    if ($OpenLogsAfterRun -and (Test-Path -LiteralPath $LogDirectory)) { Invoke-Item $LogDirectory }
    return
}

if ($NoMenu) {
    Show-Help
    return
}

Start-Menu
