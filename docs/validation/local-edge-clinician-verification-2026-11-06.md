# Local Edge clinician workflow verification — November 6, 2026

## Scope
Ran the actual built desktop web app through Microsoft Edge and Playwright against an isolated local SQLite database and synthetic HTTP Alleva server. No production patient data, real vendor credentials, or live tenant requests were used. The browser timezone was Pacific while the app displayed Eastern time. The Windows Computer Use helper was not retried.

## Passed browser checks
- Signed in through the real login form with a synthetic administrator.
- Clicked Pull clinicians on Clinicians: three staff imported and five assignments linked. Only token, client and user requests occurred; no treatment-plan or review requests. All five saved plan versions and their content/evidence hashes stayed unchanged.
- Repeated the pull without duplicate staff or changed plans.
- Opened a clinician's two-client caseload.
- Verified five computed dates, statuses and overdue ages against independent fixture expectations: PHP 4, Evening IOP 4 with creation fallback, OP due soon, PHP current, and IOP 4 late.
- Verified alphabetical clinician groups: Alpha had 60 then 30 days overdue; Beta had 40. Clinician filtering and exact-plan navigation worked.
- Verified IOP creation fallback plus 60 days, the actual creation timestamp, and matching red badges in both detail locations. Due-soon/current plans showed matching orange/green badges.
- Verified clinician completion logs and Eastern timestamps despite the Pacific browser timezone.

## Defects discovered and fixed
The initial browser check found that creation-fallback dates calculated correctly but latest-plan selection still required last_updated, excluding those plans from current worklists. Stored read models now carry a separate derived tracking_timestamp using the creation evidence already accepted for that exact plan. Source last_updated stays unchanged. Dashboard, roster and clinician worklists share that selection.

Visual review also found Plan created displayed plan start date. It now displays the actual creation timestamp. Regression tests cover both fixes. An intermediate browser check used an overly exact Worklist label selector; that test selector was corrected. The final complete Edge run passed against the final build.

## Validation and evidence
44 targeted backend tests passed. All 202 frontend tests passed across 32 files; TypeScript and the frontend production build passed. The final real-Edge walkthrough passed every check. Full platform/installer qualification and live-tenant verification are not claimed.

Synthetic screenshots and verification.json were saved locally under Temp/IZ-clinician-browser-evidence. The temporary app server was stopped. User browsers and production patient databases were untouched. The fixes and built assets are in the shared checkout for OneDrive sync and Dell restart.
