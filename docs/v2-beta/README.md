# IZ Clinical Notes Analyzer Version 2.0 Beta

Version `2.0.0-beta.3` / build `2026.09.03.1` is the active local-desktop prerelease runtime on branch `main`.

The active backend lives in `backend/app/` and exposes a V2 boundary under `/api/v2`. The active frontend lives in `frontend/src/` and renders the V2 Treatment Plans Workbench. The pre-2.0 runtime is archived under `deprecated/v1/` for traceability and regression comparison.

V2 keeps the canonical 42-step checklist, deterministic timeliness rules, patient-ID-first Alleva contract, encrypted/local-first operating model, and audit/privacy posture. V2 removes the old frontend monolith from the active runtime path and de-emphasizes FHIR/SMART remnants, patient-name matching, giant browser JSON, and one-request large pulls.

Key validation records:

- `../guides/Version 2.0 Beta  2.0.0-beta.2  beta-local-desktop-v2/Marleigh-Setup-Install-and-User-Guide.html` is the illustrated non-technical setup, install, administrator, daily audit, and troubleshooting handoff for Marleigh.
- `../validation/office-manager-production-fixes-2026-09-03.md` records the current office-manager validation map and pending Task10 package/browser evidence; it does not claim final production readiness.
- `task-coverage-audit.md` maps the PDF task list to covered, partial, blocked, and deferred work.
- `release-readiness-2026-07-11.md` records historical beta.2 metadata, synthetic-only validation instructions, and the remaining external production gates. The illustrated guide directory name is historical and remains unchanged.
