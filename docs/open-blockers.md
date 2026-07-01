# Open Blockers

Date: 2026-06-30

Applies to: IZ Clinical Notes Analyzer Beta Version `1.4.6-beta.1` / build `2026.06.30.1`.

Current app metadata is aligned in `VERSION`, `VERSION.json`, `frontend/package.json`, and `frontend/package-lock.json`.

Current patient treatment-plan handling is documented in `docs\patient-treatment-plan-handling.md`, including the local tables, approved ID matching, gated Alleva REST sync, aggregate diagnostics, deterministic evaluator, selected-client checklist output, and Treatment Plans UI files. The blockers below remain active boundaries for that implementation.

## LOC-Change Treatment-Plan Update Window

Status: unvalidated.

The required treatment-plan update window after a level-of-care change is not confirmed by R3/Marleigh. The Version 1 implementation must keep this value configurable and must visibly mark it as unvalidated in admin/App settings UI, the Treatment Plan Checklist, the timeliness dashboard, and operator documentation.

Current implementation state: the setting exists in the database and admin App settings UI. Beta 1.4.6-beta.1 defaults the manager-editable LOC-change preset to 7 calendar days, but keeps the validation checkbox off and keeps the UI/docs marked unvalidated until R3/Marleigh confirms the final rule. The timeliness work queue/detail output marks LOC-change/date-anchor conflicts as `Needs Review`, `Missing Data`, or `Conflicting Evidence` while this blocker remains unresolved. The selected-client detail view shows source-document `Next Review Due`, date-clock anchor, date-clock due date, LOC-change due date, selected-client 42-step checklist evaluation, and saved manager status/comment notes side by side. The checklist content version remains `1.2.0` and includes a dedicated step to hold the LOC-change deadline as unresolved until R3 confirms it.

## Alleva REST treatment-plan sync approval and mapping

Owner: R3 + Alleva

Status: Open

Current implementation state: Beta 1.4.6-beta.1 uses Alleva REST/OpenAPI/HL7-readiness only and can normalize approved REST payloads into the R3 timeliness engine. Startup sync remains disabled by default and cannot be armed until the admin confirms R3/Alleva live-sync approval and validated endpoint mapping. Manual retrieval is available from the Status Dashboard EMR/API card and the App Settings sync controls, but both use the same approval and mapping gates. App settings now presents one active Alleva/API connection; saved endpoint profiles are presets that must be activated into the active connection before they affect readiness checks, periodic checks, API harness tests, or approved REST sync.

The API harness also includes a `patient_treatment_plan_aggregates` dry-run report for combining `/clients`, `/treatment-plans`, and `/treatment-reviews` into PHI-minimized aggregate diagnostics. This remains readiness/testing evidence only. It does not remove the live sync approval, endpoint mapping, tenant credential, pagination/rate-limit, PHI handling, or LOC-change blocker requirements.

Current diagnostic behavior: manual sync now reports the specific failing stage instead of surfacing generic exception text. If client credentials obtain a token but Alleva returns `401 Unauthorized` or `403 Forbidden` for `/clients`, `/treatment-plans`, or `/treatment-reviews`, the App Settings status identifies this as endpoint authorization/permission failure and asks R3/Alleva to confirm tenant access, token audience/scope, endpoint permission, and API version.

Required before live startup sync:

- Confirm which Alleva tenant/environment and credentials R3 may use.
- Confirm active-client endpoint and active/discharged filtering.
- Confirm treatment-plan and treatment-review endpoints.
- Confirm pagination/cursor/date range behavior and rate limits.
- Confirm authoritative fields for admission date, current LOC, treatment-plan kind, completion status, staff/creator signature date, client signature date, last updated date, and next review due date.
- Confirm PHI handling and audit/log minimum-necessary policy for imported patient IDs and local display names.

Until R3 confirms the rule, do not hard-code a final number of days and do not silently treat a LOC-change case as compliant. If source evidence is incomplete or conflicting, return `Needs Review` or `Missing Data` according to the deterministic rules.

Required resolution evidence:

- R3/Marleigh confirms the exact update window after LOC change.
- R3 confirms whether the window is calendar days or business days.
- R3 confirms whether the trigger date is the LOC-change date, signed review date, admission date, or another source evidence date.
- R3 confirms the user-visible label and default status for overdue LOC-change updates.

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

Status: blocked by vendor/auth response.

The public Alleva Swagger UI and OpenAPI JSON are reachable, but the provided client-credentials token request returned HTTP 400 on 2026-06-12. On 2026-06-17, the public Swagger UI and both `/swagger/v1/swagger.json` and `/swagger/v2/swagger.json` were reachable and described Alleva REST API operations. Alleva later confirmed it does not currently support FHIR, so active app configuration now excludes FHIR/SMART-on-FHIR fields, discovery, scopes, and import-plan workflows. The app and `scripts\test-alleva-api-connectivity.ps1` support client-credentials token testing, keep returned access tokens in memory only, and redact token/secret values from reports and audit logs.

Current evidence:

- `https://api.allevasoft.com/swagger/index.html`: HTTP 200.
- `https://api.allevasoft.com/swagger/v1/swagger.json`: HTTP 200, 942906 bytes.
- `https://api.allevasoft.com/swagger/v2/swagger.json`: HTTP 200.
- On 2026-06-20, the public v1 Swagger JSON listed `GET /clients`, `GET /treatment-plans`, and `GET /treatment-reviews` with `Limit`, `Cursor`, optional `StartDate`/`EndDate`, `fields`, `api-version`, and `X-Version`.
- `https://api.allevasoft.com/advanced-form-elements`: HTTP 401 without credentials; protected REST operation path.
- `https://authorization.allevasoft.com/connect/token`: HTTP 400 for the provided client ID/secret using form-encoded `grant_type=client_credentials`.
- HTTP Basic client-auth with `grant_type=client_credentials` was also attempted and returned HTTP 400.
- Sanitized report files were written under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\api-connectivity-reports`.

Required resolution evidence:

- R3/Alleva confirms the exact tenant/client ID and client secret.
- R3/Alleva confirms whether a scope, audience, tenant identifier, or alternate token endpoint is required.
- R3/Alleva confirms whether credentials must be sent in the form body or HTTP Basic auth.
- A token request returns HTTP 200 with an access token, followed by one approved non-PHI operation test against a synthetic or vendor-approved test patient.

## Frontend Vitest and Direct TypeScript Check

Status: resolved for Vitest on this Windows 11 laptop.

Frontend Vitest and production build completed locally on 2026-06-30 for Beta 1.4.6-beta.1. Direct `tsc --noEmit` is not a defined package script; use the supported Vitest/build workflow unless a future TypeScript-only script is added.

Required resolution evidence:

- Keep `npm test -- --run` passing locally and in CI.
- Keep `npm run build` passing locally and in CI.
