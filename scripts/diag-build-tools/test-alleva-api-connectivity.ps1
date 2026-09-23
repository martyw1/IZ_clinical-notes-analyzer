[CmdletBinding()]
param(
    [string]$SwaggerUiUrl = 'https://api.allevasoft.com/swagger/index.html',
    [string]$BearerToken = $env:ALLEVA_API_BEARER_TOKEN,
    [string]$ApiKey = $env:ALLEVA_API_KEY,
    [string]$ClientId = $env:ALLEVA_CLIENT_ID,
    [string]$ClientSecret = $env:ALLEVA_CLIENT_SECRET,
    [string]$TokenUrl = $(if ($env:ALLEVA_TOKEN_URL) { $env:ALLEVA_TOKEN_URL } else { 'https://authorization.allevasoft.com/connect/token' }),
    [string]$Scope = $env:ALLEVA_API_SCOPE,
    [int]$TimeoutSeconds = 15,
    [switch]$WriteJsonReport
)

$ErrorActionPreference = 'Stop'
$headers = @{ Accept = 'application/json, text/html;q=0.9, */*;q=0.8' }
$tokenResult = [ordered]@{
    attempted = $false
    status = 'not_attempted'
    http_status_code = 0
    token_url = $TokenUrl
    access_token_received = $false
    detail = ''
}

if (-not $BearerToken -and $ClientId -and $ClientSecret) {
    $tokenResult.attempted = $true
    try {
        $body = @{
            grant_type = 'client_credentials'
            client_id = $ClientId
            client_secret = $ClientSecret
        }
        if ($Scope) { $body.scope = $Scope }
        $tokenResponse = Invoke-RestMethod -Method Post -Uri $TokenUrl -Body $body -ContentType 'application/x-www-form-urlencoded' -TimeoutSec $TimeoutSeconds
        if ($tokenResponse.access_token) {
            $BearerToken = [string]$tokenResponse.access_token
            $tokenResult.status = 'ok'
            $tokenResult.http_status_code = 200
            $tokenResult.access_token_received = $true
            $tokenResult.detail = 'Client-credentials token obtained. Token value redacted.'
        }
        else {
            $tokenResult.status = 'fail'
            $tokenResult.detail = 'Token response did not include access_token.'
        }
    }
    catch {
        $tokenResult.status = 'fail'
        if ($_.Exception.Response) {
            try { $tokenResult.http_status_code = [int]$_.Exception.Response.StatusCode } catch {}
        }
        $tokenResult.detail = $_.Exception.Message
    }
}

if ($BearerToken) { $headers.Authorization = "Bearer $BearerToken" }
if ($ApiKey) { $headers.'x-api-key' = $ApiKey }

function New-ProbeResult {
    param(
        [string]$Name,
        [string]$Url,
        [string]$Status,
        [int]$HttpStatusCode = 0,
        [string]$ContentType = '',
        [string]$Detail = ''
    )
    [ordered]@{
        name = $Name
        url = $Url
        status = $Status
        http_status_code = $HttpStatusCode
        content_type = $ContentType
        detail = $Detail
    }
}

function Invoke-Probe {
    param([string]$Name, [string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -Headers $headers -TimeoutSec $TimeoutSeconds -UseBasicParsing
        $contentType = $response.Headers['Content-Type']
        $status = if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) { 'ok' } else { 'warn' }
        $detail = "Received $($response.RawContentLength) byte(s)."
        return New-ProbeResult -Name $Name -Url $Url -Status $status -HttpStatusCode $response.StatusCode -ContentType $contentType -Detail $detail
    }
    catch {
        $code = 0
        $contentType = ''
        if ($_.Exception.Response) {
            try { $code = [int]$_.Exception.Response.StatusCode } catch {}
            try { $contentType = $_.Exception.Response.Headers['Content-Type'] } catch {}
        }
        return New-ProbeResult -Name $Name -Url $Url -Status 'fail' -HttpStatusCode $code -ContentType $contentType -Detail $_.Exception.Message
    }
}

$baseUri = [Uri]$SwaggerUiUrl
$root = "$($baseUri.Scheme)://$($baseUri.Host)"
$candidates = @(
    @{ name = 'Swagger UI'; url = $SwaggerUiUrl },
    @{ name = 'OpenAPI JSON v1'; url = "$root/swagger/v1/swagger.json" },
    @{ name = 'OpenAPI JSON default'; url = "$root/swagger.json" },
    @{ name = 'OpenAPI JSON openapi'; url = "$root/openapi.json" },
    @{ name = 'API root'; url = "$root/" }
)

$results = foreach ($candidate in $candidates) {
    Invoke-Probe -Name $candidate.name -Url $candidate.url
}

$summary = [ordered]@{
    checked_at_local = (Get-Date).ToString('s')
    swagger_ui_url = $SwaggerUiUrl
    credentials_supplied = [ordered]@{
        bearer_token = [bool]$BearerToken
        api_key = [bool]$ApiKey
        client_credentials = [bool]($ClientId -and $ClientSecret)
    }
    token_request = $tokenResult
    overall_status = if ($results | Where-Object { $_.status -eq 'ok' }) { 'reachable' } else { 'unreachable' }
    results = $results
    next_steps = @(
        'If Swagger UI is reachable but JSON candidates fail, inspect the Swagger UI network panel or vendor documentation for the exact OpenAPI document URL.',
        'If protected endpoints require credentials, set ALLEVA_CLIENT_ID and ALLEVA_CLIENT_SECRET, or ALLEVA_API_BEARER_TOKEN, or ALLEVA_API_KEY in the shell before running this script.',
        'Do not paste real Alleva credentials into source files or commit them to GitHub.'
    )
}

$summary | ConvertTo-Json -Depth 6

if ($WriteJsonReport) {
    $reportDir = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer\api-connectivity-reports'
    New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
    $reportPath = Join-Path $reportDir ("alleva-api-connectivity-{0}.json" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    $summary | ConvertTo-Json -Depth 6 | Set-Content -Path $reportPath -Encoding UTF8
    Write-Host "Report written to $reportPath"
}
