# Windows Startup Note

Status: resolved and retained in current Version `1.4.2` / build `2026.06.18.2`.

Historical resolution version: `1.1.1` / build `2026.06.12.1`.

## Original behavior

The Windows source-checkout launch path could incorrectly report a package-check problem after pip had already confirmed that all required packages were installed.

## Current resolution

Version `1.4.2` keeps the local Windows launch fix, stale frontend-build detection, local AppData setup, rules/checklist validation, dependency prompts, and release-folder launch behavior so:

- `scripts\startup-windows-local.ps1` runs `scripts\preflight-windows.ps1` once before launch.
- `scripts\preflight-windows.ps1` validates the complete Windows runtime package set.
- `scripts\preflight-windows.ps1` validates rules and the Treatment Plan Checklist.
- `scripts\preflight-windows.ps1` rebuilds or warns when `frontend\dist` is missing or older than the React source.
- `scripts\start-windows-local.ps1` is a thin wrapper around `startup-windows-local.ps1`, so preflight is not run twice.
- A prepared Version `1.4.2` release folder should already contain built frontend assets for non-technical Windows users.

## Validation commands

```powershell
scripts\preflight-windows.ps1 -AssumeYes
scripts\start-windows-local.ps1 -AssumeYes
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/readiness
Invoke-RestMethod http://127.0.0.1:8000/api/version
```

The expected app version after current patch installation is `1.4.2` / build `2026.06.18.2`.
