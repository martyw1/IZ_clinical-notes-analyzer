# Alleva API Contract

V2 patient-centered production pulls use:

- `GET /clients`
- `GET /treatment-plans?ClientId={patient_id}`

`patient_id` is the canonical Alleva client ID from `/clients.id`. `ClientId` is case-sensitive and must use uppercase `C` and uppercase `I`. Treatment-plan ownership is validated from raw client references such as `/clients/{id}`.

The app must not use `source_id`, `chartId`, `externalId`, `mrn`, `clientName`, lowercase `clientId`, or `uniqueId` as production join keys. Patient names are not requested, stored, displayed, exported, logged, or used for matching by default.

Live Alleva sync remains gated until official tenant credentials, endpoint mapping, pagination/rate-limit behavior, attachment behavior, vendor documentation, and compliance approval exist.

For `2.0.0-beta.2`, live validation is an external gate: R3/Alleva must approve and supervise a contract and end-to-end sync using approved non-PHI/test records. Synthetic local contract fixtures validate the implementation boundary but do not establish live production readiness.

## Recording the approved mapping in the app

OAuth client credentials prove that the local app may request an access token. They do not identify the endpoint version, patient/plan join fields, pagination behavior, or safe request rate. The app therefore keeps authentication and import approval as separate controls.

After saving the active API connection and enabling the four API/sync controls in App settings, an administrator opens **API Testing Harness** and uses **Approve the published Alleva v1 import mapping**. The one-time form records:

- a unique contract version;
- the approved non-PHI/test population reference;
- the maximum requests per minute confirmed by Alleva; and
- the administrator's confirmation that the endpoint mapping, pagination, rate limit, and test population were validated for R3's tenant.

The form binds the exact saved API base URL, OpenAPI URL, token URL, auth style, and OAuth scope to the published v1 routes. It never sends the saved client ID or secret in the contract payload. After the contract is recorded, **Pull full treatment plans** is enabled on both the Treatment Plans and Patient Roster tabs; either location runs the same import and refreshes both lists.

The operational importer accepts Alleva's numeric IDs and nested `client.id` treatment-plan ownership field. It loads canonical patients from `/clients`, then traverses every bounded `/treatment-plans?ClientId={patient_id}` page for each active patient. Returned ownership values from `client.id`, `client.route`, legacy string `/clients/{id}`, or an explicitly approved equivalent mapping must agree with the queried patient before a plan can be stored. It fetches `/treatment-plans/{id}` plus `/treatment-plans/{id}/diagnosis` for every validated plan, so multiple plans for one patient are preserved. Patient list and plan-detail requests use bounded concurrency, one shared vendor-approved rate limiter, a global 5,000-row safety ceiling, encrypted resumable checkpoints, and serial local database writes. A repeated plan ID updates the existing local row rather than creating a duplicate, and the completion audit reports the updated plan IDs.

The public v1 treatment-review list does not document a trustworthy plan/client foreign-key relationship. The approved template therefore does not attach a global review row to a patient or plan by inference. Review evidence remains missing/unknown until Alleva confirms a stable identifier mapping; the deterministic evaluator must not guess it.
