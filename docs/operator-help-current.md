# Operator help: current local desktop app

Applies to the `1.0.2` / `2026.10.16.1` source candidate on `stable-local-desktop`. The running footer and `/api/version` identify the build actually open on the laptop. Reviewed November 9, 2026 for the current checkout. Older screenshots and Version 1 guides are historical.

[Open the complete offline HTML guide](guides/current/Marleigh-Setup-Install-and-User-Guide.html). It includes installation, first-use recovery, daily work, backup and troubleshooting.

## Video introduction

[Watch the administrator introduction and help video](help/R3-Treatment-Plan-Audit-Quick-Start.mp4) (6 minutes 13 seconds). The October 3 recording uses synthetic records and shows the administrator tabs and tools available at the time. [Video help and transcript](help/README.md).

## Start and sign in

1. Double-click the prepared IZ Clinical Notes Analyzer desktop or Start Menu shortcut. If the launcher is already running, open `http://localhost:8000` on this laptop.
2. Sign in with the assigned app account. Replace a temporary password when prompted. Set up account recovery when required: save the one-time code privately and acknowledge that you saved it before entering the workspace.
3. Open Status Dashboard. Check the version footer, source readiness, unresolved blockers, and counts before working on a plan.
4. Sign out and lock Windows when finished.

The normal prepared desktop release does not require Windows administrator access, Docker, PostgreSQL, Git, Node.js, or command-line work. Local app data is under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`; do not move or edit its database or encryption files individually.

## Find an exact patient and plan

1. In Patient Roster, search by MRN, authorized name, plan ID, original reference, or service date. Use Source, patient status, level of care and Primary clinician filters together. A patient may appear without a treatment plan.
2. Open the MRN to see Patient Record Detail. Open a saved plan using its selector, or start in Treatment Plans Roster and filter by source/status.
3. Confirm the source, patient record number, external plan ID, and immutable saved version ID. MRNs and external IDs may repeat across sources or facilities. A name alone is not a match key.
4. On Treatment Plan Detail, inspect the selected saved version and its history. Importing another version does not silently change an existing selection.

Missing names, original references, and service dates remain unavailable or not supplied; the app does not invent them. An empty roster may mean a filter is active, the source has not been pulled, or the pull failed. Clear filters and inspect the last job before concluding that records are absent.

## Worklists and clinicians

Open Overdue or Due Soon from Status Dashboard to see the matching worklist. These counts use the latest saved plan for each authorized patient eligible for current tracking. Inactive, discharged, deleted, unlinked and Case Management records stay outside these worklists. All plans keeps saved records available. Use Overdue by clinician to find clinician groups, including Unassigned, with the most overdue plans first in each group.

Administrators and office managers can open an eligible overdue plan and select Mark overdue plan reviewed. The acknowledgement records the reviewer and time for that exact saved version. Reviewed overdue collapses these rows until expanded. Acknowledgement leaves the plan overdue and counted on the dashboard.

Clinicians lists saved Alleva staff with their source role and facility status, including staff without a caseload. Select a clinician or Unassigned to see the authorized active caseload, including patients without a plan. Treatment Plans Roster shows Primary clinician and Treatment Plan Detail shows Current clinician. Refresh clinicians reloads saved local data. Loading and failure messages mean counts are unavailable.

Administrators and office managers can use Link clinician to patient. Search by name or MRN, confirm the exact patient record, then choose the clinician or explicitly unassign. A local link takes precedence and survives later pulls. Use Alleva assignment restores the saved source relationship. Local links leave Alleva and app account permissions separate.

Alleva uses an explicit primary clinician reference when supplied. Without one, a single source full name can be matched to a unique staff entry when the directory pull did not reach its record limit. Multiple names, duplicate matches and unresolved references stay unassigned. Missing or unmapped staff facilities are labeled. Imported staff and app login accounts are separate.

When live access is approved and enabled, administrators can use Update patients and treatment plans on Status Dashboard. It refreshes patients first, then evaluates plans and imports staff and primary clinician relationships. An incomplete patient pull stops the sequence. The separate Pull clinicians action reads staff and patient relationship context without updating treatment plans. Review job results and counts before relying on the refresh.

## Interpret clinical timing

The 42-step checklist checks an initial signature on admission Day 1 and a signed master plan within 30 calendar days after admission. The recurring deadline uses the selected plan’s last-updated date plus its level-of-care interval. If last updated is unavailable, the app uses an unambiguous first-created date for that same plan. PHP (including PHP-5) and GOP use 30 calendar days. IOP and configured OP/Outpatient aliases use 60. A LOC containing more than one of PHP, IOP or GOP is conflicting. Missing or future clock dates and unknown LOC remain unresolved. In Treatment Plan Detail, find **Next update due (computed)** and read the calculation explanation. Compare it with the source Next Review Due and the separate checklist outcome.

For example, a PHP plan last updated November 1 has a computed deadline of December 1. On November 21 it enters Due Soon. The source Next Review Due can differ, so review the checklist for a conflict.

Event timestamps display in Eastern time (EST or EDT). Calendar-only dates keep their day, and the facility timezone still governs the date used for evaluation.

| Overall status | What to inspect |
| --- | --- |
| Overdue | A confirmed deadline has passed. Inspect the master-plan and recurring-review criteria separately. |
| Due Soon | The computed update deadline is today through 10 calendar days ahead, inclusive. |
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


## Backup and close

Sign out, then use **(2) Stop IZ Clinical Notes Analyzer** when a full stop is needed. Closing a browser tab alone does not stop the local service. Back up through the supplied Backup command when instructed by R3; keep the complete `.izcnabackup` archive intact. It contains sensitive data and configuration even though encrypted. Current backup protection uses Windows CurrentUser DPAPI and is intended for the same Windows account and computer. OneDrive synchronization alone does not establish a tested, replacement-laptop recovery plan. Support must use the supplied Restore command and verify restoration; do not unzip, copy individual database files or overwrite `.env`.

The numbered desktop tools retain their established names. **(1) Start IZ Clinical Notes Analyzer**, **(2) Stop IZ Clinical Notes Analyzer**, **(3) Collect IZ Diagnostics**, **(4) Quick Assist - R3 Support**, **(5) Short Intro Video**, and **(6) IZ Clinical Notes Analyzer User Guide** are the handoff naming convention. Shortcuts are machine-specific; the handoff checklist verifies which ones exist on the client laptop.

For ordinary appliance use, the application, its localhost browser window and OneDrive are the expected workload. ChatGPT is not required and is excluded from steady-state performance estimates. Windows security and update services still run normally. Keep the laptop plugged in for large imports, wait for a job to finish before starting another, and lock Windows with **Windows+L** when stepping away.

## Dashboard deadlines and comments in 1.0.2

At a glance shows Overdue plans and Due Soon plans only. It selects the most recently updated plan per authorized patient record and uses its computed deadline independently of overall checklist status. Missing or ambiguous dates are explained below the counts. Pull authorized Alleva updates to include new vendor changes; dashboard refresh reads saved local data.

Comments on an earlier saved version remain visible in Comments from earlier versions of this plan after Alleva updates that same plan. The original author, date and saved version are retained. Historical approvals and overrides do not approve changed content.
