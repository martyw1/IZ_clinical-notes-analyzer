# Windows Installer Build and Install Guide

This guide covers the Windows release workflow for IZ Clinical Notes Analyzer.
The build and install scripts are designed for Windows 10/11 users without
administrator rights.

## V2 beta.2 release-validation boundary

The active prerelease metadata is `2.0.0-beta.2` / build `2026.07.11.1` / channel `beta-local-desktop-v2`. Before package sign-off, run the validation procedure in `docs/v2-beta/release-readiness-2026-07-11.md` from a clean isolated local-app-data directory with synthetic data only. Never package or validate against a production SQLite database, clinical export, saved API artifact, credential profile, upload, or log. Code-signing and retention/legal-hold controls remain R3 owner decisions; this prerelease is not a production-release claim.

## Builder or Developer

### Normal build

From the repository root, double-click:

```text
Build-IZ-Windows-Installer.cmd
```

The command runs `scripts\build-windows-installer.ps1` with:

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass
```

The normal build:

- creates `backend\.venv` if needed
- installs backend runtime packages
- installs backend build/test packages from `backend\requirements-build.txt`
- verifies `pytest` is available
- runs backend tests
- installs frontend dependencies with `npm ci` when `package-lock.json` exists
- runs frontend tests
- builds `frontend\dist`
- verifies `frontend\dist\index.html` and built JS/CSS assets exist
- creates the release folder and zip under `dist\windows-release`
- validates required release files
- validates that `app\docs\patient-treatment-plan-handling.md` and `app\docs\beta-client-test-run-guide.md` are included in the release folder
- scans the release folder and zip for forbidden local files

On success, the window prints:

```text
Release folder: <repo>\dist\windows-release\IZ-Clinical-Notes-Analyzer-v<version>
Release zip: <repo>\dist\windows-release\IZ-Clinical-Notes-Analyzer-v<version>.zip
```

The same paths are written to:

```text
dist\windows-release\latest-release-paths.txt
```

### If Python is missing

Install Python 3.12 for Windows from:

```text
https://www.python.org/downloads/windows/
```

Check `Add python.exe to PATH` during install, then double-click
`Build-IZ-Windows-Installer.cmd` again.

### If Node.js or npm is missing

Install Node.js LTS for Windows from:

```text
https://nodejs.org/
```

Advanced users may install it with:

```text
winget install OpenJS.NodeJS.LTS --scope user
```

Then double-click `Build-IZ-Windows-Installer.cmd` again.

### Advanced build options

Optional arguments are passed through to the PowerShell build script:

```text
Build-IZ-Windows-Installer.cmd -SkipTests
Build-IZ-Windows-Installer.cmd -SkipFrontendBuild
```

`-SkipTests` is for advanced troubleshooting only. The normal release build
must run tests.

`-SkipFrontendBuild` still requires a valid existing `frontend\dist` with
`index.html` and built assets. The build fails if the browser app is missing or
incomplete.

### Logs

Preflight and startup logs are written under:

```text
%LOCALAPPDATA%\IZ Clinical Notes Analyzer\logs
```

### Rerun after a failure

Read the message in the build window, fix the named missing dependency, failed
test, or unsafe file, then double-click `Build-IZ-Windows-Installer.cmd` again.

## End User

Use `docs\guides\Version 2.0 Beta  2.0.0-beta.2  beta-local-desktop-v2\Marleigh-Setup-Install-and-User-Guide.html` as the primary illustrated, non-technical clinical-manager guide for installation, first sign-in, Alleva readiness, daily treatment-plan review, backup, and troubleshooting.

### Install

1. Unzip the release zip.
2. Open the unzipped release folder.
3. Double-click:

```text
Install-IZ-Clinical-Notes-Analyzer.cmd
```

The installer copies app files to:

```text
%LOCALAPPDATA%\Programs\IZ Clinical Notes Analyzer
```

Local app data is stored separately under:

```text
%LOCALAPPDATA%\IZ Clinical Notes Analyzer
```

Normal installs preserve existing `.env`, local database, uploads, exports,
reports, and logs.

The release includes `app\docs\patient-treatment-plan-handling.md`, the current reference for how patient treatment-plan data moves from manual upload or approved Alleva sync into local storage, deterministic timeliness status, aggregate diagnostics, and the Treatment Plans screen.

The release also includes `app\docs\beta-client-test-run-guide.md`, the non-technical first beta client test-run guide for install checks, day-of-test workflow, lookup status behavior, treatment-plan review expectations, diagnostics, backup, and maintenance.

### Launch

Launch the app from the Start Menu, Desktop shortcut, or:

```text
Launch-IZ-Clinical-Notes-Analyzer.cmd
```

The launcher starts the backend, serves the built browser app, opens the local
URL, and writes startup logs to the local AppData logs folder.

### Diagnostics

If support asks for diagnostics, run:

```text
Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd
```

Diagnostics redact secrets and exclude uploaded clinical documents, raw `.env`
values, SQLite databases, and uploads.

### Backup

Before uninstalling or making major changes, run:

```text
Backup-IZ-Clinical-Notes-Analyzer.cmd
```

The backup may contain regulated clinical data and local access material. Store
it securely according to R3 policy.

### Uninstall

Normal uninstall removes app files and shortcuts, but preserves local data:

```text
Uninstall-IZ-Clinical-Notes-Analyzer.cmd
```

Complete uninstall removes app files, shortcuts, and all local IZ Clinical
Notes Analyzer data for the current Windows user:

```text
Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd
```

Use complete uninstall carefully. It requires an explicit confirmation phrase.

### Do not edit `.env`

Do not manually edit `.env` unless R3 support asks you to. It contains local
configuration and encryption material needed for the app to read its local data.
