# Codebase Map - Current Version 1.4.4

Date: 2026-06-20

Branch: `main`

Version: `1.4.4` / build `2026.06.20.1`

## Scope

This file is the current orientation map for the remote repository. Older S0/S1/S2/S3/S4/S5 notes, PRDs, walkthroughs, and external analyses remain historical references, but this document reflects the active Version 1.4.4 app shape.

## Current architecture

The app is a local-first FastAPI plus React/Vite application. The normal Windows target is a one-machine desktop-style localhost app using SQLite, local encrypted uploads, role-based access control, deterministic Treatment Plan Tracking, workflow profiles, and local audit logs under per-user app data.

Docker, PostgreSQL, and nginx container serving are not ordinary Windows 10/11 requirements and are not the active R3 desktop deployment path. The old Docker/nginx archive folder and database-expose compose overlay were removed on 2026-06-17 after reference scans; deprecated legacy startup scripts remain for historical context and must not be treated as current launch instructions.

## Backend entrypoints

| Entrypoint | Purpose |
| --- | --- |
| `backend/app/main.py` | FastAPI app factory, startup readiness/schema/admin bootstrap, security headers, health/readiness/version, and primary API routers. |
| `backend/app/desktop_main.py` | Desktop runtime wrapper; serves local pages and `frontend/dist` when built. |
| `backend/app/api/routes.py` | Main authenticated API: settings, readiness, EMR profile/discovery/import-plan, chart audit, patient-note uploads/downloads, checklist, UI events, and audit logs. |
| `backend/app/api/auth_user_routes.py` | Authentication, profile/reset updates, and role-scoped user-management APIs. |
| `backend/app/api/timeliness_routes.py` | Treatment Plan Timeliness dashboard/detail/client/override APIs. |
| `backend/app/api/workflow_routes.py` | Workflow profile CRUD, draft versioning, publish/archive, and unused-draft deletion APIs. |
| `backend/app/api/api_config_routes.py` | Direct API harness for API configuration, local sample OpenAPI, OpenAPI/Swagger discovery, and selected operation testing. |
| `backend/app/api/rules_routes.py` | Rules profile and ad hoc rules evaluation API. |
| `backend/app/api/api_config_ui_routes.py` | Standalone HTML page for API configuration/testing. |
| `backend/app/api/clinical_notes_ui_routes.py` | Standalone HTML intake guide for manual upload and future direct API lookup. |

## Backend services

| Area | Files | Current behavior |
| --- | --- | --- |
| Models | `backend/app/models/models.py` | Users, app settings, EMR endpoint profiles, charts, patient note sets/documents, workflow definitions/versions, audit logs, timeliness clients, LOC history, treatment-plan records, and manual overrides. |
| Schemas | `backend/app/schemas/schemas.py` | Pydantic contracts for auth/users/settings/readiness/EMR/chart/note-set/audit/timeliness/workflow APIs. |
| Config | `backend/app/core/config.py` | SQLite-first defaults; relative DB/upload/log/report paths resolve into OS-local app data. |
| Security | `backend/app/core/security.py`, `backend/app/api/deps.py` | JWT auth, role checks, and reset gate. |
| Upload storage | `backend/app/services/patient_notes.py`, `backend/app/services/secure_storage.py` | File validation, patient ID detection, encrypted file writes, path traversal prevention, and protected text helper. |
| Evaluation | `backend/app/services/evaluation.py` | Deterministic chart-audit item generation from uploaded note metadata/text, with optional LLM hooks. |
| Timeliness | `backend/app/services/timeliness.py` | Treatment-plan date-clock evaluation, local current-date handling, PHP 30-day and non-PHP 60-day recurrence, configurable unvalidated 7-day LOC-change review, LOC alias mapping, source-evidence locations, missing/conflict handling, upload/API-style re-evaluation, fallback generated names, workflow-version audit context, and manual override audit records. |
| Rules engine | `backend/app/services/rules_engine.py` | YAML-driven deterministic rules. |
| API connectivity | `backend/app/services/api_connectivity.py`, `backend/app/services/api_monitor.py`, `backend/app/services/alleva_treatment_plan_sync.py`, `backend/app/services/emr_fhir.py` | OpenAPI/Swagger discovery, operation testing, OAuth/FHIR readiness, EMR endpoint profiles, gated Alleva REST treatment-plan sync into the R3 timeliness engine, and FHIR import planning. Ungated live import is disabled. |
| Audit | `backend/app/services/audit.py` | Request/data-event audit records, hash chaining, CEF/FHIR-style payloads, fallback JSONL log. |
| Runtime/version | `backend/app/services/runtime_checks.py`, `backend/app/services/version.py` | Readiness checks and `/api/version` payload from version files plus git values. |

## Frontend entrypoints

| Entrypoint | Purpose |
| --- | --- |
| `frontend/src/main.tsx` | Mounts React app. |
| `frontend/src/App.tsx` | Main React app with auth, dashboard, review queue, Treatment Plans tracker, upload form, profile, help, user management, workflow profiles, settings, logs, and API/EMR operations. |
| `frontend/src/components/feedback.tsx` | Shared feedback UI for dialogs, confirmation prompts, and upload progress. |
| `frontend/src/app.css` | Application styling, status colors, responsive layouts, and UI polish. |
| `frontend/src/App.test.tsx` | Vitest/Testing Library workflow tests with mocked API routes. |
| `frontend/vite.config.ts` | Vite React build/test config. |

Current frontend views are `dashboard`, `reviews`, `timeliness`, `checklist`, `uploads`, `profile`, `help`, `users`, `workflows`, `logs`, and `settings`.

## Active and legacy scripts

| File | Current status | Purpose |
| --- | --- | --- |
| `scripts/Start-IZ-Clinical-Notes-Analyzer.cmd` | Active | Double-click Windows launcher. |
| `scripts/startup-windows-local.ps1` | Active | Main ordinary Windows source-checkout startup. |
| `scripts/preflight-windows.ps1` | Active | Windows preflight for env, dependencies, rules/checklists, frontend build, and report output. |
| `scripts/setup-windows.ps1` | Active | Windows setup helper. |
| `scripts/start-windows-local.ps1` | Active | Windows local startup wrapper used by release launch command. |
| `scripts/test-local-app-stack.ps1` | Active | Windows local full-stack smoke test. |
| `scripts/test-api-configuration-local.ps1` | Active | Windows API harness smoke test. |
| `scripts/build-windows-installer.ps1` | Active | Builds release folder and zip with install/launch/uninstall commands. |
| `scripts/update-local-admin.ps1` | Active | Authorized local admin reset utility. |
| `scripts/test-alleva-api-connectivity.ps1` | Active with caution | Simple redacted Alleva/OpenAPI reachability report script. |
| `Test-AllevaApi.ps1` | Active diagnostic with high caution | Full diagnostic script; use redaction mode before creating shareable logs. |
| `scripts/smoke.sh` | Active generic smoke | Checks a running app through `BASE_URL`. |
| `scripts/startup-windows.ps1` | Deprecated legacy | Older Docker/PostgreSQL-oriented Windows launcher. Do not use for Version 1.4.4 local desktop startup. |
| `scripts/startup-macos.sh` | Deprecated legacy | Older Docker/PostgreSQL-oriented macOS launcher. |
| `scripts/startup-ubuntu-24.04.sh` | Deprecated legacy | Older Docker/PostgreSQL-oriented Ubuntu launcher. |
| `scripts/lib/dedicated-postgres.sh` | Legacy helper | Preserved for deprecated Docker/PostgreSQL launchers only. |

## Data storage paths

| Data | Resolution |
| --- | --- |
| SQLite DB | `Settings.sqlite_db_path`; relative `LOCAL_SQLITE_DB_PATH` resolves under `Settings.local_app_data_dir`. |
| Uploads | `Settings.upload_dir_path`; relative `UPLOAD_DIR=uploads` resolves under local app data. |
| Logs | `Settings.log_dir_path`; relative `LOG_DIR=logs` resolves under local app data. |
| App API reports | `api-reports` under local app data. |
| Standalone connectivity reports | `api-connectivity-reports` under local app data. |
| User env | `IZ_CNA_ENV_FILE` if set, otherwise `<local app data>/.env`. |
| Rules config | Repo `config/rules/alleva_treatment_plan_completeness_rules.yaml` if present, otherwise local app data path. |

The active non-technical deployment target is Windows.

## Major flows

### Upload flow

1. User signs in through JWT auth.
2. Frontend `uploads` view accepts supported clinical-note file types and enforces client-side file count/size limits.
3. Optional patient ID detection posts files to `/api/patient-note-sets/detect-patient-id`.
4. Upload posts metadata manifest and files to `/api/patient-note-sets`.
5. Backend validates the batch, detects patient ID if needed, supersedes prior active note set when update mode is used, creates note/document rows, encrypts files, stores source metadata, generates a chart audit, and logs upload/evaluation events.
6. Downloads require auth and role access, decrypt server-side, and stream only the selected document.
7. Authorized deletion removes the selected note set, linked generated review charts, upload-derived timeliness records, and encrypted stored files while preserving audit logs.

### Direct API harness flow

1. Admin opens App settings or standalone `/api-configuration` page.
2. API configuration reads/writes `AppSetting` fields through `/api/api-configuration`.
3. Saved API configuration is protected at rest.
4. `/api/api-configuration/sample-openapi.json` and local operation targets support synthetic smoke tests.
5. `/api/api-configuration/pull-definitions` probes Swagger/OpenAPI URLs and summarizes operations.
6. `/api/api-configuration/test-operation` executes a selected OpenAPI operation with supplied or saved auth values.
7. EMR/FHIR routes expose profile, endpoint profiles, FHIR/OAuth discovery, and import-plan generation. They do not import live patient data.

### Rules and workflow flow

1. `Settings.rules_config_file` resolves the YAML file.
2. Rules config is loaded and validated.
3. The timeliness service models initial/master signature rules, ongoing review recurrences, unvalidated LOC-change review, status priority, source conflicts, missing data, fallback generated names, and manual override audit records.
4. Workflow profile CRUD/versioning exists as admin/manager-managed definitions with draft/published/archived versions, transition rules, default Treatment Plan Timeliness seeding, validation, and draft-only delete limits.

## Test commands

Backend:

```powershell
$env:PYTHONPATH = "$PWD\backend"
.\backend\.venv\Scripts\python.exe -m pytest .\backend\tests -q
```

Frontend:

```powershell
cd frontend
npm test -- --run
npm run build
cd ..
```

Windows source-checkout validation:

```powershell
.\scripts\preflight-windows.ps1 -AssumeYes
.\scripts\test-local-app-stack.ps1
.\scripts\test-api-configuration-local.ps1
```

## CI

Current CI should cover:

| Job | File | Behavior |
| --- | --- | --- |
| `backend-tests` | `.github/workflows/ci.yml` | Python 3.11, install backend requirements, run pytest. |
| `frontend-build-test` | `.github/workflows/ci.yml` | Node 20, install, test, build. |

The old Docker Compose smoke job is not current because the active root full-stack Docker Compose file was moved out of the active app path. Reintroduce Compose CI only if R3 deliberately restores Docker/server deployment and updates active compose files, docs, and validation together.

## Packaging and installer status

`scripts/build-windows-installer.ps1` creates a Version 1.4.4 release folder and zip with install, launch, uninstall, and manifest files. The package is still not a signed MSI/MSIX with repair/modify support. Windows Home validation remains a release blocker until ordinary-user install/launch, readiness, prompted source-checkout setup, stale frontend build detection, repair/upgrade/uninstall, and data preservation are verified on the target laptop with synthetic data.

## Current risks

| Risk | Current state | Impact |
| --- | --- | --- |
| Browser/full-stack smoke is source-checkout validated only | Version 1.4.4 keeps Treatment Plan Timeliness evidence, prompted/stale `frontend\dist` handling, 42-step checklist workflow coverage, date-clock/workflow-export behavior, gated Alleva REST sync readiness, and example-plan upload validation on the current machine. | Target Dell Windows validation still needs the target machine before broad rollout. |
| Live Alleva import is disabled | API harness and EMR profiles support readiness/testing only, with no approved endpoint mapping or tenant details for production import. | Do not promise or fake live patient import until R3/Alleva clears the integration gate. |
| LOC-change update window is unvalidated | The app ships a manager-editable 7-calendar-day preset because R3/Marleigh has not confirmed the final rule. | Must stay configurable and visibly unresolved. |
| Direct API harness remains test-only for live vendors | The harness supports offline OpenAPI, protected saved configuration, redacted result/report handling, timeouts, and audit redaction. | Real vendor probing still requires official tenant inputs and safe operator handling. |
| Current audit/log messages include patient IDs | Patient IDs remain structured audit fields for workflow traceability; uploaded note text, protected values, and original filenames remain excluded. | Requires minimum-necessary logging review and PHI policy decision before pilot. |
| Signed installer is not complete | Release folder builder exists, but no signed MSI/MSIX with repair/modify support exists. | Non-technical rollout still needs final target-machine packaged validation. |
| Root diagnostic script can expose sensitive values | `Test-AllevaApi.ps1` is intentionally detailed by default. | Use only on approved private diagnostic machines; use redaction mode for shareable logs and still review output. |
| Legacy Docker files were removed from the active tree | Deprecated startup scripts remain, but the old Docker/nginx archive and compose overlay were removed after S1 cleanup evidence. | Do not treat Docker/PostgreSQL as normal R3 desktop requirements or restore the old stack without an explicit R3/server decision. |

## Version Metadata

The current app version is:

```text
1.4.4
```

Version metadata is stored in `VERSION`, `VERSION.json`, and `frontend/package.json`. The backend exposes it at:

```text
GET /api/version
```

The UI footer displays the backend-provided version, environment, and short git commit when available.
