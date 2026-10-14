# Roster update maintenance — October 13, 2026

Scope: accurate per-phase progress, responsive status/dashboard, a backend-coordinated two-stage roster update, and restart resilience. Source maintenance on 1.0.1 / build 2026.10.12.1; no new installer artifact or release qualification.

## S0 baseline and boundaries

- Initial checkout: main tracking origin/main, with two pre-existing untracked user documents. They remain untouched.
- Prior read-only investigation: 37 targeted backend tests and 31 frontend tests passed. A synthetic three-process probe verified encrypted credentials persisted across two fresh-process restarts.
- Current live profile was inspected for configured-state flags only: saved ID/secret, API enabled, sync enabled and approved, schema 12, no active jobs. Values, patient content and identifiers were not printed or copied into test fixtures.
- Automated fixtures and all browser screenshots use synthetic records. Owner explicitly authorized live read-only calls to Alleva and app restarts. No vendor records are edited; no remote reset endpoint is invented; live approval settings are not changed.

## S1 implementation

- Saved parent workflow with patient then treatment-plan child jobs; serialized operational imports and repeated approval/profile validation at stage boundaries.
- Stop before stage two on incomplete/failed/cancelled patient pull; propagate local cancellation and check it between plan writes.
- Add schema migration 13 for phase counts, stage and child reference. Existing encrypted migration backup and atomic replacement remain authoritative.
- Collection progress is indeterminate; detail retrieval and saving use measured phase counts. Terminal failure/cancellation does not manufacture 100% completion.
- Keep still-running messages and monitor active operational jobs beyond one minute. Restore monitoring after navigation; stop polling on unmount. Correct StrictMode mount handling and use current completion callbacks.
- Group all nine dashboard counts with responsive layouts and place Update patients and treatment plans immediately below. Distinguish count-calculation time from successful import completion.
- Batch only authorized patient snapshots; retain exact identity/clinical evaluation. Limit both roster tables to 75 rows per page, retaining previous rows during refresh. Search and treatment-plan exports still include every filtered row, including other pages.
- Close unchanged-plan write transactions consistently; this prevents the importing session from blocking progress writes through a second connection.

## S2 completed functional verification

- Targeted operational/roster suite: 25 passed.
- Migration, workflow, exact identity and release-consistency suite: 47 passed, including schema 12 to 13 backup/upgrade with unchanged historical clinical rows.
- Frontend first full revised run: 188 passed; new combined-update card coverage: 2 additional tests passed. TypeScript and production build passed.
- Synthetic browser: signed in, ran combined update, navigated to Help while it ran, returned to completed status, and restored completion after browser reload. All nine counts verified at 1280, 768 and 375 widths. Narrow grid uses one column; intermediate and desktop grids adapt. A minor intrinsic-grid overflow found during visual QA was corrected before the final build.
- Live bounded verification: saved OAuth returned HTTP 200 in 0.84 seconds; two-record clients read returned HTTP 200 in 0.47 seconds; two-record treatment-plan read returned HTTP 200 in 0.11 seconds. Only endpoint categories, status, counts and timings were recorded.
- Final frontend: **192 tests in 31 files passed**. TypeScript noEmit and production build passed. Added pagination tests exercise 81 synthetic records, both roster page controls and search across off-page rows. Final built JavaScript asset: `index-kX255bTY.js`; normal localhost service verified serving it.
- Final workflow suite: **7 passed**, including completed-history restart, interrupted-parent recovery/retry with saved credentials, repeated unchanged replay, partial stage-one stop, cancellation, simultaneous roster reads, overlapping-pull rejection, unexpected worker failure, authorization, and schema 12-to-13 preservation.
- Sync/harness/feedback regression rerun: **35 passed**. Corrected current-schema/historical-migration checks: **43 passed**. Earlier targeted migration/workflow/identity run: **47 passed**. These suites overlap and must not be summed as unique test counts.
- Full backend run: **631 passed / 16 failed**, 3 deprecation warnings, 1416.29 seconds. Fourteen failures were stale schema-12 assertions/verification after adding migration 13; the corrected cases passed in the 43-test rerun. Historical migration-12 tests are explicitly pinned to migration 12 rather than changing that immutable migration. Two unchanged Windows packaging/control checks remain reproducible failures, detailed below. This is not a fully green backend suite.

## S3 owner-authorized live verification and restart

- The original source desktop service was stopped with the existing app-specific stop script after confirming no live jobs were active. Migration 13 completed through the real startup path. It retains 418 patient rows and saves job progress in the new table. No tenant approval or credential settings were changed.
- A temporary local verification service invoked the real gated `run_roster_update` workflow using an existing active administrator record and saved approved configuration. It made actual OAuth and read-only Alleva collection/detail calls; this was not a mocked import. The normal browser authentication routes and permissions were covered separately by synthetic tests. No patient content, vendor identifiers, credentials or tokens were emitted in verification output or copied into fixtures/screenshots.
- Actual combined pull: **completed**, stage 2, **606 of 606 treatment plans processed**, **0 warnings**, **0 failed records**, **0 new/changed plan versions written**, **160.7 seconds**. Identical source plans correctly remained unchanged. Stage one completed before stage two. While the pull ran, live health requests succeeded with observed latencies of 402 / 15 / 7 milliseconds; these are samples, not a latency guarantee.
- The verification service was stopped after completion and replaced with the normal `uvicorn app.desktop_main:app` source desktop service. Configuration-file hash was unchanged across restart. A fresh process read the persisted completed parent, stage 2, child reference, and 606/606 phase counts. Saved encrypted client ID and secret obtained a new real OAuth token with HTTP 200 after restart.
- A final normal-service restart loaded the final worker-failure guard. The saved completed 606/606 result remained intact, and saved credentials again obtained real OAuth HTTP 200. The normal localhost service is left running with the final built UI; no new live pull is automatically started on restart.
- Synthetic browser checks verified navigation during an update, return/reload recovery, nine metric tiles at 1280/768/375 widths, and the corrected narrow grid fitting within the viewport (dashboard right edge 348 pixels inside a 360-pixel content width). Screenshots remain local synthetic evidence only. Temporary synthetic browser/service cleanup is separate from the preserved client runtime.

## Remaining Windows verification blockers

Both were reproduced after the full run; neither file/runtime path was changed by this roster maintenance:

1. `backend/tests/test_v2_production_config.py::test_windows_release_stage_and_public_paths_fit_powershell_51`: the existing historical guide's computed installer staging path is **262 characters**, exceeding the asserted **less-than-260** limit in this long OneDrive checkout. No installer build, artifact cleanup or historical-guide removal was attempted. A shorter build checkout or separately reviewed packaging-path change is required before package qualification.
2. `backend/tests/test_desktop_runtime_host.py::test_live_candidate_gate_commit_drain_and_graceful_shutdown`: an unchanged PowerShell managed-runtime control subprocess exceeds its **15-second** outer timeout (status operation in the full run; shutdown operation in the focused rerun). The source desktop's app-specific stop/restart path succeeded in the actual live checks. Managed packaged-runtime qualification remains open; the failing check was not suppressed or its timeout increased.

## Station disposition

S0 inspection, S1 implementation, S2 scoped functional verification, and S3 live read-only/restart verification are complete. The normal source desktop app is running. No files are staged or committed; the two pre-existing user documents are preserved. Publication, installer acceptance and the two Windows checks above remain unqualified. Existing historical package evidence is unchanged.

## Known limits

This work does not certify clinical policy or compliance, tenant completeness beyond the approved mapping/limits, a published installer, physical laptop reboot, or replacement-device recovery. Interrupted work is explicitly marked interrupted; it is not automatically resumed after a process/laptop restart. Saved credentials and history remain persistent. LOC-change timing remains an unvalidated owner gate.
