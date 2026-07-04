# Current Documentation State

Date: 2026-07-04

Applies to: IZ Clinical Notes Analyzer Beta Version `1.4.6-beta.1` / build `2026.06.30.1` on the `beta-local-desktop` channel.

## Purpose

This file is the current documentation alignment tracker. It summarizes what the active docs should say after the July 2026 patient-centered Alleva treatment-plan clarification and the current Swagger/OpenAPI mapping export review.

Historical validation reports, PRD notes, and earlier implementation analyses may keep the version/date they originally validated. Do not reinterpret historical reports as current production state unless they explicitly say they apply to `1.4.6-beta.1`.

## Current Product State

- The app is a local-first Windows 10/11 desktop-style FastAPI + React/Vite app served from `http://localhost:8000`.
- The normal non-technical R3 path is a prepared release folder with built frontend assets, no Windows administrator requirement, and no Docker, PostgreSQL, Git, Node.js, command-line work, cloud hosting, or database administrator requirement for ordinary use.
- Local runtime data lives under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`, not in the repo or installed app folder.
- The prepared Windows release folder installs per user under `%LOCALAPPDATA%\Programs\IZ Clinical Notes Analyzer` and includes double-click install, launch, stop, diagnostics, backup, data-preserving uninstall, and complete-uninstall commands.
- The current package is still a release-folder/zip package, not a signed MSI/MSIX with repair/modify support.

## Current Treatment-Plan State

- `config\checklists\treatment-plan-v1.json` remains the canonical 42-step checklist source.
- Checklist content version remains `1.2.0`; app version remains separate at `1.4.6-beta.1`.
- The Treatment Plans tab is the admin/office-manager Treatment Plan Timeliness work queue.
- The selected-client detail includes the `42-Step Checklist Evaluation`, source evidence, date-clock results, current-plan content summary, manager criterion status/comments, manual overrides, audit context, and CSV/JSON export paths.
- Patient ID is the only accepted patient identifier for current upload/import/display/export/log workflows. Patient names, addresses, contact details, original filenames, attachment URLs, and author/custodian labels must not be local display labels or matching keys.
- Alleva patient-name import/display remains opt-in and off by default. Name-only matching remains disabled by default and validation-only.
- The LOC-change treatment-plan update window remains unresolved. The app keeps the manager-editable 7-calendar-day preset, but docs and UI must continue marking the rule as unvalidated until R3/Marleigh confirms the exact rule.

## Current Alleva API State

The current patient-centered treatment-plan contract is:

```text
GET /clients
GET /treatment-plans?ClientId={patient_id}
```

Current contract rules:

- `patient_id` is the canonical Alleva client ID from `GET /clients.id`.
- `ClientId` is case-sensitive in the treatment-plan query.
- Treatment-plan ownership is validated from the returned treatment-plan `client` string, expected as `/clients/{id}`.
- `chartId`, `externalId`, `mrn`, `clientName`, lowercase `clientId`, `uniqueId`, and `source_id` are not production treatment-plan join keys.
- Active client status prefers `status.id` when available; observed/defined status IDs are `1049` for Active and `1356` for Discharged.
- `dischargeDate` / `dischargeDateTime` from `GET /clients` is documented as planned/scheduled discharge, not actual system discharge.
- `isActive` is treatment-plan active status. `isComplete` means EMR submission/completion and does not mean inactive, closed, superseded, or current.
- The REST review-list path is not a reliable patient join source. Do not join treatment reviews by `clientName`.

## Current Swagger/OpenAPI Mapping Evidence

The current external mapping evidence available to documentation is the Alleva Swagger/OpenAPI field mapping export generated on 2026-06-21 at 14:59:49. It was derived from:

```text
Swagger UI: https://api.allevasoft.com/swagger/index.html
Swagger JSON: https://api.allevasoft.com/swagger/v1/swagger.json
Endpoint count: 424
Unique field count: 2303
```

The export includes `alleva_api_mapping.metadata.txt`, `alleva_api_mapping.grid.tsv`, and `alleva_api_mapping.long.tsv`.

This mapping evidence removes the old documentation-only blocker that those mapping files were unavailable. It does **not** clear the live-sync blocker. The export is Swagger/OpenAPI-derived only. Runtime responses may include fields not present in Swagger, and endpoints without response schemas may appear as `__NO_RESPONSE_SCHEMA_IN_ALLEVA_SWAGGER__`.

## Current Live-Sync Boundary

Live production sync remains gated. Do not enable or rely on live Alleva patient treatment-plan import until R3/Alleva confirms:

- tenant/environment and credentials
- token endpoint requirements, scope/audience/tenant parameters, and token auth style
- active-client endpoint and active/discharged filtering
- patient-centered treatment-plan endpoint behavior and exact `ClientId` casing
- treatment-plan detail and diagnosis endpoint behavior
- whether any trusted source can supply treatment-review IDs for `GET /treatment-reviews/{id}`
- pagination, cursor behavior, date filters, rate limits, and retry expectations
- authoritative signature/date/completion/LOC/admission/status fields
- PHI handling and minimum-necessary logging/display policy
- the unresolved LOC-change treatment-plan update window

Until those items are resolved, the app may use the API harness and dry-run aggregate reports as readiness evidence only.

## Current Primary Docs

Use these as the active documentation set:

- `README.md`
- `CHANGELOG.md`
- `docs\release-notes.md`
- `docs\Windows-User-Guide-Version-1.md`
- `docs\Windows-Deployment-and-Test-Guide-Version-1.md`
- `docs\windows-installer-build-and-install.md`
- `docs\UAT-Version-1-Marleigh.md`
- `docs\patient-treatment-plan-handling.md`
- `docs\alleva-patient-treatment-plan-data-contract.md`
- `docs\alleva-patient-treatment-plan-aggregate.md`
- `docs\alleva-treatment-plan-data-coverage.md`
- `docs\api-configuration-and-connectivity.md`
- `docs\treatment-plan-checklist-v1.md`
- `docs\open-blockers.md`
- `docs\architecture.md`
- `docs\runbook.md`
- `docs\codebase-map.md`
- `docs\admin-access-reset.md`

## Documentation Maintenance Rules

- Keep current version references aligned with `VERSION`, `VERSION.json`, `frontend/package.json`, `frontend/package-lock.json`, `/api/version`, and the UI footer.
- Keep historical validation reports historically accurate; add a new validation report when validating a new release instead of rewriting old evidence.
- Keep Alleva mapping evidence separate from runtime-production proof.
- Keep patient-centered treatment-plan retrieval separate from broad diagnostic endpoint pulls.
- Keep all examples synthetic or redacted.
- Do not add PHI, real credentials, raw tokens, real API response bodies, screenshots with real patient IDs, `.env` files, SQLite databases, uploads, logs, or generated reports to documentation.
