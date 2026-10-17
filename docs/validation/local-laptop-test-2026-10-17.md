# Local laptop test — October 17, 2026

## S0 — startup and sign-in

- Preserved the copied, unusable backend virtual environment by renaming it locally; no cleanup or deletion performed. Recreated the environment for the current Windows user after the launcher installed Python 3.12.
- Frontend dependency installation and build completed through the Windows preflight launcher.
- Corrected the preflight's stale 1.0.1/build literal: active version/build/channel must match the checkout's VERSION.json, and the stable-local-desktop channel remains required.
- Windows launcher succeeded using the existing configured localhost port 8765.
- `/api/version` confirmed 1.0.2 / 2026.10.16.1, stable-local-desktop, v2 runtime.
- `/api/readiness` responded successfully: local app data, database, and build channel checks OK. Expected warnings remain for unconfigured API testing and unvalidated LOC-change timing.
- Admin sign-in succeeded in Microsoft Edge. Mandatory recovery-code setup awaits the owner before dashboard/workflow testing can proceed. No credentials or recovery codes recorded here.

## Remaining validation

Dashboard and clinical workflow tests have not yet been performed. Backend/frontend test suites and release packaging gates were not run in this startup station. This record does not qualify a release or authorize live Alleva import.


## S1 — stop and prepare main

- Stopped the identified localhost app runtime and confirmed port 8765 no longer listens.
- Owner reported local updates appeared to work. Agent-observed scope remains startup, version/readiness and successful sign-in; dashboard/clinical acceptance is not inferred.
- Aligned active documentation and Windows builder metadata with 1.0.2 / build 2026.10.16.1, and set the release metadata branch to main. Historical screenshots and validation retain original identities.
- Added a local-only credential-note ignore rule. Runtime data, copied environment backup and the pre-existing Word-guide draft are excluded from the source commit.
- Regenerated offline architecture documentation: 28 pages, 994 local references, Edge rendering, search, empty results and 390px layout checks passed.
- Frontend production build passed. Initial full frontend run: 191 passed, one checklist selection timing failure; isolated rerun: all four detail-page tests passed. Updated the test to wait for the asynchronous selected state; final full rerun recorded below.
- Existing installer version contracts: 33 assertions passed. Installer schema/source-build compatibility remains an explicit open blocker; no new installer was generated or qualified.
- Serial backend partial run stopped to restart the full suite with four isolated workers; partial output showed no failures and is not a full passing result.

- Final frontend suite: 192 passed in 31 files; TypeScript noEmit passed; production build passed.
- Windows builder metadata guard accepted 1.0.2 and rejected stale 1.0.1 identity. Changed PowerShell scripts parsed without errors.
- Staged-path safety scan and diff whitespace checks passed; staged text scan found no supplied-login-password or API-key patterns.

- Full Windows maintenance contracts passed: 117 assertions; backup round-trip 9 assertions; backup negative cases 30 assertions. All fixtures were synthetic.
- Local main fast-forwarded without conflicts to include the 1.0.2 implementation and laptop follow-up; no remote history rewrite.


## S2 — final regression and remote preparation

- Full backend run: 656 passed, two failed, five Starlette deprecation warnings, 791.29 seconds. Both failures were mocked Alleva job completion assertions after a roughly two-second polling budget. An isolated unchanged rerun reproduced both timeouts.
- Changed only those two test polling budgets to a monotonic 30-second deadline, retaining terminal-status and persisted-data assertions. Application sync behavior and vendor gates are unchanged.
- Follow-up entire Alleva-sync test module plus release-version consistency and runtime-readiness checks: 25 passed, five deprecation warnings, 54.60 seconds. Both earlier failures passed. The full 658-test suite was not repeated after this test-only correction; the full-run and follow-up results are reported separately.
- Final frontend: 192 passed; TypeScript noEmit and production build passed. Windows maintenance and architecture results are recorded above.
- Source commit prepared on main for normal non-force push. Version remains 1.0.2 / build 2026.10.16.1 / stable-local-desktop. No installer, live tenant validation, local credentials, clinical data or unrelated Word-guide draft is included.
