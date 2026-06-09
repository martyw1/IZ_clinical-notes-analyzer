# API Configuration and Connectivity Test

This app now includes a local, admin-only API configuration and connectivity-test workflow for the Alleva/API integration path.

## Where to open it

When running the Windows local desktop runtime, open:

```text
http://localhost:8000/api-configuration
```

The Windows startup script runs the desktop entrypoint:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\startup-windows-local.ps1
```

## What the page does

The API configuration page lets an admin:

1. Sign in with the existing local app admin account.
2. Enter or update the API vendor/base URL.
3. Enter an API key for a one-time test or save it for later use.
4. Pull OpenAPI/Swagger definitions from a Swagger UI page or direct JSON URL.
5. Test connectivity from inside the running app.
6. Pick any operation found in the loaded API definition and test that specific API call.
7. Fill a generated test form based on the selected operation's required path, query, header, and JSON body fields.
8. Review non-secret test results, including probed URLs, HTTP status codes, discovered OpenAPI title/version, path counts, schema counts, security scheme names, sample paths, operation-test responses, and redacted JSON report payloads.

## Operation test workbench

After a definition is loaded, the page builds an operation picker from the OpenAPI `paths` object. For each selected method/path, it derives a form from:

- path parameters, such as `{patient_id}`
- query parameters
- header parameters
- top-level JSON request-body fields
- required flags, types, enums, defaults, descriptions, and date formats where present

When an admin runs a selected API call test, the app sends the request from the local FastAPI backend using the configured base URL, one-time API key, or saved encrypted API key. The response shown in the browser includes status code, content type, timing when available, parsed JSON when the response is JSON, or a short body preview for non-JSON responses. API keys are injected into the outbound request but are not returned in the test result. Sensitive response field names such as tokens, secrets, passwords, authorization values, and API keys are redacted before display.

## Secret handling

API keys are never returned to the browser after save and are not written into audit-log details. Saved API keys are encrypted with the app's existing local secret-encryption envelope and stored in the local application database. The page may also use a pasted one-time API key without saving it. Generated report payloads redact saved keys, one-time keys, bearer strings, token-like query parameters, and sensitive fields from external API responses.

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

- API configuration reads.
- API configuration updates.
- Whether a key was added or cleared, without recording the key itself.
- Definition-pull attempts and outcomes.
- Specific API operation test attempts and non-secret outcomes.
- Probe count and selected definition URL when found.
- Generated report metadata without API keys, bearer tokens, passwords, or external response secrets.

The low-level connectivity service also emits standard Python logger warnings for request failures or HTTP errors.

## Windows 10 and 11 notes

The implementation is plain Python/FastAPI/SQLite/PowerShell and follows the existing local Windows runtime design. It does not add Docker, PostgreSQL, or unusual user prerequisites. On a source checkout, the browser UI may still require Node.js/npm to build or refresh `frontend/dist`; Version 1.0.3 preflight warns when the served React build may be stale. The API configuration page is served directly by the FastAPI desktop runtime and remains available even when the React build is missing.

## Offline validation path

The backend unit test `backend/tests/test_api_connectivity.py` uses `httpx.MockTransport` to validate URL discovery, API-key header injection, OpenAPI summary extraction, operation-form extraction, required-field validation, selected-operation request execution, timeout/error handling, report generation, saved-key encryption, and result/audit redaction without calling the live Alleva API.

Run backend tests from a configured repo checkout with:

```powershell
$env:PYTHONPATH = "$PWD\backend"
.\backend\.venv\Scripts\python.exe -m pytest .\backend\tests -q
```

Run the existing Windows stack smoke test with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-local-app-stack.ps1
```

## Runtime availability

The API configuration JSON routes are available from the main FastAPI app and the Windows desktop runtime. The browser page at `/api-configuration` is served by the desktop runtime used by the Windows startup script.

## Boundary status language

The app supports configuration and connectivity testing without pretending to import live Alleva patient data. The intended status language is:

- **configured but not connected** when local vendor/base URL/API key settings have been saved but no successful probe has run.
- **definition discovered** when an OpenAPI/Swagger definition is found and summarized.
- **connectivity passed** when a probe succeeds and returns non-secret metadata such as HTTP status, selected definition URL, title/version, path count, schema count, security scheme names, and sample paths.
- **patient import unavailable until credentials/endpoint mapping are provided** for live patient-data import. Do not fake live import without official tenant credentials and endpoint mapping.

Saved API keys are encrypted in the local database. After save, API responses return only `api_key_configured: true/false`; they do not return the key value.
