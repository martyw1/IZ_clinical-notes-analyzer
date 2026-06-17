# Validation Report - Production Readiness Pass

Date: 2026-06-16
Version under test: `1.3.0` / build `2026.06.16.1`
Data used: synthetic test fixtures only.

## Summary

Result: automated validation, Windows local smoke scripts, and browser role/harness walkthrough passed. A final target-machine packaged-install pass is still recommended before broad non-technical rollout.

This pass focused on turnkey production use: clearer UI wording/status colors, adaptive layout, in-app help, role enforcement, user-management CRUD, workflow-profile management, settings/API/LLM access boundaries, treatment-plan update/re-evaluation behavior, EMR endpoint profiles, and morning-log issue review.

## Fixes Made

- Replaced confusing `Manage Workflow` routing with a dedicated `Workflow profiles` screen for admins and office managers.
- Kept App settings, API/EMR setup, LLM setup, and Forensic logs admin-only.
- Allowed office managers to manage counselor users and workflow profiles while blocking admin/manager account management.
- Added in-app Help covering every role and major screen/button/workflow.
- Improved status badge contrast for treatment-plan risk/review/missing/conflict states and added responsive help/workflow/profile layouts.
- Added EMR endpoint profiles for multiple Alleva/future EMR/FHIR endpoints with encrypted client-secret storage and activation.
- Clarified FHIR base URL and OAuth/FHIR labels; the API harness now reuses the existing admin session when opened from App settings.
- Hardened the API harness session handoff with same-origin messaging after browser validation found opener `sessionStorage` was not reliable in every tab surface.
- Fixed stale-session handling after repeated 401s from the morning app run.
- Fixed treatment-plan fallback names. Version 1.4.0 supersedes the earlier generated/patient-ID prefix with:
  - no name found in source evidence: `no-name-found_YYYY-MM-DD_HHMMSS`
  - empty or unusable value found: `no-value-found_YYYY-MM-DD_HHMMSS`
- Fixed compliant treatment-plan due-date selection and added API-style re-pull/re-evaluation coverage.
- Verified optional LLM configuration against an OpenAI-compatible JSON response path while keeping LLM disabled by default.

## Log Review

Reviewed the pasted morning console text and local startup/app logs from 2026-06-16.

- Startup/preflight completed successfully.
- One `PATCH /api/settings` returned `400`; settings validation now keeps required LLM/API fields explicit and no optional endpoint-profile draft field blocks App settings save.
- Repeated `401` events appeared after the browser session expired/stale token was reused across `/api/ui-events`, `/api/settings`, `/api/emr/profile`, `/api/workflow-definitions`, `/api/audit/logs`, `/api/timeliness/dashboard`, and `/api/treatment-plan-checklist`.
- Frontend API calls now clear the same-browser session token and return to sign-in on 401.

## Role and Permission Coverage

| Role | UI verified | Backend verified | Result |
| --- | --- | --- | --- |
| Admin | Dashboard, Help, User management, Workflow profiles, App settings, API/EMR, LLM, Forensic logs, uploads, reviews, treatment plans | Full user CRUD, settings/admin-only routes, EMR profiles, workflow CRUD/versioning, logs, overrides | Pass |
| Office manager | Dashboard, Help, counselor User management, Workflow profiles, review decisions, treatment-plan overrides | Manager can manage counselors and workflows; manager blocked from admin/manager account management and App settings/logs | Pass |
| Counselor | Dashboard/read paths, uploads/profile, no admin tabs/actions | Counselor blocked from user management, settings, workflow mutations, logs, and overrides | Pass |

## Screen/Button/Workflow Coverage

| Area | Coverage | Result |
| --- | --- | --- |
| Dashboard | Quick actions, source cards, status colors, admin/manager/counselor navigation visibility | Pass |
| Help | Role matrix and screen/button guide visible to signed-in users | Pass |
| Treatment plans | Filters, evidence detail, manual overrides, CSV/JSON exports, upload/API-style re-evaluation, fallback names | Pass |
| Checklist | 42-step checklist, LOC blocker, `Workflow profiles` button routes to workflow screen | Pass |
| Manual upload | Initial/update modes, deletion, linked review handoff, upload-derived timeliness sync | Pass |
| Review queue | Open chart, criterion edit, manager approve/return, re-analysis | Pass |
| User management | Admin all-role CRUD, manager counselor-only CRUD, reset/delete/deactivate guards | Pass |
| Workflow profiles | Create profile, create draft, seed 42-step draft, publish, archive, delete unused draft | Pass |
| App settings | Admin-only organization/timezone/LOC/API/LLM/readiness/EMR endpoint controls | Pass |
| API harness | Admin-only, no second in-page login when opened from app, bounded/redacted results | Pass |
| Forensic logs | Admin-only log visibility and non-secret audit details | Pass |

## Automated Validation

| Check | Command | Result |
| --- | --- | --- |
| Backend test suite | `PYTHONPATH=backend backend\.venv\Scripts\python.exe -m pytest backend\tests -q` | Pass: `93 passed, 2 skipped` |
| Frontend tests | `npm run test -- --run` from `frontend` | Pass: `15 passed` |
| Frontend production build | `npm run build` from `frontend` | Pass |
| Windows local stack smoke | `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\test-local-app-stack.ps1 -Port 8768 -SkipDependencyInstall` | Pass |
| Windows API configuration smoke | `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\test-api-configuration-local.ps1 -Port 8769 -SkipDependencyInstall` | Pass |

## Browser Walkthrough

Disposable local server: `http://127.0.0.1:8767` with temporary SQLite/upload/log folders and synthetic users only.

| Persona | Actions | Result |
| --- | --- | --- |
| Admin | Signed in, confirmed `v1.3.0` Treatment Plans banner/footer, created manager and counselor users, opened App settings, verified FHIR/OAuth labels, LLM fields, LOC blocker, readiness, and stored EMR endpoint profiles | Pass |
| Manager | Completed first-login password reset, verified no App settings/Forensic logs tabs, verified counselor-only create form, opened Workflow profiles, saw manager access and seed-draft controls, opened Help role matrix | Pass |
| Counselor | Completed first-login password reset, verified restricted nav only, opened Help, My account, and Manual upload | Pass |
| API harness | Opened from App settings, reused current admin session with no second login, used local sample definition, pulled OpenAPI successfully | Pass |

## Remaining Risks

- Live Alleva patient import remains intentionally disabled until R3/Alleva provides official tenant credentials, endpoint mapping, scopes, pagination/rate limits, attachment behavior, vendor documentation, and compliance approval.
- LOC-change treatment-plan update window remains unvalidated by R3/Marleigh and must stay visibly unvalidated.
- A final hands-on packaged-install pass on the target Windows laptop should still verify install/launch/uninstall shortcuts and screenshots with synthetic data before broad rollout.
- The app is still not a signed MSI/MSIX with repair/modify support.
