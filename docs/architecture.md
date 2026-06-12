# Architecture Overview

IZ Clinical Notes Analyzer is a local-first React + FastAPI desktop-style app for Windows chart review workflows. The normal Windows 10/11 path is one local FastAPI service at `http://localhost:8000`, a built React/Vite browser UI, SQLite in the user's local app-data folder, encrypted local uploads, and forensic audit logging.

Docker and PostgreSQL remain developer/server options only. They are not ordinary Windows desktop requirements.

## Runtime components
- **Desktop runtime**: `backend/app/desktop_main.py` serves the built React app and desktop-only local pages from the same localhost service.
- **Frontend**: React/Vite app in `frontend/src`, built to `frontend/dist` and served by the desktop runtime.
- **Backend**: FastAPI app with JWT auth, RBAC, workflow state controls, encrypted uploads, deterministic rule execution, API readiness harnesses, and audit logging.
- **Database**: SQLite by default for Windows desktop installs, stored under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.
- **Local data**: encrypted clinical source files, API connectivity reports, startup logs, fallback audit logs, and `.env` live under OS-local app data, not in the OneDrive-backed repository.
- **Developer/server runtime**: Docker/PostgreSQL scripts still exist for non-desktop scenarios and are documented as separate from normal Windows use.

## Local security model
- Windows startup scripts bind the app to localhost and keep runtime data outside the source checkout.
- Startup/preflight creates local AppData folders and a local `.env` when missing.
- Backend startup runs dependency/readiness checks before the app is considered ready.
- Uploaded clinical files are encrypted before they are written to disk and decrypted only for authorized downloads or local analysis.
- Relative upload, log, database, and API-report paths resolve through `Settings.local_app_data_dir`.
- Managed users with `must_reset_password=true` can only read their own profile and reset/change their password until the reset is complete.

## Forensic audit logging
- Every HTTP request is assigned a request ID and correlation ID and is logged on completion, including status code, route, latency, source IP, forwarded IP chain, and user-agent.
- Authenticated actions bind actor identity into the request context so committed database changes can be tied back to the requesting user.
- All committed inserts, updates, and deletes for tracked domain models are captured automatically with before-state, after-state, and field-level diff payloads.
- Explicit domain events are also emitted for sensitive reads and workflow actions such as login, password reset, chart transitions, audit log access, UI button events, blocked workflow clicks, API harness activity, and safe review-source checks.
- Patient note-set uploads and downloads also emit explicit file activity events, and each stored file carries a persisted SHA-256 hash plus byte count for forensic validation.
- Audit records are tamper-evident through hash chaining and also carry CEF-style payloads plus FHIR AuditEvent-style JSON for downstream compliance integrations.
- If the audit log cannot be written to the database, records are spooled to the local app-data log directory so evidence is not silently lost.

## Patient note binders
- The app now tracks work by `patient_id` instead of relying on patient name in the UI workflow.
- Alleva-compatible document uploads are grouped into immutable `patient_note_sets`, with each update creating a new version and marking the previous active version as superseded.
- Individual uploaded files are stored as encrypted `patient_note_documents` with Alleva bucket metadata, completion state, signature flags, document dates, size, content type, and SHA-256 digest.
- The frontend presents those note sets as a document-manager-style binder so counselors and office managers can upload, update, inspect, and download source documents without overwriting historical evidence.

## EMR integration boundary
- The current production-ready path remains local file upload from the EMR export.
- Admin settings capture a vendor label, FHIR base URL, SMART client metadata, token URL, scopes, timeout, and encrypted direct-API credential state.
- The backend exposes a SMART discovery check and a FHIR R4 import plan around `Patient`, `DocumentReference`, `Binary`, and optional `Provenance`.
- The direct API harness can discover OpenAPI/Swagger definitions and test selected operations with API-key or client-credentials auth, while redacting tokens/secrets from browser payloads, reports, and audit details.
- Alleva live patient import is intentionally disabled until R3/Alleva supplies approved tenant credentials, endpoint mapping, scopes, pagination/rate limits, attachment behavior, vendor documentation, and compliance approval.

## Database connectivity model
Configuration is explicit and deterministic:
- `DATABASE_URL` defaults to a SQLite file under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.
- Relative SQLite, upload, log, and report paths are resolved through the configured local app-data directory.
- PostgreSQL settings are optional and only for developer/server deployments that intentionally opt into them.
- Windows desktop startup does not require Docker, PostgreSQL, Git, Node.js, or command-line work when using a prepared release folder with built frontend assets.

## Health model
- `/health` for direct infra probes.
- `/api/health` for API/proxy-friendly probes.
- `/api/readiness` for unauthenticated runtime readiness.
- `/api/system/readiness` for admin-visible readiness checks with audit logging.
