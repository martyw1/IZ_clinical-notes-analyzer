# Treatment-Plan Sync, Roster, and Export Validation

Date: 2026-07-13

Applies to: `2.0.0-beta.2` / build `2026.07.11.1` / `beta-local-desktop-v2`

## Scope and safety boundary

Validation used a new disposable local-app-data directory, synthetic administrator, synthetic Patient ID `912`, synthetic treatment-plan ID `plan-912`, and a localhost-only mock Alleva service. No production database, patient data, clinical export, tenant URL, vendor credential, local operator configuration, or real patient name was used.

This validation does not approve or claim live Alleva import. The approved-versioned-contract gate, encrypted saved-configuration boundary, external R3/Alleva approval requirement, and unvalidated configurable LOC-change window remain unchanged.

## Implemented behavior

- Treatment Plans and API Testing Harness share the approved operational pull and populate the same current queue.
- A changed record with an existing treatment-plan ID creates an immutable successor version, supersedes the prior same-ID version, and becomes current.
- An identical replay creates no duplicate treatment-plan version.
- Sync completion audit details include created, updated, and unchanged counts plus exact `updated_treatment_plan_ids`.
- Patient Roster is role-scoped and excludes patient-name fields.
- Administrators and office managers can download a formula-safe CSV of authorized current treatment plans and statuses; counselor/viewer export attempts are denied.

## Automated evidence

| Gate | Result |
|---|---|
| Focused backend red tests before implementation | Expected failures for missing ID/disposition, roster route, and export route |
| Focused backend feature/authorization tests | Pass — 4 passed |
| Full backend pytest | Pass — 182 passed; one existing Starlette/httpx deprecation warning |
| Full frontend Vitest | Pass — 22 passed |
| Frontend production build | Pass — 50 modules transformed |
| Diff whitespace check | Pass |
| React Doctor advisory scan | Non-gating repository-wide debt — 49 findings, dominated by existing React Compiler `try/finally` limitations and pre-existing state/effect patterns; supported Vitest/build and real UI gates pass |

Backend coverage verifies the same source treatment-plan ID across create, changed update, and unchanged replay; two immutable database versions remain and the newer row points to the prior row through `supersedes_version_id`. It also verifies exact updated-ID audit details, formula injection escaping, name/canary exclusion, role scoping, and route classification.

## Real Windows UI evidence

A visible Google Chrome window opened the built desktop app at `http://127.0.0.1:8765` through Windows Computer Use.

1. Signed in with the disposable synthetic administrator.
2. Opened Treatment Plans and confirmed the approved `Pull, evaluate, and populate queue` button, treatment-plan ID column, and status export button.
3. Pulled once and confirmed `plan-912` populated the queue without manually refreshing.
4. Changed only the synthetic mock plan content and pulled the same `plan-912` again. Current detail displayed `Synthetic revised UI problem.`
5. Queried the disposable SQLite database: `VERSIONS 2`; current row was `('plan-912', 2, 1)`.
6. Ran the approved pull from API Testing Harness and opened Treatment Plans; `plan-912` remained in the populated queue. The unchanged replay message stated that no new or changed plans were written.
7. Opened Patient Roster and confirmed Patient ID `912`, treatment-plan ID `plan-912`, status, lifecycle, LOC, source, and last-seen metadata. The page explicitly states that names are excluded and rendered no patient name.
8. Downloaded `treatment-plans.csv`. The row contained `912,plan-912,Missing Data,PHP,2026-06-01,2026-07-01,alleva_rest_api,7,0` under the expected headers.
9. Opened Forensic Logs and confirmed the update event included `updated_treatment_plan_count=1` and `updated_treatment_plan_ids=plan-912`; the export event recorded only the current plan count.
10. Verified the audit hash chain successfully.
11. Corrected the status-strip vocabulary found during visual QA and rechecked the rebuilt screen. Distinct segments rendered for Missing Data, Conflicting Evidence, Unable to Evaluate, Needs Review, Overdue, Urgent, Due Soon, Current/Compliant, and Incomplete.

## Residuals

- Live Alleva import is still blocked pending official approval, tenant/runtime mapping, pagination/rate limits, attachment behavior, vendor documentation, and compliance approval.
- The LOC-change treatment-plan update window remains unvalidated and configurable.
- The backend suite emits the existing FastAPI TestClient Starlette/httpx deprecation warning; it does not fail the suite.
- `npm run doctor -- --yes` exits nonzero on the existing V2 frontend debt (49 findings across 50 scanned files). A focused verbose scan shows the changed pull component is reported for the React Compiler's unsupported `try/finally` syntax, while the new roster's asynchronous effect state update is the standard external-request synchronization pattern. This advisory backlog was not expanded into an unrelated frontend-wide refactor.
