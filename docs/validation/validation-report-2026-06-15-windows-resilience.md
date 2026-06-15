# Validation Report - Windows Local Resilience 1.2.0

Date: 2026-06-15  
Version under test: `1.2.0` / build `2026.06.15.1`

## Scope

This validation covered the Windows local resilience and maintainability patch:

- SQLite local-desktop connection hardening.
- Same-browser session restore and stale-session clearing.
- Admin/manager default landing on Treatment Plans.
- Upload progress and in-app confirmation dialogs.
- Treatment Plan Timeliness status color separation.
- Prompted source-checkout dependency setup.
- Auth/user, Treatment Plan Timeliness, and workflow-profile route extraction plus feedback component extraction.
- Synthetic example treatment-plan PDF upload behavior.

## Commands Run

```powershell
$env:PYTHONPATH='backend'
.\backend\.venv\Scripts\python.exe -m pytest backend\tests -q
```

Result: `85 passed, 2 skipped, 1 warning`.

```powershell
$env:PYTHONPATH='backend'
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_config.py backend\tests\test_patient_note_uploads.py::test_redacted_example_pdf_upload_extracts_clinician_loc_and_placeholder_name backend\tests\test_patient_note_uploads.py::test_redacted_iop_example_pdf_upload_extracts_level_of_care backend\tests\test_patient_note_uploads.py::test_reanalysis_preserves_operator_display_name_for_redacted_upload backend\tests\test_treatment_plan_timeliness.py::test_patient_note_upload_syncs_treatment_plan_metadata -q
```

Result: `12 passed, 1 warning`.

```powershell
$env:PYTHONPATH='backend'
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_treatment_plan_timeliness.py backend\tests\test_patient_note_uploads.py backend\tests\test_system_and_emr_readiness.py -q
```

Result: `21 passed, 1 warning`.

```powershell
$env:PYTHONPATH='backend'
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_treatment_plan_timeliness.py backend\tests\test_patient_note_uploads.py backend\tests\test_config.py -q
```

Result: `22 passed, 1 warning`.

```powershell
$env:PYTHONPATH='backend'
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_auth_flow.py backend\tests\test_user_management.py backend\tests\test_forensic_audit_logging.py -q
```

Result: `16 passed, 1 warning`.

```powershell
$env:PYTHONPATH='backend'
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_workflow_definitions.py -q
```

Result: `3 passed, 1 warning`.

```powershell
$env:PYTHONPATH='backend'
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_treatment_plan_timeliness.py backend\tests\test_patient_note_uploads.py backend\tests\test_treatment_plan_checklist.py -q
```

Result: `17 passed, 1 warning`.

```powershell
cd frontend
npm test -- --run
npm run build
```

Result: Vitest `12 passed`; Vite production build passed.

```powershell
.\scripts\preflight-windows.ps1 -AssumeYes
.\scripts\test-api-configuration-local.ps1 -SkipDependencyInstall
.\scripts\test-local-app-stack.ps1 -SkipDependencyInstall
```

Result: Windows preflight passed; API configuration local smoke passed; local app stack smoke passed.

## Repository Hygiene

- Secret-pattern scan found no high-risk API key, bearer-token, or private-key matches in tracked/source files outside ignored runtime/build folders.
- Runtime-data scan found only `.env.example` in the repo after excluding ignored runtime/build folders.

## Browser Upload Validation

A final-state disposable desktop server was launched on `http://127.0.0.1:8038` with temporary SQLite, upload, log, and `.env` paths outside the repo.

Using installed Chrome through local browser automation:

1. Signed in as synthetic bootstrap admin.
2. Opened `Manual upload`.
3. Confirmed `/api/version` returned `1.2.0` / build `2026.06.15.1`.
4. Selected `example-treatment-plans\JTXP.pdf`.
5. Waited for patient-ID detection to finish and the upload button to become enabled.
6. Uploaded the file with synthetic patient ID `PAT-UI-JTXP`.
7. Waited for generated review queue.
8. Confirmed the review workbench, synthetic patient ID, treatment-plan text, and upload success status were visible.

The disposable server process was stopped after validation.

## Computer Use Status

Computer Use was reachable, enumerated Windows apps, opened Chrome to the disposable local app, signed in with the synthetic bootstrap admin, and verified the Treatment Plans queue text. The actual PDF file selection/upload was completed through Playwright against the same disposable server so the test could set the browser file input reliably.

## Residual Validation Needed

- Target Dell Windows 10/11 Home validation remains open until ordinary-user launch, prompted setup, readiness, repair/upgrade/uninstall, and data-preservation behavior are verified on that machine.
