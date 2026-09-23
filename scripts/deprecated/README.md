# Historical tools: not for Production 1.0 operation

Use `../Start-IZ-Clinical-Notes-Analyzer.cmd` for the current source app and `../preflight-windows.ps1` for setup. This directory is excluded from client packages.

| Archived item | Current workflow / reason |
|---|---|
| `startup-windows-local.ps1` | Its runtime supervision is consolidated into `../start-windows-local.ps1 -Foreground`. This preserved source snapshot assumes its original directory: do not execute it here. |
| `setup-windows.ps1` | Redundant alias of `../preflight-windows.ps1`; retained as a historical snapshot, not a runnable entry point here. |
| `test-beta4-password-upgrade.mjs` | Tests the historical beta.3-to-beta.4 transition and requires those old extracted runtimes. Current package qualification uses `../tests/test-cmd-maintenance.ps1`. |
| `admin_recovery/` | Standalone beta.3 administrator recovery source and tests. Current source support uses `../update-local-admin.ps1`; these tools have different recovery contracts. Historical recovery is retained for support, not packaged or recommended for Production 1.0. |

Archived names remain in historical validation reports. No released ZIP was rewritten. Do not move these files back into active use without checking their original version and dependencies.
