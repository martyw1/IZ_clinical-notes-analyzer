# Windows local refactor notes

## Goal

The local clinic runtime should work on ordinary Windows 10 and Windows 11 consumer machines without Docker, PostgreSQL, or unusual manual prerequisites for the end user. The app should run locally, check its runtime environment, persist audit logs, and execute deterministic completeness rules before any future LLM analysis is added.

## Current refactor direction

- Default database mode is now SQLite for local desktop use.
- PostgreSQL remains available for developer/server scenarios, but it is no longer the default local runtime.
- The app-data folder is the default persistent location for the local database, uploads, logs, and generated environment file.
- The Treatment Plan Tracking rules are now external YAML configuration under `config/rules/`.
- The deterministic rules engine is separated from the older binder evaluation code.
- The rules engine does not call an LLM.
- Runtime checks now include database configuration, database connectivity, YAML parser availability, rules config validation, storage checks, encryption checks, and dependency checks.
- A desktop FastAPI entrypoint exists at `backend/app/desktop_main.py` so desktop launch can include the rules API and optionally serve a built frontend from `frontend/dist`.

## Key files

| File | Purpose |
| --- | --- |
| `.env.example` | Documents SQLite-first local defaults. |
| `backend/app/core/config.py` | Resolves local app-data paths, SQLite default, rules config path, and optional PostgreSQL settings. |
| `backend/app/services/rules_engine.py` | Deterministic YAML rules engine for Treatment Plan Tracking and future workflows. |
| `config/rules/alleva_treatment_plan_completeness_rules.yaml` | First Treatment Plan Tracking rules configuration. |
| `backend/app/api/rules_routes.py` | Authenticated rules profile and rules evaluation API boundary. |
| `backend/app/desktop_main.py` | Desktop runtime app entrypoint. |
| `backend/app/services/runtime_checks.py` | Startup/readiness checks for dependencies, local database, storage, encryption, and rules. |
| `backend/tests/test_rules_engine.py` | Unit tests for the first rules workflow. |
| `scripts/test-local-app-stack.ps1` | Source-checkout local full stack smoke test. |
| `scripts/test-alleva-api-connectivity.ps1` | Swagger/OpenAPI/API reachability probe for Alleva connectivity. |
| `scripts/start-windows-local.ps1` -> `scripts/startup-windows-local.ps1` | Current source-checkout desktop runtime starter path. The older `scripts/start-desktop-local.ps1` was moved to `depricated/scripts/start-desktop-local.ps1` as legacy archive history. |

## Recommended Windows developer test flow

From PowerShell in the repo root:

```powershell
.\scripts\test-local-app-stack.ps1
```

This creates a test SQLite database under `%LOCALAPPDATA%`, installs source-checkout dependencies into `backend/.venv`, runs backend tests, starts the local API, checks health/readiness, logs in as the generated test admin, and calls `/api/users/me`.

To probe Alleva API documentation/connectivity:

```powershell
.\scripts\test-alleva-api-connectivity.ps1 -WriteJsonReport
```

Do not commit Alleva credentials. If credentials are required for protected endpoints, pass them through environment variables such as `ALLEVA_API_BEARER_TOKEN` or `ALLEVA_API_KEY`.

## Recommended packaged runtime direction

The final non-technical user experience should be a packaged Windows release folder containing:

- one visible double-click launcher
- one packaged Python runtime or PyInstaller executable
- built frontend assets
- the YAML rules config
- no Docker Desktop dependency
- no PostgreSQL dependency
- all persisted local runtime data under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`

The source checkout scripts are not a substitute for the final packaged release, but they establish the no-Docker runtime architecture.

## Guardrails

- Do not log PHI in script output or app logs beyond necessary internal audit metadata.
- Do not put PHI in YAML rules files.
- Do not commit Alleva credentials, API keys, bearer tokens, or patient exports.
- Keep future LLM text analysis explicitly optional and separate from deterministic v1 completeness scoring.
