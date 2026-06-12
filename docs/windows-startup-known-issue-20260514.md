# Windows Startup Note

Status: resolved and retained in Version `1.1.1` / build `2026.06.12.1`.

## Original behavior

The Windows source-checkout launch path could incorrectly report a package-check problem after pip had already confirmed that all required packages were installed.

## Resolution

Version `1.1.1` keeps the local Windows launch fix and stale frontend-build detection so:

- `scripts\startup-windows-local.ps1` runs `scripts\preflight-windows.ps1` once before launch.
- `scripts\preflight-windows.ps1` validates the complete Windows runtime package set.
- `scripts\preflight-windows.ps1` rebuilds or warns when `frontend\dist` is older than the React source.
- `scripts\start-windows-local.ps1` is a thin wrapper around `startup-windows-local.ps1`, so preflight is not run twice.

## Validation commands

```powershell
scripts\preflight-windows.ps1 -AssumeYes
scripts\start-windows-local.ps1 -AssumeYes
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/readiness
Invoke-RestMethod http://127.0.0.1:8000/api/version
```

The expected app version after this patch is `1.1.1`.
