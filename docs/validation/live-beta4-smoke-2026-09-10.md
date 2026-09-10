# Beta.4 live-data smoke test

Revision: `18a0c739e2842eb4103077def523482079c19011`. Release: `2.0.0-beta.4`, build `2026.09.10.1`.

## Scope and results

The user explicitly requested actual computer use with the saved Alleva connection and live data. Browser actions used the Codex in-app browser against the beta.4 Windows executable and the existing local runtime. The user completed sign-in and real-account recovery setup. No patient names, identifiers, clinical text, credentials, screenshots of live records, or raw payloads are included in this report.

| Check | Result |
| --- | --- |
| Full backend suite | 506 passed in 716.90 seconds; one existing Starlette/httpx deprecation warning |
| Full frontend suite | 178 passed across 27 files |
| TypeScript and production frontend build | Passed |
| Beta.4 ZIP release safety scan | Passed |
| Browser saved OAuth connectivity | Passed; token obtained and discarded |
| Browser protected GET /clients | HTTP 200; bounded diagnostic reported truncation |
| First treatment-plan sync | Failed with ReadTimeout after seeing 395 records; zero written; audit error count 1 |
| One safe resume through Settings | Completed; 581 seen, 13 updated, zero warnings and failed records |
| Dedicated patient roster pull | Completed; 395 seen and updated, zero warnings and failed records |
| Navigation during sync | Help, upload, account, rosters, and detail screens remained usable |
| Patient roster | Loaded live records; no-match search and clearing search worked; patient detail opened |
| Patient record to saved plan | Saved-plan selector opened treatment-plan detail, timeline, review history, checklist evidence and review controls |
| Treatment Plans Roster | Loaded live plans; no-match filter worked; empty-result export action exercised |
| Manual Upload | Page loaded; empty submission correctly requested files |
| Users | Creation, assignments, and reset controls rendered; no real users modified |
| Account | Password-change form rendered; recovery configured state confirmed |
| Help and Forensic Logs | Loaded; audit exposed the timeout cause without vendor response bodies |

Successful resumed sync ran from 21:18:32.829632 UTC to 21:20:58.082903 UTC: **145.25 seconds**. The dedicated roster pull ran from 21:21:16.327975 UTC to 21:21:18.008045 UTC: **1.68 seconds**. These are persisted job timings. One patient-detail click and subsequent accessibility-state read took approximately 0.75 seconds, including automation overhead; this is not a browser performance benchmark.

## Findings and limits

1. The first live sync encountered a vendor-response read timeout with the existing 10-second request timeout. Exactly one safe resume succeeded. No timeout setting or application code was changed. A clean first-attempt live-sync pass is not claimed.
2. Settings showed the completed sync as September 11 at 01:20 UTC, whereas the persisted completion is September 10 at 21:20 UTC. This is a four-hour timestamp display discrepancy. The dedicated roster completion displayed 21:21 UTC correctly. The Settings completion display uses `frontend/src/v2/components/JobStatusPanel.tsx`.
3. The failed sync panel displayed Failed records = 0 despite the job failing; the separate persisted errors_count was 1 and the audit log supplied ReadTimeout. The Settings panel did not expose that cause directly.
4. Real clinical approvals, overrides, correction comments, uploads, user creation, assignments, and password resets were not submitted against production records for testing. Their automated test coverage passed; a complete live mutation test of every user feature is not claimed. The empty-result export was initiated, but downloaded file contents were not independently inspected.
5. Audit hash-chain verification was initiated, but its terminal result was not observed before navigating away; no hash-chain pass is claimed.
6. Source-build authenticated browser checks remain pending. The main checkout starts and serves the login screen after replacing the packaged runtime. Reloading the original tab before startup completed left that tab on a connection-error data URL blocked by browser tooling. A fresh tab is available, but requires sign-in. This is a QA/browser handoff limitation, not evidence of a source-build login failure.

The finite test pass did not repeat passing suites. The original long shell tool calls timed out at the tool transport boundary, but local test processes completed and their exit files and logs confirmed success. Evidence with aggregate-only results is under `.omo/evidence/full-qa-beta4-2026-09-10/` and remains excluded from Git.

## Access and accounting

Local device: executable/source startup, browser operation, existing encrypted local data, automated tests, build, and ZIP scan. Remote access: authorized Alleva OAuth and read-only GET/import requests through the application. OpenAI LLM: coordinated checks and interpreted browser/audit results. No clinical decisions or vendor-side record writes were performed. Approximate usage for the ongoing QA: 80–120 tool/message exchanges and 35,000–60,000 tokens; exact billing and model/device peak memory are unavailable.

Follow-up: the timestamp and failure-feedback findings are addressed in build `2026.09.10.2`; see [fix validation](beta4-sync-feedback-fix-2026-09-10.md). Historical results above remain specific to build .1.
