# Windows User Guide Version 1

This guide is for R3 staff using a normal Windows 11 laptop or desktop.

## Install

1. Open the release folder `dist\windows-release\IZ-Clinical-Notes-Analyzer-v1.0.0`.
2. Double-click `Install-IZ-Clinical-Notes-Analyzer.cmd`.
3. Wait for the preflight window to finish.
4. Use the Start Menu shortcut named `IZ Clinical Notes Analyzer`.

The installer is per-user and installs under `%LOCALAPPDATA%\Programs\IZ Clinical Notes Analyzer`.

## First Launch

1. Launch from the Start Menu shortcut.
2. The app starts a local service and opens `http://localhost:8000`.
3. Sign in as `admin`.
4. Use the generated first password from the local `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\.env` file.
5. Change or protect that password according to R3 policy.

## Main Screens

- Chart audit: summary, source selection, current queue, and checklist version.
- Review queue: detailed findings, evidence, reviewer notes, disposition, and CSV/JSON export.
- Treatment plans: timeliness status, LOC-change blocker, rule results, overrides, and CSV/JSON export.
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
- App URL: `http://localhost:8000`
- Health check: `http://localhost:8000/api/health`
- Readiness check: `http://localhost:8000/api/readiness`

## Uninstall

Use the Start Menu uninstall shortcut or double-click `Uninstall-IZ-Clinical-Notes-Analyzer.cmd` from the release folder. Local data under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer` is preserved unless R3 intentionally removes it.
