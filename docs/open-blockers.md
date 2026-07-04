# Open Blockers

Date: 2026-07-04

Applies to: IZ Clinical Notes Analyzer Beta Version `1.4.6-beta.1` / build `2026.06.30.1`.

Current app metadata is aligned in `VERSION`, `VERSION.json`, `frontend/package.json`, and `frontend/package-lock.json`.

Current patient treatment-plan handling is documented in `docs\patient-treatment-plan-handling.md`, including the local tables, approved ID matching, gated Alleva REST sync, aggregate diagnostics, deterministic evaluator, selected-client checklist output, and Treatment Plans UI files. The current documentation-state tracker is `docs\current-documentation-state.md`. The blockers below remain active boundaries for that implementation.

## LOC-Change Treatment-Plan Update Window

Status: unvalidated.

The required treatment-plan update window after a level-of-care change is not confirmed by R3/Marleigh. The Version 1 implementation must keep this value configurable and must visibly mark it as unvalidated in admin/App settings UI, the Treatment Plan Checklist, the timeliness dashboard, and operator documentation.

Current implementation state: Beta 1.4.6-beta.1 defaults the manager-editable LOC-change preset to 7 calendar days, but keeps the validation checkbox off and keeps the UI/docs marked unvalidated until R3/Marleigh confirms the final rule. The timeliness work queue/detail output marks LOC-change/date-anchor conflicts as `Needs Review`, `Missing Data`, or `Conflicting Evidence` while this blocker remains unresolved. The selected-client detail view shows source-document `Next Review Due`, date-clock anchor, date-clock due date, LOC-change due date, selected-client 42-step checklist evaluation, and saved manager status/comment notes side by side. The checklist content version remains `1.2.0` and includes a dedicated step to hold the LOC-change deadline as unresolved until R3 confirms it.

Until R3 confirms the rule, do not hard-code a final number of days and do not silently treat a LOC-change case as compliant. If source evidence is incomplete or conflicting, return `Needs Review` or `Missing Data` according to the deterministic rules.

Required resolution evidence:

- R3/Marleigh confirms the exact update window after LOC change.
- R3 confirms whether the window is calendar days or business days.
- R3 confirms whether the trigger date is the LOC-change date, signed review date, admission date, or another source evidence date.
- R3 confirms the user-visible label and default status for overdue LOC-change updates.

## Alleva REST Treatment-Plan Sync Approval and Mapping

Owner: R3 + Alleva

Status: Open.

Current implementation state: Beta 1.4.6-beta.1 uses Alleva REST/OpenAPI/HL7-readiness only and can normalize approved REST payloads into the R3 timeliness engine. Startup sync remains disabled by default and cannot be armed until the admin confirms R3/Alleva live-sync approval and validated endpoint mapping. Manual retrieval is available from the Status Dashboard EMR/API card, the Treatment Plans tab, and App Settings sync controls, but all of those paths use the same approval and mapping gates. App settings presents one active Alleva/API connection; saved endpoint profiles are presets that must be activated into the active connection before they affect readiness checks, periodic checks, API harness tests, or approved REST sync.

Current patient-centered API harness contract:

```text
GET /clients
GET /treatment-plans?ClientId={patient_id}
```

Current patient-centered rules:

- `patient_id` is the canonical Alleva client ID from `GET /clients.id`.
- `ClientId` is case-sensitive.
- Treatment-plan ownership is validated by parsing the treatment-plan `client` value, expected as `/clients/{id}`.
- `chartId`, `externalId`, `mrn`, `clientName`, lowercase `clientId`, `uniqueId`, and `source_id` are not production treatment-plan join keys.
- Treatment-review list data is not a reliable patient join source. Do not join treatment reviews by `clientName`.

The API harness also includes a `patient_treatment_plan_aggregates` dry-run report for combining `/clients`, `/treatment-plans`, and safely attributable treatment-review evidence into PHI-minimized aggregate diagnostics. This remains readiness/testing evidence only. It does not remove the live sync approval, endpoint mapping, tenant credential, pagination/rate-limit, PHI handling, or LOC-change blocker requirements.

Current Swagger/OpenAPI mapping evidence: the Alleva Swagger/OpenAPI mapping export generated on `2026-06-21 14:59:49` is now available to the documentation set and is reflected in `docs\alleva-treatment-plan-data-coverage.md` and `docs\alleva-patient-treatment-plan-aggregate.md`. The export was derived from the public Alleva Swagger UI and v1 Swagger JSON and listed 424 endpoints and 2303 unique fields. This resolves the old documentation-only note that the mapping files were unavailable, but it does **not** prove runtime production payloads or approve live sync. Runtime fields can differ from Swagger, and endpoints without Swagger response schemas can still require live validation.

Current diagnostic behavior: manual sync reports the specific failing stage instead of surfacing generic exception text. If a saved connection can authenticate but required protected endpoint calls are not authorized, App Settings identifies this as endpoint authorization/permission failure and asks R3/Alleva to confirm tenant access, token audience/scope, endpoint permission, and API version.

Required before live startup sync:

- Confirm which Alleva tenant/environment and credentials R3 may use.
- Confirm active-client endpoint and active/discharged filtering.
- Confirm treatment-plan endpoint behavior, including patient-centered `ClientId` casing in the approved tenant.
- Confirm treatment-plan detail, diagnosis, and advanced-form endpoint behavior if those fields are needed for completeness review.
- Confirm whether a trusted source can supply stable treatment-review IDs for direct treatment-review detail retrieval.
- Confirm pagination/cursor/date range behavior and rate limits.
- Confirm authoritative fields for admission date, current LOC, treatment-plan kind, completion status, staff/creator signature date, client signature date, last updated date, and next review due date.
- Confirm PHI handling and audit/log minimum-necessary policy for imported patient IDs and local display names.

Required resolution evidence:

- R3/Alleva confirms the exact approved endpoints and runtime payload fields.
- The patient-centered harness proves a synthetic or approved non-PHI patient can be retrieved with `GET /clients` plus `GET /treatment-plans?ClientId={patient_id}`.
- The returned treatment-plan `client` value validates to `/clients/{id}` for the queried patient.
- Required signature/date/completion fields are present or documented as unavailable with deterministic missing-data behavior.
- A documented decision exists for treatment-review due-date availability through a trusted review ID or an explicit unavailable state.

## Windows Packaging and Validation

Status: in progress for Version 1.

The recommended long-term end-user path is a packaged signed `.exe` or `.msi` with bundled runtime, built frontend assets, shortcuts, repair/modify support, uninstall support, and local app-data preservation by default.

Current implementation state: Beta 1.4.6-beta.1 keeps Windows preflight, prompted source-checkout setup/start wrappers, a release-folder builder, double-click install/launch/diagnostics/backup/data-preserving uninstall/complete uninstall commands, built frontend assets, Start Menu and desktop shortcut creation, AppData preflight reports, redacted diagnostics bundles, backup zips, manual-upload delete-button usability fixes, selected-client 42-step checklist detail visibility, Status Dashboard branding, admin-only clear-patient-data controls, and legacy SQLite audit-log repair for retired FHIR-era audit columns. The package is not code-signed and is not a full MSI/MSIX with repair/modify support.

Required resolution evidence:

- Source checkout validation passes on the target Windows 10/11 laptop.
- `/api/version` and the UI footer show `1.4.6-beta.1` and `beta-local-desktop` on that machine.
- The `Treatment plans` tab shows the updated evidence queue, selected-client 42-step checklist evaluation with manager notes, and footer version `Beta v1.4.6-beta.1`, proving the date-clock/source-evidence workflow UI is the currently served build.
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
- The current patient-centered contract uses `GET /clients` and `GET /treatment-plans?ClientId={patient_id}`.
- Advanced-form endpoints remain protected operation paths and still require approved runtime access before use.
- Prior supplied client-credentials attempts did not produce a working access-token response.
- Sanitized report files are written under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\api-connectivity-reports`.

Required resolution evidence:

- R3/Alleva confirms the exact tenant/client values and token request requirements.
- A token request succeeds with an approved non-PHI operation test against a synthetic or vendor-approved test patient.

## Frontend Vitest and Direct TypeScript Check

Status: resolved for Vitest on this Windows 11 laptop.

Frontend Vitest and production build completed locally on 2026-06-30 for Beta 1.4.6-beta.1. Direct `tsc --noEmit` is not a defined package script; use the supported Vitest/build workflow unless a future TypeScript-only script is added.

Required resolution evidence:

- Keep `npm test -- --run` passing locally and in CI.
- Keep `npm run build` passing locally and in CI.
