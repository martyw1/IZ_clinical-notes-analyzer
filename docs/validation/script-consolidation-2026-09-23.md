# Script workflow consolidation — 2026-09-23

## Result

The audit covered 96 scripts. There were no exact or newline-normalized duplicate files, but the folder mixed operator commands, internal implementations, tests and historical tools. The top-level script count is reduced from 42 to 25. The task-oriented [script guide](../../scripts/README.md) now directs each operator task to one entry point.

The Windows source launcher now has one implementation, `scripts/start-windows-local.ps1`. Its default mode launches a hidden copy with `-Foreground` and waits for readiness. The foreground branch alone runs preflight, starts/supervises Uvicorn, opens the browser after readiness, and cleans up its owned process. Both modes reuse one port-validation function and one readiness function. `Stop` retains recognition of the old startup filename for a process launched before consolidation.

Regression tests live under `scripts/tests/`; direct API probes live under `scripts/diag-build-tools/`. The current password browser test no longer has a beta-specific filename. Historical beta upgrade/recovery tools and the superseded startup/setup scripts are under `scripts/deprecated/`. Archived startup/setup snapshots are not executable entry points in their new location; their README directs operators to the current commands.

Client installer templates and installed launcher filenames are preserved. Similar-named CMD/PowerShell files remain where they are required delegation pairs. Runtime application code, authentication rules, version metadata, local user data and the immutable client ZIP are unchanged. Private diagnostic settings/logs/exports were not moved or staged.

## Verification

- Five existing launcher contract checks passed before and after consolidation.
- 31 production-configuration, version-consistency and CI-receipt tests passed.
- 58 synthetic diagnostic Pester tests passed after relocation.
- 24 office-manager CLI/credential guard tests passed.
- Changed PowerShell files parsed; both moved Node scripts and Bash smoke passed syntax checks.
- Actual source CMD startup, health/version, fresh temporary-password login, duplicate-start refusal, background stop, foreground readiness and foreground stop passed in a fresh isolated local profile. No existing user database was used.
- Stop regression passed, including idempotence and preserving an unrelated Python listener.
- Release-safety regression passed. Executing the builder's actual copy function against synthetic fixtures confirmed exclusion of `deprecated`, `diag-build-tools`, `tests` and installer authoring inputs while retaining required config data.
- The relocated broader lifecycle test reached its profile/WAL setup checks, then stopped at the pre-existing OneDrive `PATH_REPARSE_POINT` guard in `maintenance-paths.psm1`. Its full result is not claimed as passing. The earlier full-build limitation in this checkout remains documented in [the preceding validation](script-organization-2026-09-23.md); no new installer ZIP was built.

Local execution evidence and baseline hashes are under `.omo/evidence/script-consolidation/`, excluded from Git. No live vendor API calls were made. macOS and client-machine qualification were not performed by this Windows source-script refactor.

## Move inventory

| Previous absolute path | Current absolute path |
|---|---|
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/test-alleva-api-connectivity.ps1` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/diag-build-tools/test-alleva-api-connectivity.ps1` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/test-alleva-end-user-tools.ps1` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/tests/test-alleva-end-user-tools.ps1` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/test-alleva-patient-workflow-live.ps1` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/diag-build-tools/test-alleva-patient-workflow-live.ps1` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/test-api-configuration-local.ps1` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/tests/test-api-configuration-local.ps1` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/test-cmd-maintenance.ps1` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/tests/test-cmd-maintenance.ps1` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/test-local-app-stack.ps1` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/tests/test-local-app-stack.ps1` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/test-office-manager-smoke.ps1` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/tests/test-office-manager-smoke.ps1` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/test-release-safety.ps1` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/tests/test-release-safety.ps1` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/test-windows-installer-packaging.ps1` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/tests/test-windows-installer-packaging.ps1` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/test-windows-lifecycle.ps1` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/tests/test-windows-lifecycle.ps1` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/test-windows-release-archive.ps1` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/tests/test-windows-release-archive.ps1` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/test-windows-stop.ps1` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/tests/test-windows-stop.ps1` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/smoke.sh` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/tests/smoke.sh` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/test-beta4-password-browser.mjs` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/tests/test-password-browser.mjs` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/test-beta4-password-upgrade.mjs` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/deprecated/test-beta4-password-upgrade.mjs` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/startup-windows-local.ps1` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/deprecated/startup-windows-local.ps1` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/setup-windows.ps1` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/deprecated/setup-windows.ps1` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/admin_recovery/READ-ME-FIRST.txt` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/deprecated/admin_recovery/READ-ME-FIRST.txt` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/admin_recovery/Reset-IZ-Admin.py` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/deprecated/admin_recovery/Reset-IZ-Admin.py` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/admin_recovery/build-recovery.ps1` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/deprecated/admin_recovery/build-recovery.ps1` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/admin_recovery/recovery_core.py` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/deprecated/admin_recovery/recovery_core.py` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/admin_recovery/test_packaged_recovery.py` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/deprecated/admin_recovery/test_packaged_recovery.py` |
| `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/admin_recovery/test_recovery.py` | `C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/scripts/deprecated/admin_recovery/test_recovery.py` |
