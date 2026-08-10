# V2 UI Workflows

Primary navigation contains only:

- Status Dashboard
- Patient Roster
- Manual Upload
- Treatment Plan Detail
- Treatment Plans Roster
- API Testing Harness
- Users
- Forensic Logs
- Settings
- Help

MRN is the primary patient identifier. Patient Roster is the second tab and shows one row per authorized MRN/source pair. Its Treatment Plans column contains every locally stored plan for that row in descending last-updated order. Options use `(#<treatment plan ID>) YYYY-MM-DD HH:mm UTC`; the old standalone Treatment Plan ID and Status columns are not present.

Selecting a Patient Roster option opens the fourth tab, Treatment Plan Detail, and loads the exact MRN, treatment-plan ID, and source combination. The detail page merges the full stored treatment-plan aggregate into the readable content graph, source evidence, LOC history, 42-step checklist, evidence coverage map, manager actions, override history, audit refs, and export/source-document controls.

Treatment Plans Roster lists every locally synchronized Alleva treatment plan with Treatment Plan ID, MRN, last updated, previous treatment-plan ID, and the initial plan ID/date for that MRN. Selecting an ID opens that exact plan in Treatment Plan Detail. The approved operational pull remains available on both rosters and in API Testing Harness; the diagnostic preview remains non-populating.

Changed records with an existing treatment-plan ID become the current visible plan while the encrypted earlier version remains immutable. Identical replays do not create duplicates. Forensic Logs show minimum-necessary created/updated/unchanged counts and the exact updated treatment-plan IDs.

Patient-name fields are not part of either roster response or UI. Local source-mode identity is retained so matching manual and Alleva identifiers cannot collapse into one selection. Treatment Plans Roster intentionally excludes manual uploads because it represents Alleva-synchronized records.

Large jobs show a job card immediately, progress, cancel, retry-ready state, artifact list, and bounded preview. The browser must not receive full all-fields payloads.

The footer identifies beta.2 as `Version 2.0 Beta | 2.0.0-beta.2 | beta-local-desktop-v2`. This identifies the active prerelease build only; it is not a production-readiness assertion.
