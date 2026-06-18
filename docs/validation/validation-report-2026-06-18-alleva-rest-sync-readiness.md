# Validation Report - Alleva REST Treatment-Plan Sync Readiness

Date: 2026-06-18

Version under test: `1.4.1` / build `2026.06.18.1`

## Scope

This validation covers the patch that separates Alleva REST treatment-plan sync from FHIR readiness. The goal is to support R3's desired workflow: pull treatment-plan source data from Alleva, normalize it locally, and run the existing R3 Treatment Plan Timeliness compliance rules inside this app.

## Key Assertions

- `Test-AllevaApi.ps1` style REST connectivity does not require a FHIR root.
- App settings now has separate Alleva REST API base URL, OpenAPI URL, API version, sync limit, startup toggle, live-sync approval, and endpoint-mapping validation controls.
- Startup sync is disabled by default.
- Live startup/manual sync cannot be armed unless credentials, approval, and endpoint mapping are present.
- Approved REST payloads can map into `TreatmentPlanClient`, `LevelOfCareHistory`, and `TreatmentPlanRecord` rows and then run through the R3 timeliness evaluator.

## Local Validation

Commands:

```powershell
$env:PYTHONPATH='backend'
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_system_and_emr_readiness.py backend/tests/test_treatment_plan_timeliness.py -q
cd frontend
npm run test -- --run
```

Results:

- Focused backend tests: `18 passed`
- Frontend Vitest: `15 passed`

## Remaining Gate

Do not enable startup live sync for production R3 data until R3/Alleva confirms the tenant credentials, endpoint mapping, active/discharged filtering, pagination, rate limits, authoritative signature/date/status fields, and PHI logging policy.
