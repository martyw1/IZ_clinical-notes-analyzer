# Deprecated File Manifest

Date: 2026-06-11

This folder contains files removed from the active Version 1 app path because the product direction is Windows local-first. Normal R3 Windows use does not require Docker, Docker Compose, PostgreSQL containers, or nginx container serving.

## Cleanup entries

| Original path | New path / recovery path | Reason moved or removed from active path | Replacement / current source of truth | Validation note |
|---|---|---|---|---|
| `docker-compose.yml` | `deprecated/docker-compose.yml` | Docker Compose stack is no longer needed for the normal Windows local-first app path. | Windows local launcher and scripts: `scripts/Start-IZ-Clinical-Notes-Analyzer.cmd`, `scripts/startup-windows-local.ps1`, `scripts/preflight-windows.ps1`. | Active root file removed on 2026-06-11. Original content archived here. |
| `backend/Dockerfile` | `deprecated/backend/Dockerfile` | Backend container build is no longer needed for the normal Windows local-first app path. | Windows local backend runtime using `backend/.venv` and `backend/requirements-windows-local.txt`. | Archived copy created on 2026-06-11; active deletion was attempted but blocked by connector safety checks and should be completed locally if still present. |
| `frontend/Dockerfile` | Git history; summary note at `deprecated/frontend/Dockerfile.md` | Frontend container build is no longer needed for the normal Windows local-first app path. | Built frontend assets via `frontend` npm workflow and Windows preflight stale-build detection. | Connector blocked verbatim archived copy; recover original from Git history if needed. Active deletion should be completed locally if still present. |
| `frontend/nginx.conf` | Git history | Docker/nginx reverse-proxy config is no longer needed for the normal Windows local-first app path. | FastAPI desktop app serves the built frontend at `http://localhost:8000`; Vite dev server is optional for development. | Connector blocked archived copy/note; recover original from Git history if needed. Active deletion should be completed locally if still present. |

## Validation still required locally

Because this cleanup was made through the GitHub connector rather than a local Windows checkout, run the following locally after pulling latest `main`:

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

Then remove any remaining active Docker-specific files that the connector could not delete, confirm no active docs point ordinary Windows users to Docker, and commit the final local cleanup.
