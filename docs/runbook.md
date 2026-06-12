# Operations Runbook

## Health endpoints
- Backend direct: `GET /health`
- Backend API alias: `GET /api/health`
- Through frontend proxy: `GET /api/health`

## Forensic log handling
- Primary forensic logs are stored in the `audit_logs` table.
- Each record includes request metadata, actor identity, source IP, event category, CEF payload, FHIR AuditEvent JSON, and a tamper-evident hash chain.
- If database persistence fails during logging, the app writes JSONL fallback records under the local app-data log directory.
- Admin access to forensic logs is available through `GET /api/audit/logs`.
- Preserve UTC timestamps during exports, use the app-provided local timestamp for operator review, and correlate events using `request_id` and `correlation_id`.

## Patient note set handling
- Patient note uploads are keyed by `patient_id` and stored under `UPLOAD_DIR/patient-notes/...`.
- Initial uploads use `POST /api/patient-note-sets` with `upload_mode=initial`; later changes must use `upload_mode=update`, which creates a new immutable version instead of replacing the prior set.
- Current and historical binders can be listed with `GET /api/patient-note-sets` and inspected with `GET /api/patient-note-sets/{id}`.
- Stored source files can be retrieved with `GET /api/patient-note-sets/{note_set_id}/documents/{document_id}/download`.
- Every stored file has a SHA-256 digest in the database; use that hash when validating backup integrity or investigating file tampering.

## Windows desktop runtime
- The ordinary Windows path runs one local FastAPI desktop service at `http://localhost:8000`.
- The default database is SQLite under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.
- Uploads, logs, API reports, and `.env` also live under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.
- Use `scripts\Start-IZ-Clinical-Notes-Analyzer.cmd` for double-click launch and `scripts\preflight-windows.ps1 -AssumeYes` for support validation.
- Do not move runtime data into the OneDrive-backed source repository.

## Developer/server runtime
- Docker and PostgreSQL remain optional developer/server modes.
- `scripts/startup-ubuntu-24.04.sh` and `scripts/startup-macos.sh` bring up their Docker/PostgreSQL dependencies for those scenarios.
- Do not present Docker, PostgreSQL, Git, Node.js, or command-line work as ordinary Windows desktop requirements.

## Recovery
- If the Windows app will not start, inspect `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\logs\preflight-windows-latest.json` and the startup logs in the same AppData tree.
- If no local admin can sign in, follow `docs\admin-access-reset.md`.
- For Docker/PostgreSQL developer mode only, a DB password mismatch requires restoring the original database credentials or rebuilding that developer database. Treat volume resets as destructive.

## Backup/restore
For ordinary Windows desktop installs:

- Back up the entire `%LOCALAPPDATA%\IZ Clinical Notes Analyzer` directory according to R3 policy.
- Keep the backup encrypted and access-controlled because it can contain local SQLite data, encrypted uploads, audit logs, and configuration.
- Restore by stopping the local app, replacing the AppData directory from the approved backup, and restarting the app.

For Docker/PostgreSQL developer/server runs only:

- Backup: `pg_dump -Fc iz_clinical_notes_analyzer > backup.dump`
- Restore: `pg_restore -d iz_clinical_notes_analyzer backup.dump`
