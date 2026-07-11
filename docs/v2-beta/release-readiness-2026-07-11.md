# V2 Beta.2 Release Readiness Record

Date: 2026-07-11
Applies to: `2.0.0-beta.2` / build `2026.07.11.1` / channel `beta-local-desktop-v2`

## Release Classification

This is a local-desktop prerelease metadata and documentation update. It is not a production release and must not be represented as one. The V2 application remains local-first, deterministic for treatment-plan decisions, and gated against unapproved live Alleva synchronization.

## Version Surface Contract

The following surfaces must agree before packaging:

- `VERSION` and `VERSION.json`
- `frontend/package.json` and `frontend/package-lock.json`
- `backend/app/core/config.py` and `GET /api/version`
- V2 authenticated shell footer
- sample OpenAPI definition
- `scripts/preflight-windows.ps1`

Expected values are version `2.0.0-beta.2`, build `2026.07.11.1`, channel `beta-local-desktop-v2`, and release date `2026-07-11`.

## Required Isolated Synthetic Validation

Run final validation from a fresh local clone or clean worktree. Use Windows PowerShell and an empty temporary local-data directory; never reuse the normal operator app-data location.

```powershell
$runId = [guid]::NewGuid().ToString('N')
$env:IZ_CNA_LOCAL_APP_DATA_DIR = Join-Path $env:TEMP "iz-cna-beta2-$runId"
$env:ENVIRONMENT = 'development'
Remove-Item -LiteralPath $env:IZ_CNA_LOCAL_APP_DATA_DIR -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $env:IZ_CNA_LOCAL_APP_DATA_DIR -Force | Out-Null
```

Before launch, verify that this environment has no `IZ_CNA_ENV_FILE`, no tenant credential profile, and no copied `.env`, local SQLite database, upload, export, API-harness report, or log. Use only generated synthetic users, synthetic Patient IDs, and repository-approved synthetic fixtures. Do not inspect or import content from clinical-export artifacts.

Run the normal automated gates and package process:

```powershell
$env:PYTHONPATH = "$PWD\backend"
.\backend\.venv\Scripts\python.exe -m pytest .\backend\tests -q
Push-Location .\frontend
npm run test -- --run
npm run build
Pop-Location
.\Build-IZ-Windows-Installer.cmd
```

Then drive the built/installed desktop application through its real UI using the same isolated environment. Confirm `/api/version` returns the expected values and the authenticated V2 footer reads `Version 2.0 Beta | 2.0.0-beta.2 | beta-local-desktop-v2`. Validate login, recovery/lockout, dashboard, manual synthetic upload, plan detail, deterministic 42-step findings, manager/counselor workflow, redacted API harness behavior, logs, backup/restore, and package lifecycle only with synthetic data. Preserve only redacted screenshots and command results outside the repository; do not stage `.omo`, build output, local app data, logs, or evidence artifacts.

## External Production Gates

The following items are not code-completion claims and must be closed by the named accountable owners:

1. R3 and Alleva approve and supervise a live contract and end-to-end sync validation using approved non-PHI/test records.
2. The exposed credential owner rotates and disables the exposed credential; downstream clone, cache, artifact, backup, and support-copy owners complete metadata-only disposition; the repository owner approves any history-remediation procedure before a destructive rewrite or `--force-with-lease` update.
3. R3 IT decides whether signing/MSI/MSIX is required for the target deployment and records the selected distribution control.
4. R3 records/security owners define retention and legal-hold handling for incident evidence, diagnostics, backups, and release support materials.

Until every applicable gate is closed with retained redacted evidence, do not label the software production-ready, do not enable live sync, and do not merge a release on the basis of this document alone.

## Support Handoff

Support may report the version, build, channel, failure classification, redacted log timestamps, and safe diagnostic artifact identifiers. Support must not collect patient names, clinical narrative, original filenames, credentials, tokens, Authorization headers, raw Alleva payloads, local encryption material, or unsafe Git-history content.
