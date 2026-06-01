# Codex `/goal` Prompt: Implement Treatment Plan Timeliness Tracker MVP

Date/time stamp: 2026-06-01 08:00 America/New_York
Repository: `martyw1/IZ_clinical-notes-analyzer`
Primary PRD: `docs/prd-treatment-plan-timeliness-mvp-2026-06-01.md`

---

## Prompt to paste into Codex

```text
/goal
You are working in the GitHub repository `martyw1/IZ_clinical-notes-analyzer` on the `main` branch unless otherwise instructed. Use the full repo context and the PRD at `docs/prd-treatment-plan-timeliness-mvp-2026-06-01.md` as the source of truth.

Your mission is to implement the Treatment Plan Timeliness Tracker MVP described in the PRD. Work for as long as needed inside the Codex task/session to complete the implementation, tests, documentation, and packaging work. Use as much internal parallelization as your environment supports for independent analysis/test/build tasks, but avoid race conditions on the same files. Do not stop after a partial implementation unless blocked by missing external credentials or unavailable OS-specific resources; when blocked, document the blocker, preserve all completed work, and leave clear next steps.

Important constraints:
- Target users are non-technical Windows 10 Home and Windows 11 Home users.
- The MVP must not require Docker, PostgreSQL, Git, Node.js, Python setup, or command-line work for ordinary users.
- Keep the app local-first with SQLite as the desktop default.
- Preserve and extend the existing FastAPI backend, React/Vite frontend, encrypted local storage, YAML rules engine, audit logging, readiness checks, and Windows launcher/startup work already in the repo.
- Do not implement live Alleva API import as part of this MVP unless official sample data/API credentials and client approval are available. Keep live API import gated.
- Do not use an LLM for deterministic compliance decisions. Rule logic must remain explainable, testable, and auditable.
- Do not log PHI. Do not place PHI in rule files, logs, tests, or sample files. Use synthetic/de-identified data only.

Start by reading:
1. `docs/prd-treatment-plan-timeliness-mvp-2026-06-01.md`
2. `README.md`
3. `backend/app/services/rules_engine.py`
4. `backend/app/services/evaluation.py`
5. `backend/app/services/patient_notes.py`
6. `backend/app/models/models.py`
7. `backend/app/schemas/schemas.py`
8. `backend/app/api/routes.py`
9. `backend/app/core/config.py`
10. `backend/app/services/runtime_checks.py`
11. `backend/app/services/secure_storage.py`
12. `frontend/src/App.tsx`
13. `scripts/startup-windows-local.ps1`
14. `scripts/Start-IZ-Clinical-Notes-Analyzer.cmd`
15. `scripts/test-local-app-stack.ps1`

Implementation objectives:

1. Data model and schema
- Add or extend data structures for active client treatment-plan tracking.
- Support patient/client ID, optional client display name, active/discharged status, admission date, counselor/therapist, current level of care, level-of-care history, treatment plan records, signature dates, chart displayed due date, calculated due date, status, evidence, confidence, and manual overrides.
- Preserve backward compatibility with existing local SQLite installs using schema compatibility/bootstrap logic.

2. Rules engine
- Implement PRD rules for Initial Treatment Plan, Master Treatment Plan, ongoing Treatment Plan Reviews, PHP 30-day cycle, IOP-5/IOP-19/IOP-3/OP 60-day cycle, and level-of-care change update requirement.
- Make the level-of-care-change "immediate" window configurable. Default to same-calendar-day until R3 confirms otherwise.
- Add configurable level-of-care aliases.
- Implement status priority: Overdue, Urgent, Due Soon, Needs Review, Missing Data, Compliant.
- Implement the missing-data/conflicting-data decision matrix from the PRD.
- Ensure all calculations produce plain-English explanation and evidence fields.

3. Import/data entry
- Add a structured CSV/Excel-compatible template import path for the MVP.
- Prefer CSV and/or XLSX if feasible without adding fragile dependencies; otherwise provide CSV first and document XLSX as future/optional.
- Provide synthetic sample import files with no PHI.
- Support manual correction/editing of key fields.
- Do not build brittle PDF parsing as the primary MVP path.

4. Backend API
- Add APIs for dashboard summary, dashboard table, client detail, treatment-plan timeline records, manual overrides, and import/template download if appropriate.
- Enforce RBAC: admin and manager/office-manager can override by default; counselor cannot override unless explicitly configured later.
- Audit every import, calculation, edit, override, and unauthorized override attempt.
- Add or update readiness/version endpoints if installer/runtime changes require it.

5. Frontend UI
- Add Treatment Plan Timeliness dashboard view.
- Show summary cards: total active, compliant, due soon, urgent, overdue, needs review, missing data, compliance percentage.
- Add sortable/filterable table with patient ID or permitted name, level of care, counselor, admission date, last review date, next due date, days until due, status, rule used, evidence, last checked, and actions.
- Add client detail page with chronological treatment-plan table, level-of-care history, source evidence, warnings, and override form.
- Keep UI simple and clear for Marleigh/non-technical users.
- Use green/yellow/orange/red/gray-purple color semantics, with accessible text labels so color is not the only signal.

6. Security/session controls
- Confirm or implement 15-minute inactivity timeout, configurable if practical.
- Confirm or implement failed login lockout threshold of 5 failed attempts with admin unlock.
- Confirm PHI is not logged.
- Preserve encrypted local storage and encrypted secrets.
- Add tests for unauthorized override attempts and audit logging.

7. Windows installer and non-technical lifecycle
- Build or add a robust Windows installer approach suitable for Windows 10 Home and Windows 11 Home.
- The installer must bundle required runtime and built frontend assets or clearly build them during packaging, not require ordinary users to install developer tools.
- Installer must create Start Menu and optional Desktop shortcuts.
- Installer must support repair/modify behavior preserving database, encrypted uploads, `.env`, encryption keys, and audit logs.
- Uninstaller must preserve local app data by default and require explicit confirmation before deleting database, uploads, logs, or encryption keys.
- Add installer smoke tests/check scripts where possible.
- If the actual Windows installer cannot be built in the current environment, create the installer scripts/specification and document exactly how to build and verify it on Windows 10 Home and Windows 11 Home.

8. Browser support
- Support current Microsoft Edge and current Google Chrome on Windows 10/11 Home.
- Edge is the default supported browser.

9. Documentation
- Update README and/or add docs explaining:
  - Treatment Plan Timeliness MVP
  - rule behavior
  - import template
  - dashboard use
  - missing data / needs review handling
  - overrides and audit logging
  - Windows install/repair/uninstall
  - backup/restore, especially `.env` encryption key preservation
  - known open questions for R3

10. Testing requirements
Run and/or create tests across the full stack:
- Backend unit tests for rules and missing-data matrix.
- Backend API tests for dashboard, detail, imports, overrides, RBAC, audit logging.
- Frontend tests for dashboard/status rendering and detail/override flows.
- Full-stack local app smoke test.
- Functional tests for PRD acceptance criteria.
- Performance tests for at least 100 active clients and at least 1,000 historical treatment-plan records.
- Security-oriented tests for auth, lockout, unauthorized override, no PHI in logs, traversal/file safety where relevant, and encrypted storage behavior.
- Installer/packaging smoke tests where the environment supports it.

Test all PRD acceptance criteria, including edge cases:
- Admission 2026-02-26 with Initial signed same day is compliant.
- Admission 2026-02-26 with Master signed 2026-03-03 is compliant.
- PHP last review 2026-04-02 gives next due 2026-05-02.
- IOP-5 last review 2026-04-02 gives next due 2026-06-01.
- PHP to IOP-5 on 2026-03-30 with review 2026-04-02 uses IOP-5 60-day rule.
- Due in 10 days is Due Soon.
- Due in 5 days is Urgent.
- Due today is Overdue/red unless configured otherwise.
- Missing LOC with therapist signature is Needs Review, not guessed.
- Missing therapist signature is Missing Data.
- Duplicate reviews use latest therapist signature by default and show evidence.
- Master created within 30 days but signed after 30 days is noncompliant unless configuration says otherwise.
- LOC change without review inside configured window is Overdue or LOC Update Needed.
- Alleva displayed due date conflicts with calculated due date is Needs Review.
- Discharged client excluded from active dashboard.
- Unsupported/unreadable file never implies compliance.
- Manual override audits original value, new value, user, timestamp, and reason.
- Unauthorized override is blocked and logged.

Performance targets:
- Dashboard for 100 active clients loads in under 3 seconds on a typical local Windows laptop target, or document measured result and bottlenecks.
- Client detail loads in under 3 seconds for typical record sizes.
- Import of 100 clients and 1,000 treatment-plan history records should complete within a practical local-use window; document actual measured timing.

Security/pentest style checks:
- Verify auth required for protected APIs.
- Verify RBAC enforcement on override/admin routes.
- Verify upload path traversal is blocked.
- Verify unsupported files do not crash the app.
- Verify secrets/API keys are not returned to frontend.
- Verify logs avoid PHI/sample client names.
- Verify session timeout and lockout behavior.
- Verify encrypted storage marker/behavior for uploaded files where applicable.

Completion requirements:
- Commit all code, tests, docs, and installer artifacts/specs to the repo.
- Run all feasible tests and include exact commands and results in a completion log, such as `docs/CODEX_TREATMENT_PLAN_MVP_COMPLETION_LOG_2026-06-01.md`.
- If any tests cannot run because the environment lacks Windows, browsers, packaging tools, or external credentials, document the limitation and provide precise commands for a Windows validation machine.
- Update README with user-facing instructions.
- Leave the repo in a clean state with no temporary files, no secrets, no PHI, and no unrelated changes.
- Push completed work to the remote GitHub repo.

Do not stop at planning. Implement, test, document, and package as far as the environment allows. Be conservative about compliance claims: say "security-oriented tests" rather than claiming a formal penetration test unless a real pen-test methodology and tooling were executed.
```

---

## Notes

This prompt assumes the user will reference `docs/prd-treatment-plan-timeliness-mvp-2026-06-01.md` in Codex and wants Codex to implement the MVP directly in the repository. It intentionally tells Codex to avoid live Alleva API import, avoid LLM-based compliance decisions, avoid PHI in logs/tests, and preserve the local-first Windows desktop architecture.
