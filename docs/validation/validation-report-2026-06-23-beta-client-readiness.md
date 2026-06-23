# Validation Report - 2026-06-23 Beta Client Readiness

Scope: IZ Clinical Notes Analyzer `1.4.5-beta.1` / build `2026.06.23.1`, local Windows desktop beta-client-readiness pass for R3.

## Summary

- Status Dashboard branding, R3 logo display, Treatment Plans tab ordering, gated treatment-plan retrieval, App Settings clear-data controls, Help text, and responsive layout were browser-verified against a disposable local SQLite/upload/log environment.
- Backend and frontend automated tests passed after adding coverage for clear-data, manual-upload rollback, timeliness boundary windows, inactive clients, Alleva review field aliases, and Treatment Plan criterion manager notes.
- Review Queue was retained. It remains the uploaded-binder/manual generated chart-review workbench; Treatment Plans remains the active timeliness/due-date work queue.
- No `alleva_api_mapping.metadata.txt`, `.grid.tsv`, or `.long.tsv` mapping export files were present in the repo during this pass. The REST treatment-review mapper was only broadened with conservative date/signature/due-date field aliases while keeping live sync gated.

## Source Review

Reviewed source artifacts under `video-extract (2026-06-05)`:

- `clinical-logic-spec.md`: PHP cadence is 30 days, IOP/other configured non-PHP levels are 60 days, ongoing review date-clock uses Treatment Plan Review evidence, and LOC-change behavior remains unresolved.
- `source-evidence-matrix.md`: admission date, current LOC, LOC history, staff signature date, displayed next due date, and review evidence remain the important mapped fields.
- `verification-steps.md`: due today must not be silently overdue, and evidence conflicts/missing fields must stay explicit.

Resulting app behavior:

- Due dates before the evaluation date are `Overdue`.
- Due today and 1 day out are `Urgent`.
- 2 through 7 days out are `Due Soon`.
- 8+ days out are `Compliant`.
- Missing/conflicting source evidence still returns deterministic `Missing Data`, `Needs Review`, `Conflicting Evidence`, or `Unable to Evaluate`.

## Browser Validation

Disposable app launch:

- Port: `127.0.0.1:8765`
- Data: temp SQLite/upload/log directory under `%TEMP%`
- Login: synthetic bootstrap admin only

Verified in browser:

- Pre-login hero shows R3 logo and `R3 Recovery Services Status Dashboard`.
- Footer shows `Beta v1.4.5-beta.1`.
- Treatment Plans shows synthetic `PAT-BROWSER-100`, `Overdue`, `42-Step Checklist Evaluation`, `Save manager notes`, and `Export counselor actions`.
- Manager criterion status/comment saved, survived reload, and remained visible.
- Counselor action export button was clickable; the in-app browser cannot persist downloads, but the app stayed healthy and unit/backend tests cover CSV generation.
- Status Dashboard shows logo, EMR/API access, Manual upload card, `Retrieve Active Treatment Plans`, and `Clear All Patient Data`.
- No floating `Intake Guide` or `API Connectivity` buttons were present.
- Retrieve action was safely blocked with: `Alleva treatment-plan sync is off in App Settings...`
- Manual upload screen remains reachable and shows patient ID, upload mode, file input, and upload action.
- Help mentions Status Dashboard, Retrieve Active Treatment Plans, Clear All Patient Data, manager status/comments, Review Queue/Treatment Plans split, and startup sync off by default.
- App Settings shows Clear All Patient Data, API harness, treatment-plan sync button, and startup sync label `off by default for beta`.
- Clear-data modal required exact phrase `CLEAR ALL PATIENT DATA`; confirm button was disabled before typing; cancel closed the modal.
- Clear-data delete removed the synthetic patient from the Treatment Plans queue and showed the preservation message.
- Responsive checks at `1920x1080` and `390x844` showed no horizontal overflow; mobile retained logo and nav.

## Automated Validation

Commands run:

```powershell
$env:PYTHONPATH='backend'
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_patient_note_uploads.py backend/tests/test_treatment_plan_timeliness.py -q
backend\.venv\Scripts\python.exe -m pytest backend/tests -q
cd frontend
npm run test -- --run
npm run build
cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-local-app-stack.ps1 -Port 8767 -SkipDependencyInstall
```

Results:

- Focused backend tests: `29 passed`.
- Full backend tests: `114 passed, 2 skipped`.
- Frontend Vitest: `17 passed`.
- Frontend production build: passed.
- Windows local stack smoke: passed on `127.0.0.1:8767`; the script reran backend tests (`114 passed, 2 skipped`) and verified readiness, version, login, authenticated profile, and workflow-profile API calls against synthetic local app data.

## Boundaries

- Alleva live patient import and startup treatment-plan sync remain blocked unless R3/Alleva approval and endpoint mapping validation are both explicitly enabled.
- LOC-change treatment-plan update window remains unvalidated and configurable.
- Browser validation used synthetic data only. No PHI, real patient notes, real credentials, or live Alleva payloads were used.
