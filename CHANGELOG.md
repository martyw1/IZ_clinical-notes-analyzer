# Changelog

## Unreleased

### Changed
- Updated documentation and legacy startup references so the repository reflects the current Version 1.3.0 Windows local desktop app state.

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
