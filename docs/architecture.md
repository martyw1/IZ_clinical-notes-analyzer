# Architecture Overview

IZ Clinical Notes Analyzer is a React + FastAPI + PostgreSQL application for enterprise chart review workflows.

## Runtime components
- **Frontend**: React/Vite app served via nginx in Docker.
- **Backend**: FastAPI app with JWT auth, RBAC, workflow state controls, uploads, and audit logging.
- **Database**: Dedicated PostgreSQL service owned by this application and managed through Docker Compose.
- **Backend data volume**: encrypted clinical source files and audit fallback logs, kept outside the OneDrive-backed repository by default.

## Local security model
- Docker Compose binds frontend, backend, and PostgreSQL to `127.0.0.1` by default.
- Startup scripts generate strong local secrets when `.env` still contains placeholders.
- Backend startup runs dependency/readiness checks before database bootstrap completes.
- Uploaded clinical files are encrypted before they are written to disk and decrypted only for authorized downloads or local analysis.
- Relative upload/log paths resolve to OS-local app data on host runs; Compose uses a dedicated backend data volume.
- Managed users with `must_reset_password=true` can only read their own profile and reset/change their password until the reset is complete.

## Forensic audit logging
- Every HTTP request is assigned a request ID and correlation ID and is logged on completion, including status code, route, latency, source IP, forwarded IP chain, and user-agent.
- Authenticated actions bind actor identity into the request context so committed database changes can be tied back to the requesting user.
- All committed inserts, updates, and deletes for tracked domain models are captured automatically with before-state, after-state, and field-level diff payloads.
- Explicit domain events are also emitted for sensitive reads and workflow actions such as login, password reset, chart transitions, and audit log access.
- Patient note-set uploads and downloads also emit explicit file activity events, and each stored file carries a persisted SHA-256 hash plus byte count for forensic validation.
- Audit records are tamper-evident through hash chaining and also carry CEF-style payloads plus FHIR AuditEvent-style JSON for downstream compliance integrations.
- If the audit log cannot be written to the database, records are spooled to `logs/forensic-audit-fallback.jsonl` so evidence is not silently lost.

## Patient note binders
- The app now tracks work by `patient_id` instead of relying on patient name in the UI workflow.
- Alleva-compatible document uploads are grouped into immutable `patient_note_sets`, with each update creating a new version and marking the previous active version as superseded.
- Individual uploaded files are stored as encrypted `patient_note_documents` with Alleva bucket metadata, completion state, signature flags, document dates, size, content type, and SHA-256 digest.
- The frontend presents those note sets as a document-manager-style binder so counselors and office managers can upload, update, inspect, and download source documents without overwriting historical evidence.

## EMR integration boundary
- The current production-ready path remains local file upload from the EMR export.
- Admin settings now capture a vendor label, FHIR base URL, SMART client metadata, scopes, and timeout.
- The backend exposes a SMART discovery check and a FHIR R4 import plan around `Patient`, `DocumentReference`, `Binary`, and optional `Provenance`.
- Alleva live API import is intentionally stubbed until the client/vendor supplies official API documentation, registration details, credentials, and allowed scopes.

## Database connectivity model
Configuration is explicit and deterministic:
- `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD` define the dedicated application database.
- `DATABASE_URL` is optional; when omitted, the backend assembles the DSN from the component settings.
- Backend containers automatically rewrite host-local Postgres URLs to the internal Compose `postgres` service.
- Startup scripts provision the dedicated application database before the backend starts, so the VPS deployment does not depend on any shared PostgreSQL service.

## Health model
- `/health` for direct infra probes.
- `/api/health` for API/proxy-friendly probes.
- `/api/readiness` for unauthenticated runtime readiness.
- `/api/system/readiness` for admin-visible readiness checks with audit logging.
