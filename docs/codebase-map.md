# Codebase Map - S0 Baseline

Date: 2026-06-04
Branch: `refactor/codex-v0.5.0`
Baseline: `695080d`, tagged `baseline-pre-codex-20260604-164125`

## Scope

This map summarizes the current source checkout before v0.5.0 implementation work. It is a read-only S0 architecture inventory plus risk map. It does not approve deletions or cleanup by itself.

## Current Architecture

The app is a local-first FastAPI plus React/Vite application. The normal Windows target is a one-machine desktop-style localhost app using SQLite, local encrypted uploads, and local audit logs under per-user app data. Docker and PostgreSQL exist for developer/server scenarios, but are not acceptable as ordinary Windows 10/11 Home requirements.

Current implementation includes clinical-note binder upload, chart-audit review, and the S2 first-class Treatment Plan Timeliness Tracker. The timeliness tracker now has active-client records, LOC history, treatment-plan records, manual overrides, dashboard status APIs, and a React detail page. Workflow CRUD/versioning and full Windows packaging remain later v0.5.0 stations.

## Backend Entrypoints

| Entrypoint | Purpose |
|---|---|
| `backend/app/main.py` | FastAPI app factory, startup readiness/schema/admin bootstrap, CORS/trusted-host/security headers, health/readiness/version, primary API routers. |
| `backend/app/desktop_main.py` | Desktop runtime wrapper. Includes rules API, API configuration UI, clinical-notes intake UI, and serves `frontend/dist` when built. |
| `backend/app/api/routes.py` | Main authenticated API: auth, users, settings, readiness, EMR profile/discovery/import-plan, chart audit, patient-note uploads/downloads, timeliness dashboard/detail/override APIs, audit logs. |
| `backend/app/api/api_config_routes.py` | Direct API harness for API configuration, local sample OpenAPI, OpenAPI/Swagger discovery, and selected operation testing. |
| `backend/app/api/rules_routes.py` | Rules profile and ad hoc rules evaluation API. |
| `backend/app/api/api_config_ui_routes.py` | Standalone HTML page for API configuration/testing. |
| `backend/app/api/clinical_notes_ui_routes.py` | Standalone HTML intake guide for manual upload and future direct API lookup. |

## Backend Domain and Services

| Area | Files | Current behavior |
|---|---|---|
| Models | `backend/app/models/models.py` | Users, app settings, charts, patient note sets/documents, workflow transitions, audit item responses, audit logs, timeliness clients, LOC history, treatment-plan records, and manual overrides. Workflow-definition/version tables are not implemented yet. |
| Schemas | `backend/app/schemas/schemas.py` | Pydantic contracts for auth/users/settings/readiness/EMR/chart/note-set/audit-log APIs plus timeliness dashboard/detail/override schemas. |
| Config | `backend/app/core/config.py` | SQLite-first defaults; relative DB/upload/log paths resolve into OS-local app data; local PostgreSQL only allowed for supported developer/server modes. |
| Security | `backend/app/core/security.py`, `backend/app/api/deps.py` | JWT auth, password hashing/policy, role checks, password-reset gate. |
| Upload storage | `backend/app/services/patient_notes.py`, `backend/app/services/secure_storage.py` | File type/count/size validation, safe filenames, patient ID detection, encrypted file writes, path traversal prevention, encrypted text helper. |
| Evaluation | `backend/app/services/evaluation.py` | Deterministic chart-audit item generation from uploaded note metadata/text, with optional LLM gap analysis hooks. |
| Timeliness | `backend/app/services/timeliness.py` | Deterministic treatment-plan due-date evaluation, LOC alias mapping, missing/conflict handling, LOC-change-unvalidated rule, upload metadata sync, and summary/detail payload generation. |
| Rules engine | `backend/app/services/rules_engine.py` | YAML-driven deterministic rules supporting field checks, lookup, date add/compare, days-until, numeric compare, and result serialization. |
| API connectivity | `backend/app/services/api_connectivity.py`, `backend/app/services/emr_fhir.py` | OpenAPI/Swagger discovery, operation testing, SMART/FHIR/Alleva import planning. Live import is gated. |
| Audit | `backend/app/services/audit.py` | Request/data-event audit records, hash chaining, CEF/FHIR AuditEvent payloads, fallback JSONL log. |
| Runtime/version | `backend/app/services/runtime_checks.py`, `backend/app/services/version.py` | Readiness checks and `/api/version` payload from version files plus git values. |

## Frontend Entrypoints

| Entrypoint | Purpose |
|---|---|
| `frontend/src/main.tsx` | Mounts React app. |
| `frontend/src/App.tsx` | Single large UI component with auth, dashboard, review queue, Treatment Plans tracker, upload form, profile, user management, settings, logs, and API/EMR operations. |
| `frontend/src/app.css` | Application styling. |
| `frontend/src/App.test.tsx` | Vitest/Testing Library workflow tests with mocked API routes. |
| `frontend/vite.config.ts` | Vite React build/test config. |

Current frontend views are `dashboard`, `reviews`, `timeliness`, `uploads`, `profile`, `users`, `logs`, and `settings`. The Treatment Plans view provides dashboard counts, active-client queue, detail rule results, LOC history, treatment-plan history, overrides, and audit history.

## Scripts and Launchers

| File | Purpose | Keep status |
|---|---|---|
| `scripts/Start-IZ-Clinical-Notes-Analyzer.cmd` | Double-click Windows launcher; calls `startup-windows-local.ps1`. | Required for Windows target. |
| `scripts/startup-windows-local.ps1` | Main ordinary Windows source-checkout startup; creates venv, installs dependencies, generates local `.env`, builds frontend, starts desktop backend. | Required for Windows target. |
| `scripts/test-local-app-stack.ps1` | Windows local full-stack smoke test. | Required validation path. |
| `scripts/test-api-configuration-local.ps1` | Windows API harness smoke test. | Required validation path. |
| `scripts/test-alleva-api-connectivity.ps1` | External Swagger/OpenAPI/API probe script. | Keep for direct API readiness, but ensure no secret output. |
| `scripts/start-desktop-local.ps1` | Lean local desktop runner for debugging. | Referenced by README. |
| `scripts/smoke.sh` | Compose/source smoke test used by CI and docs. | Required by CI. |
| `scripts/startup-macos.sh`, `scripts/startup-ubuntu-24.04.sh` | Docker/PostgreSQL developer/server launchers. | Keep, but not ordinary Windows requirements. |
| `scripts/startup-windows.ps1` | Older dedicated PostgreSQL/Docker-oriented Windows launcher. | Legacy candidate, but referenced indirectly by server-mode docs context and should not be removed without a reference pass. |
| `scripts/lib/dedicated-postgres.sh` | Shared helper for macOS/Ubuntu Docker/PostgreSQL launchers. | Required by those scripts. |

## Data Storage Paths

Default runtime storage is OS-local app data:

| Data | Resolution |
|---|---|
| SQLite DB | `Settings.sqlite_db_path`; relative `LOCAL_SQLITE_DB_PATH` resolves under `Settings.local_app_data_dir`. |
| Uploads | `Settings.upload_dir_path`; relative `UPLOAD_DIR=uploads` resolves under local app data. |
| Logs | `Settings.log_dir_path`; relative `LOG_DIR=logs` resolves under local app data. |
| User env | `IZ_CNA_ENV_FILE` if set, otherwise `<local app data>/.env`. |
| Rules config | Repo `config/rules/alleva_treatment_plan_completeness_rules.yaml` if present, otherwise local app data path. |

Platform defaults:

| Platform | Local app data root |
|---|---|
| Windows | `%LOCALAPPDATA%\IZ Clinical Notes Analyzer` |
| macOS | `~/Library/Application Support/IZ Clinical Notes Analyzer` |
| Linux | `~/.local/share/iz-clinical-notes-analyzer` |

## Upload Flow

1. User signs in through JWT auth.
2. Frontend `uploads` view accepts `.pdf`, `.doc`, `.docx`, `.txt`, `.csv`, `.rtf`, `.jpg`, `.jpeg`, `.png`, and `.zip`, enforcing client-side file count/size limits.
3. Optional patient ID detection posts files to `/api/patient-note-sets/detect-patient-id`.
4. Upload posts metadata manifest and files to `/api/patient-note-sets`.
5. Backend validates batch size/count/types, parses file manifest, detects patient ID if missing, supersedes prior active note set when update mode is used, creates note/document rows, encrypts each file, stores SHA-256 and source metadata, generates a chart audit from the note set, and logs upload/evaluation events.
6. Downloads require auth and role access, decrypt server-side, and stream only the selected document.

## Direct API Harness Flow

1. Admin opens the settings UI or standalone `/api-configuration` page.
2. API configuration reads/writes `AppSetting` fields through `/api/api-configuration`.
3. Saved API key material uses the encrypted text envelope on the API configuration route.
4. `/api/api-configuration/sample-openapi.json` and local operation targets support synthetic smoke tests.
5. `/api/api-configuration/pull-definitions` probes Swagger/OpenAPI URLs and summarizes operations.
6. `/api/api-configuration/test-operation` executes a selected OpenAPI operation with supplied or saved API key.
7. EMR/FHIR routes expose profile, SMART discovery, and import-plan generation. They do not import live patient data.

Boundary: this harness is for configuration, testing, OpenAPI discovery, and future-readiness planning. It is not live Alleva patient import approval.

## Rules Engine Flow

1. `Settings.rules_config_file` resolves the YAML file.
2. `load_rules_config` reads YAML and `validate_rules_config` checks required structure.
3. `evaluate_rules` maps current LOC aliases, derives effective treatment-plan date, calculates due dates, and emits rule findings/statuses.
4. Current YAML has draft Treatment Plan Tracking rules for active scope, current LOC presence/mapping, treatment-plan existence/date, 30/60-day recurrence, warning window, attendance checks, and configurable aliases for PHP, IOP-5, IOP-19, IOP-3, and OP.

S2 status: the dedicated timeliness service now models initial/master signature rules, ongoing 30/60-day review recurrences, unvalidated LOC-change `Needs Review`, status priority, source conflicts, missing data, and manual override audit records. S5 still needs generic workflow CRUD/versioning.

## Audit and Logging Flow

1. Request middleware binds request context, writes security headers, and logs completed requests/unhandled exceptions.
2. API routes call `log_event` for login, user management, settings, EMR/API configuration, chart activity, upload/download, and audit log viewing.
3. SQLAlchemy session events track changes for configured models.
4. Audit records include hash chaining plus CEF and FHIR AuditEvent payloads.
5. Fallback audit records are written under the local log directory if DB persistence fails.

Current risk: some user-facing and audit messages include patient IDs and document filenames. That may be acceptable if patient ID is permitted, but the PHI/no-PHI logging policy needs explicit minimum-necessary review before pilot.

## Test Commands

Backend:

```bash
python -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q
```

Frontend:

```bash
cd frontend
npm install
npm run test -- --run
npm run build
```

Windows source-checkout validation:

```powershell
scripts\Start-IZ-Clinical-Notes-Analyzer.cmd
scripts\startup-windows-local.ps1
scripts\test-api-configuration-local.ps1
scripts\test-alleva-api-connectivity.ps1
scripts\test-local-app-stack.ps1
```

CI:

| Job | File | Behavior |
|---|---|---|
| `backend-tests` | `.github/workflows/ci.yml` | Python 3.11, install backend requirements, run pytest. |
| `frontend-build-test` | `.github/workflows/ci.yml` | Node 20, install, test, build. |
| `compose-smoke` | `.github/workflows/ci.yml` | Copy `.env.example`, run Docker Compose, run `scripts/smoke.sh`. |

## Packaging and Installer Status

The repo has Dockerfiles, Compose files, `pyinstaller` in backend requirements, and Windows source-checkout launchers. It does not yet contain a signed `.exe`/`.msi` installer, installer project, code-signing plan, repair/modify/uninstall implementation, or evidence from the target purchased Dell Windows 10/11 Home validation machine.

For v0.5.0, Windows Home validation remains a release blocker until ordinary-user install/launch, readiness, repair/upgrade/uninstall, and data preservation are verified on the target laptop.

## Current Risks

| Risk | Evidence | Impact |
|---|---|---|
| Generic workflow CRUD/versioning not yet implemented | Timeliness tracker is first-class, but workflow definition/version models are not present. | S5 must add admin-managed workflow definitions beyond the MVP tracker. |
| LOC-change update window is unvalidated | PRD open question asks what "immediate" means after LOC change. | Must stay configurable and visibly unvalidated. |
| Direct API harness remains test-only for live vendors | S4 added offline OpenAPI, saved-key encryption, redacted result/report, timeout/error, and audit redaction coverage. | Real vendor probing still requires official tenant inputs and credential-safe operator handling. |
| Current audit/log messages include patient IDs | Patient IDs remain structured audit fields for workflow traceability; S3 removed original filenames and note-derived strings from patient-note upload/download audit details. | Requires minimum-necessary logging review and PHI policy decision before pilot. |
| Live Alleva import is intentionally gated | EMR profile/import plan exists, but no approved endpoint mapping/tenant credentials. | Do not build fake live import. |
| OneDrive checkout has local untracked artifacts | `Product Requirements Document.docx` and `walkthroughs/` are untracked. | Do not delete without explicit S1 decision. |
| Windows target not validated here | macOS build agent cannot prove Dell Windows Home behavior. | Requires real Windows validation gate. |
| Installer missing | No signed installer or repair/uninstall implementation. | Required before external distribution. |
