# Operations runbook

Current source: **1.0.2**, build **2026.10.16.1**, revision **1**, `stable-local-desktop`; reviewed October 17, 2026. [Operator help](operator-help-current.md) and [HTML guide](guides/current/Marleigh-Setup-Install-and-User-Guide.html) are client instructions. [Current validation](validation/current-work-2026-10-16.md) is separate from historical package receipts.

## Safe support sequence

1. Obtain non-PHI symptom, approximate time, screen and running footer version. Establish installed package versus source checkout.
2. Inspect health/version/readiness. Do not change secrets, policy, live API enablement or client data to hide a warning.
3. Clear filters, check source/exact saved version, inspect job progress and reproduce using an isolated synthetic profile when necessary.
4. Collect redacted diagnostics only when needed. Review before sending through approved R3 support. Never send raw logs, `.env`, uploads, database or patient screenshots.
5. Preserve data/recovery material before authorized repair. Stop the owned app cleanly; never kill unrelated processes or delete a lock/database file blindly.

## Health and identity

At `http://127.0.0.1:8000`, `/health` and `/api/health` check health; `/api/version` reports identity; `/api/readiness` gives readiness; authenticated administrator `/api/system/readiness` supplies details. Readiness is not HIPAA certification. Authentication/role errors are expected on protected routes.

If another app owns port 8000, identify it before stopping anything. For old assets, refresh and compare footer/API with the package receipt. Source support can rebuild frontend and restart; clients should receive a rebuilt prepared package instead of installing build tools.

## Detailed logging and privacy

The active V2 audit store records structured actor, action, target, outcome, UTC time and redacted details in SQLite with a SHA-256 linked hash chain. Administrator Forensic Logs and the audit verification API support review. Authentication/recovery, settings, patient/plan detail, review/export, upload/import and job actions have their own events. Do not claim every HTTP request or roster read is a separate clinical access event.

The common audit wrapper supports local JSONL fallback on database logging failure. Startup/preflight logs and job artifacts are separate evidence. Preserve timestamps, event IDs and request/correlation identifiers where present. A valid chain shows consistency of covered records; it is not independent proof against an administrator controlling the host/database. Legacy records may have narrower verification scope.

Privacy mode is `redacted_minimum_necessary`; retention remains `local_policy_required`. Redaction blocks selected secret/content keys and patterns, not all possible PHI. Callers must supply safe metadata. Never add note text, raw responses, names, original filenames, passwords, recovery codes or encryption material for verbosity. Identifiers/dates remain sensitive. Follow R3 retention/legal hold; do not truncate audit history ad hoc.

## Troubleshooting

| Symptom | Client first step | Support checks |
| --- | --- | --- |
| Page will not open | Start once, wait, try localhost:8000 | Owned listener, preflight/startup log, shortcut target and maintenance state |
| Missing tab/access denied | Confirm assigned account | Role/facility scope; 401 authentication, 403 permission |
| Password changed, workspace blocked | Save and acknowledge recovery code | Forced-password/recovery state; do not edit `.env` |
| Forgotten password | Forgot password and saved one-time code | Authorized Users reset; compatible recovery procedure only |
| Empty/stale roster | Clear filters and Source; inspect last job | Patient and plan pulls differ; inspect failures/pagination |
| Wrong plan/evidence | Check source, MRN, plan ID/version | Exact source/facility identity; ambiguity remains unresolved |
| Unexpected due date | Compare signatures and checklist | Timezone/Windows clock, rule version, unvalidated LOC candidate |
| Upload warning | Read warning and saved result | Format/extraction bounds; opaque storage is not parsed success |
| API authorization failure | Record safe phase; contact R3 | Tenant permission, audience/scope, endpoint/version and mapping |
| Slow import | Wait; avoid duplicate jobs | File sizes/counts, parser allocation, job load, memory and OneDrive |
| Recovery required | Stop; contact R3 | Documented Recover workflow; no manual directory replacement |

## Accounts and clinical workflow

Use [password management](password-management-beta4.md) and [admin recovery](admin-access-reset.md). Password change/recovery invalidate prior sessions through password epoch. Sign out and lock Windows unattended; have IT configure automatic locking. Browser sign-out is not host access control.

Office managers review authorized exact saved plans. Administrator controls include connection settings, Users and Forensic Logs. Follow actual role behavior rather than historical screenshots. Optional LLM stays disabled and is unnecessary for deterministic decisions.

The 42-step checklist and versioned rules govern Day-1 initial signatures, 30-calendar-day master signatures, PHP 30-day and IOP/OP 60-day recurring reviews. Settings shows intervals read-only. The LOC seven-day candidate cannot establish compliance; [R3 policy remains open](open-blockers.md). Missing Data, Needs Review, Conflicting Evidence and Unable to Evaluate remain valid results.

## Integration boundary

Live Alleva import remains off by default and requires approved tenant credentials, read-only authorization, endpoint/mapping and pagination/rate-limit validation and compliance approval. Startup import stays disabled. Connection tests/dry runs and bounded harness previews are readiness evidence only. Do not place raw vendor data or tokens in diagnostics. See [API configuration](api-configuration-and-connectivity.md) and [patient data handling](patient-treatment-plan-handling.md).

## Backup and restore

Current scripts create an encrypted `.izcnabackup` containing local data, configuration and encryption material, with semantic verification before publication. Protection uses AES-256-CBC plus HMAC and Windows CurrentUser DPAPI-wrapped random key material. It is intended for the same Windows account/computer. Do not promise replacement-device restoration until R3 tests a separate recovery method.

Stop the app, run the supplied Backup command and retain the complete verified archive in an approved location. Default destination is current user's Documents/IZ Clinical Notes Analyzer Backups; Documents may be redirected, so verify actual location and OneDrive policy. Use the supplied Restore command (source support: `scripts/restore-local-data.ps1 -BackupPath <approved archive>`), follow confirmations and verify the restored runtime. Never unzip or replace only the database. Keep `.env`, SQLite and encrypted sources together. Rehearse only in an isolated synthetic profile.

Normal uninstall preserves data. Complete purge requires `REMOVE IZ DATA` and authorized destruction; it is not repair or upgrade. See [CMD maintenance](windows-cmd-maintenance.md).

## Performance operating envelope

Expected steady state is local service/browser plus OneDrive and normal Windows services. ChatGPT is excluded. Small synthetic October 12 measurements are smoke evidence, not capacity qualification. Full rosters are materialized/rendered; large extraction and concurrent jobs can pressure an 8 GB laptop. Keep one large operation active, avoid unnecessary tabs and schedule major synchronization outside review time. Measure realistic synthetic dataset sizes before promising throughput.

## Developer verification

Use the existing environment; avoid reinstalling dependencies on a client profile for diagnosis. Backend: set `PYTHONPATH=backend`, then `backend/.venv/Scripts/python.exe -m pytest backend/tests -q`. Frontend: from `frontend`, `npm run test -- --run`, `npm run build`; direct TypeScript `npx tsc --noEmit`. Windows build: `scripts/Build-IZ-Windows-Installer.cmd` with all required gates, prepared-folder validation and ZIP forbidden-file checks. Fixtures must be synthetic. A source test does not qualify a ZIP; bind checks to the exact archive. Results belong in the [October 12 ledger](validation/current-work-2026-10-12.md).

## Configured source laptop: portable OneDrive ZIP workflow (October 12, 2026)

At the owner's explicit request, `scripts/backup-onedrive-zip.ps1` and `scripts/restore-onedrive-zip.ps1` provide a separate unencrypted portable profile ZIP workflow. Do not feed these ZIPs to the encrypted `.izcnabackup` restore tool. Full create/check/restore/rollback and replacement-device instructions are in the current HTML guide, Backup section, and the app Help page. The archive includes `.env` and encryption material; possession gives access to sensitive records and settings. Keep it private in R3 OneDrive. No physical replacement-device or cloud-upload validation is implied by local verification. Backup directories, diagnostics and transient SQLite journals are excluded. App code/runtime must be prepared separately.
