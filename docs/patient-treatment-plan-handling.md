# Patient treatment-plan handling

Current source **1.0.1 / build 2026.10.12.1 / stable-local-desktop**. V2 denotes the internal architecture. This is the active source/API/storage map; dated evolution notes at the end retain historical scope. All verification uses synthetic data. Live vendor approval, retention and LOC policy remain external gates.

## Exact identity and data flow

Alleva `/clients.mrn` is the clinical MRN represented by the compatibility field `patient_id`; `/clients.id` is a separate source relationship key. MRN alone cannot uniquely identify a record across sources/facilities. Authorization and detail selection use the exact `patient_record_id` and immutable `plan_version_id`, with source mode and treatment-plan ID. `backend/app/v2/authorization.py` resolves selectors and rejects ambiguous or mismatched scope instead of guessing.

Manual parsing or an approved Alleva pull produces `TreatmentPlanAggregate` from `backend/app/v2/domain/schemas.py`. `services/treatment_plan_store.py` saves encrypted aggregates and clinical evidence, immutable plan versions and persisted evaluations. `services/treatment_plan_read_model.py` assembles authorized queue/detail projections. `services/deterministic_evaluator.py` and the canonical 42-step checklist produce timing/completeness outcomes. Manager actions and corrections attach to exact saved versions through their stores. Detail and roster APIs expose selected authorized evidence to the V2 browser.

Patient roster refresh is separate from full treatment-plan pull and retains patients with no plans. Names can be displayed to authorized users from encrypted patient snapshots; names are neither join keys nor audit detail. Both Manual and Alleva saved plans appear in current plan browsing. Missing original references, service dates or names remain unavailable rather than invented.

## Source input and storage

| Responsibility | Active source |
| --- | --- |
| Binder upload route and bounded reads | `backend/app/v2/api/manual_binder_routes.py` |
| Aggregate API import and source download/delete authorization | `backend/app/v2/api/manual_upload_routes.py` |
| Binder assembly and parsing | `backend/app/v2/services/manual_binder.py`, `manual_file_parser.py`, `manual_file_extractors.py`, `manual_file_aggregate.py` |
| Atomic encrypted source archive | `backend/app/v2/services/manual_source_batch.py`, `manual_source_file_store.py` |
| Operational Alleva plan and patient pulls | `backend/app/v2/services/alleva_sync.py`, `alleva_roster.py`, `alleva_patient_identity.py` |
| Approved mapping/provenance and job persistence | `backend/app/v2/services/alleva_contracts.py`, `jobs.py`, `job_store.py`, `job_runner.py` |
| Encrypted aggregate/patient source snapshots | `backend/app/v2/services/clinical_snapshot_codec.py`, `patient_snapshot_store.py` |
| Exact source-document membership | `backend/app/v2/services/source_membership_store.py` |

Manual uploads are point-in-time snapshots. Supported document extraction is bounded, and opaque source archival does not mean clinical parsing succeeded. Original filenames and clinical narratives must not enter forensic details. Live sync is off by default; approved tenant credentials, enablement, read-only authorization, endpoint/mapping and pagination/rate-limit validation and compliance approval are required. The operational collection reads `/clients` and bounded global `/treatment-plans` pages, rather than relying on a patient-name join or diagnostic ClientId-filtered preview. API harness operation tests and artifacts are readiness evidence, not authorization or a complete import.

SQLAlchemy account/settings/audit/import/source/action/job models live in `backend/app/v2/models.py`: `User`, `AppSetting`, `AuditLog`, `TreatmentPlanImport`, `UploadedDocument`, `TreatmentPlanManagerAction` and `ApiHarnessJobRecord`. Structural clinical tables are defined/migrated under `backend/app/v2/migrations/`, including `patients`, `loc_history`, `treatment_plan_versions`, `treatment_review_versions`, `diagnosis_snapshots`, `source_documents`, `evaluation_runs`, `criterion_results` and `source_document_plan_memberships`. Do not confuse these tables with removed legacy ORM classes.

Structural v12 membership backfill accepts only valid original source-document/plan-version pairs. Repeated/new imports attach exact saved memberships. Ambiguous legacy rows remain missing/unlinked evidence. Clinical detach/erase/retention choices remain owner-controlled; source deletion API existence is not a blanket data-destruction policy. Runtime SQLite, encrypted sources, logs and configuration remain under local AppData, outside the repository. SQLite identifiers/dates are sensitive metadata; application envelope encryption does not replace disk encryption.

## Aggregate and deterministic evaluation

The aggregate contains MRN/source, authorized display fields, LOC/admission/history, source update time, plan/review/signature content, due-date evidence, warnings, exactly 42 criterion results, manager reviews/overrides, audit references, evidence coverage, source-document references and checklist/rules/evaluation/timezone provenance. The detail API adds exact saved identity fields. Frontend types are `frontend/src/v2/types/treatmentPlan.ts` and `identity.ts`.

Initial signatures are checked on admission Day 1; master signatures within 30 calendar days of admission. Recurring PHP reviews use 30 calendar days and IOP/OP 60, anchored to latest valid signed review or admission. Source Next Review Due is compared with computed due date. Late master signatures affect overall status. Settings clinical intervals are read-only. The seven-calendar-day LOC candidate is unvalidated; LOC cases remain Needs Review. Missing Data, Conflicting Evidence and Unable to Evaluate must not silently become compliance. [Current rules](v2-beta/rules-contract.md).

## Active API and UI map

Routes are composed by `backend/app/v2/api/routes.py`; `runtime_routes.py` includes the split plan-read/export routers.

| Operation | Active API / route module |
| --- | --- |
| Dashboard | `GET /api/v2/dashboard` — `runtime_routes.py` |
| Patient and plan rosters | `GET /api/v2/patient-roster`, `GET /api/v2/treatment-plan-roster` — `roster_routes.py` |
| Patient source detail | `GET /api/v2/patients/{patient_id}` — `roster_routes.py` |
| Plan list and exact selected detail | `GET /api/v2/treatment-plans`, `GET /api/v2/treatment-plans/{patient_id}/{treatment_plan_id}` — `plan_read_routes.py` |
| Binder and aggregate import | `POST /api/v2/manual-uploads/treatment-plan-file`, `POST /api/v2/manual-uploads/treatment-plan-aggregate` — manual route modules |
| Source archive | `GET` source download and `DELETE /api/v2/treatment-plans/{patient_id}/source-documents/{source_file_id}` — `manual_upload_routes.py` |
| Manager action | `POST /api/v2/treatment-plans/{patient_id}/manager-actions` — `runtime_routes.py` |
| Corrections and explicit reevaluation | `POST /api/v2/treatment-plans/{patient_id}/correction-submissions`, `POST /api/v2/treatment-plans/{patient_id}/evaluations/refresh` — correction/evaluation modules |
| Plan and criterion CSV | `/api/v2/exports/treatment-plans.csv`, `/api/v2/exports/{patient_id}/checklist-evidence.csv` — `plan_export_routes.py` |
| Gated operational pulls | `POST /api/v2/alleva-sync/run`, `POST /api/v2/patient-roster/pull` and associated job status routes — `alleva_sync_routes.py` |
| Diagnostic jobs/artifacts | `/api/v2/api-harness/jobs` and job-specific status/cancel/artifact/preview routes — `runtime_routes.py` |

Protected detail, source, manager, correction and export calls must carry the exact selector fields required by their contract, particularly `plan_version_id` and `patient_record_id`; route IDs alone are not sufficient proof of authorization. `services/manager_action_store.py`, `correction_work_item_store.py`, `evaluation_store.py` and `evaluation_projection.py` preserve exact decision/evidence context. `services/audit_store.py` writes safe metadata and verifies the chain.

`frontend/src/v2/AppV2.tsx` owns session/selection routing. Current pages are `pages/DashboardPage.tsx`, `PatientRosterPage.tsx`, `PatientRecordDetailPage.tsx`, `TreatmentPlansRosterPage.tsx`, `TreatmentPlanDetailPage.tsx`, `ManualUploadPage.tsx`, `ApiHarnessPage.tsx`, `ForensicLogsPage.tsx` and `HelpPage.tsx`. `components/TreatmentPlanDetailViewer.tsx` renders clinical evidence. Both rosters show authorized source-scoped records, including names when available from encrypted snapshots; the plan roster includes saved Manual and Alleva plans. Importing a successor does not silently replace an already selected saved version.

## Verification

Use synthetic isolated profiles. Relevant existing suites include `backend/tests/test_v2_treatment_plan_rosters.py`, `test_v2_source_scoped_roster.py`, `test_v2_plan_version_authorization.py`, `test_v2_plan_version_actions.py`, `test_v2_plan_version_corrections.py`, `test_v2_evaluation_persistence.py`, `test_v2_manual_binder.py`, `test_v2_manual_upload_bounds.py` and `test_v2_audit_verification.py`. Run the complete backend suite and frontend tests/build for a release. Package safety must exclude runtime data/secrets and validate the exact ZIP. [Current verification](validation/current-work-2026-10-12.md) records results; old beta reports cannot qualify this build.

## Historical evolution notes

The following dated notes describe earlier implementations and UI arrangements. Current source, routes and controls are mapped above; historical navigation/order is not current instruction.

### 2026-07-13 V2 treatment-plan queue update

- The Treatment Plans tab, Patient Roster, and API Testing Harness share the same operational pull. A completed pull refreshes the active list on the initiating screen.
- The V2 sync imports every attributable treatment plan in the bounded global collection across all patient lifecycle states. `GET /api/v2/treatment-plans` and the CSV export expose the current revision of every distinct treatment-plan ID; `GET /api/v2/treatment-plans/{patient_id}/{treatment_plan_id}?source_mode=...` loads the selected plan without collapsing multiple plans for one patient. Patient, plan, roster, evaluation, and UI selection identities include the source system so matching manual and Alleva IDs cannot overwrite or display each other's detail.
- A changed record with the same source treatment-plan ID creates an encrypted immutable successor version and replaces the visible current plan. An identical replay creates no duplicate version.
- The completion audit records created, updated, and unchanged counts plus the exact `updated_treatment_plan_ids`; clinical narrative and patient names remain excluded from logs.
- `Patient Roster` lists authorized MRNs, full names, lifecycle/LOC/source metadata, and every linked treatment plan. Names remain excluded from logs and audit detail.
- Administrators and office managers can export the authorized current treatment-plan list and statuses as formula-safe CSV through `GET /api/v2/exports/treatment-plans.csv`.
- The published Alleva v1 patient/treatment-plan mapping is now an automatic internal contract. The API and sync enable switches, encrypted credential requirement, read-only boundary, and unvalidated LOC-change window remain in force.

### 2026-08-10 MRN-centered roster update

- Alleva `/clients.mrn` is the primary patient identifier in V2 persistence, API routes, UI, roster contracts, evaluation, and exports. The legacy aggregate property name `patient_id` remains an internal compatibility name whose value is the MRN. Alleva `/clients.id` is stored separately only as the source relationship key used to attribute treatment plans.
- Primary navigation begins with Status Dashboard, Patient Roster, Manual Upload, and Treatment Plan Detail. Treatment Plans Roster is the additional Alleva-plan browsing surface.
- Patient Roster groups every locally stored plan by MRN and source. Its Treatment Plans selector is ordered by descending last-updated time and displays `(#<plan ID>) YYYY-MM-DD HH:mm UTC`; selecting an option opens the exact plan in Treatment Plan Detail.
- Treatment Plans Roster lists each locally synchronized Alleva plan with MRN, last-updated time, the prior plan ID, and the initial plan ID/date. Selecting an ID opens the same full Treatment Plan Detail surface.
- The operational pull reads the complete bounded global `/treatment-plans` collection and maps every plan to `/clients.mrn` through its validated `/clients.id` relationship. Older plans and plans for inactive, discharged, or deleted clients are not discarded.
- API configuration, gated Alleva pull controls, encrypted persistence, role filtering, source-mode isolation, and minimum-necessary audit logging are unchanged. The live-sync authorization and unvalidated LOC-change-window gates remain in force.
- Windows desktop launch disables Uvicorn's raw request-path access log because patient and plan detail routes contain restricted identifiers. Metadata-only forensic audit events remain enabled.

### 2026-08-11 complete patient and plan workflow

- Navigation now begins with Status Dashboard, Patient Roster, Patient Record Detail, Treatment Plan Detail, and Treatment Plans Roster. Patient Roster is the normal starting point after login.
- Every `/clients` record with a nonblank `patient.mrn` is retained as a patient, including patients with no treatment plan. The complete source client object is versioned, encrypted at rest, and decrypted only after patient-read authorization.
- Authorized rosters and detail views display the full patient name derived from the encrypted client snapshot. Names are never used for identity matching and never enter forensic audit details.
- Patient Record Detail renders the selected patient's complete source record in readable semantic sections and lists all linked treatment plans newest-first by the plan's source-updated timestamp.
- Treatment Plans Roster preserves every valid global plan ID. Plans with a validated `/clients.id` relationship display the corresponding `/clients.mrn` and link to Patient Record Detail; plans without a resolvable MRN remain available as explicitly unlinked Treatment Plan Detail records.
- Treatment Plan Detail composes the selected plan's identity, source dates, lineage, clinical hierarchy, diagnoses, behavioral definitions, goals, objectives, interventions, signatures, reviews, checklist evidence, warnings, source archive, and raw diagnostics into one document-like view.
- Source-updated timestamps are preserved exactly. Valid values sort by their UTC instant, deterministic ties use plan ID, and missing or invalid values sort last; import, access, and capture times are not substituted.
