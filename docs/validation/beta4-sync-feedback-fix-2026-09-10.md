# Beta.4 final fix and smoke validation

Release: `2.0.0-beta.4`, build `2026.09.10.2`. Main repository and rebuilt Windows client contain the same changed source and frontend assets.

## Fixes

- Persisted sync events retain timezone information, and Settings renders the correct UTC completion time.
- Newly recorded Alleva timeouts retain an allowlisted, safe explanation after navigation or restart. Historical unclassified failures retain generic feedback. Job Errors and Failed records have separate counters. Raw vendor exception content is not exposed.
- Rapid approval, comment, override, and return-for-correction actions no longer collide when Windows assigns the same clock tick. Within the existing write transaction, tied event times advance by one microsecond; every action remains a separate record. No schema migration, artificial delay, discarded action, clinical-rule change, or approval-gate change was introduced.

## Results

| Check | Result |
| --- | --- |
| Final full backend suite | 511 passed in 728.60 seconds; one existing Starlette/httpx deprecation warning |
| Frontend tests | 182 passed in 28 files |
| TypeScript and production frontend build | Passed |
| Browser harness safety tests | 58 passed |
| Supporting administrator recovery utility | 8 passed |
| Final full source browser smoke | 33/33 passed; clean teardown |
| Final full packaged browser smoke | 33/33 application scenarios passed; cleanup exception noted below |
| Password browser smoke, source and package | Passed; 24 captures per run, zero browser errors |
| Beta.3-to-beta.4 executable upgrade | Passed; chosen password preserved, starter rejected, recovery setup available |
| Independent visual reviews | Both PASS; all six sync-status and three Help captures inspected |
| Release folder and ZIP safety scans | Passed |
| Artifact integrity | Changed source and frontend assets match repository; ZIP executable matches tested executable |

Password checks cover initial mandatory change, recovery-code use and replacement, one-time-code reuse rejection, staff temporary passwords, and rejection of old passwords and sessions. Browser scenarios cover roles, uploads, exact-plan selection, all four review actions, corrections, rosters, filters, exports, session expiry, settings, logs, dashboard, Help, and responsive layouts. New sync-feedback browser cases simulate job responses explicitly; backend tests verify real SQLite persistence, restart behavior, and private-exception omission.

The initial full backend pass was 510 tests in 757.04 seconds. A broader browser run then exposed approval followed by comment returning HTTP 500. A frozen-clock API regression reproduced the exact database uniqueness error. After the persistence fix, 38 focused tests passed, followed by the final source and packaged browser runs; all four actions returned HTTP 200. No assertion was weakened and no retry was added to mask the failure.

## Live-data boundary

The earlier [live Alleva smoke](live-beta4-smoke-2026-09-10.md) records real connectivity, a successful safe resume, and a roster pull. An authenticated local read on the corrected source runtime verified the existing live sync: completed, 581 seen, 13 written, zero errors, completion corresponding to September 10 at 21:20:58.082903 UTC. That check made no new vendor request. Post-fix browser scenarios use synthetic data; a new authenticated live-browser session and another live Alleva pull are not claimed. External vendor timeouts remain possible; safe Resume remains available.

## Runner and cleanup notes

Packaging preflight first found the owned source test app on port 8000; that app was stopped before building. A temporary wrapper also treated dependency notices as terminating errors; its handling was corrected without changing application code.

Two packaged browser runs completed their application scenarios but the runner exited during cleanup with `INVALID_RUNNER_INPUT`. For the final run, the owned runtime process was independently confirmed absent and port 49331 closed. Temporary synthetic data remains outside the repository. Automatic approval review rejected a manual recursive cleanup attempt with `blocked by policy`; no workaround deletion was attempted. No test data, credentials, live screenshots, or vendor payloads are packaged or committed.

Evidence is local and ignored under `.omo/evidence/beta4-sync-fix/`, with final application receipts under its `final/` directory.

## Access and usage accounting

Local device: code changes, builds, automated browser/API tests, artifact checks, and the authenticated read of previously imported live data. OpenAI LLM: diagnosis, coordination, code review, and two independent visual reviews. Remote: no new Alleva request during this fix; Git publishing is recorded in the completion response.

Unmetered estimate for this extended fix/QA work, including independent reviews: roughly 250�350 tool/message exchanges and 150,000�300,000 tokens. Exact billing and model-memory telemetry are unavailable. Observed backend-test peak working memory was approximately 170 MiB; total browser/build/device peak memory was not measured.
