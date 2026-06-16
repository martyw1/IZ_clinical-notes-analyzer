<#
.VERSION
  REBUILT-2026-06-15-v3

.SYNOPSIS
  Alleva API diagnostic tester for Windows PowerShell 5.1 and PowerShell 7+.

.DESCRIPTION
  This script is intentionally built for diagnostics. By default, it prints and saves
  full tokens, secrets, Authorization headers, request bodies, and response bodies.

  Use -RedactSensitive when you need shareable logs. Do not use real PHI in test payloads.

  Main fixes in this rebuild:
  - Token/auth values are NOT redacted by default.
  - TokenAuthStyle supports Body, Basic, BasicUrlEncoded, Both, and All.
  - GET/HEAD/OPTIONS requests do not send a Body or Content-Type unless a body is actually required.
  - PowerShell 7+ uses -SkipHttpErrorCheck when available so HTTP 400/401/403 responses are captured.
  - Windows PowerShell 5.1 falls back to reading the error response stream.
  - Settings can be edited and saved to .\.alleva.local.ps1.
  - Mode Call lets you pick a discovered OpenAPI endpoint, a local provider endpoint list, or manual entry.

.EXAMPLES
  .\Test-AllevaApi.ps1 -Mode Version
  .\Test-AllevaApi.ps1 -Mode SetSettings
  .\Test-AllevaApi.ps1 -Mode Token -TokenAuthStyle All -SaveLogs
  .\Test-AllevaApi.ps1 -Mode Call
  .\Test-AllevaApi.ps1 -Mode Token -TokenAuthStyle All -RedactSensitive -SaveLogs
#>

[CmdletBinding()]
param(
    [ValidateSet('Interactive','Version','ShowSettings','SetSettings','Token','Discover','ListEndpoints','Call','SmokeTestGet','HelpCodes')]
    [string]$Mode = 'Interactive',

    [string]$ClientId = '',
    [string]$ClientSecret = '',
    [string]$BearerToken = '',
    [string]$ApiKey = '',

    [string]$TokenUrl = '',
    [string]$ApiBaseUrl = '',
    [string]$SwaggerJsonUrl = '',
    [string]$Scope = '',

    [ValidateSet('Body','Basic','BasicUrlEncoded','Both','All')]
    [string]$TokenAuthStyle = 'Body',

    [ValidateSet('GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS')]
    [string]$Method = 'GET',

    [string]$Path = '',
    [string]$QueryString = '',
    [string]$BodyJson = '',
    [switch]$AllowUnsafeMethods,

    # Default is full diagnostic output. Use -RedactSensitive to hide tokens/secrets.
    [switch]$RedactSensitive,

    # Backward-compatible switches. ShowSensitive is accepted but not needed because output is unredacted by default.
    [switch]$ShowSensitive,
    [switch]$NoRedaction,
    [switch]$ShowHeaders,
    [switch]$HideHeaders,

    [switch]$SaveLogs,
    [string]$LogDirectory = '.\alleva-api-test-logs',
    [int]$TimeoutSec = 60,

    [string]$SettingsPath = '.\.alleva.local.ps1',
    [string]$EndpointsCsvPath = '.\.alleva.endpoints.csv',
    [switch]$NoLocalSettings,

    [int]$SmokeTestLimit = 25,
    [string]$SmokeTestPathContains = ''
)

$script:ScriptVersion = 'REBUILT-2026-06-15-v3'
$ErrorActionPreference = 'Stop'

try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

$script:ClientIdValue = ''
$script:ClientSecretValue = ''
$script:BearerTokenValue = ''
$script:ApiKeyValue = ''
$script:TokenUrlValue = 'https://authorization.allevasoft.com/connect/token'
$script:ApiBaseUrlValue = 'https://api.allevasoft.com'
$script:SwaggerJsonUrlValue = ''
$script:ScopeValue = ''
$script:TokenAuthStyleValue = 'Body'
$script:AccessToken = $null
$script:TokenExpiresAtUtc = [datetime]::MinValue
$script:OpenApiSpec = $null
$script:OpenApiSourceUrl = $null

function Write-Section {
    param([string]$Title)
    Write-Host ''
    Write-Host ('=' * 78) -ForegroundColor DarkGray
    Write-Host $Title -ForegroundColor Cyan
    Write-Host ('=' * 78) -ForegroundColor DarkGray
}

function Write-Subsection {
    param([string]$Title)
    Write-Host ''
    Write-Host $Title -ForegroundColor Yellow
    Write-Host ('-' * $Title.Length) -ForegroundColor DarkGray
}

function Test-ShouldShowHeaders {
    if ($HideHeaders) { return $false }
    return $true
}

function Read-PlainSecret {
    param([string]$Prompt)
    $secure = Read-Host -Prompt $Prompt -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally {
        if ($bstr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    }
}

function ConvertTo-SingleQuotedPowerShellString {
    param([AllowNull()][string]$Value)
    if ($null -eq $Value) { $Value = '' }
    return "'" + ([string]$Value).Replace("'", "''") + "'"
}

function Get-FirstNonBlank {
    param([AllowNull()][string]$A, [AllowNull()][string]$B, [AllowNull()][string]$C)
    if (-not [string]::IsNullOrWhiteSpace($A)) { return $A }
    if (-not [string]::IsNullOrWhiteSpace($B)) { return $B }
    if (-not [string]::IsNullOrWhiteSpace($C)) { return $C }
    return ''
}

function Import-LocalSettings {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return }
    if (-not (Test-Path -LiteralPath $Path)) { return }

    Write-Host "Loading local Alleva settings from $Path" -ForegroundColor DarkGray
    $allowed = @{
        'ALLEVA_CLIENT_ID' = $true
        'ALLEVA_CLIENT_SECRET' = $true
        'ALLEVA_API_BEARER_TOKEN' = $true
        'ALLEVA_API_KEY' = $true
        'ALLEVA_TOKEN_URL' = $true
        'ALLEVA_API_BASE_URL' = $true
        'ALLEVA_SWAGGER_JSON_URL' = $true
        'ALLEVA_API_SCOPE' = $true
        'ALLEVA_TOKEN_AUTH_STYLE' = $true
    }

    foreach ($line in (Get-Content -LiteralPath $Path -ErrorAction Stop)) {
        $s = [string]$line
        if ($s -match '^\s*(#|$)') { continue }

        $m = [regex]::Match($s, '^\s*\$env:([A-Za-z0-9_]+)\s*=\s*''((?:''''|[^''])*)''\s*$')
        if ($m.Success) {
            $name = $m.Groups[1].Value.ToUpperInvariant()
            if ($allowed.ContainsKey($name)) {
                Set-Item -Path ("env:{0}" -f $name) -Value ($m.Groups[2].Value.Replace("''", "'"))
            }
            continue
        }

        $m = [regex]::Match($s, '^\s*\$env:([A-Za-z0-9_]+)\s*=\s*"([^"]*)"\s*$')
        if ($m.Success) {
            $name = $m.Groups[1].Value.ToUpperInvariant()
            if ($allowed.ContainsKey($name)) { Set-Item -Path ("env:{0}" -f $name) -Value $m.Groups[2].Value }
        }
    }
}

function Save-LocalSettings {
    param(
        [string]$Path,
        [string]$ClientIdToSave,
        [string]$ClientSecretToSave,
        [string]$BearerTokenToSave,
        [string]$ApiKeyToSave,
        [string]$TokenUrlToSave,
        [string]$ApiBaseUrlToSave,
        [string]$SwaggerJsonUrlToSave,
        [string]$ScopeToSave,
        [string]$TokenAuthStyleToSave
    )

    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add('# Local Alleva diagnostic settings for Test-AllevaApi.ps1')
    $lines.Add('# This file may contain secrets. Keep it local. It is gitignored by this repo.')
    $lines.Add(('$env:ALLEVA_CLIENT_ID = {0}' -f (ConvertTo-SingleQuotedPowerShellString $ClientIdToSave)))
    $lines.Add(('$env:ALLEVA_CLIENT_SECRET = {0}' -f (ConvertTo-SingleQuotedPowerShellString $ClientSecretToSave)))
    $lines.Add(('$env:ALLEVA_API_BEARER_TOKEN = {0}' -f (ConvertTo-SingleQuotedPowerShellString $BearerTokenToSave)))
    $lines.Add(('$env:ALLEVA_API_KEY = {0}' -f (ConvertTo-SingleQuotedPowerShellString $ApiKeyToSave)))
    $lines.Add(('$env:ALLEVA_TOKEN_URL = {0}' -f (ConvertTo-SingleQuotedPowerShellString $TokenUrlToSave)))
    $lines.Add(('$env:ALLEVA_API_BASE_URL = {0}' -f (ConvertTo-SingleQuotedPowerShellString $ApiBaseUrlToSave)))
    $lines.Add(('$env:ALLEVA_SWAGGER_JSON_URL = {0}' -f (ConvertTo-SingleQuotedPowerShellString $SwaggerJsonUrlToSave)))
    $lines.Add(('$env:ALLEVA_API_SCOPE = {0}' -f (ConvertTo-SingleQuotedPowerShellString $ScopeToSave)))
    $lines.Add(('$env:ALLEVA_TOKEN_AUTH_STYLE = {0}' -f (ConvertTo-SingleQuotedPowerShellString $TokenAuthStyleToSave)))

    Set-Content -LiteralPath $Path -Value $lines -Encoding UTF8
    Write-Host "Saved local settings to $Path" -ForegroundColor Green
}

function Initialize-EffectiveSettings {
    if (-not $NoLocalSettings) { Import-LocalSettings -Path $SettingsPath }

    $script:ClientIdValue = Get-FirstNonBlank $ClientId $env:ALLEVA_CLIENT_ID ''
    $script:ClientSecretValue = Get-FirstNonBlank $ClientSecret $env:ALLEVA_CLIENT_SECRET ''
    $script:BearerTokenValue = Get-FirstNonBlank $BearerToken $env:ALLEVA_API_BEARER_TOKEN ''
    $script:ApiKeyValue = Get-FirstNonBlank $ApiKey $env:ALLEVA_API_KEY ''
    $script:TokenUrlValue = Get-FirstNonBlank $TokenUrl $env:ALLEVA_TOKEN_URL 'https://authorization.allevasoft.com/connect/token'
    $script:ApiBaseUrlValue = Get-FirstNonBlank $ApiBaseUrl $env:ALLEVA_API_BASE_URL 'https://api.allevasoft.com'
    $script:SwaggerJsonUrlValue = Get-FirstNonBlank $SwaggerJsonUrl $env:ALLEVA_SWAGGER_JSON_URL ''
    $script:ScopeValue = Get-FirstNonBlank $Scope $env:ALLEVA_API_SCOPE ''

    if (-not $PSBoundParameters.ContainsKey('TokenAuthStyle') -and -not [string]::IsNullOrWhiteSpace($env:ALLEVA_TOKEN_AUTH_STYLE)) {
        if (@('Body','Basic','BasicUrlEncoded','Both','All') -contains $env:ALLEVA_TOKEN_AUTH_STYLE) {
            $script:TokenAuthStyleValue = $env:ALLEVA_TOKEN_AUTH_STYLE
        } else {
            Write-Host "Ignoring invalid ALLEVA_TOKEN_AUTH_STYLE '$env:ALLEVA_TOKEN_AUTH_STYLE'." -ForegroundColor DarkYellow
            $script:TokenAuthStyleValue = $TokenAuthStyle
        }
    } else {
        $script:TokenAuthStyleValue = $TokenAuthStyle
    }

    if (-not [string]::IsNullOrWhiteSpace($script:BearerTokenValue)) {
        $script:AccessToken = $script:BearerTokenValue
        $script:TokenExpiresAtUtc = [datetime]::MaxValue
    }
}

function Format-SensitiveText {
    param([AllowNull()][string]$Text)
    if ($null -eq $Text) { return $null }
    if (-not $RedactSensitive) { return $Text }

    $out = [string]$Text
    foreach ($value in @($script:ClientSecretValue, $script:AccessToken, $script:BearerTokenValue, $script:ApiKeyValue)) {
        if (-not [string]::IsNullOrEmpty($value)) {
            $out = $out.Replace($value, '***REDACTED***')
            $out = $out.Replace([uri]::EscapeDataString($value), '***REDACTED***')
        }
    }
    $out = [regex]::Replace($out, '(?i)("access_token"\s*:\s*")[^"]+("?)', '$1***REDACTED_ACCESS_TOKEN***$2')
    $out = [regex]::Replace($out, '(?i)("refresh_token"\s*:\s*")[^"]+("?)', '$1***REDACTED_REFRESH_TOKEN***$2')
    $out = [regex]::Replace($out, '(?i)("id_token"\s*:\s*")[^"]+("?)', '$1***REDACTED_ID_TOKEN***$2')
    $out = [regex]::Replace($out, '(?i)(Authorization\s*[:=]\s*Bearer\s+)[^\r\n]+', '$1***REDACTED_BEARER_TOKEN***')
    $out = [regex]::Replace($out, '(?i)(Authorization\s*[:=]\s*Basic\s+)[^\r\n]+', '$1***REDACTED_BASIC_TOKEN***')
    $out = [regex]::Replace($out, '(?i)(client_secret=)[^&\s]+', '$1***REDACTED_CLIENT_SECRET***')
    $out = [regex]::Replace($out, '(?i)(x-api-key\s*[:=]\s*)[^\r\n]+', '$1***REDACTED_API_KEY***')
    return $out
}

function Get-DisplayValue {
    param([AllowNull()][string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return '<not set>' }
    if (-not $RedactSensitive) { return $Value }
    if ($Value.Length -le 8) { return '***' }
    return ("{0}...{1}" -f $Value.Substring(0,4), $Value.Substring($Value.Length - 4))
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

function ConvertTo-PrettyJsonOrText {
    param([AllowNull()][string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return '' }
    try { return (($Text | ConvertFrom-Json) | ConvertTo-Json -Depth 80) }
    catch { return $Text }
}

function Get-HeadersText {
    param($Headers)
    if ($null -eq $Headers) { return '' }
    $lines = New-Object System.Collections.Generic.List[string]

    if ($Headers -is [System.Collections.IDictionary]) {
        foreach ($key in $Headers.Keys) {
            $value = $Headers[$key]
            if ($value -is [System.Collections.IEnumerable] -and -not ($value -is [string])) { $value = ($value -join ', ') }
            $lines.Add(("{0}: {1}" -f $key, $value))
        }
    } else {
        try {
            foreach ($h in $Headers) {
                if ($h.PSObject.Properties.Name -contains 'Key' -and $h.PSObject.Properties.Name -contains 'Value') {
                    $value = $h.Value
                    if ($value -is [System.Collections.IEnumerable] -and -not ($value -is [string])) { $value = ($value -join ', ') }
                    $lines.Add(("{0}: {1}" -f $h.Key, $value))
                }
            }
        } catch { $lines.Add(($Headers | Out-String)) }
    }
    return (($lines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join [Environment]::NewLine)
}

function Get-HttpStatusExplanation {
    param([int]$StatusCode)
    switch ($StatusCode) {
        200 { return 'OK: request succeeded.' }
        201 { return 'Created: request succeeded and a resource was created.' }
        202 { return 'Accepted: request accepted but processing may not be complete.' }
        204 { return 'No Content: request succeeded with no response body.' }
        301 { return 'Moved Permanently: endpoint URL changed permanently.' }
        302 { return 'Found/Redirect: endpoint redirected.' }
        307 { return 'Temporary Redirect: retry same method at Location.' }
        308 { return 'Permanent Redirect: retry same method at Location.' }
        400 { return 'Bad Request: malformed request, missing/wrong grant_type/scope/body/query, or provider validation.' }
        401 { return 'Unauthorized: missing/expired/invalid token or invalid client credentials.' }
        403 { return 'Forbidden: authenticated but not permitted for this scope/tenant/resource.' }
        404 { return 'Not Found: wrong base URL/path or missing route value.' }
        405 { return 'Method Not Allowed: endpoint exists but method is wrong.' }
        415 { return 'Unsupported Media Type: Content-Type is wrong.' }
        422 { return 'Unprocessable Entity: JSON valid but business validation failed.' }
        429 { return 'Too Many Requests: rate limited.' }
        500 { return 'Internal Server Error: provider/server-side failure.' }
        502 { return 'Bad Gateway: gateway problem.' }
        503 { return 'Service Unavailable: provider unavailable or maintenance.' }
        504 { return 'Gateway Timeout: upstream timeout.' }
        default {
            if ($StatusCode -ge 200 -and $StatusCode -lt 300) { return 'Success response.' }
            if ($StatusCode -ge 300 -and $StatusCode -lt 400) { return 'Redirect response.' }
            if ($StatusCode -ge 400 -and $StatusCode -lt 500) { return 'Client/auth/request issue.' }
            if ($StatusCode -ge 500 -and $StatusCode -lt 600) { return 'Server/gateway issue.' }
            return 'No HTTP status or non-standard status.'
        }
    }
}

function Save-DiagnosticLog {
    param([string]$Name, [string]$Content)
    if (-not $SaveLogs) { return }
    if (-not (Test-Path -LiteralPath $LogDirectory)) { New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $safeName = ($Name -replace '[^a-zA-Z0-9._-]', '_')
    $file = Join-Path $LogDirectory "$stamp-$safeName.txt"
    Set-Content -LiteralPath $file -Value (Format-SensitiveText $Content) -Encoding UTF8
    if ($RedactSensitive) { Write-Host "Saved redacted diagnostic log: $file" -ForegroundColor DarkGray }
    else { Write-Host "Saved UNREDACTED diagnostic log: $file" -ForegroundColor DarkYellow }
}

function Get-WebResponsePartsFromException {
    param($ErrorRecord)
    $status = 0
    $statusDescription = ''
    $headers = @{}
    $content = ''

    if ($ErrorRecord.ErrorDetails -and -not [string]::IsNullOrWhiteSpace($ErrorRecord.ErrorDetails.Message)) {
        $content = [string]$ErrorRecord.ErrorDetails.Message
    }

    $ex = $ErrorRecord.Exception
    if ($null -eq $ex -or $null -eq $ex.Response) {
        return [pscustomobject]@{ StatusCode=$status; StatusDescription=$statusDescription; Headers=$headers; Content=$content }
    }

    $webResp = $ex.Response
    try { $status = [int]$webResp.StatusCode } catch { }
    try { $statusDescription = [string]$webResp.StatusDescription } catch { }
    if ([string]::IsNullOrWhiteSpace($statusDescription)) { try { $statusDescription = [string]$webResp.ReasonPhrase } catch { } }
    try { if ($webResp.Headers) { $headers = $webResp.Headers } } catch { }

    try {
        if ($webResp.Content) {
            try {
                $combined = @{}
                foreach ($h in $webResp.Headers) { $combined[$h.Key] = ($h.Value -join ', ') }
                foreach ($h in $webResp.Content.Headers) { $combined[$h.Key] = ($h.Value -join ', ') }
                if ($combined.Count -gt 0) { $headers = $combined }
            } catch { }
            $body = $webResp.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            if (-not [string]::IsNullOrWhiteSpace($body)) { $content = $body }
        }
    } catch { }

    if ([string]::IsNullOrWhiteSpace($content)) {
        try {
            $stream = $webResp.GetResponseStream()
            if ($stream) {
                $reader = New-Object System.IO.StreamReader($stream)
                $content = $reader.ReadToEnd()
                $reader.Close()
            }
        } catch { }
    }

    return [pscustomobject]@{ StatusCode=$status; StatusDescription=$statusDescription; Headers=$headers; Content=$content }
}

function Invoke-HttpRaw {
    param(
        [Parameter(Mandatory=$true)][ValidateSet('GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS')][string]$HttpMethod,
        [Parameter(Mandatory=$true)][string]$Url,
        [hashtable]$Headers = @{},
        [AllowNull()][string]$Body = $null,
        [string]$ContentType = '',
        [string]$LogName = 'request'
    )

    $hasBody = ($null -ne $Body -and [string]$Body -ne '')

    Write-Subsection 'Outbound request'
    Write-Host "Method: $HttpMethod"
    Write-Host "URL:    $Url"

    $requestLog = New-Object System.Text.StringBuilder
    [void]$requestLog.AppendLine('REQUEST')
    [void]$requestLog.AppendLine("Method: $HttpMethod")
    [void]$requestLog.AppendLine("URL: $Url")

    $headersText = Get-HeadersText $Headers
    if (Test-ShouldShowHeaders) {
        Write-Host 'Headers:' -ForegroundColor DarkGray
        if ($headersText) { Write-Host (Format-SensitiveText $headersText) } else { Write-Host '<none>' }
    } else {
        Write-Host 'Headers: hidden by -HideHeaders' -ForegroundColor DarkGray
    }
    [void]$requestLog.AppendLine('Headers:')
    [void]$requestLog.AppendLine($headersText)

    if ($hasBody) {
        if ($ContentType) { Write-Host "Content-Type: $ContentType" }
        Write-Host 'Body:' -ForegroundColor DarkGray
        Write-Host (Format-SensitiveText (ConvertTo-PrettyJsonOrText $Body))
        [void]$requestLog.AppendLine("Content-Type: $ContentType")
        [void]$requestLog.AppendLine('Body:')
        [void]$requestLog.AppendLine($Body)
    } else {
        Write-Host 'Body:   <none>' -ForegroundColor DarkGray
        [void]$requestLog.AppendLine('Body: <none>')
    }

    $params = @{
        Uri = $Url
        Method = $HttpMethod
        Headers = $Headers
        TimeoutSec = $TimeoutSec
        ErrorAction = 'Stop'
    }

    $iwr = Get-Command Invoke-WebRequest -ErrorAction Stop
    if ($iwr.Parameters.ContainsKey('SkipHttpErrorCheck')) { $params['SkipHttpErrorCheck'] = $true }
    if ($iwr.Parameters.ContainsKey('UseBasicParsing')) { $params['UseBasicParsing'] = $true }

    # Critical bug fix: do NOT send Body or ContentType on GET/HEAD/OPTIONS when no body exists.
    if ($hasBody) {
        $params['Body'] = $Body
        if (-not [string]::IsNullOrWhiteSpace($ContentType)) { $params['ContentType'] = $ContentType }
    }

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $resp = Invoke-WebRequest @params
        $sw.Stop()

        $status = 0
        try { $status = [int]$resp.StatusCode } catch { }
        $statusDescription = ''
        try { $statusDescription = [string]$resp.StatusDescription } catch { }
        $content = ''
        try { $content = [string]$resp.Content } catch { }
        $responseHeadersText = Get-HeadersText $resp.Headers
        $parsed = $null
        try { if (-not [string]::IsNullOrWhiteSpace($content)) { $parsed = $content | ConvertFrom-Json } } catch { }
        $ok = ($status -ge 200 -and $status -lt 300)

        Write-Subsection 'Inbound response'
        $color = if ($ok) { 'Green' } else { 'Red' }
        Write-Host ("HTTP {0} - {1}" -f $status, (Get-HttpStatusExplanation $status)) -ForegroundColor $color
        if ($statusDescription) { Write-Host "Description: $statusDescription" }
        Write-Host ("Duration: {0} ms" -f $sw.ElapsedMilliseconds)

        if (Test-ShouldShowHeaders) {
            Write-Host 'Headers:' -ForegroundColor DarkGray
            if ($responseHeadersText) { Write-Host (Format-SensitiveText $responseHeadersText) } else { Write-Host '<none>' }
        }

        if (-not [string]::IsNullOrWhiteSpace($content)) {
            Write-Host 'Body:' -ForegroundColor DarkGray
            Write-Host (Format-SensitiveText (ConvertTo-PrettyJsonOrText $content))
        } else { Write-Host 'Body: <empty>' -ForegroundColor DarkGray }

        $fullLog = New-Object System.Text.StringBuilder
        [void]$fullLog.AppendLine($requestLog.ToString())
        [void]$fullLog.AppendLine('RESPONSE')
        [void]$fullLog.AppendLine("HTTP $status $statusDescription")
        [void]$fullLog.AppendLine("DurationMs: $($sw.ElapsedMilliseconds)")
        [void]$fullLog.AppendLine('Headers:')
        [void]$fullLog.AppendLine($responseHeadersText)
        [void]$fullLog.AppendLine('Body:')
        [void]$fullLog.AppendLine($content)
        Save-DiagnosticLog -Name $LogName -Content $fullLog.ToString()

        return [pscustomobject]@{ Ok=$ok; StatusCode=$status; StatusDescription=$statusDescription; Headers=$resp.Headers; Content=$content; ParsedJson=$parsed; DurationMs=$sw.ElapsedMilliseconds; Error=$null }
    } catch {
        $sw.Stop()
        $parts = Get-WebResponsePartsFromException -ErrorRecord $_
        $status = [int]$parts.StatusCode
        $statusDescription = [string]$parts.StatusDescription
        # Do not assign response headers to a variable named $headers here.
        # PowerShell variable names are case-insensitive, so $headers would collide with
        # the typed [hashtable]$Headers function parameter and can throw:
        # "Cannot convert System.Net.WebHeaderCollection to System.Collections.Hashtable".
        $responseHeaders = $parts.Headers
        $content = [string]$parts.Content
        $errorText = $_.Exception.Message
        $responseHeadersText = Get-HeadersText $responseHeaders
        $parsed = $null
        try { if (-not [string]::IsNullOrWhiteSpace($content)) { $parsed = $content | ConvertFrom-Json } } catch { }

        Write-Subsection 'Inbound response / error'
        if ($status -gt 0) { Write-Host ("HTTP {0} - {1}" -f $status, (Get-HttpStatusExplanation $status)) -ForegroundColor Red }
        else { Write-Host 'No HTTP status received. This is DNS/TLS/proxy/firewall/timeout or a local PowerShell request construction error.' -ForegroundColor Red }
        if ($statusDescription) { Write-Host "Description: $statusDescription" }
        Write-Host ("Duration: {0} ms" -f $sw.ElapsedMilliseconds)
        Write-Host "PowerShell error: $(Format-SensitiveText $errorText)" -ForegroundColor Red

        if (Test-ShouldShowHeaders) {
            Write-Host 'Headers:' -ForegroundColor DarkGray
            if ($responseHeadersText) { Write-Host (Format-SensitiveText $responseHeadersText) } else { Write-Host '<none>' }
        }

        if (-not [string]::IsNullOrWhiteSpace($content)) {
            Write-Host 'Body:' -ForegroundColor DarkGray
            Write-Host (Format-SensitiveText (ConvertTo-PrettyJsonOrText $content))
        } else { Write-Host 'Body: <empty or unavailable>' -ForegroundColor DarkGray }

        $fullLog = New-Object System.Text.StringBuilder
        [void]$fullLog.AppendLine($requestLog.ToString())
        [void]$fullLog.AppendLine('RESPONSE/ERROR')
        [void]$fullLog.AppendLine("HTTP $status $statusDescription")
        [void]$fullLog.AppendLine("DurationMs: $($sw.ElapsedMilliseconds)")
        [void]$fullLog.AppendLine("PowerShellError: $errorText")
        [void]$fullLog.AppendLine('Headers:')
        [void]$fullLog.AppendLine($responseHeadersText)
        [void]$fullLog.AppendLine('Body:')
        [void]$fullLog.AppendLine($content)
        Save-DiagnosticLog -Name $LogName -Content $fullLog.ToString()

        return [pscustomobject]@{ Ok=$false; StatusCode=$status; StatusDescription=$statusDescription; Headers=$responseHeaders; Content=$content; ParsedJson=$parsed; DurationMs=$sw.ElapsedMilliseconds; Error=$errorText }
    }
}

function Ensure-Credentials {
    if ([string]::IsNullOrWhiteSpace($script:ClientIdValue)) { $script:ClientIdValue = Read-Host -Prompt 'Alleva client id' }
    if ([string]::IsNullOrWhiteSpace($script:ClientSecretValue)) { $script:ClientSecretValue = Read-PlainSecret -Prompt 'Alleva client secret' }
}

function Get-BasicPairString {
    param([string]$Style)
    if ($Style -eq 'BasicUrlEncoded') {
        return ("{0}:{1}" -f [uri]::EscapeDataString($script:ClientIdValue), [uri]::EscapeDataString($script:ClientSecretValue))
    }
    return ("{0}:{1}" -f $script:ClientIdValue, $script:ClientSecretValue)
}

function Request-TokenOnce {
    param([ValidateSet('Body','Basic','BasicUrlEncoded')][string]$Style)
    Ensure-Credentials

    $headers = @{ Accept = 'application/json' }
    $form = [ordered]@{ grant_type = 'client_credentials' }

    if ($Style -eq 'Body') {
        $form['client_id'] = $script:ClientIdValue
        $form['client_secret'] = $script:ClientSecretValue
    } else {
        $pair = Get-BasicPairString -Style $Style
        $basic = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($pair))
        $headers['Authorization'] = "Basic $basic"
    }

    if (-not [string]::IsNullOrWhiteSpace($script:ScopeValue)) { $form['scope'] = $script:ScopeValue }

    $body = ConvertTo-FormUrlEncoded $form
    Write-Section "Requesting OAuth bearer token using client_credentials ($Style auth style)"
    return (Invoke-HttpRaw -HttpMethod POST -Url $script:TokenUrlValue -Headers $headers -Body $body -ContentType 'application/x-www-form-urlencoded' -LogName "token-$Style")
}

function Get-AccessToken {
    $styles = @()
    switch ($script:TokenAuthStyleValue) {
        'Body' { $styles = @('Body') }
        'Basic' { $styles = @('Basic') }
        'BasicUrlEncoded' { $styles = @('BasicUrlEncoded') }
        'Both' { $styles = @('Body','Basic') }
        'All' { $styles = @('Body','Basic','BasicUrlEncoded') }
    }

    foreach ($style in $styles) {
        $resp = Request-TokenOnce -Style $style
        if ($resp.Ok -and $resp.ParsedJson -and $resp.ParsedJson.access_token) {
            $script:AccessToken = [string]$resp.ParsedJson.access_token
            $script:BearerTokenValue = $script:AccessToken
            $expiresIn = 3600
            try { if ($resp.ParsedJson.expires_in) { $expiresIn = [int]$resp.ParsedJson.expires_in } } catch { }
            $script:TokenExpiresAtUtc = (Get-Date).ToUniversalTime().AddSeconds($expiresIn)
            Write-Host ''
            Write-Host "Token acquired successfully with $style auth style." -ForegroundColor Green
            Write-Host "Expires in: approximately $expiresIn seconds"
            Write-Host "Expires at UTC: $($script:TokenExpiresAtUtc.ToString('yyyy-MM-dd HH:mm:ss'))"
            Write-Host 'Bearer token:' -ForegroundColor DarkYellow
            Write-Host (Format-SensitiveText $script:AccessToken)
            return $true
        }
        Write-Host "Token attempt using $style style did not succeed." -ForegroundColor DarkYellow
    }

    Write-Host 'Could not acquire a token. Review the HTTP status, OAuth body, auth style, scope, and credentials.' -ForegroundColor Red
    return $false
}

function Ensure-AccessToken {
    $now = (Get-Date).ToUniversalTime()
    if ($script:AccessToken -and $script:TokenExpiresAtUtc -gt $now.AddSeconds(120)) { return $true }
    if ($script:AccessToken) { Write-Host 'Bearer token is near expiry or expired; requesting a new token.' -ForegroundColor DarkYellow }
    return (Get-AccessToken)
}

function Build-FullUrl {
    param([Parameter(Mandatory=$true)][string]$EndpointPath, [string]$Qs = '')
    if ($EndpointPath -match '^https?://') { $url = $EndpointPath }
    else {
        $base = $script:ApiBaseUrlValue.TrimEnd('/')
        $pathPart = $EndpointPath
        if (-not $pathPart.StartsWith('/')) { $pathPart = "/$pathPart" }
        $url = "$base$pathPart"
    }
    if (-not [string]::IsNullOrWhiteSpace($Qs)) {
        $cleanQs = $Qs
        if ($cleanQs.StartsWith('?')) { $cleanQs = $cleanQs.Substring(1) }
        if ($url.Contains('?')) { $url = "$url&$cleanQs" } else { $url = "$url?$cleanQs" }
    }
    return $url
}

function Invoke-ApiEndpoint {
    param(
        [Parameter(Mandatory=$true)][ValidateSet('GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS')][string]$ApiMethod,
        [Parameter(Mandatory=$true)][string]$EndpointPath,
        [string]$Qs = '',
        [string]$JsonBody = '',
        [switch]$ForceUnsafe
    )

    if (@('POST','PUT','PATCH','DELETE') -contains $ApiMethod -and -not ($AllowUnsafeMethods -or $ForceUnsafe)) {
        Write-Host "Refusing to run $ApiMethod without -AllowUnsafeMethods or interactive confirmation." -ForegroundColor Red
        return $null
    }

    if (-not (Ensure-AccessToken)) { return $null }

    $url = Build-FullUrl -EndpointPath $EndpointPath -Qs $Qs
    $headers = @{ Accept = 'application/json'; Authorization = "Bearer $script:AccessToken" }
    if (-not [string]::IsNullOrWhiteSpace($script:ApiKeyValue)) { $headers['x-api-key'] = $script:ApiKeyValue }

    $bodyToSend = $null
    $contentType = ''
    if (-not [string]::IsNullOrWhiteSpace($JsonBody)) {
        try { $null = $JsonBody | ConvertFrom-Json } catch { Write-Host "BodyJson is not valid JSON: $($_.Exception.Message)" -ForegroundColor Red; return $null }
        $bodyToSend = $JsonBody
        $contentType = 'application/json'
    }

    Write-Section 'Calling Alleva API endpoint'
    return (Invoke-HttpRaw -HttpMethod $ApiMethod -Url $url -Headers $headers -Body $bodyToSend -ContentType $contentType -LogName "api-$ApiMethod-$EndpointPath")
}

function Get-CandidateSwaggerUrls {
    $urls = New-Object System.Collections.Generic.List[string]
    if (-not [string]::IsNullOrWhiteSpace($script:SwaggerJsonUrlValue)) { $urls.Add($script:SwaggerJsonUrlValue) }
    $base = $script:ApiBaseUrlValue.TrimEnd('/')
    foreach ($u in @(
        "$base/swagger/v1/swagger.json",
        "$base/swagger/docs/v1",
        "$base/swagger/swagger.json",
        "$base/swagger.json",
        "$base/openapi.json"
    )) { $urls.Add($u) }
    return ($urls | Select-Object -Unique)
}

function Try-ParseSwaggerUrlFromUi {
    param([string]$Html)
    $found = New-Object System.Collections.Generic.List[string]
    if ([string]::IsNullOrWhiteSpace($Html)) { return $found }
    foreach ($m in [regex]::Matches($Html, '(?i)url\s*:\s*["'']([^"'']+)["'']')) { $found.Add($m.Groups[1].Value) }
    foreach ($m in [regex]::Matches($Html, '(?i)["'']url["'']\s*:\s*["'']([^"'']+)["'']')) { $found.Add($m.Groups[1].Value) }
    $base = $script:ApiBaseUrlValue.TrimEnd('/')
    $normalized = New-Object System.Collections.Generic.List[string]
    foreach ($u in ($found | Select-Object -Unique)) {
        if ($u -match '^https?://') { $normalized.Add($u) }
        elseif ($u.StartsWith('/')) { $normalized.Add("$base$u") }
        else { $normalized.Add("$base/$u") }
    }
    return ($normalized | Select-Object -Unique)
}

function Discover-OpenApiSpec {
    Write-Section 'Discovering Swagger/OpenAPI document'
    $candidates = New-Object System.Collections.Generic.List[string]
    foreach ($u in (Get-CandidateSwaggerUrls)) { $candidates.Add($u) }

    $uiUrl = "$($script:ApiBaseUrlValue.TrimEnd('/'))/swagger/index.html"
    Write-Host "Checking Swagger UI for embedded JSON URL: $uiUrl" -ForegroundColor DarkGray
    $uiResp = Invoke-HttpRaw -HttpMethod GET -Url $uiUrl -Headers @{Accept='text/html,application/json'} -LogName 'swagger-ui'
    if ($uiResp.Ok) { foreach ($u in (Try-ParseSwaggerUrlFromUi -Html $uiResp.Content)) { $candidates.Add($u) } }

    foreach ($url in ($candidates | Select-Object -Unique)) {
        Write-Host ''
        Write-Host "Trying OpenAPI candidate: $url" -ForegroundColor Cyan
        $resp = Invoke-HttpRaw -HttpMethod GET -Url $url -Headers @{Accept='application/json'} -LogName 'swagger-json'
        if ($resp.Ok -and $resp.ParsedJson -and ($resp.ParsedJson.paths -or $resp.ParsedJson.swagger -or $resp.ParsedJson.openapi)) {
            $script:OpenApiSpec = $resp.ParsedJson
            $script:OpenApiSourceUrl = $url
            Write-Host "OpenAPI/Swagger document found: $url" -ForegroundColor Green
            return $true
        }
    }

    Write-Host 'Could not auto-discover Swagger JSON.' -ForegroundColor DarkYellow
    Write-Host 'Use manual endpoint entry or ask Alleva for the exact OpenAPI/Swagger JSON URL and save it in settings.' -ForegroundColor DarkYellow
    return $false
}

function Get-EndpointRowsFromSpec {
    if ($null -eq $script:OpenApiSpec -or $null -eq $script:OpenApiSpec.paths) { return @() }
    $rows = New-Object System.Collections.Generic.List[object]
    $index = 1
    foreach ($pathName in $script:OpenApiSpec.paths.PSObject.Properties.Name) {
        $pathObj = $script:OpenApiSpec.paths.$pathName
        foreach ($methodName in @('get','post','put','patch','delete','head','options')) {
            if ($pathObj.PSObject.Properties.Name -contains $methodName) {
                $op = $pathObj.$methodName
                $requiredParams = New-Object System.Collections.Generic.List[string]
                if ($op.parameters) {
                    foreach ($p in $op.parameters) { if ($p.required -eq $true) { $requiredParams.Add(("{0}({1})" -f $p.name, $p.in)) } }
                }
                if ($op.requestBody -and $op.requestBody.required -eq $true) { $requiredParams.Add('requestBody(body)') }
                $rows.Add([pscustomobject]@{ Index=$index; Source='OpenAPI'; Method=$methodName.ToUpperInvariant(); Path=$pathName; Summary=[string]$op.summary; Required=($requiredParams -join ', ') })
                $index++
            }
        }
    }
    return $rows
}

function Get-ProviderEndpointRows {
    $rows = New-Object System.Collections.Generic.List[object]
    $index = 1

    if (Test-Path -LiteralPath $EndpointsCsvPath) {
        try {
            foreach ($row in (Import-Csv -LiteralPath $EndpointsCsvPath)) {
                if ($row.Method -and $row.Path) {
                    $rows.Add([pscustomobject]@{ Index=$index; Source='LocalCsv'; Method=([string]$row.Method).ToUpperInvariant(); Path=[string]$row.Path; Summary=[string]$row.Summary; Required=[string]$row.Required })
                    $index++
                }
            }
        } catch { Write-Host "Could not read endpoint CSV $EndpointsCsvPath : $($_.Exception.Message)" -ForegroundColor DarkYellow }
    }

    if ($rows.Count -eq 0) {
        foreach ($candidate in @(
            @{Method='GET'; Path='/api/Client'; Summary='Candidate provider endpoint from support-style examples; adjust path/query if needed'; Required=''},
            @{Method='GET'; Path='/api/Clients'; Summary='Candidate plural client endpoint; adjust if needed'; Required=''},
            @{Method='GET'; Path='/api/Patient'; Summary='Candidate patient endpoint; adjust if needed'; Required=''},
            @{Method='GET'; Path='/api/Patients'; Summary='Candidate plural patient endpoint; adjust if needed'; Required=''},
            @{Method='GET'; Path='/api/Admissions'; Summary='Candidate admissions endpoint; adjust if needed'; Required=''},
            @{Method='GET'; Path='/api/Facilities'; Summary='Candidate facilities endpoint; adjust if needed'; Required=''},
            @{Method='GET'; Path='/api/Programs'; Summary='Candidate programs endpoint; adjust if needed'; Required=''},
            @{Method='GET'; Path='/api/Users'; Summary='Candidate users endpoint; adjust if needed'; Required=''}
        )) {
            $rows.Add([pscustomobject]@{ Index=$index; Source='BuiltInCandidate'; Method=$candidate.Method; Path=$candidate.Path; Summary=$candidate.Summary; Required=$candidate.Required })
            $index++
        }
    }

    return $rows
}

function Write-SampleEndpointsCsv {
    if (Test-Path -LiteralPath $EndpointsCsvPath) { return }
    @'
Method,Path,Summary,Required
GET,/api/Client,Provider/manual endpoint candidate,
GET,/api/Clients,Provider/manual endpoint candidate,
'@ | Set-Content -LiteralPath $EndpointsCsvPath -Encoding UTF8
    Write-Host "Created sample endpoint CSV: $EndpointsCsvPath" -ForegroundColor Green
    Write-Host 'Edit it with exact endpoints from Alleva/provider support screenshots if needed.' -ForegroundColor DarkYellow
}

function Show-Endpoints {
    if ($null -eq $script:OpenApiSpec) { [void](Discover-OpenApiSpec) }
    $rows = @()
    if ($null -ne $script:OpenApiSpec) { $rows = @(Get-EndpointRowsFromSpec) }
    if ($rows.Count -eq 0) { $rows = @(Get-ProviderEndpointRows) }
    Write-Section 'Endpoints'
    if ($script:OpenApiSourceUrl) { Write-Host "OpenAPI source: $script:OpenApiSourceUrl" -ForegroundColor DarkGray }
    $rows | Format-Table Index, Source, Method, Path, Summary, Required -AutoSize
    if (-not (Test-Path -LiteralPath $EndpointsCsvPath)) { Write-Host "Tip: create $EndpointsCsvPath with Method,Path,Summary,Required to load exact provider-supplied endpoints." -ForegroundColor DarkYellow }
}

function Resolve-PathTemplateInteractively {
    param([string]$TemplatePath)
    $resolved = $TemplatePath
    $seen = @{}
    foreach ($m in [regex]::Matches($TemplatePath, '\{([^}/]+)\}')) {
        $name = $m.Groups[1].Value
        if ($seen.ContainsKey($name)) { continue }
        $seen[$name] = $true
        $value = Read-Host "Value for path parameter {$name} (for version try 1.0, not 1, if the API reports supported versions 1.0/2.0)"
        $resolved = $resolved.Replace("{$name}", [uri]::EscapeDataString($value))
    }
    return $resolved
}

function Invoke-EndpointPicker {
    Write-Section 'Call one endpoint'

    $openApiRows = @()
    if ($null -eq $script:OpenApiSpec) { [void](Discover-OpenApiSpec) }
    if ($null -ne $script:OpenApiSpec) { $openApiRows = @(Get-EndpointRowsFromSpec | Sort-Object Path, Method) }

    $rows = @()
    if ($openApiRows.Count -gt 0) { $rows = $openApiRows }
    else { $rows = @(Get-ProviderEndpointRows) }

    if ($rows.Count -gt 0) {
        Write-Host 'Choose an endpoint Index, M for manual entry, or C to create/edit local endpoint CSV.' -ForegroundColor Cyan
        $rows | Format-Table Index, Source, Method, Path, Summary, Required -AutoSize
        $choice = Read-Host 'Endpoint Index, M, or C'
    } else { $choice = 'M' }

    if ($choice -match '^[cC]$') {
        Write-SampleEndpointsCsv
        Write-Host "Open this file and add provider endpoints: $EndpointsCsvPath" -ForegroundColor Cyan
        return
    }

    $selected = $null
    if ($choice -notmatch '^[mM]$') {
        $choiceNumber = 0
        if ([int]::TryParse($choice, [ref]$choiceNumber)) { $selected = $rows | Where-Object { $_.Index -eq $choiceNumber } | Select-Object -First 1 }
        if ($null -eq $selected) { Write-Host 'Invalid endpoint index; using manual entry.' -ForegroundColor DarkYellow }
    }

    if ($null -ne $selected) {
        $m = $selected.Method
        $p = Resolve-PathTemplateInteractively -TemplatePath $selected.Path
        Write-Host ("Selected: {0} {1}" -f $m, $p) -ForegroundColor Green
    } else {
        $m = Read-Host 'HTTP method [GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS]'
        if ([string]::IsNullOrWhiteSpace($m)) { $m = 'GET' }
        $m = $m.ToUpperInvariant()
        if (@('GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS') -notcontains $m) { Write-Host 'Unsupported method.' -ForegroundColor Red; return }
        $p = Read-Host 'Endpoint path or full URL, e.g. /api/Client'
        if ([string]::IsNullOrWhiteSpace($p)) { Write-Host 'Path is required.' -ForegroundColor Red; return }
    }

    $qs = Read-Host 'Query string without ?, or leave blank. Example: page=1&pageSize=25'
    $body = ''
    if (@('POST','PUT','PATCH') -contains $m) { $body = Read-Host 'JSON body, or leave blank' }

    $forceUnsafe = $false
    if (@('POST','PUT','PATCH','DELETE') -contains $m -and -not $AllowUnsafeMethods) {
        Write-Host "$m can create, modify, or delete data." -ForegroundColor DarkYellow
        $confirm = Read-Host 'Type YES to call this endpoint anyway'
        if ($confirm -ne 'YES') { Write-Host 'Cancelled.' -ForegroundColor DarkYellow; return }
        $forceUnsafe = $true
    }

    [void](Invoke-ApiEndpoint -ApiMethod $m -EndpointPath $p -Qs $qs -JsonBody $body -ForceUnsafe:$forceUnsafe)
}

function Invoke-SafeSmokeTestGetEndpoints {
    if ($null -eq $script:OpenApiSpec) { if (-not (Discover-OpenApiSpec)) { return } }
    $rows = Get-EndpointRowsFromSpec | Where-Object { $_.Method -eq 'GET' -and [string]::IsNullOrWhiteSpace($_.Required) }
    if (-not [string]::IsNullOrWhiteSpace($SmokeTestPathContains)) { $rows = $rows | Where-Object { $_.Path -like "*$SmokeTestPathContains*" } }
    $rows = $rows | Select-Object -First $SmokeTestLimit
    if ($null -eq $rows -or @($rows).Count -eq 0) { Write-Host 'No safe GET endpoints without required parameters were found.' -ForegroundColor DarkYellow; return }
    $summary = New-Object System.Collections.Generic.List[object]
    foreach ($row in $rows) {
        $resp = Invoke-ApiEndpoint -ApiMethod GET -EndpointPath $row.Path
        $summary.Add([pscustomobject]@{ Method='GET'; Path=$row.Path; StatusCode=if($resp){$resp.StatusCode}else{0}; Ok=if($resp){$resp.Ok}else{$false}; Meaning=if($resp){Get-HttpStatusExplanation $resp.StatusCode}else{'Not attempted'} })
    }
    Write-Section 'Smoke test summary'
    $summary | Format-Table -AutoSize
}

function Show-CurrentSettings {
    Write-Section 'Current settings'
    Write-Host "Script version:         $script:ScriptVersion"
    Write-Host "PowerShell version:     $($PSVersionTable.PSVersion)"
    Write-Host "Working directory:      $(Get-Location)"
    Write-Host "SettingsPath:           $SettingsPath"
    Write-Host "EndpointsCsvPath:       $EndpointsCsvPath"
    Write-Host "TokenUrl:               $script:TokenUrlValue"
    Write-Host "ApiBaseUrl:             $script:ApiBaseUrlValue"
    Write-Host "SwaggerJsonUrl:         $script:SwaggerJsonUrlValue"
    Write-Host "Scope:                  $script:ScopeValue"
    Write-Host "TokenAuthStyle:         $script:TokenAuthStyleValue"
    Write-Host "ClientId:               $(Get-DisplayValue $script:ClientIdValue)"
    Write-Host "ClientSecret:           $(Get-DisplayValue $script:ClientSecretValue)"
    Write-Host "BearerToken:            $(Get-DisplayValue $script:BearerTokenValue)"
    Write-Host "ApiKey:                 $(Get-DisplayValue $script:ApiKeyValue)"
    Write-Host "RedactSensitive:        $RedactSensitive"
    Write-Host "HideHeaders:            $HideHeaders"
    Write-Host "SaveLogs:               $SaveLogs"
    Write-Host "LogDirectory:           $LogDirectory"
}

function Set-SettingsInteractive {
    Write-Section 'Set/update local Alleva settings'
    Write-Host 'Leave a value blank to keep the current setting.' -ForegroundColor DarkGray
    $newClientId = Read-Host "Client ID [$($script:ClientIdValue)]"
    if ([string]::IsNullOrWhiteSpace($newClientId)) { $newClientId = $script:ClientIdValue }
    $newSecret = Read-PlainSecret -Prompt 'Client SECRET [press Enter to keep current]'
    if ([string]::IsNullOrWhiteSpace($newSecret)) { $newSecret = $script:ClientSecretValue }
    $newBearerToken = Read-Host "Existing bearer token, optional [$([bool]$script:BearerTokenValue)]"
    if ([string]::IsNullOrWhiteSpace($newBearerToken)) { $newBearerToken = $script:BearerTokenValue }
    $newApiKey = Read-Host "API key, optional [$([bool]$script:ApiKeyValue)]"
    if ([string]::IsNullOrWhiteSpace($newApiKey)) { $newApiKey = $script:ApiKeyValue }
    $newTokenUrl = Read-Host "Token URL [$script:TokenUrlValue]"
    if ([string]::IsNullOrWhiteSpace($newTokenUrl)) { $newTokenUrl = $script:TokenUrlValue }
    $newApiBaseUrl = Read-Host "API base URL [$script:ApiBaseUrlValue]"
    if ([string]::IsNullOrWhiteSpace($newApiBaseUrl)) { $newApiBaseUrl = $script:ApiBaseUrlValue }
    $newSwaggerUrl = Read-Host "Swagger/OpenAPI JSON URL, optional [$script:SwaggerJsonUrlValue]"
    if ([string]::IsNullOrWhiteSpace($newSwaggerUrl)) { $newSwaggerUrl = $script:SwaggerJsonUrlValue }
    $newScope = Read-Host "Scope, optional [$script:ScopeValue]"
    if ([string]::IsNullOrWhiteSpace($newScope)) { $newScope = $script:ScopeValue }
    $newStyle = Read-Host "Token auth style [Body/Basic/BasicUrlEncoded/Both/All] [$script:TokenAuthStyleValue]"
    if ([string]::IsNullOrWhiteSpace($newStyle)) { $newStyle = $script:TokenAuthStyleValue }
    if (@('Body','Basic','BasicUrlEncoded','Both','All') -notcontains $newStyle) { Write-Host 'Invalid token auth style. Keeping prior value.' -ForegroundColor DarkYellow; $newStyle = $script:TokenAuthStyleValue }

    Save-LocalSettings -Path $SettingsPath -ClientIdToSave $newClientId -ClientSecretToSave $newSecret -BearerTokenToSave $newBearerToken -ApiKeyToSave $newApiKey -TokenUrlToSave $newTokenUrl -ApiBaseUrlToSave $newApiBaseUrl -SwaggerJsonUrlToSave $newSwaggerUrl -ScopeToSave $newScope -TokenAuthStyleToSave $newStyle
    $script:ClientIdValue = $newClientId
    $script:ClientSecretValue = $newSecret
    $script:BearerTokenValue = $newBearerToken
    $script:ApiKeyValue = $newApiKey
    $script:TokenUrlValue = $newTokenUrl
    $script:ApiBaseUrlValue = $newApiBaseUrl
    $script:SwaggerJsonUrlValue = $newSwaggerUrl
    $script:ScopeValue = $newScope
    $script:TokenAuthStyleValue = $newStyle
}

function Show-ErrorCodeGuide {
    Write-Section 'Error and Status Code Guide'
    Write-Host @'
OAuth token diagnostics:
  invalid_request         Missing/malformed form fields, wrong content type, or duplicate values.
  invalid_client          Wrong ID/secret, inactive client, or wrong client auth style.
  unauthorized_client     Client is not allowed to use client_credentials or the target API.
  invalid_scope           Scope is missing/wrong/not assigned. Try blank scope if provider says no scope is needed.
  unsupported_grant_type  grant_type must be client_credentials.

Local PowerShell diagnostics:
  "Cannot send a content-body with this verb-type" means the script sent Body/ContentType on GET/HEAD.
  This rebuilt script avoids that by only adding Body/ContentType when there is a non-empty body.
'@
}

function Start-InteractiveMenu {
    while ($true) {
        Write-Section 'Alleva API Connectivity Tester'
        Write-Host '1. Request/refresh bearer token'
        Write-Host '2. Discover Swagger/OpenAPI JSON'
        Write-Host '3. List endpoints'
        Write-Host '4. Call one endpoint from provider/OpenAPI/local list or enter manually'
        Write-Host '5. Safe smoke test: GET endpoints with no required parameters'
        Write-Host '6. Explain error/status codes'
        Write-Host '7. Show current settings'
        Write-Host '8. Set/update local ID, SECRET, URLs, scope, and auth style'
        Write-Host '9. Create sample local endpoint CSV'
        Write-Host '0. Exit'
        $choice = Read-Host 'Choose an option'
        switch ($choice) {
            '1' { [void](Get-AccessToken) }
            '2' { [void](Discover-OpenApiSpec) }
            '3' { Show-Endpoints }
            '4' { Invoke-EndpointPicker }
            '5' { Invoke-SafeSmokeTestGetEndpoints }
            '6' { Show-ErrorCodeGuide }
            '7' { Show-CurrentSettings }
            '8' { Set-SettingsInteractive }
            '9' { Write-SampleEndpointsCsv }
            '0' { return }
            default { Write-Host 'Choose 0 through 9.' -ForegroundColor DarkYellow }
        }
        Write-Host ''
        $null = Read-Host 'Press Enter to continue'
    }
}

Initialize-EffectiveSettings

Write-Host "Alleva API Connectivity Tester - $script:ScriptVersion" -ForegroundColor Cyan
if ($RedactSensitive) { Write-Host 'Redaction is ENABLED. Use without -RedactSensitive for full diagnostic output.' -ForegroundColor DarkYellow }
else { Write-Host 'Full diagnostic output is ENABLED by default. Do not share logs/screenshots containing tokens or secrets.' -ForegroundColor Red }
Write-Host 'Use only authorized test/development access and avoid PHI in test payloads.' -ForegroundColor DarkYellow

switch ($Mode) {
    'Interactive' { Start-InteractiveMenu }
    'Version' { Write-Host $script:ScriptVersion }
    'ShowSettings' { Show-CurrentSettings }
    'SetSettings' { Set-SettingsInteractive }
    'Token' { [void](Get-AccessToken) }
    'Discover' { [void](Discover-OpenApiSpec) }
    'ListEndpoints' { Show-Endpoints }
    'Call' {
        if ([string]::IsNullOrWhiteSpace($Path)) { Invoke-EndpointPicker }
        else { [void](Invoke-ApiEndpoint -ApiMethod $Method -EndpointPath $Path -Qs $QueryString -JsonBody $BodyJson) }
    }
    'SmokeTestGet' { Invoke-SafeSmokeTestGetEndpoints }
    'HelpCodes' { Show-ErrorCodeGuide }
}
