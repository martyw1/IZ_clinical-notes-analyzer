# Windows Installer Build and Install Guide

This guide covers the Windows release workflow for IZ Clinical Notes Analyzer.
The build and install scripts are designed for Windows 10/11 users without
administrator rights.

## Production 1.0

The current candidate is `1.0.0` / build `2026.09.21.2` / installer revision `1`. Its prepared ZIP, full build and core component-profile lifecycle passed; client-site and full platform qualification remain open. Read the [installer portability validation criteria](validation/installer-portability-2026-09-21.md) before deployment. The September 15 package and [its validation report](validation/windows-cmd-maintenance-2026-09-15.md) remain immutable historical evidence.

The maintenance contract is in [Windows CMD maintenance](windows-cmd-maintenance.md). It recognizes beta.3 and earlier beta.4 builds for smart upgrade in place, preserves current-user data and existing account passwords on successful upgrade and normal uninstall, and keeps complete purge as a separate exact-phrase action. Package-root `Launch-IZ-Clinical-Notes-Analyzer.cmd` delegates to the installed current-user launcher; when no install exists it prints `Run Install-IZ-Clinical-Notes-Analyzer.cmd first.` and exits with code `20` (`PREFLIGHT_FAILED`).

The candidate build must be made from a clean source revision. The final build receipt is the authoritative place for the commit SHA, gate results, package path, and hash; later documentation-only commits may record the final hash and receipts without rebuilding the ZIP; the immutable receipt remains bound to the original clean build source.

## Historical V2 beta.3 release-validation boundary

The historical prerelease metadata recorded by this validation procedure is `2.0.0-beta.3` / build `2026.09.03.1` / channel `beta-local-desktop-v2`. Before package sign-off, use `docs/validation/office-manager-production-fixes-2026-09-03.md` and run the procedure from a clean isolated local-app-data directory with synthetic data only. Never package or validate against a production SQLite database, clinical export, saved API artifact, credential profile, upload, or log. Code-signing and retention/legal-hold controls remain R3 owner decisions; this historical prerelease is not a production-release claim. The builder now places `VERSION.json` at the external release-folder `app/` path and in the internal PyInstaller `_MEIPASS` runtime root; Task10 must verify both archive locations and the packaged `/api/version` response.

## Builder or Developer

### Normal build

Open the repository’s scripts folder and double-click `Build-IZ-Windows-Installer.cmd`, or run from the repository root:

```text
scripts/Build-IZ-Windows-Installer.cmd
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
`scripts/Build-IZ-Windows-Installer.cmd` again.

### If Node.js or npm is missing

Install Node.js LTS for Windows from:

```text
https://nodejs.org/
```

Advanced users may install it with:

```text
winget install OpenJS.NodeJS.LTS --scope user
```

Then double-click `scripts/Build-IZ-Windows-Installer.cmd` again.

### Preserved upgrade-test inputs

The builder verifies the immutable beta.3 and beta.4 ZIPs used to identify older installations. It checks `dist/windows-release` first, then the current user’s `not-required-for-deployment/repo/dist/windows-release` archive. To use a different storage location, pass `-PreservedArchiveDirectory "C:/path/to/preserved-zips"`. Both original files must be present and pass their pinned size/SHA-256 checks. These are development build inputs, not client runtime requirements. Existing production ZIPs are immutable; a normal build refuses to overwrite an existing release identity.

### Developer checkout location

Use a local checkout outside OneDrive for packaging. The current builder rejects reparse points in safe-data trees; the September 23 validation passed all 799 application tests but packaging stopped on the OneDrive `config/checklists` directory. This developer-build limitation is separate from the already-validated client ZIP installation paths. See [the validation record](validation/script-organization-2026-09-23.md).

### Advanced build options

Optional arguments are passed through to the PowerShell build script:

```text
scripts/Build-IZ-Windows-Installer.cmd -ValidationOnly -SkipTests
scripts/Build-IZ-Windows-Installer.cmd -ValidationOnly -SkipFrontendBuild
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
test, or unsafe file, then double-click `scripts/Build-IZ-Windows-Installer.cmd` again.

## End User

Use `docs\guides\Version 2.0 Beta  2.0.0-beta.2  beta-local-desktop-v2\Marleigh-Setup-Install-and-User-Guide.html` as the primary illustrated, non-technical clinical-manager guide for installation, first sign-in, Alleva readiness, daily treatment-plan review, backup, and troubleshooting.

### Install

1. Unzip the release zip completely. The candidate is designed to accept a normal local folder such as Downloads or Desktop and a OneDrive-backed package folder; do not run commands from inside the ZIP preview.
2. Open the unzipped release folder. The bootstrap stages and verifies the package before it writes the per-user installed application.
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

On a truly fresh install, sign in with the starter administrator credential supplied by R3 and replace it immediately when prompted. The starter credential is the same approved value across supported devices; it is not documented in the package. An upgrade or reinstall preserves existing account passwords and does not restore the starter credential for an initialized account.

The release includes `app\docs\patient-treatment-plan-handling.md`, the current reference for how patient treatment-plan data moves from manual upload or approved Alleva sync into local storage, deterministic timeliness status, aggregate diagnostics, and the Treatment Plans screen.

The release also includes `app\docs\beta-client-test-run-guide.md`, the non-technical first beta client test-run guide for install checks, day-of-test workflow, lookup status behavior, treatment-plan review expectations, diagnostics, backup, and maintenance.

### Launch

Launch the app from the Start Menu, Desktop shortcut, or:

```text
Launch-IZ-Clinical-Notes-Analyzer.cmd
```

The launcher starts the backend, serves the built browser app, opens the local
URL, and writes startup logs to the local AppData logs folder.

The package-root launcher checks the installed current-user launcher before it
delegates. If the app is absent, it prints `Run Install-IZ-Clinical-Notes-Analyzer.cmd first.` and exits with `20` (`PREFLIGHT_FAILED`). Extracting a package does not install it.

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

Use this data-preserving action for an upgrade or reinstall. A successful
operation returns `0`; cancellation is `10`, preflight failure is `20`,
incomplete removal is `40` (`REMOVAL_INCOMPLETE`), and cleanup pending is `41`
(`REMOVED_CLEANUP_PENDING`). Files whose ownership, length, or hash cannot be
verified are preserved; retained unknown files can therefore produce `40`.

Complete uninstall removes app files, shortcuts, and all local IZ Clinical
Notes Analyzer data for the current Windows user:

```text
Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd
```

Use complete uninstall only for an intentional current-user purge. It requires
the exact confirmation phrase `REMOVE IZ DATA`; without that phrase it returns
`10` without deleting local data. External backups, downloaded packages, and
other Windows profiles remain outside its scope. If a transaction is pending,
support must use `Recover` and wait for `RECOVERY_REQUIRED` (`31`) to clear
before starting the app.

### Do not edit `.env`

Do not manually edit `.env` unless R3 support asks you to. It contains local
configuration and encryption material needed for the app to read its local data.
