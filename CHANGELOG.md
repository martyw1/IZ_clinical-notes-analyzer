# Changelog

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
