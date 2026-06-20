# Validation Report - 2026-06-19 API Settings and Audit Repair

Scope: Version `1.4.4` / build `2026.06.19.2` patch for legacy SQLite audit-log startup errors, detached audit actor hardening, API settings save/reload reliability, API harness OpenAPI URL save behavior, saved OAuth credential reuse, Alleva quick-pull harness buttons, Chart Audit manual daily check behavior, Help/operator docs, and normal Windows local startup.

## Results

| Check | Result |
| --- | --- |
| Focused API/profile regression | Pass: `backend/tests/test_system_and_emr_readiness.py` and `backend/tests/test_api_connectivity.py` returned `30 passed` |
| Full backend pytest | Pass: `100 passed, 2 skipped` |
| Frontend Vitest | Pass: `16 passed` |
| Frontend production build | Pass: `npm run build` completed and generated `frontend/dist` assets |
| Windows local stack smoke | Pass: `scripts\test-local-app-stack.ps1 -Port 8030 -SkipDependencyInstall` completed; readiness, version, login, and workflow profile checks passed |
| API configuration smoke | Pass: `scripts\test-api-configuration-local.ps1 -SkipDependencyInstall` completed; focused API tests `20 passed`, page load, encrypted placeholder save, and local sample OpenAPI pull passed |
| Normal AppData startup | Pass: `scripts\startup-windows-local.ps1 -NoBrowser -SkipFrontendBuild -AssumeYes` started on port `8000`; `/api/health` returned `ok`; `/api/version` returned `1.4.4` / `2026.06.19.2` |
| Legacy audit schema repair | Pass: first normal AppData startup detected retired `audit_logs.fhir_audit_event` and rebuilt `audit_logs` without the retired required FHIR column |
| Button-click audit path | Pass: authenticated synthetic `/api/ui-events` click returned HTTP `204` on the normal local AppData database |
| Audit error scan | Pass: startup and button-click output contained zero `Forensic audit persistence failed`, `IntegrityError`, or `NOT NULL constraint failed` patterns |

## Notes

- No live Alleva patient import was run.
- No production Alleva credentials were used.
- API smoke used local synthetic/sample OpenAPI endpoints only.
- Alleva quick-pull regression used synthetic mocked treatment-plan/client payloads and verified raw returned rows were not written to audit details.
- Settings regression verified that encrypted API client secrets remain configured after a later save with a blank secret field and that the standalone harness recommends OAuth client-credentials mode when saved client credentials exist.
- Chart Audit daily-check regression verified that a manual check uses saved App Settings credentials even when the background periodic scheduler is off.
- An initial local stack smoke attempt on port `8000` hit an already-running Python app and returned login `401`; the same smoke passed on isolated port `8030`.
- The normal AppData startup repair modifies only the local SQLite `audit_logs` table shape to remove the retired required FHIR audit column while preserving current audit rows.
- Live Alleva REST treatment-plan sync remains disabled until R3/Alleva approval and endpoint mapping validation are complete.
