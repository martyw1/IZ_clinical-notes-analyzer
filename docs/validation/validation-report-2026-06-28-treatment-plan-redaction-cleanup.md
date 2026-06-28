# Validation Report - 2026-06-28 Treatment-Plan Redaction Cleanup

Scope: IZ Clinical Notes Analyzer remediation for Alleva treatment-plan patient-name redaction, App Settings persistence, Treatment Plans pull/refresh access, deprecated-code quarantine, and documentation sync.

## Summary

- Alleva treatment-plan sync now defaults to generated `no-name-found_YYYY-MM-DD_HHMMSS` labels and does not retrieve/store/display patient names unless an administrator explicitly enables and saves `Import and display Alleva patient names`.
- Saving App Settings with patient-name import off redacts existing Alleva-sourced treatment-plan names again.
- Validation-only name fallback remains a separate off-by-default setting.
- The Treatment Plans tab has an admin-only `Pull / refresh treatment plans` action plus the existing queue `Refresh`.
- Legacy startup/helper scripts and historical UI reference code were moved into `depricated/` with `depricated/DEPRECATED-MANIFEST.md`.

## Automated Validation

Commands run:

```powershell
$env:PYTHONPATH='backend'
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_treatment_plan_timeliness.py backend/tests/test_schema_bootstrap.py -q
backend\.venv\Scripts\python.exe -m pytest backend/tests -q

cd frontend
npm run test -- --run App.test.tsx
npm run test -- --run
npm run build
cd ..

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-local-app-stack.ps1 -Port 8767 -SkipDependencyInstall
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-api-configuration-local.ps1 -Port 8768 -SkipDependencyInstall
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-alleva-api-connectivity.ps1
```

Results:

- Focused backend redaction/schema tests: `26 passed, 1 warning`.
- Full backend pytest: `118 passed, 2 skipped, 1 warning`.
- Focused frontend App tests: `17 passed`.
- Full frontend Vitest: `17 passed`.
- Frontend production build: passed.
- Windows local stack smoke: passed on `127.0.0.1:8767`; the script reran backend tests and verified health, readiness, version, login, authenticated profile, and workflow-profile calls.
- API configuration smoke: passed on `127.0.0.1:8768`; the script reran API connectivity tests, loaded the API configuration page, logged in, saved synthetic config, and pulled a sample OpenAPI definition.
- Alleva connectivity probe: public Swagger/OpenAPI endpoints were reachable; protected endpoints returned expected authentication responses without credentials.

## Browser Validation

Disposable app launch:

- Started through `scripts\start-windows-local.ps1 -NoBrowser -AssumeYes -SkipFrontendBuild`, matching the normal PowerShell launch path used by the desktop wrapper.
- Used synthetic local app data, synthetic bootstrap admin credentials, temp SQLite/uploads/logs, and no real PHI or live patient payloads.
- App health check passed on `127.0.0.1:8770`.

Verified in the in-app browser:

- Signed in as the synthetic admin user.
- App Settings showed `Import and display Alleva patient names`, `Allow name fallback only for validation`, and `Run treatment-plan sync now`.
- Toggling patient-name import and validation-only name fallback on, saving, and reading back showed both settings persisted.
- Toggling both settings off, saving, and reading back showed both settings stayed off.
- Treatment Plans showed exactly one `Pull / refresh treatment plans` button and one normal `Refresh` button.
- Clicking `Pull / refresh treatment plans` while sync was disabled showed the safe gated message: `Alleva treatment-plan sync is off in App Settings. Turn on Enable Alleva REST treatment-plan sync, save settings, then run again.`
- Primary navigation sweep passed for Status Dashboard, Treatment plans, Review queue, Checklist, Manual upload, User management, Workflow profiles, Forensic logs, Help, and App settings.
- Browser console error count: `0`.

## Boundaries

- Alleva live patient import and live treatment-plan sync remain blocked unless R3/Alleva approval, endpoint mapping validation, and the relevant App Settings gates are explicitly enabled.
- Patient-name import/display remains off by default and separate from validation-only name fallback.
- LOC-change treatment-plan update timing remains unvalidated and configurable.
- Validation used synthetic data only. No PHI, real patient names, real patient notes, production credentials, or live patient imports were used.
