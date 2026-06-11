# Codex /goal Prompt — Treatment Plan Checklist, UI/UX, API Harness, Windows 11 Completion

Use this prompt in the Windows 11 OpenAI Codex app with GPT-5.5 Extra High reasoning.

---

## /goal

You are working in the local Windows 11 clone of:

```text
https://github.com/martyw1/IZ_clinical-notes-analyzer.git
```

You have full local repo access on this Windows 11 laptop. Your job is to update the app so it fully implements the comprehensive updated PRD:

```text
docs/updated-treatment-plan-comprehensive-prd-2026-06-11.md
```

This includes treatment-plan checklist functionality, Marleigh’s validated 42-step checklist, daily API-monitoring workflow, manual monthly compliance-check workflow, UI/UX updates from `video-extract (2026-06-05)`, API harness updates, Windows 11 readiness, tests, documentation, and safe cleanup of obsolete files.

Do not make shallow changes. Inspect the entire repo first, including all subfolders, docs, configs, frontend, backend, scripts, tests, sample data, and especially:

```text
video-extract (2026-06-05)
```

That folder may include actual style sheets, CSS, component snippets, screenshots, extracted video notes, and UI recommendations. Treat it as a required UI/UX source.

---

## Mandatory Ground Rules

1. Work from the current local `main` branch after pulling latest remote changes.
2. Before editing, run:

```powershell
git status
git fetch origin
git pull --ff-only origin main
git status
```

3. If the working tree is dirty before you start, stop and report exactly what is dirty unless the dirty files are clearly your own generated temp files.
4. Use synthetic, fake, or approved de-identified data only.
5. Do not commit PHI, real patient names, secrets, API keys, bearer tokens, passwords, local `.env`, logs with PHI, runtime DBs, or screenshots with PHI.
6. Keep live Alleva patient import disabled until official credentials, endpoint mapping, and compliance approval exist.
7. Keep deterministic rules as the primary compliance mechanism.
8. Keep optional LLM features disabled by default.
9. Do not claim a test, build, browser walkthrough, or computer-use validation passed unless you actually ran it.
10. Commit only when the repo is in a tested, coherent state.

---

## Required Source Documents

Read and reconcile at minimum:

```text
docs/updated-treatment-plan-comprehensive-prd-2026-06-11.md
docs/prd-treatment-plan-timeliness-mvp-2026-06-01.md
docs/treatment-plan-checklist-v1.md
config/checklists/treatment-plan-v1.json
config/rules/alleva_treatment_plan_completeness_rules.yaml
docs/open-blockers.md
README.md
CHANGELOG.md
VERSION
VERSION.json
```

Also inspect all relevant files under:

```text
frontend/
backend/
scripts/
config/
docs/
docs/sample-clinical-notes/
video-extract (2026-06-05)/
```

If paths differ, find the equivalent folders/files and document what you found.

---

## Functional Implementation Requirements

### 1. Canonical 42-Step Treatment Plan Checklist

Implement Marleigh’s validated 42-step operational checklist as the current Version 1 treatment-plan checklist. Reconcile the current 20-step checklist with the 42-step checklist so the app does not contain conflicting sources of truth.

Update as needed:

```text
config/checklists/treatment-plan-v1.json
docs/treatment-plan-checklist-v1.md
frontend checklist UI
backend checklist APIs/tests
README/version-facing docs
```

The UI must show the checklist steps, acronym definitions, statuses, and LOC-change blocker clearly.

### 2. API and Manual Upload Source Modes

Ensure the dashboard and intake flow support both:

- EMR/API access path
- Manual upload path

Both paths must route into the same review/checklist/status workflow.

API mode must support daily monitoring when enabled/configured, but live Alleva patient import must remain gated until approved. Manual mode must clearly support monthly compliance-check workflow when 60+ active charts make weekly manual upload unrealistic.

### 3. Treatment Plan Timeliness Rules

Implement or verify:

- Active-client scope.
- Admission date capture.
- Current LOC capture and configurable LOC aliases.
- LOC history.
- Initial Treatment Plan exists, date, and required signatures.
- Master Treatment Plan exists, completed within 30 calendar days of admission, and required signatures.
- Latest valid Treatment Plan Review.
- PHP 30-day recurrence.
- IOP/IOP-5/IOP-19/IOP-3/OP/Outpatient 60-day recurrence.
- Current, due soon, urgent, overdue, missing data, conflicting evidence, unable to evaluate, returned, approved/finalized statuses.
- PHP and IOP/OP individual-session evidence checks when evidence is available.
- LOC-change update check stays unresolved/configurable/unvalidated.

Missing/conflicting evidence must never silently pass.

### 4. Manual Review, Overrides, Approval, Return

Implement or verify:

- Authorized reviewer confirmation.
- Override reason required.
- Override audit records user, timestamp, original value, new value, reason, affected rule/result, and chart.
- Manager review routing.
- Return for correction with specific correction comment.
- Approval only after issues are resolved or manually accepted.
- Review history preserved.

### 5. API Harness Updates

Verify and improve as needed:

- API configuration UI.
- Encrypted saved credentials.
- One-time API credential testing.
- OpenAPI/Swagger pull.
- Selected operation test workbench.
- Redaction of API keys, bearer tokens, sensitive query parameters, and sensitive response fields.
- JSON reports safe for sharing.
- Mock/source discovery remains available while live import is disabled.

---

## UI/UX Implementation Requirements

Inspect `video-extract (2026-06-05)` in depth and implement the UI/UX recommendations, including any real CSS/style sheets/snippets found there.

At minimum:

- Dashboard has clear source-mode cards for EMR/API and Manual Upload.
- Treatment Plans worklist is visibly current and shows version/current-build marker.
- Status filters and priority sorting are easy to use.
- Detail view is evidence-first: dates, signatures, LOC history, source/staff/LOC due-date comparison, conflicts, notes, audit history.
- Buttons have clear labels: View Details, Confirm, Override, Return for Correction, Approve, Export CSV, Export JSON, Copy Task List.
- Overrides require reason.
- Returns require correction comment.
- Status is not color-only; use labels/icons/text.
- Keyboard navigation and focus states work.
- Layout works on typical Windows 11 laptop screen sizes.
- Error messages and readiness results are plain-English.

---

## Deprecated / No-Longer-Needed Files Requirement

You must audit the repo for files that are no longer needed because they are obsolete, superseded, duplicate, abandoned, old generated artifacts, stale one-off outputs, or contradicted by the current Version 1 design.

Do **not** delete those files outright.

Create a top-level folder named:

```text
deprecated/
```

If the repo already contains a misspelled `depriceated/` folder from prior instructions, preserve it but migrate toward the correct `deprecated/` folder unless doing so would break an existing test or documented path. Document both names in the manifest if both exist.

Move no-longer-needed files into `deprecated/`, preserving original path context where practical. Example:

```text
old/path/file.ext -> deprecated/old/path/file.ext
```

Create or update:

```text
deprecated/DEPRECATED-MANIFEST.md
```

The manifest must list for every moved file:

- original path
- new path
- date moved
- reason moved
- replacement/current source of truth
- validation performed after moving it

Do not move active runtime files, current source files, active configs, active migrations, active tests, linked current docs, sample data required by tests, frontend build inputs, Windows startup scripts, or anything needed for install/start/test unless you first prove it is truly unused and update all references.

After moving deprecated files, search the repo for broken references and fix or document them. Then rerun tests/builds.

---

## Required Tests and Validation

Run as many of these as apply to the repo. If a command differs, find the current equivalent and document it.

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

Add or update tests for:

- 42 checklist steps.
- Checklist config/docs/UI consistency.
- API/upload source routing.
- Daily API-monitoring simulation.
- Manual monthly compliance-check workflow.
- Initial/Master plan timing and signatures.
- PHP 30-day and IOP/OP 60-day recurrence.
- LOC alias handling.
- LOC-change unresolved blocker.
- Missing/conflicting evidence.
- Override reason required.
- Role restrictions.
- Approval/return workflow.
- Export redaction.
- API secret redaction.
- Audit logs without secrets or note text.
- Deprecated-file manifest.
- UI/UX behavior and visible labels.

---

## Required Computer-Use / Browser Walkthrough

Use computer use or browser automation to actually walk through the app UI on localhost.

Required path:

1. Launch app.
2. Confirm version/footer/current-build marker.
3. Sign in as admin.
4. Complete password reset if prompted.
5. Open Dashboard.
6. Verify EMR/API and Manual Upload source cards.
7. Open Treatment Plans.
8. Verify visible updated evidence/worklist marker.
9. Verify status cards, filters, sorting, and worklist.
10. Open treatment-plan detail.
11. Verify source evidence, signatures, LOC history, source/staff/LOC due-date comparison, conflicts, and audit history.
12. Attempt override without reason and confirm blocked.
13. Add override with synthetic reason.
14. Export CSV and JSON.
15. Copy task list.
16. Open Manual Upload and upload synthetic/de-identified sample files.
17. Confirm created/updated review case.
18. Open Review Queue / Chart Audit and step through findings.
19. Return chart for correction with specific comment.
20. Approve chart after issues are resolved/accepted.
21. Open API Configuration and run safe sample tests.
22. Confirm secrets are redacted.
23. Open Settings and confirm LOC-change setting is visible/configurable/unvalidated.
24. Open Forensic Logs and confirm actions appear without secrets or uploaded note text.
25. Confirm keyboard navigation/focus states.

Save a validation report under:

```text
docs/validation/
```

Do not save screenshots containing PHI.

---

## Documentation Updates

Update documentation so a non-technical R3 user and a future developer understand the current state.

At minimum update as needed:

```text
README.md
docs/treatment-plan-checklist-v1.md
docs/open-blockers.md
docs/Windows-User-Guide-Version-1.md
docs/Windows-Deployment-and-Test-Guide-Version-1.md
docs/UAT-Version-1-Marleigh.md
CHANGELOG.md
```

Document exactly what remains incomplete, especially:

- live Alleva import gate
- LOC-change blocker
- signed installer/MSI/MSIX if not finished
- any validation that could not run

---

## Final Deliverables

When finished, provide:

1. Summary of functional changes.
2. Summary of UI/UX changes and exactly which `video-extract (2026-06-05)` assets/recommendations were used.
3. Summary of API harness changes.
4. Summary of deprecated files moved and manifest path.
5. Tests/builds run with pass/fail output.
6. Computer-use/browser walkthrough results.
7. Remaining blockers.
8. Final git status.
9. Commit hash.

Only push to remote `main` after all required tests and walkthroughs pass, or clearly state why a separate branch/PR is safer.
