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

Then open the app in your browser at `http://localhost:5173`.

## Docker local run
```bash
cp .env.example .env
docker compose up --build
```

Then open the app in your browser at `http://localhost:${FRONTEND_PORT:-5173}` (default is usually `5173`).

---

## Non-technical quick start (recommended)
If you are not a developer, follow this exact checklist:

1. **Start the app**
   - Use one of the startup scripts in this README (`startup-windows.ps1`, `startup-macos.sh`, or `startup-ubuntu-24.04.sh`).
   - Wait until you see messages that backend/frontend are running.
2. **Open the sign-in page**
   - In a browser, go to `http://localhost:5173`.
3. **Log in as the admin user**
   - Username: `admin`
   - Password: `r3`
   - If prompted, complete password reset.
4. **Confirm the app loaded**
   - You should see a status banner and dashboard heading.
5. **Stop the app when done**
   - In the terminal running the app, press `Ctrl + C`.

---

## Running as **iz-admin** while testing with **demo-run** (lower privileges)

This workflow lets a supervisor stay logged in as admin while separately validating what a lower-privilege user can do.

### Why this matters
- Admin accounts can do more than standard users.
- For realistic testing/training, use a reduced-permission account (`demo-run`) for normal operations.
- Keeping both sessions open helps compare “what admin can do” vs “what standard staff can do.”

### Step 1: Prepare accounts
By default, the seeded admin account is:
- Username: `admin` (treat this as your **iz-admin** session)
- Password: `r3`

Create the `demo-run` account once (admin-only action):

1. Log in to the app as `admin`.
2. In a second terminal, run:

```bash
curl -X POST http://localhost:8000/api/users \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"username":"demo-run","password":"demo-run-pass","role":"counselor"}'
```

How to get `<ADMIN_TOKEN>` quickly:

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"r3"}'
```

Copy the `access_token` value from the response and paste it into the create-user command above.

> If `demo-run` already exists, you may receive a `409 Username exists` response; that is expected.

### Step 2: Keep admin logged in, open a separate lower-privilege session
Use **two browser sessions**:

- **Window A (normal browser profile):** log in as `admin` (**iz-admin** session).
- **Window B (Incognito/Private window):** log in as `demo-run` (lower privilege).

This prevents one login from replacing the other and is the easiest method for non-technical users.

### Step 3: Validate lower-privilege behavior in the `demo-run` session
In the `demo-run` window, verify:

- You can create/view only your own charts.
- You cannot access admin-only capabilities (for example, admin audit log endpoint).
- Workflow actions are limited by the counselor role.

### Step 4: Keep credentials safe
- Do not share admin credentials in screenshots, chat, or email.
- For demos, use temporary passwords and rotate them after sessions.
- Avoid using real patient data in demo environments.

## VPS deployment notes
1. Install Docker and Docker Compose plugin.
2. Copy project to VPS and configure `.env` ports and secrets.
3. Start with `docker compose up -d --build`.
4. Put Nginx/Caddy in front for TLS and domain routing.
5. Persist Postgres volume and schedule `pg_dump` backups.

## One-command startup scripts (with dependency checks + logging)
Use the platform-specific script from the repo root. Each script:
- verifies core dependencies,
- installs missing packages where supported,
- creates `.env` from `.env.example` when missing,
- prepares backend/frontend runtime dependencies,
- starts the stack with Docker Compose,
- writes detailed logs to `logs/`.

### Windows (PowerShell)
```powershell
./scripts/startup-windows.ps1
```

### macOS
```bash
./scripts/startup-macos.sh
```

### Ubuntu 24.04 (local or VPS)
```bash
./scripts/startup-ubuntu-24.04.sh
```

Run the same script under the lower-privilege `demo-run` Linux account:
```bash
sudo -iu demo-run bash -lc 'cd /home/iz-admin/app/demo/iz/IZ_clinical-notes-analyzer && ./scripts/startup-ubuntu-24.04.sh'
```

## Configurable listening ports
- Backend listens using `PORT` env var.
- Docker maps `${BACKEND_PORT}` to backend `PORT`.
- Frontend published on `${FRONTEND_PORT}`.

## Test
```bash
cd backend
PYTHONPATH=$(pwd) pytest
```
