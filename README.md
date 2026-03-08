# IZ Clinical Notes Analyzer (Chart Review Workflow)

Enterprise-oriented clinical chart review workflow with secure authentication, RBAC, workflow state controls, uploads, and audit logging.

The app now runs against its own dedicated PostgreSQL service in every supported environment. It no longer depends on a shared VPS PostgreSQL instance.

## Health endpoints
- `GET /health`
- `GET /api/health`

## Dedicated PostgreSQL configuration
Key env vars:
- `COMPOSE_PROJECT_NAME` (default: `iz_clinical_notes_analyzer`, keeps containers/networks/volumes isolated from other apps)
- `DATABASE_HOST` (default: `127.0.0.1` for host-local backend runs)
- `DATABASE_PORT` (host-visible dedicated Postgres port; defaults to `5432`)
- `DATABASE_NAME` (default: `iz_clinical_notes_analyzer`)
- `DATABASE_USER` (default: `iz_clinical_notes_app`)
- `DATABASE_PASSWORD` (default: `change-me-app`)
- `POSTGRES_PORT` (host port published by the dedicated Docker Postgres service)
- `DATABASE_URL` is optional; when omitted, the backend builds its own DSN from `DATABASE_*`

Behavior inside the Docker backend container:
- Host-local DB URLs are automatically rewritten from `127.0.0.1`/`localhost` to the dedicated Compose `postgres` service.
- The Ubuntu/macOS/Windows startup scripts start the dedicated Postgres container first and create the application database if it is missing.
- The backend rejects non-local PostgreSQL hosts so an old shared-VPS DSN cannot survive this startup path.


## Default login credentials
- Username: `admin`
- Password: `r3!@analyzer#123`

Bootstrap credential settings (backend env vars):
- `BOOTSTRAP_ADMIN_USERNAME` (default: `admin`)
- `BOOTSTRAP_ADMIN_PASSWORD` (default: `r3!@analyzer#123`)
- `RESET_BOOTSTRAP_ADMIN_ON_STARTUP` (default: `true` in non-production to keep demo credentials working and unlock the bootstrap account)

## Docker run
```bash
cp .env.example .env
# Dedicated app-owned Postgres + backend + frontend
docker compose up -d --build
./scripts/smoke.sh
```

## Local development (without Docker)
Start the dedicated local Postgres container first:

```bash
cp .env.example .env
docker compose up -d postgres
```

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export PYTHONPATH=$(pwd)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm install
VITE_API_URL=http://localhost:8000/api npm run dev
```

## Startup scripts
- Ubuntu: `./scripts/startup-ubuntu-24.04.sh`
- macOS: `./scripts/startup-macos.sh`
- Windows: `./scripts/startup-windows.ps1`

All startup scripts normalize `.env` to the dedicated Postgres configuration, start the dedicated database service first, and ensure the application database exists before the backend starts.

## Testing
```bash
cd backend && PYTHONPATH=$(pwd) pytest
cd frontend && npm test
cd frontend && npm run build
```
