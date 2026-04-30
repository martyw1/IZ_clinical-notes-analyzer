# IZ Clinical Notes Analyzer

IZ Clinical Notes Analyzer is a chart-review application for clinical note binders. It combines a React frontend, a FastAPI backend, and a dedicated PostgreSQL database to support uploads, automated checklist scoring, office-manager review, role-based access control, and forensic-style audit logging.

## What this app does

- Accepts clinical note binder uploads grouped by `patient_id`
- Auto-detects `patient_id` from uploaded files when possible
- Creates an immutable versioned note set for every upload/update
- Generates an automated review chart from the uploaded binder
- Lets reviewers confirm, reject, or mark checklist items as not applicable
- Supports office-manager approval or return-to-counselor workflow
- Keeps tamper-evident forensic audit logs for reads, writes, auth, downloads, and workflow changes
- Stores uploaded source files encrypted at rest with SHA-256 digests for later validation
- Includes a readiness screen and startup checks for required dependencies, writable private storage, parser support, and placeholder secrets
- Provides a SMART-on-FHIR/FHIR R4 EMR connector profile and import-plan stub for future EMR API work

## Who should use which section

- Non-technical users: start with [Quick Start For Non-Technical Users](#quick-start-for-non-technical-users)
- Developers: use [Local Development](#local-development)
- Server operators: use [VPS Deployment](#vps-deployment) and [Troubleshooting](#troubleshooting)

## Quick Start For Non-Technical Users

If you just need to start the app and use it, use one of the startup scripts. They create `.env` if needed, prepare dependencies, start the database first, launch the app, and run a smoke test.

### macOS

1. Open Terminal in this project folder.
2. Run:

```bash
./scripts/startup-macos.sh
```

3. If asked, choose ports for the frontend, backend, and database.
4. Wait for the script to finish and open the frontend URL it prints, usually `http://localhost:5173`.

### Windows

1. Open PowerShell in this project folder.
2. Run:

```powershell
.\scripts\startup-windows.ps1
```

3. Wait for the script to finish and open `http://localhost:5173` unless you changed the port.

### Ubuntu 24.04 or VPS

1. SSH into the server and open this project folder.
2. Run:

```bash
./scripts/startup-ubuntu-24.04.sh
```

3. Wait for the smoke test to pass.
4. Open the frontend on the configured `FRONTEND_PORT`.

### First sign-in

- Username: value of `BOOTSTRAP_ADMIN_USERNAME` in `.env`
- Password: value of `BOOTSTRAP_ADMIN_PASSWORD` in `.env`
- Default bootstrap username: `admin`
- Startup scripts replace placeholder `DATABASE_PASSWORD`, `SECRET_KEY`, `DATA_ENCRYPTION_KEY`, and `BOOTSTRAP_ADMIN_PASSWORD` with strong local random values.
- The generated `.env.example` still shows placeholders so operators can see which values exist.

The bootstrap admin password is managed outside the app and is reset from `.env` on startup when `RESET_BOOTSTRAP_ADMIN_ON_STARTUP=true`.

## Simple User Instructions

### Counselor or uploader

1. Sign in.
2. Open `Upload clinical notes`.
3. Enter the `patient_id`, or leave it blank and let the app try to detect it from the files.
4. Add the clinical note files and their metadata.
5. Submit the upload.
6. The app creates a binder, stores the files, and generates an automated review chart.

### Reviewer or manager

1. Open `Review queue`.
2. Select the patient chart.
3. Read the system summary and checklist results.
4. Confirm or correct the checklist items.
5. Approve the chart or return it with a comment.

### Administrator

Admins can also:

- create and manage users
- unlock users or require password reset
- review forensic logs
- update app settings for access-intel, LLM analysis, and EMR API connector registration
- review `System readiness` from the Settings/dashboard area

## How The App Runs

### Runtime services

The normal runtime is Docker Compose with three services:

| Service | Purpose | Default exposed port |
| --- | --- | --- |
| `frontend` | Serves the React app through nginx and proxies `/api/*` to the backend | `127.0.0.1:5173` |
| `backend` | FastAPI API, auth, workflow, uploads, audit logging, schema bootstrap | `127.0.0.1:8000` |
| `postgres` | Dedicated application-owned PostgreSQL database | `127.0.0.1:5432` |

### Startup sequence

When you use one of the startup scripts, the app starts in this order:

1. Create `.env` from `.env.example` if it does not exist.
2. Normalize or choose ports.
3. Fill in dedicated database settings in `.env`.
4. Generate strong local secrets if `.env` still contains placeholders.
5. Start the `postgres` container first.
6. Ensure the application database exists and is owned by the configured database user.
7. Start the full Docker Compose stack.
8. Let the backend:
   - run dependency and runtime readiness checks
   - wait for the database
   - add missing legacy columns with defensive schema compatibility checks
   - create tables if needed
   - create or reset the bootstrap admin account
9. Run a smoke test to verify the frontend, API health, login, and chart loading path.

### Health endpoints

- `GET /health`
- `GET /api/health`

### Default URLs

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- Backend through frontend proxy: `http://localhost:5173/api`
- PostgreSQL: `127.0.0.1:5432`

## Architecture

```mermaid
flowchart LR
    Browser["User Browser"] --> Frontend["React + Vite UI\nserved by nginx"]
    Frontend -->|"/api"| Backend["FastAPI API"]
    Backend --> DB["PostgreSQL"]
    Backend --> Uploads["encrypted app-data uploads\nmacOS/Windows local storage\nDocker backend_data volume"]
    Backend --> Audit["audit_logs table\n+ fallback JSONL log"]
    Backend --> Access["Access-intel providers\n(ipwho.is / AbuseIPDB)"]
    Backend --> LLM["OpenAI-compatible LLM endpoint\n(optional)"]
```

### Frontend

- Single-page React app in `frontend/src/App.tsx`
- Built with Vite and served by nginx in Docker
- Uses `/api` by default, so the browser usually talks only to the frontend host
- Main views:
  - summary dashboard
  - review queue
  - upload clinical notes
  - profile
  - user management
  - forensic logs
  - settings

### Backend

The FastAPI backend is responsible for:

- JWT login and password-reset flows
- role-based access control
- chart creation and workflow transitions
- patient note set uploads and file downloads
- automatic checklist evaluation
- access-intelligence lookups during login
- optional OpenAI-compatible LLM gap analysis
- forensic request and database audit logging

Key backend files:

- `backend/app/main.py`: app creation, CORS, health routes, startup bootstrap, request audit middleware
- `backend/app/api/routes.py`: API routes and role checks
- `backend/app/core/config.py`: settings and database URL rules
- `backend/app/db/session.py`: SQLAlchemy engine/session setup and Docker DB host rewriting
- `backend/app/db/bootstrap.py`: defensive schema compatibility layer
- `backend/app/services/evaluation.py`: automatic checklist scoring from uploaded binder contents
- `backend/app/services/patient_notes.py`: upload storage, text extraction, file validation, patient ID detection
- `backend/app/services/audit.py`: request logging, event logging, DB change capture, fallback audit spool

### Database and storage model

Main tables:

- `users`
- `app_settings`
- `charts`
- `audit_item_responses`
- `workflow_transitions`
- `patient_note_sets`
- `patient_note_documents`
- `audit_logs`

File storage:

- Uploaded files are encrypted at rest before they are written to disk.
- Local desktop runs store uploads under the operating system app-data folder:
  - macOS: `~/Library/Application Support/IZ Clinical Notes Analyzer/uploads`
  - Windows: `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\uploads`
- Docker runs store uploads in the named `backend_data` volume at `/app/data/uploads`.
- Storage is organized by sanitized `patient_id`, note set ID, and document ID.
- Every stored file records:
  - original filename
  - content type
  - size in bytes
  - SHA-256 digest

### Workflow model

The main workflow is:

1. A counselor or uploader creates a patient note binder.
2. The backend stores the files and metadata.
3. The backend generates an automated evaluation report.
4. A chart is created and moved into `Awaiting Office Manager Review`.
5. A manager or admin reviews, approves, or returns the chart.
6. Every step is written to the forensic audit log.

### Optional external integrations

- Access intelligence:
  - geolocation lookup via `ipwho.is`
  - reputation lookup via AbuseIPDB
- LLM analysis:
  - any OpenAI-compatible `/chat/completions` endpoint
  - used for access-review summarization and evaluation gap analysis when enabled in app settings

## Current App Behavior

### Roles

- `admin`
  - full access
  - can manage users, settings, logs, charts, and uploads
- `manager`
  - can review charts and patient note sets
  - can approve or return charts
- `counselor`
  - can upload note sets
  - can view only their own charts and uploads

### Password behavior

- Managed users can be forced to reset passwords.
- Accounts lock after 5 failed login attempts.
- The bootstrap admin password cannot be changed in-app.
- If `RESET_BOOTSTRAP_ADMIN_ON_STARTUP=true`, the bootstrap admin is reset from `.env` on every startup.

### Binder versioning

- Initial upload requires `upload_mode=initial`
- Later changes require `upload_mode=update`
- Updates do not overwrite history
- The prior note set becomes `superseded`
- The new upload becomes the active immutable version

### File rules

- Supported file extensions:
  - `.csv`
  - `.doc` (stored securely; text extraction requires converting to DOCX/PDF/TXT first)
  - `.docx`
  - `.jpeg`
  - `.jpg`
  - `.pdf`
  - `.png`
  - `.rtf`
  - `.txt`
  - `.zip`
- Per-file limit: `50MB`
- Total binder upload limit: `250MB`
- Maximum files per binder upload: `40`
- Patient ID auto-detection scans filenames and readable file contents up to a smaller detection limit
- New uploads are encrypted before they are written to disk. Downloads are decrypted only after auth/RBAC checks pass.

### Local data storage

- Host-side runs store relative `UPLOAD_DIR` and `LOG_DIR` under the operating system's local app-data folder, not the OneDrive-backed repo.
  - macOS: `~/Library/Application Support/IZ Clinical Notes Analyzer`
  - Windows: `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`
- Docker Compose stores backend uploads and fallback logs in the `BACKEND_DATA_VOLUME_NAME` Docker volume.
- Runtime readiness warns if upload storage appears to be inside OneDrive, iCloud, Dropbox, or Google Drive.

### EMR API readiness

The app is upload-first today, but it now has a standards-aligned EMR connector boundary:

- Admin settings store the EMR vendor label, FHIR base URL, SMART client ID/secret, scopes, and timeout.
- `GET /api/emr/profile` reports the configured SMART/FHIR profile.
- `POST /api/emr/discover` validates SMART `.well-known/smart-configuration` discovery when a real EMR FHIR base URL is available.
- `GET /api/emr/import-plan?patient_id=...` shows the planned FHIR R4 `Patient`, `DocumentReference`, `Binary`, and optional `Provenance` request flow.
- Alleva Document Manager exports are mapped to Custom Forms, Uploaded Documents, Portal Documents, Labs, Medications, Notes, or Other source buckets.
- SMART client secrets are stored through the local encrypted secret envelope instead of plaintext app settings.
- Alleva-specific live API import remains gated until the client/vendor provides official API credentials, tenant base URLs, attachment behavior, pagination/rate-limit rules, and documentation.

## Configuration

### Important environment variables

These are the settings you will use most often:

| Variable | Purpose | Default |
| --- | --- | --- |
| `BACKEND_PORT` | Host port for the FastAPI service | `8000` |
| `FRONTEND_PORT` | Host port for the nginx-served frontend | `5173` |
| `POSTGRES_PORT` | Host port for PostgreSQL | `5432` |
| `BACKEND_DATA_VOLUME_NAME` | Docker volume for encrypted uploads and fallback logs | `iz_clinical_notes_analyzer_backend_data` |
| `DATABASE_NAME` | Dedicated app database name | `iz_clinical_notes_analyzer` |
| `DATABASE_USER` | Dedicated app DB user | `iz_clinical_notes_app` |
| `DATABASE_PASSWORD` | Dedicated app DB password | placeholder in `.env.example` |
| `DATABASE_URL` | Optional full SQLAlchemy DSN override | blank |
| `SECRET_KEY` | JWT signing key | placeholder in `.env.example` / container fallback `change-me-in-production` |
| `DATA_ENCRYPTION_KEY` | File encryption key for uploaded clinical documents | placeholder in `.env.example` |
| `FRONTEND_ORIGIN` | Primary frontend origin | `http://localhost:5173` |
| `FRONTEND_ORIGINS` | Comma-separated allowed origins | `http://localhost:5173` |
| `ALLOWED_HOSTS` | Allowed backend host headers | `localhost,127.0.0.1,::1` |
| `BOOTSTRAP_ADMIN_USERNAME` | Bootstrap admin username | `admin` |
| `BOOTSTRAP_ADMIN_PASSWORD` | Bootstrap admin password | placeholder in `.env.example`; replace before VPS startup |
| `RESET_BOOTSTRAP_ADMIN_ON_STARTUP` | Reset bootstrap admin from `.env` every startup | `true` |
| `UPLOAD_DIR` | Upload storage directory; relative paths resolve to local app data | `uploads` |
| `LOG_DIR` | Fallback log directory; relative paths resolve to local app data | `logs` |
| `POSTGRES_SERVICE_HOST` | Docker-internal host name for Postgres | `postgres` |

### Database rules

- This app only supports its own isolated PostgreSQL instance.
- The backend rejects non-local/non-Compose PostgreSQL hosts.
- If `DATABASE_URL` uses `localhost` and the backend is running inside Docker, the backend rewrites the host to `postgres`.

## Local Development

### Full Docker stack

```bash
cp .env.example .env
docker compose up -d --build
./scripts/smoke.sh
```

### Backend only

Run PostgreSQL in Docker, then run the backend from your host:

```bash
cp .env.example .env
docker compose up -d postgres
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Frontend only

```bash
cd frontend
npm install
npm run dev
```

### Tests

```bash
backend/.venv/bin/python -m pytest backend/tests -q
cd frontend && npm test
cd frontend && npm run build
```

### Useful development commands

```bash
docker compose ps
docker compose logs --tail=200
docker compose logs --tail=200 backend
docker compose logs --tail=200 frontend
docker compose logs --tail=200 postgres
```

## VPS Deployment

The current server deployment model is the Ubuntu startup script plus Docker Compose. There is no separate deployment service in this repository.

### First-time VPS setup

1. Clone the repo to the server.
2. Create or review `.env`.
3. Change at least these values before going live:
   - `SECRET_KEY`
   - `DATA_ENCRYPTION_KEY`
   - `DATABASE_PASSWORD`
   - `BOOTSTRAP_ADMIN_PASSWORD`
   - `FRONTEND_ORIGIN`
   - `FRONTEND_ORIGINS`
4. Run:

```bash
./scripts/startup-ubuntu-24.04.sh
```

5. Confirm:
   - `docker compose ps`
   - `curl http://localhost:8000/health`
   - `curl http://localhost:<FRONTEND_PORT>/api/health`

### Updating the VPS after a code change

```bash
git pull
./scripts/startup-ubuntu-24.04.sh
```

The script pulls images where possible, ensures the DB exists, rebuilds containers, and reruns the smoke test.

### Restarting without redeploying

```bash
docker compose up -d
```

### Stopping the app

```bash
docker compose down
```

### Destructive reset

This deletes the PostgreSQL volume and all DB contents:

```bash
docker compose down -v
```

On Ubuntu there is also a helper path for auth-mismatch recovery:

```bash
RESET_DEDICATED_DB_VOLUME_ON_AUTH_FAILURE=1 ./scripts/startup-ubuntu-24.04.sh
```

Use that only if you intentionally want to recreate the dedicated database volume.

## Troubleshooting

### Docker starts but the site does not open

Check:

```bash
docker compose ps
docker compose logs --tail=200
```

Common causes:

- Docker Desktop or Docker Engine is not actually running
- the chosen frontend port is already in use
- the backend failed health checks because it could not connect to the database

### A port is already busy

- macOS script prompts you to choose another port
- Ubuntu script auto-selects the next open port
- Check what the app chose in `.env`

### Login fails or the account becomes locked

- Accounts lock after 5 bad passwords.
- An admin can unlock managed accounts in the UI.
- For the bootstrap admin, verify `BOOTSTRAP_ADMIN_USERNAME` and `BOOTSTRAP_ADMIN_PASSWORD` in `.env`, then restart the app.

### The bootstrap admin password keeps changing back

That is expected when `RESET_BOOTSTRAP_ADMIN_ON_STARTUP=true`.

Use one of these approaches:

- keep the desired bootstrap password in `.env`
- set `RESET_BOOTSTRAP_ADMIN_ON_STARTUP=false` if you intentionally do not want startup resets

Remember: the bootstrap admin password cannot be changed from inside the app.

### Database password mismatch after an earlier install

This usually happens when the Postgres volume was initialized with older credentials.

Safe fix:

- restore the original `DATABASE_USER` and `DATABASE_PASSWORD` in `.env`

Destructive fix:

- recreate the volume with `docker compose down -v`
- or on Ubuntu use `RESET_DEDICATED_DB_VOLUME_ON_AUTH_FAILURE=1 ./scripts/startup-ubuntu-24.04.sh`

### Backend says it cannot reach PostgreSQL

Check:

```bash
docker compose logs --tail=200 postgres
docker compose logs --tail=200 backend
```

Also verify:

- `DATABASE_HOST=127.0.0.1` for host-side backend runs
- `POSTGRES_SERVICE_HOST=postgres`
- `DATABASE_NAME`, `DATABASE_USER`, and `DATABASE_PASSWORD` match the current volume state

### Frontend cannot talk to backend

Check these settings in `.env`:

- `FRONTEND_ORIGIN`
- `FRONTEND_ORIGINS`

For Docker Compose, the browser normally talks to the frontend port and nginx proxies `/api` to the backend.

### Upload fails

Check for:

- unsupported file extension
- file larger than `50MB`
- missing `patient_id` with no successful auto-detection
- conflicting detected patient IDs across uploaded files

### Uploaded files are missing

Stored files live under `UPLOAD_DIR/patient-notes/...`. Relative `UPLOAD_DIR` values resolve to the local app-data folder on host runs and `/app/data/uploads` in Docker Compose.

If a database row exists but the file is gone:

- download will fail with `Stored patient note file is missing`
- investigate the backend Docker volume or host local app-data backup
- restore the missing encrypted files to the same storage path

### Audit logs are not reaching the database

If audit persistence fails, the app writes fallback records to:

```text
LOG_DIR/forensic-audit-fallback.jsonl
```

Check that file if the `audit_logs` table is missing expected events.

### Smoke test fails

Run it manually:

```bash
./scripts/smoke.sh
```

It verifies:

- frontend HTML loads
- `/api/health` returns `{"status":"ok"}`
- login works
- `/api/users/me` works
- chart list loads when password reset is not required

## Backups And Restore

Use the dedicated application DB name consistently.

### Backup

```bash
pg_dump -Fc iz_clinical_notes_analyzer > backup.dump
```

### Restore

```bash
pg_restore -d iz_clinical_notes_analyzer backup.dump
```

Validate uploaded-file backups separately if you need full recovery, because database backups do not include the encrypted upload volume or host app-data folder.

## Repository Layout

```text
backend/                     FastAPI app, models, services, tests
frontend/                    React/Vite UI and nginx config
scripts/                     Startup and smoke-test helpers
docs/                        Supporting runbook and architecture notes
backend data volume          Encrypted clinical note files and fallback logs at runtime
docker-compose.yml           Main local/VPS runtime definition
```

## Important Notes

- This project is designed around an application-owned PostgreSQL container, not a shared external database.
- The backend performs defensive schema compatibility updates on startup for older database volumes.
- The frontend is served from nginx in Docker and proxies API traffic to the backend.
- The bootstrap admin account is environment-managed and behaves differently from regular managed users.
