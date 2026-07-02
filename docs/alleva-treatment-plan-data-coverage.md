# Alleva Treatment-Plan Data Coverage Matrix

Date: 2026-06-26

Applies to: IZ Clinical Notes Analyzer Beta Version `1.4.6-beta.1` / build `2026.06.30.1`.

## Source Map

This matrix is based on the supplied Alleva Swagger/OpenAPI mapping export:

- `alleva_api_mapping.metadata.txt`, generated `2026-06-21 14:59:49`
- Swagger UI: `https://api.allevasoft.com/swagger/index.html`
- Swagger JSON used: `https://api.allevasoft.com/swagger/v1/swagger.json`
- Export size: 424 endpoints and 2303 unique fields

Important limitation: the export is derived from Swagger/OpenAPI only. Runtime API responses may include fields not documented in Swagger, and endpoints without response schemas are marked `__NO_RESPONSE_SCHEMA_IN_ALLEVA_SWAGGER__`. Live production import remains gated until R3/Alleva approves endpoint mapping, pagination behavior, tenant credentials, rate limits, attachment behavior, and compliance use.

For how these fields flow into local treatment-plan rows, aggregate diagnostics, deterministic timeliness status, selected-client checklist results, and the Treatment Plans UI, see `docs/patient-treatment-plan-handling.md`.

## Identifier Contract

The app now keeps these identifiers separate:

- Current patient-centered API harness contract: `patient_id` is `GET /clients.id`; treatment plans are pulled with `GET /treatment-plans?ClientId={patient_id}` and joined only by parsing treatment-plan `client: "/clients/{id}"`. See `docs/alleva-patient-treatment-plan-data-contract.md`.
- `app_patient_id`: the local Treatment Plan Timeliness patient key. For Alleva client records this prefers `clientId`, then falls back to `id`, `leadId`, `chartId` / `chartNumber`, `luin`, `uniqueId`, or `mrn`.
- `source_id` / `internal_client_id`: the Alleva source/internal client identifier, commonly `id`.
- `source_client_id`: endpoint-specific nested client identifier, commonly `client.id` under treatment-plan records.
- `treatment_plan_id`: the Alleva treatment-plan or treatment-review record identifier.
- `chart_id` / `luin` / `unique_id` / `mrn`: additional source identifiers used for diagnostics and lookup aliases when the primary client ID is absent.

Example canary covered by tests: a patient may appear with `uniqueId = RM340328`, `source_id = 40328`, and `app_patient_id = 30268`. The app must not treat those as interchangeable.

## Coverage Matrix

| Completeness/timeliness rule or diagnostic | Field needed | Endpoint | Raw API field name | Normalized app field | Identifier required | Coverage status | App behavior when missing | Missing means source missing vs unknown | Tests |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Active patient/client roster | Active/discharged/inactive status | `GET /clients`, candidate `GET /clients/list` | `status`, `isClient`, `isDischarge`, `dischargeDateTime`, `actualSysDischargeDateTime` | `status_scope`, `is_active` | None for roster; `Limit`/`Cursor` for paging | Required | Excluded rows are counted with exclusion reasons; ambiguous rows are not silently treated as active | Only "missing from source" after the endpoint was paginated fully; otherwise "Not retrieved / unknown" | `backend/tests/test_api_connectivity.py::test_api_configuration_alleva_quick_pull_computes_summaries_without_logging_rows` |
| Admission / episode anchor | Admission date | `GET /clients`, candidate `GET /clients/list` | `admissionDateTime`, `admissionDate` | `admission_date`, `first_admitted` | `clientId`/`id` mapping from roster | Required | Timeliness result becomes `Missing Data` or source reliability remains unknown if roster/detail retrieval was incomplete | Missing only if fully retrieved client record lacks admission date | `backend/tests/test_treatment_plan_timeliness.py::test_timeliness_missing_data_and_manual_override_are_audited` |
| Current level of care | LOC value and configured cadence | `GET /clients` | `levelOfCare` | `current_level_of_care`, LOC interval | `clientId`/`id` mapping from roster | Required | Timeliness result becomes `Missing Data` if the retrieved LOC is blank or unmapped | Missing only if client record retrieved and lacks mapped LOC | `backend/tests/test_treatment_plan_timeliness.py::test_timeliness_due_date_boundary_windows` |
| Client/source ID mapping | External and internal IDs | `GET /clients` | `clientId`, `id`, `leadId`, `uniqueId`, `mrn` | `patient_id`, `source_id`, `internal_client_id`, `id_mapping_summary` | None for roster | Required | Diagnostics show mapped/unmapped counts; no name-only matching | Unknown until roster retrieval completes | `backend/tests/test_api_connectivity.py::test_api_configuration_alleva_quick_pull_computes_summaries_without_logging_rows` |
| Treatment-plan roster | Treatment-plan record ID and linked client | `GET /treatment-plans` | `id`, `client.id`, `client.clientId`, `client.leadId`, `isActive`, `isComplete`, `startDate`, `endDate`, `lastModified` | `treatment_plan_id`, `source_client_id`, `is_active`, `is_complete`, `document_date` | `client.id`/aliases matched to client roster | Required | Unmapped treatment plans are counted and block confidence in completeness | Unknown if treatment-plan endpoint fails, is partial, or reaches sync limit | `backend/tests/test_treatment_plan_timeliness.py::test_alleva_rest_payloads_sync_into_r3_timeliness_engine` |
| Treatment-plan problems/goals/objectives/interventions | Nested clinical structure presence | `GET /treatment-plans`, `GET /treatment-plans/{id}` | `problems[].description`, `problems[].goals[].description`, `objectives[].description`, `interventions[].description` | Coverage flags in deep inspection; derived checklist source coverage only | `treatment_plan_id` plus mapped client ID | Required for full 42-step readiness if approved for use | If not retrieved, selected-client diagnostic shows "Not retrieved / unknown"; if Swagger lacks field, shows "Not exposed by API" | Unknown until runtime detail response is verified for the selected treatment plan | `backend/tests/test_api_connectivity.py::test_api_configuration_alleva_quick_pull_computes_summaries_without_logging_rows` |
| Treatment-plan signatures | Staff/client/guardian signature dates | `GET /treatment-plans`, `GET /treatment-reviews` | `clientSignature.signatureDateTime`, `guardianSignature.signatureDateTime`, runtime aliases such as `staffSignatureDate`, `creatorSignatureDate`, `therapistSignatureDate` | `client_signature_date`, `staff_signature_date`, `reviewer_signature_date` | `treatment_plan_id` plus mapped client ID | Required | Missing signature dates keep the plan in `Needs Review` or `Missing Data` rather than compliant | Missing only after relevant plan/review endpoint was retrieved fully | `backend/tests/test_treatment_plan_timeliness.py::test_alleva_rest_payloads_sync_into_r3_timeliness_engine` |
| Ongoing review date | Latest valid review/update timestamp | `GET /treatment-reviews`, fallback `GET /treatment-plans` | `createdDated`, `createdDate`, `generatedDate`, `creatorSignatureDate`, `staffSignatureDate` | `last_valid_review_date`, date-clock anchor | Runtime client linkage or mapped nested client ID | Required | App falls back to admission date only when no valid review/update date exists and labels the anchor source | Unknown if treatment-review endpoint is unavailable or cannot map review to client | `backend/tests/test_treatment_plan_timeliness.py::test_api_style_treatment_plan_repull_updates_record_and_reevaluates` |
| Displayed next review due | Source-document due date | `GET /treatment-reviews` | `nextReviewDue`, `nextReviewDueDate`, `displayedNextReviewDueDate` | `displayed_next_due_date`, `document_next_due_date` | Runtime review-to-client mapping | Optional but important | Missing source-document due date is shown separately from calculated due date | Missing only if treatment review was retrieved and field absent; otherwise unknown | `backend/tests/test_treatment_plan_timeliness.py::test_timeliness_due_date_conflict_stays_needs_review` |
| LOC-change update clock | LOC effective date and LOC-change window | `GET /clients` plus app settings | `levelOfCare`, admission/discharge fields; app setting `treatment_plan_loc_change_window_days` | `loc_effective_date`, `loc_change_due_date` | Client roster mapping | Required when LOC history has more than one row | LOC-change rule remains `Needs Review` while R3/Marleigh validation is unchecked | Not an Alleva-only missing state; unresolved business rule is documented separately | `backend/tests/test_treatment_plan_timeliness.py::test_timeliness_dashboard_surfaces_iop_5_loc_anchor_ambiguity` |
| Counselor/manager content update markers | Content last-updated by role | Not documented in current Swagger mapping | Not exposed by supplied mapping | `not_exposed_by_api` diagnostic | Runtime-only if vendor exposes it later | Unavailable | UI/report marks as `Not exposed by API`; app does not invent values | Unavailable from Swagger, not proof of absence in runtime responses | Source diagnostics and `docs/alleva-treatment-plan-data-coverage.md` |
| Review-to-client linkage | Client ID on treatment review | `GET /treatment-reviews` | Swagger prominently documents `clientName`; runtime may include `client.id`, `clientId`, `leadId`, or `patientId` | `review_identifier_summary`, mapped review count | Runtime ID alias required | Runtime-only | Name-only matching is disabled; unmapped reviews are counted and excluded | Unknown until runtime response proves an ID linkage | `backend/tests/test_treatment_plan_timeliness.py::test_alleva_rest_payloads_sync_into_r3_timeliness_engine` |
| Pagination completeness | Complete page traversal | `GET /clients`, `GET /treatment-plans`, `GET /treatment-reviews` | `Limit`, `Cursor`, optional `StartDate`, `EndDate`, `api-version`, `X-Version` | `page_count`, `complete`, `pagination_warning` | Endpoint-specific cursor | Required | Partial pulls warn/block sync; quick-pull reports page counts and warnings | Unknown if endpoint stops at configured limit or max pages | `backend/tests/test_api_connectivity.py::test_api_configuration_alleva_quick_pull_computes_summaries_without_logging_rows` |
| API error / cannot evaluate | Endpoint error stage | All required endpoints | HTTP status, timeout, vendor response category | `latest_source_pull_status`, `partial_retrieval_warnings`, `api_error` | Endpoint path and auth context | Required diagnostic | Evaluation is qualified as partial/unknown; sync blocks on required endpoint failures | Unknown until endpoint is retried successfully | `backend/tests/test_system_and_emr_readiness.py::test_manual_alleva_sync_warns_on_optional_treatment_reviews_unauthorized` |
| Manager review history | Manager status/comments per element | Local app database | `treatment_plan_criterion_reviews.status`, `comment`, `updated_at` | `manager_status`, `manager_comment`, report rows | Local app client ID and criterion key | Required local state | API pulls refresh source data without deleting manager reviews or overrides | Local app state, not Alleva source data | `backend/tests/test_treatment_plan_timeliness.py::test_timeliness_criterion_reviews_persist_and_are_audited_without_comments` |
| Report/export provenance | Export type, filters, row count | Local app audit log | `timeliness.report.exported` details | Non-PHI export audit details | Report type/filter only | Required | Audit logs row counts and filter metadata, not report content or comments | Not a source-data field | `backend/tests/test_treatment_plan_timeliness.py::test_timeliness_reports_export_csv_html_and_audit_without_comment_leak` |

## Current App Behavior

- API harness quick pulls and treatment-plan sync use the shared retrieval normalizer for pagination, status scope, ID mapping, and redacted samples.
- The patient-centered API harness reports (`patient_centered_treatment_plans`, `active_patient_centered_treatment_plans`, and `single_patient_treatment_plans`) use `ClientId` per patient and expose `review_data_status = "unavailable_via_rest_without_known_review_id"` because treatment reviews cannot be listed/joined by patient through REST alone.
- The API harness can run a `patient_treatment_plan_aggregates` dry-run that combines active clients, treatment plans, and treatment reviews into JSON aggregates with endpoint coverage, identifier matching, diagnosis reconciliation, completeness, due-date, and PHI-minimized source diagnostics.
- Quick-pull responses show endpoint, method, query parameters, page count, returned/excluded record counts, raw redacted sample, normalized sample, ID mapping, and warnings.
- Deep inspection lets an admin enter a patient/source/client/treatment-plan identifier and compare `/clients`, `/treatment-plans`, and optionally `/treatment-reviews` data with a merged normalized model.
- The Treatment Plan Timeliness dashboard exposes last successful source pull time, latest pull status/message, latest pull record count, excluded/unmapped count, partial retrieval warnings, current filters, manager review pending count, unknown retrieval count, and API error count.
- Selected-client detail exposes source diagnostics: source records retrieved, missing-from-source fields, not-retrieved/unknown fields, not-exposed-by-API fields, and source warnings.
- Reports are available as CSV or printable HTML for manager summary, counselor action, patient assessment, overdue/due-soon, source-data gaps, review history, completeness snapshot, timeliness snapshot, and API/source pull summary. Export filenames use timestamps and do not include patient names or patient IDs.

## Remaining Runtime Verification

The Swagger mapping does not prove production runtime payloads. Before any live import is treated as reliable for compliance decisions, R3/Alleva still needs to verify:

- Whether a trusted source can provide `treatmentPlanReviewId` values for `GET /treatment-reviews/{id}`. Do not rely on a review list endpoint or `clientName` join.
- Whether production treatment-plan payloads consistently expose the documented `client` string shape `/clients/{id}`.
- Whether staff/creator/therapist signature date fields are present and authoritative for every required treatment-plan document type.
- Whether treatment-plan content update timestamps by counselor or manager are exposed by any endpoint.
- Whether `/treatment-plans/{id}` adds fields beyond summary `/treatment-plans`.
- Exact pagination cursor behavior, rate limits, and behavior when the configured `Limit` equals the real result size.
- Whether additional endpoints without Swagger response schemas carry required treatment-plan detail fields.
