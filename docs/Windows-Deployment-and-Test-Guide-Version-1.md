# Windows Deployment and Test Guide Version 1

Current beta version: `1.4.6-beta.1` / build `2026.06.25.1`.

## Target

Version 1 targets a normal Windows 10/11 Home or Pro laptop or desktop. Normal use should be double-click install/launch with no Docker, PostgreSQL, Git, Node.js, or command-line work.

Beta 1.4.6-beta.1 keeps the Version 1 startup reliability, stale-build safeguards, global and selected-client 42-step workflow coverage, selected-client manager notes/action export, redacted PDF handling, Patient-ID-only privacy hardening, treatment-plan date-clock behavior, workflow/checklist exports, admin-only clear-patient-data controls, redacted diagnostics, and API harness hardening while removing active FHIR/SMART-on-FHIR configuration, discovery, scopes, import-plan workflows, defaults, and validation requirements from Alleva workflows.

## Prerequisites for Source Build

- Python 3.11 or newer
- Node.js/npm for frontend builds
- PowerShell 5.1 or newer
- Git only for development

The release package includes built frontend assets. Ordinary source-checkout launch prompts before installing Python, backend packages, or rebuilding frontend assets. Support automation can still pass `-AssumeYes` to run unattended setup.

## Setup

```powershell
scripts\setup-windows.ps1 -AssumeYes
```

## Preflight

```powershell
scripts\preflight-windows.ps1 -AssumeYes
```

Preflight creates AppData folders, creates a local `.env` when missing, checks Python, repairs `backend\.venv`, validates the full Windows runtime dependency set, validates rules and the Treatment Plan Checklist, confirms frontend build assets, detects stale `frontend\dist` assets, checks the app port, and writes a JSON report.

Startup readiness fails closed when a production-like/local-client run is missing a bootstrap admin password or still uses a known placeholder/test value. The Windows preflight/install path generates local values; do not ship a release folder with `BOOTSTRAP_ADMIN_PASSWORD=change-me`.

## Local Launch

```powershell
scripts\start-windows-local.ps1 -AssumeYes
```

The double-click launcher uses:

```cmd
scripts\Start-IZ-Clinical-Notes-Analyzer.cmd
```

Expected Beta 1.4.6-beta.1 behavior: startup runs preflight once, prompts before dependency installation or frontend rebuilds unless `-AssumeYes` is supplied, detects missing or stale frontend build assets, repairs legacy local audit-log schemas that still contain retired required FHIR audit columns, then starts `app.desktop_main:app` through `backend\.venv\Scripts\python.exe` without calling the legacy dependency-check path that could falsely report failure after a successful package install.

## Admin Access Reset

When at least one admin can sign in, use the app's `User management` screen to reset another user account.

When no admin can sign in on a local Windows desktop install, follow:

```text
docs\admin-access-reset.md
```

Do not record credential values in Git, screenshots, email, support tickets, or chat.

## Tests

Backend:

```powershell
$env:PYTHONPATH='backend'
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
```

Frontend:

```powershell
cd frontend
npm test -- --run
npm run build
```

Windows preflight:

```powershell
scripts\preflight-windows.ps1 -AssumeYes
```

Version checks after local launch:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/readiness
Invoke-RestMethod http://127.0.0.1:8000/api/version
```

Release package:

```powershell
scripts\build-windows-installer.ps1
```

Diagnostics bundle:

```powershell
scripts\collect-diagnostics.ps1
```

## Release Artifacts

The release builder writes:

- `dist\windows-release\IZ-Clinical-Notes-Analyzer-v1.4.6-beta.1`
- `dist\windows-release\IZ-Clinical-Notes-Analyzer-v1.4.6-beta.1.zip`

The release folder contains:

- `Install-IZ-Clinical-Notes-Analyzer.cmd`
- `Launch-IZ-Clinical-Notes-Analyzer.cmd`
- `Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd`
- `Uninstall-IZ-Clinical-Notes-Analyzer.cmd`
- `release-manifest.json`
- `app\` source/runtime files with built frontend assets

The installer creates Start Menu and desktop shortcuts for Launch, Diagnostics, and Uninstall. The Diagnostics shortcut creates a redacted zip under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\diagnostics` and excludes uploads, local databases, generated reports, and raw `.env` values.

Note: the Beta 1.4.6-beta.1 source metadata, scripts, and frontend assets should be rebuilt into a fresh release folder before handing the package to non-technical testers.

## Security Checks

Before commit or push:

```powershell
git status --short --branch
git diff --check
rg -n "sk-[A-Za-z0-9]|api[_-]?key|bearer |password|secret|token|BEGIN PRIVATE KEY|AKIA|AIza" -g "!frontend/package-lock.json" -g "!docs/version-1-final-validation-report.md"
```

Review every result. Synthetic placeholder words in code and docs are allowed only when they are not real credentials.

## Known Version 1 Limits

- Live Alleva patient import is disabled.
- The LOC-change treatment-plan update window ships with a manager-editable 7-calendar-day preset, remains unvalidated, and must stay configurable.
- Manual upload is an upload-time snapshot; monthly compliance checks are the documented fallback when API refresh is unavailable.
- Admins and office managers can edit future checklist workflow versions through Workflow profiles, but published workflow history is preserved.
- App settings, API/EMR setup, LLM setup, and forensic logs are admin-only.
- OCR quality depends on source document readability.
- LLM assistance is optional and disabled by default.
- The package is not yet a signed MSI/MSIX; a signed installer remains the recommended long-term endpoint for non-technical deployment.
