<#
.SYNOPSIS
  Alleva EMR API connectivity tester for Windows 11 PowerShell.

.DESCRIPTION
  This script tests OAuth2 client_credentials connectivity against Alleva's token endpoint,
  discovers Swagger/OpenAPI endpoints when the Swagger JSON is publicly reachable, and lets
  you safely call endpoints from a PowerShell terminal.

  It is designed for connectivity testing and integration development only.

.SECURITY NOTES
  - Do not paste real client secrets into chat, tickets, screenshots, logs, or Git.
  - Prefer environment variables ALLEVA_CLIENT_ID and ALLEVA_CLIENT_SECRET.
  - By default, this script redacts client_secret, access_token, and Authorization headers.
  - Do not use real patient data in BodyJson while testing unless you have approval and a BAA-covered workflow.
  - The token is kept in memory only. To refresh it, the script requests a new client_credentials token.

.EXAMPLES
  # Recommended: put credentials in this terminal session only
  $env:ALLEVA_CLIENT_ID = "your-client-id"
  $env:ALLEVA_CLIENT_SECRET = "your-secret"
  .\Test-AllevaApi.ps1

  # Just test token retrieval
  .\Test-AllevaApi.ps1 -Mode Token

  # Discover Swagger/OpenAPI JSON and list endpoints
  .\Test-AllevaApi.ps1 -Mode ListEndpoints

  # Call a known GET endpoint after obtaining a token
  .\Test-AllevaApi.ps1 -Mode Call -Method GET -Path "/api/someEndpoint"

  # Call a known GET endpoint with a query string
  .\Test-AllevaApi.ps1 -Mode Call -Method GET -Path "/api/someEndpoint" -QueryString "page=1&pageSize=10"

  # Call a POST endpoint. Unsafe methods require -AllowUnsafeMethods.
  .\Test-AllevaApi.ps1 -Mode Call -Method POST -Path "/api/someEndpoint" -BodyJson '{"test":true}' -AllowUnsafeMethods

  # Show full raw token/secret in output. Use only on a private machine and do not screenshot.
  .\Test-AllevaApi.ps1 -Mode Token -ShowSensitive
#>

[CmdletBinding()]
param(
    [string]$ClientId = $env:ALLEVA_CLIENT_ID,
    [string]$ClientSecret = $env:ALLEVA_CLIENT_SECRET,
    [string]$TokenUrl = "https://authorization.allevasoft.com/connect/token",
    [string]$ApiBaseUrl = "https://api.allevasoft.com",
    [string]$SwaggerJsonUrl = "",
    [string]$Scope = "",

    [ValidateSet("Interactive", "Token", "Discover", "ListEndpoints", "Call", "SmokeTestGet", "HelpCodes")]
    [string]$Mode = "Interactive",

    [ValidateSet("Body", "Basic", "Both")]
    [string]$TokenAuthStyle = "Body",

    [ValidateSet("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")]
    [string]$Method = "GET",

    [string]$Path = "",
    [string]$QueryString = "",
    [string]$BodyJson = "",
    [switch]$AllowUnsafeMethods,

    [switch]$ShowSensitive,
    [switch]$ShowHeaders,
    [switch]$SaveLogs,
    [string]$LogDirectory = ".\alleva-api-test-logs",
    [int]$TimeoutSec = 60,

    [int]$SmokeTestLimit = 25,
    [string]$SmokeTestPathContains = ""
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$script:AccessToken = $null
$script:TokenExpiresAtUtc = [datetime]::MinValue
$script:OpenApiSpec = $null
$script:OpenApiSourceUrl = $null

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host ("=" * 78) -ForegroundColor DarkGray
    Write-Host $Title -ForegroundColor Cyan
    Write-Host ("=" * 78) -ForegroundColor DarkGray
}

function Write-Subsection {
    param([string]$Title)
    Write-Host ""
    Write-Host $Title -ForegroundColor Yellow
    Write-Host ("-" * $Title.Length) -ForegroundColor DarkGray
}

function Read-PlainSecret {
    param([string]$Prompt)
    $secure = Read-Host -Prompt $Prompt -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        if ($bstr -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
    }
}

function Ensure-Credentials {
    if ([string]::IsNullOrWhiteSpace($script:ClientIdValue)) {
        $script:ClientIdValue = Read-Host -Prompt "Alleva client id"
    }
    if ([string]::IsNullOrWhiteSpace($script:ClientSecretValue)) {
        $script:ClientSecretValue = Read-PlainSecret -Prompt "Alleva client secret"
    }
}

function Redact-Text {
    param([AllowNull()][string]$Text)
    if ($null -eq $Text) { return $null }
    if ($ShowSensitive) { return $Text }

    $out = [string]$Text

    if (-not [string]::IsNullOrEmpty($script:ClientSecretValue)) {
        $out = $out.Replace($script:ClientSecretValue, "***REDACTED_CLIENT_SECRET***")
        $encodedSecret = [uri]::EscapeDataString($script:ClientSecretValue)
        $out = $out.Replace($encodedSecret, "***REDACTED_CLIENT_SECRET***")
    }

    if (-not [string]::IsNullOrEmpty($script:AccessToken)) {
        $out = $out.Replace($script:AccessToken, "***REDACTED_ACCESS_TOKEN***")
    }

    $out = [regex]::Replace($out, '(?i)("access_token"\s*:\s*")[^"]+("?)', '$1***REDACTED_ACCESS_TOKEN***$2')
    $out = [regex]::Replace($out, '(?i)(client_secret=)[^&\s]+', '$1***REDACTED_CLIENT_SECRET***')
    $out = [regex]::Replace($out, '(?i)(Authorization\s*[:=]\s*Bearer\s+)[A-Za-z0-9\-\._~\+\/]+=*', '$1***REDACTED_BEARER_TOKEN***')
    $out = [regex]::Replace($out, '(?i)(Authorization\s*[:=]\s*Basic\s+)[A-Za-z0-9\+\/]+=*', '$1***REDACTED_BASIC_TOKEN***')

    return $out
}

function ConvertTo-FormUrlEncoded {
    param([Parameter(Mandatory=$true)]$Form)

    $pairs = New-Object System.Collections.Generic.List[string]
    foreach ($key in $Form.Keys) {
        $value = $Form[$key]
        if ($null -ne $value -and "${value}" -ne "") {
            $pairs.Add(("{0}={1}" -f [uri]::EscapeDataString([string]$key), [uri]::EscapeDataString([string]$value)))
        }
    }
    return ($pairs -join "&")
}

function ConvertTo-PrettyJsonOrText {
    param([AllowNull()][string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return "" }
    try {
        $obj = $Text | ConvertFrom-Json
        return ($obj | ConvertTo-Json -Depth 50)
    }
    catch {
        return $Text
    }
}

function Save-RedactedLog {
    param(
        [string]$Name,
        [string]$Content
    )
    if (-not $SaveLogs) { return }
    if (-not (Test-Path -LiteralPath $LogDirectory)) {
        New-Item -ItemType Directory -Path $LogDirectory | Out-Null
    }
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss-fff"
    $safeName = ($Name -replace '[^a-zA-Z0-9._-]', '_')
    $file = Join-Path $LogDirectory "$stamp-$safeName.txt"
    Set-Content -Path $file -Value (Redact-Text $Content) -Encoding UTF8
    Write-Host "Saved redacted log: $file" -ForegroundColor DarkGray
}

function Get-HeadersText {
    param($Headers)
    if ($null -eq $Headers) { return "" }

    $lines = New-Object System.Collections.Generic.List[string]

    if ($Headers -is [System.Collections.IDictionary]) {
        foreach ($key in $Headers.Keys) {
            $lines.Add(("{0}: {1}" -f $key, $Headers[$key]))
        }
    }
    elseif ($Headers.PSObject.Properties.Name -contains "AllKeys") {
        foreach ($key in $Headers.AllKeys) {
            $lines.Add(("{0}: {1}" -f $key, $Headers[$key]))
        }
    }
    else {
        $lines.Add(($Headers | Out-String))
    }

    return ($lines -join [Environment]::NewLine)
}

function Get-HttpStatusExplanation {
    param([int]$StatusCode)

    switch ($StatusCode) {
        100 { return "Continue: request started; server expects more input." }
        101 { return "Switching Protocols: server accepted a protocol switch." }
        200 { return "OK: request succeeded." }
        201 { return "Created: request succeeded and a resource was created." }
        202 { return "Accepted: request accepted but processing may not be complete." }
        204 { return "No Content: request succeeded with no response body." }
        301 { return "Moved Permanently: endpoint URL changed permanently." }
        302 { return "Found/Redirect: endpoint redirected; check final URL and auth headers." }
        304 { return "Not Modified: cached copy is still valid." }
        307 { return "Temporary Redirect: retry same method at the Location URL." }
        308 { return "Permanent Redirect: retry same method at the Location URL." }
        400 { return "Bad Request: malformed request, missing fields, wrong grant_type, bad JSON, or bad query parameters." }
        401 { return "Unauthorized: missing/expired/invalid bearer token or invalid token request credentials." }
        403 { return "Forbidden: authenticated, but your client is not allowed to access this resource/scope/tenant." }
        404 { return "Not Found: wrong base URL/path, endpoint disabled, or missing route parameter." }
        405 { return "Method Not Allowed: endpoint exists but does not support this HTTP method." }
        406 { return "Not Acceptable: Accept header asks for a response format the API will not produce." }
        408 { return "Request Timeout: server timed out waiting for request." }
        409 { return "Conflict: request conflicts with current state, duplicate record, or versioning issue." }
        415 { return "Unsupported Media Type: Content-Type is wrong, often JSON vs form-url-encoded." }
        422 { return "Unprocessable Entity: JSON is valid but business validation failed." }
        429 { return "Too Many Requests: rate limited; wait and retry, honoring Retry-After if provided." }
        500 { return "Internal Server Error: server-side failure; save request id/body and contact API support." }
        501 { return "Not Implemented: method/function not supported by server." }
        502 { return "Bad Gateway: gateway/proxy received a bad response from upstream server." }
        503 { return "Service Unavailable: maintenance, overload, or transient outage." }
        504 { return "Gateway Timeout: upstream server timed out." }
        default {
            if ($StatusCode -ge 200 -and $StatusCode -lt 300) { return "Success response." }
            if ($StatusCode -ge 300 -and $StatusCode -lt 400) { return "Redirect response." }
            if ($StatusCode -ge 400 -and $StatusCode -lt 500) { return "Client-side request/auth/permission/input issue." }
            if ($StatusCode -ge 500 -and $StatusCode -lt 600) { return "Server-side or gateway issue." }
            return "Unknown or non-standard HTTP status."
        }
    }
}

function Show-ErrorCodeGuide {
    Write-Section "Error and Status Code Guide"

    Write-Host @"
OAuth token endpoint errors you may see in JSON responses:

  invalid_request
    The token request is missing a required value, has a duplicate value, or is not form-url-encoded correctly.
    Common fix: use POST, grant_type=client_credentials, Content-Type application/x-www-form-urlencoded.

  invalid_client
    The client_id/client_secret pair is wrong, inactive, not allowed, or sent in the wrong authentication style.
    Common fix: verify id/secret; try -TokenAuthStyle Body, Basic, or Both.

  unauthorized_client
    The client exists but is not allowed to use client_credentials or this tenant/API.
    Common fix: ask Alleva to enable this integration/client for the right environment and grant type.

  unsupported_grant_type
    The grant_type is wrong or not accepted by the authorization server.
    Common fix: make sure the form body includes grant_type=client_credentials exactly.

  invalid_scope
    Scope is missing, malformed, or not assigned to the client.
    Common fix: omit -Scope first; if Alleva gave a scope, pass it exactly.

  invalid_token
    The bearer token sent to the API is expired, malformed, revoked, or intended for another API/audience.
    Common fix: run Mode Token again or let the script refresh automatically.

  insufficient_scope
    Token is valid but does not include permission for that endpoint.
    Common fix: ask Alleva which scope/role is needed for the endpoint.

  temporarily_unavailable / server_error
    Authorization server has a temporary problem.
    Common fix: retry later; save timestamp, request id, and response body for support.

Common HTTP status codes:

  200 OK                  Success with response body.
  201 Created             Success; a resource was created.
  202 Accepted            Accepted for later processing.
  204 No Content          Success, no body.
  301/302/307/308         Redirect; check URL and whether Authorization header is preserved.
  400 Bad Request         Bad syntax, bad body, bad grant_type, bad Content-Type, or missing fields.
  401 Unauthorized        Missing/expired/invalid token or invalid client credentials at token endpoint.
  403 Forbidden           Authenticated but not allowed for tenant/scope/resource.
  404 Not Found           Wrong base URL/path, missing route variable, or endpoint unavailable.
  405 Method Not Allowed  Wrong HTTP method.
  409 Conflict            Duplicate or state conflict.
  415 Unsupported Type    Wrong Content-Type; token endpoint usually needs form-url-encoded, APIs often need JSON.
  422 Validation Error    Input shape is valid JSON, but business validation failed.
  429 Too Many Requests   Rate limited; slow down and honor Retry-After.
  500 Server Error        Alleva/server-side failure, not normally fixable in your script.
  502 Bad Gateway         Proxy/gateway problem.
  503 Unavailable         Service down, overloaded, or maintenance.
  504 Gateway Timeout     Upstream timeout.

Connectivity / local-machine errors:

  DNS failure             Your machine cannot resolve the host name; check Wi-Fi/VPN/DNS.
  TLS/SSL error           TLS negotiation/cert issue; confirm system date/time and TLS 1.2+.
  Timeout                 No response in -TimeoutSec seconds; check VPN, firewall, endpoint, or service status.
  Proxy authentication    Corporate proxy may require sign-in or whitelisting.
"@
}

function Invoke-HttpRaw {
    param(
        [Parameter(Mandatory=$true)][ValidateSet("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")][string]$HttpMethod,
        [Parameter(Mandatory=$true)][string]$Url,
        [hashtable]$Headers = @{},
        [AllowNull()][string]$Body = $null,
        [string]$ContentType = "",
        [string]$LogName = "request"
    )

    Write-Subsection "Outbound request"
    Write-Host "Method: $HttpMethod"
    Write-Host "URL:    $Url"

    $requestLog = New-Object System.Text.StringBuilder
    [void]$requestLog.AppendLine("REQUEST")
    [void]$requestLog.AppendLine("Method: $HttpMethod")
    [void]$requestLog.AppendLine("URL: $Url")

    if ($Headers.Count -gt 0) {
        $headersText = Get-HeadersText $Headers
        if ($ShowHeaders) {
            Write-Host "Headers:" -ForegroundColor DarkGray
            Write-Host (Redact-Text $headersText)
        }
        else {
            Write-Host "Headers: hidden; use -ShowHeaders to display redacted headers" -ForegroundColor DarkGray
        }
        [void]$requestLog.AppendLine("Headers:")
        [void]$requestLog.AppendLine($headersText)
    }

    if ($ContentType) {
        Write-Host "Content-Type: $ContentType"
        [void]$requestLog.AppendLine("Content-Type: $ContentType")
    }

    if ($null -ne $Body -and $Body.Length -gt 0) {
        Write-Host "Body:" -ForegroundColor DarkGray
        Write-Host (Redact-Text (ConvertTo-PrettyJsonOrText $Body))
        [void]$requestLog.AppendLine("Body:")
        [void]$requestLog.AppendLine($Body)
    }
    else {
        Write-Host "Body:   <none>" -ForegroundColor DarkGray
        [void]$requestLog.AppendLine("Body: <none>")
    }

    $params = @{
        Uri         = $Url
        Method      = $HttpMethod
        Headers     = $Headers
        TimeoutSec  = $TimeoutSec
        ErrorAction = "Stop"
    }

    if ($ContentType) { $params["ContentType"] = $ContentType }
    if ($null -ne $Body) { $params["Body"] = $Body }
    if ($PSVersionTable.PSVersion.Major -lt 6) { $params["UseBasicParsing"] = $true }

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $resp = Invoke-WebRequest @params
        $sw.Stop()

        $status = [int]$resp.StatusCode
        $content = [string]$resp.Content
        $parsed = $null
        try { if (-not [string]::IsNullOrWhiteSpace($content)) { $parsed = $content | ConvertFrom-Json } } catch { }

        Write-Subsection "Inbound response"
        Write-Host ("HTTP {0} - {1}" -f $status, (Get-HttpStatusExplanation $status)) -ForegroundColor Green
        Write-Host ("Duration: {0} ms" -f $sw.ElapsedMilliseconds)

        $responseHeadersText = Get-HeadersText $resp.Headers
        if ($ShowHeaders) {
            Write-Host "Headers:" -ForegroundColor DarkGray
            Write-Host (Redact-Text $responseHeadersText)
        }
        else {
            Write-Host "Headers: hidden; use -ShowHeaders to display redacted headers" -ForegroundColor DarkGray
        }

        if (-not [string]::IsNullOrWhiteSpace($content)) {
            Write-Host "Body:" -ForegroundColor DarkGray
            Write-Host (Redact-Text (ConvertTo-PrettyJsonOrText $content))
        }
        else {
            Write-Host "Body: <empty>" -ForegroundColor DarkGray
        }

        $fullLog = New-Object System.Text.StringBuilder
        [void]$fullLog.AppendLine($requestLog.ToString())
        [void]$fullLog.AppendLine("RESPONSE")
        [void]$fullLog.AppendLine("HTTP $status")
        [void]$fullLog.AppendLine("DurationMs: $($sw.ElapsedMilliseconds)")
        [void]$fullLog.AppendLine("Headers:")
        [void]$fullLog.AppendLine($responseHeadersText)
        [void]$fullLog.AppendLine("Body:")
        [void]$fullLog.AppendLine($content)
        Save-RedactedLog -Name $LogName -Content $fullLog.ToString()

        return [pscustomobject]@{
            Ok                 = ($status -ge 200 -and $status -lt 300)
            StatusCode         = $status
            StatusDescription  = $resp.StatusDescription
            Headers            = $resp.Headers
            Content            = $content
            ParsedJson         = $parsed
            DurationMs         = $sw.ElapsedMilliseconds
            Error              = $null
        }
    }
    catch {
        $sw.Stop()
        $status = 0
        $statusDescription = ""
        $headers = @{}
        $content = ""
        $parsed = $null
        $errorText = $_.Exception.Message

        if ($_.Exception.Response) {
            $webResp = $_.Exception.Response
            try { $status = [int]$webResp.StatusCode } catch { $status = 0 }
            try { $statusDescription = [string]$webResp.StatusDescription } catch { $statusDescription = "" }
            try { $headers = $webResp.Headers } catch { $headers = @{} }

            try {
                $stream = $webResp.GetResponseStream()
                if ($stream) {
                    $reader = New-Object System.IO.StreamReader($stream)
                    $content = $reader.ReadToEnd()
                    $reader.Close()
                }
            }
            catch {
                $content = ""
            }
            try { if (-not [string]::IsNullOrWhiteSpace($content)) { $parsed = $content | ConvertFrom-Json } } catch { }
        }

        Write-Subsection "Inbound response / error"
        if ($status -gt 0) {
            Write-Host ("HTTP {0} - {1}" -f $status, (Get-HttpStatusExplanation $status)) -ForegroundColor Red
        }
        else {
            Write-Host "No HTTP status received. This is likely DNS, TLS, proxy, firewall, or timeout." -ForegroundColor Red
        }
        Write-Host ("Duration: {0} ms" -f $sw.ElapsedMilliseconds)
        Write-Host "PowerShell error: $(Redact-Text $errorText)" -ForegroundColor Red

        $responseHeadersText = Get-HeadersText $headers
        if ($ShowHeaders -and $responseHeadersText) {
            Write-Host "Headers:" -ForegroundColor DarkGray
            Write-Host (Redact-Text $responseHeadersText)
        }

        if (-not [string]::IsNullOrWhiteSpace($content)) {
            Write-Host "Body:" -ForegroundColor DarkGray
            Write-Host (Redact-Text (ConvertTo-PrettyJsonOrText $content))
        }
        else {
            Write-Host "Body: <empty or unavailable>" -ForegroundColor DarkGray
        }

        $fullLog = New-Object System.Text.StringBuilder
        [void]$fullLog.AppendLine($requestLog.ToString())
        [void]$fullLog.AppendLine("RESPONSE/ERROR")
        [void]$fullLog.AppendLine("HTTP $status $statusDescription")
        [void]$fullLog.AppendLine("DurationMs: $($sw.ElapsedMilliseconds)")
        [void]$fullLog.AppendLine("PowerShellError: $errorText")
        [void]$fullLog.AppendLine("Headers:")
        [void]$fullLog.AppendLine($responseHeadersText)
        [void]$fullLog.AppendLine("Body:")
        [void]$fullLog.AppendLine($content)
        Save-RedactedLog -Name $LogName -Content $fullLog.ToString()

        return [pscustomobject]@{
            Ok                 = $false
            StatusCode         = $status
            StatusDescription  = $statusDescription
            Headers            = $headers
            Content            = $content
            ParsedJson         = $parsed
            DurationMs         = $sw.ElapsedMilliseconds
            Error              = $errorText
        }
    }
}

function Request-TokenOnce {
    param([ValidateSet("Body", "Basic")][string]$Style)

    Ensure-Credentials

    $headers = @{ Accept = "application/json" }
    $form = [ordered]@{
        grant_type = "client_credentials"
    }

    if ($Style -eq "Body") {
        $form["client_id"] = $script:ClientIdValue
        $form["client_secret"] = $script:ClientSecretValue
    }
    else {
        $pair = "{0}:{1}" -f $script:ClientIdValue, $script:ClientSecretValue
        $basic = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($pair))
        $headers["Authorization"] = "Basic $basic"
    }

    if (-not [string]::IsNullOrWhiteSpace($Scope)) {
        $form["scope"] = $Scope
    }

    $body = ConvertTo-FormUrlEncoded $form
    Write-Section "Requesting OAuth bearer token using client_credentials ($Style auth style)"
    $resp = Invoke-HttpRaw -HttpMethod POST -Url $TokenUrl -Headers $headers -Body $body -ContentType "application/x-www-form-urlencoded" -LogName "token-$Style"
    return $resp
}

function Get-AccessToken {
    $styles = @()
    if ($TokenAuthStyle -eq "Both") { $styles = @("Body", "Basic") } else { $styles = @($TokenAuthStyle) }

    foreach ($style in $styles) {
        $resp = Request-TokenOnce -Style $style
        if ($resp.Ok -and $resp.ParsedJson -and $resp.ParsedJson.access_token) {
            $script:AccessToken = [string]$resp.ParsedJson.access_token

            $expiresIn = 3600
            if ($resp.ParsedJson.expires_in) {
                try { $expiresIn = [int]$resp.ParsedJson.expires_in } catch { $expiresIn = 3600 }
            }
            $script:TokenExpiresAtUtc = (Get-Date).ToUniversalTime().AddSeconds($expiresIn)

            Write-Host ""
            Write-Host "Token acquired successfully." -ForegroundColor Green
            Write-Host ("Expires in: approximately {0} seconds" -f $expiresIn)
            Write-Host ("Expires at UTC: {0}" -f $script:TokenExpiresAtUtc.ToString("yyyy-MM-dd HH:mm:ss"))
            if (-not $ShowSensitive) {
                Write-Host "Token value is redacted. Use -ShowSensitive only on a private terminal if you must see it." -ForegroundColor DarkYellow
            }
            return $true
        }
        else {
            Write-Host "Token attempt using $style style did not succeed." -ForegroundColor DarkYellow
        }
    }

    Write-Host ""
    Write-Host "Could not acquire a token. Review the HTTP status, OAuth error body, grant_type, auth style, and credentials." -ForegroundColor Red
    return $false
}

function Ensure-AccessToken {
    $now = (Get-Date).ToUniversalTime()
    if ($script:AccessToken -and $script:TokenExpiresAtUtc -gt $now.AddSeconds(120)) {
        return $true
    }

    if ($script:AccessToken) {
        Write-Host "Bearer token is near expiry or expired; requesting a new client_credentials token." -ForegroundColor DarkYellow
    }
    return (Get-AccessToken)
}

function Build-FullUrl {
    param(
        [Parameter(Mandatory=$true)][string]$EndpointPath,
        [string]$Qs = ""
    )

    if ($EndpointPath -match '^https?://') {
        $url = $EndpointPath
    }
    else {
        $base = $ApiBaseUrl.TrimEnd('/')
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
        [Parameter(Mandatory=$true)][ValidateSet("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")][string]$ApiMethod,
        [Parameter(Mandatory=$true)][string]$EndpointPath,
        [string]$Qs = "",
        [string]$JsonBody = ""
    )

    $unsafe = @("POST", "PUT", "PATCH", "DELETE")
    if ($unsafe -contains $ApiMethod -and -not $AllowUnsafeMethods) {
        Write-Host "Refusing to run $ApiMethod without -AllowUnsafeMethods." -ForegroundColor Red
        Write-Host "Reason: write/delete endpoints can create, modify, or delete EMR data." -ForegroundColor Red
        return $null
    }

    if (-not (Ensure-AccessToken)) { return $null }

    $url = Build-FullUrl -EndpointPath $EndpointPath -Qs $Qs
    $headers = @{
        Accept        = "application/json"
        Authorization = "Bearer $script:AccessToken"
    }

    $bodyToSend = $null
    $contentType = ""
    if (-not [string]::IsNullOrWhiteSpace($JsonBody)) {
        try { $null = $JsonBody | ConvertFrom-Json } catch { Write-Host "BodyJson is not valid JSON: $($_.Exception.Message)" -ForegroundColor Red; return $null }
        $bodyToSend = $JsonBody
        $contentType = "application/json"
    }

    Write-Section "Calling Alleva API endpoint"
    return (Invoke-HttpRaw -HttpMethod $ApiMethod -Url $url -Headers $headers -Body $bodyToSend -ContentType $contentType -LogName "api-$ApiMethod-$EndpointPath")
}

function Get-CandidateSwaggerUrls {
    $urls = New-Object System.Collections.Generic.List[string]
    if (-not [string]::IsNullOrWhiteSpace($SwaggerJsonUrl)) { $urls.Add($SwaggerJsonUrl) }
    $base = $ApiBaseUrl.TrimEnd('/')
    $urls.Add("$base/swagger/v1/swagger.json")
    $urls.Add("$base/swagger/docs/v1")
    $urls.Add("$base/swagger/swagger.json")
    $urls.Add("$base/swagger.json")
    $urls.Add("$base/openapi.json")
    return ($urls | Select-Object -Unique)
}

function Try-ParseSwaggerUrlFromUi {
    param([string]$Html)
    $found = New-Object System.Collections.Generic.List[string]

    if ([string]::IsNullOrWhiteSpace($Html)) { return $found }

    $matches1 = [regex]::Matches($Html, '(?i)url\s*:\s*["'']([^"'']+swagger[^"'']+\.json|[^"'']+openapi[^"'']+\.json|/[^"'']+)["'']')
    foreach ($m in $matches1) { $found.Add($m.Groups[1].Value) }

    $matches2 = [regex]::Matches($Html, '(?i)["'']url["'']\s*:\s*["'']([^"'']+)["'']')
    foreach ($m in $matches2) { $found.Add($m.Groups[1].Value) }

    $base = $ApiBaseUrl.TrimEnd('/')
    $normalized = New-Object System.Collections.Generic.List[string]
    foreach ($u in ($found | Select-Object -Unique)) {
        if ($u -match '^https?://') { $normalized.Add($u) }
        elseif ($u.StartsWith('/')) { $normalized.Add("$base$u") }
        else { $normalized.Add("$base/$u") }
    }

    return ($normalized | Select-Object -Unique)
}

function Discover-OpenApiSpec {
    Write-Section "Discovering Swagger/OpenAPI document"

    $candidates = New-Object System.Collections.Generic.List[string]
    foreach ($u in (Get-CandidateSwaggerUrls)) { $candidates.Add($u) }

    $uiUrl = "$($ApiBaseUrl.TrimEnd('/'))/swagger/index.html"
    Write-Host "Checking Swagger UI for embedded JSON URL: $uiUrl" -ForegroundColor DarkGray
    $uiResp = Invoke-HttpRaw -HttpMethod GET -Url $uiUrl -Headers @{Accept="text/html,application/json"} -LogName "swagger-ui"
    if ($uiResp.Ok) {
        foreach ($u in (Try-ParseSwaggerUrlFromUi -Html $uiResp.Content)) { $candidates.Add($u) }
    }

    foreach ($url in ($candidates | Select-Object -Unique)) {
        Write-Host ""
        Write-Host "Trying OpenAPI candidate: $url" -ForegroundColor Cyan
        $resp = Invoke-HttpRaw -HttpMethod GET -Url $url -Headers @{Accept="application/json"} -LogName "swagger-json"
        if ($resp.Ok -and $resp.ParsedJson -and ($resp.ParsedJson.paths -or $resp.ParsedJson.swagger -or $resp.ParsedJson.openapi)) {
            $script:OpenApiSpec = $resp.ParsedJson
            $script:OpenApiSourceUrl = $url
            Write-Host "OpenAPI/Swagger document found: $url" -ForegroundColor Green
            return $true
        }
    }

    Write-Host ""
    Write-Host "Could not auto-discover Swagger JSON." -ForegroundColor DarkYellow
    Write-Host "Open https://api.allevasoft.com/swagger/index.html in a browser, inspect the network request for swagger.json, then rerun with -SwaggerJsonUrl <that URL>." -ForegroundColor DarkYellow
    return $false
}

function Get-EndpointRowsFromSpec {
    if ($null -eq $script:OpenApiSpec -or $null -eq $script:OpenApiSpec.paths) { return @() }

    $rows = New-Object System.Collections.Generic.List[object]
    $httpMethods = @("get", "post", "put", "patch", "delete", "head", "options")

    foreach ($pathName in $script:OpenApiSpec.paths.PSObject.Properties.Name) {
        $pathObj = $script:OpenApiSpec.paths.$pathName
        foreach ($methodName in $httpMethods) {
            if ($pathObj.PSObject.Properties.Name -contains $methodName) {
                $op = $pathObj.$methodName
                $requiredParams = New-Object System.Collections.Generic.List[string]

                if ($op.parameters) {
                    foreach ($p in $op.parameters) {
                        if ($p.required -eq $true) {
                            $requiredParams.Add(("{0}({1})" -f $p.name, $p.in))
                        }
                    }
                }

                $requestBodyRequired = $false
                if ($op.requestBody -and $op.requestBody.required -eq $true) { $requestBodyRequired = $true }
                if ($requestBodyRequired) { $requiredParams.Add("requestBody(body)") }

                $rows.Add([pscustomobject]@{
                    Method          = $methodName.ToUpperInvariant()
                    Path            = $pathName
                    OperationId     = [string]$op.operationId
                    Summary         = [string]$op.summary
                    Required        = ($requiredParams -join ", ")
                    HasRequestBody  = [bool]$op.requestBody
                })
            }
        }
    }

    return $rows
}

function Show-Endpoints {
    if ($null -eq $script:OpenApiSpec) {
        if (-not (Discover-OpenApiSpec)) { return }
    }

    Write-Section "Swagger/OpenAPI endpoints"
    Write-Host "Source: $script:OpenApiSourceUrl" -ForegroundColor DarkGray
    $rows = Get-EndpointRowsFromSpec
    if ($rows.Count -eq 0) {
        Write-Host "No endpoint rows found in the OpenAPI document." -ForegroundColor Red
        return
    }

    $rows | Sort-Object Path, Method | Format-Table -AutoSize
}

function Invoke-SafeSmokeTestGetEndpoints {
    if ($null -eq $script:OpenApiSpec) {
        if (-not (Discover-OpenApiSpec)) { return }
    }

    $rows = Get-EndpointRowsFromSpec | Where-Object {
        $_.Method -eq "GET" -and [string]::IsNullOrWhiteSpace($_.Required)
    }

    if (-not [string]::IsNullOrWhiteSpace($SmokeTestPathContains)) {
        $rows = $rows | Where-Object { $_.Path -like "*$SmokeTestPathContains*" }
    }

    $rows = $rows | Select-Object -First $SmokeTestLimit

    if ($null -eq $rows -or @($rows).Count -eq 0) {
        Write-Host "No safe GET endpoints without required parameters were found." -ForegroundColor DarkYellow
        return
    }

    Write-Section "Safe smoke test: GET endpoints with no required parameters"
    Write-Host "Limit: $SmokeTestLimit" -ForegroundColor DarkGray
    Write-Host "This may still return live API data. Stop now with Ctrl+C if you are not authorized." -ForegroundColor DarkYellow

    $summary = New-Object System.Collections.Generic.List[object]
    foreach ($row in $rows) {
        $resp = Invoke-ApiEndpoint -ApiMethod GET -EndpointPath $row.Path
        $summary.Add([pscustomobject]@{
            Method     = "GET"
            Path       = $row.Path
            StatusCode = if ($resp) { $resp.StatusCode } else { 0 }
            Ok         = if ($resp) { $resp.Ok } else { $false }
            Meaning    = if ($resp) { Get-HttpStatusExplanation $resp.StatusCode } else { "Not attempted" }
        })
    }

    Write-Section "Smoke test summary"
    $summary | Format-Table -AutoSize
}

function Start-InteractiveMenu {
    while ($true) {
        Write-Section "Alleva API Connectivity Tester"
        Write-Host "1. Request/refresh bearer token"
        Write-Host "2. Discover Swagger/OpenAPI JSON"
        Write-Host "3. List Swagger/OpenAPI endpoints"
        Write-Host "4. Call one endpoint"
        Write-Host "5. Safe smoke test: GET endpoints with no required parameters"
        Write-Host "6. Explain error/status codes"
        Write-Host "7. Show current settings"
        Write-Host "0. Exit"
        $choice = Read-Host "Choose an option"

        switch ($choice) {
            "1" { [void](Get-AccessToken) }
            "2" { [void](Discover-OpenApiSpec) }
            "3" { Show-Endpoints }
            "4" {
                $m = Read-Host "HTTP method [GET/POST/PUT/PATCH/DELETE]"
                if ([string]::IsNullOrWhiteSpace($m)) { $m = "GET" }
                $m = $m.ToUpperInvariant()
                if (@("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS") -notcontains $m) {
                    Write-Host "Unsupported method." -ForegroundColor Red
                    continue
                }
                $p = Read-Host "Endpoint path, e.g. /api/example"
                if ([string]::IsNullOrWhiteSpace($p)) {
                    Write-Host "Path is required." -ForegroundColor Red
                    continue
                }
                $qs = Read-Host "Query string without ?, or leave blank"
                $body = ""
                if (@("POST", "PUT", "PATCH") -contains $m) {
                    $body = Read-Host "JSON body, or leave blank"
                }
                [void](Invoke-ApiEndpoint -ApiMethod $m -EndpointPath $p -Qs $qs -JsonBody $body)
            }
            "5" { Invoke-SafeSmokeTestGetEndpoints }
            "6" { Show-ErrorCodeGuide }
            "7" {
                Write-Section "Current settings"
                Write-Host "PowerShell version: $($PSVersionTable.PSVersion)"
                Write-Host "TokenUrl:           $TokenUrl"
                Write-Host "ApiBaseUrl:         $ApiBaseUrl"
                Write-Host "SwaggerJsonUrl:     $SwaggerJsonUrl"
                Write-Host "Scope:              $Scope"
                Write-Host "TokenAuthStyle:     $TokenAuthStyle"
                Write-Host "ShowSensitive:      $ShowSensitive"
                Write-Host "ShowHeaders:        $ShowHeaders"
                Write-Host "SaveLogs:           $SaveLogs"
                Write-Host "LogDirectory:       $LogDirectory"
                Write-Host "Token in memory:    $([bool]$script:AccessToken)"
                if ($script:AccessToken) { Write-Host "Token expires UTC:  $($script:TokenExpiresAtUtc.ToString('yyyy-MM-dd HH:mm:ss'))" }
            }
            "0" { return }
            default { Write-Host "Choose 0 through 7." -ForegroundColor DarkYellow }
        }

        Write-Host ""
        $null = Read-Host "Press Enter to continue"
    }
}

$script:ClientIdValue = $ClientId
$script:ClientSecretValue = $ClientSecret

Write-Host "Alleva API Connectivity Tester" -ForegroundColor Cyan
Write-Host "Secrets and bearer tokens are redacted by default." -ForegroundColor DarkYellow
Write-Host "Use only authorized test/development access and avoid PHI in test payloads." -ForegroundColor DarkYellow

switch ($Mode) {
    "Interactive"   { Start-InteractiveMenu }
    "Token"         { [void](Get-AccessToken) }
    "Discover"      { [void](Discover-OpenApiSpec) }
    "ListEndpoints" { Show-Endpoints }
    "Call"          {
        if ([string]::IsNullOrWhiteSpace($Path)) {
            Write-Host "-Path is required for -Mode Call." -ForegroundColor Red
            exit 2
        }
        [void](Invoke-ApiEndpoint -ApiMethod $Method -EndpointPath $Path -Qs $QueryString -JsonBody $BodyJson)
    }
    "SmokeTestGet"  { Invoke-SafeSmokeTestGetEndpoints }
    "HelpCodes"     { Show-ErrorCodeGuide }
}
