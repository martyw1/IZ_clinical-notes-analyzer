# AGENTS.md - IZ Clinical Notes Analyzer

## Repo purpose
Local-first Windows 10/11 clinical-notes completeness-check app for R3 Recovery Services. The v0.5.0 direction is the Treatment Plan Timeliness Tracker MVP while preserving the existing upload-first chart-review workflow. Normal Windows desktop use must not require Docker, PostgreSQL, Git, Node.js, or command-line work.

## R3 project architecture
- Backend: `backend/app/` FastAPI service with auth/RBAC, settings, audit logging, encrypted uploads, deterministic rules, API connectivity harness, REST/OpenAPI/HL7 readiness boundary, and version/readiness endpoints.
- Frontend: `frontend/src/` React/Vite single-page UI for login, dashboard, uploads, review queue, users, logs, settings, API/EMR status, and version footer.
- Desktop runtime: `backend/app/desktop_main.py` mounts the built React app plus desktop-only rules/API/intake pages for one-service localhost use.
- Data: default SQLite, uploads, logs, and user `.env` live in OS-local app data, not the repo. Relative runtime paths must resolve through `Settings.local_app_data_dir`.
- Rules: deterministic YAML rules in `config/rules/` remain the primary workflow engine. Optional LLM behavior must stay disabled by default and must never be required for MVP compliance or timeliness decisions.
- Windows scripts: `scripts/Start-IZ-Clinical-Notes-Analyzer.cmd` and `scripts/startup-windows-local.ps1` are the ordinary Windows checkout launch path; PowerShell test scripts cover local stack and API configuration smoke flows.

## Important directories
- `backend/app/` - FastAPI API, auth/RBAC, audit logging, uploads, encrypted storage, rules execution, API connectivity boundary.
- `backend/tests/` - pytest backend and smoke coverage.
- `frontend/src/` - React UI for login, uploads/reviews, user management, logs, settings, and version footer.
- `scripts/` - Windows launch and smoke-test scripts.
- `config/rules/` - deterministic completeness rules.
- `docs/` - operator/developer docs and synthetic examples.

## How to run checks
- Backend: `python -m venv backend/.venv && backend/.venv/bin/python -m pip install -r backend/requirements.txt && PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q`
- Frontend: `cd frontend && npm install && npm run test -- --run && npm run build`
- Windows launcher: inspect or run `scripts\Start-IZ-Clinical-Notes-Analyzer.cmd`, `scripts\startup-windows-local.ps1`, `scripts\test-api-configuration-local.ps1`, `scripts\test-alleva-api-connectivity.ps1`, and `scripts\test-local-app-stack.ps1` on Windows PowerShell.
- Before commits: check `git status --short --branch` and verify generated runtime data, secrets, uploads, logs, and databases are not staged.

## Security / PHI rules
- Do not commit PHI, real patient notes, `.env`, SQLite databases, uploaded notes, logs, API keys, bearer tokens, encryption keys, or passwords.
- Tests, fixtures, docs, screenshots, and examples must use synthetic data only.
- Do not log uploaded note text, PHI-like names/content, API keys, bearer tokens, encryption keys, passwords, or local encryption secrets.
- Keep uploads encrypted at rest with the existing local encryption envelope.
- Saved API credentials must be encrypted at rest and never returned to the browser. Browser responses should expose only boolean configured flags.
- Keep direct API probes and OpenAPI discovery limited to configuration/testing/future-readiness unless official production import approval exists.
- Do not fake Alleva live patient import. Live patient import remains disabled until official tenant credentials, endpoint mapping, auth requirements, pagination, rate limits, attachment behavior, vendor documentation, and compliance approval exist.
- Do not add Docker or PostgreSQL as Windows desktop requirements.

## Treatment Plan Timeliness Tracker blockers
- The level-of-care change treatment-plan update window is not confirmed by R3/Marleigh. Keep it configurable, visibly marked unvalidated in admin/settings UI and documentation, and do not hard-code a final value.
- Document the LOC-change blocker in `docs/open-blockers.md`, relevant README/PRD implementation notes, and future release notes until resolved.
- Preserve deterministic Missing Data and Needs Review outcomes. Do not silently guess compliance when admission date, LOC, signature date, or source evidence is missing or conflicting.

## Direct API harness boundary
- The API configuration page, OpenAPI discovery, and operation-test endpoints are a direct API harness for readiness and tenant/vendor testing.
- Saved API keys/secrets must use encrypted storage and should never appear in audit details, browser payloads, console output, docs, tests, or screenshots.
- Local sample OpenAPI/operation endpoints may use synthetic patient IDs only.
- Alleva live import plans are planning artifacts until the live import gate above is satisfied.

## Commit and validation expectations
- Work in stations and do not perform destructive cleanup before the S0 validation gate.
- S1 cleanup requires a removal log and proof that removed files are unreferenced or generated/unsafe.
- Version metadata must be updated and visible through `/api/version` and the UI for release work.
- Backend tests must pass or exact blockers must be documented.
- Frontend tests and build must pass or exact blockers must be documented.
- Windows scripts must remain source-checkout-friendly and documented for a purchased Dell Windows 10/11 Home laptop.
- Docs, changelog, and completion log should be updated for each completed station.
