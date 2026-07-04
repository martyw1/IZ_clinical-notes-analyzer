# Alleva Patient Treatment-Plan Aggregate

Date: 2026-07-04

Applies to: IZ Clinical Notes Analyzer Beta Version `1.4.6-beta.1` / build `2026.06.30.1`.

## Purpose

`PatientTreatmentPlanAggregate` is the canonical local model for viewing Alleva patient-level treatment-plan source coverage without turning Alleva into the compliance decision engine. The aggregate combines active-client roster data, treatment plans, treatment reviews when they are safely attributable, diagnosis evidence, advanced-form metadata, deterministic due-date status, data-quality flags, and raw-source provenance.

The model is additive. Existing Treatment Plan Timeliness dashboard behavior, deterministic checklist evaluation, manager review state, manual overrides, local SQLite storage, and sync approval gates remain unchanged.

For the complete patient treatment-plan handling map, including local tables, manual-upload sync, gated Alleva sync, selected-client aggregate route, current-plan content capture, and frontend surfaces, see `docs/patient-treatment-plan-handling.md`.

For the current patient-centered retrieval contract, see `docs/alleva-patient-treatment-plan-data-contract.md`.

## Current Entry Points

- `POST /api/api-configuration/alleva-quick-pull` with `report: "patient_treatment_plan_aggregates"` runs a bounded admin-only dry-run over `GET /clients`, `GET /treatment-plans`, and `GET /treatment-reviews`.
- `POST /api/api-configuration/alleva-quick-pull` with `report: "patient_centered_treatment_plans"`, `"active_patient_centered_treatment_plans"`, or `"single_patient_treatment_plans"` runs the clarified production-style API harness flow: `GET /clients`, then `GET /treatment-plans?ClientId={patient_id}`.
- `GET /api/timeliness/clients/{client_id}/treatment-plan` returns the enriched aggregate for a locally stored timeliness client while preserving the previous `current_plan`, `historical_plans`, and `review_records` keys.
- `POST /api/alleva/treatment-plan-sync/run` remains gated by App settings approval and validated endpoint mapping before live sync can import anything.

Code entry points:

- `backend/app/services/alleva_treatment_plan_aggregate.py`: raw Alleva payload aggregate builder for API-harness dry-runs.
- `backend/app/services/timeliness.py::treatment_plan_aggregate_payload`: aggregate payload for a stored local treatment-plan client.
- `backend/app/api/timeliness_routes.py::get_timeliness_client_treatment_plan_aggregate`: selected-client aggregate route.
- `backend/app/api/api_config_routes.py::run_alleva_quick_pull`: API-harness aggregate dry-run route.

## Aggregate Shape

Top-level fields:

- `schema_version`
- `patient_key`
- `patient`
- `episode`
- `current_treatment_plan`
- `treatment_plans`
- `treatment_reviews`
- `diagnoses`
- `advanced_form_captures`
- `computed_status`
- `data_quality`
- `raw_sources`
- `source_confidence`
- `source_endpoint_count`

The stored timeliness route also keeps legacy fields so current UI and exports do not break: `patient_id`, `permitted_name`, `alleva_ids`, `id_join_confidence`, `current_plan`, `historical_plans`, and `review_records`.

## Identifier Resolver

The older broad aggregate dry-run can still inspect approved identifier aliases before any fallback:

1. `leadId`
2. `clientId`
3. `chartId` / `chartNumber`
4. `mrn`
5. `uniqueId`
6. `luin`
7. source `id` / `href`

Treatment-plan and review records can match by top-level aliases or nested client aliases in diagnostic aggregate mode. Name-only fallback remains disabled by default. When explicitly enabled for validation, it must be unique; ambiguous name matches are rejected and counted as unmatched instead of guessed.

For production patient-plan alignment after the July 2, 2026 Alleva clarification, use the patient-centered contract instead:

- canonical `patient_id` is `GET /clients` field `id`
- treatment plans are pulled per patient with `GET /treatment-plans?ClientId={patient_id}`
- treatment-plan ownership is validated by parsing `client: "/clients/{id}"`
- `chartId`, `externalId`, `mrn`, `clientName`, `clientId`, `uniqueId`, and `source_id` are not production treatment-plan join keys

See `docs/alleva-patient-treatment-plan-data-contract.md`.

## Data Quality Rules

The aggregate does not silently infer compliance. It emits structured data-quality objects with `code`, `severity`, `message`, and `source` for cases such as:

- missing current active treatment plan
- duplicate or ambiguous identifiers
- name fallback use
- active patient with discharge evidence
- complete treatment plan missing staff signature date or content counts
- active client diagnosis missing from the current treatment plan
- displayed Alleva next-review due date disagreeing with deterministic calculated due date
- missing required timeliness evidence
- unavailable treatment-review data through REST without a trusted treatment-review ID

Deterministic timeliness status still comes from the existing R3 rules/checklist engine. The aggregate exposes that result under `computed_status`.

## Raw Source Provenance

`raw_sources` stores source references only:

- endpoint
- method
- source record ID
- SHA-256 payload/source hash
- source record count
- source version when available

Raw upstream payloads, free-text treatment-plan narrative, filenames, API keys, bearer tokens, client secrets, and patient direct identifiers are not returned in aggregate provenance.

## Advanced Forms

Advanced-form captures are represented as metadata, not narrative content. Boolean, integer, decimal, date/time, JSON, file, and signature-like values are typed. File/signature values expose only presence and metadata keys, not filenames, URLs, binary data, or signature images.

`https://api.allevasoft.com/advanced-form-elements` is still a protected Alleva REST path. Runtime use requires R3/Alleva endpoint approval and field mapping.

## Privacy Boundary

Patient-name import/display is opt-in and remains off by default. The aggregate builder and harness default to `include_patient_name: false`; returned records use patient/source identifiers and generated local labels, not Alleva names.

Audit logs store report type, operation, auth mode, counts, outcome, and non-PHI diagnostic codes. They do not store raw returned rows, patient names, uploaded note text, API secrets, bearer tokens, or upstream response bodies.

## Current Swagger/OpenAPI Mapping Evidence

The Alleva Swagger/OpenAPI field mapping export is now available as documentation evidence and is reflected in `docs/alleva-treatment-plan-data-coverage.md`.

Current available mapping files:

- `alleva_api_mapping.metadata.txt`
- `alleva_api_mapping.grid.tsv`
- `alleva_api_mapping.long.tsv`

The export was generated on `2026-06-21 14:59:49` from:

```text
Swagger UI: https://api.allevasoft.com/swagger/index.html
Swagger JSON: https://api.allevasoft.com/swagger/v1/swagger.json
Endpoint count: 424
Unique field count: 2303
```

This resolves the old documentation note that the mapping files were unavailable when the first aggregate model was drafted. It does **not** resolve production sync approval or runtime data validation. The mapping is Swagger/OpenAPI-derived only. Runtime API responses can include fields not documented in Swagger, and Swagger can omit response schemas for endpoints that still return useful runtime data.

Current relevant documented endpoint families include:

- `GET /clients` and `GET /clients/{id}` for roster, active/discharged status, admission/LOC, and patient-centered canonical `id`
- `GET /treatment-plans`, `GET /treatment-plans/{id}`, and `GET /treatment-plans/{id}/diagnosis` for treatment-plan summary/detail/diagnosis evidence
- `GET /treatment-reviews` and `GET /treatment-reviews/{id}` for review evidence only when a trusted review ID or safe linkage exists
- advanced-form endpoints for possible future metadata coverage after R3/Alleva approval

## Verification Coverage

Synthetic tests cover:

- alias matching across `leadId`, `clientId`, nested client IDs, and `luin`
- patient-centered `GET /clients` plus `GET /treatment-plans?ClientId={patient_id}` retrieval
- `client: "/clients/{id}"` ownership parsing and join validation
- ambiguous name fallback rejection
- current-plan selection
- treatment-review due-date disagreement and unavailable-review status
- diagnosis reconciliation flags
- advanced-form value typing without filenames or narrative text
- aggregate route backward compatibility
- quick-pull aggregate dry-run without PHI/name leakage
- audit details that omit patient names and secrets

Run:

```powershell
$env:PYTHONPATH = "$PWD\backend"
.\backend\.venv\Scripts\python.exe -m pytest .\backend\tests -q
cd .\frontend
npm run test -- --run
npm run build
```

## Open Approval Items

Do not enable or rely on live production sync until R3/Alleva confirms:

- tenant/environment and credentials
- token endpoint requirements, scope/audience/tenant parameters, and token auth style
- endpoint mapping for active clients, treatment plans, treatment-plan details, diagnosis details, and advanced forms
- the patient-centered `ClientId` treatment-plan query behavior in the approved tenant
- whether any trusted source can supply stable treatment-review IDs for `GET /treatment-reviews/{id}`
- pagination, date filters, rate limits, and retry behavior
- authoritative signature/date/completion/status fields
- whether production payloads consistently expose `client: "/clients/{id}"` on treatment plans
- PHI handling for patient identifiers, names, and source references
- the unresolved LOC-change treatment-plan update window
