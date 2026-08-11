# Alleva Patient Treatment-Plan Data Contract

Date: 2026-07-02

This contract distinguishes the current V2 operational importer from the patient-filtered API Test Harness diagnostics. The TypeScript diagnostic contract lives in `frontend/src/types/allevaTreatmentPlan.ts`; backend tests also cover the operational MRN mapping and global collection boundary.

## Canonical Keys

- `/clients.mrn` is the canonical local patient identity and the value represented by the legacy `patient_id` property in operational app payloads.
- `/clients.id` is stored separately as `source_patient_id`; it is the Alleva relationship key and may be called `leadId` in other contexts.
- Treatment-plan ownership is validated from `client.id`, `client.route`, or a treatment-plan `client` string such as `/clients/{id}`.
- `raw_client_ref` stores the original treatment-plan `client` value.
- `extracted_patient_id` / `plan_client_id` stores the parsed `{id}` from `/clients/{id}`.
- `join_validated` is `true` only when all returned relationship forms agree on one source patient ID that maps to an observed client MRN.

## Disallowed Join Keys

Do not use these as treatment-plan join keys:

- `source_id`
- `chartId`
- `externalId`
- `clientName`
- `clientId`
- `uniqueId`

`source_id` may remain a display/reference field when present, but it is not an alignment key.

## Operational Collection and Diagnostic ClientId Query

The operational patient-plan pull is:

```text
GET /clients
GET /treatment-plans (bounded global pages)
```

This preserves every attributable older and newer plan across patient lifecycle states. The API Test Harness may still issue `GET /treatment-plans?ClientId={source_patient_id}` for a diagnostic single-patient probe. `ClientId` is case-sensitive in that diagnostic route; it is not the operational local patient key.

## Client Reference Parsing

For each returned treatment plan:

1. Preserve `client` as `raw_client_ref`.
2. Parse `/clients/{id}`.
3. Store `{id}` as `extracted_patient_id` and `plan_client_id`.
4. Resolve the source patient ID to the matching `/clients.mrn`.
5. Do not import plans with blank, malformed, conflicting, or unmapped relationships; report the skipped record without guessing.

## Active Client Versus Active Plan

Active client status comes from `GET /clients` status:

- `status.id == 1049`: Active
- `status.id == 1356`: Discharged

`status.id` is the canonical field when present. If a live response exposes only a status label, preserve `status_id` as blank, derive a visible `status_scope` from the label for operator review, and emit `missing_patient_status_id` so the app does not silently invent `1049` or `1356`.

Unknown values such as `InActive` remain `other`/non-active until Alleva defines them.

Active treatment-plan status comes from `isActive`. `isComplete` means EMR submission/completion; it does not mean inactive, closed, superseded, or current.

## Discharge Fields

`dischargeDate` / `dischargeDateTime` from `GET /clients` is planned or scheduled discharge, not actual system discharge. It is reported as `planned_discharge_date`.

`actualSysDischargeDateTime` and `isDischarge` are not trusted from `GET /clients` because current observed responses did not expose reliable values. The app does not use them to decide active/discharged status.

## Multiple Active Plans

A client can have multiple treatment plans, including older and newer records.

- Store all attributable plans regardless of client lifecycle state.
- Store all active plans.
- Set `has_multiple_active_plans = true` when `active_plan_count > 1`.
- For display/default selection only, choose `latest_created_active_plan` as the active plan with the highest internal treatment-plan ID / TPId.
- Label it as latest-created active plan, not an official current plan.

## Treatment Reviews

`nextReviewDue` is only available on `GET /treatment-reviews/{id}` when a trusted `treatmentPlanReviewId` is already known. The REST API clarification says there is no reliable review list endpoint and review payloads do not expose stable client/treatment-plan foreign keys.

Therefore patient-plan aggregates return:

```json
{
  "review_data_status": "unavailable_via_rest_without_known_review_id",
  "next_review_due_source": "unavailable"
}
```

Do not join treatment reviews by `clientName`.

## Safe Tested Samples

Synthetic local harness fixture, using non-PHI values:

```json
{
  "patient_id": "307",
  "status_id": "1049",
  "status_label": "Active",
  "endpoint": "GET /treatment-plans?ClientId=307",
  "treatment_plan_id": "10",
  "raw_client_ref": "/clients/307",
  "extracted_patient_id": "307",
  "join_validated": true,
  "is_active": true,
  "is_complete": true,
  "is_initial_tp": true,
  "start_date": "2026-01-02",
  "end_date": "2099-12-31",
  "problem_count": 1,
  "diagnosis_count": 1,
  "goal_count": 1,
  "objective_count": 1,
  "intervention_count": 1,
  "review_data_status": "unavailable_via_rest_without_known_review_id"
}
```

Redacted live route proof from the local API Configuration page on 2026-07-02. The real patient identifier was asserted as visible DOM text by Playwright but is intentionally not committed to docs:

```json
{
  "route": "/api-configuration",
  "action": "Pull Single Patient Treatment Plans",
  "patient_id": "[redacted real synced value asserted in DOM]",
  "status": "ok",
  "source_operation": "GET /clients + GET /treatment-plans?ClientId={source_patient_id}",
  "client_query_parameter": "ClientId",
  "lowercase_clientId_used": false,
  "status_id": "[blank in live response]",
  "status_label": "Active",
  "active_plan_count": 1,
  "total_plan_count": 1,
  "has_multiple_active_plans": false,
  "warning_code": "missing_patient_status_id",
  "review_data_status": "unavailable_via_rest_without_known_review_id",
  "next_review_due_source": "unavailable",
  "evidence": "Playwright DOM assertion plus local AppData screenshot; screenshot is not committed because it contains a real patient identifier."
}
```
