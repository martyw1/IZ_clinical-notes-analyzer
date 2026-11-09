# Current documentation state

Updated November 9, 2026 for source **1.0.2**, build **2026.10.16.1**, installer revision **1**, channel **stable-local-desktop**. This identifies current source; it does not relabel an older installer or certify a new package. The footer and `/api/version` identify the app actually running.

The browser product name is **R3 Treatment Plan Audit Application**. Existing shortcuts, packages and `%LOCALAPPDATA%\IZ Clinical Notes Analyzer` retain the established IZ name for compatibility.

## Authoritative current instructions

| Need | Current document |
| --- | --- |
| Nontechnical offline guide | [Marleigh's HTML guide](guides/current/Marleigh-Setup-Install-and-User-Guide.html) |
| Daily work, clinical statuses, exact saved version | [Operator help](operator-help-current.md) |
| Troubleshooting, logging, recovery and performance | [Operations runbook](runbook.md) |
| Copy/install and first-use acceptance | [Client handoff](client-handoff-checklist.md) |
| Builder and installer contract | [Windows build/install](windows-installer-build-and-install.md), [CMD maintenance](windows-cmd-maintenance.md) |
| Password setup and recovery | [Password management](password-management-beta4.md), [administrator recovery](admin-access-reset.md) |
| Data flow and source code map | [Patient treatment-plan handling](patient-treatment-plan-handling.md) |
| Exact packages and historical hashes | [Package index](client-release-packages.md) |
| Changes and unresolved owner decisions | [Release notes](release-notes.md), [open blockers](open-blockers.md) |
| Laptop, HIPAA, security and performance assessment | [Assessment](security/appliance-assessment-2026-10-12.md) |
| Offline architecture and source navigation | [Architecture guide](../architecture/index.html) |
| Complete inventory | [Documentation inventory](documentation-inventory.md) |

## Current feature boundary

One localhost service serves the built browser UI and uses local SQLite, encrypted uploads, encrypted saved API settings, role-scoped access, password/recovery workflows, immutable saved plan versions, deterministic timing and a 42-step checklist. Administrators also have connection settings, API harness, users and forensic audit views. Office-manager permissions do not include administrator-only connection or log controls. Optional LLM configuration stays disabled by default and is unnecessary for clinical timing decisions.

Initial signatures are checked on admission Day 1 and master signatures within 30 calendar days. The recurring deadline uses the selected plan’s last-updated date plus its level-of-care interval. If last updated is unavailable, the app uses an unambiguous first-created date for that same plan. PHP (including PHP-5) and GOP use 30 calendar days. IOP and configured OP/Outpatient aliases use 60. A LOC containing more than one of PHP, IOP or GOP is conflicting. Missing or future clock dates and unknown LOC remain unresolved. Due Soon includes today through 10 calendar days ahead. Overdue starts the day after the computed due date. Worklists use the facility date. The LOC-change seven-day value is an unvalidated candidate and these cases stay Needs Review. Prior-version comments remain visible for the same source plan. Approvals stay with their saved version. Settings displays clinical intervals read-only.

Open Overdue or Due Soon from Status Dashboard to see the matching worklist. These counts use the latest saved plan for each authorized patient eligible for current tracking. Inactive, discharged, deleted, unlinked and Case Management records stay outside these worklists. All plans keeps saved records available. Use Overdue by clinician to find clinician groups, including Unassigned, with the most overdue plans first in each group. Administrators and office managers can open an eligible overdue plan and select Mark overdue plan reviewed. The acknowledgement records the reviewer and time for that exact saved version. Reviewed overdue collapses these rows until expanded. Acknowledgement leaves the plan overdue and counted on the dashboard.

Clinicians lists saved Alleva staff with their source role and facility status, including staff without a caseload. Select a clinician or Unassigned to see the authorized active caseload, including patients without a plan. Treatment Plans Roster shows Primary clinician and Treatment Plan Detail shows Current clinician. Refresh clinicians reloads saved local data. Loading and failure messages mean counts are unavailable. Administrators and office managers can use Link clinician to patient. Search by name or MRN, confirm the exact patient record, then choose the clinician or explicitly unassign. A local link takes precedence and survives later pulls. Use Alleva assignment restores the saved source relationship. Local links leave Alleva and app account permissions separate. Event timestamps display in Eastern time (EST or EDT). Calendar-only dates keep their day, and the facility timezone still governs the date used for evaluation.

Live Alleva use remains conditional on official tenant credentials, approved mapping/read-only authorization, pagination/rate-limit validation and compliance approval. A connectivity test is not import acceptance. No startup import is authorized by this documentation.

## Evidence and archives

September 21 build `2026.09.21.2` and its 799-test receipt remain immutable historical package evidence. October 3 video/screenshots demonstrate that source workflow and branding; they do not prove a new installer. [October 16 verification](validation/current-work-2026-10-16.md) and [October 17 laptop checks](validation/local-laptop-test-2026-10-17.md) record source evidence separately.

November source evidence covers the [tracker and version-scoped review](validation/treatment-plan-tracker-2026-11-04.md), [local clinician links and GOP](validation/local-clinician-link-gop-2026-11-06.md), [clinician-only pull](validation/clinician-only-pull-2026-11-06.md), [combined update](validation/combined-update-clinician-2026-11-06.md), [Eastern timestamps](validation/eastern-time-display-2026-11-06.md) and [unique-name fallback](validation/clinician-name-fallback-2026-11-07.md). The one-page shipping PDF remains a startup handout. Use the HTML guide for daily workflows.

Dated validation, beta release notes, old PRDs, Version 1 guides and historical screenshots remain evidence of their original scope. The documentation inventory labels these explicitly. Follow current instructions above when they conflict. No older binary document or video substitutes for the current written guide or running version.

## November 9 documentation verification

Compared the current guides and in-app copy with local commit `a79355e` and confirmed that the checkout matched remote main at review time. Refreshed the operator guide, current workflow and data contracts, and source-generated architecture. Verified all 243 inventory entries exist. Edge rendered the operator guide with 24 valid references and the 29-page architecture guide with 1,051 valid references. The architecture search and narrow viewport checks passed.

The frontend passed 205 tests and the production build. The targeted backend run passed 52 tests for deadline, clinician import, local assignment and operational workflows. The copied virtual environment pointed at a Python installation on another laptop. The backend run used local Python with the checkout's installed test dependencies. This station covers documentation and source checks. Package qualification and live tenant acceptance are tracked separately.
