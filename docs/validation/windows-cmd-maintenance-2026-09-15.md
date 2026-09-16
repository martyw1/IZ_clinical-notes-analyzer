# Windows CMD maintenance validation - 2026-09-15

## Current package

- Version `2.0.0-beta.4`, build `2026.09.15.2`, installer revision `1`.
- Clean build source: `a79d2a77ce3377ba31f8b38b08e6c9f5e6dd12ef`.
- Package folder: `dist/windows-release/IZ-CNA-337308272cfbf7e6`.
- ZIP: `IZ-Clinical-Notes-Analyzer-v2.0.0-beta.4-build-2026.09.15.2-installer-r1.zip`, 39,192,346 bytes.
- ZIP SHA-256: `7a9dbbfa54f204cda2d88a4dfdb18a1007e79e30666db5fc2cdcaca567c52a65`.
- Sibling build receipt SHA-256: `8ed305d3b6a39bb20ad9642ab1cde58ad5c6ef20b75f7ef4b7ae30e5fc8f59cb`.
- Manifest SHA-256: `5e4da285b320d13b86f222be406cbfa27781dcc25bc728c65ee2cbd2f988d0bf`.

The ZIP is immutable and remains bound to the clean source above. Subsequent documentation-only commits record results; they do not rebuild or replace the package. Original beta.3 and earlier beta.4 archives remain unchanged.

## Corrections found through actual Windows use

1. Accept SYSTEM ownership only for the exact Windows UserProfile known folder when the current SID's registered ProfileList path also matches. Package, application, data and arbitrary path ownership checks remain strict.
2. Normalize absent optional arguments at both public PowerShell entry points. Windows PowerShell 5.1 previously rejected ordinary CMD invocation through a null `.Count` access.
3. After validating the removal bundle and context, stop only the receipt-owned runtime before fingerprinting the database. This avoids reading locked, actively changing SQLite files without weakening file sharing or data checks.
4. Remove only the bootstrap's marker-validated empty transaction scaffold before dispatching removal. Unknown files, directories and reparse points still fail closed. Complete purge now finishes in one invocation.

The temporary QA harness also needed file-backed output capture because a deliberately running child app retained redirected output pipes. Mixed diagnostic identities and old diagnostic residue were corrected in the fixture; those failed attempts are not represented as product passes. Final tests use a fresh copy of the immutable package.

## Build and packaged-app results

All seven build gates passed: 595 backend tests (one existing deprecation warning), 182 frontend tests across 28 files, frontend build, repository safety, release-folder safety, ZIP safety, and frozen executable inspection.

The first final-source full run encountered a one-second runtime shutdown timing assertion despite observing process exit. Its immediate focused rerun passed. One unchanged full-build retry then passed all 595 backend tests; no test or timeout was weakened.

The exact-artifact P02 run passed using the packaged executable, live localhost HTTP and Edge. It covered beta.3 seeding, semantic upgrade preservation, browser checks, multipart upload/readback and access control, retained uninstall, reinstall, password rotation, typed purge, and zero owned processes/listeners after cleanup. This component-profile run does not by itself certify default Windows profiles.

- P02 receipt: `.omo/evidence/windows-cmd-maintenance/cmd-d72a4fb83e16/maintenance-run-receipt.json`.
- Receipt SHA-256: `37a1b0e04ace2468780befd5f4d934626dc1eeadcc563c5698f51705bced99bc`.
- Case SHA-256: `ceeec7f0c8d18907729121819f5f93ab4efb4eeb97d9475218fee0ce7aa709c8`.

## User-approved core deployment acceptance

The user accepted this immutable package for the critical core deployment scope: fresh install, beta.3 smart upgrade with preserved data, live local API and browser operation, data-preserving uninstall, reinstall, and typed complete purge. The final exact-package acceptance rerun passed all nine live HTTP/Edge/executable lifecycle steps, safety and redaction checks, and cleanup with zero owned processes or listeners.

- Final core-acceptance P02 receipt: `.omo/evidence/windows-cmd-maintenance/cmd-9ac37e50b421/maintenance-run-receipt.json`.
- Receipt SHA-256: `cda9db5e33682d4940ba1d7dc357b495524e142f7a0a7ac2be527e6f944ca9df`.
- Case SHA-256: `7f6e40146b1f65a68b120d699579904e2dec36737532d640e55c305c5364f034`.
- Bound source: `a79d2a77ce3377ba31f8b38b08e6c9f5e6dd12ef`; immutable ZIP SHA-256: `7a9dbbfa54f204cda2d88a4dfdb18a1007e79e30666db5fc2cdcaca567c52a65`.

This is a scoped deployment acceptance, not a claim that every Home, VM, browser, power-loss, or process-isolation case passed. The broader cases under **Remaining qualification boundary** remain explicitly unverified and are deferred by the user; they are not critical blockers for the accepted core deployment.

Host cleanup subsequently verified zero temporary QA accounts, profiles, profile directories, and credential XML files. One verified public QA staging folder remains because automatic approval policy blocked its removal; it is noncritical housekeeping and not an application deployment blocker.

## Actual standard accounts on Windows 11 Home

Two temporary, separate standard Windows accounts were used with their actual default profiles on Windows 11 Home build 26200. Their installer processes were not administrators, and Git, Node, Python and Docker were absent from the test PATH. Account creation/removal required host administration; normal app installation and removal did not.

The final artifact passed fresh installation, running normal uninstall retaining data, reinstall, and first-call typed complete purge under the second account. Program, data, maintenance folders and owned shortcuts were absent afterward, with zero owned app processes. The diagnostic run is preserved separately and is not substituted for final-package evidence.

The first account's beta.3 baseline was installed using the original public installer and seeded through live HTTP with four accounts, three plans and three encrypted sources. Its upgrade to the final package passed without complete uninstall. Build identity, preserved accounts/plans, new upload (201), encrypted readback/hash verification, and role denial (403) passed. Full encrypted backup and public launch also passed.

R07 is not fully qualified. Cross-user backup decryption was rejected (`BACKUP_KEY_UNAVAILABLE`), but account B could terminate account A's live app process in the credential-created test session. A control test showed the same behavior for an ordinary PowerShell child owned by A: B had a different SID, was not an administrator, and had no SeDebugPrivilege, yet termination succeeded. This does not establish an app-specific defect or prove isolation on normal interactive sessions. No product or host permission changes were made. Repeat the process-isolation test using independently signed-in standard accounts in the target Windows environment. The other cross-user checks passed: B could not read A's configuration; B's own uninstall left A's runtime intact; A subsequently authenticated over live HTTP and verified four plans, four encrypted sources, readback hash equality and role denial (403). The upgraded account then passed retained uninstall, reinstall with live readback, password rotation and replacement login, and first-call typed purge. Final inspection of both accounts found no program, data, maintenance folders or owned shortcuts, and zero app/listener/controller processes.

The combined final standard-user receipt is `.omo/evidence/windows-cmd-maintenance/standard-user-qa-20260915/final-standard-user-qualification.json`, SHA-256 `08e4a8b3a33c0cf4b08ed440a667422f3ade68b304f0e7289fc3da7a9d68bf12`. It binds the final source, ZIP, P02, account-specific results and the process-control qualification limit. Ownership/control and platform evidence is also retained under `.omo/evidence/windows-cmd-maintenance/standard-home-20260915/`. Credentials, database contents, raw runtime logs and encrypted fixture secrets are not committed or packaged.

## Remaining qualification boundary

This is not a claim that the entire Home or power-loss matrix passed. Windows 10 Home, verified offline/network-isolated operation, the full running-upgrade/browser/write-drain scenario, all bootstrap-shortcut scenarios and complete Edge/Chrome Home coverage remain unqualified by this run. See the exact cases in `scripts/tests/maintenance-cases.json`.

R09 remains blocked: no disposable Windows 10/11 Home guest images or VM controller have been supplied. Abrupt guest power-off before/after every defined journal-state boundary and reboot recovery were not performed. Killing a process is not power-loss evidence, and the host was not interrupted.

All test records were synthetic. Live calls were to actual local app APIs; no approved tenant import or real patient access is claimed. Alleva live import/sync remains gated. LOC-change timing remains configurable and visibly unvalidated. Beta.3 supports upgrade in place; complete uninstall is not an upgrade step. Normal uninstall preserves data, and complete purge separately requires `REMOVE IZ DATA`.
