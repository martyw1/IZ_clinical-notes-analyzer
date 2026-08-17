# IZ Clinical Notes Analyzer Version 2.0 Beta

Version `2.0.0-beta.2` / build `2026.07.11.1` is the active local-desktop prerelease runtime on branch `main`.

The active backend lives in `backend/app/` and exposes a V2 boundary under `/api/v2`. The active frontend lives in `frontend/src/` and renders the V2 Treatment Plans Workbench. The pre-2.0 runtime is archived under `deprecated/v1/` for traceability and regression comparison.

V2 keeps the canonical 42-step checklist, deterministic timeliness rules, patient-ID-first Alleva contract, encrypted/local-first operating model, and audit/privacy posture. V2 removes the old frontend monolith from the active runtime path and de-emphasizes FHIR/SMART remnants, patient-name matching, giant browser JSON, and one-request large pulls.

Key validation records:

- `validation-report.md` records the final real PowerShell, browser, Computer Use, and installer-build evidence.
- `task-coverage-audit.md` maps the PDF task list to covered, partial, blocked, and deferred work.
- `release-readiness-2026-07-11.md` records beta.2 metadata, synthetic-only final validation instructions, and the remaining external production gates.
