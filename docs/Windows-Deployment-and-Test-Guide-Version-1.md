# Windows Deployment and Test Guide Version 1

Current beta version: `1.4.6-beta.1` / build `2026.06.30.1`.

## Target

Version 1 targets a normal Windows 10/11 Home or Pro laptop. The prepared release folder should let a non-technical R3 user install, launch, back up, collect diagnostics, uninstall, and completely remove local data without administrator access and without Docker, PostgreSQL, Git, Node.js, or command-line work.

The source-checkout path remains for development and support. It can prompt before installing Python packages or rebuilding `frontend\dist`; it is not the preferred non-technical install path.

## Release Package

Build from a prepared source checkout:

```powershell
scripts\build-windows-installer.ps1
```

The builder writes:

- `dist\windows-release\IZ-Clinical-Notes-Analyzer-v1.4.6-beta.1`
- `dist\windows-release\IZ-Clinical-Notes-Analyzer-v1.4.6-beta.1.zip`

The release folder contains these double-click commands:

- `Install-IZ-Clinical-Notes-Analyzer.cmd`
- `Launch-IZ-Clinical-Notes-Analyzer.cmd`
- `Stop-IZ-Clinical-Notes-Analyzer.cmd`
- `Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd`
- `Backup-IZ-Clinical-Notes-Analyzer.cmd`
- `Uninstall-IZ-Clinical-Notes-Analyzer.cmd`
- `Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd`
- `release-manifest.json`
- `app\` source/runtime files with built frontend assets
- `app\docs\patient-treatment-plan-handling.md` current treatment-plan handling and code-location reference

## Installed Shortcuts

The per-user installer copies app files to:

```text
%LOCALAPPDATA%\Programs\IZ Clinical Notes Analyzer
```

It creates Start Menu shortcuts for:

- `IZ Clinical Notes Analyzer`
- `Stop IZ Clinical Notes Analyzer`
- `IZ Clinical Notes Analyzer Diagnostics`
- `Backup IZ Clinical Notes Analyzer`
- `Uninstall IZ Clinical Notes Analyzer`
- `Complete Uninstall IZ Clinical Notes Analyzer`

It creates desktop shortcuts for:

- `IZ Clinical Notes Analyzer`
- `IZ Clinical Notes Analyzer Diagnostics`
- `IZ Clinical Notes Analyzer Backup`

The normal uninstall shortcut removes app files and shortcuts while preserving local runtime data. The complete uninstall shortcut requires typing `REMOVE IZ DATA` and removes app files, shortcuts, and `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.

## Local Data

Local runtime data is outside the app folder:

```text
%LOCALAPPDATA%\IZ Clinical Notes Analyzer
```

Important contents:

- `.env`: local configuration, generated bootstrap admin value, and encryption material.
- `clinical-notes-analyzer.sqlite3`: local SQLite database.
- `uploads`: encrypted uploaded source documents.
- `logs`: startup logs and fallback audit logs.
- `api-reports` and `api-connectivity-reports`: redacted readiness reports.
- `diagnostics`: redacted support bundles.

The `.env` file, SQLite database, and encrypted uploads must be backed up and restored together.

## Backup Behavior

`scripts\backup-local-data.ps1` and `Backup-IZ-Clinical-Notes-Analyzer.cmd` create a zip under:

```text
%USERPROFILE%\Documents\IZ Clinical Notes Analyzer Backups
```

The backup helper:

- Prompts for `BACKUP` unless `-AssumeYes` is passed.
- Stops app-specific local processes first unless `-NoStop` is passed.
- Copies the whole `%LOCALAPPDATA%\IZ Clinical Notes Analyzer` folder.
- Adds `README-BACKUP.txt` explaining sensitivity and restore coupling.
- Does not redact the backup because it is intended for full restore. Store it encrypted and access-controlled.

## Uninstall Behavior

Data-preserving uninstall:

```powershell
Uninstall-IZ-Clinical-Notes-Analyzer.cmd
```

Removes:

- `%LOCALAPPDATA%\Programs\IZ Clinical Notes Analyzer`
- Start Menu shortcuts
- Desktop shortcuts created by the installer

Preserves:

- `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`

Complete uninstall:

```powershell
Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd
```

Requires exact confirmation:

```text
REMOVE IZ DATA
```

Removes app files, installer-created shortcuts, and `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.

## Source Checkout Support Path

Use this path only for development, validation, or support:

```powershell
scripts\setup-windows.ps1 -AssumeYes
scripts\preflight-windows.ps1 -AssumeYes
scripts\start-windows-local.ps1 -AssumeYes
```

The double-click source launcher is:

```cmd
scripts\Start-IZ-Clinical-Notes-Analyzer.cmd
```

The cleanup launcher is:

```cmd
scripts\Stop-IZ-Clinical-Notes-Analyzer.cmd
```

Preflight creates local AppData folders, creates `.env` when missing, checks Python, repairs `backend\.venv`, validates backend dependencies, validates rules/checklists, detects stale or missing `frontend\dist`, checks the app port, and writes:

```text
%LOCALAPPDATA%\IZ Clinical Notes Analyzer\logs\preflight-windows-latest.json
```

## Validation Commands

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

Windows smoke:

```powershell
scripts\preflight-windows.ps1 -AssumeYes
scripts\test-local-app-stack.ps1
scripts\test-api-configuration-local.ps1
```

Version checks after local launch:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/readiness
Invoke-RestMethod http://127.0.0.1:8000/api/version
```

Diagnostics bundle:

```powershell
scripts\collect-diagnostics.ps1
```

Script syntax checks:

```powershell
$scripts = @(
  'scripts\backup-local-data.ps1',
  'scripts\complete-uninstall-local-data.ps1',
  'scripts\build-windows-installer.ps1'
)
foreach ($script in $scripts) {
  $null = [scriptblock]::Create((Get-Content -LiteralPath $script -Raw))
}
```

Complete uninstall should be manually tested only on disposable synthetic data.

## Target-Laptop Acceptance

Before giving the release to a non-technical tester, verify on the target Windows laptop with synthetic data:

1. Install from the release folder using a normal non-admin Windows account.
2. Launch from Start Menu and desktop shortcut.
3. Confirm `/api/version` returns `1.4.6-beta.1` / `2026.06.30.1`.
4. Confirm the UI footer shows `Beta v1.4.6-beta.1`.
5. Create a synthetic upload/review/treatment-plan workflow.
6. Confirm `app\docs\patient-treatment-plan-handling.md` is present in the release app files and matches the active treatment-plan workflow.
7. Run Diagnostics and confirm a zip appears under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\diagnostics`.
8. Run Backup and confirm a zip appears under Documents.
9. Run data-preserving uninstall and confirm local data remains.
10. Reinstall and confirm the prior local data is still present.
11. Run complete uninstall on disposable data and confirm both app files and local data are removed.

## Security Checks

Before commit or release packaging:

```powershell
git status --short --branch
git diff --check
rg -n "sk-[A-Za-z0-9]|api[_-]?key|bearer |password|secret|token|BEGIN PRIVATE KEY|AKIA|AIza" -g "!frontend/package-lock.json" -g "!docs/version-1-final-validation-report.md"
```

Review every result. Synthetic placeholder words in code and docs are allowed only when they are not real credentials.

## Known Version 1 Limits

- Live Alleva patient import is disabled until approved by R3/Alleva with endpoint mapping and compliance signoff.
- The LOC-change treatment-plan update window ships with a manager-editable 7-calendar-day preset, remains unvalidated, and must stay configurable.
- Manual upload is an upload-time snapshot; monthly compliance checks are the documented fallback when API refresh is unavailable.
- App settings, API/EMR setup, optional LLM setup, and forensic logs are admin-only.
- OCR quality depends on source document readability.
- Optional LLM assistance is disabled by default.
- The package is not yet a signed MSI/MSIX with repair/modify support.
