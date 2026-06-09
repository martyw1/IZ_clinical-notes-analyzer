# Windows User Guide Version 1

This guide is for R3 staff using a normal Windows 11 laptop or desktop.

Current patch version: `1.0.3` / build `2026.06.09.4`.

Version 1.0.3 keeps the Version 1 Windows startup reliability fixes, aligns app version metadata everywhere the app reads release information, documents the local admin recovery utility, and makes the updated Treatment Plan Timeliness evidence queue visibly identifiable in the UI.

## Install

1. Open the release folder `dist\windows-release\IZ-Clinical-Notes-Analyzer-v1.0.3`.
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

The Version 1.0.3 local recovery path is:

```powershell
.\scripts\update-local-admin.ps1
.\scripts\Start-IZ-Clinical-Notes-Analyzer.cmd
```

Run the utility from the repo root, save the generated value securely, restart the app, and sign in locally as `admin` using the generated value. Do not record real access values in Git, screenshots, email, support tickets, or chat.

## Main Screens

- Chart audit: summary, source selection, current queue, and checklist version.
- Review queue: detailed findings, evidence, reviewer notes, disposition, and CSV/JSON export.
- Treatment plans: updated evidence queue banner, timeliness status, source/staff/LOC due-date comparison, LOC-change blocker, rule results, overrides, and CSV/JSON export.
- Checklist: acronym definitions, review statuses, LOC-change blocker, and the 20 Version 1 steps.
- Manual upload: upload exported clinical note or treatment plan files.
- Settings: admin-only API, LLM, readiness, and workflow settings.
- Forensic logs: admin-only audit trail.

## API Mode

Version 1 includes a direct API readiness harness and mock source discovery. Live Alleva patient import is disabled until official credentials, endpoint mapping, scopes, pagination/rate limits, attachment handling, vendor documentation, and compliance approval exist.

## Upload Mode

Supported file types are shown in the upload screen. Use synthetic data for testing. Production use with PHI requires R3-approved controls and secure local handling.

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
