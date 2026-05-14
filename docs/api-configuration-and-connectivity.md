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
6. Review non-secret test results, including probed URLs, HTTP status codes, discovered OpenAPI title/version, path counts, schema counts, security scheme names, and sample paths.

## Secret handling

API keys are never returned to the browser after save and are not written into audit-log details. Saved API keys are encrypted with the app's existing local secret-encryption envelope and stored in the local application database. The page may also use a pasted one-time API key without saving it.

## Backend endpoints

The Windows desktop runtime exposes these routes:

```text
GET   /api/api-configuration
PATCH /api/api-configuration
POST  /api/api-configuration/pull-definitions
POST  /api/api-configuration/test
GET   /api/api-configuration/sample-openapi.json
```

The privileged endpoints require an authenticated admin bearer token. The sample OpenAPI JSON endpoint is intentionally non-sensitive and exists so local smoke tests can validate the pull-definition logic without live Alleva credentials or internet access.

## Logging

The API configuration workflow uses the app's existing forensic audit service. It records:

- API configuration reads.
- API configuration updates.
- Whether a key was added or cleared, without recording the key itself.
- Definition-pull attempts and outcomes.
- Probe count and selected definition URL when found.

The low-level connectivity service also emits standard Python logger warnings for request failures or HTTP errors.

## Windows 10 and 11 notes

The implementation is plain Python/FastAPI/SQLite/PowerShell and follows the existing local Windows runtime design. It does not add Docker, PostgreSQL, or unusual user prerequisites. On a source checkout, the browser UI may still require Node.js/npm to build `frontend/dist`, but the API configuration page is served directly by the FastAPI desktop runtime and remains available even when the React build is missing.

## Offline validation path

The backend unit test `backend/tests/test_api_connectivity.py` uses `httpx.MockTransport` to validate URL discovery, API-key header injection, and OpenAPI summary extraction without calling the live Alleva API.

Run backend tests from a configured repo checkout with:

```powershell
$env:PYTHONPATH = "$PWD\backend"
.\backend\.venv\Scripts\python.exe -m pytest .\backend\tests -q
```

Run the existing Windows stack smoke test with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-local-app-stack.ps1
```

## Current limitation

The new API configuration routes are wired into the Windows desktop entrypoint, `app.desktop_main:app`, which is what the Windows startup script uses. The generic `app.main:app` entrypoint was not changed in this update.
