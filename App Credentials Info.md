# App Credentials Info

This tracked file is intentionally sanitized. Do not store live Alleva client IDs,
client secrets, bearer tokens, API keys, passwords, or tenant-specific patient data
in this repository.

## Alleva Public Endpoints

- Swagger UI: `https://api.allevasoft.com/swagger/index.html`
- Token endpoint: `https://authorization.allevasoft.com/connect/token`
- Expected auth flow for testing: OAuth2 `client_credentials`, then send the
  returned access token as an `Authorization: Bearer <token>` header.

## Safe Local Credential Handling

For one-time connectivity testing, set temporary PowerShell environment variables
in the current shell only:

```powershell
$env:ALLEVA_CLIENT_ID = "<provided-by-Alleva>"
$env:ALLEVA_CLIENT_SECRET = "<provided-by-Alleva>"
$env:ALLEVA_TOKEN_URL = "https://authorization.allevasoft.com/connect/token"
scripts\test-alleva-api-connectivity.ps1 -WriteJsonReport
```

For app-based testing, enter the client ID, token URL, and client secret in the
admin settings/API configuration screen. The client secret is encrypted at rest
and never returned to the browser after save.

Live Alleva patient import remains disabled until R3 has approved tenant
credentials, endpoint mapping, scopes, pagination/rate-limit behavior, attachment
handling, vendor documentation, and compliance sign-off.
