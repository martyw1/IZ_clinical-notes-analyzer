# Alleva Patient Treatment-Plan Data Contract

Date: 2026-07-02

This contract reflects Alleva technical-team clarifications for patient-centered treatment-plan retrieval in the API Test Harness. The TypeScript contract lives in `frontend/src/types/allevaTreatmentPlan.ts`; backend tests exercise the same shape through the patient-centered harness reports.

## Canonical Keys

- `patient_id` is the canonical Alleva client ID from `GET /clients` field `id`.
- `id` from `GET /clients` is the same value other Alleva contexts may call `leadId`.
- Treatment-plan ownership is validated from the treatment-plan `client` string, expected as `/clients/{id}`.
- `raw_client_ref` stores the original treatment-plan `client` value.
- `extracted_patient_id` / `plan_client_id` stores the parsed `{id}` from `/clients/{id}`.
- `join_validated` is `true` only when `extracted_patient_id` equals the queried `patient_id`.

## Disallowed Join Keys

Do not use these as treatment-plan join keys:

- `source_id`
- `chartId`
- `externalId`
- `mrn`
- `clientName`
- `clientId`
- `uniqueId`

`source_id` may remain a display/reference field when present, but it is not an alignment key.

## ClientId Query Casing

The production patient-plan pull is:

```text
GET /clients
GET /treatment-plans?ClientId={patient_id}
```

`ClientId` is case-sensitive. Lowercase `clientId` is not used in the production patient-centered sync path.

## Client Reference Parsing

For each returned treatment plan:

1. Preserve `client` as `raw_client_ref`.
2. Parse `/clients/{id}`.
3. Store `{id}` as `extracted_patient_id` and `plan_client_id`.
4. Compare it with the `patient_id` used in the `ClientId` query.
5. Preserve plans with blank, malformed, or mismatched refs, but set `join_validated = false` and add a specific warning.

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

A client can have multiple active treatment plans.

- Store all plans.
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
  "source_operation": "GET /clients + GET /treatment-plans?ClientId={patient_id}",
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
