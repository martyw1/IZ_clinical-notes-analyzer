# Deprecated Files Manifest

Date created: 2026-06-11

This folder contains files moved out of the active application path because Version 1 is now focused on the local-first Windows desktop runtime. These files are preserved for rollback/history and must not be treated as active deployment instructions. The folder name is intentionally `depriceated/` to match the 2026-06-11 PRD.

Normal R3 Windows use does not require Docker, Docker Compose, PostgreSQL containers, or nginx container serving.

## Files moved

| Original path | New path | Date moved | Reason moved | Replacement / current source of truth | Validation |
|---|---|---|---|---|---|
| `docker-compose.yml` | `depriceated/docker-compose.yml` | 2026-06-11 | Docker/PostgreSQL stack is no longer needed for the active Version 1 Windows desktop path and was confusing for non-technical Windows users. | Windows local desktop launch through `scripts/Start-IZ-Clinical-Notes-Analyzer.cmd`, `scripts/startup-windows-local.ps1`, SQLite runtime, and Windows docs. | Active original path verified absent from this branch after move. Full local validation is recorded in `docs/validation/validation-report-2026-06-11-treatment-plan-prd-42.md`. |
| `backend/Dockerfile` | `depriceated/backend/Dockerfile` | 2026-06-11 | Backend container build is no longer part of the active Version 1 Windows desktop path. | Backend local virtual environment and Windows startup/preflight scripts. | Active original path verified absent from this branch after move. Full local validation is recorded in `docs/validation/validation-report-2026-06-11-treatment-plan-prd-42.md`. |
| `frontend/Dockerfile` | `depriceated/frontend/Dockerfile` | 2026-06-11 | Frontend container/nginx build is no longer part of the active Version 1 Windows desktop path. | React/Vite build into `frontend/dist` served by the local FastAPI desktop runtime. | Active original path verified absent from this branch after move. Full local validation is recorded in `docs/validation/validation-report-2026-06-11-treatment-plan-prd-42.md`. |
| `frontend/nginx.conf` | `depriceated/frontend/nginx.conf` | 2026-06-11 | This nginx config only supported the deprecated frontend Docker image. | Local FastAPI desktop runtime serving built frontend assets. | Active original path verified absent from this branch after move. Full local validation is recorded in `docs/validation/validation-report-2026-06-11-treatment-plan-prd-42.md`. |

## Validation still required locally

Run the following locally after changes that touch launch/runtime files:

```powershell
git status
.\scripts\preflight-windows.ps1 -AssumeYes
.\scripts\test-local-app-stack.ps1
.\scripts\test-api-configuration-local.ps1
cd frontend
npm test -- --run
npm run build
cd ..
.\backend\.venv\Scripts\python.exe -m pytest backend\tests -q
```

## Notes

- These files were moved, not permanently deleted, so the old Docker approach can be inspected if needed.
- Do not restore these files to active paths unless R3 explicitly reintroduces Docker/server deployment as a supported target and updates README, Windows docs, tests, and release instructions accordingly.
- The active product path is local-first Windows desktop use, with runtime data under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer` and normal app access at `http://localhost:8000`.
