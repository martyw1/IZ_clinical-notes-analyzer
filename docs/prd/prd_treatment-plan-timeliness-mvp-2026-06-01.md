# PRD: Treatment Plan Timeliness Tracker MVP

Date: 2026-06-01
Client context: R3 Recovery Services
Product context: IZ Clinical Notes Analyzer
Primary stakeholder: Marleigh / office manager workflow
Status: MVP requirements draft pending R3 validation

## 1. Purpose

This PRD defines the first MVP for a Treatment Plan Timeliness Tracker inside the IZ Clinical Notes Analyzer product. The MVP is deliberately narrow. It targets the treatment-plan due-date workflow described by Marleigh: active clients, admission dates, level of care, treatment plan signature dates, next due date calculations, warning/urgent/overdue status, and a simple dashboard that can reduce manual Asana tracking.

This is not the full future clinical notes analyzer. The first release should solve the operational problem of trusted treatment-plan timeline tracking.

Implementation note 2026-06-09: the production `Treatment plans` tab now uses a compact work queue with quick status filters, selected-client evidence detail, date-anchor comparison, LOC history, evidence preview, and task-list copy/export for manual Asana tracking. Version `1.0.3` adds a visible updated-evidence-queue banner and stale-build detection for Windows source-checkout launches. Because the LOC-change anchor/window is still unvalidated, source-document `Next Review Due`, staff-signature cadence due date, and LOC-effective cadence due date are shown side by side; conflicts remain `Needs Review`.

## 2. MVP Positioning

Use the product label **Treatment Plan Timeliness Tracker** in screens and planning. The broader repo can remain IZ Clinical Notes Analyzer, but this MVP should not imply broad clinical-note content scoring or AI judgment.

## 3. Business Context

The office manager currently checks Alleva chart areas and then manually tracks next treatment-plan due dates in Asana. The observed workflow uses the Treatment Plan tab, Treatment Plan Review tab, Level of Care tab, admission date, staff/therapist signatures, client signatures where required, and displayed next due date when available. This must scale across roughly 60 active clients.

Before pilot acceptance, R3 should baseline current weekly time spent on treatment-plan date tracking and number of manual Asana updates. Those values become the success baseline.

## 4. Primary Users

### Office Manager
Primary MVP user. Needs a trusted dashboard showing compliant, due soon, urgent, overdue, needs review, and missing data clients. Needs evidence for why each status was calculated.

### Counselor / Therapist
May need to view which client treatment plans need work. Counselor workflow was not directly observed and should not drive MVP scope until validated.

### Administrator
Installs the app, manages users/settings/backups, runs readiness checks, and handles repair or uninstall on Windows 10 Home and Windows 11 Home.

### Future Read-Only Reviewer
Possible later role for compliance review. Not required for MVP unless R3 confirms a named user and workflow.

## 5. MVP Scope

The following items are in scope for the first MVP targeted to Marleigh's Treatment Plan Timeliness workflow.

| # | Scope Item | Layman's Description |
|---|---|---|
| 1 | Active client list tracking | Keep a list of clients currently active and needing treatment-plan tracking. |
| 2 | Admission date capture | Store each client's admission date because that starts the Initial and Master Treatment Plan clocks. |
| 3 | Current level-of-care capture | Store whether the client is in PHP, IOP-5, IOP-19, IOP-3, or OP because that determines 30-day or 60-day rules. |
| 4 | Level-of-care history when available | Track when a client changed levels of care, with manual correction when source data is incomplete. |
| 5 | Initial Treatment Plan validation | Check whether the first treatment plan was completed on the admission day. |
| 6 | Master Treatment Plan validation | Check whether the master treatment plan was completed within 30 days of admission. |
| 7 | Ongoing Treatment Plan Review validation | Check whether later reviews were completed on time based on level of care. |
| 8 | PHP 30-day cycle | For PHP, calculate next review as last valid treatment-plan date plus 30 days. |
| 9 | IOP/OP 60-day cycle | For IOP-5, IOP-19, IOP-3, and OP, calculate next review as last valid treatment-plan date plus 60 days. |
| 10 | Level-of-care change update | If the client changes level of care, flag that a treatment plan update is due within a configurable R3-approved window. |
| 11 | Required signature checks | Check staff/client signatures for Initial and Master plans where required. |
| 12 | Therapist signature checks | For ongoing reviews, use therapist signature date as the MVP completion date. |
| 13 | Compliance dashboard | Show compliant, due soon, urgent, overdue, needs review, and missing data clients. |
| 14 | Alerts | Warn at 10 days, urgent at 5 days, and red/overdue on the due date unless R3 changes that rule. |
| 15 | Non-technical Windows install/repair/uninstall | A normal Windows 10/11 Home user can install, repair, modify, and uninstall without Docker, Git, Node.js, PostgreSQL, or command-line steps. |

## 6. Out of Scope for MVP

Do not include broad clinical note content scoring, full payer-specific rule profiles unless R3 requires them for MVP, Asana integration, email alerts, live Alleva API import, automated writeback to Alleva, multi-machine shared database operation, silent auto-update, full auditor workflow, LLM clinical judgment, or a complex visual timeline.

## 7. Critical Decisions Required Before Build

| Decision | Owner | Target | Blocks |
|---|---|---|---|
| Exact Alleva/export/input format for Phase 1 | R3 / Marleigh / Alleva admin | Before Sprint 1 | Import design and tests |
| Meaning of "immediate" after level-of-care change | R3 clinical/compliance owner | Before Sprint 1 | Rules and dashboard status |
| Override authority | R3 leadership / office manager | Before Sprint 1 | RBAC and audit |
| Missing/conflicting data behavior | R3 + product owner | Before Sprint 1 | Rules and tests |
| Single-machine vs multi-computer access | R3 leadership / technical owner | Before Sprint 1 | Architecture and installer |
| Payer/program-specific timeline differences | R3 compliance owner | Before Sprint 2 | Future rule profiles or MVP scope change |

Default MVP assumption: single-machine local-first app with multiple logins on the same installed instance; not concurrent multi-computer shared access.

## 8. Source Data Requirement

Before ingestion work begins, R3 should provide de-identified sample data showing Treatment Plan, Treatment Plan Review, Level of Care, admission date, active/discharged status, staff/therapist signatures, client signatures, and chart-displayed due date when available.

Preferred MVP ingestion path:

1. Structured Excel/CSV template controlled by this app.
2. Structured Alleva CSV/Excel export if available.
3. Manual entry/editing for key fields.
4. PDF/document parsing only if structured exports are unavailable.
5. Live Alleva API later only after official access and approvals.

## 9. Business Rules

### Active Client Scope

- Default dashboard includes active clients only.
- Discharged/inactive clients are excluded unless filtered explicitly.
- Current level of care is the row with no end/discharge date, or most recent row if no explicit current marker exists.

### Treatment Plan Requirements

- Initial Treatment Plan is due on admission date.
- Initial Treatment Plan needs staff/therapist and client signatures on admission date unless R3 defines an exception.
- Master Treatment Plan is due within 30 calendar days of admission.
- Master Treatment Plan needs staff/therapist and client signatures within 30 days unless R3 defines an exception.
- Ongoing Treatment Plan Reviews are tracked after initial/master.
- Ongoing review completion date is the therapist/staff signature date for MVP.
- Client signature is not required for ongoing review timeliness unless R3/payer rules say otherwise.

### Level-of-Care Recurrence

| Level of Care | Recurrence |
|---|---|
| PHP | Last valid treatment plan date + 30 calendar days |
| IOP-5 | Last valid treatment plan date + 60 calendar days |
| IOP-19 | Last valid treatment plan date + 60 calendar days |
| IOP-3 | Last valid treatment plan date + 60 calendar days |
| OP | Last valid treatment plan date + 60 calendar days |

Level-of-care aliases such as IOP5, IOP-5, and IOP 5 must be configurable after R3 confirms accepted labels.

### Level-of-Care Change

A treatment plan update is required after a level-of-care change within a configurable window. The window is not confirmed by R3/Marleigh, so the MVP must mark it unvalidated, keep it configurable, and avoid treating any placeholder as final.

### Alerts and Status Priority

| Status | Timing / Meaning | Color |
|---|---|---|
| Overdue | Due date is today or earlier | Red |
| Urgent | 5 days or fewer before due date | Orange/yellow |
| Due Soon | 10 days or fewer before due date | Yellow |
| Needs Review | Conflicting evidence or ambiguous calculation | Gray/purple |
| Missing Data | Not enough data to calculate | Gray/purple |
| Compliant | More than 10 days before due date | Green |

Dashboard status updates on dashboard load, import/refresh, or manual source-data edit.

## 10. Missing Data Decision Matrix

| Scenario | MVP Result |
|---|---|
| Missing admission date | Missing Data; cannot evaluate initial/master. |
| Missing current level of care | Needs Review; do not guess 30/60-day rule. |
| Missing therapist signature date for ongoing review | Missing Data; review cannot be used as completion evidence. |
| Initial/Master plan lacks required signature | Noncompliant or Needs Review depending on confirmed exception rules. |
| Master created within 30 days but signed after 30 days | Noncompliant unless R3 says created date is authoritative. |
| Two reviews in same period | Use latest therapist signature date by default and show evidence. |
| LOC change exists but no review after change | LOC Update Needed / Overdue based on configured immediate window. |
| Alleva displayed due date conflicts with calculated due date | Needs Review; show both dates and calculation basis. |
| Discharge date present | Exclude from active dashboard. |
| Unsupported/unreadable file | Missing Data or Needs Review; never assume compliance. |

## 11. Data Dictionary

### Client Fields

| Field | Type | Required | Example |
|---|---|---|---|
| patient_id | string | yes | R3-12345 |
| client_name | string | optional/role-gated | Jane Doe |
| active_status | enum | yes | active |
| admission_date | date | yes | 2026-02-26 |
| discharge_date | date/null | no | null |
| counselor_name | string/null | no | Saffron |
| program | string/null | no | R3 PHP |

### Level-of-Care Fields

| Field | Type | Required | Example |
|---|---|---|---|
| current_level_of_care | enum/string | yes | IOP-5 |
| loc_start_date | date | conditional | 2026-03-30 |
| loc_end_date | date/null | no | null |
| prior_level_of_care | string/null | no | PHP |
| loc_source | string/null | no | Level of Care tab |
| loc_confidence | enum | no | high |

### Treatment Plan Fields

| Field | Type | Required | Example |
|---|---|---|---|
| treatment_plan_type | enum | yes | Review |
| created_date | date/null | no | 2026-03-03 |
| therapist_signature_date | date/null | conditional | 2026-04-02 |
| therapist_signer | string/null | no | Saffron |
| client_signature_date | date/null | conditional | 2026-03-03 |
| chart_displayed_due_date | date/null | no | 2026-05-29 |
| source_tab | string/null | no | Treatment Plan Review |
| source_document_id | string/null | no | doc-001 |
| extraction_confidence | enum | no | high |

### Derived Fields

| Field | Type | Example |
|---|---|---|
| initial_due_date | date | 2026-02-26 |
| initial_status | enum | compliant |
| master_due_date | date | 2026-03-27 |
| master_status | enum | compliant |
| last_valid_review_date | date/null | 2026-04-02 |
| recurrence_days | integer/null | 60 |
| next_due_date | date/null | 2026-06-01 |
| days_until_due | integer/null | 5 |
| calculated_status | enum | urgent |
| override_status | enum/null | compliant |
| override_reason | text/null | Corrected after chart review |

## 12. Dashboard Requirements

Show summary cards for total active clients, compliant, due soon, urgent, overdue, needs review, missing data, and overall compliance percentage.

Table columns: patient ID or permitted name, current level of care, counselor, admission date, last valid treatment plan review date, next due date, days until due, status, rule used, evidence summary, last checked/imported timestamp, View Details action, and optional Acknowledge / Mark Needs Review quick action.

Default sort: Overdue, Urgent, Due Soon, Needs Review, Missing Data, Compliant; nearest due date first within each group.

For MVP, show all active clients if client count is near 60. If active clients exceed 100, add pagination or virtualized rows.

## 13. Client Detail Page

For MVP, show a chronological table rather than a complex graphical timeline.

Required sections: client overview, current status, Initial Treatment Plan result, Master Treatment Plan result, Level-of-Care history, Treatment Plan Review history, calculated next due date, source evidence, missing/conflicting data warnings, manual override form, and audit history for relevant changes.

## 14. Manual Overrides

Default MVP assumption: admin and manager/office-manager roles can override; counselor role cannot override unless R3 authorizes it.

Every override must capture user, timestamp, original value, new value, reason, affected client, and affected rule/result. Overrides must appear in detail view and audit logs.

## 15. Installation, Repair, Upgrade, and Uninstall

### Target Platforms

Support Windows 10 Home and Windows 11 Home. Ordinary users must not need Docker, PostgreSQL, Git, Node.js, Python setup, or command-line work.

### Installer

Provide a signed `.exe` or `.msi` before external distribution. Installer must install app files, create shortcuts, bundle runtime and frontend assets, configure local app-data storage, generate local secrets on first run, initialize SQLite, show readiness in plain English, and launch the local app in a supported browser. Code-signing certificate type and SmartScreen strategy should be decided before production release.

### Repair / Modify

Repair must reinstall binaries, recreate shortcuts, restore bundled runtime if missing, preserve SQLite, preserve encrypted uploads, preserve `.env` and encryption keys, preserve audit logs, and validate readiness.

### Uninstall

Uninstaller removes binaries/shortcuts and stops the local process. It preserves local app data by default and requires explicit confirmation before deleting database, uploads, logs, or encryption keys.

### Upgrade

MVP updates may be manual installer-based. Upgrade must preserve data and keys, back up database before schema changes, run schema compatibility checks, validate YAML rules, and show plain-English result. In-app update notification is future scope.

## 16. Browser Support

Support current Microsoft Edge and current Google Chrome on Windows 10 Home and Windows 11 Home. Edge is the default supported browser because it is included with Windows. Firefox is best-effort unless R3 requires formal support.

## 17. Security and Privacy Controls

Required MVP controls:

- Login before client data access.
- Role-based access.
- Encrypted local storage for clinical uploads.
- Encrypted API secrets.
- No PHI in application logs.
- Audit logging for login, upload, view, download, override, approval/return, user management, and settings changes.
- Session inactivity timeout, default 15 minutes, configurable.
- Account lockout after 5 failed login attempts, with admin unlock.
- Readiness checks for weak/missing secrets.
- Backup guidance for database, encrypted uploads, audit logs, and `.env` encryption key.

Windows Home caveat: Windows 10/11 Home deployments may not have centrally managed BitLocker Drive Encryption. Some devices support Windows Device Encryption depending on hardware and account configuration. The app should warn if device/app-data storage appears risky, and R3 must accept or mitigate workstation risk.

Support/BAA caveat: If developers, support staff, remote tools, cloud services, or AI tools may access PHI, R3 must confirm legal/compliance coverage before any PHI exposure.

## 18. Reporting

MVP reports: active-client compliance, due soon, urgent, overdue, needs review/missing data, counselor summary, and CSV export with minimum necessary fields. Future reports may include trends, payer/program comparisons, full audit export, and counselor caseload risk.

## 19. Acceptance Criteria

### Happy Path

- Admission 2026-02-26 plus Initial signed by staff/client on 2026-02-26 equals compliant.
- Admission 2026-02-26 plus Master signed by staff/client on 2026-03-03 equals compliant.
- PHP last review signature 2026-04-02 gives next due date 2026-05-02.
- IOP-5 last review signature 2026-04-02 gives next due date 2026-06-01.
- PHP to IOP-5 change on 2026-03-30 with review signed 2026-04-02 uses IOP-5 60-day rule.
- Due in 10 days appears Due Soon.
- Due in 5 days appears Urgent.
- Due today appears Overdue/red unless R3 creates a Due Today status.

### Edge Cases

- Therapist signature exists but current level of care is missing: Needs Review, no guessed due date.
- Level of care exists but therapist signature is missing: Missing Data.
- Two reviews in same period: latest therapist signature used by default and evidence shown.
- Initial plan signature date differs from admission date: noncompliant or Needs Review based on configured exceptions.
- Master created within 30 days but signed after 30 days: noncompliant unless R3 says created date is authoritative.
- LOC change with no review inside configured window: Overdue or LOC Update Needed.
- Alleva displayed due date conflicts with calculated date: Needs Review with both dates shown.
- Discharged client excluded from active dashboard.
- Missing admission date: Initial/Master Missing Data.
- Unsupported/unreadable file: no compliance assumed.
- Manual override records user, timestamp, original value, new value, and reason.
- Unauthorized override attempt is blocked and logged.

### Installation

- Non-technical Windows 10 Home and Windows 11 Home users can install and launch without command line.
- Installer creates shortcuts.
- App opens in Edge or Chrome at the local URL.
- Readiness check completes in plain English.
- Repair preserves data, uploads, logs, and keys.
- Uninstall preserves local data by default and warns before deletion.

## 20. Success Metrics

| Metric | Target |
|---|---|
| Manual tracking reduction | Reduce manual Asana treatment-plan tracking entries by at least 80% within 60 days. |
| Office-manager time saved | Reduce treatment-plan date tracking to 30 minutes/week or less after baseline is measured. |
| Calculation accuracy | At least 95% agreement with office-manager validation sample. |
| Missing-data handling | 100% of insufficient-data records flagged Missing Data or Needs Review rather than silently miscalculated. |
| Audit completeness | 100% of overrides include user, timestamp, original value, new value, and reason. |
| PHI logging | Zero PHI found in logs during test review. |
| Install success | Non-technical Windows user can install and launch without command-line steps. |
| Dashboard usability | Office manager can identify overdue and due-soon plans within 2 minutes of opening dashboard. |

## 21. Release Plan

### Phase 1: MVP Timeliness Tracker

Structured manual/CSV/Excel import, active client dashboard, initial/master/review calculations, LOC-based 30/60-day rules, missing-data handling, override audit, Windows installer prototype, full-stack tests, installer tests.

### Phase 2: Alleva Export Enhancement

Parse actual Alleva export format, improve signature/date extraction, import LOC history, compare displayed due date to calculated due date, add confidence scoring.

### Phase 3: Workflow Enhancements

Email reminders if required, counselor-level reporting, CSV/Excel export, optional Asana export, historical trends.

### Phase 4: Alleva API/FHIR Integration

Official Alleva API/FHIR registration, read-only DocumentReference/Binary import, scheduled refresh, vendor-approved production integration, compliance/legal sign-off.

## 22. Open Questions

| Question | Owner | Target | Blocks |
|---|---|---|---|
| What exact Alleva export/input format will MVP use? | R3 / Marleigh / Alleva admin | Before Sprint 1 | Import design |
| What does immediate mean after LOC change? | R3 compliance/clinical owner | Before Sprint 1 | Rules |
| Who can override due dates/statuses? | R3 leadership | Before Sprint 1 | RBAC |
| Are client signatures always required for Initial/Master? | R3 clinical/compliance | Before Sprint 1 | Rules |
| Are client signatures ever required for ongoing reviews? | R3 clinical/compliance | Before Sprint 1 | Rules |
| Do payer/program rules change timelines? | R3 compliance | Before Sprint 2 | Rule profiles |
| Should compliance percentage exclude Missing Data? | R3 / office manager | Before Sprint 1 | Dashboard |
| Should due today be red/overdue or separate? | R3 / office manager | Before Sprint 1 | Dashboard |
| Is MVP single-machine or multi-computer shared? | R3 leadership / technical owner | Before Sprint 1 | Architecture |
| Should names or patient IDs display by default? | R3 privacy/compliance | Before Sprint 1 | UI |
| Should email alerts be MVP? | R3 / office manager | Before Sprint 2 | Notifications |
| Should Asana integration be MVP? | R3 / office manager | Before Sprint 2 | Workflow |
| Who owns backup/restore? | R3 admin / technical owner | Before pilot | Operations |

## 23. Implementation Notes for Existing Repo

Reuse the existing FastAPI backend, React/Vite frontend, SQLite-first local runtime, encrypted local upload storage, YAML rules engine, readiness checks, user/role model, audit logging, API configuration, and future EMR/FHIR boundary.

The level-of-care change treatment-plan update window remains unvalidated. Keep it configurable, visibly mark it unvalidated in admin/settings UI and documentation, and do not hard-code a final value until `docs/open-blockers.md` is resolved.

S2-S7 implementation status on 2026-06-04: backend timeliness tables, APIs, deterministic evaluation, upload metadata sync, settings fields, manual override audit logging, React dashboard/detail UI, clinical upload hardening, direct API harness redaction/report hardening, admin-managed workflow profile CRUD/versioning with default seeding and draft-only delete limits, expanded full-stack smoke coverage, workflow extensibility documentation, and Dell Windows validation commands are implemented on `refactor/codex-v0.5.0`. Remaining release blockers are browser e2e/Vitest recovery, target Dell validation, structured import templates, and a real Windows installer/repair/uninstall package.

Expected implementation work:

1. Recover browser e2e/Vitest validation locally or in CI.
2. Complete Windows Home packaging decision and Dell validation.
3. Add structured import templates.
4. Add robust Windows Home installer/repair/uninstall flow.
5. Add backend, frontend, full-stack, functional, performance, and security-oriented tests.
