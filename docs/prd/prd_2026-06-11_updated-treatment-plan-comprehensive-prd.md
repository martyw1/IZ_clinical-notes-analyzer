# PRD: IZ Clinical Notes Analyzer — Treatment Plan Checklist, Timeliness, API/Upload Workflow, and UI/UX Update

**Date:** 2026-06-11  
**Repo:** `martyw1/IZ_clinical-notes-analyzer`  
**Primary stakeholder:** Marleigh Johnson, Clinical Director, R3 Recovery Services  
**Product:** IZ Clinical Notes Analyzer  
**Release target:** Version 1.x completion / pilot-ready Windows desktop release  
**Implementation target:** Windows 11 local repo, OpenAI Codex app, GPT-5.5 Extra High reasoning

---

## 1. Executive Summary

The IZ Clinical Notes Analyzer is a local-first Windows clinical chart-review app for R3 Recovery Services. The immediate product goal is to make the app pilot-ready for treatment-plan review and tracking, including all treatment-plan checklist steps validated by Marleigh and the latest UI/UX direction from the `video-extract (2026-06-05)` folder.

The product must support two intake paths:

1. **EMR/API access path** — when Alleva or another EMR integration is approved and configured, the app should identify active charts and treatment-plan review items automatically, refresh daily, and notify/alert Marleigh about anything needing review, follow-up, correction, or approval.
2. **Manual upload path** — when API access is unavailable, Marleigh or another authorized user can upload chart exports or treatment-plan documents manually. Because R3 has 60+ active charts, manual upload is not ideal for weekly review; if manual upload remains the only path, Version 1 should support a monthly compliance-check workflow rather than pretending manual weekly uploads are practical.

The app must remain conservative: missing, conflicting, unreadable, or unvalidated evidence must be flagged as **Missing Data**, **Needs Review**, or **Unable to Evaluate** rather than assumed compliant. Real PHI must not be used in development, tests, screenshots, docs, commits, logs, or API probes unless R3 has approved production PHI handling.

---

## 2. Source Inputs Consolidated Into This PRD

This PRD consolidates:

- Current repo baseline, including README, rules config, checklist config, existing PRDs, open blockers, Windows docs, API configuration docs, and recent release/changelog notes.
- Marleigh’s June 10, 2026 response validating the acronym definitions and the 42 treatment-plan checklist steps.
- Existing `docs/prd-treatment-plan-timeliness-mvp-2026-06-01.md`.
- Existing `docs/treatment-plan-checklist-v1.md` and `config/checklists/treatment-plan-v1.json`.
- Existing deterministic rules in `config/rules/alleva_treatment_plan_completeness_rules.yaml`.
- Latest UI/UX material in `video-extract (2026-06-05)`, including any style sheets, component snippets, screenshots, notes, and extracted recommendations.

Codex must inspect the full repo, not only this document, before implementing changes.

Current implementation note 2026-07-01: Beta `1.4.6-beta.1` documents the actual patient treatment-plan handling path in `docs/patient-treatment-plan-handling.md`. The current code stores local `TreatmentPlanClient`, `LevelOfCareHistory`, `TreatmentPlanRecord`, `TreatmentPlanOverride`, and `TreatmentPlanCriterionReview` rows; gates Alleva REST sync behind App settings approval and endpoint mapping; supports a `patient_treatment_plan_aggregates` API-harness dry-run; captures current-plan content counts/facts without raw narrative text; and keeps deterministic local timeliness/checklist logic as the compliance decision engine.

---

## 3. Confirmed Stakeholder Requirements From Marleigh

Marleigh confirmed:

1. If the process is automated, the app should check daily and notify her of anything that needs to be looked at or followed up on.
2. If the process is not automated, each chart would have to be downloaded and uploaded manually.
3. Manual upload for 60+ active charts is not ideal.
4. If manual upload remains the only workable path, monthly compliance checks may be more realistic than weekly manual upload of every chart.
5. The acronym and terminology definitions previously sent are acceptable.
6. The 42 treatment-plan checklist items previously sent are acceptable.
7. Marleigh will provide client treatment plans with names blacked out for testing.

These are binding Version 1 requirements unless R3 later provides a superseding decision.

---

## 4. Product Goals

### 4.1 Primary Goals

- Give Marleigh a trusted treatment-plan worklist showing active client chart status.
- Support both API-driven monitoring and manual-upload workflows while routing both through the same checklist and review workflow.
- Implement all 42 Marleigh-validated treatment-plan checklist steps as the complete operational checklist.
- Reconcile the existing 20-step repo checklist with the 42-step operational checklist so the UI, config, docs, tests, and rules are not inconsistent.
- Provide a Windows 11 pilot-ready experience for non-technical R3 users.
- Ensure each status is evidence-backed, auditable, and reversible only through authorized manual confirmation or override.
- Preserve review history, source evidence, manual decisions, approvals, returns, and audit timestamps.
- Make the UI/UX clear enough that Marleigh can use the app without command-line help.

### 4.2 Non-Goals

- Do not enable live Alleva patient import until official vendor credentials, scopes, endpoint mapping, pagination, attachment behavior, rate limits, and compliance/legal approval are confirmed.
- Do not write back to Alleva.
- Do not use LLM clinical judgment as the source of truth for compliance.
- Do not store or expose API keys, bearer tokens, passwords, or encryption keys in UI, logs, docs, screenshots, exports, or commits.
- Do not commit real PHI or screenshots containing PHI.
- Do not hard-code the LOC-change treatment-plan update window until R3 confirms the exact rule.
- Do not implement full Asana integration unless explicitly required later; support copy/export for manual Asana-style tracking first.

---

## 5. Users and Roles

### 5.1 Admin

- Installs and configures the app.
- Manages users, roles, password resets, lock/unlock, deactivation/reactivation, and safe admin recovery.
- Reviews readiness, settings, API configuration, forensic logs, and workflow definitions.
- Can create manual overrides and manager decisions where permitted.
- Handles backup/restore guidance.

### 5.2 Manager / Clinical Director / Office Manager

- Primary Version 1 user.
- Reviews treatment-plan status worklist.
- Selects charts needing review.
- Confirms or corrects checklist findings.
- Adds override reasons.
- Approves charts or returns them with correction comments.
- Exports CSV/JSON reports or copies task lists for follow-up.

### 5.3 Counselor / Therapist

- Uploads or updates chart documents where authorized.
- Views returned items and correction comments.
- Does not approve final checklist results or perform override actions unless R3 explicitly grants that authority.

---

## 6. Definitions and Acronyms

The UI must expose these definitions in a Checklist tab, help panel, or definitions drawer.

| Term | Definition |
|---|---|
| EMR | Electronic Medical Record, such as Alleva or another system where the client chart and clinical documents are stored. |
| API | Application Programming Interface, meaning a direct system-to-system connection that could allow the app to read approved chart documents from the EMR instead of requiring manual upload. |
| PHI | Protected Health Information, meaning client-identifying health information that must be handled under approved privacy/security procedures. |
| PII | Personally Identifiable Information. |
| MRN | Medical Record Number or equivalent client identifier used by the EMR. |
| LOC | Level of Care, such as PHP, IOP, IOP-5, IOP-19, IOP-3, OP, or Outpatient. |
| PHP | Partial Hospitalization Program. |
| IOP | Intensive Outpatient Program. |
| OP | Outpatient. |
| TP | Treatment Plan. |
| Initial Treatment Plan | The first treatment plan expected at admission. |
| Master Treatment Plan | The fuller treatment plan expected within the required post-admission timeframe. |
| Treatment Plan Review | An ongoing update/review of the treatment plan after the initial and master treatment plans. |
| LOC Change Update | A treatment-plan update or review that may be required when the client’s level of care changes. |
| Source Evidence | The document, form, note, signature, date, or EMR record used to support the checklist result. |
| OCR | Optical Character Recognition. |
| LLM | Large Language Model; optional and disabled by default. |
| SUD | Substance Use Disorder. |
| ASAM | American Society of Addiction Medicine criteria, if used by the facility/workflow. |
| SMART | Specific, Measurable, Achievable, Relevant, Time-bound. |

---

## 7. Intake Modes

### 7.1 API / EMR Mode

When approved API access exists, the app shall:

- Authenticate using encrypted saved credentials or secure one-time test credentials.
- Never expose saved secrets to the browser.
- Discover active client charts and available treatment-plan related records.
- Classify charts by status: done/current, due soon, urgent, overdue, missing data, conflicting, needs review, returned for correction, approved, or unable to evaluate.
- Refresh daily by default.
- Notify/alert Marleigh in-app and through any approved configured notification method.
- Preserve last refresh timestamp, changed item count, error count, next scheduled refresh, source IDs, and status history.
- Provide a safe mock/simulation mode until live import is approved.
- Continue to block live Alleva import until official credentials, endpoint mapping, and compliance approval are confirmed.

### 7.2 Manual Upload Mode

When API access is unavailable, the app shall:

- Support initial chart review and existing chart update.
- Accept supported files and reject unsafe/unsupported/oversized/empty uploads.
- Capture patient/chart ID, client status, admission date, LOC, document dates, signatures, source system/file, clinician/provider, and notes where available.
- Route uploaded records through the same checklist workflow as API-sourced records.
- Clearly warn that manual upload only reflects the uploaded documents as of upload time.
- Support monthly compliance-check workflow when manual mode is the only feasible method for 60+ active charts.

---

## 8. Marleigh-Validated 42-Step Treatment Plan Checklist

The app must implement, display, test, and document the following operational checklist steps.

1. **Confirm this is the correct client chart** — Verify documents belong to the intended client and that no conflicting client IDs exist across source documents.
2. **Identify whether the review is for a new chart or an existing chart update** — New charts establish baseline; updates compare newly added notes against history.
3. **Confirm the client is active** — Version 1 evaluates active clients and excludes discharged/inactive clients from Treatment Plan Tracking by default.
4. **Confirm the admission date** — Admission date drives Initial and Master Treatment Plan timing.
5. **Confirm the current LOC** — LOC determines treatment-plan timing rules.
6. **Confirm the LOC maps to a Version 1 rule category** — Unknown LOC is Unable to Evaluate or Needs Review.
7. **Capture LOC history when available** — Preserve prior/current LOC data to identify LOC-change cases.
8. **Classify each source document** — Label each document as Initial Treatment Plan, Master Treatment Plan, Treatment Plan Review, LOC Change Update, supporting note, or other relevant type.
9. **Confirm each document date** — Capture reliable document dates because checklist timing depends on them.
10. **Confirm each document’s completion status** — Mark completed, incomplete, missing, not applicable, or needing review.
11. **Confirm staff/therapist signature status** — Track required staff/therapist signature presence.
12. **Confirm client signature status** — Track required client signature presence.
13. **Check for conflicting evidence** — Flag conflicts in dates, LOC, completion status, signatures, identity, or source evidence.
14. **Check that the Initial Treatment Plan exists** — Flag if missing.
15. **Check that the Initial Treatment Plan is dated correctly** — Tie to admission date unless R3 confirms another rule.
16. **Check that the Initial Treatment Plan has required signatures** — Do not count as valid unless required signature evidence is present.
17. **Check that the Master Treatment Plan exists** — Flag if missing.
18. **Check that the Master Treatment Plan was completed within 30 calendar days of admission** — Use 30 calendar days unless R3 confirms another standard.
19. **Check that the Master Treatment Plan has required signatures** — Do not count as valid unless required signature evidence is present.
20. **Identify the latest valid Treatment Plan Review** — Find the most recent completed and signed review used to calculate next due date.
21. **Calculate the next Treatment Plan Review due date** — Calculate from latest valid review date using configured LOC interval.
22. **Apply the PHP timing rule** — PHP treatment-plan reviews use a 30-day update interval.
23. **Apply the IOP/OP timing rule** — IOP, IOP-5, IOP-19, IOP-3, OP, and Outpatient use a 60-day update interval.
24. **Mark the treatment plan as current when inside the allowed window** — Current/compliant only when latest valid review remains inside required timeframe.
25. **Mark the treatment plan as due soon when approaching the deadline** — Surface before overdue.
26. **Mark the treatment plan as overdue when past the deadline** — Flag overdue/noncompliant after due date.
27. **Check PHP individual-session evidence when available** — Confirm required count when notes contain that evidence.
28. **Check IOP/OP individual-session evidence when available** — Confirm required count when notes contain that evidence.
29. **Identify whether an LOC change occurred** — Flag LOC-change treatment-plan update check.
30. **Check for an LOC Change Update document when applicable** — Look for related update/review tied to LOC change.
31. **Hold the LOC-change deadline as unresolved until R3 confirms it** — Do not hard-code window until R3 confirms days, calendar/business days, and clock start.
32. **Flag missing data instead of assuming compliance** — Missing date, signature, LOC, plan, or review evidence must not pass.
33. **Allow manual reviewer confirmation** — Reviewer can confirm, correct, override, or mark as needing manual confirmation.
34. **Require a reason for manual overrides** — Manual correction/override requires clear audit reason.
35. **Produce a final checklist result for the chart** — Show compliant, overdue, due soon, missing, conflicting, or needs review.
36. **Update the status worklist after review** — Show done, needs review, overdue, due soon, missing data, or returned for correction.
37. **Route the chart for manager review** — Checklist should be ready for manager review, approval, or return.
38. **Return charts with specific correction comments** — Comments identify what is missing, incorrect, late, or unclear.
39. **Approve charts only after checklist issues are resolved or accepted** — Approval means Version 1 items passed or were manually reviewed and accepted.
40. **Preserve the review history** — Store source evidence, checklist result, confirmations, overrides, approvals, returns, and timestamps.
41. **Continue periodic monitoring when API access is available** — Continue scheduled checking for new notes, changed statuses, overdue items, or newly due reviews.
42. **Use synthetic or approved non-PHI data for validation until production handling is approved** — No real client-identifying data in tests, screenshots, docs, or shared examples without approval.

---

## 9. Business Rules

### 9.1 Active Client Scope

- Default dashboard includes active clients only.
- Discharged/inactive clients are excluded unless explicitly filtered.
- Current LOC is the row with no end/discharge date, or most recent row if no explicit current marker exists.

### 9.2 Treatment Plan Requirements

- Initial Treatment Plan is expected at admission unless R3 later confirms another rule.
- Initial Treatment Plan must include required staff/therapist and client signature evidence.
- Master Treatment Plan is due within 30 calendar days of admission unless R3 confirms another standard.
- Master Treatment Plan must include required staff/therapist and client signature evidence.
- Ongoing Treatment Plan Reviews are tracked after initial/master plan requirements.
- Latest valid treatment-plan review date is the anchor for next review due date.
- Missing or conflicting signature evidence must not count as valid without reviewer confirmation.

### 9.3 LOC Recurrence Rules

| LOC | Recurrence |
|---|---|
| PHP | Latest valid treatment-plan review/update date, or admission date when no later valid update exists, + 30 calendar days |
| IOP | Latest valid treatment-plan review/update date, or admission date when no later valid update exists, + 60 calendar days |
| IOP-5 | Latest valid treatment-plan review/update date, or admission date when no later valid update exists, + 60 calendar days |
| IOP-19 | Latest valid treatment-plan review/update date, or admission date when no later valid update exists, + 60 calendar days |
| IOP-3 | Latest valid treatment-plan review/update date, or admission date when no later valid update exists, + 60 calendar days |
| OP | Latest valid treatment-plan review/update date, or admission date when no later valid update exists, + 60 calendar days |
| Outpatient | Latest valid treatment-plan review/update date, or admission date when no later valid update exists, + 60 calendar days |

LOC aliases such as `IOP5`, `IOP 5`, `O/P`, and `OUTPATIENT` must stay configurable.

### 9.4 LOC-Change Blocker

The LOC-change treatment-plan update window remains unvalidated. The app must:

- Keep the setting configurable.
- Mark it unvalidated in Settings, Checklist, dashboard/detail UI, and docs.
- Ship the current manager-editable 7-calendar-day preset only as an unvalidated default until R3 confirms the final rule.
- Show source-document due date, date-clock due date, date-clock anchor, and LOC-change due date side by side.
- Treat LOC-change conflicts as Needs Review or Missing Data.
- Never hard-code a final LOC-change window until R3 confirms exact days, calendar/business basis, and clock-start date.

### 9.5 Status Priority

Recommended display priority:

1. Overdue
2. Urgent
3. Due Soon
4. Returned for Correction
5. Needs Review
6. Missing Data
7. Conflicting Evidence
8. Unable to Evaluate
9. Current / Compliant
10. Approved / Finalized

Status must not rely on color alone. Include labels, text, icons, and evidence.

---

## 10. Data Requirements

### 10.1 Client Fields

- patient_id / MRN or safe equivalent
- client display name when allowed by PHI policy
- active_status
- admission_date
- discharge_date
- counselor/primary clinician
- program
- current LOC
- LOC history
- source system
- last imported/uploaded timestamp

### 10.2 Document Fields

- source document ID
- source type: API or upload
- original file metadata where safe
- document type
- document date
- completion status
- staff/therapist signature status/date
- client signature status/date
- source evidence summary
- extraction/confidence status
- conflicts and warnings

### 10.3 Derived Fields

- initial due date/status
- master due date/status
- latest valid review date
- recurrence interval
- next due date
- days until due
- status
- rule used
- evidence completeness
- override status/reason
- approval/return disposition

---

## 11. Functional Requirements

### FR-1 Checklist Canonicalization

The repo shall contain a canonical checklist source that represents the 42 Marleigh-validated operational steps and reconciles the earlier 20-step checklist. UI, backend APIs, docs, exports, and tests must refer to the same checklist version.

### FR-2 Source Mode Selection

The dashboard shall show EMR/API and Manual Upload source modes with clear descriptions, readiness state, and next actions.

### FR-3 Daily API Monitoring

When API mode is approved/configured, the app shall run or support a daily refresh that identifies active charts and status changes, then surfaces items needing review/follow-up.

### FR-4 Manual Monthly Compliance Mode

When manual upload is the only source, the app shall support monthly compliance-check workflow appropriate for 60+ active charts.

### FR-5 Active Chart Worklist

The Treatment Plans tab shall display active charts and prioritize overdue, urgent, due soon, returned, needs review, missing data, and current items.

### FR-6 Evidence-First Detail View

Each chart detail shall show client overview, LOC history, source documents, initial/master/review results, signature evidence, conflicts, source/staff/LOC due-date comparison, manual overrides, manager disposition, and audit history.

### FR-7 Manual Review and Overrides

Authorized users may confirm, correct, override, or mark items as needing review. Overrides require a reason and must be audited.

### FR-8 Approval and Return Workflow

Managers/admins may approve a chart only when issues are resolved or accepted. Returns require specific correction comments.

### FR-9 Reporting and Export

The app shall support CSV and JSON export of review/timeliness data while excluding secrets and avoiding unnecessary PHI.

### FR-10 API Configuration Harness

The API configuration harness shall support OpenAPI/Swagger pull, base connectivity test, selected operation test, encrypted saved credentials, one-time credentials, redaction, and safe JSON reports.

### FR-11 Audit Logging

The app shall audit sign-in, upload, view/download, review, override, export, approval, return, settings changes, user changes, and API tests without logging PHI-like clinical note text or secrets.

---

## 12. UI/UX Requirements

Codex must inspect and implement the latest repo UI/UX recommendations in `video-extract (2026-06-05)`, including actual CSS, style sheets, snippets, screenshots, extracted notes, and walkthrough guidance.

Minimum UI/UX requirements:

- Dashboard has clear review-source cards for EMR/API and Manual Upload.
- Treatment Plans tab has visible current-build/current-queue marker.
- Treatment Plans worklist has status filters, clear sorting, readable status labels, and evidence summaries.
- Detail view is evidence-first and avoids burying signatures, dates, LOC history, conflicts, and audit history.
- Acronyms/definitions are available inside the app.
- Errors and readiness results use plain-English, non-technical recovery steps.
- Buttons are explicit: View Details, Confirm, Override, Return for Correction, Approve, Export CSV, Export JSON, Copy Task List.
- Returning a chart requires specific correction comments.
- Overrides require reasons.
- UI is keyboard navigable and has visible focus states.
- Status is never communicated by color alone.
- Layout works on typical Windows laptop screens without awkward horizontal scrolling.
- No demo/test screenshots contain PHI.

---

## 13. Non-Functional Requirements

### 13.1 Security and Privacy

- Login required before client data access.
- RBAC enforced on every protected backend action.
- Uploaded files encrypted at rest.
- API secrets encrypted at rest.
- Saved API keys never returned to browser.
- PHI and secrets excluded from logs and test artifacts.
- Session timeout and account lockout enforced.
- Backup guidance covers `.env`, database, uploads, and logs.

### 13.2 Reliability

- Missing data must not be silently treated as compliant.
- Rules engine must be deterministic and covered by tests.
- Startup/preflight must detect missing dependencies and stale frontend assets.
- App must keep running locally without Docker/PostgreSQL for normal Windows use.

### 13.3 Usability

- Non-technical Windows user can launch and use app from a local release folder or installer path.
- UI text must explain what is wrong and what to do next.
- Marleigh can identify highest-priority charts within two minutes of opening Treatment Plans.

### 13.4 Performance

- Worklist must comfortably handle at least 60 active charts.
- If active chart count exceeds 100, add pagination, virtualized rows, or equivalent.
- Startup and dashboard load should remain acceptable on a typical Windows 11 laptop.

### 13.5 Maintainability

- Rules, LOC aliases, and unresolved LOC-change settings must be configurable.
- Keep deterministic rules separate from optional LLM features.
- Deprecated files must be either quarantined or removed only with a documented removal log and proof that no active runtime, test, launch, config, or docs path needs them.

---

## 14. Windows Release Requirements

The app should be realistic for Windows 11 non-technical use.

Required:

- Source-checkout startup still works.
- Preflight checks frontend build freshness.
- Built frontend assets are current.
- Local runtime data stays under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.
- Scripts use clear error messages.
- Installer/release-folder path is documented and tested as far as the repo supports.
- If signed MSI/MSIX is not implemented, docs must state exactly what remains.
- Repair/uninstall behavior should preserve app data by default wherever implemented.

---

## 15. Testing Requirements

Required test coverage:

- 42 checklist steps exist and are presented correctly.
- API/upload source routing.
- Daily API monitoring simulation.
- Monthly manual compliance-check workflow.
- LOC mapping and unknown LOC.
- Initial and Master plan due dates/signatures.
- PHP 30-day and IOP/OP 60-day calculations.
- LOC-change unresolved blocker.
- Missing/conflicting evidence behavior.
- Override reason required.
- Role restrictions.
- Approval/return workflow.
- Export redaction.
- API secret redaction.
- Forensic logs without PHI/secrets.
- UI status sorting/filtering.
- UI/UX components from video extract.
- Deprecated-file manifest.

Expected Windows validation commands, adjusted if repo commands differ:

```powershell
git status
python --version
node --version
npm --version
.\scripts\preflight-windows.ps1 -AssumeYes
.\scripts\test-local-app-stack.ps1
.\scripts\test-api-configuration-local.ps1
cd frontend
npm install
npm test -- --run
npm run build
cd ..
.\backend\.venv\Scripts\python.exe -m pytest backend\tests -q
```

---

## 16. Computer-Use / Browser Walkthrough Acceptance

Codex must run the app and use computer use or browser automation to walk the UI, not only unit tests.

Required walkthrough:

1. Launch app on localhost.
2. Confirm version/footer/current build marker.
3. Sign in as admin.
4. Complete password reset if prompted.
5. Open Dashboard.
6. Verify EMR/API and Manual Upload source cards.
7. Open Treatment Plans.
8. Verify updated evidence queue marker.
9. Verify status cards, filters, sorting, and worklist.
10. Open a treatment-plan detail record.
11. Verify evidence sections, source/staff/LOC due-date comparison, LOC history, signatures, and audit history.
12. Add authorized manual override with synthetic reason.
13. Confirm override without reason is blocked.
14. Export CSV and JSON.
15. Copy task list.
16. Open Manual Upload.
17. Upload synthetic/de-identified sample files.
18. Confirm created/updated review case.
19. Open Review Queue / Chart Audit.
20. Step through checklist findings.
21. Return chart for correction with specific comment.
22. Approve chart after issues are resolved/accepted.
23. Open API Configuration.
24. Run safe connectivity/sample OpenAPI tests.
25. Confirm secrets are redacted.
26. Open Settings.
27. Confirm LOC-change setting is visible/configurable/unvalidated.
28. Open Forensic Logs.
29. Confirm actions appear and no secrets/note text are logged.
30. Confirm keyboard navigation and focus states.
31. Confirm no PHI appears in screenshots/logs/artifacts.

Save validation report under `docs/validation/`.

---

## 17. Deprecated File Cleanup Requirement

Original 2026-06-11 requirement: Codex must identify files no longer needed and move them, not delete them, into:

```text
depriceated/
```

Use this exact spelling.

Preserve original relative paths where practical. Create:

```text
depriceated/DEPRECATED-MANIFEST.md
```

Manifest must include original path, new path, reason moved, replacement, date moved, and validation that tests/build still pass after move.

Superseding 2026-06-17 cleanup rule: because the deprecated Docker/nginx archive was already quarantined, already documented, and later proven unused, it may be removed when `docs/removal-log.md` records the path, reason, reference-scan evidence, and validation results. Do not remove active runtime files, active docs linked from README, migrations, configs, sample test data, current scripts, tests, or anything needed by build/start/test unless replacement behavior is verified.

Do not move or remove active runtime files, active docs linked from README, migrations, configs, sample test data, current scripts, tests, or anything needed by build/start/test unless replacement behavior is verified.

---

## 18. Acceptance Criteria

### 18.1 Product Acceptance

- Marleigh can see all active charts and immediately identify overdue, due soon, missing data, and needs-review items.
- App supports daily API monitoring when API mode is approved/configured.
- App supports monthly compliance-check workflow when manual upload is the only practical source.
- All 42 checklist steps are visible, testable, and documented.
- Missing or conflicting data never silently passes.
- LOC-change update window remains unvalidated/configurable until R3 confirms exact rule.
- Manager approval and return workflows work with required comments/reasons.
- Review history and audit logs are preserved.

### 18.2 Technical Acceptance

- Backend tests pass.
- Frontend tests and build pass.
- Windows preflight and smoke scripts pass.
- API configuration tests pass.
- Browser/computer-use walkthrough completed with synthetic data.
- Docs updated.
- Deprecated/unused files quarantined or removed with `docs/removal-log.md` evidence.

---

## 19. Open Questions / Blockers

| Question / Blocker | Owner | Requirement Until Resolved |
|---|---|---|
| Exact LOC-change update window | R3/Marleigh/compliance | Keep unvalidated/configurable; mark Needs Review/Missing Data on conflicts. |
| Calendar vs business days for LOC-change | R3/Marleigh/compliance | Do not hard-code. |
| LOC-change clock-start date | R3/Marleigh/compliance | Show evidence anchors side by side. |
| Official Alleva credentials/endpoints/scopes | R3/Alleva | Keep live import disabled; use upload/mock/API harness only. |
| Production PHI handling approval | R3/legal/compliance | Use synthetic or approved de-identified data only. |
| Signed installer/MSI/MSIX | Technical owner | Document current release-folder limitation until completed. |

---

## 20. Implementation Notes for Codex

Codex must:

- Inspect all repo folders before coding.
- Treat this PRD as controlling, but reconcile conflicts with current repo docs and configs carefully.
- Preserve security and PHI boundaries.
- Use deterministic rules as primary compliance logic.
- Keep optional LLM features disabled by default.
- Update tests with every functional change.
- Use computer use/browser automation for actual UI walkthrough.
- Do not push broken work to `main`.
- Do not claim tests or walkthroughs passed unless actually run.
