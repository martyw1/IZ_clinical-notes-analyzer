# IZ Clinical Notes Analyzer (Chart Review Workflow)

Enterprise-oriented clinical chart review workflow with secure authentication, RBAC, workflow state controls, uploads, and audit logging.

## Health endpoints
- `GET /health`
- `GET /api/health`

## Database configuration
Key env vars:
- `DATABASE_URL` (default host-local): `postgresql+psycopg2://iz_clinical_notes:change-me@127.0.0.1:5432/iz_clinical_notes_analyzer`
- `USE_INTERNAL_POSTGRES=1|0`
- `DATABASE_HOST_MODE=internal|host|external`

Behavior inside Docker backend container:
- `internal`: localhost DB host rewrites to `db` (internal Compose Postgres).
- `host`: localhost DB host rewrites to `host.docker.internal` (shared PostgreSQL on Docker host/VPS).
- `external`: explicit non-local DB hosts are used as-is.

## Docker run
```bash
cp .env.example .env
# Internal DB mode (default)
docker compose --profile internal-db up -d --build
./scripts/smoke.sh
```

### External/shared DB mode
Set `.env`:
- `USE_INTERNAL_POSTGRES=0`
- `DATABASE_HOST_MODE=host` (for host DB) or `external` (for remote DB)
- `DATABASE_URL` to your target DB credentials/host

Then run:
```bash
docker compose up -d --build
./scripts/smoke.sh
```

## Local development (without Docker)
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

All scripts honor `USE_INTERNAL_POSTGRES` and `DATABASE_HOST_MODE`; none auto-rewrite DB credentials.

## Testing
```bash
cd backend && PYTHONPATH=$(pwd) pytest
cd frontend && npm test
cd frontend && npm run build
```
