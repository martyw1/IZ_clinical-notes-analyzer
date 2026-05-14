# AGENTS.md - IZ Clinical Notes Analyzer

## Repo purpose
Local-first Windows 10/11 clinical-notes completeness-check app. It is upload-first, uses FastAPI + React, stores runtime data in local app data, and must not require Docker or PostgreSQL for normal Windows desktop use.

## Important directories
- `backend/app/` - FastAPI API, auth/RBAC, audit logging, uploads, encrypted storage, rules execution, API connectivity boundary.
- `backend/tests/` - pytest backend and smoke coverage.
- `frontend/src/` - React UI for login, uploads/reviews, user management, logs, settings, and version footer.
- `scripts/` - Windows launch and smoke-test scripts.
- `config/rules/` - deterministic completeness rules.
- `docs/` - operator/developer docs and synthetic examples.

## How to run checks
- Backend: `python -m venv backend/.venv && backend/.venv/bin/python -m pip install -r backend/requirements.txt && PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q`
- Frontend: `cd frontend && npm install && npm run test -- --run && npm run build`
- Windows launcher: inspect or run `scripts\Start-IZ-Clinical-Notes-Analyzer.cmd`, `scripts\startup-windows-local.ps1`, `scripts\test-api-configuration-local.ps1`, `scripts\test-alleva-api-connectivity.ps1`, and `scripts\test-local-app-stack.ps1` on Windows PowerShell.

## Security / PHI rules
- Do not commit PHI, real patient notes, `.env`, SQLite databases, uploaded notes, logs, API keys, bearer tokens, encryption keys, or passwords.
- Do not log uploaded note text, PHI-like names/content, API keys, bearer tokens, encryption keys, or passwords.
- Keep uploads encrypted at rest with the existing local encryption envelope.
- Saved API credentials must be encrypted and never returned to the browser.
- Do not fake Alleva live patient import; keep live import unavailable until real tenant credentials and endpoint mapping are provided.
- Do not add Docker or PostgreSQL as Windows desktop requirements.

## Done means
- Version metadata is updated and visible through `/api/version` and the UI.
- Backend tests pass.
- Frontend tests and build pass.
- Windows scripts are kept source-checkout-friendly and documented.
- Docs, changelog, and completion log are updated.
- Git status is checked so generated runtime data and secrets are not committed.
