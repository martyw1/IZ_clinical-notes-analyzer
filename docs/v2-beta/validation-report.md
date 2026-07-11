# V2 Validation Report

## 2026-07-11 beta.2 release-readiness boundary

This report is updated for metadata `2.0.0-beta.2` / build `2026.07.11.1`. It records no new production, signing, retention, destructive-history, credential-rotation, or live Alleva validation claim. The required final gate is an isolated synthetic-only validation run with redacted evidence; supervised approved non-PHI/test-record Alleva validation remains external.

The procedure is maintained in `release-readiness-2026-07-11.md` and requires a fresh `%TEMP%` `IZ_CNA_LOCAL_APP_DATA_DIR`, no loaded local credentials/production `.env`, and no clinical export or production local-data reuse.

Validation recorded on 2026-07-08 for branch `codex/v2-beta-local-rebuild`.

## Final Command Evidence

The installer build evidence below was rerun after the final typed-response and route-size cleanup.

| Command | Result | Important output |
|---|---|---|
| `git status --short --branch` | Pass, dirty worktree expected before final commit | Branch `codex/v2-beta-local-rebuild`; active V2 files and `deprecated/v1/` archive changes are present; no runtime `.env`, database, upload, log, `node_modules`, or release artifact paths were shown as staged. |
| `$env:PYTHONPATH="$PWD\backend"; .\backend\.venv\Scripts\python.exe -m pytest .\backend\tests -q` | Pass | `8 passed, 1 warning`; warning is FastAPI/TestClient `httpx` deprecation. |
| `cd .\frontend; npm test -- --run` | Pass | `1 passed`, `4 passed`. |
| `cd .\frontend; npm run build` | Pass | Vite built `frontend/dist` successfully. |
| `.\scripts\preflight-windows.ps1 -AssumeYes` | Pass | Repo, AppData, local env, Python, backend venv, dependencies, current frontend build, V2 config/checklist, and port checks passed. |
| `.\scripts\test-local-app-stack.ps1` | Pass | Installs deps, runs backend tests, starts `app.main:app`, checks health/readiness/version/login/workflow, and shuts down. |
| `.\scripts\test-api-configuration-local.ps1` | Pass | Runs V2 backend tests, starts `app.desktop_main:app`, loads API configuration page, saves redacted API config, pulls sample OpenAPI definition with `ClientId`, starts bounded Pull ALL job, verifies preview and required artifacts. |
| `.\Build-IZ-Windows-Installer.cmd` | Pass | Backend tests, frontend tests/build, release required-file validation, release forbidden-file scan, and zip forbidden-file scan passed. |

Release outputs:

- `dist/windows-release/IZ-Clinical-Notes-Analyzer-v2.0.0-beta.1`
- `dist/windows-release/IZ-Clinical-Notes-Analyzer-v2.0.0-beta.1.zip`

## Fixes From Final Sweep

- Fixed `/api/readiness` response validation by replacing the shallow generic JSON response with typed `ReadinessOut` / `ReadinessCheck` models. Top-level readiness is now `warn` while the LOC-change update window remains unvalidated.
- Added backend coverage for `/api/readiness`.
- Fixed API configuration/OpenAPI response validation by adding typed API configuration, sample OpenAPI, and pull-definition models.
- Added backend coverage for the redacted API configuration response, sample OpenAPI definition, and `ClientId` pull-definition request.
- Updated `scripts/test-api-configuration-local.ps1` from archived V1 test coverage to active V2 coverage, including bounded Pull ALL job artifacts and preview checks.
- Split V2 API response models into `backend/app/v2/api/models.py` so the active route module stays under the route-size budget while preserving typed FastAPI response validation.

## Browser And Computer Use QA

Playwright/Chrome assertions passed against the built local desktop app at `http://127.0.0.1:8030`.

Screenshots saved under:

- `C:/Users/r3developer/AppData/Local/Temp/iz-v2-final-ui-qa/dashboard.png`
- `C:/Users/r3developer/AppData/Local/Temp/iz-v2-final-ui-qa/treatment-plans.png`
- `C:/Users/r3developer/AppData/Local/Temp/iz-v2-final-ui-qa/api-harness.png`
- `C:/Users/r3developer/AppData/Local/Temp/iz-v2-final-ui-qa/mobile-dashboard.png`

Assertions covered:

- Login reaches active V2 app shell.
- Header/footer show `Version 2.0 Beta`, `2.0.0-beta.1`, and `beta-local-desktop-v2`.
- Dashboard shows `Active runtime: V2`.
- Treatment Plans status order is exactly `Missing Data`, `Needs Review`, `Incomplete`, `Within Window`, `Late`, `Conflicting Evidence`, `Unable to Evaluate`.
- Treatment Plans uses `Patient ID 307` and did not render patient-name-like text.
- Treatment detail renders nested clinical content, signatures metadata without base64/image data, 42-step checklist, Evidence Coverage Map, and Raw Field Explorer.
- API Testing Harness renders `ClientId`, Pull ALL Treatment Plans, bounded browser output language, preview limit, and cancel action.
- Forensic Logs did not render synthetic secret/password strings.
- Settings keeps the LOC-change update window visibly `unvalidated`.
- Mobile viewport `390x844` had no document-level horizontal overflow.

Real Computer Use was used after the automated browser checks:

- Computer Use connected to Windows, listed apps, selected the returned Chrome window `IZ Clinical Notes Analyzer V2 Beta - Google Chrome`, and captured a real Windows screenshot of the V2 dashboard.
- Computer Use clicked Treatment Plans and captured the real Windows screenshot showing status cards, `Patient ID 307`, and selected treatment-plan detail.
- Computer Use clicked API Testing Harness and captured the real Windows screenshot showing `ClientId`, Pull ALL Treatment Plans, bounded preview, and cancel controls.

The temporary UI QA backend process was stopped after validation.

## Known Residuals

- Live Alleva import remains intentionally disabled until official tenant credentials, endpoint mapping, pagination, rate limits, attachment behavior, vendor documentation, and compliance approval exist.
- The LOC-change treatment-plan update window remains an R3/Marleigh blocker and is intentionally configurable/unvalidated.
- Manual upload production parsing is represented by V2 UI/contract readiness, but production parser hardening remains deferred.
- The exhaustive PDF test matrix is covered by active tests, scripts, docs, and UI evidence at the beta-slice level; it is not yet a full production certification suite.
