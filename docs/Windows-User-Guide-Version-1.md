# Windows User Guide Version 1

This guide is for R3 staff using a normal Windows 11 laptop or desktop.

Current patch version: `1.4.4` / build `2026.06.20.1`.

Version 1.4.4 keeps the Version 1 Windows startup reliability fixes, repairs legacy local audit-log startup errors, and removes active FHIR/SMART-on-FHIR configuration from Alleva workflows. Alleva integration is REST/OpenAPI/HL7-readiness only, with exact App settings validation messages, one active Alleva/API connection, optional saved endpoint presets, and gated Alleva REST treatment-plan sync controls.

## Install

1. Open the release folder `dist\windows-release\IZ-Clinical-Notes-Analyzer-v1.4.4`.
2. Double-click `Install-IZ-Clinical-Notes-Analyzer.cmd`.
3. Wait for the preflight window to finish.
4. Use the Start Menu shortcut named `IZ Clinical Notes Analyzer`.

The installer is per-user and installs under `%LOCALAPPDATA%\Programs\IZ Clinical Notes Analyzer`.

## First Launch

1. Launch from the Start Menu shortcut.
2. The app starts a local service and opens `http://localhost:8000`.
3. Sign in as `admin`.
4. Use the generated first local admin access value from the local app settings file under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.
5. Change or protect that access value according to R3 policy.

## Admin Access Reset

When a working admin account can sign in, use `User management` to reset another user account and require a new credential at next sign-in when available.

When no admin can sign in on a local Windows desktop install, follow `docs\admin-access-reset.md`.

The Version 1.4.4 local recovery path is:

```powershell
.\scripts\update-local-admin.ps1
.\scripts\Start-IZ-Clinical-Notes-Analyzer.cmd
```

Run the utility from the repo root, save the generated value securely, restart the app, and sign in locally as `admin` using the generated value. Do not record real access values in Git, screenshots, email, support tickets, or chat.

## Main Screens

- Chart audit: summary, source selection, current queue, and checklist version.
- Review queue: detailed findings, evidence, reviewer notes, disposition, and CSV/JSON export.
- Treatment plans: the default landing screen for admins and office managers, updated evidence queue banner, local date-clock status, source-document/date-clock/LOC-change due-date comparison, LOC-change blocker, rule results, overrides, source-mode cards, and CSV/JSON export with workflow-step statuses.
- Checklist: acronym definitions, review statuses, LOC-change blocker, and the 42 Version 1.2.0 PRD steps.
- Manual upload: upload exported clinical note or treatment plan files, inspect uploaded binder details, download stored documents when authorized, and delete an uploaded binder when it should be removed from the local app.
- Help: role permissions, screen/button guide, setup notes, API/EMR definitions, workflow guidance, and LLM setup notes.
- User management: admins can manage admins, managers, and counselors; office managers can manage counselor accounts only; counselors manage only their own account.
- Workflow profiles: admin/manager workflow logic screen, including `Seed draft from 42-step checklist`, draft creation, in-place draft editing, publish, archive, and unused-draft delete.
- App settings: admin-only organization, access intelligence, LLM, readiness, periodic API-check, one active Alleva/API connection, optional API endpoint presets, Alleva REST/OpenAPI settings, and LOC-change settings.
- Forensic logs: admin-only audit trail.

## API Mode

Version 1 includes a direct API readiness harness and mock source discovery. Live Alleva patient import is disabled until official credentials, endpoint mapping, scopes, pagination/rate limits, attachment handling, vendor documentation, and compliance approval exist.

Admins can open the API connectivity test harness from App settings or directly at `http://localhost:8000/api-configuration`. When opened from the app, the harness uses the current admin session and does not require a second in-page admin login. App settings is the source of truth for the one active Alleva/API connection; the harness loads and tests that same connection.

For Alleva OAuth setup, it is normal to paste the client ID and client secret supplied by R3/Alleva. The client secret is encrypted locally and is never shown again after save. The browser only shows whether a secret is configured. App settings can also enable periodic safe API readiness checks after the REST API base URL, OpenAPI URL, token URL, client ID, encrypted client secret, and token auth style are saved. These checks authenticate and verify readiness; they do not import live patient charts or treatment plans until the approval gate above is complete.

Alleva confirmed it does not currently support FHIR. Stored API endpoint profiles are optional presets. Activating a preset copies its values into the active App settings connection used by readiness/API tests, periodic checks, and approved REST treatment-plan sync.

When API monitoring is unavailable, manual upload is treated as an upload-time snapshot. Use the monthly compliance-check fallback for large chart sets instead of assuming weekly automatic monitoring.

## Upload Mode

Supported file types are shown in the upload screen. Use synthetic data for testing. Production use with PHI requires R3-approved controls and secure local handling.

To delete a binder that was uploaded and analyzed, open `Manual upload`, select the binder, type the patient ID exactly in the delete confirmation field, and click `Delete uploaded binder`. If you click before the confirmation matches, the app shows exact guidance instead of leaving the button unavailable. This removes the local uploaded binder, its linked automated review, linked upload-derived timeliness records, and encrypted stored files from the computer. Forensic audit logs remain.

## Troubleshooting

- Preflight report: `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\logs\preflight-windows-latest.json`
- Startup logs: `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\logs`
- Local settings: `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\.env`
- Admin access reset guide: `docs\admin-access-reset.md`
- App URL: `http://localhost:8000`
- Health check: `http://localhost:8000/api/health`
- Readiness check: `http://localhost:8000/api/readiness`
- Version check: `http://localhost:8000/api/version`

## Uninstall

Use the Start Menu uninstall shortcut or double-click `Uninstall-IZ-Clinical-Notes-Analyzer.cmd` from the release folder. Local data under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer` is preserved unless R3 intentionally removes it.
