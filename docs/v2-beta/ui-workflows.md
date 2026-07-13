# V2 UI Workflows

Primary navigation contains only:

- Status Dashboard
- Treatment Plans
- Patient Roster
- Manual Upload
- API Testing Harness
- Users
- Forensic Logs
- Settings
- Help

The Treatment Plans Workbench includes the approved `Pull, evaluate, and populate queue` action, sticky toolbar, treatment-plan status export, risk-first status strip, queue table with patient and treatment-plan IDs, selected-client detail, content graph, source evidence, LOC history, 42-step checklist, evidence coverage map, manager actions, override history, audit refs, and counselor action export surface. The same approved operational pull remains available in API Testing Harness and populates this queue; the diagnostic preview remains non-populating.

Changed records with an existing treatment-plan ID become the current visible plan while the encrypted earlier version remains immutable. Identical replays do not create duplicates. Forensic Logs show minimum-necessary created/updated/unchanged counts and the exact updated treatment-plan IDs.

Patient Roster shows only authorized patient IDs and workflow metadata: treatment-plan ID/status, lifecycle, LOC, source, and last-seen time. Patient-name fields are not part of the roster response or UI.

Large jobs show a job card immediately, progress, cancel, retry-ready state, artifact list, and bounded preview. The browser must not receive full all-fields payloads.

The footer identifies beta.2 as `Version 2.0 Beta | 2.0.0-beta.2 | beta-local-desktop-v2`. This identifies the active prerelease build only; it is not a production-readiness assertion.
