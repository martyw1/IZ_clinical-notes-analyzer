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
- Uploaded binders can be deleted with `DELETE /api/patient-note-sets/{id}` by an authorized user. Deletion removes the selected note set, linked generated review charts, upload-derived timeliness records, and encrypted stored files. If the deleted binder was the current active version and an older version remains, the latest remaining version is reactivated and resynced into the timeliness tracker.
- Every stored file has a SHA-256 digest in the database; use that hash when validating backup integrity or investigating file tampering.
- Forensic audit logs are retained after binder deletion. Audit snapshots redact uploaded filenames, storage paths, document labels, descriptions, and source attachment/author metadata.

## API readiness checks
- The admin API harness is available at `/api-configuration` in the Windows desktop runtime.
- When opened from App settings, the harness uses the current admin session; it should not prompt for a second admin login inside the harness.
- The harness supports API-key auth, no-auth probes, and OAuth client credentials using body credentials, Basic auth, URL-encoded Basic auth, or try-both/try-all fallback modes.
- Operation-test responses are capped before returning to the UI. Large responses are marked as truncated and summarized instead of rendering the full payload.
- Periodic API readiness checks can be enabled in App settings after saving API/FHIR base URL, token URL, client ID, encrypted client secret, token auth style, and interval.
- FHIR base URL means the root FHIR R4 endpoint supplied by Alleva or a future EMR vendor.
- Stored EMR endpoint profiles are admin-only and can be activated for the current readiness/API test configuration without returning stored secrets to the browser.
- Periodic checks authenticate and pull/summarize API definitions only. They do not import live Alleva patient data until the live-import compliance gate is cleared.

## Roles and workflow controls
- Admins can use every screen and action, including all user roles, App settings, API/EMR, LLM, workflow profiles, logs, uploads, reviews, overrides, and exports.
- Office managers can manage counselor accounts and Workflow profiles, approve/return reviews, and record treatment-plan overrides. They cannot open App settings, API/EMR setup, LLM setup, forensic logs, or manage admin/manager accounts.
- Counselors can upload/update their own work, review returned work, view permitted details, export permitted work lists, and manage only their own account.
- Workflow profile create/version/publish/archive/delete attempts are audited. Published/archived workflow history must remain available for interpreting historical metrics.

## Windows desktop runtime
- The ordinary Windows path runs one local FastAPI desktop service at `http://localhost:8000`.
- The default database is SQLite under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.
- Uploads, logs, API reports, and `.env` also live under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.
- Use `scripts\Start-IZ-Clinical-Notes-Analyzer.cmd` for double-click launch. Ordinary launch prompts before installing missing dependencies or rebuilding frontend assets. Use `scripts\preflight-windows.ps1 -AssumeYes` only for unattended support validation.
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
