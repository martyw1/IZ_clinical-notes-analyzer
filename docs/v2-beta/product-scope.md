# Current V2 product scope

Source **1.0.1 / build 2026.10.12.1 / stable-local-desktop**. Browser product: R3 Treatment Plan Audit Application. V2 names internal architecture, not an active beta release.

The single-user local Windows workflow starts with Dashboard and Patient Roster, then Patient Record Detail and an exact saved Treatment Plan Detail. Treatment Plans Roster browses latest saved Manual and Alleva plans. Features include encrypted point-in-time manual sources, bounded extraction/warnings, saved immutable plan history, 42-step checklist/evidence coverage, authorized manager actions/corrections/exports, password/recovery setup and safe forensic audit metadata.

Administrators additionally manage Users, Settings, API Testing Harness and Forensic Logs. Live Alleva operations remain conditional on approved tenant credentials, read-only authorization, mapping/pagination/rate-limit validation and compliance approval. Diagnostic jobs and connection tests are readiness evidence, not full import approval. Patient roster pull and full plan pull are distinct operations.

Authorized names may appear from encrypted patient snapshots. Names do not determine identity joins and must remain absent from logs/diagnostic exports. Exact source/facility, patient-record ID and saved-plan-version identity prevent ambiguous MRN/plan selections. Missing evidence remains unresolved rather than guessed.

Clinical decisions remain deterministic and require no LLM; optional LLM is disabled by default. Settings clinical intervals are read-only. LOC-change seven-day date is an unvalidated candidate and cases remain Needs Review pending a reviewed R3 policy/rule release. The app does not certify HIPAA compliance, authorize live imports or establish whole-device protection/device-loss recovery by software alone.

See [current operator help](../operator-help-current.md), [rules](rules-contract.md), [data contract](data-contract.md), [assessment](../security/appliance-assessment-2026-10-12.md) and [current validation](../validation/current-work-2026-10-12.md). Older beta scope/results retain their dated evidence limits.
