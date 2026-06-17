# Architecture Overview

Date: 2026-06-16

Applies to: IZ Clinical Notes Analyzer Version `1.3.0` / build `2026.06.16.1`.

## Current architecture

IZ Clinical Notes Analyzer is a local-first React + FastAPI desktop-style app for Windows chart review workflows. The normal Windows 10/11 path is one local FastAPI service at `http://localhost:8000`, a built React/Vite browser UI, SQLite in the user's local app-data folder, encrypted local uploads, encrypted saved API secrets, role-based access control, deterministic Treatment Plan Tracking rules, workflow profiles, readiness checks, and forensic audit logging.

The active Version 1.3.0 product path is local Windows desktop use. Docker, PostgreSQL, and nginx container serving are not ordinary runtime requirements and are not the current supported R3 desktop deployment path.

Legacy Docker/PostgreSQL artifacts are preserved under `depriceated/` for history and rollback reference. The folder name is intentionally spelled `depriceated/` because that was the earlier project instruction. Do not restore those files to active paths unless R3 explicitly reintroduces Docker/server deployment and updates README, Windows docs, CI, tests, and release instructions together.

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
- Saved API keys and client secrets are encrypted and are not returned to the browser.
- Relative upload, log, database, and API-report paths resolve through `Settings.local_app_data_dir`.
- Managed users with `must_reset_password=true` can only read their own profile and reset/change their password until the reset is complete.

## Forensic audit logging

- Every HTTP request is assigned a request ID and correlation ID and is logged on completion, including status code, route, latency, source IP, forwarded IP chain, and user-agent.
- Authenticated actions bind actor identity into the request context so committed database changes can be tied back to the requesting user.
- Committed inserts, updates, and deletes for tracked domain models are captured with before-state, after-state, and field-level diff payloads.
- Explicit domain events are emitted for sensitive reads and workflow actions such as login, password reset, chart transitions, audit log access, UI button events, blocked workflow clicks, API harness activity, and safe review-source checks.
- Patient note-set uploads and downloads emit explicit file activity events, and each stored file carries a persisted SHA-256 hash plus byte count for forensic validation.
- Audit records are tamper-evident through hash chaining and also carry CEF-style payloads plus FHIR AuditEvent-style JSON for downstream compliance integrations.
- If the audit log cannot be written to the database, records are spooled to the local app-data log directory so evidence is not silently lost.
- Audit snapshots redact uploaded filenames, storage paths, document labels, descriptions, and source attachment/author metadata.

## Patient note binders

- The app tracks work by `patient_id` instead of relying on patient name in the UI workflow.
- Alleva-compatible document uploads are grouped into immutable `patient_note_sets`, with each update creating a new version and marking the previous active version as superseded.
- Individual uploaded files are stored as encrypted `patient_note_documents` with bucket metadata, completion state, signature flags, document dates, size, content type, and SHA-256 digest.
- The frontend presents note sets as a document-manager-style binder so counselors and office managers can upload, update, inspect, delete, and download source documents without overwriting historical evidence.
- Authorized binder deletion removes the selected note set, linked generated review charts, upload-derived timeliness records, and encrypted stored files while retaining forensic audit logs.

## Treatment Plan Timeliness

- The Treatment Plans view is the default landing work queue for admins and office managers when no explicit view is requested.
- The work queue shows active clients, LOC, counselor/primary clinician, admission date, last valid treatment-plan review date, next due date, days until due, status, rule used, source evidence summary, evidence completeness, detail records, manual overrides, and recent audit history.
- The selected-client detail view compares source-document `Next Review Due`, staff-signature cadence due date, and LOC-effective cadence due date side by side.
- Uploaded and API-style re-pulled evidence re-runs deterministic evaluation while preserving historical audit context.
- Missing names fall back to `generated-name_YYYYMMDD_HHMMSS` or `patient-id_YYYYMMDD_HHMMSS` according to whether a patient ID exists.
- The LOC-change update window remains unvalidated by R3/Marleigh and must remain configurable and visibly marked as unresolved.

## EMR/API integration boundary

- The current production-style path remains local file upload from an EMR export.
- Admin App settings capture vendor label, FHIR base URL, OAuth/FHIR client metadata, token URL, scopes, timeout, token auth style, and encrypted direct-API credential state.
- Stored EMR endpoint profiles capture multiple Alleva/future EMR endpoint options with encrypted client secrets and an active/default profile used by readiness checks.
- The backend exposes a FHIR/OAuth discovery check and a FHIR R4 import plan around `Patient`, `DocumentReference`, `Binary`, and optional `Provenance`.
- The direct API harness can discover OpenAPI/Swagger definitions and test selected operations with API-key or client-credentials auth, while redacting tokens/secrets from browser payloads, reports, and audit details.
- Alleva live patient import is intentionally disabled until R3/Alleva supplies approved tenant credentials, endpoint mapping, scopes, pagination/rate limits, attachment behavior, vendor documentation, and compliance approval.

## Database connectivity model

Configuration is explicit and deterministic:

- `DATABASE_BACKEND=sqlite` is the normal Windows local-desktop setting.
- `DATABASE_URL` defaults to a SQLite file under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer` for the local desktop path.
- Relative SQLite, upload, log, and report paths are resolved through the configured local app-data directory.
- PostgreSQL environment keys can remain in `.env.example` for historical/developer reference, but the active Version 1.3.0 Windows product path does not require a PostgreSQL container.

## Health model

- `/health` for direct infra probes.
- `/api/health` for API/proxy-friendly probes.
- `/api/readiness` for unauthenticated runtime readiness.
- `/api/system/readiness` for admin-visible readiness checks with audit logging.
