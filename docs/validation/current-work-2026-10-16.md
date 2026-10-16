# Version 1.0.2 maintenance validation October 16 2026

Target: 1.0.2 / build 2026.10.16.1 / stable-local-desktop. Work branch: `codex/1.0.2-loc-deadlines`.

## S0 preservation and baseline

- Before code edits, created local tracked-source ZIP and verified full Git bundle in the OneDrive sibling checkpoint folder. Preserved pre-existing untracked architecture documentation and Word guide separately without staging them.
- Created and pushed annotated tag `checkpoint/1.0.1-before-1.0.2-2026-10-16`. Remote peeled target verified as `3c2a4a4a10a16afff2e51c823d08c68550beb7bd`, matching pre-change local HEAD.
- Existing repository Python environment points to an unavailable installation on another computer. Created a separate test environment under the developer cache; did not replace the app environment or modify user settings.
- Initial unchanged frontend baseline: 189 passed, 3 roster-pull failures. All four roster-pull tests then passed alone. Single-worker unchanged baseline: 191 passed, 1 patient-roster pagination failure. These observations predate implementation.
- A partial backend baseline ran against a separate extraction of archived 1.0.1 source and reproduced two Windows runtime failures. Diagnosis: Windows PowerShell script loading was blocked by the host execution policy. Both checks passed with a process-only test setting; no machine-wide policy changed. The partial baseline was stopped to prioritize final full regression.
- No destructive cleanup, real patient fixtures, live vendor requests, production database writes or existing administrator password changes.

## S2 deadline computation

- Replaced review/admission recurrence anchoring with plan last updated plus the LOC interval. Shared Monday-Friday ten-business-day warning horizon. Invalid, missing and future update dates fail explicitly.
- Normalized nested Alleva LOC values; current saved Alleva versions can use current patient snapshot LOC without rewriting historical source snapshots. Derived evaluation hashes reflect a changed patient LOC.
- Targeted initial verification: 54 backend tests passed. Expanded core verification after rule/metadata revision: 60 backend tests passed.

## S3 dashboard

- Select latest updated plan per authorized patient record and count computed deadlines independently of overall checklist status. Explain excluded ambiguous/missing dates. Removed dashboard-only Workload, quality and Urgent metrics.
- Six targeted backend dashboard tests and nine frontend dashboard/detail tests passed.

## S4 persisted comments

- Added display-only prior-version comment history scoped by patient record, source and original plan ID. Exact-version actions and approvals remain separate.
- Targeted comment/action/authorization run passed 79 tests; one metadata assertion used the earlier loaded rule revision while files were being updated. The core rerun with finalized metadata passed; the full suite checks the final source together.
- Nine frontend detail/mapper tests and production build passed.

## S5 full regression and handoff

- Full frontend suite: 192 tests in 31 files passed; TypeScript noEmit and production build passed.
- Desktop browser suite: eight tests passed against the built frontend and isolated synthetic app data, including actual local API counts, latest-plan selection and persisted prior-version comments after reload. Vendor responses in the existing pull tests remain mocked; these tests do not establish live Alleva connectivity.
- Source index and built frontend safety scans passed. Dependency lockfile checked against the checkpoint: only the two application version fields changed.
- First completed backend full run: 654 passed, four failed. Three requested the intentionally removed Workload metric; assertions were updated to verify the new deadline counts. The fourth used the copied repository virtual environment, which points to another computer. The recovery utility now accepts an optional interpreter argument and the isolated test supplies its actual interpreter; default launcher behavior is unchanged. No recovery was run against an existing app account.
- Final full backend run: 658 passed, five warnings, in 584.92 seconds. Four isolated workers; test-process-only PowerShell script loading. All earlier failures resolved. Nine targeted correction/recovery/readiness tests also passed against isolated temporary app data.
- User requested real vendor calls additionally. Chrome inventory contained only GitHub, no normal local app server was listening, and standard app data/settings were absent. Real credential-free GET requests to https://api.allevasoft.com/swagger/v1/swagger.json returned HTTP 200 with JSON on October 16, 2026. The first probe was bounded to 256 KiB; a subsequent bounded 4 MiB inspection read the 942,906-byte public definition. It declares Client.levelOfCare and TreatmentPlan.lastModified as strings and nextReviewDue on TxReviewDetails. No patient data was requested. Production sync uses a normal HTTP client; no mock transport exists in backend application code. Awaiting the existing configured app URL/session for authenticated vendor and treatment-plan verification; public metadata reachability is not proof of authentication or imports.
- No installer was deployed and no existing account, configuration or clinical database was reset. Exact installer/live-tenant acceptance remains separate.

The LOC-change update window remains unvalidated. A live-tenant comparison and owner-controlled production/Windows installer gates are separate from synthetic source regression.

## Completion scope

Source implementation and automated regression are complete. The rebuilt frontend is present in the local source checkout. Existing administrator passwords and normal app-data settings were not reset, replaced or used as test fixtures. The 1.0.1 checkpoint remains immutable. Authenticated real-tenant plan verification and installer deployment are pending, rather than inferred from public API metadata or synthetic tests.
