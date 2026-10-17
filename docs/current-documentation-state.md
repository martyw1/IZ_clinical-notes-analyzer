# Current documentation state

Updated October 17, 2026 for source **1.0.2**, build **2026.10.16.1**, installer revision **1**, channel **stable-local-desktop**. This identifies current source; it does not relabel an older installer or certify a new package. The footer and `/api/version` identify the app actually running.

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
| Complete inventory | [Documentation inventory](documentation-inventory.md) |

## Current feature boundary

One localhost service serves the built browser UI and uses local SQLite, encrypted uploads, encrypted saved API settings, role-scoped access, password/recovery workflows, immutable saved plan versions, deterministic timing and a 42-step checklist. Administrators also have connection settings, API harness, users and forensic audit views. Office-manager permissions do not include administrator-only connection or log controls. Optional LLM configuration stays disabled by default and is unnecessary for clinical timing decisions.

Initial signatures are checked on admission Day 1, the master signature within 30 calendar days, recurring PHP updates at 30 calendar days and IOP/OP at 60 calendar days from the latest saved plan last-updated date. Dashboard counts select one latest plan per patient; Due Soon spans ten Monday-Friday business days. Updated versions display earlier comments from the same source plan without transferring approvals. Settings displays clinical intervals read-only. The LOC-change seven-day value is an unvalidated review candidate; cases remain Needs Review pending R3 policy. Source ambiguity or unavailable evidence must remain unresolved rather than guessed.

Live Alleva use remains conditional on official tenant credentials, approved mapping/read-only authorization, pagination/rate-limit validation and compliance approval. A connectivity test is not import acceptance. No startup import is authorized by this documentation.

## Evidence and archives

September 21 build `2026.09.21.2` and its 799-test receipt remain immutable historical package evidence. October 3 video/screenshots demonstrate that source workflow and branding; they do not prove a new installer. [October 16 verification](validation/current-work-2026-10-16.md) and [October 17 laptop checks](validation/local-laptop-test-2026-10-17.md) record source evidence separately.

Dated validation, beta release notes, old PRDs, Version 1 guides and historical screenshots remain evidence of their original scope. The documentation inventory labels these explicitly. Follow current instructions above when they conflict. No older binary document or video substitutes for the current written guide or running version.
