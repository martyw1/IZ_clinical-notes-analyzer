# Current V2 UI workflows

Source **1.0.1 / build 2026.10.12.1 / stable-local-desktop**. V2 names the internal architecture. Browser title is R3 Treatment Plan Audit Application; current footer/API identify version 1.0.1 and build 2026.10.12.1, not a beta footer. Version identity does not certify clinical or deployment readiness.

## Access and navigation

Sign in with an assigned account, replace a temporary password when required, then save/acknowledge recovery setup before workspace access. Account supports password change and one-time recovery replacement. Administrator navigation/detail surfaces include Dashboard, Patient Roster, Patient Record Detail, Treatment Plan Detail, Treatment Plans Roster, Manual Upload, API Testing Harness, Users, Forensic Logs, Settings and Help. Office-manager actions are limited by role/facility; administrator training screenshots do not grant extra permissions.

## Patient and saved-plan selection

Patient Roster shows authorized source-scoped patient rows, including patients without plans. It displays full names when available from authorized encrypted snapshots, MRN and source metadata. Selecting an MRN opens Patient Record Detail; selecting a plan opens exact Treatment Plan Detail. Plan options order by source last-updated time, not import/access time. Missing values remain unavailable.

Treatment Plans Roster includes latest saved **Manual and Alleva** plans, with authorized name/source/MRN/plan/lineage data. Source and status filters apply to saved local records. Exact selection carries `patientRecordId`, `planVersionId`, source mode and plan ID, in addition to MRN. Identical MRNs/plan IDs in another source/facility cannot collapse into one selection. A new import does not silently replace the saved version already open; use the version selector to inspect history.

## Evidence and actions

Treatment Plan Detail renders clinical content hierarchy, signatures/reviews, source/calculated dates, LOC history, warnings, 42-step checklist, evidence coverage, source archive and bounded raw-field diagnostics. Open a criterion to inspect evidence before approving/returning/commenting or using an authorized override with a reason. Manager actions/corrections/exports stay exact-version scoped. CSV can include off-screen filtered rows and sensitive identifiers/dates while omitting names/narrative; use approved sharing.

Settings clinical intervals are read-only. The LOC seven-calendar-day candidate remains unvalidated Needs Review. Optional LLM is disabled by default and unnecessary for deterministic decisions. [Current rules](rules-contract.md).

## Imports and jobs

Manual Upload shows parsing warnings and saved exact identity. Opaque archival is not successful clinical extraction. Authorized administrators can pull patients separately from full plans when approved connection/read-only/live-import gates are satisfied. Diagnostic harness previews do not populate the operational roster merely by testing a connection. Jobs show bounded progress, safe errors and supported cancel/artifact/preview controls; wait for completion and inspect failure/warning counts before another large job.

[Current operator help](../operator-help-current.md), [data contract](data-contract.md), [patient implementation map](../patient-treatment-plan-handling.md) and [October 12 verification](../validation/current-work-2026-10-12.md) provide details. Dated beta UI evidence describes its original scope.
