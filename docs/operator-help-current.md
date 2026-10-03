# Operator help: current local desktop app

Applies to the `1.0.0` / `2026.09.21.2` source candidate on `stable-local-desktop`. The running footer and `/api/version` identify the build actually open on the laptop. This guide describes the current V2 interface; older beta screenshots and Version 1 guides are historical.

## Video introduction

[Watch the administrator introduction and help video](help/R3-Treatment-Plan-Audit-Quick-Start.mp4) (6 minutes 13 seconds). It uses example records and shows all administrator tabs and numbered desktop tools. [Video help and transcript](help/README.md).

## Start and sign in

1. Double-click the prepared IZ Clinical Notes Analyzer desktop or Start Menu shortcut. If the launcher is already running, open `http://localhost:8000` on this laptop.
2. Sign in with the assigned app account. Replace a temporary password when prompted.
3. Open Status Dashboard. Check the version footer, source readiness, unresolved blockers, and counts before working on a plan.
4. Sign out and lock Windows when finished.

The normal prepared desktop release does not require Windows administrator access, Docker, PostgreSQL, Git, Node.js, or command-line work. Local app data is under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`; do not move or edit its database or encryption files individually.

## Find an exact patient and plan

1. In Patient Roster, search by MRN, authorized name, plan ID, original reference, or service date. Use the Source filter when needed. A patient may appear without a treatment plan.
2. Open the MRN to see Patient Record Detail. Open a saved plan using its selector, or start in Treatment Plans Roster and filter by source/status.
3. Confirm the source, patient record number, external plan ID, and immutable saved version ID. MRNs and external IDs may repeat across sources or facilities. A name alone is not a match key.
4. On Treatment Plan Detail, inspect the selected saved version and its history. Importing another version does not silently change an existing selection.

Missing names, original references, and service dates remain unavailable or not supplied; the app does not invent them. An empty roster may mean a filter is active, the source has not been pulled, or the pull failed. Clear filters and inspect the last job before concluding that records are absent.

## Interpret clinical timing

The 42-step checklist and versioned rule package are the active clinical timing source. The initial plan is checked for an admission Day-1 signature. A signed master plan is due within **30 calendar days after admission**. Recurring PHP reviews use **30 calendar days**; IOP variants and OP/Outpatient use **60 calendar days**. The recurring clock uses the latest valid signed review, or admission when there is no valid signed review. The calculated due date is compared with the source Next Review Due date.

| Overall status | What to inspect |
| --- | --- |
| Overdue | A confirmed deadline has passed. Inspect the master-plan and recurring-review criteria separately. |
| Urgent | Recurring review is due today or tomorrow. |
| Due Soon | Recurring review is two through seven days away. |
| Current/Compliant | Evaluated timing is in window. Still inspect source evidence and checklist findings before a clinical conclusion. |
| Missing Data | A required plan, signature, or date is absent. |
| Conflicting Evidence | Source and calculated dates, or other required evidence, disagree. |
| Unable to Evaluate | A date or level of care cannot be interpreted under the active rules. |
| Needs Review | Human resolution is needed, including LOC changes or a Day-1 signature mismatch. |

**LOC-change boundary:** The displayed seven-calendar-day date is a provisional *candidate*, not an enforced compliance deadline. The change remains `Needs Review` until R3/Marleigh confirms the number of days, calendar versus business counting, and the clock start. Do not approve an LOC-change case solely because the candidate date appears to be met.

Settings shows the active clinical values read-only. Saving organization or facility timezone does not change clinical intervals. Clinical timing changes require a reviewed, versioned rule update, tests, and release validation. Readiness continues to flag the unresolved LOC-change policy.

## Review evidence and record an action

1. Compare admission, source due date, computed due date, signed reviews, master signature, LOC history, and data-quality warnings on Treatment Plan Detail.
2. Search the 42-step checklist and open the relevant criterion for its safe evidence and source path. A top-level status is a queue signal, not a substitute for criterion review.
3. Resolve missing or conflicting data against the source document. Use authorized correction, return, approval, comment, or override controls according to your role.
4. Supply the required reason for an override. An override documents a manager decision; it does not rewrite the source or validate the unresolved LOC-change policy.

Filtered CSV export includes all matching rows, including those below the visible viewport. It omits patient names and narrative text. Verify selection and share only through an approved R3 channel.

## Import records

**Manual Upload:** Choose approved binder files. Provide an MRN correction only after checking the source. Read extraction and processing warnings, then open the exact saved plan. Encrypted storage alone does not mean content was parsed or found compliant.

**Patient roster pull:** An authorized administrator can use **Pull patient roster** on Patient Roster. This refreshes patient records and does not require treatment plans. Wait for the job to finish and inspect seen, updated, warning, and failure counts.

**Treatment-plan pull:** An authorized administrator can use **Pull full treatment plans** on Treatment Plans Roster when the saved Alleva connection and approved read-only import controls are ready. The app retrieves source records, normalizes them, evaluates them, and populates the local roster. Check the completed job and resulting roster; a successful OAuth or connectivity test alone does not prove a complete import. Do not start duplicate jobs while a pull is active.

**API Testing Harness:** Use bounded diagnostic pulls and redacted previews for connection or mapping questions. It does not replace review of the saved patient and plan records. Report a failed phase and safe error summary to R3 support; do not send raw vendor responses or credentials.

## Accounts, troubleshooting, and support

- Open Account to change your password or create a replacement recovery code. The code appears once and works once. Keep it privately. Use Forgot password with your username and saved code, or ask an authorized administrator for a reset.
- Administrators manage staff accounts in Users and can inspect Forensic Logs. Screens and actions are role-limited. Settings controls organization, timezone, and the authorized API connection.
- If the page does not open, confirm the launcher is running and try `http://localhost:8000`. If a roster looks old, clear filters and inspect the latest pull job. If a plan status looks wrong, open the exact version and compare its source dates and checklist criteria.
- For support, provide the app version, approximate time, screen, job phase, and a non-PHI error message through an approved R3 channel. Keep patient narratives, passwords, recovery codes, raw logs, and API credentials out of ordinary chat or email.

For support staff updating this source checkout, consult `README.md`, `docs/runbook.md`, and `docs/open-blockers.md`. Ordinary client use does not require pulling Git or running scripts.
