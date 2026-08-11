# Open Blockers

Date: 2026-07-11

Applies to: IZ Clinical Notes Analyzer Version `2.0.0-beta.2` / build `2026.07.11.1`.

Current app metadata is aligned in `VERSION`, `VERSION.json`, `frontend/package.json`, and `frontend/package-lock.json`.

## Production Release Gates

Status: **open external gates; no production claim.**

- R3 and Alleva must approve and supervise a live contract and end-to-end sync validation using approved non-PHI/test records.
- The exposed credential must be rotated, all downstream copies inventoried, and the required history-remediation procedure explicitly approved before any destructive rewrite or force push.
- R3 IT/records owners must decide whether code signing is required and define retention/legal-hold handling for release, diagnostic, backup, and incident records.
- Final validation must run in a clean isolated local-app-data environment using synthetic data only. Details and the required evidence boundary are in `docs/v2-beta/release-readiness-2026-07-11.md`.

Current V2 treatment-plan handling is documented in `docs\v2-beta\`, including product scope, data contract, Alleva/API contract, rules contract, UI workflows, security/privacy/audit notes, validation evidence, and task coverage audit. Version 1 treatment-plan handling remains archived for historical reference under `deprecated\v1\`. The blockers below remain active boundaries for the V2 beta runtime.

## LOC-Change Treatment-Plan Update Window

Status: unvalidated for Version 2.0 Beta.

The required treatment-plan update window after a level-of-care change is not confirmed by R3/Marleigh. The active V2 implementation must keep this value configurable and must visibly mark it as unvalidated in readiness, settings UI, Treatment Plans/checklist evidence, and operator documentation.

Current implementation state: Version 2.0 Beta keeps the LOC-change update window visibly unresolved in Settings, Treatment Plans, checklist evidence, V2 docs, and validation notes. The placeholder remains 7 calendar days and must stay configurable until R3/Marleigh confirms the final rule. When an imported aggregate has more than one LOC history entry while the setting is unvalidated, the V2 evaluator returns `Needs Review`; missing required evidence returns `Missing Data` and malformed dates return `Unable to Evaluate`.

Until R3 confirms the rule, do not hard-code a final number of days and do not silently treat a LOC-change case as compliant. If source evidence is incomplete or conflicting, return `Needs Review` or `Missing Data` according to the deterministic rules.

Required resolution evidence:

- R3/Marleigh confirms the exact update window after LOC change.
- R3 confirms whether the window is calendar days or business days.
- R3 confirms whether the trigger date is the LOC-change date, signed review date, admission date, or another source evidence date.
- R3 confirms the user-visible label and default status for overdue LOC-change updates.

## Alleva REST Treatment-Plan Sync Validation

Owner: R3

Status: Mapping accepted for operator-triggered use; supervised live validation remains open.

Current implementation state: Version 2.0 Beta includes encrypted saved OAuth configuration, bounded OpenAPI/operation testing, and an admin-only read-only treatment-plan sync job. The sync remains off by default and requires a client ID, encrypted secret, API and sync enablement, and explicit live read-only tenant authorization. The published Alleva v1 mapping is applied automatically and stored as an encrypted versioned contract when a pull begins; there is no separate mapping-approval form. Startup sync remains disabled. Supervised validation against R3's live tenant, credential rotation, and compliance release approval remain open production-readiness tasks.

Current operational import contract:

```text
GET /clients
GET /treatment-plans (bounded global pages)
```

Current operational rules:

- `/clients.mrn` is the canonical local patient key.
- `/clients.id` is stored separately as the Alleva source relationship key.
- Treatment-plan ownership is validated from `client.id`, `client.route`, or a string `/clients/{id}`, then mapped to the corresponding MRN.
- The complete bounded global treatment-plan collection is read across active, inactive, discharged, and deleted client states so older plans are retained.
- `chartId`, `externalId`, `clientName`, lowercase `clientId`, `uniqueId`, and `source_id` are not substitutes for MRN.
- Treatment-review list data is not a reliable patient join source. Do not join treatment reviews by `clientName`.

The API harness also includes a `patient_treatment_plan_aggregates` dry-run report for combining `/clients`, `/treatment-plans`, and safely attributable treatment-review evidence into PHI-minimized aggregate diagnostics. This remains readiness/testing evidence only. It does not remove the tenant credential, API/sync enablement, pagination/rate-limit, PHI handling, supervised live validation, or LOC-change blocker requirements.

Current Swagger/OpenAPI mapping evidence: the Alleva Swagger/OpenAPI mapping export generated on `2026-06-21 14:59:49` is now available to the documentation set and is reflected in `docs\alleva-treatment-plan-data-coverage.md` and `docs\alleva-patient-treatment-plan-aggregate.md`. The export was derived from the public Alleva Swagger UI and v1 Swagger JSON and listed 424 endpoints and 2303 unique fields. This resolves the old documentation-only note that the mapping files were unavailable, but it does **not** prove runtime production payloads or approve live sync. Runtime fields can differ from Swagger, and endpoints without Swagger response schemas can still require live validation.

Current diagnostic behavior: manual sync reports the specific failing stage instead of surfacing generic exception text. If a saved connection can authenticate but required protected endpoint calls are not authorized, App Settings identifies this as endpoint authorization/permission failure and asks R3/Alleva to confirm tenant access, token audience/scope, endpoint permission, and API version.

Required before live startup sync:

- Confirm which Alleva tenant/environment and credentials R3 may use.
- Confirm client endpoint MRN completeness and active/discharged lifecycle semantics.
- Confirm global treatment-plan pagination and date-filter behavior in the approved tenant.
- Confirm treatment-plan detail, diagnosis, and advanced-form endpoint behavior if those fields are needed for completeness review.
- Confirm whether a trusted source can supply stable treatment-review IDs for direct treatment-review detail retrieval.
- Confirm pagination/cursor/date range behavior and rate limits.
- Confirm authoritative fields for admission date, current LOC, treatment-plan kind, completion status, staff/creator signature date, client signature date, last updated date, and next review due date.
- Confirm PHI handling and audit/log minimum-necessary policy for imported patient IDs and local display names.

Required resolution evidence:

- R3/Alleva confirms the exact approved endpoints and runtime payload fields.
- The operational importer proves that approved non-PHI clients supply both `id` and `mrn`, and that bounded global treatment-plan pagination reaches a terminal page.
- Every imported treatment-plan relationship validates to one observed `/clients.id` and is stored under the matching `/clients.mrn`.
- Required signature/date/completion fields are present or documented as unavailable with deterministic missing-data behavior.
- A documented decision exists for treatment-review due-date availability through a trusted review ID or an explicit unavailable state.

## Windows Packaging and Validation

Status: beta.2 synthetic package and CMD-launcher validation passed on 2026-07-11. Signed MSI/MSIX remains open pending the R3 IT deployment decision.

The recommended long-term end-user path is a packaged signed `.exe` or `.msi` with bundled runtime, built frontend assets, shortcuts, repair/modify support, uninstall support, and local app-data preservation by default.

Current implementation state: Version 2.0 Beta keeps Windows preflight, source-checkout local stack testing, API configuration smoke testing, release-folder builder, built frontend assets, required-file validation, and forbidden-file scans for the release folder and zip. The package is not code-signed and is not a full MSI/MSIX with repair/modify support.

Required resolution evidence:

- Source checkout validation passes on the target Windows 10/11 laptop.
- `/api/version` and the UI footer show `2.0.0-beta.2` and `beta-local-desktop-v2` on that machine.
- The `Treatment Plans` workbench shows the V2 evidence queue, selected-client 42-step checklist evidence, manager action controls, and footer version `Version 2.0 Beta | 2.0.0-beta.2 | beta-local-desktop-v2`, proving the V2 workflow UI is the currently served build.
- `scripts\test-local-app-stack.ps1` and `scripts\test-api-configuration-local.ps1` pass with synthetic data only.
- The Diagnostics shortcut creates a redacted support zip that excludes uploads, SQLite databases, generated reports, and raw `.env` values.
- The Backup shortcut creates a full local-data backup zip under the user's Documents folder and warns that it can contain clinical data and encryption material.
- Normal uninstall removes app files and shortcuts while preserving `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.
- Complete uninstall requires typing `REMOVE IZ DATA` and removes app files, shortcuts, and `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.
- A signed installer or MSI/MSIX exists, bundles runtime/assets, supports repair/modify/uninstall, and preserves `%LOCALAPPDATA%\IZ Clinical Notes Analyzer` by default.

## Alleva Client-Credentials Token Request

Status: blocked by vendor/auth response until R3/Alleva supplies a confirmed working tenant credential set.

The public Alleva Swagger UI and OpenAPI JSON are reachable, and the supplied Swagger/OpenAPI field mapping export is available as documentation evidence. Alleva confirmed it does not currently support FHIR, so active app configuration excludes FHIR/SMART-on-FHIR fields, discovery, scopes, and import-plan workflows. The app and simple standalone connectivity script support client-credentials token testing, keep returned access tokens in memory only, and redact token/secret values from reports and audit logs.

Current evidence:

- Prior validation reached the public Alleva Swagger UI and v1/v2 Swagger JSON.
- The 2026-06-21 Swagger/OpenAPI mapping export lists 424 endpoints and 2303 unique fields.
- The current operational contract uses `GET /clients` plus bounded global `GET /treatment-plans` pages; the patient-filtered `ClientId` route remains available only in diagnostic harness flows.
- Advanced-form endpoints remain protected operation paths and still require approved runtime access before use.
- Prior supplied client-credentials attempts did not produce a working access-token response.
- Sanitized report files are written under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\api-connectivity-reports`.

Required resolution evidence:

- R3/Alleva confirms the exact tenant/client values and token request requirements.
- A token request succeeds with an approved non-PHI operation test against a synthetic or vendor-approved test patient.

## Frontend Vitest and Direct TypeScript Check

Status: resolved for Vitest on this Windows 11 laptop.

Frontend Vitest and production build completed locally on 2026-07-08 for Version 2.0 Beta. Direct `tsc --noEmit` is not a defined package script; use the supported Vitest/build workflow unless a future TypeScript-only script is added.

Required resolution evidence:

- Keep `npm test -- --run` passing locally and in CI.
- Keep `npm run build` passing locally and in CI.
