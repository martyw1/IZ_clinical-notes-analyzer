# /goal Codex Prompt — Complete IZ Clinical Notes Analyzer Treatment Plan Checklist, UI/UX, API/Upload Workflow, Tests, and Cleanup

/goal

You are running in the OpenAI Codex app on a Windows 11 laptop, using GPT-5.5 Extra High reasoning. You have full access to the local clone of:

`https://github.com/martyw1/IZ_clinical-notes-analyzer.git`

Assume you are already in the correct local repo directory. Work locally first. Do not push to `main` until every required implementation, validation, test, UI walkthrough, and documentation update is complete.

## Mission

Complete the app so it satisfies the new comprehensive PRD for IZ Clinical Notes Analyzer: Treatment Plan Checklist, Timeliness, API/Upload Workflow, UI/UX Update, and Windows pilot readiness.

The controlling product requirement is the updated PRD provided with this prompt. Also inspect and reconcile all repo sources, especially:

- `README.md`
- `CHANGELOG.md`
- `VERSION`
- `VERSION.json`
- `docs/`
- all existing PRDs in `docs/`
- `docs/treatment-plan-checklist-v1.md`
- `docs/open-blockers.md`
- `config/checklists/treatment-plan-v1.json`
- `config/rules/alleva_treatment_plan_completeness_rules.yaml`
- backend app routes/services/models/tests
- frontend React source, components, CSS, tests
- scripts for Windows preflight/start/build/test
- `video-walkthrough/`
- `video-extract (2026-06-05)/` and any related stylesheets, snippets, screenshots, transcripts, or extracted UI recommendations

You must inspect the latest UI/UX recommendations in `video-extract (2026-06-05)` and implement every relevant UI/UX change unless it conflicts with security, PHI rules, or the PRD. If you choose not to implement a recommendation, document the reason in a PRD implementation note and in the final completion report.

## Critical Business Requirements

Marleigh confirmed:

1. If API/EMR automation is available, the app should check daily and notify her of anything needing review or follow-up.
2. If API/EMR automation is not available, each chart must be manually downloaded/uploaded, which is not ideal for 60+ active charts.
3. If manual upload remains the only option, the app should support a monthly compliance-check workflow rather than implying weekly manual upload is realistic.
4. The acronym definitions are accepted.
5. The 42 checklist items are accepted.
6. Use only de-identified/synthetic data until production PHI handling is approved.

## Non-Negotiable Safety and Compliance Rules

- Do not commit real PHI.
- Do not use real PHI in test fixtures, logs, screenshots, docs, exports, or prompts.
- Do not commit `.env`, SQLite runtime DBs, encrypted uploads, logs containing PHI, API keys, bearer tokens, passwords, encryption keys, or real patient notes.
- Do not expose saved API keys or tokens to the browser.
- Redact one-time keys, saved keys, bearer strings, token query parameters, sensitive response fields, and secrets in API reports.
- Do not fake live Alleva import.
- Keep deterministic rules as the primary compliance path.
- Optional LLM features must remain disabled by default and may not substitute for deterministic evidence.
- Missing or conflicting data must be Missing Data, Needs Review, or Unable to Evaluate; never silently compliant.
- The LOC-change treatment-plan update window remains unvalidated. Keep it configurable and visibly marked unresolved until R3 confirms the exact rule.

## Required Implementation Outcomes

### 1. Update Checklist Coverage

Implement the 42 Marleigh-validated treatment-plan checklist steps across configuration, backend logic, frontend UI, exports, and tests.

The current repo has a 20-step checklist framework. Reconcile it with the 42-step operational checklist. Do not simply hide or replace the old framework without ensuring current app logic still works. The UI must show the 42-step treatment-plan process in a practical, reviewable form.

Each checklist item must support:

- status
- source evidence
- finding message
- severity/priority
- reviewer action
- manual confirmation/correction/override where applicable
- required reason for overrides
- audit event
- export representation

### 2. Support API and Upload Source Modes

Implement or improve the two source modes:

#### API/EMR Mode

- Clearly show whether API mode is disabled, mock/stub mode, connectivity-test-only mode, or live approved mode.
- Maintain the current rule that live Alleva import is disabled unless official vendor/compliance approval exists.
- When live API mode is approved and configured, support daily refresh/checks.
- Daily check should surface new, changed, due soon, urgent, overdue, missing data, returned, and needs-review items.
- Provide in-app notifications/badges for Marleigh.
- Record last refresh, next refresh, changed item count, and errors.
- Include safe test/simulation coverage for daily monitoring without needing real Alleva credentials.

#### Manual Upload Mode

- Keep and harden file upload validation.
- Support initial chart review and existing chart update.
- Route uploads through the same review/checklist workflow as API items.
- Add UI language making clear that manual upload only reflects the uploaded data as of upload time.
- Add or improve a monthly compliance-check workflow for the manual-only scenario with 60+ active charts.

### 3. Treatment Plan Timeliness

Ensure the app correctly handles:

- active chart scope
- admission date
- current LOC
- LOC alias mapping
- LOC history
- Initial Treatment Plan existence/date/signatures
- Master Treatment Plan existence/date/signatures/completion within 30 calendar days
- latest valid Treatment Plan Review
- PHP 30-day interval
- IOP/IOP-5/IOP-19/IOP-3/OP/Outpatient 60-day interval
- due soon, urgent, overdue/current status
- conflicting source due date vs calculated due date
- source-document due date, staff-signature cadence due date, and LOC-effective cadence due date side by side
- LOC-change update as unresolved/configurable/Needs Review until confirmed
- PHP and IOP/OP individual-session evidence checks when source evidence exists

### 4. UI/UX Update

Read `video-extract (2026-06-05)` deeply and implement the latest UI/UX recommendations, including any provided CSS or component snippets.

Minimum UI/UX acceptance:

- Dashboard has clear review-source cards for EMR/API and Manual Upload.
- Treatment Plans tab has a visible current-build/current-queue marker.
- Treatment Plans worklist prioritizes overdue, urgent, due soon, needs review, missing data, returned, current, approved.
- Detail view is evidence-first and shows signatures, dates, LOC history, source evidence, conflicts, and audit history.
- Acronyms/definitions are available inside the app.
- Errors and readiness results are plain-English and actionable.
- Buttons are explicit: View Details, Confirm, Override, Return for Correction, Approve, Export CSV, Export JSON, Copy Task List.
- Returning a chart requires specific correction comments.
- Overrides require reasons.
- UI is keyboard navigable and has visible focus states.
- Status is never communicated by color alone.
- Layout works on typical Windows laptop screen sizes without awkward horizontal scrolling.
- No test screenshot or demo contains PHI.

### 5. API Harness Updates

Review and harden the API configuration/connectivity harness:

- Pull OpenAPI/Swagger definitions.
- Test base connectivity.
- Test selected operations.
- Redact secrets from request/response previews and reports.
- Save API keys encrypted only when the user explicitly saves them.
- Never return saved keys to browser.
- Produce JSON reports under the approved local app-data report folder.
- Add/repair tests for redaction, one-time key use, saved key non-disclosure, and failure messages.
- Include Alleva readiness but no unapproved live patient import.

### 6. Windows Non-Technical Readiness

Make the app realistic for Windows 11 non-technical use:

- Source-checkout startup still works.
- Preflight checks frontend build freshness.
- Built frontend assets are current.
- Local runtime data stays under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.
- Scripts use clear error messages.
- Installer/release-folder path is documented and tested as far as current repo supports.
- If a full signed MSI/MSIX is not implemented, document exactly what remains and why.
- Repair/uninstall behavior should preserve app data by default wherever implemented.

### 7. Deprecated File Cleanup

Identify files no longer needed.

Do not blindly delete anything. Move deprecated files into a repo-level folder named exactly:

`depriceated/`

Use this spelling exactly because that is the requested folder name.

Preserve original relative paths where practical. For example:

`old/path/file.ext` -> `depriceated/old/path/file.ext`

Create:

`depriceated/DEPRECATED-MANIFEST.md`

The manifest must include:

- original path
- new deprecated path
- reason moved
- replacement file/functionality, if any
- date moved
- validation that tests/build still pass after move

Do not move active runtime files, active docs linked from README, migrations, configs, sample test data, current scripts, tests, or anything needed by build/start/test unless you have verified replacement behavior.

### 8. Documentation Updates

Update docs after implementation:

- README
- CHANGELOG
- PRD implementation note
- Windows user guide
- Windows deployment/test guide
- UAT script for Marleigh
- open blockers
- API configuration docs
- workflow/checklist docs
- any docs impacted by UI/UX or script changes

Docs must clearly state:

- API mode daily monitoring requirement
- manual upload monthly compliance-check fallback
- 42-step checklist
- LOC-change unresolved blocker
- PHI restrictions
- how to run tests on Windows
- how to launch app on Windows
- what remains before pilot/production

## Required Testing

Run all relevant tests and fix failures. At minimum:

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

If paths differ, inspect the repo and use the correct commands. Do not skip tests because the first command fails; diagnose and repair.

Add or update tests for:

- 42 checklist steps
- API/upload source-mode routing
- daily API monitoring simulation
- monthly manual compliance-check workflow
- LOC mapping and unknown LOC
- Initial and Master plan due dates/signatures
- PHP 30-day and IOP/OP 60-day calculations
- LOC-change unresolved blocker
- missing/conflicting evidence behavior
- override reason required
- role restrictions
- approval/return workflow
- export redaction
- API secret redaction
- forensic logs without PHI/secrets
- UI status sorting/filtering
- UI/UX components from video extract
- deprecated file manifest

## Required Computer Use / Browser Walkthrough

Use Codex computer use or equivalent browser automation to actually walk through the app. Do not only rely on unit tests.

Start the app locally and verify the UI end-to-end in the browser. Walk through all key screens and buttons:

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
12. Add an authorized manual override with synthetic reason.
13. Confirm override without reason is blocked.
14. Export CSV and JSON.
15. Copy task list.
16. Open Manual Upload.
17. Upload synthetic/de-identified sample file(s).
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
30. Confirm keyboard navigation and focus states for key actions.
31. Confirm no PHI appears in screenshots/logs/artifacts.

Save a validation report in `docs/validation/` with:

- date/time
- machine/environment
- commands run
- test results
- browser walkthrough results
- screenshots if safe/synthetic only
- known limitations
- exact commit SHA

## Git Workflow

1. Start clean and synced.

```powershell
git fetch origin
git status
git log --oneline --decorate -5
```

2. Create a working branch.

```powershell
git checkout -b feature/treatment-plan-prd-42-ui-api-completion
```

3. Make small coherent commits as you complete work.

4. Before final push:

```powershell
git status
git diff --stat
git log --oneline --decorate -10
```

5. Final verification must pass.

6. Only after everything passes, push the branch. Do not push broken work to `main`.

7. If the user explicitly wants direct main update and all tests pass, merge/push to main using the repo’s accepted workflow. Otherwise leave as branch/PR-ready.

## Final Response Required From Codex

When done, provide a concise but complete completion report:

- summary of implemented functionality
- UI/UX changes completed from video extract
- checklist coverage confirmation
- API harness changes
- Windows install/start/test status
- deprecated files moved and manifest path
- tests run and results
- browser/computer-use walkthrough results
- remaining blockers/open questions
- exact branch and commit SHA
- whether anything was not completed and why

Do not claim success for tests or walkthroughs that were not actually run.
