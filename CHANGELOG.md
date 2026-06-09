# Changelog

## 1.0.0 - 2026-06-09

### Added
- Added the canonical Treatment Plan Checklist Version 1 JSON source, backend validator, readiness check, API endpoint, and React Checklist tab.
- Added review-source discovery for mock API readiness and manual uploads while keeping live Alleva import disabled until credentials, mapping, scopes, pagination/rate limits, attachment behavior, vendor documentation, and compliance approval are complete.
- Added dashboard review-source cards, checklist version visibility, and CSV/JSON export controls for chart review and treatment-plan detail reports.
- Added Windows preflight, setup, local start, smoke, API-configuration smoke, and release package scripts for a normal Windows 10/11 laptop or desktop.
- Added Version 1 Windows user, deployment/test, UAT, checklist, completion, and validation documentation.

### Changed
- Promoted version metadata to `1.0.0` / build `2026.06.09.1`.
- Seeded the default treatment-plan workflow from the canonical checklist snapshot.
- Kept the LOC-change treatment-plan update window configurable and visibly unvalidated in UI/docs.
- Hardened Windows smoke scripts for paths with spaces and `127.0.0.1` localhost binding behavior.
- Excluded generated release output, local virtualenvs, node modules, logs, uploads, and archived walkthrough/video folders from the Windows release package.

### Verified
- Backend test suite passed with `74 passed, 2 skipped`.
- Frontend user-oriented Vitest suite passed with `9 passed`, including upload, review save, checklist, settings, and CSV/JSON export coverage.
- Frontend production build passed.
- Windows preflight passed and wrote a local AppData JSON report.
- Windows release builder produced `dist\windows-release\IZ-Clinical-Notes-Analyzer-v1.0.0` and `dist\windows-release\IZ-Clinical-Notes-Analyzer-v1.0.0.zip`.
- Windows local stack smoke passed health, readiness, version, login/profile, and workflow profile API checks.
- Windows API configuration smoke passed focused API connectivity tests, encrypted API-key save, sample OpenAPI pull, and API configuration page load.
- Real in-app browser smoke passed login, dashboard, checklist, manual upload form, live synthetic upload via local API, generated review queue/detail, reviewer decision save, treatment-plan tracker, and 1366x768 laptop viewport checks.

## 0.5.0 - 2026-06-04

### Added
- Added S0 codebase map, cleanup audit, open blocker register, and S1 removal log for the v0.5.0 Treatment Plan Timeliness Tracker workflow.
- Added first-class Treatment Plan Timeliness Tracker backend models, APIs, rule evaluation service, upload metadata sync, manual override audit trail, and React dashboard/detail UI.
- Added configurable LOC aliases for `IOP-5`, `IOP-19`, `IOP-3`, and `OP`, plus timeliness edge-case coverage for missing data, override RBAC, upload sync, and the unvalidated LOC-change blocker.
- Added upload hardening tests for per-file size limits, binder total size limits, missing patient IDs, conflicting detected patient IDs, unauthorized downloads, encrypted storage, and PHI-safe audit logging.
- Added redacted JSON report payloads for API definition pulls and selected OpenAPI operation tests.
- Added admin-managed workflow definition/version tables, audited workflow profile CRUD/versioning APIs, and a Settings UI panel for creating, publishing, and archiving workflow profiles.
- Added a seeded published Treatment Plan Timeliness Tracker workflow profile for fresh local databases.
- Added Windows Dell validation guidance, packaging path recommendations, and workflow extensibility documentation.

### Changed
- Expanded project `AGENTS.md` with R3 architecture, PHI/synthetic-data boundaries, direct API harness limits, Windows target assumptions, and the unvalidated LOC-change blocker.
- Tightened `.gitignore` for local SQLite files, logs, coverage output, caches, local PRD duplicates, and walkthrough exports.
- Updated README/PRD notes to keep the LOC-change update window configurable and visibly unvalidated.
- Encrypted LLM and access reputation API keys saved through the main settings API instead of storing those values directly.
- Removed original filenames and note-derived detection reasons from patient-note upload/download audit details while preserving authenticated UI metadata and file hashes.
- Redacted sensitive API response fields, bearer/API-key text, and token query parameters from direct API harness result payloads and reports.
- Expanded local smoke coverage to check version metadata, runtime readiness, and workflow profile APIs in addition to health, login, profile, and chart loading.
- Validated workflow profile definition snapshots and transition rules before saving, and limited hard delete to unused draft-only profiles that were never published.

### Verified
- Backend tests passed with `72 passed` using Python 3.11 from a temporary local validation venv.
- Focused S2 backend timeliness/schema tests passed with `8 passed`.
- Focused S3 upload/security tests passed with `13 passed`.
- Focused S4 API connectivity tests passed with `11 passed`.
- Focused S5 workflow-definition/schema tests passed with `6 passed`.
- Focused workflow-definition seed/delete/validation tests passed with `3 passed`.
- Focused smoke-script tests passed with `2 passed`.
- Live desktop full-stack smoke passed on macOS against `app.desktop_main` with temporary SQLite/env data on port `8765`, including `/api/version` reporting `0.5.0`.
- Frontend production build passed after repairing missing local optional native packages in `node_modules`.
- Frontend Vitest and direct `tsc --noEmit` did not complete locally because their worker/process execution hung before test import or diagnostics; this is documented as a local validation blocker.

## 0.4.1 - 2026-06-03

### Changed
- Rewrote `README.md` as a non-technical operator guide covering current app functionality, Windows local installation, configuration, everyday use, backup/restore, API connectivity testing, EMR/FHIR boundaries, troubleshooting, Docker/server mode, architecture, and key files.

### Verified
- Backend tests passed with `54 passed`.
- Frontend tests passed with `6 passed`.
- Frontend production build passed.
- Frontend production dependency audit reported `0 vulnerabilities`.

## 0.4.0 - 2026-05-14

### Added
- Backend `/api/version` endpoint with version, environment, branch, commit, and dirty-state metadata.
- React UI footer that displays the backend-provided app version on every page.
- Synthetic sample clinical notes and export-shaped CSV/JSON examples under `docs/sample-clinical-notes/`.
- Regression tests for version metadata and API-configuration non-secret boundary behavior.
- Repository AGENTS.md guidance for future Codex/local agent work.

### Changed
- Promoted `VERSION` to `0.4.0` to match `VERSION.json` release metadata.
- Exposed API configuration JSON routes from the main FastAPI app as well as the desktop runtime.
- Refreshed test setup so startup hardening checks run with explicit non-placeholder local test secrets.
- Updated PostgreSQL config tests to preserve SQLite as the Windows desktop default while still validating developer PostgreSQL mode.

### Security
- Verified API configuration responses indicate whether a key is configured without returning the saved secret.
- Maintained local encrypted clinical-file storage and secret redaction boundaries in tests and docs.
