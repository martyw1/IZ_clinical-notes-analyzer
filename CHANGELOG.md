# Changelog

## Unreleased

### Changed
- No unreleased changes.

## 1.4.3 - 2026-06-19

### Changed
- Removed active FHIR/SMART-on-FHIR configuration, discovery, import-plan routes, read scopes, UI fields, defaults, validation requirements, and tests from Alleva workflows.
- Reframed Alleva setup as REST/OpenAPI/HL7-readiness only, using the Alleva API base URL, OpenAPI URL, token URL, API client ID, encrypted API client secret, token auth style, and validated endpoint mapping.
- Updated endpoint profiles, settings payloads, audit payloads, upload/source-evidence examples, operator docs, readiness docs, and version metadata for the REST/OpenAPI boundary.

### Verified
- Backend pytest passed with `95 passed, 2 skipped`.
- Frontend Vitest passed with `16 passed`.
- Frontend production build passed.

## 1.4.2 - 2026-06-18

### Fixed
- Fixed Manual upload binder deletion usability so disabled controls no longer show the Windows busy cursor.
- Kept `Delete uploaded binder` clickable before the patient-ID confirmation matches, showing the exact confirmation guidance instead of feeling unresponsive.

### Changed
- Promoted version metadata to `1.4.2` / build `2026.06.18.2`.

### Verified
- Backend pytest passed with `96 passed, 2 skipped`.
- Frontend Vitest passed with `16 passed`.
- Frontend production build passed.
- Example-treatment-plan upload/timeliness smoke passed across all 4 files in `example-treatment-plans`.
- Live in-app browser and Computer Use-assisted UI sweep passed on a disposable local desktop server, including Manual upload delete hover/click guidance, Review Queue exports, Treatment Plan exports/task buttons/status filters, all main navigation tabs, and button cursor scans across active screens.

## 1.4.1 - 2026-06-18

### Added
- Added separate Alleva REST API base/OpenAPI/startup-sync settings so `Test-AllevaApi.ps1` style REST connectivity no longer depends on the FHIR base URL field.
- Added a gated Alleva REST treatment-plan sync service that can pull active-client, treatment-plan, and treatment-review REST payloads into the local R3 timeliness engine after live-sync approval and endpoint mapping validation.
- Added startup-sync and manual-sync controls in App settings, including exact missing-field validation and last sync status/message display.
- Added audit events for Alleva REST sync blocked/skipped/failure/completion and per-client R3 compliance analysis results.

### Changed
- Promoted version metadata to `1.4.1` / build `2026.06.18.1`.
- Updated the API connectivity harness to use the Alleva REST API base URL and OpenAPI URL fields instead of reusing the FHIR base URL.
- Clarified docs and Help text that Alleva supplies source data while R3 runs compliance checks locally.

### Verified
- Focused backend tests passed with `18 passed`.
- Frontend Vitest passed with `15 passed`.

## 1.4.0 - 2026-06-17

### Added
- Added the local treatment-plan date clock using the laptop/facility-local current date, admission date, and latest valid treatment-plan review/update date.
- Added PHP 30-calendar-day and non-PHP 60-calendar-day recurrence calculations, plus a manager-editable 7-calendar-day LOC-change preset that remains visibly unvalidated until R3/Marleigh confirms the final rule.
- Added forensic audit events for every treatment-plan timeliness analysis result, including workflow definition key/version/checklist context.
- Added source-evidence locations for deterministic findings, including manual PDF page references when readable and API/FHIR source identifiers when present.
- Added 42-step workflow status rows to review and treatment-plan CSV/JSON exports while preserving the existing 18-domain checklist export rows.
- Added in-place editing for draft workflow versions from Workflow profiles and App settings workflow panels.

### Changed
- Promoted version metadata to `1.4.0` / build `2026.06.17.1`.
- Promoted the Treatment Plan Checklist metadata to `1.2.0` to reflect date-clock, source-evidence, export, and workflow-editing behavior.
- Changed missing-name fallbacks to `no-name-found_YYYY-MM-DD_HHMMSS` or `no-value-found_YYYY-MM-DD_HHMMSS`.
- Clarified App settings validation so enabled EMR/API and periodic API checks report the exact missing fields/scopes.
- Updated the Alleva endpoint profile defaults and help text to pre-fill the public OpenAPI URL while keeping FHIR base URL reserved for a vendor/tenant-supplied FHIR R4 root endpoint.
- Updated Help and operator docs with field-level guidance for admission date, latest review/update date, LOC mapping, LOC-change window validation, API settings, exports, and source evidence.

### Fixed
- Fixed the Review Queue detail title from the truncated `Patient enti` presentation to `Patient Details`.
- Fixed periodic API-check enablement behavior so saved settings can be checked without the button staying unintentionally unavailable.
- Fixed treatment-plan sync/export behavior so uploaded/API re-analysis preserves the workflow version context used for later audit interpretation.

### Verified
- Full backend pytest passed with `93 passed, 2 skipped`.
- Frontend Vitest passed with `15 passed`.
- Frontend production build passed.
- Focused example-treatment-plan upload/timeliness tests passed for the tracked synthetic PDFs under `example-treatment-plans`.

## 1.3.0 - 2026-06-16

See git history and `docs/validation/validation-report-2026-06-16-production-readiness.md` for the detailed 1.3.0 release notes and validation evidence.
