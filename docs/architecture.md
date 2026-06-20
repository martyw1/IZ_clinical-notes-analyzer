# Architecture Overview

Date: 2026-06-20

Applies to: IZ Clinical Notes Analyzer Version `1.4.4` / build `2026.06.20.1`.

## Current architecture

IZ Clinical Notes Analyzer is a local-first React + FastAPI desktop-style app for Windows chart review workflows. The normal Windows 10/11 path is one local FastAPI service at `http://localhost:8000`, a built React/Vite browser UI, SQLite in the user's local app-data folder, encrypted local uploads, protected API configuration storage, role-based access control, deterministic Treatment Plan Tracking rules, workflow profiles, readiness checks, and forensic audit logging.

The active Version 1.4.4 product path is local Windows desktop use. Docker, PostgreSQL, and nginx container serving are not ordinary runtime requirements and are not the current supported R3 desktop deployment path.

The deprecated Docker/nginx archive and unused Compose overlay were removed on 2026-06-17 after reference scans proved no active launch, test, backend, frontend, config, or CI path used them. Do not restore those files to active paths unless R3 explicitly reintroduces Docker/server deployment and updates README, Windows docs, CI, tests, and release instructions together.

## Runtime components

- **Desktop runtime**: `backend/app/desktop_main.py` serves the built React app and desktop-only local pages from the same localhost service.
- **Frontend**: React/Vite app in `frontend/src`, built to `frontend/dist` and served by the desktop runtime.
- **Backend**: FastAPI app with JWT auth, RBAC, workflow state controls, encrypted uploads, deterministic rule execution, API readiness harnesses, and audit logging.
- **Database**: SQLite by default for Windows desktop installs, stored under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.
- **Local data**: encrypted clinical source files, API reports, startup logs, fallback audit logs, and `.env` live under OS-local app data, not in the OneDrive-backed repository.
- **Version metadata**: `VERSION` and `VERSION.json` are exposed through `/api/version` and shown in the UI footer when available.

## Local security model

- Windows startup scripts bind the app to localhost and keep runtime data outside the source checkout.
- Startup/preflight creates local AppData folders and a local `.env` when missing.
- Backend startup runs dependency/readiness checks before the app is considered ready.
- Uploaded clinical files are encrypted before they are written to disk and decrypted only for authorized downloads or local analysis.
- Saved API configuration values are protected and are not returned to the browser.
- Relative upload, log, database, and API-report paths resolve through `Settings.local_app_data_dir`.
- Managed users with a required reset can only read their own profile and complete the reset flow until that requirement is complete.

## Forensic audit logging

- Every HTTP request is assigned a request ID and correlation ID and is logged on completion, including status code, route, latency, source IP, forwarded IP chain, and user-agent.
- Authenticated actions bind actor identity into the request context so committed database changes can be tied back to the requesting user.
- Committed inserts, updates, and deletes for tracked domain models are captured with before-state, after-state, and field-level diff payloads.
- Explicit domain events are emitted for sensitive reads and workflow actions such as login, reset flows, chart transitions, audit log access, UI button events, blocked workflow clicks, API harness activity, and safe review-source checks.
- Patient note-set uploads and downloads emit explicit file activity events, and each stored file carries a persisted SHA-256 hash plus byte count for forensic validation.
- Audit records are tamper-evident through hash chaining and also carry CEF-style payloads plus FHIR AuditEvent-style JSON for downstream compliance integrations.
- If the audit log cannot be written to the database, records are spooled to the local app-data log directory so evidence is not silently lost.
- Audit snapshots redact uploaded filenames, storage paths, document labels, descriptions, and source attachment/author metadata.

## Patient note binders

- The app tracks work by `patient_id` instead of relying on patient name in the UI workflow.
- Alleva-compatible document uploads are grouped into immutable `patient_note_sets`, with each update creating a new version and marking the previous active version as superseded.
- Individual uploaded files are stored as encrypted `patient_note_documents` with Alleva bucket metadata, completion state, signature flags, document dates, size, content type, and SHA-256 digest.
- The frontend presents note sets as a document-manager-style binder so counselors and office managers can upload, update, inspect, delete, and download source documents without overwriting historical evidence.
- Authorized binder deletion removes the selected note set, linked generated review charts, upload-derived timeliness records, and encrypted stored files while retaining forensic audit logs.
- PDF uploads retain page-level extracted text when available so deterministic findings can cite manual source locations such as `manual upload page 2` without logging raw clinical note text.

## Treatment-plan timeliness model

- The Treatment Plans view is the default landing work queue for admins and office managers when no explicit view is requested.
- The timeliness evaluator uses the local/facility current date, admission date, latest valid treatment-plan review/update date, current LOC, and LOC history to calculate status.
- PHP levels use a 30-calendar-day recurring update interval; other configured treatment levels use 60 calendar days.
- LOC changes use a separate manager-editable 7-calendar-day preset that remains unvalidated until R3/Marleigh confirms the final rule.
- Missing names fall back to `no-name-found_YYYY-MM-DD_HHMMSS` or `no-value-found_YYYY-MM-DD_HHMMSS`.
- Timeliness analysis results are audited with workflow definition key/version/checklist context, and CSV/JSON exports include both checklist/domain rows and active workflow-step statuses.

## EMR/API integration boundary

- The current production-style path remains local file upload from an EMR export.
- Admin App settings capture a vendor label, FHIR base URL, OpenAPI URL, OAuth/FHIR client metadata, token URL, scopes, timeout, token auth style, and protected direct-API configuration state.
- Stored EMR endpoint profiles capture multiple Alleva/future EMR endpoint options with protected client configuration and an active/default profile used by readiness checks.
- The backend exposes a FHIR/OAuth discovery check and a FHIR R4 import plan around `Patient`, `DocumentReference`, `Binary`, and optional `Provenance`.
- The direct API harness can discover OpenAPI/Swagger definitions and test selected operations with API-key or client-credentials auth, while redacting sensitive values from browser payloads, reports, and audit details. Alleva Swagger/OpenAPI URLs are not treated as FHIR base URLs.
- The gated Alleva REST treatment-plan sync path uses the Alleva REST API base URL/OpenAPI mapping, not the FHIR base URL, to normalize approved active-client, treatment-plan, and treatment-review payloads into the local R3 timeliness engine.
- Ungated Alleva live patient import is intentionally disabled until R3/Alleva supplies approved tenant details, endpoint mapping, scopes, pagination/rate limits, attachment/signature behavior, vendor documentation, and compliance approval.

## Database connectivity model

Configuration is explicit and deterministic:

- `DATABASE_BACKEND=sqlite` is the normal Windows local-desktop setting.
- `DATABASE_URL` defaults to a SQLite file under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer` for the local desktop path.
- Relative SQLite, upload, log, and report paths are resolved through the configured local app-data directory.
- PostgreSQL environment keys can remain in `.env.example` for historical/developer reference, but the active Version 1.4.4 Windows product path does not require a PostgreSQL container.

## Health model

- `/health` for direct infra probes.
- `/api/health` for API/proxy-friendly probes.
- `/api/readiness` for unauthenticated runtime readiness.
- `/api/system/readiness` for admin-visible readiness checks with audit logging.
