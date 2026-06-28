# Deprecated Code Manifest

Updated: 2026-06-28

This folder quarantines code/reference-code files that are not part of the active Windows local desktop runtime, backend tests, frontend tests, CI, or release package.

| Original path | Deprecated path | Reason |
| --- | --- | --- |
| `diag-build-tools/git_sync_20260611-mac.sh` | `depricated/diag-build-tools/git_sync_20260611-mac.sh` | Historical diagnostic sync script; no active references. |
| `diag-build-tools/git_sync_20260611-win.ps1` | `depricated/diag-build-tools/git_sync_20260611-win.ps1` | Historical diagnostic sync script; no active references. |
| `scripts/start-desktop-local.ps1` | `depricated/scripts/start-desktop-local.ps1` | Superseded by `scripts/start-windows-local.ps1` and `scripts/startup-windows-local.ps1`. |
| `scripts/startup-windows.ps1` | `depricated/scripts/startup-windows.ps1` | Deprecated legacy Windows Docker/PostgreSQL startup path. |
| `scripts/startup-macos.sh` | `depricated/scripts/startup-macos.sh` | Deprecated legacy macOS Docker/PostgreSQL startup path. |
| `scripts/startup-ubuntu-24.04.sh` | `depricated/scripts/startup-ubuntu-24.04.sh` | Deprecated legacy Ubuntu Docker/PostgreSQL startup path. |
| `scripts/lib/dedicated-postgres.sh` | `depricated/scripts/lib/dedicated-postgres.sh` | Legacy PostgreSQL helper for deprecated container/server startup paths. |
| `video-extract (2026-06-05)/frontend-reference/` | `depricated/video-extract (2026-06-05)/frontend-reference/` | Historical UI mockup/reference code already implemented in the active React app. |

Current Windows launch remains `scripts/Start-IZ-Clinical-Notes-Analyzer.cmd` -> `scripts/start-windows-local.ps1` -> `scripts/startup-windows-local.ps1`.
