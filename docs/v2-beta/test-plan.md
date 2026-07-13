# V2 Test Plan

Automated checks:

- Backend V2 runtime tests verify version metadata, readiness, navigation, 42 criterion aggregate, manager override reason enforcement, redacted API configuration/sample OpenAPI contract, `ClientId` pull-definition flow, large job lifecycle artifacts, immutable same-ID treatment-plan updates, unchanged replay deduplication, exact updated-ID audit details, patient-roster scoping/name exclusion, and manager-only formula-safe status export.
- Frontend tests verify login, V2 navigation, the Treatment Plans operational pull and automatic queue refresh, backend status-vocabulary preservation, treatment-plan IDs, patient-ID-only roster rendering, status export download, updated-ID forensic rendering, nested detail sections, override reason enforcement, and large job bounded artifacts.
- Import scans verify active code does not import from `deprecated/v1/`.
- Windows scripts verify preflight, local app stack, API configuration harness, bounded Pull ALL job preview/artifacts, and release package forbidden-file scans.

Manual QA:

- Run the local app at `http://localhost:8000`.
- Sign in as admin.
- Open Treatment Plans and run the approved synthetic operational pull. Verify the queue populates without a manual refresh, shows treatment-plan IDs, and retains the current plan after an unchanged replay.
- Change a synthetic source record without changing its treatment-plan ID, pull again, and verify the current detail changes while Forensic Logs list the exact updated ID.
- Open Patient Roster and verify authorized patient/plan IDs and statuses appear without patient names.
- Export treatment plans and verify the CSV includes treatment-plan ID and status.
- Open API Testing Harness, run its approved operational pull, open the Treatment Plans queue, and verify the same populated list. Then start a synthetic large diagnostic job.
- Verify the browser remains responsive and no full payload is rendered.
- Use Computer Use or equivalent desktop capture for a real Windows screenshot pass on Dashboard, Treatment Plans, and API Testing Harness before release sign-off.

Current validation evidence is recorded in `validation-report.md`; task-list coverage is recorded in `task-coverage-audit.md`.

## Beta.2 final validation environment

Run release validation only against a freshly created, isolated `%TEMP%` local-app-data directory with synthetic users, Patient IDs, and fixtures. Do not point `IZ_CNA_LOCAL_APP_DATA_DIR` at an operator profile; do not load `.env`, credential profiles, production databases, clinical exports, saved harness reports, or uploads. Record only redacted command results and screenshots. See `release-readiness-2026-07-11.md` for the exact procedure and unresolved external gates.
