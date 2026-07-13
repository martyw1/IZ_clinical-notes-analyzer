# Patient Treatment Plan Handling

Date: 2026-07-06

Applies to: IZ Clinical Notes Analyzer Beta Version `1.4.6-beta.1` / build `2026.06.30.1`.

## V2 beta.2 note

The active V2 implementation is `2.0.0-beta.2` / build `2026.07.11.1` / channel `beta-local-desktop-v2`. This document remains the historical/shared implementation map; the V2 contract and final synthetic-only validation procedure are in `docs/v2-beta/`. No live Alleva production validation is claimed. Do not use production patient data, exports, databases, credentials, or uploads when performing beta.2 release validation.

### 2026-07-13 V2 treatment-plan queue update

- The Treatment Plans tab and API Testing Harness now share the same approved operational pull. A completed pull refreshes the current queue on the Treatment Plans screen.
- A changed record with the same source treatment-plan ID creates an encrypted immutable successor version and replaces the visible current plan. An identical replay creates no duplicate version.
- The completion audit records created, updated, and unchanged counts plus the exact `updated_treatment_plan_ids`; clinical narrative and patient names remain excluded from logs.
- `Patient Roster` lists authorized patient IDs, plan IDs, lifecycle/LOC/source metadata, and plan status without patient-name fields.
- Administrators and office managers can export the authorized current treatment-plan list and statuses as formula-safe CSV through `GET /api/v2/exports/treatment-plans.csv`.
- These V2 changes do not open live Alleva import. The approved versioned contract, API/sync gates, external R3/Alleva approval blocker, and unvalidated LOC-change window remain in force.

## Purpose

This is the current implementation reference for how patient treatment plans are handled in the app. It covers the local database model, manual upload sync, gated Alleva REST sync, the patient-level aggregate, deterministic timeliness decisions, selected-client checklist results, privacy controls, and the user-facing Treatment Plans queue.

Alleva and uploaded files are source evidence. The compliance decision remains local and deterministic. The app does not rely on an LLM and does not ask Alleva to decide whether a treatment plan is compliant.

## Current Data Flow

1. A treatment-plan client is created or refreshed from either a manual uploaded note set or an approved Alleva REST sync.
2. The app stores local rows for the active patient key, level-of-care history, treatment-plan records, manual overrides, and manager checklist reviews.
3. The timeliness evaluator calculates current status from local/facility date, admission date, current LOC, latest valid treatment-plan review/update date, source-document due date, signatures, and LOC-change evidence.
4. The selected-client detail payload builds the 42-step checklist result from `config/checklists/treatment-plan-v1.json` and enriches each step with evidence, finding text, evaluated values, manager status, manager comments, and audit context.
5. The Treatment Plans UI displays the work queue, evidence comparison, treatment-plan content summary, LOC history, treatment-plan evidence, rule results, checklist rows, manual overrides, and export actions.

## Source Inputs

Manual upload:

- `backend/app/services/timeliness.py::sync_from_note_set` turns an uploaded `PatientNoteSet` into one local `TreatmentPlanClient`.
- Uploaded document metadata creates local treatment-plan records when labels/types indicate Initial, Master, Review, or LOC update evidence.
- Manual upload is a point-in-time snapshot. It does not imply live monitoring.

Alleva REST readiness and sync:

- `backend/app/services/alleva_treatment_plan_sync.py` defines the approved endpoint names: `/clients`, `/treatment-plans`, `/treatment-plans/{id}`, `/treatment-plans/{id}/diagnosis`, `/treatment-reviews`, and `/treatment-reviews/{id}`.
- Live sync is blocked unless App settings enable sync, approve live treatment-plan sync, provide credentials, and mark endpoint mapping validated.
- Startup sync remains off by default. Manual sync uses the same gates.
- `/clients` and `/treatment-plans` are required for sync. `/treatment-reviews` is optional but warnings are surfaced when it is unavailable.
- Optional current-plan detail fetch can pull nested clinical content from `/treatment-plans/{id}` and diagnosis detail from `/treatment-plans/{id}/diagnosis`, subject to the configured cap.

API harness aggregate dry-run:

- `POST /api/api-configuration/alleva-quick-pull` with `report: "patient_centered_treatment_plans"`, `"active_patient_centered_treatment_plans"`, or `"single_patient_treatment_plans"` runs the clarified patient-centered flow: `GET /clients`, then `GET /treatment-plans?ClientId={patient_id}` using canonical `/clients.id`.
- `POST /api/api-configuration/alleva-quick-pull` with `report: "patient_treatment_plan_aggregates"` builds patient-level aggregate diagnostics from `/clients`, `/treatment-plans`, and `/treatment-reviews` without arming live sync.
- This is readiness evidence only. It does not bypass live-sync approval, endpoint mapping, or PHI handling requirements.

## Local Storage Model

The core tables live in `backend/app/models/models.py`:

- `TreatmentPlanClient`: Patient-ID-keyed local client row, active flag, current LOC, admission date, counselor/primary clinician, Alleva ID aliases, join confidence, data-quality warnings, current-plan pointer, import timestamps, and display label.
- `LevelOfCareHistory`: LOC, facility, effective date, discharge date, source evidence, and optional source note-set link.
- `TreatmentPlanRecord`: Initial/Master/Review/LOC update record with document date, staff/client/reviewer/guardian signature dates, displayed next due date, source evidence, source document ID, validity/conflict fields, Alleva lifecycle flags, current-plan detail status, content counts, and PHI-minimized content facts.
- `TreatmentPlanOverride`: admin/manager manual override with original value, new value, reason, affected rule, actor, and timestamp.
- `TreatmentPlanCriterionReview`: one manager status/comment row per treatment-plan client and checklist criterion.

Runtime SQLite, uploads, logs, reports, and `.env` stay under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`, not in the repo or installed app folder.

## Matching and Privacy

Patient matching uses approved ID aliases before any fallback:

- For the patient-centered API harness contract, treatment-plan joins use only `GET /clients.id` and treatment-plan `client: "/clients/{id}"`. The alias list below remains historical/local-sync readiness context, not the production patient-centered treatment-plan join rule.
- `clientId`
- `leadId`
- `patientId`
- `chartId` / `chartNumber`
- `luin`
- `uniqueId`
- `mrn`
- source `id` / `href`

Name-only joins are disabled by default and are for validation only when explicitly enabled. Ambiguous ID or name matches remain unmapped instead of guessed.

Patient-name import/display is also disabled by default. When disabled, Alleva-sourced clients store a generated `no-name-found_YYYY-MM-DD_HHMMSS` display label even if `/clients` returns a name. Saving App settings with name import/display off redacts existing Alleva-sourced treatment-plan display names again.

Treatment-plan element values are stored only after direct-identifier redaction and patient identifier fields are omitted before content snapshot storage. Detail capture stores counts, structured item kinds/labels, source paths, redacted text values, text-present flags, redacted text hashes, and non-name metadata.

## Deterministic Timeliness Rules

`backend/app/services/timeliness.py::evaluate_client` is the main decision path.

The evaluator uses:

- facility-local current date
- admission date
- current level of care
- configured LOC cadence from `config/rules/alleva_treatment_plan_completeness_rules.yaml`
- latest valid treatment-plan review/update staff signature date
- current treatment-plan start/document/last-modified fallback when no review or admission anchor exists
- source-document `Next Review Due`
- LOC effective date and the App settings LOC-change window
- conflict notes, missing signatures, and missing source evidence

Current date-window behavior:

- due date before current date: `Overdue`
- due today or one day out: `Urgent`
- two through seven days out: `Due Soon`
- eight or more days out: `Compliant`

Recurring cadence:

- PHP: 30 calendar days
- configured non-PHP levels: 60 calendar days

The LOC-change treatment-plan update window remains unvalidated by R3/Marleigh. The app keeps the manager-editable 7-calendar-day preset visible and unresolved. LOC-change cases must not be silently treated as compliant while the blocker is open.

## Aggregate Shape

There are two aggregate-related paths:

- `backend/app/services/alleva_treatment_plan_aggregate.py` builds the API-harness dry-run `PatientTreatmentPlanAggregate` from raw Alleva payloads.
- `backend/app/services/timeliness.py::treatment_plan_aggregate_payload` builds the stored selected-client aggregate returned by `GET /api/timeliness/clients/{client_id}/treatment-plan`.

The stored selected-client aggregate preserves legacy fields for the current UI/export contract and adds source-confidence, endpoint-count, current treatment plan, treatment plans, reviews, diagnoses, content facts, computed status, data-quality warnings, and PHI-minimized source provenance.

Raw upstream payloads, filenames, API keys, bearer tokens, client secrets, and patient direct identifiers are not returned as aggregate provenance. Redacted structured treatment-plan element values are returned so the app and completeness checker can inspect the actual plan contents.

## User-Facing Surfaces

Treatment Plans tab:

- `frontend/src/App.tsx` renders the `timeliness` view.
- Admins and office managers can open the Treatment Plans queue. Counselors do not have queue access because explicit counselor ownership is not modeled in the treatment-plan table.
- Admins see `Pull / refresh treatment plans`, which calls the gated Alleva REST sync route.
- The app shell keeps the daily work areas in the primary navigation: `Status Dashboard`, `Treatment plans`, `Review queue`, and `Manual upload`. Less-frequent support/admin pages are secondary shortcuts.
- The queue shows active clients, status, next due date, current LOC, evidence completeness, current-plan selection, and data-quality warnings.
- Selected-client detail shows the current treatment-plan content summary, evidence comparison, LOC history, treatment-plan evidence, rule results, 42-step checklist evaluation, manager notes, manual overrides, audit history, and export actions.
- Alleva/API lookup status and lookup result rows are bounded inside the treatment-plan lookup panel so progress messages and long diagnostics do not expand the page and hide lower treatment-plan details.
- When source-document `Next Review Due` disagrees with the computed date-clock due date and no validated LOC-change cadence explains the difference, the evaluator should keep the item in a review/error state such as `Needs Review` with `TP-DUE-DATE-CONFLICT`; it must not silently treat the item as compliant.

API routes:

- `GET /api/timeliness/dashboard`: active-client work queue with counts and sorted status rows.
- `GET /api/timeliness/clients/{client_id}`: selected-client detail and 42-step checklist evaluation.
- `GET /api/timeliness/clients/{client_id}/treatment-plan`: stored selected-client treatment-plan aggregate.
- `POST /api/timeliness/clients/{client_id}/overrides`: admin/manager manual override.
- `PATCH /api/timeliness/clients/{client_id}/criterion-reviews`: saved manager status/comment notes for checklist rows.
- `POST /api/alleva/treatment-plan-sync/run`: admin-only gated manual Alleva REST sync.
- `POST /api/api-configuration/alleva-quick-pull`: admin-only API harness quick-pull and aggregate dry-run.
- `GET /api/emr/alleva/id-mapping`: admin-only stored ID mapping diagnostic.
- `POST /api/emr/alleva/sync/detail-sample`: admin-only current-plan detail/diagnosis sample tool for approved mapping checks.

## Code Location Map

Backend model and storage:

- `backend/app/models/models.py`: `TreatmentPlanClient`, `LevelOfCareHistory`, `TreatmentPlanRecord`, `TreatmentPlanOverride`, `TreatmentPlanCriterionReview`.
- `backend/app/services/timeliness.py`: local upsert, manual-upload sync, evaluation, summary/detail payloads, selected-client aggregate payload, and checklist results.
- `backend/app/services/treatment_plan_content_safety.py`: safe content-item normalization and metadata redaction.

Alleva/API handling:

- `backend/app/services/alleva_treatment_plan_sync.py`: gated live sync, endpoint retrieval, ID matching, current-plan selection, detail fetch, content counts/facts, warnings, and sync audit events.
- `backend/app/services/alleva_treatment_plan_aggregate.py`: API-harness aggregate dry-run builder and diagnostics.
- `backend/app/services/alleva_retrieval.py`: shared Alleva response parsing helpers used by aggregate/readiness paths.
- `backend/app/services/alleva_patient_linkage.py`: ID mapping summary helpers.
- `backend/app/api/api_config_routes.py`: `patient_treatment_plan_aggregates` quick-pull route.
- `backend/app/api/routes.py`: App settings, manual sync route, ID mapping diagnostic, and current-plan detail sample route.
- `backend/app/api/timeliness_routes.py`: Treatment Plan Timeliness dashboard/detail/aggregate/override/manager-note routes.

Frontend:

- `frontend/src/App.tsx`: Treatment Plans queue, selected-client detail, sync button, exports, manager-note controls, App settings controls, and help text.
- `frontend/src/components/TreatmentPlanContentSummary.tsx`: current treatment-plan content counts and safe captured facts.
- `frontend/src/treatmentPlanContentSafety.ts`: frontend display helpers for safe content facts.

Rules and canonical workflow:

- `config/rules/alleva_treatment_plan_completeness_rules.yaml`: deterministic LOC cadence and treatment-plan tracking rules.
- `config/checklists/treatment-plan-v1.json`: canonical 42-step checklist source.
- `docs/treatment-plan-checklist-v1.md`: checklist/operator explanation.
- `docs/open-blockers.md`: unresolved LOC-change and Alleva live-sync blockers.

## Verification

Focused synthetic validation should include:

```powershell
$env:PYTHONPATH = "$PWD\backend"
.\backend\.venv\Scripts\python.exe -m pytest .\backend\tests\test_treatment_plan_timeliness.py .\backend\tests\test_api_connectivity.py -q
cd .\frontend
npm run test -- --run
npm run build
```

Regression coverage should include source-document due-date disagreement, missing admission or LOC evidence, LOC-change unresolved behavior, selected-client checklist payloads, manager criterion notes, bounded lookup status display, and release-package doc inclusion.

Packaging validation should use:

```powershell
.\Build-IZ-Windows-Installer.cmd
```

The release build must include `docs\patient-treatment-plan-handling.md`, `docs\beta-client-test-run-guide.md`, built frontend assets, install/launch/diagnostics/backup/uninstall commands, and must scan the folder and zip to exclude local `.env`, databases, uploads, logs, API tokens, raw vendor credentials, and other generated or sensitive files.
