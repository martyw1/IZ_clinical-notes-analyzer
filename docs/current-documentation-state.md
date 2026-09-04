# Current Documentation State

Date: 2026-09-04

Applies to: IZ Clinical Notes Analyzer Version `2.0.0-beta.3` / build `2026.09.03.1` on the `beta-local-desktop-v2` channel.

## Purpose

This file is the current documentation alignment tracker. It summarizes what the active docs should say after the July 2026 patient-centered Alleva treatment-plan clarification and the current Swagger/OpenAPI mapping export review.

Historical validation reports, PRD notes, and earlier implementation analyses may keep the version/date they originally validated. Do not reinterpret historical reports as current beta state unless they explicitly say they apply to `2.0.0-beta.3`.

## Current Product State

- The app is a local-first Windows 10/11 desktop-style FastAPI + React/Vite app served from `http://localhost:8000`.
- The normal non-technical R3 path is a prepared release folder with built frontend assets, no Windows administrator requirement, and no Docker, PostgreSQL, Git, Node.js, command-line work, cloud hosting, or database administrator requirement for ordinary use.
- Local runtime data lives under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`, not in the repo or installed app folder.
- The prepared Windows release folder installs per user under `%LOCALAPPDATA%\Programs\IZ Clinical Notes Analyzer` and includes double-click install, launch, stop, diagnostics, backup, data-preserving uninstall, and complete-uninstall commands.
- The current package is still a release-folder/zip package, not a signed MSI/MSIX with repair/modify support.

## Current Treatment-Plan State

- `config\checklists\treatment-plan-v1.json` remains the canonical 42-step checklist source.
- Checklist content version remains `1.2.0`; app version remains separate at `2.0.0-beta.3`.
- `Treatment Plans Roster` is the admin/office-manager operational pull and exact-plan work queue. `Patient Roster`, `Patient Record Detail`, and `Treatment Plan Detail` provide the MRN-centered review path.
- The V2 administrator navigation exposes `Status Dashboard`, patient and treatment-plan work areas, `Manual Upload`, `API Testing Harness`, `Users`, `Forensic Logs`, `Settings`, and `Help`; role restrictions still control which pages and actions each account can use.
- The selected-plan detail includes deterministic timeliness status, source evidence, date-clock results, current-plan content facts, the 42-step checklist, manager actions, immutable plan lineage, audit context, and authorized export paths.
- Office-manager roster and export views are source-scoped and must preserve exact patient, source, plan, and immutable plan-version identity; the Task7 source-membership receipt remains pending. Task8's backend metrics subgate is independently verified (28/28 focused tests, five raw-source probes, and byte-identical 63-by-42 clinical replay), while its browser/build evidence remains pending.
- Exact raw-plan reads exclude standalone historical patient-wide treatment reviews when no reliable plan/version link exists. Embedded reviews that are bound to the selected plan remain preserved; deterministic rules are unchanged, and older projected recurrence dates may differ for excluded legacy reviews.
- Structural v12 source-document associations use exact saved memberships; approved migration backfills only valid original `(source_document_id, plan_version_id)` pairs, and new or repeated imports attach the exact saved plan version. Existing ambiguous legacy rows remain missing/unlinked evidence rather than guessed associations. Detach/erase/removal behavior remains subject to the unanswered retention choice; no such behavior is claimed in this beta3 documentation state.
- Alleva/API treatment-plan lookup status and lookup results should stay inside bounded scroll areas so long progress/diagnostic text does not push lower content below the viewport.
- Source-document due-date disagreement without a validated LOC-change explanation remains a review/error outcome such as `Needs Review`, not silent compliance.
- MRN/patient ID remains the identity key; exact UI selection uses the authorized `patient_record_id` together with source system, source record ID, plan ID, and immutable plan-version identity. Names are never identity or matching keys and are not emitted in CSV, query parameters, audit details, or logs. Authorized encrypted patient-name display is limited to permitted UI rows; original filenames, addresses, contact details, attachment URLs, and author/custodian labels remain excluded from CSV/audit/log/query surfaces.
- Alleva patient-name import/display remains opt-in and off by default. Name-only matching remains disabled by default and validation-only.
- The LOC-change treatment-plan update window remains unresolved. The app keeps the manager-editable 7-calendar-day preset, but docs and UI must continue marking the rule as unvalidated until R3/Marleigh confirms the exact rule.

## Current beta3 validation boundary

The beta3 metadata and current operator documentation are aligned to build `2026.09.03.1`. This alignment is not a packaged-runtime or full-smoke completion claim. Task10 must validate the freshly built isolated Windows package, `/api/version`, the visible footer, and the complete Edge/Chrome office-manager workflow matrix before any production, clinical-production, GA, or full-smoke claim.

## Current Alleva API State

The current operational treatment-plan contract is:

```text
GET /clients
GET /treatment-plans (bounded global pages)
```

Current contract rules:

- `/clients.mrn` is the canonical local patient identity and the value exposed through the legacy `patient_id` property.
- `/clients.id` is retained separately as the source patient ID used for treatment-plan relationship validation.
- Treatment-plan ownership is validated from `client.id`, `client.route`, or a string `/clients/{id}`, then mapped to the matching MRN.
- The operational pull collects older and newer plans across every lifecycle state; it does not issue one filtered list request per active client.
- `chartId`, `externalId`, `clientName`, lowercase `clientId`, `uniqueId`, and `source_id` are not substitutes for MRN.
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

- `docs\guides\Version 2.0 Beta  2.0.0-beta.2  beta-local-desktop-v2\Marleigh-Setup-Install-and-User-Guide.html`
- `README.md`
- `CHANGELOG.md`
- `docs\release-notes.md`
- `docs\beta-client-test-run-guide.md`
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
