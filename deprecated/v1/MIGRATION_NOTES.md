# V1 To V2 Migration Notes

| V1 file or feature | V2 destination | Action | Notes |
|---|---|---|---|
| Treatment Plan Timeliness dashboard | `frontend/src/v2/pages/TreatmentPlansPage.tsx` | Pulled forward and rewritten | Rebuilt as the focused Treatment Plans Workbench. |
| 42-step checklist | `config/checklists/treatment-plan-v1.json` plus V2 criteria contracts | Pulled forward as config | The canonical 42 criteria remain the source of truth. |
| Alleva patient-centered treatment-plan pull | `backend/app/v2/api/routes.py` and V2 docs | Pulled forward and rewritten | V2 exposes ClientId-centered harness surfaces and keeps live sync gated. |
| manual upload ingestion | `frontend/src/v2/pages/ManualUploadPage.tsx` | Deferred | UI and contract are present; production parser hardening remains future work. |
| manager criterion review notes | `frontend/src/v2/components/TreatmentPlanDetailViewer.tsx` | Pulled forward and rewritten | V2 requires comments and override reasons at the criterion level. |
| manual overrides | `backend/app/v2/api/routes.py` | Pulled forward and rewritten | Overrides without a reason are rejected. |
| forensic audit logging | `backend/app/services/audit.py` | Pulled forward and rewritten | V2 hash-chain log records safe summaries only. |
| user management | `frontend/src/v2/pages/UsersPage.tsx` | Pulled forward and rewritten | Role boundaries are documented in the V2 surface. |
| API configuration/testing harness | `frontend/src/v2/pages/ApiHarnessPage.tsx` and `backend/app/v2/services/jobs.py` | Pulled forward and rewritten | Large all-fields pulls run as local jobs with bounded browser previews. |
| workflow profiles | `backend/app/v2/api/routes.py` | Deferred | A compatibility endpoint is present for smoke tests; full editor is deferred. |
| LLM configuration | V2 settings docs | Removed from V2 | LLMs remain disabled for compliance decisions. |
| FHIR/SMART-on-FHIR remnants | None | Removed from V2 | V2 focuses on Alleva REST/OpenAPI and manual upload evidence. |
| legacy Docker/PostgreSQL assumptions | None | Removed from V2 | Normal Windows use remains local FastAPI, React/Vite, and SQLite-ready local app data. |
| Windows preflight/start/build scripts | root `scripts/` | Pulled forward as config | Scripts remain active shared infrastructure and now target the V2 runtime path. |
| Treatment-plan detail/content model | `backend/app/v2/domain/schemas.py` | Pulled forward and rewritten | V2 models nested content snapshots, evidence refs, signatures metadata, and coverage. |
| Treatment-plan full field extraction | `backend/app/v2/services/jobs.py` | Pulled forward and rewritten | V2 writes JSONL, TSV/CSV, observed schema, and warnings/errors incrementally. |
| Large API pull/no-browser-timeout architecture | `backend/app/v2/services/jobs.py` and `frontend/src/v2/components/JobProgressCard.tsx` | Replaced | V2 returns compact job state and bounded previews instead of full payloads. |
