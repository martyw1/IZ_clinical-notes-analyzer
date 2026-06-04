# Changelog

## Unreleased

### Added
- Added S0 codebase map, cleanup audit, open blocker register, and S1 removal log for the v0.5.0 Treatment Plan Timeliness Tracker workflow.
- Added first-class Treatment Plan Timeliness Tracker backend models, APIs, rule evaluation service, upload metadata sync, manual override audit trail, and React dashboard/detail UI.
- Added configurable LOC aliases for `IOP-5`, `IOP-19`, `IOP-3`, and `OP`, plus timeliness edge-case coverage for missing data, override RBAC, upload sync, and the unvalidated LOC-change blocker.

### Changed
- Expanded project `AGENTS.md` with R3 architecture, PHI/synthetic-data boundaries, direct API harness limits, Windows target assumptions, and the unvalidated LOC-change blocker.
- Tightened `.gitignore` for local SQLite files, logs, coverage output, caches, local PRD duplicates, and walkthrough exports.
- Updated README/PRD notes to keep the LOC-change update window configurable and visibly unvalidated.
- Encrypted LLM and access reputation API keys saved through the main settings API instead of storing those values directly.

### Verified
- Backend tests passed with `59 passed` using Python 3.11 from a temporary local validation venv.
- Focused S2 backend timeliness/schema tests passed with `8 passed`.
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
