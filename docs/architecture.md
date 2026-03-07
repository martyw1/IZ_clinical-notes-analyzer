# Architecture Overview

IZ Clinical Notes Analyzer is a React + FastAPI + PostgreSQL application for enterprise chart review workflows.

## Runtime components
- **Frontend**: React/Vite app served via nginx in Docker.
- **Backend**: FastAPI app with JWT auth, RBAC, workflow state controls, uploads, and audit logging.
- **Database**: Dedicated PostgreSQL service owned by this application and managed through Docker Compose.

## Database connectivity model
Configuration is explicit and deterministic:
- `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD` define the dedicated application database.
- `DATABASE_URL` is optional; when omitted, the backend assembles the DSN from the component settings.
- Backend containers automatically rewrite host-local Postgres URLs to the internal Compose `postgres` service.
- Startup scripts provision the dedicated application database before the backend starts, so the VPS deployment does not depend on any shared PostgreSQL service.

## Health model
- `/health` for direct infra probes.
- `/api/health` for API/proxy-friendly probes.
