# API Configuration and Connectivity Test

Date: 2026-06-16

Applies to: IZ Clinical Notes Analyzer Version `1.3.0` / build `2026.06.16.1` local Windows desktop runtime.

## Where to open it

When running the Windows local desktop runtime, open:

```text
http://localhost:8000/api-configuration
```

Admins can also open the API harness from App settings. When opened from the app, the harness reuses the current signed-in admin session and does not require a second in-page admin login.

## What the page does

The API configuration page lets an admin:

1. Enter or update the API vendor/base URL.
2. Enter an API key for a one-time test or save it for later use.
3. Enter OAuth2 client-credentials values for a one-time test or save the client ID/token URL plus encrypted client secret.
4. Select the OAuth token auth style that matches the provider: body credentials, Basic auth, URL-encoded Basic auth, try-both, or try-all supported styles.
5. Pull OpenAPI/Swagger definitions from a Swagger UI page or direct JSON URL.
6. Test connectivity from inside the running app.
7. Pick an operation found in the loaded API definition and test that specific API call.
8. Fill a generated test form based on the selected operation's required path, query, header, and JSON body fields.
9. Review non-secret test results, including probed URLs, HTTP status codes, discovered OpenAPI title/version, path counts, schema counts, security scheme names, sample paths, token-request status, operation-test responses, and redacted JSON report payloads.

The app also writes a redacted copy of pull-definition and selected-operation test reports under local app data so admins can retain test evidence without exposing API keys, client secrets, or bearer tokens in browser payloads.

## Operation test workbench

After a definition is loaded, the page builds an operation picker from the OpenAPI `paths` object. For each selected method/path, it derives a form from:

- path parameters, such as `{patient_id}`
- query parameters
- header parameters
- top-level JSON request-body fields
- required flags, types, enums, defaults, descriptions, and date formats where present

When an admin runs a selected API call test, the app sends the request from the local FastAPI backend using the configured base URL, selected auth mode, one-time API key, saved encrypted API key, or client-credentials bearer token obtained for that test. GET/HEAD requests do not send a request body unless the selected OpenAPI operation genuinely requires one.

The browser result includes status code, content type, timing when available, parsed JSON when the response is JSON, or a short body preview for non-JSON responses. API keys and bearer tokens are injected into the outbound request but are not returned in the test result. Sensitive response field names such as tokens, secrets, passwords, authorization values, and API keys are redacted before display.

Large operation responses are capped before returning to the browser. The app captures at most 200 KB from a selected operation response and shows at most a short preview if the response is larger. Saved redacted reports omit full OpenAPI definitions and compact long JSON arrays/objects so a provider response cannot overwhelm the UI or local report directory.

For FHIR tests, the base URL is the root FHIR R4 endpoint supplied by Alleva or a future EMR vendor, such as a tenant endpoint ending in `/fhir/R4`.

## Periodic API readiness checks

Admins can turn on periodic safe Alleva/API checks from `App settings` after saving:

- API or FHIR base URL
- token URL
- client ID
- encrypted client secret
- token auth style
- check interval in minutes

The background checker authenticates with the saved client ID/secret, applies the selected token auth style, and runs the same bounded OpenAPI/readiness probe used by the harness. App settings shows the last check time, status, message, last success/failure, and next scheduled check through the Review Source Discovery payload.

Periodic checks are readiness checks only. They do not import live patient charts or treatment plans until R3 has vendor endpoint mapping, scopes, pagination/rate limits, attachment handling, documentation, and compliance approval.

## EMR endpoint profiles

Admins can save multiple endpoint profiles for Alleva and future EMR/FHIR integrations from App settings. Each profile stores vendor label, adapter key, FHIR base URL, optional OpenAPI URL, token URL, token auth style, client ID, encrypted client secret, scopes, timeout, active/default flags, and notes.

Browser responses return only configured flags for secrets. Activating a profile copies it into the current App settings EMR/API configuration used by discovery, import-plan, and readiness tests.

## Secret handling inside the app

API keys and client secrets are never returned to the browser after save and are not written into audit-log details. Saved API keys/client secrets are encrypted with the app's local secret-encryption envelope and stored in the local application database. The page may also use pasted one-time values without saving them. Client-credentials access tokens are held in memory only for the current pull/test request. Generated report payloads redact saved keys, one-time keys, client secrets, bearer strings, token-like query parameters, and sensitive fields from external API responses.

## Standalone Alleva scripts

Two standalone scripts exist and should not be confused with each other.

| Script | Purpose | Output and secret behavior |
| --- | --- | --- |
| `scripts\test-alleva-api-connectivity.ps1` | Simple Swagger/OpenAPI/API reachability probe and JSON report writer. | Designed for redacted report evidence. Review every report before sharing. |
| `Test-AllevaApi.ps1` | Full diagnostic tester with interactive endpoint selection, local settings, endpoint CSV support, detailed request/response capture, and multiple token-auth styles. | Sensitive by default. It prints and saves tokens, secrets, Authorization headers, request bodies, and response bodies unless `-RedactSensitive` is used. |

Use the root `Test-AllevaApi.ps1` only on an approved private diagnostic machine. Do not screenshot or share its default output. For shareable diagnostics, use `-RedactSensitive -SaveLogs` and still review the resulting logs manually.

`.alleva.local.ps1` and `alleva-api-test-logs/` are gitignored, but operators must still treat them as sensitive local files.

## Backend endpoints

The Windows desktop runtime exposes these routes:

```text
GET   /api/api-configuration
PATCH /api/api-configuration
POST  /api/api-configuration/pull-definitions
POST  /api/api-configuration/test
POST  /api/api-configuration/test-operation
GET   /api/api-configuration/sample-openapi.json
```

The privileged endpoints require an authenticated admin bearer token. The sample OpenAPI JSON endpoint is intentionally non-sensitive and exists so local smoke tests can validate the pull-definition logic without live Alleva credentials or internet access.

## Logging

The API configuration workflow uses the app's existing forensic audit service. It records:

- API configuration reads
- API configuration updates
- whether a key was added or cleared, without recording the key itself
- whether a client-credentials token request succeeded, without recording the token or secret
- definition-pull attempts and outcomes
- specific API operation test attempts and non-secret outcomes
- probe count and selected definition URL when found
- generated report metadata without API keys, bearer tokens, passwords, or external response secrets

The low-level connectivity service also emits standard Python logger warnings for request failures or HTTP errors.

## Windows 10 and 11 notes

The implementation is plain Python/FastAPI/SQLite/PowerShell and follows the current local Windows runtime design. It does not add Docker, PostgreSQL, or unusual end-user prerequisites. On a source checkout, the browser UI may still require Node.js/npm to build or refresh `frontend\dist`; Version 1.3.0 preflight keeps the stale-build warning behavior when the served React build may be stale. The API configuration page is served directly by the FastAPI desktop runtime and remains available even when the React build is missing.

## Offline validation path

The backend unit test `backend/tests/test_api_connectivity.py` uses `httpx.MockTransport` to validate URL discovery, API-key header injection, client-credentials token handling, OpenAPI summary extraction, operation-form extraction, required-field validation, selected-operation request execution, timeout/error handling, report generation, saved-key encryption, and result/audit redaction without calling the live Alleva API.

Run backend tests from a configured repo checkout with:

```powershell
$env:PYTHONPATH = "$PWD\backend"
.\backend\.venv\Scripts\python.exe -m pytest .\backend\tests -q
```

Run the Windows stack smoke tests with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-local-app-stack.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-api-configuration-local.ps1
```

## Boundary status language

The app supports configuration and connectivity testing without pretending to import live Alleva patient data. The intended status language is:

- **configured but not connected** when local vendor/base URL/API key settings have been saved but no successful probe has run
- **definition discovered** when an OpenAPI/Swagger definition is found and summarized
- **connectivity passed** when a probe succeeds and returns non-secret metadata such as HTTP status, selected definition URL, title/version, path count, schema count, security scheme names, and sample paths
- **client-credentials token blocked** when the token endpoint returns an error such as HTTP 400
- **patient import unavailable until credentials/endpoint mapping are provided** for live patient-data import

Keep live operation tests blocked until R3/Alleva confirms the exact client ID, secret, scopes, tenant, and auth style. Do not fake live import without official tenant credentials and endpoint mapping.

## Local report files

Redacted app API harness report files are written below:

```text
%LOCALAPPDATA%\IZ Clinical Notes Analyzer\api-reports
```

The simpler standalone connectivity script writes below:

```text
%LOCALAPPDATA%\IZ Clinical Notes Analyzer\api-connectivity-reports
```

These report files may include endpoint URLs, HTTP status codes, OpenAPI metadata, and redacted response summaries. They must not include saved API keys, one-time pasted keys, bearer tokens, passwords, external response secrets, or PHI.
