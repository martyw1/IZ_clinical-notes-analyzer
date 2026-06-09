# Version 1 Final Validation Report

Date: 2026-06-09

Branch validated: `version1/windows-ready-local-20260609-074037`

Version: `1.0.0`

Build: `2026.06.09.1`

## Result

Version 1 is validated for local Windows laptop/desktop use with deterministic upload/review and Treatment Plan Timeliness Tracker workflows. Normal operator launch remains local-first and does not require Docker, PostgreSQL, Git, Node.js, or command-line work when using the packaged release.

## Artifacts

- Release folder: `dist\windows-release\IZ-Clinical-Notes-Analyzer-v1.0.0`
- Release zip: `dist\windows-release\IZ-Clinical-Notes-Analyzer-v1.0.0.zip`
- Preflight report: `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\logs\preflight-windows-latest.json`

Generated release artifacts are intentionally ignored by Git.

## Validation Commands

- `backend\.venv\Scripts\python.exe -m pytest backend\tests -q`
- `npm test -- --run`
- `npm run build`
- `scripts\preflight-windows.ps1 -AssumeYes`
- `scripts\build-windows-installer.ps1`
- `scripts\test-local-app-stack.ps1 -SkipDependencyInstall`
- `scripts\test-api-configuration-local.ps1 -SkipDependencyInstall`

## Results

- Backend tests: PASS, `74 passed, 2 skipped`.
- Frontend UI tests: PASS, `9 passed`.
- Frontend production build: PASS.
- Frontend dependency audit: PASS, `0 vulnerabilities`.
- Windows preflight: PASS.
- Windows release package: PASS.
- Local stack smoke: PASS.
- API configuration smoke: PASS.
- Real browser UI smoke: PASS.

## Real User UI Smoke

The in-app browser exercised the desktop app on `http://127.0.0.1:8000`:

- Signed in as the local bootstrap admin without exposing credentials.
- Verified dashboard queue cards, review-source choices, checklist version, readiness summary, and desktop shortcut footer.
- Verified the Checklist tab displays acronym definitions, the LOC-change blocker, review statuses, and 20 checklist steps.
- Verified the Manual Upload screen renders the expected Windows desktop form controls.
- Uploaded a synthetic TXT binder through the local API, then verified the generated binder and review chart in the browser UI.
- Saved a synthetic reviewer follow-up decision from the Criterion Review Workbench.
- Verified chart-review and treatment-plan export controls are present; frontend tests click CSV/JSON export controls and verify the download path because the in-app browser does not support download events.
- Verified the authenticated review screen at `1366x768` has no horizontal overflow and keeps nav/export controls reachable.

## Security Boundary

- All validation data was synthetic.
- No real PHI/PII was added to tests, docs, screenshots, or release notes.
- Saved local `.env`, SQLite databases, uploads, logs, generated package output, virtualenvs, and node modules remain ignored/untracked.
- Live Alleva patient import remains disabled.
- Direct Alleva connectivity probing was not run because official credentials and compliance approval were not supplied.

## Repo Hygiene Checks

- `git diff --check`: PASS, with Windows CRLF conversion warnings only.
- High-confidence secret scan: PASS; the only match was the documented scan command in the Windows deployment guide.
- Broader credential-name scan: reviewed; matches were synthetic test passwords, generated local secret variables in scripts, README placeholders, or non-secret encryption/save code paths.
- PHI/PII-shaped scan: reviewed; matches were synthetic test dates, EMR/MRN planning language, and pre-existing reference artifacts. No new real patient data was added.
- Runtime artifact scan: PASS; no `.env`, SQLite database, upload, or log files are tracked or unignored inside the repo.
- Release package scan: PASS; archived walkthrough/video reference folders are excluded from the Version 1 Windows package.

## Open Blocker

The treatment-plan update window after a level-of-care change is still unvalidated by R3/Marleigh. It remains configurable and visibly marked unvalidated in UI and docs.
