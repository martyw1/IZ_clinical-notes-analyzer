# Installer Portability Validation - 2026-09-21

## Candidate identity and status

Version: `1.0.0`

Build: `2026.09.21.2`

Installer revision: `1`

Channel: `stable-local-desktop`

Status: **under validation; not yet client-ready.**

This document defines the evidence required for the portable Windows release candidate. Fill each pending field from the final clean-source package and its exact extracted ZIP. Do not reuse receipts, hashes, or lifecycle results from build `2026.09.15.2`; that package remains immutable historical evidence in [windows-cmd-maintenance-2026-09-15.md](windows-cmd-maintenance-2026-09-15.md).

## Intended client contract

- The client receives one prepared ZIP with a bundled desktop runtime and built frontend assets.
- After complete extraction, installation works from a relocated normal folder and a OneDrive-backed package folder.
- Ordinary Windows 10/11 use requires no Windows administrator access, Python, Node.js, Git, Docker, PostgreSQL, or command-line work.
- The bootstrap stages and verifies package content before writing the per-user installation.
- Installed application paths remain restricted to `%LOCALAPPDATA%\Programs\IZ Clinical Notes Analyzer` and runtime data remains restricted to `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.
- A truly fresh install uses the starter administrator credential supplied by R3 and requires immediate replacement with a personal password.
- The starter credential is device-independent and embedded in the application bootstrap. Saved local credentials are never copied into the package; passwords are excluded from screenshots, logs, and validation receipts.
- Upgrade and reinstall preserve existing accounts, passwords, password state, settings, encrypted uploads, audit history, and supported local data.

## Required build evidence

| Criterion | Status | Evidence |
| --- | --- | --- |
| Clean source revision recorded | Pending | Commit SHA: pending |
| Backend tests pass | Pending | Count/log: pending |
| Frontend tests pass | Pending | Count/log: pending |
| Frontend production build passes | Pending | Log: pending |
| Bundled desktop runtime builds | Pending | Log: pending |
| Release-folder required-file validation passes | Pending | Receipt field: pending |
| Release-folder and ZIP forbidden-file scans pass | Pending | Receipt field: pending |
| Final package identity matches version/build/revision above | Pending | Manifest/receipt: pending |
| Final ZIP SHA-256 recorded | Pending | SHA-256: pending |

## Required portability and lifecycle evidence

Use synthetic data only. Record Windows edition/build, standard-user status, source package path class, exact result code, and receipt location for every run.

| Scenario | Windows 10 | Windows 11 | Acceptance condition |
| --- | --- | --- | --- |
| Fresh install from a relocated normal local folder | Pending | Pending | Install succeeds without elevation; installed and data roots are exact and package-source-independent. |
| Fresh install from a OneDrive-backed package folder | Pending | Pending | Cloud-source handling stages and verifies the complete package; install succeeds without loosening destination checks. |
| Launch from Start Menu or Desktop shortcut | Pending | Pending | Installed launcher starts the local app and `/api/version` reports the candidate identity. |
| Truly fresh administrator sign-in | Pending | Pending | The R3-supplied starter credential works consistently and forces a personal password change before workspace use. |
| Upgrade from a supported beta.3/beta.4 install | Pending | Pending | Existing account password and password state remain valid; supported local data is preserved. |
| Data-preserving uninstall and reinstall | Pending | Pending | Application files are replaced while the existing account password and local data remain usable. |
| Typed complete purge | Pending | Pending | Exact confirmation is required and only the current user's owned application/data roots are removed. |
| Relocated package after extraction | Pending | Pending | Moving the extracted package to another allowed source folder does not bind installation to the original extraction path. |
| Incomplete or unavailable cloud files | Pending | Pending | Installation fails closed with a stable safe result and does not commit a partial install. |
| Invalid installed/data destination attempt | Pending | Pending | Strict canonical destination validation rejects the attempt. |

## Security and privacy evidence

| Criterion | Status | Evidence |
| --- | --- | --- |
| No PHI, local database, uploads, logs, `.env`, tokens, or encryption material in the release folder or ZIP | Pending | Scan receipt: pending |
| No saved local credentials in release files; no passwords in logs, screenshots, or receipts | Pending | Search result: pending |
| Diagnostics remain redacted and exclude clinical content and access material | Pending | Lifecycle evidence: pending |
| Existing password hashes and sessions follow the documented upgrade contract | Pending | Focused test/lifecycle evidence: pending |
| Rollback or recovery leaves no unverified partial install | Pending | Failure-path evidence: pending |

## Clinical and integration boundaries

Deterministic clinical rules are unchanged. Production 1.0 also corrects unlinked-placeholder lifecycle handling and expands safe authentication and Alleva forensic diagnostics. The LOC-change treatment-plan update window remains configurable and visibly unvalidated. Missing or conflicting evidence must continue to produce deterministic `Missing Data`, `Needs Review`, `Conflicting Evidence`, or `Unable to Evaluate` outcomes. Alleva treatment-plan sync remains off by default and gated by the existing tenant authorization, mapping, compliance, and PHI approvals.

## Final determination

Client-ready decision: **Pending**

Final package path: pending

Final ZIP SHA-256: pending

Build receipt: pending

Validation owner/date: pending

Known limits or deferred scenarios: pending
