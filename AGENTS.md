# AGENTS.md - IZ Clinical Notes Analyzer

## Repo purpose
Local-first Windows 10/11 clinical-notes and Treatment Plan Timeliness Tracker app for R3 Recovery Services. The current app version is `2.0.0-beta.3` / build `2026.09.03.1` on the `beta-local-desktop-v2` channel. Normal Windows desktop use must not require Windows administrator access, Docker, PostgreSQL, Git, Node.js, or command-line work when a prepared release folder with built frontend assets is used.

## R3 project architecture
- Backend: `backend/app/` FastAPI service with auth/RBAC, settings, audit logging, encrypted uploads, deterministic rules, API connectivity harness, REST/OpenAPI/HL7 readiness boundary, gated Alleva REST treatment-plan sync readiness, workflow profiles, and version/readiness endpoints.
- Frontend: `frontend/src/` React/Vite single-page UI for login, dashboard, Treatment plans, Checklist, Manual upload, Review queue, Help, user management, Workflow profiles, App settings, Forensic logs, API/EMR status, optional LLM setup, and version footer.
- Desktop runtime: `backend/app/desktop_main.py` mounts the built React app plus desktop-only rules/API pages for one-service localhost use.
- Data: default SQLite, uploads, logs, reports, and user `.env` live in OS-local app data, not the repo. Relative runtime paths must resolve through `Settings.local_app_data_dir`.
- Rules: deterministic YAML rules in `config/rules/` and the canonical 42-step checklist in `config/checklists/treatment-plan-v1.json` remain the primary workflow engine. Optional LLM behavior must stay disabled by default and must never be required for compliance or timeliness decisions.
- Windows scripts: `scripts/Start-IZ-Clinical-Notes-Analyzer.cmd` and `scripts/startup-windows-local.ps1` are the ordinary Windows checkout launch path; PowerShell test scripts cover local stack and API configuration smoke flows.

## Important directories
- `backend/app/` - FastAPI API, auth/RBAC, audit logging, uploads, encrypted storage, rules execution, API connectivity boundary, workflow profiles, and timeliness services.
- `backend/tests/` - pytest backend and smoke coverage.
- `frontend/src/` - React UI for login, dashboards, treatment plans, uploads/reviews, checklist, help, user management, workflow profiles, logs, settings, API/EMR controls, and version footer.
- `scripts/` - Windows launch, packaging, admin-recovery, API diagnostic, and smoke-test scripts.
- `config/rules/` - deterministic completeness rules.
- `config/checklists/` - canonical Treatment Plan Checklist Version 1 JSON source.
- `docs/` - operator/developer docs, release notes, validation notes, PRD history, and synthetic examples.
- `docs/patient-treatment-plan-handling.md` - current implementation map for patient treatment-plan storage, manual upload sync, gated Alleva sync, aggregates, timeliness, checklist output, privacy boundaries, and UI/API code locations.

## How to run checks
- Windows release build: double-click `Build-IZ-Windows-Installer.cmd` from the repo root. The script must install backend runtime requirements plus `backend/requirements-build.txt`, run backend tests, run frontend tests/build, validate `frontend/dist`, create `dist/windows-release`, and scan the release folder and zip.
- Backend: `python -m venv backend/.venv && backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-windows-local.txt && backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-build.txt && set PYTHONPATH=backend && backend/.venv/Scripts/python.exe -m pytest backend/tests -q`
- Frontend: `cd frontend && npm install && npm run test -- --run && npm run build`
- Windows launcher: inspect or run `scripts\Start-IZ-Clinical-Notes-Analyzer.cmd`, `scripts\startup-windows-local.ps1`, `scripts\test-api-configuration-local.ps1`, `scripts\test-alleva-api-connectivity.ps1`, and `scripts\test-local-app-stack.ps1` on Windows PowerShell.
- Before commits: check `git status --short --branch` and verify generated runtime data, local configuration files, uploads, logs, and databases are not staged.

## Security / PHI rules
- Do not commit PHI, real patient notes, local runtime configuration, SQLite databases, uploaded notes, generated logs, access material, encryption material, or vendor connection material.
- Tests, fixtures, docs, screenshots, and examples must use synthetic data only.
- Do not log uploaded note text, PHI-like names/content, local runtime values, original uploaded filenames, or vendor connection material.
- Keep uploads encrypted at rest with the existing local encryption envelope.
- Saved API configuration must be encrypted at rest and browser responses should expose only configured-state flags.
- Keep direct API probes and OpenAPI discovery limited to configuration/testing/future-readiness unless official production import approval exists.
- Do not fake Alleva live patient import. Live patient import remains disabled until official tenant credentials, endpoint mapping, auth requirements, pagination, rate limits, attachment behavior, vendor documentation, and compliance approval exist.
- Do not add Docker or PostgreSQL as Windows desktop requirements.
- Do not package `.env`, `.env.*`, databases, uploads, exports, reports, logs, virtual environments, node_modules, pytest/coverage caches, raw vendor credentials, API tokens, local API reports, or PHI-like generated files.
- Validate generated release folders and zips before declaring Windows packaging work complete.

## Treatment Plan Timeliness Tracker blockers
- The level-of-care change treatment-plan update window is not confirmed by R3/Marleigh. Keep it configurable, visibly marked unvalidated in admin/settings UI and documentation, and do not hard-code a final value.
- Document the LOC-change blocker in `docs/open-blockers.md`, relevant README/PRD implementation notes, and future release notes until resolved.
- Preserve deterministic Missing Data, Needs Review, Conflicting Evidence, and Unable to Evaluate outcomes. Do not silently guess compliance when admission date, LOC, signature date, treatment-plan date, source evidence, or API mapping is missing or conflicting.

## Direct API and Alleva boundary
- The API configuration page, OpenAPI discovery, and operation-test endpoints are a direct API harness for readiness and tenant/vendor testing.
- Saved API configuration must use encrypted storage and should not appear in audit details, browser payloads, console output, docs, tests, or screenshots.
- Local sample OpenAPI/operation endpoints may use synthetic patient IDs only.
- Alleva live import plans are planning artifacts until the live import gate above is satisfied.
- The Alleva REST treatment-plan sync path is present but gated off by default and must remain blocked until R3/Alleva approves live sync and endpoint mapping.

## Commit and validation expectations
- Work in stations and do not perform destructive cleanup before the S0 validation gate.
- S1 cleanup requires a removal log and proof that removed files are unreferenced or generated/unsafe.
- Version metadata must be updated in `VERSION`, `VERSION.json`, `frontend/package.json`, release docs, and visible through `/api/version` and the UI for release work.
- Backend tests must pass or exact blockers must be documented.
- Frontend tests and build must pass or exact blockers must be documented.
- Windows scripts must remain source-checkout-friendly and documented for a purchased Dell Windows 10/11 Home laptop.
- Docs, release notes, and completion logs should be updated for each completed station.
