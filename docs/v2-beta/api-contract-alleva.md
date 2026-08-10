# Alleva API Contract

V2 patient-centered production pulls use:

- `GET /clients`
- `GET /treatment-plans?ClientId={patient_id}`

`patient_id` is the canonical Alleva client ID from `/clients.id`. `ClientId` is case-sensitive and must use uppercase `C` and uppercase `I`. Treatment-plan ownership is validated from raw client references such as `/clients/{id}`.

The app must not use `source_id`, `chartId`, `externalId`, `mrn`, `clientName`, lowercase `clientId`, or `uniqueId` as production join keys. Patient names are not requested, stored, displayed, exported, logged, or used for matching by default.

Live Alleva sync is disabled by default. It requires a saved client ID and encrypted secret, API and sync enablement, and explicit administrator authorization for live read-only import on the tenant.

For `2.0.0-beta.2`, live validation is an external gate: R3/Alleva must approve and supervise a contract and end-to-end sync using approved non-PHI/test records. Synthetic local contract fixtures validate the implementation boundary but do not establish live production readiness.

## Automatic published mapping

OAuth client credentials prove that the local app may request an access token. When a pull starts, the app automatically binds the published Alleva v1 routes to the saved API base URL, token URL, auth style, OAuth scope, pagination limit, sync limit, and configurable application request ceiling. The encrypted internal mapping record retains a version, checksum, effective time, and administrator identity for audit provenance. No mapping-approval form is required, and a previously submitted custom contract cannot override the canonical built-in mapping.

After the administrator saves the connection, enables API use and treatment-plan sync, and authorizes live read-only import for the tenant, **Pull full treatment plans** is enabled on the API Testing Harness, Patient Roster, and Treatment Plans Roster tabs. Each location runs the same importer and refreshes the operational lists.

The operational importer accepts Alleva's numeric IDs and nested `client.id` treatment-plan ownership field. It loads canonical patients from `/clients`, then traverses every bounded `/treatment-plans?ClientId={patient_id}` page for each active patient. Returned ownership values from `client.id`, `client.route`, or a string `/clients/{id}` must agree with the queried patient before a plan can be stored. It fetches `/treatment-plans/{id}` plus `/treatment-plans/{id}/diagnosis` for every validated plan, so multiple plans for one patient are preserved. Patient list and plan-detail requests use bounded concurrency, one shared configurable application rate ceiling, a global 5,000-row safety ceiling, encrypted resumable checkpoints, and serial local database writes. A repeated plan ID updates the existing local row rather than creating a duplicate, and the completion audit reports the updated plan IDs. Local detail and roster identity also includes `source_mode`, preventing a manual record and an Alleva record with matching patient/plan IDs from collapsing into one selection.

The public v1 treatment-review list does not document a trustworthy plan/client foreign-key relationship. The approved template therefore does not attach a global review row to a patient or plan by inference. Review evidence remains missing/unknown until Alleva confirms a stable identifier mapping; the deterministic evaluator must not guess it.
