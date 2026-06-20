# Removal Log

Initial date: 2026-06-04

Latest update: 2026-06-20

Scope: historical S1 cleanup records plus later main-branch legacy Docker/PostgreSQL removal records.

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
| `scripts/startup-windows.ps1` | Potential legacy/server-mode Windows launcher, but not proven obsolete. Not the current Version 1.4.2 local-desktop launch path. |
| `scripts/startup-macos.sh` | Deprecated legacy launcher retained for history. Not a current R3 Windows desktop path. |
| `scripts/startup-ubuntu-24.04.sh` | Deprecated legacy launcher retained for history. Not a current R3 Windows desktop path. |
| `scripts/lib/dedicated-postgres.sh` | Legacy helper retained only for deprecated Docker/PostgreSQL startup references. |
| `docs/prd-ver0.0-old-original.rtf` | Historical PRD archive. |
| `docs/chart-review-workflow-codex-build-prompt.md` | Historical chart-audit build prompt and implementation context. |
| `docs/windows-startup-known-issue-20260514.md` | Historical startup issue note; now marked resolved and superseded by current Version 1.4.2 guidance. |
| `Product Requirements Document.docx` | Untracked root artifact, likely duplicate/reference material; ignored to avoid accidental commit, but not deleted. |
| `walkthroughs/` | Untracked walkthrough exports/screenshots/transcripts; ignored because they may contain sensitive or non-synthetic content, but not deleted. |

## Ignore Rule Updates

Updated `.gitignore` to keep runtime SQLite files, logs, temporary files, coverage output, pytest/mypy caches, local root PRD duplicates, and walkthrough exports out of commits.

## Current Legacy Boundary

As of Version `1.4.2`, Docker, PostgreSQL, nginx, and old Compose artifacts are not ordinary R3 Windows desktop requirements. Do not restore the old Docker/server stack to active paths unless R3 explicitly reintroduces that deployment model and updates README, Windows docs, CI, tests, release instructions, and validation evidence together.

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
