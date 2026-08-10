# V2 Data Contract

The backend Pydantic contract in `backend/app/v2/domain/schemas.py` and the frontend TypeScript contract in `frontend/src/v2/types/treatmentPlan.ts` define the V2 treatment-plan aggregate.

Required aggregate fields include MRN (stored in the legacy `patient_id` field), MRN-only display label, source mode, active status, status IDs/labels, LOC, admission date, LOC history, all treatment plans, active treatment plans, latest-created active plan, multiple-active-plan flag, review data status, due-date sources, overall status, data-quality warnings, source evidence, content sections present/missing, 42 criterion results, manager reviews, overrides, audit refs, evidence coverage, the source last-updated timestamp, and full content snapshot.

`GET /api/v2/patient-roster` returns MRN-centered rows with a `treatment_plans` collection ordered by descending `last_updated`. `GET /api/v2/treatment-plan-roster` returns locally synchronized Alleva plan rows with MRN, plan ID, last updated, previous plan ID, and initial plan ID/date. Exact detail retrieval uses MRN, plan ID, and source mode together.

The content snapshot preserves reason for admission, initial client needs, family education needs, problems, diagnoses, behavioral definitions, goals, objectives, interventions, signature metadata, observed fields, safe evidence references, redaction status, and content hash.

Signature image/base64 data is not included in normal browser payloads. Clinical narrative text is not written to forensic logs.

Beta.2 final validation uses only synthetic fixtures in an isolated local-app-data directory. It must not reuse clinical exports, production local databases, API reports, credentials, or uploads.
