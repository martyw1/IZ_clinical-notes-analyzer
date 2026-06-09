# Windows Deployment and Test Guide Version 1

## Target

Version 1 targets a normal Windows 10/11 Home or Pro laptop or desktop. Normal use should be double-click install/launch with no Docker, PostgreSQL, Git, Node.js, or command-line work.

## Prerequisites for Source Build

- Python 3.11 or newer
- Node.js/npm for frontend builds
- PowerShell 5.1 or newer
- Git only for development

The release package includes built frontend assets. A source checkout can install Python and Node through `winget` when `scripts\preflight-windows.ps1 -AssumeYes` is used.

## Setup

```powershell
scripts\setup-windows.ps1 -AssumeYes
```

## Preflight

```powershell
scripts\preflight-windows.ps1 -AssumeYes
```

Preflight creates AppData folders, creates a local `.env` when missing, checks Python, repairs `backend\.venv`, validates backend dependencies, validates rules and the Treatment Plan Checklist, confirms frontend build assets, checks the app port, and writes a JSON report.

## Local Launch

```powershell
scripts\start-windows-local.ps1 -AssumeYes
```

The double-click launcher uses:

```cmd
scripts\Start-IZ-Clinical-Notes-Analyzer.cmd
```

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

Release package:

```powershell
scripts\build-windows-installer.ps1
```

## Release Artifacts

The release builder writes:

- `dist\windows-release\IZ-Clinical-Notes-Analyzer-v1.0.0`
- `dist\windows-release\IZ-Clinical-Notes-Analyzer-v1.0.0.zip`

The release folder contains:

- `Install-IZ-Clinical-Notes-Analyzer.cmd`
- `Launch-IZ-Clinical-Notes-Analyzer.cmd`
- `Uninstall-IZ-Clinical-Notes-Analyzer.cmd`
- `release-manifest.json`
- `app\` source/runtime files with built frontend assets

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
- The LOC-change treatment-plan update window is unvalidated and must stay configurable.
- OCR quality depends on source document readability.
- LLM assistance is optional and disabled by default.
