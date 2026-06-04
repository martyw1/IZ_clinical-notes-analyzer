# Cleanup Audit - S0 Baseline

Date: 2026-06-04
Branch: `refactor/codex-v0.5.0`
Baseline: `695080d`, tagged `baseline-pre-codex-20260604-164125`

## Scope

This is the S0 cleanup audit. No files were deleted or moved in this station. S1 cleanup should use this as a starting point, then re-run reference checks before any deletion.

## File Inventory by Purpose

| Purpose | Files/directories |
|---|---|
| Repo instructions | `AGENTS.md` |
| Product/version metadata | `README.md`, `CHANGELOG.md`, `VERSION`, `VERSION.json` |
| Backend app | `backend/app/` |
| Backend tests | `backend/tests/`, `pytest.ini` |
| Backend dependencies | `backend/requirements.txt`, `backend/requirements-windows-local.txt` |
| Backend packaging/container | `backend/Dockerfile` |
| Frontend app | `frontend/src/`, `frontend/index.html`, `frontend/app.css` through `frontend/src/app.css` |
| Frontend dependencies/config | `frontend/package.json`, `frontend/package-lock.json`, `frontend/tsconfig.json`, `frontend/vite.config.ts` |
| Frontend container/static serving | `frontend/Dockerfile`, `frontend/nginx.conf` |
| Deterministic rules | `config/rules/alleva_treatment_plan_completeness_rules.yaml` |
| Windows launch/validation | `scripts/Start-IZ-Clinical-Notes-Analyzer.cmd`, `scripts/startup-windows-local.ps1`, `scripts/test-local-app-stack.ps1`, `scripts/test-api-configuration-local.ps1`, `scripts/test-alleva-api-connectivity.ps1`, `scripts/start-desktop-local.ps1` |
| Developer/server launch | `scripts/smoke.sh`, `scripts/startup-macos.sh`, `scripts/startup-ubuntu-24.04.sh`, `scripts/startup-windows.ps1`, `scripts/lib/dedicated-postgres.sh` |
| Docker/CI | `docker-compose.yml`, `docker-compose.db-expose.yml`, `.github/workflows/ci.yml` |
| Operator/developer docs | `docs/*.md`, `docs/Product Requirements Document.pdf`, `docs/prd-treatment-plan-timeliness-mvp-2026-06-01.docx`, `docs/prd-ver0.0-old-original.rtf`, `docs/open-blockers.md` |
| Synthetic examples | `docs/sample-clinical-notes/` |
| Ignored local credential note | `docs/First sign-in credentials.txt` |
| Untracked local artifacts | `Product Requirements Document.docx`, `walkthroughs/` |

## Dead-Code Candidates

These are candidates only. Do not delete until S1 proves they are unreferenced, superseded, or generated.

| Candidate | Evidence | Safety assessment |
|---|---|---|
| `scripts/startup-windows.ps1` | Main README and AGENTS point to `startup-windows-local.ps1`; this script appears to be an older Docker/PostgreSQL Windows path. | Potentially removable only if no supported server-mode Windows workflow needs it. Retain for now. |
| `docker-compose.db-expose.yml` | Minimal overlay exposes Postgres port and is not referenced by README or CI scan. | Candidate for removal or documentation, but keep until Compose workflow intent is confirmed. |
| `docs/prd-ver0.0-old-original.rtf` | Renamed legacy PRD archive. | Not dead if archive history is desired. Retain unless superseded archive policy says remove. |
| `docs/chart-review-workflow-codex-build-prompt.md` | Historical build prompt for earlier chart-audit workflow. | Legacy reference, not runtime dead code. Retain until docs archive policy is set. |
| `docs/windows-startup-known-issue-20260514.md` | Known issue doc may be stale after launcher hardening. | Candidate for archive/update, not deletion until current Windows behavior is verified. |

## Legacy Candidates

| Area | Candidate | Notes |
|---|---|---|
| Product direction | Existing chart-audit dashboard and workflow labels | Current app still says "Clinical notes completeness review" and "R3 Chart Audit"; v0.5.0 needs Treatment Plan Timeliness Tracker positioning. Do not remove until replacement workflow is implemented. |
| Rules | Broad `IOP`/`OUTPATIENT` rules | PRD needs configurable IOP-5, IOP-19, IOP-3, OP aliases and 30/60-day recurrence. Existing rules should be migrated/expanded, not deleted blindly. |
| Docs | Older PRD/runbook/refactor notes | Useful as implementation history. Move to archive only after README and current PRD cover required operator/developer information. |
| Server-mode scripts | macOS/Ubuntu/Docker/PostgreSQL launchers | Not ordinary Windows requirements, but still referenced in docs and CI/server contexts. Keep unless product scope removes server mode. |

## Duplicate Code Paths

| Duplicate/overlap | Files | Assessment |
|---|---|---|
| Settings/API credential editing | `backend/app/api/routes.py`, `backend/app/api/api_config_routes.py`, frontend settings UI | API config route encrypts saved API key material; general settings route directly assigns LLM and reputation API keys. Consolidate secret handling in S2/S3. |
| API configuration UI | React settings view plus standalone `api_config_ui_routes.py` HTML page | Useful for desktop direct harness, but duplicate UX paths need consistency tests. |
| Startup scripts | `startup-windows-local.ps1`, `start-desktop-local.ps1`, `startup-windows.ps1`, macOS/Ubuntu scripts | Keep all currently referenced scripts, but distinguish ordinary Windows local runtime from Docker/server launchers in docs. |
| Health/readiness endpoints | `/health`, `/api/health`, `/api/readiness`, `/api/system/readiness` | Intentional compatibility overlap, but should be documented. |
| Treatment plan logic | `config/rules/*.yaml`, `backend/app/services/rules_engine.py`, `backend/app/services/evaluation.py`, audit template | Rules engine and chart-audit evaluator both touch treatment-plan concepts. v0.5.0 should make one canonical timeliness engine/API. |

## Stale Docs and Scripts

| File | Reason to review | Delete now? |
|---|---|---|
| `docs/windows-startup-known-issue-20260514.md` | May describe an old startup dependency issue. | No. Validate on Windows first. |
| `docs/windows-local-refactor.md` | Refactor notes may be partially superseded by README. | No. Update/archive after v0.5.0 docs stabilize. |
| `docs/runbook.md` | Mentions dedicated PostgreSQL runtime, while Windows target is SQLite-first. | No. Clarify server vs desktop modes. |
| `docs/CODEX_COMPLETION_LOG.md` | Historical completion log needs new station entries. | No. Append after stations. |
| `scripts/startup-windows.ps1` | Older Docker/PostgreSQL Windows path can confuse ordinary Windows users. | No. Either document as legacy/server or remove in S1 after references and need are resolved. |

## Unused Dependency Candidates

No dependency was proven unused in S0. Evidence scan shows current references for the major dependencies:

| Dependency | Evidence |
|---|---|
| `fastapi`, `uvicorn`, `SQLAlchemy` | Core backend app, routing, DB. |
| `psycopg[binary]` | PostgreSQL developer/server support and DB URL tests. |
| `python-jose`, `passlib`, `bcrypt` | JWT and password hashing. |
| `python-multipart` | Upload forms/files. |
| `pydantic-settings` | Environment-backed settings. |
| `email-validator` | Pydantic email support dependency; not directly imported in app code. Keep until schema validation needs are checked. |
| `pypdf` | PDF text extraction and readiness checks. |
| `cryptography` | Upload and secret encryption. |
| `PyYAML` | YAML rules engine. |
| `pyinstaller` | Packaging direction; not currently evidenced by a packaging script. Candidate for review after installer plan. |
| `pytest`, `httpx` | Backend tests and API clients. |
| React/Vite/Vitest/testing-library packages | Frontend app, build, and tests. |

S1 may remove only dependencies that pass import/test verification and are not needed by packaging or Windows scripts.

## Generated and Runtime Files That Should Stay Ignored

Current `.gitignore` covers:

- `__pycache__/`
- `*.pyc`
- `.DS_Store`
- `.venv/`
- `node_modules/`
- `frontend/dist/`
- `*.db`
- `.env`
- `uploads/`
- `logs/`
- `.venv-*`
- `backend/.venv-*`
- `/docs/First sign-in credentials.txt`

Additional ignore candidates for S1:

| Candidate | Reason |
|---|---|
| `*.sqlite`, `*.sqlite3` | Runtime SQLite default is `clinical-notes-analyzer.sqlite3`; `*.db` alone is incomplete. |
| `coverage/`, `.coverage`, `htmlcov/` | Common Python coverage output. |
| `frontend/coverage/` | Common Vitest coverage output if enabled. |
| `*.log` | Local logs should not be tracked. |
| `*.tmp`, `*.bak` | Local/generated scratch files. |
| Windows packaged build outputs | Add once installer/packaging paths are chosen. |

## Tracked Unsafe Artifact Check

Tracked scan did not show `.env`, runtime SQLite DBs, upload directories, log directories, `node_modules`, `frontend/dist`, or credential note files. It did show `.env.example`, which is a placeholder template and currently safe as long as placeholder secrets remain non-production.

`docs/First sign-in credentials.txt` exists locally but is ignored and untracked. Do not commit it.

## Untracked Local Artifacts

| Artifact | Status | Assessment |
|---|---|---|
| `Product Requirements Document.docx` | Untracked at repo root | Likely duplicate or legacy source artifact. Do not delete without comparing to tracked PRD docs. Candidate for moving into docs or ignoring/removing in S1. |
| `walkthroughs/` | Untracked directory with PDFs, transcripts, screenshots, screenshot zips | Likely local evidence/reference material. It may contain screenshots or transcript content that should be reviewed for PHI before any commit. Do not delete or commit in S0. |

## Deletion Safety Assessment

Safe to remove in S1 only after re-verification:

- Generated caches and build artifacts if present and untracked: `__pycache__/`, `.pytest_cache/`, `frontend/dist/`, `node_modules/`, coverage output, local logs, local DB files.
- Duplicate root PRD document if it is byte/content-confirmed superseded by tracked docs and contains no unique needed content.
- Stale docs/scripts only after README/docs/tests/launchers no longer reference them and the replacement path is documented.

Not safe to remove yet:

- Any backend/frontend source, tests, current docs, rules config, launch scripts, Docker/CI files, or sample clinical notes.
- Server-mode scripts until product scope explicitly drops Docker/server support.
- Historical PRD and prompt docs until archive policy is set.
- Untracked `walkthroughs/` until content is reviewed and the user decides whether to keep, ignore, archive, or delete.
- Ignored credentials note. It should remain untracked and local; do not edit or commit it.

## Files Not Safe to Delete and Why

| File/path | Why |
|---|---|
| `backend/app/services/secure_storage.py` | Required for encrypted upload and secret envelope storage. |
| `backend/app/services/audit.py` | Required for forensic logging and hash-chained audit records. |
| `backend/app/services/rules_engine.py` | Required deterministic rules engine. |
| `config/rules/alleva_treatment_plan_completeness_rules.yaml` | Current rules config and seed for v0.5.0 timeliness work. |
| `backend/tests/` | Required backend safety net. |
| `frontend/src/App.test.tsx` | Required frontend workflow safety net. |
| `scripts/Start-IZ-Clinical-Notes-Analyzer.cmd` | Ordinary Windows entrypoint. |
| `scripts/startup-windows-local.ps1` | Ordinary Windows source-checkout startup. |
| `scripts/test-*.ps1` | Windows validation and API harness smoke coverage. |
| `docs/sample-clinical-notes/` | Synthetic examples for testing/docs; keep synthetic-only. |
| `docs/prd-treatment-plan-timeliness-mvp-2026-06-01.md` | Authoritative MVP PRD for v0.5.0 work. |
| `.github/workflows/ci.yml` | CI validation. |

## S1 Recommendations

1. Update `.gitignore` for SQLite, coverage, logs, and package/build outputs before cleanup.
2. Create `docs/removal-log.md` before deleting anything.
3. Compare the untracked root `Product Requirements Document.docx` with tracked PRD artifacts and decide keep/move/delete/ignore.
4. Review `walkthroughs/` for PHI and decide whether it is local-only evidence, archive material, or safe synthetic documentation.
5. Classify `scripts/startup-windows.ps1` as legacy/server-mode or remove it after references and product scope are resolved.
6. Review `docker-compose.db-expose.yml` and either document it or remove it if truly unused.
7. Consolidate settings/API secret storage so every saved API key/secret uses the encrypted text envelope and browser payloads only return configured flags.
8. Keep `docs/open-blockers.md`, README, and PRD implementation notes current until the unvalidated LOC-change window is resolved.
