# API Configuration and Connectivity Test

Date: 2026-06-30

Applies to: IZ Clinical Notes Analyzer Beta Version `1.4.6-beta.1` / build `2026.06.30.1` local Windows desktop runtime.

## V2 beta.2 contract and release boundary

The active V2 prerelease is `2.0.0-beta.2` / build `2026.07.11.1` / channel `beta-local-desktop-v2`. Saved credentials remain write-only and encrypted at rest; release validation must use synthetic fixtures and an isolated temporary local-app-data directory. Do not enter a production secret during release validation. Supervised R3/Alleva validation using approved non-PHI/test records remains an external gate, so beta.2 does not claim a live production connection or sync approval. See `docs/v2-beta/api-contract-alleva.md` and `docs/v2-beta/release-readiness-2026-07-11.md`.

## Where to open it

When running the Windows local desktop runtime, open:

```text
http://localhost:8000/api-configuration
```

Admins can also open the API harness from App settings. When opened from the app, the harness reuses the current signed-in admin session and does not require a second in-page admin login.

App settings is the source of truth for the one active Alleva/API connection. The API harness loads and saves that same active connection. Saved API endpoint profiles in App settings are optional presets; activating a profile copies its values into the active connection.

## What the page does

The API configuration page lets an admin:

1. Enter or update the API vendor/base URL.
2. Enter an API key for a one-time test or save it for later use.
3. Enter OAuth2 client-credentials values for a one-time test or save the client ID/token URL plus encrypted client secret.
4. Save the OpenAPI/Swagger JSON URL used for readiness checks and operation tests.
5. Select the OAuth token auth style that matches the provider: body credentials, Basic auth, URL-encoded Basic auth, try-both, or try-all supported styles.
6. Pull OpenAPI/Swagger definitions from a Swagger UI page or direct JSON URL.
7. Test connectivity from inside the running app.
8. Pick an operation found in the loaded API definition and test that specific API call.
9. Fill a generated test form based on the selected operation's required path, query, header, and JSON body fields.
10. Run the Alleva `ALL Patient Records` pull after authentication/connectivity is understood.
11. Run the Alleva patient-centered treatment-plan harness pulls for all patients, active patients, or one canonical `patient_id`.
12. Copy tab-separated `ALL Patient Records` output into Excel when needed.
13. Review non-secret test results, including probed URLs, HTTP status codes, discovered OpenAPI title/version, path counts, schema counts, security scheme names, sample paths, token-request status, operation-test responses, patient-record pull status, treatment-plan pull status, response file paths, and redacted JSON report payloads.

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

Alleva has confirmed it does not currently support FHIR. Active Alleva integration in this app is REST/OpenAPI/HL7-readiness only. The public Alleva Swagger UI (`https://api.allevasoft.com/swagger/index.html`) and OpenAPI JSON (`https://api.allevasoft.com/swagger/v1/swagger.json` or `/swagger/v2/swagger.json`) belong in the OpenAPI URL/API harness fields. `https://api.allevasoft.com/advanced-form-elements` is a protected Alleva REST operation path.

For Alleva OAuth client credentials, pasting the R3/Alleva-provided client ID and client secret is normal. The secret is write-only after save: browser responses return only configured flags, not the stored secret. If R3 has multiple candidate endpoints or environments, save them as endpoint profiles, then activate the one that should become the active connection.

When the active connection has a saved client ID, token URL, and encrypted client secret, the standalone harness defaults to OAuth client-credentials mode so definition pulls, operation tests, and the `ALL Patient Records` pull reuse the saved ID/secret without showing the secret in the browser.

## Alleva ALL Patient Records pull

The standalone harness is organized as a step-by-step workflow: use the current admin session, load/save active API settings, test authentication/connectivity, then run `ALL Patient Records`. The user-facing quick-pull area keeps one action only.

`ALL Patient Records` uses the public Alleva v1 Swagger operation `GET /clients`. On June 20, 2026, the public Swagger JSON still listed `GET /clients`, `GET /treatment-plans`, and `GET /treatment-reviews` with these parameters: `Limit`, `Cursor`, optional `StartDate`/`EndDate`, `fields`, `api-version`, and `X-Version`.

The default `ALL Patient Records` payload includes:

- `auth_mode: client_credentials`
- active App settings base URL, token URL, token auth style, client ID, and saved encrypted client secret usage
- `GET /clients`
- `Limit`, `Cursor`, `api-version`, `X-Version`, optional `StartDate`/`EndDate`, and selected `fields`
- `max_pages` for bounded cursor pagination

The backend returns a bounded operational table with canonical Alleva `patient_id` from `/clients.id`, display/reference `source_id`, `status_id`, `status_label`, admission date, client flag, planned discharge date, level of care, facility, primary clinician, and first contact date. Patient names and addresses returned by Alleva are ignored/redacted and are not used for local matching. `planned_discharge_date` is not actual discharge status; active/discharged status uses `status.id` when present. It also returns TSV text intended for Excel copy/paste. Operators should still treat the output as sensitive because patient IDs and treatment context can be regulated data. The app does not write raw quick-pull rows to audit details or report files; audit records store only the report type, operation, auth mode, counts, and outcome.

The same backend quick-pull endpoint also supports the admin-only dry-run report `patient_treatment_plan_aggregates`. That report reads `GET /clients`, `GET /treatment-plans`, and `GET /treatment-reviews` into the local `PatientTreatmentPlanAggregate` shape without arming live sync. It returns JSON aggregates plus diagnostics for endpoint coverage, identifier matching, unmatched plans/reviews, diagnosis reconciliation, completeness, and due-date status. It does not return raw upstream payloads, patient names, filenames, client secrets, bearer tokens, or treatment-plan narrative text. See [`docs/alleva-patient-treatment-plan-aggregate.md`](alleva-patient-treatment-plan-aggregate.md).

For the end-to-end implementation map from API source rows into local treatment-plan tables, deterministic status, selected-client aggregate payloads, and the Treatment Plans UI, see [`docs/patient-treatment-plan-handling.md`](patient-treatment-plan-handling.md).

## Alleva treatment-plan harness pulls

The standalone harness includes production-style patient-centered pulls directly after `Pull ALL Patient Records`:

- `Pull Patient-Centered Treatment Plans`
- `Pull Active Patient-Centered Treatment Plans`
- `Pull Single Patient Treatment Plans`

These production-style actions call `GET /clients` first, then call `GET /treatment-plans?ClientId={patient_id}` for each selected canonical `/clients.id`. The query parameter is case-sensitive: `ClientId` is correct; lowercase `clientId` is not used in the production patient-plan path.

The diagnostic `Diagnostic: Pull All Treatment Plans` action remains available for broad endpoint inspection. It calls `GET /treatment-plans` without patient-centered alignment and must not be treated as the production patient-to-plan matching method.

Patient-centered treatment-plan responses show patient ID, status ID/label, exact `ClientId` endpoint URL, treatment-plan IDs, raw client ref, extracted patient ID, join validation, `isActive`, `isComplete`, `isInitialTP`, plan dates, nested content counts, warnings, and review-data availability. `nextReviewDue` remains unavailable unless a trusted treatment-review ID is supplied from another approved source. See [`docs/alleva-patient-treatment-plan-data-contract.md`](alleva-patient-treatment-plan-data-contract.md).

## Alleva REST treatment-plan sync

Beta `1.4.6-beta.1` keeps the separate Alleva REST treatment-plan sync configuration and removes active FHIR/SMART-on-FHIR fields, discovery, import-plan routes, scopes, defaults, and validation requirements from Alleva workflows. This is the path that matches the root `Test-AllevaApi.ps1` script: it uses `https://api.allevasoft.com` as the REST API base URL, `https://api.allevasoft.com/swagger/v1/swagger.json` as the OpenAPI definition, and `https://authorization.allevasoft.com/connect/token` for OAuth client-credentials testing when credentials are provided.

This sync path is intended to pull source data from Alleva, then run R3's local deterministic Treatment Plan Timeliness compliance checks inside this app. Alleva is the source system, not the compliance decision engine.

When optional current-plan detail fetch is enabled, the app captures content counts and PHI-minimized structured content facts. It does not store raw treatment-plan narrative text; content facts retain source paths, text-present flags, redacted hashes, and non-name metadata needed for source coverage review.

Treatment-plan sync readiness maps records by patient/client ID by default. Name-only matches are intentionally disabled; records without an approved ID mapping remain unmapped instead of being guessed from patient names. App settings includes a separate validation-only name-fallback control for approved mapping investigations, but it stays off by default.

Alleva patient-name import/display is also a separate App settings control and stays off by default. When it is off, the sync stores generated `no-name-found_YYYY-MM-DD_HHMMSS` display labels for Alleva-sourced treatment-plan clients even if the `/clients` payload contains a name. Turning the setting off later redacts existing Alleva-sourced treatment-plan names again.

Manual sync status messages distinguish common failure stages for non-technical users:

- authentication/token request failed before endpoint calls
- token request succeeded but endpoint authorization/permission failed
- endpoint path, query parameter, or API version mapping failed
- network timeout or reachability failed
- endpoints returned no records
- sync completed with warnings
- sync completed successfully

Startup sync is disabled by default. Before enabling it, admins must confirm and document:

- R3/Alleva approval for live treatment-plan sync.
- Validated endpoints for active clients, treatment plans, treatment reviews, and any required signature/status detail endpoints.
- Pagination/cursor behavior, rate limits, date filters, and retry expectations.
- Authoritative response fields for active/discharged status, admission date, current level of care, treatment-plan kind, completion status, client signature date, staff/creator signature date, last modified/update date, and next review due date.
- Credential scopes and tenant/environment boundaries for R3 Recovery Services.
- Whether R3 has explicitly approved storing/displaying Alleva patient names, or whether the redacted default must remain in place.

If any required setting is missing, App settings lists the exact missing field and will not arm startup sync. The live sync route records a blocked status rather than importing partial or unmapped data.

## Periodic API readiness checks

Admins can turn on periodic safe Alleva/API checks from `App settings` after saving:

- REST API base URL
- OpenAPI URL
- token URL
- client ID
- encrypted client secret
- token auth style
- check interval in minutes

The settings form validates these fields before save. If one or more required values are missing, the modal lists the exact missing field names instead of using a generic failure message.

The background checker authenticates with the saved client ID/secret, applies the selected token auth style, and runs the same bounded OpenAPI/readiness probe used by the harness. App settings shows the last check time, status, message, last success/failure, and next scheduled check through the Review Source Discovery payload.

Periodic checks are readiness checks only. They do not import live patient charts or treatment plans until R3 has vendor endpoint mapping, pagination/rate limits, attachment handling, documentation, and compliance approval.

See also: [`docs/alleva-treatment-plan-data-coverage.md`](alleva-treatment-plan-data-coverage.md) for the Swagger-derived treatment-plan coverage matrix, ID mapping rules, unknown/unavailable source-data states, and test coverage references.

## API endpoint profiles

Admins can save multiple endpoint profiles for Alleva REST/OpenAPI testing from App settings. Each profile stores vendor label, adapter key, REST API base URL, OpenAPI URL, token URL, token auth style, client ID, encrypted client secret, timeout, active/default flags, and notes.

Browser responses return only configured flags for secrets. Activating a profile copies it into the active App settings API configuration used by readiness checks, operation tests, periodic checks, and approved REST treatment-plan sync. Profiles that are merely saved do not affect the app until activated.

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
POST  /api/api-configuration/alleva-quick-pull
GET   /api/api-configuration/sample-openapi.json
POST  /api/alleva/treatment-plan-sync/run
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
- Alleva patient-record pull report type, operation, counts, and outcome without raw returned rows
- probe count and selected definition URL when found
- generated report metadata without API keys, bearer tokens, passwords, or external response secrets

The low-level connectivity service also emits standard Python logger warnings for request failures or HTTP errors.

## Windows 10 and 11 notes

The implementation is plain Python/FastAPI/SQLite/PowerShell and follows the current local Windows runtime design. It does not add Docker, PostgreSQL, or unusual end-user prerequisites. On a source checkout, the browser UI may still require Node.js/npm to build or refresh `frontend\dist`; Beta 1.4.6-beta.1 preflight keeps the stale-build warning behavior when the served React build may be stale. The API configuration page is served directly by the FastAPI desktop runtime and remains available even when the React build is missing.

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

Keep live operation tests blocked until R3/Alleva confirms the exact client ID, secret, tenant, auth style, and endpoint mapping. Do not fake live import without official tenant credentials and endpoint mapping.

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
