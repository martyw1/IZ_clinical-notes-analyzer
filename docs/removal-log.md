# Removal Log

Initial date: 2026-06-04

Latest update: 2026-07-10

Scope: historical S1 cleanup records plus later main-branch legacy Docker/PostgreSQL removal records.

## 2026-07-10 S0 Incident Containment (No Removals)

S0 preserved metadata-only evidence for tracked clinical-export artifacts and credential exposure in Git history. No artifact, export, credential-bearing path, Git object, branch, tag, remote ref, release artifact, or history entry was removed or modified during this station.

The authoritative exposure categories, counts, blob IDs, credential commit metadata, rotation requirement, downstream-owner inventory, remediation gates, and verification procedure are recorded in `docs/security/privacy-incident-s0-2026-07-10.md`.

Ordinary current-tree/release-scope removal is deferred to S1 and must be logged here only after the S0 gate passes. Any later current-tree deletion is containment, not Git-history remediation. Destructive history rewriting and any coordinated remote update remain separately gated by credential rotation, downstream-owner inventory, evidence retention, and explicit user approval.

## Policy

Cleanup is intentionally conservative. Files are removed only when they are generated, unsafe, or proven obsolete. When a file might contain unique product history, Windows validation evidence, PHI, credentials, or user-owned local work, it is retained or ignored rather than deleted.

## Removed Files

| Path | Reason | Safety evidence |
|---|---|---|
| `docs/First sign-in credentials.txt` | Local first-sign-in credential note; unsafe to retain in a source checkout and already ignored by `.gitignore`. | It was an ignored, untracked local credential artifact. Removed without reading or printing credential contents. |
| `.pytest_cache/` | Generated pytest cache. | Pytest hung before test collection while reading cache JSON from this directory; removing it restored a clean validation path. |
| `frontend/node_modules/.vite/` | Generated Vite dependency cache. | Vite/Vitest hung before producing a banner or test output; removed generated cache before retrying frontend validation. |
| `depriceated/` | Deprecated Docker/nginx-era archive had already been moved out of the active runtime path and was only referenced by historical docs. | 2026-06-17 `git ls-files depriceated docker-compose.db-expose.yml` showed only deprecated archive files; `rg` found no active script/backend/frontend/config/CI references, only historical/deprecated documentation. |
| `docker-compose.db-expose.yml` | Minimal Postgres port-exposure overlay is not an ordinary Windows desktop requirement and was not referenced by active launch, test, backend, frontend, config, or CI paths. | 2026-06-17 reference scan found only cleanup/history docs. Current Windows and CI validation do not depend on this overlay. |

## Retained Files and Reasons

| Path | Reason retained |
|---|---|
| `depricated/scripts/startup-windows.ps1` | Deprecated legacy Windows launcher retained as archive history only after being moved out of active `scripts/`. |
| `depricated/scripts/startup-macos.sh` | Deprecated legacy launcher retained as archive history only. Not a current R3 Windows desktop path. |
| `depricated/scripts/startup-ubuntu-24.04.sh` | Deprecated legacy launcher retained as archive history only. Not a current R3 Windows desktop path. |
| `depricated/scripts/lib/dedicated-postgres.sh` | Legacy helper retained as archive history only for deprecated Docker/PostgreSQL startup references. |
| `docs/prd-ver0.0-old-original.rtf` | Historical PRD archive. |
| `docs/chart-review-workflow-codex-build-prompt.md` | Historical chart-audit build prompt and implementation context. |
| `docs/windows-startup-known-issue-20260514.md` | Historical startup issue note; now marked resolved and superseded by current Version 1.4.2 guidance. |
| `Product Requirements Document.docx` | Untracked root artifact, likely duplicate/reference material; ignored to avoid accidental commit, but not deleted. |
| `walkthroughs/` | Untracked walkthrough exports/screenshots/transcripts; ignored because they may contain sensitive or non-synthetic content, but not deleted. |

## Moved to Deprecated Archive

| Original path | New path | Safety evidence |
|---|---|---|
| `diag-build-tools/git_sync_20260611-mac.sh` | `depricated/diag-build-tools/git_sync_20260611-mac.sh` | `rg` found no active references. Not part of Windows launch, backend, frontend, config, CI, or packaging paths. |
| `diag-build-tools/git_sync_20260611-win.ps1` | `depricated/diag-build-tools/git_sync_20260611-win.ps1` | `rg` found no active references. Not part of Windows launch, backend, frontend, config, CI, or packaging paths. |
| `scripts/start-desktop-local.ps1` | `depricated/scripts/start-desktop-local.ps1` | Active launch path is `Start-IZ-Clinical-Notes-Analyzer.cmd` -> `start-windows-local.ps1` -> `startup-windows-local.ps1`. |
| `scripts/startup-windows.ps1` | `depricated/scripts/startup-windows.ps1` | Deprecated legacy Docker/PostgreSQL Windows launcher; not called by current Windows startup wrappers. |
| `scripts/startup-macos.sh` | `depricated/scripts/startup-macos.sh` | Deprecated legacy Docker/PostgreSQL macOS launcher; not part of Windows local desktop requirements. |
| `scripts/startup-ubuntu-24.04.sh` | `depricated/scripts/startup-ubuntu-24.04.sh` | Deprecated legacy Docker/PostgreSQL Ubuntu launcher; not part of Windows local desktop requirements. |
| `scripts/lib/dedicated-postgres.sh` | `depricated/scripts/lib/dedicated-postgres.sh` | Legacy helper used only by deprecated Docker/PostgreSQL startup paths. |
| `video-extract (2026-06-05)/frontend-reference/` | `depricated/video-extract (2026-06-05)/frontend-reference/` | Historical UI reference code already translated into the active React app; no active references to the component file. |

## Ignore Rule Updates

Updated `.gitignore` to keep runtime SQLite files, logs, temporary files, coverage output, pytest/mypy caches, local root PRD duplicates, and walkthrough exports out of commits.

## Current Legacy Boundary

As of the 2026-06-28 cleanup pass, Docker, PostgreSQL, nginx, old Compose artifacts, and quarantined legacy startup/helper scripts are not ordinary R3 Windows desktop requirements. Do not restore the old Docker/server stack to active paths unless R3 explicitly reintroduces that deployment model and updates README, Windows docs, CI, tests, release instructions, and validation evidence together.

## Follow-Up Checks

- Re-run `git status --short --ignored` before staging to verify runtime/secret artifacts are not included.
- Re-run reference checks before deleting any retained legacy doc/script.
- Review any local credential files and remove them from the source checkout when confirmed generated/local-only.

## Historical Validation

| Check | Result |
|---|---|
| `git diff --check` | Passed. |
| Backend tests | Passed: `54 passed` using Python 3.11 from `/tmp/iz-cna-backend-venv-311`. |
| Frontend build | Passed after repairing missing local optional native packages in ignored `node_modules`. |
| Frontend tests | Blocked locally at the time of this historical cleanup note: Vitest worker pool timed out before importing tests under both Node 24 and Node 25. Later current docs track the supported frontend Vitest/build workflow for Version 1.4.2. |
