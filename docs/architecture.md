# Chart Review Workflow Architecture

## Stack
- Frontend: React + TypeScript (Vite)
- Backend: FastAPI + SQLAlchemy
- Database: PostgreSQL (SQLite fallback for local quick start)
- Deployment: Docker Compose local, VPS-ready via reverse proxy + systemd/docker

## Core modules
- Authentication + RBAC (`admin`, `counselor`, `manager`)
- Chart workflow management with guarded transitions
- Forensic audit logging with hash-chained events
- Upload endpoint for Alleva-exported files

## Port configuration
- Backend listens on `PORT` env var (default `8000`)
- Frontend externally published on `FRONTEND_PORT` (default `5173`)
- Postgres externally published on `POSTGRES_PORT` (default `5432`)

All ports are configurable via `.env` + `docker-compose.yml` variable interpolation.
