# Version 1 Completion Plan

Created: 2026-06-09

## Starting State

- Local repo path: `C:\Users\r3developer\OneDrive - R3 Recovery Services Inc\Development\IZ_clinical-notes-analyzer`
- Starting branch: `main`
- Starting commit: `09bbf2b360b17237e88de08a6c422250666f962f`
- Remote: `git@github.com:martyw1/IZ_clinical-notes-analyzer.git`
- Local `main` versus `origin/main` after `git fetch origin`: 0 ahead, 0 behind
- Safety branch: `version1/pre-existing-local-work-20260609-074037`
- Working branch: `version1/windows-ready-local-20260609-074037`
- Pre-existing uncommitted local changes: none

## Version 1 Stations

1. Repository and command discovery
   - Confirm backend, frontend, scripts, rules, docs, tests, CI, and packaging entry points.
   - Record exact detected commands instead of guessing.

2. Canonical Treatment Plan Checklist v1
   - Add one maintainable checklist source of truth with acronym definitions and the required 20 workflow steps.
   - Expose the checklist through backend APIs and a user-visible frontend panel.
   - Keep deterministic outcomes for missing or conflicting data.

3. API, upload, review, and export readiness
   - Verify existing API configuration and mock readiness boundary.
   - Add or harden missing review-source selection, status labels, exports, report output, and checklist evidence display.
   - Preserve the existing upload-first chart-review workflow.

4. Windows preflight and release package
   - Add standardized Windows scripts when they fit the repo structure.
   - Ensure launch-time checks create local AppData folders, validate config, validate rules, check runtime health, and write a readable report.
   - Build a per-user release folder under `dist\windows-release`.

5. Documentation
   - Update README and create the Version 1 checklist, Windows user guide, deployment/test guide, UAT script, completion log, and final validation report.
   - Keep the LOC-change timing blocker visible and unvalidated.

6. Validation
   - Run backend tests, frontend tests, frontend build, Windows preflight, release build, smoke tests, and security scans where practical.
   - Document exact commands, results, blockers, and artifacts.

7. Local merge and push gate
   - Commit only intended changes after validation or a documented checkpoint.
   - Merge validated work into local `main`.
   - Rerun critical smoke validation from `main`.
   - Push `origin main` only if the repo is clean, validation passes, no secrets or PHI/PII are found, and no force push is needed.

## Detected Commands

- Backend tests: `python -m pytest backend/tests -q` with `PYTHONPATH=backend`
- Frontend tests: `cd frontend; npm test -- --run`
- Frontend build: `cd frontend; npm run build`
- Existing local Windows launcher: `scripts\Start-IZ-Clinical-Notes-Analyzer.cmd`
- Existing local Windows startup: `scripts\startup-windows-local.ps1`
- Existing local stack smoke: `scripts\test-local-app-stack.ps1`
- Existing API configuration smoke: `scripts\test-api-configuration-local.ps1`
- Existing Alleva API connectivity smoke: `scripts\test-alleva-api-connectivity.ps1`

## Guardrails

- Use synthetic data only.
- Do not commit `.env`, runtime databases, uploads, logs, credentials, API keys, tokens, real patient data, or real facility data.
- Keep local runtime data under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.
- Do not make Docker, PostgreSQL, Git, Node.js, or command-line work part of normal Windows desktop use.
- Do not enable live Alleva patient import without official credentials, endpoint mapping, scopes, pagination/rate-limit behavior, vendor documentation, attachment handling, and compliance approval.
