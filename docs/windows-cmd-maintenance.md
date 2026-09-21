# Windows CMD Maintenance

> **Production 1.0 candidate under validation.** Current build: `2026.09.21.1`, version `2.0.0-beta.4`, installer revision `1`. See the [installer portability validation criteria](validation/installer-portability-2026-09-21.md) before deployment. The verified September 15 package remains immutable historical evidence.

This page describes the Windows CMD contract implemented for Task 17. It is an operator draft for the candidate build. It does not certify a package, a target laptop, or a client deployment.

## Use a prepared package folder

1. Extract the supplied ZIP completely to a normal local folder or OneDrive-backed package folder. Do not run it from inside the ZIP preview.
2. Double-click `Install-IZ-Clinical-Notes-Analyzer.cmd`.
3. Wait for the installer window to report success or a stable failure code.
4. Start the app from the Start Menu shortcut `IZ Clinical Notes Analyzer`, or use `Launch-IZ-Clinical-Notes-Analyzer.cmd` from the package folder.

The packaged flow is intended for Windows 10/11 Home and Pro users without Windows administrator access. After extraction it is designed to work offline and without Git, Node.js, Python, Docker, PostgreSQL, or command-line work. The bootstrap stages and verifies package content before installation so the extracted package can be relocated without weakening installed-app or local-data path checks. A prepared package with built frontend assets is required; a source checkout is a developer path and is not the client package.

The install root is `%LOCALAPPDATA%\Programs\IZ Clinical Notes Analyzer`. The data root is `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`. The installer operates for the current Windows user and keeps application files separate from local data, encrypted uploads, audit history, settings, and recovery backups.

## Beta.3 and prior beta.4 upgrades

The installer performs a **smart upgrade in place** when it recognizes the shipped `2.0.0-beta.3` / build `2026.09.03.1` identity or an earlier beta.4 identity, including builds `2026.09.10.2` and `2026.09.15.2`. It backs up the current-user data, stages the new application, verifies the candidate runtime and data contract, then commits the new install. Existing accounts, password state, settings, encrypted uploads, audit history, and other supported local data stay in the current-user data root when preflight and verification succeed.

On a truly fresh install, the desktop administrator uses the starter credential supplied by R3 and must replace it before using the workspace. The approved starter credential is consistent across supported devices but is not printed in this guide or stored in release metadata. Upgrade and reinstall flows preserve initialized account passwords; the starter credential does not unlock or replace an existing account.

Do not run complete uninstall as an upgrade step. If preflight, verification, or the runtime acknowledgement fails, the controller returns a stable failure result and leaves recovery state for the `Recover` action. A committed install does not automatically replace newer work with an older snapshot.

## Launch behavior

The package-root `Launch-IZ-Clinical-Notes-Analyzer.cmd` delegates to the installed launcher under `%LOCALAPPDATA%\Programs\IZ Clinical Notes Analyzer`. If the current user has no installed launcher, it prints `Run Install-IZ-Clinical-Notes-Analyzer.cmd first.` and exits with code `20` (`PREFLIGHT_FAILED`). It never treats an extracted package folder as an installed app by itself.

## Normal uninstall preserves local data

Use `Uninstall-IZ-Clinical-Notes-Analyzer.cmd` for ordinary removal. It removes the owned application files and shortcuts for the current Windows user while preserving the local data root and recovery backups. The result reports `SUCCEEDED` / `NO_OP` with exit code `0`, cancellation with `10`, preflight failure with `20`, incomplete removal with `40` (`REMOVAL_INCOMPLETE`), or cleanup still pending with `41` (`REMOVED_CLEANUP_PENDING`).

Files under the per-user Program Files root whose ownership, length, or hash cannot be verified are preserved. If any such files remain, removal reports `40` (`REMOVAL_INCOMPLETE`) so support can investigate; the command does not delete unknown content.

Before reinstalling, keep the recovery backup and run the packaged `Backup-IZ-Clinical-Notes-Analyzer.cmd` when support requests a fresh copy. Use `Restore-IZ-Clinical-Notes-Analyzer.cmd` only with a same-user, same-computer backup. Do not edit or replace original archives; preserve them unchanged for provenance.

## Complete purge requires the exact phrase

Use `Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd` only when the current user intentionally wants the app-owned data removed. The confirmation phrase is exactly:

```text
REMOVE IZ DATA
```

Without that exact phrase, the command exits safely with code `10` and does not delete app data. The complete action removes the current-user app files and app-owned local data only. It does not delete external backups, downloaded packages, or data belonging to another Windows profile. Ambiguous or unowned paths fail closed and report a stable result; unknown files retained under the Program Files root can therefore produce `40` (`REMOVAL_INCOMPLETE`).

## Maintenance actions and support codes

The underlying maintenance dispatcher exposes these actions: `AutoInstall`, `Repair`, `Uninstall`, `RemoveData`, `Recover`, and `Status`. CMD wrappers select the appropriate action; support can use the action name and the printed receipt fields when triaging a result.

| Exit code | Status or reason | Meaning |
| ---: | --- | --- |
| `0` | `SUCCEEDED` / `NO_OP` | The requested operation completed, or the requested state was already present. |
| `10` | `CANCELLED` | Confirmation was absent or the user cancelled; destructive work did not proceed. |
| `20` | `PREFLIGHT_FAILED` | The package, identity, ownership, or required precondition was rejected. |
| `21` | `BUSY` | Another owned maintenance operation is active. Retry after it exits. |
| `30` | `ROLLED_BACK` | A failed transaction restored the pre-operation application/data state. |
| `31` | `RECOVERY_REQUIRED` | Recovery state remains; do not start the app until `Recover` completes. |
| `40` | `REMOVAL_INCOMPLETE` | Owned removal could not finish; local data remains protected. |
| `41` | `REMOVED_CLEANUP_PENDING` | Application removal finished but cleanup needs a later safe pass. |

`Status` is read-only. A clean committed install returns code `0`; pending or recovery state returns `RECOVERY_REQUIRED` / `31`. The result contract keeps secrets, raw exception text, PHI, and absolute machine-specific paths out of support output.

## Qualification and clinical boundaries

Build `2026.09.21.1` remains under validation. Its ZIP hash, final build receipt, relocated normal-folder and OneDrive-backed package tests, fresh-install credential behavior, upgrade password preservation, and Windows 10/11 lifecycle evidence must be recorded in [the current validation document](validation/installer-portability-2026-09-21.md) before any client-ready claim.

Historical build `2026.09.15.2` passed all seven build gates and the exact-package live HTTP/Edge lifecycle test in its recorded scope. Actual Windows 11 Home standard-user fresh installation, running uninstall, reinstall, and first-call purge passed. Its immutable package identity and remaining limits are recorded in [the September 15 validation report](validation/windows-cmd-maintenance-2026-09-15.md); those results are not evidence for the current candidate.

The clinical LOC-change timing rule remains configurable and visibly unvalidated. Missing or conflicting evidence must retain deterministic `Missing Data`, `Needs Review`, `Conflicting Evidence`, or `Unable to Evaluate` outcomes. Alleva REST treatment-plan sync remains an explicitly gated readiness path; live tenant import and startup sync remain disabled until the existing R3/Alleva authorization, mapping, compliance, and PHI approvals are complete.

Read the [open blockers](open-blockers.md), [Windows build/install guide](windows-installer-build-and-install.md), and [client package index](client-release-packages.md) together with the detached final build receipt. Do not publish or describe this candidate as released or client-ready until that evidence is present.
