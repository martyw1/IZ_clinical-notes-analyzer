# Alleva Patient Treatment-Plan Aggregate

Date: 2026-06-30

Applies to: IZ Clinical Notes Analyzer Beta Version `1.4.6-beta.1` / build `2026.06.30.1`.

## Purpose

`PatientTreatmentPlanAggregate` is the canonical local model for viewing Alleva patient-level treatment-plan source coverage without turning Alleva into the compliance decision engine. The aggregate combines active-client roster data, treatment plans, treatment reviews, diagnosis evidence, advanced-form metadata, deterministic due-date status, data-quality flags, and raw-source provenance.

The model is additive. Existing Treatment Plan Timeliness dashboard behavior, deterministic checklist evaluation, manager review state, manual overrides, local SQLite storage, and sync approval gates remain unchanged.

For the complete patient treatment-plan handling map, including local tables, manual-upload sync, gated Alleva sync, selected-client aggregate route, current-plan content capture, and frontend surfaces, see `docs/patient-treatment-plan-handling.md`.

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

The stored timeliness route also keeps the legacy fields so current UI and exports do not break: `patient_id`, `permitted_name`, `alleva_ids`, `id_join_confidence`, `current_plan`, `historical_plans`, and `review_records`.

## Identifier Resolver

The older aggregate dry-run used approved identifier aliases before any fallback:

1. `leadId`
2. `clientId`
3. `chartId` / `chartNumber`
4. `mrn`
5. `uniqueId`
6. `luin`
7. source `id` / `href`

Treatment-plan and review records can match by top-level aliases or nested `client` aliases. Name-only fallback remains disabled by default. When explicitly enabled for validation, it must be unique; ambiguous name matches are rejected and counted as unmatched instead of guessed.

For production patient-plan alignment after the July 2, 2026 Alleva clarification, use the patient-centered contract instead:

- canonical `patient_id` is `GET /clients` field `id`
- treatment plans are pulled per patient with `GET /treatment-plans?ClientId={patient_id}`
- treatment-plan ownership is validated by parsing `client: "/clients/{id}"`
- `chartId`, `externalId`, `mrn`, `clientName`, `clientId`, and `uniqueId` are not treatment-plan join keys

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

## Verification Coverage

Synthetic tests cover:

- alias matching across `leadId`, `clientId`, nested client IDs, and `luin`
- ambiguous name fallback rejection
- current-plan selection
- treatment-review due-date disagreement
- diagnosis reconciliation flags
- advanced-form value typing without filenames or narrative text
- aggregate route backward compatibility
- quick-pull aggregate dry-run without PHI/name leakage
- audit details that omit patient IDs and secrets

Run:

```powershell
$env:PYTHONPATH = "$PWD\backend"
.\backend\.venv\Scripts\python.exe -m pytest .\backend\tests -q
cd .\frontend
npm run test -- --run
npm run build
```

## Known Missing Inputs

The following user-mentioned mapping/source files were not present in this checkout when this aggregate was implemented, so the implementation is based on the in-repo Alleva coverage docs and existing synthetic tests:

- `alleva_api_mapping.metadata.txt`
- `alleva_api_mapping.grid.tsv`
- `alleva_api_mapping.long.tsv`
- `allevasoft_api_data.json`
- `allevasoft_api_data.xlsx`
- `alleva_v1.json`
- `alleva_v2.json`
- `swagger.json`

If those files become available, use them to update the coverage matrix and add new synthetic fixtures before enabling any production import.

## Open Approval Items

Do not enable or rely on live production sync until R3/Alleva confirms:

- tenant/environment and credentials
- endpoint mapping for active clients, treatment plans, reviews, diagnosis details, and advanced forms
- pagination, date filters, rate limits, and retry behavior
- authoritative signature/date/completion fields
- whether `GET /treatment-reviews` consistently returns stable client identifiers
- PHI handling for patient names and source identifiers
- the unresolved LOC-change treatment-plan update window
