# Laptop first user live workflow validation

October 12, 2026, America/New_York. Source candidate: 1.0.1, build 2026.10.12.1, stable-local-desktop. This run used the configured laptop runtime and owner-authorized real Alleva reads. It is not a clean-machine installation test or exact-package acceptance. Patient content, identifiers, credentials, and raw vendor responses are excluded from this report.

## S0 baseline and scope

The checkout began clean on main. The existing desktop Start shortcut targets the source-checkout launcher, not an installed frozen release. Launching that actual shortcut started the localhost service and opened Microsoft Edge. The interactive walkthrough used a separate Codex browser tab against the same service and the administrator credentials supplied by the owner. No administrator elevation was requested.

The existing laptop profile already contained records and configured credentials; this was not a pristine first-login profile. No synthetic patient records were added to that runtime. Standard backend/frontend tests use their existing isolated fixtures. Windows component checks use disposable test fixtures, independently of the real-data walkthrough.

An unrelated untracked `docs/guides/current/Getting-Started-Guide v2.docx` appeared during validation and was preserved. No application source, credentials, settings, users, clinical approvals, comments, or overrides were changed. The requested real pulls updated local patient snapshots and plan versions and created normal audit events.

## Live application and Alleva checks

| Check | Result |
|---|---|
| Desktop Start shortcut | Service started; startup preflight passed; Edge opened the app. Source checkout remains under OneDrive. |
| Supplied administrator login | Passed; correct administrator navigation available. |
| Status Dashboard | Existing risk metrics and source readiness loaded. |
| Patient Roster live pull | Completed successfully; 409 records updated; 409 rows displayed. |
| Full treatment-plan pull | Completed, 100 percent; 606 records seen, 3 written, 0 failed, 0 warnings, 0 errors. Writes are changed/new records, not total saved inventory. |
| Saved Alleva inventory after pull | 409 patients; 607 saved plans; 598 linked and 9 unlinked; 105 patients without plans. Saved inventory is distinct from records returned in this pull. |
| Patient Record Detail | Identity/demographic, care/admission, and source sections loaded. A patient with six saved plans offered seven selector options including the placeholder. |
| Treatment Plan Detail | Opened from both plan roster and patient selector; clinical overview, review/signature sections, checklist, source-field explorer, source archive, and review controls loaded. |
| Checklist | All 42 criteria displayed for the selected real plan; criterion selection changed the evidence panel; unmatched search showed an explicit empty state; search restored. No review decisions saved. |
| Treatment Plans Roster | Refreshed count 607; Alleva source filter worked; unmatched search showed an empty state. |
| Manual Upload | Both import/file controls and handling guidance loaded. No patient files uploaded or duplicated. End-to-end real-file upload is not qualified. |
| API Testing Harness | Loaded; saved OAuth test passed; real read-only `/clients` test returned HTTP 200, JSON, with bounded response preview truncation. |
| Saved OpenAPI discovery | Passed; 424 operations available. |
| Users | Existing user, role/status table, creation and assignment controls loaded. No account changes made. |
| Forensic Logs | Recent login, view, pull-start/completion and OAuth events displayed; UI hash-chain check verified 55/55 events at that checkpoint. |
| Settings | Saved credential configured-state flags, live-read authorization and mapping present; no credential values exposed in this report; settings unchanged. |
| Account | Password/recovery controls loaded; credentials and recovery material unchanged. |
| Help | Startup, record selection, deadlines, review, imports, access, backup and troubleshooting sections and eight internal links loaded. |
| Sign-out | Returned to login; authenticated patient detail removed from the view. |
| Actual desktop Stop shortcut | Passed; port 8000 released. This distinguishes working actual stop behavior from the failed temporary-listener regression fixture. |
| Actual desktop restart | Passed; service and login returned after roughly two minutes under concurrent test load. Administrator sign-in and dashboard loaded again. |

After restart, API verification confirmed 409 patients and 607 saved Alleva plans. The patient roster again displayed 409 rows with 105 disabled no-plan selectors. Audit verification passed across 62/62 events. The app was returned to the dashboard.

The repository's existing `test-alleva-patient-workflow-live.ps1` passed against the completed job and the configured database. It validated four patient details and ten plan details, patient/plan linkage and ordering, display-label consistency, 411 encrypted patient snapshots with the expected envelope/schema, and audit privacy for events in its verification window. Private aggregate-only evidence: `%LOCALAPPDATA%\IZ-CNA-QA\first-user-2026-10-12\live-workflow.json`.

Unauthenticated requests to patient roster, plan roster, forensic logs, settings and users each returned HTTP 401. Health, readiness and version returned HTTP 200 with `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`. Readiness remains `warn` solely for the unvalidated LOC-change update window; the seven-day candidate remains display-only. Clinical and vendor policy gates are not certified by these software checks.

## Automated checks

| Check | Result |
|---|---|
| Full backend pytest | 642 passed, 1 failed, 3 deprecation warnings; 1693.67 seconds (28 minutes 13 seconds). Failure: `test_windows_release_stage_and_public_paths_fit_powershell_51`, `backend/tests/test_v2_production_config.py:214`. The bounded staging path is 262 characters in this checkout; the Windows assertion requires fewer than 260. |
| Frontend Vitest | 184 passed in 28 files. |
| Production frontend build | Passed. |
| TypeScript noEmit | Passed. |
| Release safety scanner regression | Passed, including folder/ZIP forbidden-file boundaries and private-report distribution canaries. |
| Maintenance harness | Passed, 46 assertions. |
| Windows installer packaging | Passed using its default owned evidence root. An initial custom-root invocation was rejected by the harness's ownership guard; it was rerun correctly. This is component validation, not a newly published release. |
| Maintenance contracts All | Failed `PATH_REPARSE_POINT`, after 33 successful assertions, under PowerShell 7 and Windows PowerShell 5.1. |
| Maintenance contracts negative | Failed `CONTRACT_ASSERTION_FAILED:inherited_known_folder_override_rejected`. |
| Maintenance backup All | Failed `BACKUP_VERIFICATION_FAILED`, after one assertion. Neither backup roundtrip nor negative suite qualified. Client backup/restore was not attempted. |
| Windows stop regression | Failed `legacy_app_command_shape_listens` under both PowerShell editions before reaching stop behavior. The fixture's temporary listener did not become available. Actual application remained running. |

The first frontend invocation could not find npm/npx in the tool PATH. Running the existing tools directly with the bundled Node executable completed all frontend checks. The failed Windows checks are not waived and are not automatically attributed to application defects without further diagnosis.

The backend failure concerns a historical HTML guide's path under the current OneDrive checkout's release staging directory. It is a reproducible release-build portability constraint for this source location, not a failed live patient request. No Windows long-path settings or release paths were changed to bypass it. This run collected 643 backend cases; the earlier maintenance ledger's 629-case result remains evidence for its own earlier run.

## Verification artifact and cleanup boundary

An initial encrypted-snapshot verification used the default `clinical-notes-analyzer-v2.sqlite3` filename instead of this laptop's configured `clinical-notes-analyzer.sqlite3`. SQLite created an empty, zero-byte default-name file and the verifier failed because it had no tables. The verifier was rerun successfully against the configured database. The active database was not replaced.

Automatic approval review blocked the command proposing removal of that empty file; the tool returned `blocked by policy` without a more specific reason. It remains at `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\clinical-notes-analyzer-v2.sqlite3`. No destructive cleanup or workaround was performed.

## Final disposition

S0 baseline, real-read walkthrough, desktop Stop/Start persistence verification, regression execution, and this completion report are complete. Overall result is mixed: the real workflow passed, while backend packaging-path, maintenance, backup, and isolated stop-fixture checks failed. The app remains running at its dashboard with the existing administrator session in the walkthrough tab.

No real-file upload, clinical review mutation, account lifecycle change, OS/device-loss restore, fresh Windows-account installation, or new release-package qualification is claimed. No application fixes, commits, or release artifacts were produced. The unvalidated LOC-change window and owner-controlled platform/clinical gates remain open.
