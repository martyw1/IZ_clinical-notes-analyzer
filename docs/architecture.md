# Architecture Overview

IZ Clinical Notes Analyzer is a React + FastAPI + PostgreSQL application for enterprise chart review workflows.

## Runtime components
- **Frontend**: React/Vite app served via nginx in Docker.
- **Backend**: FastAPI app with JWT auth, RBAC, workflow state controls, uploads, and audit logging.
- **Database**: PostgreSQL (internal Docker service or external/shared PostgreSQL).

## Database connectivity model
Configuration is explicit and deterministic:
- `DATABASE_URL`: canonical DSN (defaults to host-local `127.0.0.1` for non-Docker runs).
- `USE_INTERNAL_POSTGRES`: enables/disables internal Compose Postgres profile.
- `DATABASE_HOST_MODE`:
  - `internal`: rewrite localhost DB host to `db` inside containers.
  - `host`: rewrite localhost DB host to `host.docker.internal` inside containers.
  - `external`: do not rewrite host.

Linux containers resolve `host.docker.internal` via Compose `extra_hosts: host-gateway`.

## Health model
- `/health` for direct infra probes.
- `/api/health` for API/proxy-friendly probes.
