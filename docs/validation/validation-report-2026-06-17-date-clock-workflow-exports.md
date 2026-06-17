# Validation Report - Date Clock and Workflow Exports

Date: 2026-06-17
Version under test: `1.4.0` / build `2026.06.17.1`
Data used: synthetic test fixtures only.

## Summary

Result: automated backend and frontend validation passed for the treatment-plan date-clock update, workflow exports, missing-name fallbacks, API settings validation, and workflow draft-edit behavior.

## Changes Validated

- Treatment-plan recurring date clock uses local/facility current date plus admission date or latest valid treatment-plan review/update date.
- PHP treatment levels use 30 calendar days; other configured treatment levels use 60 calendar days.
- LOC changes use a manager-editable 7-calendar-day preset while remaining visibly unvalidated until R3/Marleigh confirms the final rule.
- Timeliness analysis results are audited with workflow key/version/checklist context.
- Manual PDF source evidence can cite readable page numbers; API/FHIR evidence can cite source document IDs, DocumentReference IDs, attachment URLs, and Provenance IDs.
- Review and treatment-plan CSV/JSON exports include active workflow-step rows in addition to legacy checklist/domain rows.
- Draft workflow versions can be edited in place.
- App settings reports exact missing EMR/API and periodic-check fields before save.
- Alleva Swagger/OpenAPI URLs are documented as OpenAPI/API harness URLs, not FHIR base URLs.

## Automated Validation

| Check | Command | Result |
| --- | --- | --- |
| Backend test suite | `backend\.venv\Scripts\python.exe -m pytest backend\tests -q` | Pass: `93 passed, 2 skipped` |
| Frontend tests | `npm run test -- --run` from `frontend` | Pass: `15 passed` |
| Frontend production build | `npm run build` from `frontend` | Pass |
| Focused date-clock/upload/API tests | `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_treatment_plan_timeliness.py backend\tests\test_patient_note_uploads.py backend\tests\test_system_and_emr_readiness.py -q` | Pass: `24 passed` |
| Example treatment-plan upload smoke | Local synthetic TestClient upload pass across every file currently in `example-treatment-plans` | Pass: `4 file(s)` uploaded and appeared in the timeliness dashboard |

## Alleva Endpoint Check

On 2026-06-17, public endpoint review found:

- `https://api.allevasoft.com/swagger/index.html` is a Swagger UI page that references OpenAPI definitions.
- `https://api.allevasoft.com/swagger/v1/swagger.json` is an OpenAPI definition for Alleva REST API 1.0.
- `https://api.allevasoft.com/swagger/v2/swagger.json` is an OpenAPI definition for Alleva REST API 2.0.
- `https://api.allevasoft.com/advanced-form-elements` returned `401 Unauthorized` without credentials and is a protected REST operation path.

None of those URLs is the root FHIR R4 endpoint. The `FHIR base URL` field still requires an Alleva/R3 tenant-supplied FHIR root endpoint, for example an endpoint ending in `/fhir/R4`.

## Remaining Risks

- LOC-change treatment-plan update window remains unvalidated by R3/Marleigh.
- Live Alleva patient import remains intentionally disabled until official tenant credentials, endpoint mapping, scopes, pagination/rate limits, attachment behavior, vendor documentation, and compliance approval exist.
- Target Dell Windows packaging validation should still be repeated after building the 1.4.0 release package.
