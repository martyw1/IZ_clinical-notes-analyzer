# Alleva API Contract

The V2 operational roster and treatment-plan importer uses:

- `GET /clients`
- bounded pages of `GET /treatment-plans` without a patient filter

`/clients.mrn` is the canonical local patient key and the value displayed as MRN. `/clients.id` is retained separately as `source_patient_id` only for validating each treatment plan's Alleva relationship. Treatment-plan ownership from `client.id`, `client.route`, or a string `/clients/{id}` must resolve to one source patient ID, which is then mapped to that client's MRN.

The app must not substitute `/clients.id`, `source_id`, `chartId`, `externalId`, `clientName`, lowercase `clientId`, or `uniqueId` for MRN as the local patient identity. Patient source snapshots may retain full client objects encrypted at rest and authorized views may display names from those snapshots. Names must never substitute for source ID/MRN relationships and must remain absent from forensic details, diagnostic exports and ordinary logs. Exact local patient-record and saved-plan-version identities govern authorization/selection.

Live Alleva sync is disabled by default. It requires a saved client ID and encrypted secret, API and sync enablement, and explicit administrator authorization for live read-only import on the tenant.

For current source `1.0.1` / build `2026.10.12.1`, live validation remains an external gate: R3/Alleva must approve and supervise a contract and end-to-end sync using approved non-PHI/test records. Synthetic local contract fixtures validate the implementation boundary but do not establish live production readiness.

## Automatic published mapping

OAuth client credentials prove that the local app may request an access token. When a pull starts, the app automatically binds the published Alleva v1 routes to the saved API base URL, token URL, auth style, OAuth scope, pagination limit, sync limit, and configurable application request ceiling. The encrypted internal mapping record retains a version, checksum, effective time, and administrator identity for audit provenance. No mapping-approval form is required, and a previously submitted custom contract cannot override the canonical built-in mapping.

After an administrator saves the approved connection, enables the required API/sync controls and authorizes live read-only tenant import, **Pull full treatment plans** on Treatment Plans Roster and the API Testing Harness runs the operational plan importer. **Pull patient roster** on Patient Roster is a separate operation that refreshes patient source records, including patients without treatment plans; it does not perform the full plan pull. Inspect the corresponding job results and warnings for each operation.

The operational importer accepts Alleva's numeric IDs and nested `client.id` treatment-plan ownership field. It loads clients from `/clients`, requires each importable client to provide both `id` and `mrn`, then traverses the complete bounded global `/treatment-plans` collection. It does not filter out inactive, discharged, deleted, older, or superseded records during collection. Returned ownership values from `client.id`, `client.route`, or a string `/clients/{id}` must agree before the plan is mapped to the matching `/clients.mrn`. It fetches `/treatment-plans/{id}` plus `/treatment-plans/{id}/diagnosis` for every validated plan, so the full plan history for each MRN is preserved. Collection and detail requests use one shared configurable application rate ceiling, a 5,000-row safety ceiling, encrypted resumable checkpoints, bounded detail concurrency, and serial local database writes. A repeated plan ID updates the existing local row rather than creating a duplicate, and the completion audit reports the updated plan IDs. Local detail and roster identity also includes `source_mode`, preventing a manual record and an Alleva record with matching MRN/plan IDs from collapsing into one selection.

The public v1 treatment-review list does not document a trustworthy plan/client foreign-key relationship. The approved template therefore does not attach a global review row to a patient or plan by inference. Review evidence remains missing/unknown until Alleva confirms a stable identifier mapping; the deterministic evaluator must not guess it.


October 12 current boundary: [operator help](../operator-help-current.md), [rules contract](rules-contract.md), [runbook](../runbook.md) and [current validation](../validation/current-work-2026-10-12.md) govern current instructions. Clinical intervals are read-only in Settings; LOC timing remains unvalidated. Live Alleva use requires explicit external approval. Historical beta results do not qualify a new package.
