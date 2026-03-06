# IZ Clinical Notes Analyzer (Chart Review Workflow)

Enterprise-oriented clinical chart review workflow with secure authentication, role-based permissions, workflow state controls, and forensic audit logging.

## What is currently implemented

### Backend (FastAPI + SQLAlchemy)
- JWT-style bearer-token authentication (`/api/auth/login`).
- Forced first-login password reset (`must_reset_password`) via `/api/auth/reset-password`.
- Account lockout after repeated failed login attempts.
- RBAC roles: `admin`, `counselor`, `manager`.
- Role-aware chart access:
  - counselors only see their own charts,
  - elevated roles can see broader chart sets.
- Chart creation and guarded workflow transitions.
- Transition validation with role + state rules.
- Return transitions require a non-empty comment.
- Multi-file upload metadata ingestion endpoint (`/api/uploads`).
- Tamper-evident audit logs with hash chaining.
- Admin-only audit retrieval endpoint (`/api/audit/logs`).
- Health endpoint (`/health`).

### Frontend (React + Vite)
- Login screen with detailed HTTP-aware error messages.
- Explicit auth lifecycle states:
  - anonymous,
  - logging in,
  - authenticated/loading profile,
  - password reset required,
  - authenticated/ready,
  - error.
- Forced password reset screen before dashboard access.
- Persistent status banner for current system/session status.
- Role-labeled dashboard (admin/counselor view title).
- Table-based chart listing.
- “Create sample chart” action for authenticated users with allowed role.
- Header branding: `r3recoveryservices.com`.

---

## Default seeded account
- Username: `admin`
- Password: `r3`
- On first login, the user is flagged for required password reset.

---

## API summary

Base prefix: `/api`

### Auth
- `POST /api/auth/login`
- `POST /api/auth/reset-password`
- `GET /api/users/me`

### User administration
- `POST /api/users` (admin only)

### Charts
- `GET /api/charts`
- `POST /api/charts` (counselor/admin)
- `POST /api/charts/{chart_id}/transition`

### Uploads and audits
- `POST /api/uploads`
- `GET /api/audit/logs` (admin only)

### Health
- `GET /health`

---

## Workflow states and transition behavior

### States
- `draft`
- `submitted`
- `in_progress`
- `returned`
- `completed`
- `verified`

### Allowed transitions by role
- **Counselor**
  - `draft -> submitted`
  - `returned -> submitted`
- **Admin**
  - `submitted -> in_progress` or `returned`
  - `in_progress -> completed` or `returned`
  - `completed -> verified`
- **Manager**
  - `submitted -> in_progress`
  - `completed -> verified`

If a target state is not allowed for the caller’s role/current state, the API returns `400`.

---

## Local development run (without Docker)

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

Open: `http://localhost:5173`

---

## Docker run

```bash
cp .env.example .env
docker compose up -d --build
./scripts/smoke.sh
```

Open: `http://localhost:${FRONTEND_PORT:-5173}`

Notes:
- In Docker mode, frontend `/api` calls are proxied to backend.
- Default local fallback DB URL (when env not set) is PostgreSQL on `127.0.0.1:5432`.
- Use least-privilege DB credentials for real environments.

Optional host PostgreSQL exposure for debug/admin tooling:
```bash
docker compose -f docker-compose.yml -f docker-compose.db-expose.yml up -d
```

---

## One-command startup scripts

These scripts verify dependencies, prepare environment/runtime, launch Docker Compose services, and log into `logs/`.

- Windows PowerShell:
  ```powershell
  ./scripts/startup-windows.ps1
  ```
- macOS:
  ```bash
  ./scripts/startup-macos.sh
  ```
- Ubuntu 24.04:
  ```bash
  ./scripts/startup-ubuntu-24.04.sh
  ```

Run under lower-privilege Linux account example:
```bash
sudo -u demo-run -g demoapps /bin/bash -lc "cd /home/iz-admin/app/demo/iz/IZ_clinical-notes-analyzer && ./scripts/startup-ubuntu-24.04.sh --non-interactive"
```

---

## Testing

### Backend tests
```bash
cd backend
PYTHONPATH=$(pwd) pytest
```

### Frontend tests
```bash
cd frontend
npm test
```

---

## Security/operations notes
- Keep admin credentials out of screenshots/chats/email.
- Rotate demo passwords after sessions.
- Avoid real patient data in demo/non-production systems.
- For VPS deployment, run behind TLS reverse proxy (Nginx/Caddy) and schedule DB backups (`pg_dump`).

---

## Project docs
- Architecture: `docs/architecture.md`
- Runbook: `docs/runbook.md`
- QA plan: `docs/qa-plan.md`
- Build prompt/history: `docs/chart-review-workflow-codex-build-prompt.md`
