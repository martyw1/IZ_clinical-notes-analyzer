# Codex completion log - 2026-05-14

## 2026-07-11 V2 beta.2 release-readiness metadata and documentation

- Updated V2 prerelease metadata to `2.0.0-beta.2` / build `2026.07.11.1` / channel `beta-local-desktop-v2` in release files, backend version configuration, frontend package metadata/footer, sample OpenAPI metadata, and Windows preflight.
- Added the V2 release-readiness handoff record and aligned the V2 contracts, workflows, privacy/security, validation, blocker, release-note, and operator documentation.
- Kept the release explicitly prerelease-only. Supervised approved live Alleva validation, credential rotation and downstream/history-remediation approval, and signing/retention/legal-hold decisions remain external gates.
- Required final validation remains synthetic-data-only in an isolated local-app-data environment; it must not reuse production data, credentials, clinical exports, diagnostics, uploads, databases, or artifacts.

## 2026-07-01 treatment-plan handling docs and installer sync
- Added `docs/patient-treatment-plan-handling.md` as the current implementation reference for manual-upload treatment plans, gated Alleva REST treatment-plan sync, patient-level aggregate diagnostics, local treatment-plan tables, deterministic timeliness evaluation, selected-client 42-step checklist output, content-fact privacy handling, API routes, and Treatment Plans UI files.
- Updated README, architecture, runbook, codebase map, API connectivity docs, Windows user/deployment/install guides, release notes, blocker notes, UAT, checklist, workflow, and PRD notes to point to the current treatment-plan handling path and preserve the gated Alleva/live-import boundaries.
- Updated Windows release-builder/install surfaces so packaged releases validate and advertise `app\docs\patient-treatment-plan-handling.md` and record the local deterministic treatment-plan compliance engine in `release-manifest.json`.
- Kept PHI, uploaded documents, runtime databases, logs, `.env`, API tokens, and local credential material out of the documented package scope.

## 2026-06-28 treatment-plan redaction and cleanup remediation
- Added disabled-by-default Alleva patient-name import/display setting and kept validation-only name fallback as a separate saved setting.
- Changed Alleva treatment-plan sync to store generated redacted labels by default and to redact existing Alleva-sourced treatment-plan names when App settings is saved with patient-name import off.
- Added an admin-only `Pull / refresh treatment plans` button to the Treatment Plans tab.
- Moved unused/legacy code files into `depricated/` with `depricated/DEPRECATED-MANIFEST.md`, while preserving the active Windows launch path.
- Verification passed focused backend redaction/schema tests, full backend pytest (`118 passed, 2 skipped`), frontend Vitest (`17 passed`), frontend production build, Windows local stack smoke, API configuration smoke, Alleva connectivity probe, and in-app browser validation against a disposable synthetic local app launched through the normal PowerShell startup path.
- Validation evidence is recorded in `docs/validation/validation-report-2026-06-28-treatment-plan-redaction-cleanup.md`.

## 2026-06-23 v1.4.5-beta.1 R3 beta-client readiness
- Updated app/version metadata to `1.4.5-beta.1` / build `2026.06.23.1` on the `beta-local-desktop` channel.
- Renamed `Chart audit` to `Status Dashboard`, moved `Treatment plans` immediately after it, added bundled R3 logo support, and removed the desktop floating shortcuts/intake-guide page.
- Added admin-only `Clear All Patient Data` controls with typed confirmation, preserving settings, credentials, users, docs/rules, and audit logs while clearing patient/chart/upload/timeliness/review data.
- Moved gated manual Alleva `Retrieve Active Treatment Plans` to the Status Dashboard EMR/API card and kept startup sync off by default.
- Added saved manager status/comments per selected Treatment Plan checklist criterion and a selected-client counselor action CSV export.
- Corrected timeliness boundary handling so due today is not overdue, hardened manual upload 500s, and added backend tests for clear-data, upload rollback, criterion notes, inactive clients, and 30/60/7-day windows.
- Verification passed full backend pytest (`114 passed, 2 skipped`), frontend Vitest (`17 passed`), frontend production build, Windows local stack smoke on port `8767`, and browser validation against a disposable local app with synthetic data only.

## 2026-06-21 v1.4.4-beta.1 beta treatment-plan checklist detail visibility
- Converted current app/version metadata to `1.4.4-beta.1` / build `2026.06.21.1` on the `beta-local-desktop` channel.
- Added selected-client 42-step checklist evaluation results to Treatment Plans detail payloads, UI, and selected treatment-plan CSV/JSON exports while keeping checklist content version `1.2.0`.
- Preserved the gated Alleva REST treatment-plan sync boundary, including required `/clients` and `/treatment-plans` behavior and optional `/treatment-reviews` warning behavior.

## 2026-06-20 v1.4.4 Alleva treatment-plan sync follow-up
- Kept `/clients` and `/treatment-plans` as required Alleva REST sync endpoints while treating `/treatment-reviews` failures as warning-only optional endpoint failures.
- Moved enabled startup Alleva sync into a non-blocking background startup task and removed traceback logging for expected external sync failures.
- Added the admin-only Review Queue `Pull active treatment plans` action backed by the same approved sync endpoint used in App Settings.
- Verification passed targeted Alleva sync regression, relevant backend API/timeliness/connectivity tests (`39 passed`), full backend pytest (`101 passed, 2 skipped`), frontend Vitest (`17 passed`), and frontend production build.

## 2026-06-19 v1.4.4 API settings consolidation and startup audit repair
- Updated app/version metadata to `1.4.4` / build `2026.06.19.2`.
- Repaired startup and button-click audit persistence for legacy SQLite databases that still had the retired `audit_logs.fhir_audit_event` column marked `NOT NULL`.
- Clarified App settings, the Help tab, the standalone API harness, README, runbook, API guide, and Windows user guide around one active Alleva/API connection plus optional saved endpoint presets.
- Documented that pasting the R3/Alleva client ID and client secret is expected for OAuth client-credentials setup while saved secrets remain encrypted and write-only.
- Fixed the API harness save action so the active OpenAPI URL is saved with the rest of the active API configuration.
- Verification passed full backend pytest (`96 passed, 2 skipped`), frontend Vitest (`16 passed`), frontend production build, Windows local stack smoke, API configuration smoke, normal AppData startup, and authenticated UI button-event audit check with no legacy audit error patterns.

## 2026-06-19 v1.4.3 Alleva REST/OpenAPI readiness cleanup
- Updated app/version metadata to `1.4.3` / build `2026.06.19.1`.
- Removed active FHIR/SMART-on-FHIR configuration, discovery, import-plan routes, read scopes, UI fields, defaults, validation requirements, tests, and synthetic examples from Alleva workflows.
- Reframed Alleva integration as REST/OpenAPI/HL7-readiness only, preserving encrypted API credentials, OpenAPI operation testing, HL7 readiness language, and the gated Alleva REST treatment-plan sync path.
- Updated README, API configuration docs, architecture/runbook/codebase docs, Windows/UAT guides, blocker notes, changelog, and synthetic Alleva examples for the new boundary.
- Verification passed backend pytest (`95 passed, 2 skipped`), frontend Vitest (`16 passed`), and frontend production build.

## 2026-06-18 v1.4.2 manual upload button usability
- Updated app/version metadata to `1.4.2` / build `2026.06.18.2`.
- Fixed Manual upload binder deletion usability so disabled buttons no longer show the Windows busy cursor.
- Kept `Delete uploaded binder` clickable before the patient-ID confirmation matches, surfacing the exact confirmation guidance instead of leaving the button unavailable.
- Added a frontend regression test for clicking `Delete uploaded binder` before confirmation.
- Verification passed backend pytest (`96 passed, 2 skipped`), frontend Vitest (`16 passed`), frontend production build, example-treatment-plan upload/timeliness smoke across 4 files, and a live in-app browser/Computer Use-assisted button sweep against a disposable local server.

## 2026-06-18 v1.4.1 Alleva REST treatment-plan sync readiness
- Updated app/version metadata to `1.4.1` / build `2026.06.18.1`.
- Separated Alleva REST API base/OpenAPI settings from FHIR readiness so REST diagnostics and sync do not require a FHIR root.
- Added gated startup/manual Alleva REST treatment-plan sync into the R3 timeliness engine with approval and endpoint-mapping validation requirements.
- Added exact App settings validation, last sync status display, startup sync hook, manual sync endpoint, and audit events for sync outcomes and per-client R3 compliance analysis.
- Updated API harness defaults to use the Alleva REST base URL and OpenAPI URL.

## 2026-06-17 v1.4.0 treatment-plan date clock and workflow export hardening
- Updated app/version metadata to `1.4.0` / build `2026.06.17.1` and checklist/rules metadata to `1.2.0`.
- Added local current-date clock behavior for Treatment Plan Timeliness: PHP uses 30 calendar days, other configured LOC values use 60 calendar days, and the LOC-change preset defaults to 7 calendar days while remaining visibly unvalidated.
- Added per-analysis forensic audit logging with patient ID, status, next due date, current date, rule used, and workflow definition/version/checklist context.
- Added manual-upload page-level source evidence where PDF extraction can identify a page, and API/FHIR source identifiers for future Alleva/FHIR evidence traceability.
- Added 42-step workflow rows to CSV/JSON review and treatment-plan exports while preserving the existing checklist/domain export rows.
- Added in-place editing for draft workflow versions and clarified the UI distinction between editing a draft and using a published/archived version as a new draft template.
- Fixed the Review Queue selected-patient heading, periodic API-check enablement, specific App settings missing-field validation, and safe missing-name fallback format.
- Verified the public Alleva Swagger UI and `/swagger/v1/swagger.json` plus `/swagger/v2/swagger.json` are OpenAPI/REST API definitions, not FHIR base URLs; `/advanced-form-elements` is a protected REST path.
- Updated README, Windows user/deployment/UAT/Dell docs, API/EMR docs, runbook, architecture, workflow, checklist, blocker register, changelog, validation report, and removal-log planning.
- Verification passed full backend pytest (`93 passed, 2 skipped`), frontend Vitest (`15 passed`), frontend production build, and example-treatment-plan upload/timeliness smoke coverage across 4 files.

## 2026-06-16 v1.3.0 production usability and role-control hardening
- Updated app/version metadata to `1.3.0` / build `2026.06.16.1`.
- Reviewed the 2026-06-16 morning console/startup logs and local app logs; startup preflight was clean, while one settings `400` and repeated stale-session `401` loops were identified from the app session.
- Added stale-session handling so browser-side 401 responses clear the stored session token and return the operator to sign-in instead of repeating background requests.
- Added first-class Workflow profiles navigation for admins and office managers; the Checklist workflow action now opens Workflow profiles instead of App settings.
- Added role-scoped user management: admins manage all user roles, office managers manage counselor accounts only, and counselors manage only their own account.
- Kept App settings, API/EMR setup, optional LLM setup, and forensic logs admin-only.
- Added in-app Help covering role permissions, screen/button behavior, setup notes, workflow profile changes, API/EMR definitions, and LLM configuration notes.
- Added stored EMR endpoint profiles for Alleva and future EMR/FHIR endpoints, with encrypted client-secret storage and activation into current readiness/API settings.
- Renamed confusing SMART-only UI labels to OAuth/FHIR wording and clarified FHIR base URL as the vendor-supplied root FHIR R4 endpoint.
- Removed the standalone API harness second admin-login requirement when opened from the app; it now reuses the current signed-in admin session.
- Fixed uploaded/API-style treatment-plan re-evaluation behavior, safe fallback generated display names, and compliant-rule due-date selection.
- Verified optional LLM configuration against an OpenAI-compatible JSON response path while keeping LLM use disabled by default.
- Updated README, Windows user/deployment/UAT guides, API connectivity docs, runbook, workflow docs, blocker register, changelog, and validation reporting.
- Browser validation found opener `sessionStorage` was not reliable for the standalone API harness in every tab surface, so the harness now uses same-origin message handoff and was retested successfully.
- Verification passed full backend pytest (`93 passed, 2 skipped`), frontend Vitest (`15 passed`), frontend production build, Windows local stack smoke on port `8768`, Windows API configuration smoke on port `8769`, and a browser walkthrough against a disposable local server with synthetic admin/manager/counselor users.

## 2026-06-16 manual upload deletion and API readiness hardening
- Added authorized Manual upload binder deletion, including linked automated review cleanup, upload-derived timeliness cleanup, encrypted stored-file removal, and typed patient-ID confirmation in the UI.
- Added periodic API readiness settings for saved Alleva/API client ID and encrypted secret, configurable interval, token auth style, last-check status, and a background checker that remains dormant unless enabled.
- Ported `Test-AllevaApi.ps1` learnings into the app harness: body credentials, Basic auth, URL-encoded Basic auth, try-both, and try-all token styles; GET/HEAD operation tests avoid bodies unless required.
- Capped selected API operation response capture at 200 KB and compacted saved API reports so large provider responses cannot swamp the browser or report directory.
- Tightened forensic audit redaction for uploaded document labels, filenames, storage paths, descriptions, and source attachment/author metadata.
- Fixed Manual upload/review navigation found during browser smoke testing: uploaded binder details now open the automated review workbench, and linked reviews return to the binder detail panel.
- Updated API connectivity, Windows user guide, runbook, changelog, backend tests, and frontend tests for the new workflows.
- Verification passed full backend pytest (`89 passed, 2 skipped`), frontend Vitest (`14 passed`), frontend production build, and a local browser smoke against a disposable desktop server using synthetic data for periodic API checks, API harness large-response truncation, manual upload review handoff, criterion save, binder deletion, linked-review deletion, and sign out.

## 2026-06-15 v1.2.0 Windows local resilience and maintainability
- Updated app/version metadata to `1.2.0` / build `2026.06.15.1`.
- Added SQLite local-desktop hardening with busy timeout, foreign-key enforcement, and WAL mode where supported.
- Added same-browser session restore, admin/manager default landing on Treatment Plans, accessible confirmation dialogs, Escape dismissal, upload progress, and distinct Treatment Plan Timeliness status colors.
- Updated ordinary Windows double-click startup so it no longer forces `-AssumeYes`; preflight prompts before installing Python, backend packages, or rebuilding frontend assets unless support automation explicitly opts into unattended setup.
- Extracted auth/user, Treatment Plan Timeliness, and workflow-profile API routes into focused backend modules, and moved feedback dialogs/progress UI into `frontend/src/components/feedback.tsx`.
- Validation passed focused backend route/upload/config tests, frontend Vitest, frontend build, and a real local browser upload of `example-treatment-plans\JTXP.pdf` against a disposable desktop server.
- Computer Use opened the disposable local app in Chrome, signed in with the synthetic admin, and verified the Treatment Plans queue; local browser automation handled the example-PDF file selection/upload for reliable file input handling.

## 2026-06-09 v1.0.3 Treatment Plan Timeliness UI visibility patch
- Updated app/version metadata to `1.0.3` / build `2026.06.09.4`.
- Added a visible Treatment Plan Timeliness `Updated evidence queue` banner so operators can confirm the current UI is being served.
- Updated Windows preflight to detect stale `frontend\dist` assets and rebuild or warn when source-checkout React files are newer than the built browser UI.
- Updated release-facing README, changelog, Windows user/deployment/UAT docs, blocker notes, PRD implementation note, validation report, and completion log.
- Validation passed backend tests, frontend tests/build, Windows preflight, Windows local stack smoke, and visible browser smoke against a temporary localhost instance with synthetic data.
- Computer Use was attempted twice but was blocked because the local native pipe was unavailable on this laptop.

## 2026-06-04 v0.5.0 S0/S1 audit and conservative cleanup
- Synced `main` to `695080d`, created baseline tag `baseline-pre-codex-20260604-164125`, and worked on `refactor/codex-v0.5.0`.
- Added `docs/codebase-map.md`, `docs/cleanup-audit.md`, `docs/open-blockers.md`, and `docs/removal-log.md`.
- Updated `AGENTS.md`, README, and PRD notes to preserve R3 architecture guidance, PHI/synthetic-data boundaries, direct API harness limits, Windows assumptions, and the unvalidated LOC-change treatment-plan update window.
- Updated `.gitignore` for runtime SQLite files, logs, temporary files, coverage output, caches, local PRD duplicates, and walkthrough exports.
- Removed ignored/generated local artifacts: `docs/First sign-in credentials.txt`, corrupted pytest cache, and Vite cache/build output.
- Verification: backend tests passed with `54 passed` using Python 3.11 in `/tmp/iz-cna-backend-venv-311`; frontend production build passed after restoring missing local optional native packages for Rolldown and Lightning CSS.
- Validation blocker: frontend Vitest worker pool timed out before importing tests on this macOS checkout under both Node 24 and Node 25. No test assertions ran; rerun on CI/Node 20 or after local Node/Vitest worker repair.

## 2026-06-04 v0.5.0 S2 Treatment Plan Timeliness Tracker
- Added first-class timeliness domain tables for active clients, LOC history, treatment plan records, and manual overrides, with schema bootstrap and initial migration coverage.
- Added `backend/app/services/timeliness.py` for deterministic Initial, Master, ongoing review, LOC alias, missing-data, conflict, and LOC-change-unvalidated evaluation.
- Added authenticated timeliness APIs for dashboard, client upsert/detail, and audited manual overrides; counselors can read but denied override attempts are blocked and logged.
- Synced treatment plan metadata from uploaded patient note sets into the timeliness tracker without logging note text or PHI-bearing document content.
- Added React Treatment Plans dashboard/detail UI, LOC-change blocker visibility in Settings, manual override form for admin/manager roles, and frontend mocked route coverage.
- Encrypted LLM and access reputation API keys when saved through the main settings API; browser responses still return configured flags rather than secrets.
- Verification: focused S2 backend tests passed with `8 passed`; full backend suite passed with `59 passed`; frontend production build passed.
- Local validation blocker: frontend Vitest repeated the pre-import worker hang, and direct `tsc --noEmit` hung silently in this OneDrive checkout. Both processes were stopped; rerun on a repaired local Node/Vitest setup or CI/Node 20.

## 2026-06-04 v0.5.0 S3 clinical upload hardening
- Enforced binder total size from streamed stored byte counts in addition to preflight upload metadata, so uploads remain bounded even when request size metadata is absent.
- Kept supported extension, file count, per-file size, encrypted storage, metadata capture, patient ID auto-detection, conflict detection, immutable binder versioning, authenticated download, and counselor access boundaries covered by tests.
- Removed original filenames and note-derived detection reasons from upload/download audit details and messages; audit events retain minimum-necessary IDs, hashes, sizes, bucket, status, and request metadata.
- Added regression tests for too-large file, binder total limit, missing patient ID, conflicting detected patient IDs, unauthorized download, encrypted storage, and no note text/original filename in audit logs.
- Verification: focused upload/security tests passed with `13 passed`; full backend suite passed with `64 passed`.

## 2026-06-04 v0.5.0 S4 direct API test harness hardening
- Added redacted JSON report payloads for API definition pulls and selected OpenAPI operation tests.
- Redacted sensitive API result fields, bearer/API-key text, token query parameters, probe messages, operation URLs, and report request/result payloads before returning direct API harness results to the browser.
- Extended API connectivity tests for invalid URLs, request timeout handling, saved-key encryption, route-level inline/saved key redaction, operation response redaction, audit-log secret redaction, and report generation.
- Verification: focused API connectivity tests passed with `11 passed`; full backend suite passed with `68 passed`.

## 2026-06-04 v0.5.0 S5 workflow CRUD/versioning
- Added workflow definition and workflow definition version tables with draft/published/archived status, JSON definition snapshots, transition rules, schema bootstrap compatibility, and user-deletion blockers for workflow ownership/history.
- Added admin-only create/update/version/publish/archive APIs plus admin/manager read APIs, all with forensic audit events and no hard-delete path.
- Added a Settings workflow profile panel for admins to view profile/version status, create profiles, create draft versions, publish drafts, and archive active profiles.
- Added focused backend tests for workflow lifecycle, duplicate-key handling, role gates, immutable published versions, audit records, and legacy schema bootstrap.
- Verification: focused workflow/schema tests passed with `6 passed`; full backend suite passed with `71 passed`; frontend production build passed.
- Local validation blocker: a single-file `tsc --noEmit src/App.test.tsx` check also hung silently and was killed, matching the existing local Vitest/tsc worker issue in this OneDrive checkout.

## 2026-06-04 v0.5.0 S6 full-stack smoke hardening
- Expanded `scripts/smoke.sh` to check frontend HTML, `/api/health`, `/api/version`, `/api/readiness`, login, `/api/users/me`, `/api/charts`, and `/api/workflow-definitions?include_archived=true`.
- Updated `backend/tests/test_smoke_script.py` fake-curl coverage for version/readiness/workflow-profile calls and read-only password-reset behavior.
- Updated `scripts/test-local-app-stack.ps1` so Windows source-checkout smoke checks `/api/version` and the workflow profile API after authenticated login.
- Verification: focused smoke-script tests passed with `2 passed`; frontend production build passed; live desktop full-stack smoke passed on macOS against `app.desktop_main` with a temporary SQLite/env file on port `8765`.

## 2026-06-04 v0.5.0 S7 Windows validation docs, workflow seed hardening, and version bump
- Seeded fresh local databases with a published `Treatment Plan Timeliness Tracker` workflow profile and a synthetic, non-PHI definition snapshot.
- Added workflow definition payload validation for step labels and transition roles, plus an admin-only delete route limited to unused draft-only profiles that were never published.
- Added Settings UI support for deleting unused draft workflow profiles while preserving published/archived workflow history.
- Added `docs/workflow-extensibility.md` for workflow profile data model, API, validation, audit behavior, seeded defaults, and current limits.
- Added `docs/windows-dell-test-plan.md` with exact Dell Windows PowerShell commands, source-checkout validation steps, Option A packaged-release recommendation, and Option B source-checkout tradeoffs.
- Updated README, PRD notes, blocker register, changelog, and version metadata to `0.5.0`.
- Verification: full backend suite passed with `72 passed`; frontend production build passed; live desktop smoke passed on macOS against `app.desktop_main` with temporary SQLite/env data on port `8765`, `/api/version` reporting `0.5.0`, readiness `ok`, authenticated admin login, charts, and workflow profiles.

## 2026-06-03 README/operator documentation refresh
- Rewrote `README.md` as a current non-technical operator guide for Windows 10/11 local desktop use, including functionality, install/startup, configuration, everyday workflows, backup/restore, API connectivity, EMR/FHIR readiness boundaries, security guardrails, troubleshooting, Docker/server mode, architecture, and key files.
- Updated version metadata to `0.4.1` / build `2026.06.03.1` so `/api/version` and the UI footer can show the documentation refresh.
- Added this completion-log entry and a `CHANGELOG.md` entry.
- Verification: backend tests passed with `54 passed`; frontend tests passed with `6 passed`; frontend build passed; `npm audit --omit=dev --audit-level=high` reported `0 vulnerabilities`.

## Starting state
- Starting commit: `328d443310ed9277f1829b08143e8dab4dd73dea`.
- Local branch at start: `work` in `/workspace/IZ_clinical-notes-analyzer`.
- `origin` remote was not configured at start. It was added later as `https://github.com/martyw1/IZ_clinical-notes-analyzer.git`, but push failed because the non-interactive container had no GitHub credentials.

## Major decisions
- Kept SQLite as the default local Windows desktop database path and updated tests to request PostgreSQL explicitly for developer/server-mode validation.
- Added `/api/version` to the main FastAPI app so both test and desktop runtimes can report version metadata.
- Kept API configuration routes in the main app and UI/static desktop additions in `desktop_main.py` to avoid duplicate router registration.
- Added synthetic, clearly labeled clinical note samples rather than claiming official Alleva export formats.

## Files changed
- Version metadata: `VERSION`, `backend/app/services/version.py`, `backend/app/main.py`, `frontend/src/App.tsx`, `frontend/src/app.css`.
- API configuration exposure/tests: `backend/app/main.py`, `backend/app/desktop_main.py`, `backend/tests/test_api_connectivity.py`.
- Startup hardening test setup: `backend/tests/conftest.py`, `backend/tests/test_config.py`, `backend/tests/test_system_and_emr_readiness.py`.
- Documentation/samples: `README.md`, `CHANGELOG.md`, `AGENTS.md`, `docs/api-configuration-and-connectivity.md`, `docs/sample-clinical-notes/`.

## Tests run and results
- `PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q` - passed, 51 tests.
- `cd frontend && npm run test -- --run` - passed, 6 tests.
- `cd frontend && npm run build` - passed.
- `cd frontend && npm install` - completed with npm warnings about an unknown `http-proxy` env config and one dependency requiring newer Node for its preferred engine; install still succeeded on Node v20.20.2.

## Unresolved risks
- This Linux container is not a Windows 10/11 desktop, so PowerShell/CMD launcher behavior was not executed here.
- Pushing to GitHub could not be completed from this environment because `git push -u origin main` failed with `could not read Username for https://github.com` in the non-interactive container.
- Live Alleva connectivity still requires real tenant URL, credentials, and endpoint mapping; the app intentionally does not fake patient-data import.

## Windows validation still needing a real Windows box
1. Double-click `scripts\Start-IZ-Clinical-Notes-Analyzer.cmd` from a normal source checkout.
2. Run `scripts\startup-windows-local.ps1` in Windows PowerShell.
3. Run `scripts\test-api-configuration-local.ps1` and `scripts\test-local-app-stack.ps1` without real Alleva credentials.
4. Optionally run `scripts\test-alleva-api-connectivity.ps1` with non-secret public Swagger/OpenAPI target or real credentials supplied only via local environment variables.

## Additional resilience pass
- Added explicit Windows startup warnings for cloud-synced source checkout paths.
- Added localhost port 8000 conflict detection before opening the browser or starting Uvicorn.
- Statically reviewed Windows CMD/PowerShell launcher paths in this Linux container; `pwsh` was not installed, so script execution remains a Windows-box validation item.
- Ran a Linux full-stack smoke test on port 8765 against `/api/health`, `/api/readiness`, `/api/version`, `/`, login, `/api/users/me`, sample OpenAPI, and API definition pull; all checked endpoints succeeded and the Uvicorn process was terminated afterward.
