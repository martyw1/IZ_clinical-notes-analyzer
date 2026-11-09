# Local clinician linking and GOP rule validation - 2026-11-06

Source maintenance; no installer release or production qualification claimed.

## Changes
- Clinicians offers Link clinician to patient for administrators and office managers. Exact authorized patient search uses a request body; local association drives patient/plan clinician labels, caseload filters and overdue grouping. Explicit local unassignment and restoration of the Alleva relationship are available. Local links survive import; source evidence and app-account permissions remain unchanged.
- Revision checks prevent stale writes. Audit records contain internal identifiers, UTC time and action metadata, without names or clinical text.
- Rules 1.2.3 recognizes GOP within LOC strings and uses 30 calendar days, displayed in Settings. PHP 30 and IOP/OP 60 remain. Multiple families conflict; same-plan last-updated/created fallback remains deterministic.

## Checks
- Focused backend assignment, deadline, deterministic evaluator and persistence suite: 94 passed.
- Frontend TypeScript check passed; complete frontend suite: 33 files, 205 tests passed; production frontend build passed.
- Isolated Microsoft Edge end-to-end test used synthetic clients/plans and a mock vendor HTTP server. Clinician-only pulls made no treatment-plan/review requests and preserved all six plan evidence/version hashes. Repeated pulls were idempotent. Local reassignment survived another pull, moved overdue grouping into descending order, explicit unassignment worked, and restoring Alleva restored the original group. PHP, IOP substring/creation fallback, OP, GOP substring, 10-day warning, red/orange/green detail badges and Eastern timestamps passed independent expected-date checks.
- Cleanly stopped the owned local app after confirming no active import jobs and restarted on loopback port 8000. Version endpoint returned 200. Existing signed-in Edge session worked. Live clinician-only pull completed; directory, patient search, disabled save before selection and GOP Settings rule were verified. No real local assignments were changed. No patient/staff names, credentials or real screenshots retained in this report.

The live vendor response still supplies no current primary-clinician assignments. Local links require the user's actual selections. Dell deployment still depends on OneDrive synchronization and restart there.

Additional clinician-import backend regressions: 11 passed. Total focused backend tests: 105 passed. git diff --check passed.
