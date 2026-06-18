# Operations Runbook

Date: 2026-06-18

Applies to: IZ Clinical Notes Analyzer Version `1.4.1` / build `2026.06.18.1` local Windows desktop runtime.

## Health endpoints

- Backend direct: `GET /health`
- Backend API alias: `GET /api/health`
- Runtime readiness: `GET /api/readiness`
- Admin readiness details: `GET /api/system/readiness`
- Version metadata: `GET /api/version`

## Forensic log handling

- Primary forensic logs are stored in the `audit_logs` table.
- Each record includes request metadata, actor identity, source IP, event category, CEF payload, FHIR AuditEvent JSON, and a tamper-evident hash chain.
- If database persistence fails during logging, the app writes JSONL fallback records under the local app-data log directory.
- Admin access to forensic logs is available through `GET /api/audit/logs` and the `Forensic logs` screen.
- Preserve UTC timestamps during exports, use the app-provided local timestamp for operator review, and correlate events using `request_id` and `correlation_id`.
- Audit snapshots must not expose uploaded note text, original filenames, storage paths, API keys, bearer tokens, passwords, encryption keys, or PHI-like clinical content.

## Patient note set handling

- Patient note uploads are keyed by `patient_id` and stored under the encrypted local upload directory.
- Initial uploads use `POST /api/patient-note-sets` with `upload_mode=initial`; later changes use `upload_mode=update`, which creates a new immutable version instead of replacing the prior set.
- Current and historical binders can be listed with `GET /api/patient-note-sets` and inspected with `GET /api/patient-note-sets/{id}`.
- Stored source files can be retrieved with `GET /api/patient-note-sets/{note_set_id}/documents/{document_id}/download` after authentication and authorization checks.
- Uploaded binders can be deleted with `DELETE /api/patient-note-sets/{id}` by an authorized user. Deletion removes the selected note set, linked generated review charts, upload-derived timeliness records, and encrypted stored files. If the deleted binder was the current active version and an older version remains, the latest remaining version is reactivated and resynced into the timeliness tracker.
- Every stored file has a SHA-256 digest in the database; use that hash when validating backup integrity or investigating file tampering.
- Forensic audit logs are retained after binder deletion.

## Treatment Plan Timeliness operations

- Admins and office managers normally land on the Treatment Plans work queue when no explicit view is requested.
- The queue uses deterministic rules and current Version 1.4.1 status colors for overdue, urgent, due soon, returned, needs review, missing data, conflicting evidence, unable-to-evaluate, approved, and compliant records.
- The selected-client detail view compares source-document `Next Review Due`, staff-signature cadence due date, and LOC-effective cadence due date.
- Manual overrides are restricted to admins and office managers and must be audited with a reason.
- Missing names use safe generated placeholders: `no-name-found_YYYY-MM-DD_HHMMSS` or `no-value-found_YYYY-MM-DD_HHMMSS`.
- The LOC-change treatment-plan update window is still unvalidated and must stay configurable and visibly marked as unresolved.

## API readiness checks

- The admin API harness is available at `/api-configuration` in the Windows desktop runtime.
- When opened from App settings, the harness uses the current admin session; it should not prompt for a second admin login inside the harness.
- The harness supports API-key auth, no-auth probes, and OAuth client credentials using body credentials, Basic auth, URL-encoded Basic auth, or try-both/try-all fallback modes.
- Operation-test responses are capped before returning to the UI. Large responses are marked as truncated and summarized instead of rendering the full payload.
- Periodic API readiness checks can be enabled in App settings after saving API/FHIR base URL, token URL, client ID, encrypted client secret, token auth style, and interval.
- FHIR base URL means the root FHIR R4 endpoint supplied by Alleva or a future EMR vendor. Alleva Swagger/OpenAPI URLs belong in the OpenAPI/API harness fields, and `https://api.allevasoft.com/advanced-form-elements` is a protected REST operation path, not a FHIR base URL.
- Stored EMR endpoint profiles are admin-only and can be activated for the current readiness/API test configuration without returning stored secrets to the browser.
- Periodic checks authenticate and pull/summarize API definitions only. They do not import live Alleva patient data until the live-import compliance gate is cleared.

## Alleva REST treatment-plan sync

- `Test-AllevaApi.ps1` works without a FHIR root because it uses Alleva REST API base URL, token URL, and Swagger/OpenAPI definitions.
- App startup sync uses the same REST concept, not FHIR discovery. It is disabled by default.
- To arm startup sync, App settings must have Alleva REST API base URL, token URL, client ID, encrypted client secret, explicit R3/Alleva live-sync approval, and validated endpoint mapping.
- Endpoint mapping must confirm active-client filtering, treatment-plan records, treatment-review records, staff/creator signature dates, client signature dates, current LOC, admission date, next review due, pagination, and status fields.
- When sync runs, Alleva is only the source system. The app normalizes the REST payloads into local timeliness records and runs R3's deterministic compliance logic.
- If required approval or mapping is missing, the sync records a blocked status and imports no live patient treatment-plan data.

## Standalone API diagnostics

- `scripts\test-alleva-api-connectivity.ps1` is the simple redacted reachability/report script.
- Root `Test-AllevaApi.ps1` is a full diagnostic script and is sensitive by default. It can print and save tokens, secrets, Authorization headers, request bodies, and response bodies unless `-RedactSensitive` is used.
- `.alleva.local.ps1` and `alleva-api-test-logs/` are gitignored but should still be treated as sensitive local diagnostic artifacts.
- Do not use real PHI in API test payloads.

## Treatment-plan date clock

- The timeliness evaluator uses the laptop/facility-local current date on startup and during runtime.
- The recurring update clock starts from the latest valid treatment-plan review/update date, or from admission date when no later valid review/update exists.
- PHP levels use 30 calendar days; other configured treatment levels use 60 calendar days.
- LOC changes use a separate manager-editable 7-calendar-day preset. The setting remains unvalidated until R3/Marleigh confirms the final rule.
- Every timeliness analysis result is audited with patient ID, status, due date, rule used, current date, and active workflow key/version/checklist context.
- Exports include both the legacy checklist/domain rows and active workflow-step statuses.

## Roles and workflow controls

- Admins can use every screen and action, including all user roles, App settings, API/EMR, LLM, workflow profiles, logs, uploads, reviews, overrides, and exports.
- Office managers can manage counselor accounts and Workflow profiles, approve/return reviews, and record treatment-plan overrides. They cannot open App settings, API/EMR setup, LLM setup, forensic logs, or manage admin/manager accounts.
- Counselors can upload/update their own work, review returned work, view permitted details, export permitted work lists, and manage only their own account.
- Workflow profile create/version/edit-draft/publish/archive/delete attempts are audited. Published/archived workflow history must remain available for interpreting historical metrics.

## Windows desktop runtime

- The ordinary Windows path runs one local FastAPI desktop service at `http://localhost:8000`.
- The default database is SQLite under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.
- Uploads, logs, API reports, and `.env` also live under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.
- Use `scripts\Start-IZ-Clinical-Notes-Analyzer.cmd` for double-click launch.
- Ordinary launch prompts before installing missing dependencies or rebuilding frontend assets.
- Use `scripts\preflight-windows.ps1 -AssumeYes` only for unattended support validation.
- Do not move runtime data into the OneDrive-backed source repository.

## Recovery

- If the Windows app will not start, inspect `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\logs\preflight-windows-latest.json` and the startup logs in the same AppData tree.
- If no local admin can sign in, follow `docs\admin-access-reset.md`.
- If the browser shows an old UI, rebuild `frontend\dist` or use a freshly built release folder.
- If API readiness fails, use `docs\api-configuration-and-connectivity.md` and keep live patient import disabled until credentials and endpoint mapping are approved.

## Backup and restore

For ordinary Windows desktop installs:

1. Stop the app.
2. Back up the entire `%LOCALAPPDATA%\IZ Clinical Notes Analyzer` directory according to R3 policy.
3. Keep the backup encrypted and access-controlled because it can contain local SQLite data, encrypted uploads, audit logs, and configuration.
4. Restore by stopping the local app, replacing the AppData directory from the approved backup, and restarting the app.

The `.env` file, SQLite database, and encrypted uploads must stay together. If the `.env` file is lost, encrypted uploads and saved API secrets may not be recoverable.

## Legacy Docker/PostgreSQL artifacts

Docker/PostgreSQL is not the current supported R3 Windows desktop path. The root full-stack `docker-compose.yml` is not active in this branch. The old Docker/nginx archive folder and database-expose compose overlay were removed on 2026-06-17 after cleanup evidence; deprecated startup scripts remain as legacy references.

Do not present Docker, PostgreSQL, nginx, Git, Node.js, or command-line work as ordinary Windows desktop-user requirements. Do not restore the old Docker stack to active paths unless R3 explicitly reintroduces Docker/server deployment and updates README, Windows docs, CI, tests, and release instructions together.
