# Release Notes

Current app version: `1.4.6-beta.1` / build `2026.06.30.1`.

Current release channel: `beta-local-desktop`.

Current release date in version metadata: `2026-06-30`.

## 1.4.6-beta.1 - Windows no-admin install readiness

Build: `2026.06.30.1`

Version metadata name: `Beta 1.4.6-beta.1 Windows no-admin install readiness`

Summary:

- Aligns version metadata and active docs to `1.4.6-beta.1` / build `2026.06.30.1`.
- Adds packaged local-data backup helpers through `scripts\backup-local-data.ps1`, `scripts\Backup-IZ-Clinical-Notes-Analyzer.cmd`, the release-folder backup command, and installed Start Menu/Desktop backup shortcuts.
- Adds a confirmed complete-uninstall path through `scripts\complete-uninstall-local-data.ps1`, `scripts\Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd`, the release-folder complete-uninstall command, and an installed Start Menu shortcut that requires typing `REMOVE IZ DATA`.
- Keeps normal uninstall data-preserving: app files and shortcuts are removed, while `%LOCALAPPDATA%\IZ Clinical Notes Analyzer` stays in place for reinstall/upgrade.
- Rewrites the Windows User Guide for no-admin install, first launch, backup, troubleshooting, diagnostics, data-preserving uninstall, and complete uninstall.
- Updates the Windows Deployment and Test Guide with release-folder contents, installed shortcuts, backup behavior, uninstall behavior, and target-laptop acceptance criteria.
- Makes Patient ID the only patient identifier accepted for upload, Treatment Plans, chart labels, generated review records, exports, downloads, API summaries, and audit context.
- Removes patient names, addresses, contact details, source filenames, source attachment URLs, author/custodian labels, and similar direct identifiers from new upload/import storage and browser payloads; existing local rows are neutralized by schema compatibility startup.
- Rejects deprecated manual `client_name` uploads and chart creates when a patient name is supplied, while preserving compatibility fields by setting them to Patient ID.
- Disables Alleva/API name matching for treatment-plan sync readiness; REST records must map by patient/client ID, and name-only records remain unmapped.
- Tightens Treatment Plan Timeliness dashboard/detail/override access to administrators and office managers because counselor ownership is not explicit in that table.
- Blocks unsafe bootstrap-admin defaults in production-like/local-client startup readiness and changes default reset-on-startup to off unless a recovery script explicitly enables it.
- Adds a disabled-by-default `Import and display Alleva patient names` App settings control. Alleva treatment-plan sync stores generated redacted display labels by default and redacts existing Alleva-sourced names again when the setting is saved off.
- Keeps validation-only name fallback separate from patient-name import/display and verifies both settings persist after save/readback.
- Adds an admin-only `Pull / refresh treatment plans` button directly on the Treatment Plans tab.
- Moves documented unused/legacy code files into `depricated/` with a manifest and excludes deprecated folders from Windows release packaging.
- Adds redacted diagnostics collection through `scripts\collect-diagnostics.ps1`, `Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd`, and installer-created Start Menu/Desktop Diagnostics shortcuts.
- Hardens the standalone API configuration page against OpenAPI/schema text injection by building generated operation fields with DOM APIs rather than markup strings.
- Adds CSV formula injection protection and keeps saved API client credentials write-only in browser responses.
- Validation evidence for the redaction cleanup is recorded in `docs/validation/validation-report-2026-06-28-treatment-plan-redaction-cleanup.md`; target-laptop packaged install/backup/uninstall validation remains listed in `docs/Windows-Deployment-and-Test-Guide-Version-1.md`.

## 1.4.5-beta.1 - R3 beta-client readiness

Build: `2026.06.23.1`

Version metadata name: `Beta 1.4.5-beta.1 R3 beta-client readiness`

Summary:

- Renames the primary dashboard tab to `Status Dashboard`, moves `Treatment plans` immediately after it, and adds bundled R3 Recovery Services header-logo support via `/api/branding/header-logo` with an overrideable filesystem setting.
- Removes the desktop floating oval shortcuts and the obsolete intake-guide page. Manual upload remains in normal navigation; API testing remains available through App Settings and `/api-configuration`.
- Adds admin-only `Clear All Patient Data` actions in Status Dashboard Quick Actions and App Settings. The action requires the exact phrase `CLEAR ALL PATIENT DATA`, clears local patient/chart/treatment-plan/manual-upload/review rows and encrypted upload files, and preserves settings, API credentials, user accounts, audit logs, docs, and rules.
- Moves manual `Retrieve Active Treatment Plans` to the Status Dashboard EMR/API card and keeps startup sync off by default behind the existing approval and endpoint-mapping gates.
- Adds saved manager status/comment notes for each selected-client Treatment Plan checklist criterion plus a selected-client counselor action CSV export.
- Fixes due-date classification so due today is `Urgent`, 1 day out is `Urgent`, 2-7 days out is `Due Soon`, 8+ days out is `Compliant`, and only dates before the evaluation date are `Overdue`.
- Hardens manual upload errors so unexpected 500s return non-PHI JSON detail, roll back partial rows, and clean up encrypted files written before failure.
- Keeps Review Queue as the generated/manual chart-review workbench and Treatment Plans as the timeliness/due-date work queue.
- Documents that Alleva mapping exports were not present in the repo during this readiness pass; conservative REST review-date/signature/due-date aliases were added without opening live import.
- Validation evidence is recorded in `docs/validation/validation-report-2026-06-23-beta-client-readiness.md`.

## 1.4.4-beta.1 - Beta treatment-plan checklist detail visibility

Build: `2026.06.21.1`

Version metadata name: `Beta 1.4.4-beta.1 treatment-plan checklist detail visibility`

Summary:

- Converts the current local Windows desktop app metadata to beta: app version `1.4.4-beta.1`, channel `beta-local-desktop`, stability `beta`, and prerelease metadata enabled.
- Keeps Treatment Plan Checklist content version separate at `1.2.0`; the checklist JSON content version did not change.
- Adds selected-client `42-Step Checklist Evaluation` results to the Treatment Plans detail payload and UI so a manager can inspect every canonical checklist step for the selected treatment-plan client/item.
- Adds checklist results to selected treatment-plan CSV/JSON exports.
- Keeps the global Checklist tab as the canonical rule reference and exposes finding examples, remediation suggestions, and evidence fields.
- Preserves the gated Alleva REST treatment-plan sync path, including required `/clients` and `/treatment-plans` behavior and optional `/treatment-reviews` warning behavior.
- Keeps LOC-change timing visibly unvalidated until R3/Marleigh confirms the exact rule.

## 1.4.4 - Documentation and metadata alignment

Build: `2026.06.20.1`

Version metadata name: `Version 1.4.4 current documentation and metadata alignment`

Summary:

- Promotes the current app version metadata and documentation references to `1.4.4` on `main`.
- Keeps the Version 1 local Windows desktop runtime, FastAPI desktop service, built React/Vite frontend assets, SQLite local data, encrypted uploaded-file storage, encrypted saved API-secret storage, role-based access control, deterministic Treatment Plan Tracking rules, Workflow profiles, in-app Help, readiness checks, and forensic audit logging.
- Preserves the gated Alleva REST treatment-plan sync readiness boundary and manual-upload binder deletion usability behavior.
- Replaces generic manual Alleva treatment-plan sync failure text with stage-specific user messages for token, endpoint permission, endpoint mapping/version, timeout, empty-result, warning, and success states.
- Simplifies the API Testing Harness into a step-by-step flow and keeps one Alleva quick action: `ALL Patient Records`, backed by `GET /clients` with Excel-ready TSV output.
- Lets approved Alleva treatment-plan sync continue when the optional `/treatment-reviews` endpoint is unauthorized or unavailable, while keeping `/clients` and `/treatment-plans` required.
- Adds an admin-only Review Queue button to pull active treatment plans through the same approved sync path and then open the Treatment Plans queue.

## 1.4.2 - Manual upload button usability

Build: `2026.06.18.2`

Version metadata name: `Version 1.4.2 manual upload button usability`

Summary:

- Fixes manual-upload binder deletion usability.
- The delete-binder action remains clickable enough to show exact patient-ID confirmation guidance when clicked before the confirmation value matches.
- The app no longer presents unavailable delete buttons with a Windows busy cursor in the manual-upload workflow.
- Keeps the gated Alleva REST treatment-plan sync readiness work from Version 1.4.1.
- Keeps Version 1 local Windows desktop runtime, built React/Vite frontend assets, FastAPI desktop service, SQLite local data, encrypted uploaded-file storage, encrypted saved API-secret storage, role-based access control, deterministic Treatment Plan Tracking rules, Workflow profiles, in-app Help, readiness checks, and forensic audit logging.

## 1.4.1 - Alleva REST treatment-plan sync readiness

Summary:

- Added a separate Alleva REST treatment-plan sync configuration path that does not require a FHIR root.
- Kept live startup sync disabled by default.
- Required explicit R3/Alleva live-sync approval and validated endpoint mapping before any live patient treatment-plan data can be imported.
- Preserved the boundary that Alleva is the source system while R3's deterministic local timeliness engine performs compliance decisions.

## 1.4.0 - Treatment-plan hardening and generated-name fallback

Summary:

- Hardened Treatment Plan Timeliness behavior, evidence handling, and export details.
- Superseded earlier generated/patient-ID fallback naming with:
  - `no-name-found_YYYY-MM-DD_HHMMSS` when no name is found in source evidence.
  - `no-value-found_YYYY-MM-DD_HHMMSS` when an empty or unusable value is found.

## Current implementation boundaries

- Live Alleva patient import remains disabled until R3/Alleva supplies approved tenant credentials, endpoint mapping, scopes, pagination/rate limits, attachment/signature behavior, vendor documentation, and compliance approval.
- The LOC-change treatment-plan update window remains unvalidated by R3/Marleigh. The app ships a manager-editable 7-calendar-day preset, but this must stay configurable and visibly unresolved until confirmed.
- Manual upload remains an upload-time snapshot. Use the monthly compliance-check fallback when API refresh is unavailable.
- Optional LLM setup exists but is disabled by default and is not the primary review path.
- Docker, PostgreSQL, and nginx are not ordinary Windows desktop requirements for the current R3 beta-local-desktop path.
- The package is still not a signed MSI/MSIX with repair/modify support; the release-folder builder is the current packaging path.

## Version metadata files

Current version values must stay aligned in:

- `VERSION`
- `VERSION.json`
- `frontend/package.json`
- `frontend/package-lock.json`
- README and primary docs
- `/api/version`
- UI footer
- release metadata

## Primary current docs

- `README.md`
- `docs\Windows-User-Guide-Version-1.md`
- `docs\Windows-Deployment-and-Test-Guide-Version-1.md`
- `docs\UAT-Version-1-Marleigh.md`
- `docs\treatment-plan-checklist-v1.md`
- `docs\open-blockers.md`
- `docs\api-configuration-and-connectivity.md`
- `docs\architecture.md`
- `docs\runbook.md`
- `docs\codebase-map.md`
- `docs\admin-access-reset.md`

Historical validation reports keep their original tested version numbers and should not be read as the current app version unless they explicitly say they were updated for `1.4.6-beta.1`.
