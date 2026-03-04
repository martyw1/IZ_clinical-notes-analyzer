# Chart Review Workflow

Enterprise-oriented clinical chart review workflow starter built from the project prompt.

## Features implemented
- RBAC auth for `admin`, `counselor`, `manager`
- Seed admin: `admin` / `r3` with forced password-reset flag
- Chart workflow states and role-gated transitions
- Tamper-evident audit logs (hash chaining)
- Upload endpoint for multi-file ingestion metadata logging
- React dashboard UI with persistent status banner and `r3recoveryservices.com` header branding
- Dockerized local deployment with PostgreSQL

## Local run (without Docker)
### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export PYTHONPATH=$(pwd)
export PORT=8000
uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
```

### Frontend
```bash
cd frontend
npm install
VITE_API_URL=http://localhost:8000/api npm run dev
```

## Docker local run
```bash
cp .env.example .env
docker compose up --build
```

## VPS deployment notes
1. Install Docker and Docker Compose plugin.
2. Copy project to VPS and configure `.env` ports and secrets.
3. Start with `docker compose up -d --build`.
4. Put Nginx/Caddy in front for TLS and domain routing.
5. Persist Postgres volume and schedule `pg_dump` backups.

## Configurable listening ports
- Backend listens using `PORT` env var.
- Docker maps `${BACKEND_PORT}` to backend `PORT`.
- Frontend published on `${FRONTEND_PORT}`.

## Test
```bash
cd backend
PYTHONPATH=$(pwd) pytest
```
