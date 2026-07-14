# V2 Validation Report

## 2026-07-13 treatment-plan sync, roster, and export validation

The post-beta.2 feature validation passed on Windows with a disposable local-app-data directory and local synthetic Alleva service. A real Chrome window was driven through the visible Windows UI. The Treatment Plans pull created synthetic `plan-912`; a second pull with changed content under the same ID made version 2 current and preserved version 1; an unchanged pull from API Testing Harness left the populated queue intact. Patient Roster contained IDs/status metadata without patient names, the downloaded CSV included plan ID and status, and Forensic Logs showed `updated_treatment_plan_ids=plan-912`. The audit hash chain verified across the synthetic run.

Automated results after the automatic-mapping and source-identity fixes: backend `193 passed` with the existing Starlette/httpx deprecation warning; frontend `24 passed`; TypeScript `tsc --noEmit` and the production Vite build passed. Desktop Playwright UI validation passed `6` flows, including the shared pull, multiple selectable plans, same patient/plan IDs kept distinct by source, the name-free roster, manual upload, mocked sync, and queued-sync cancellation. Full details are in `../validation/validation-report-2026-07-13-treatment-plan-sync-roster-export.md`.

This is synthetic validation only. It does not approve live Alleva import, validate production credentials/data, resolve the LOC-change rule, or change the external production gates.

## 2026-07-11 beta.2 release-readiness boundary

This report is updated for metadata `2.0.0-beta.2` / build `2026.07.11.1`. It records no new production, signing, retention, destructive-history, credential-rotation, or live Alleva validation claim. The required isolated synthetic-only validation run completed with redacted evidence; supervised approved non-PHI/test-record Alleva validation remains external.

The procedure is maintained in `release-readiness-2026-07-11.md` and requires a fresh `%TEMP%` `IZ_CNA_LOCAL_APP_DATA_DIR`, no loaded local credentials/production `.env`, and no clinical export or production local-data reuse.

The retained 2026-07-08 evidence below is historical `2.0.0-beta.1` evidence. The completed beta.2 run is recorded next; it validates the final synthetic package, ZIP, and current launcher behavior without making a production or live-sync claim.

## Final beta.2 synthetic validation (2026-07-11)

Validation used an isolated synthetic local-data profile and no tenant credentials, clinical exports, or production local data. Only redacted command outcomes are retained here.

| Gate | Result |
|---|---|
| Windows preflight, V2 version/rules, and 42-step checklist | Pass |
| Active backend suite | Pass — 156 passed; one known Starlette/httpx deprecation warning |
| Frontend Vitest and production build | Pass — 15 tests and Vite build |
| Source-checkout CMD launcher | Pass — fresh-profile startup returned success only after HTTP 200 readiness; occupied-port startup returned nonzero |
| Packaged CMD launcher | Pass — readiness success and timeout-failure behavior verified |
| PyInstaller package, required-file validation, release-folder and ZIP forbidden-file scans | Pass |

Generated artifact: `IZ-Clinical-Notes-Analyzer-v2.0.0-beta.2.zip` (34,578,027 bytes), SHA-256 `26E9B89862BA68112B575C1CDCB62CE0ECFE46D4430AC3C6ED587AFA0C2EDFD3`.

## Historical beta.1 command evidence (2026-07-08)

The historical beta.1 installer build evidence below was rerun after the final typed-response and route-size cleanup.

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

Historical beta.1 release outputs:

- `dist/windows-release/IZ-Clinical-Notes-Analyzer-v2.0.0-beta.1`
- `dist/windows-release/IZ-Clinical-Notes-Analyzer-v2.0.0-beta.1.zip`

## Fixes From Final Sweep

- Fixed `/api/readiness` response validation by replacing the shallow generic JSON response with typed `ReadinessOut` / `ReadinessCheck` models. Top-level readiness is now `warn` while the LOC-change update window remains unvalidated.
- Added backend coverage for `/api/readiness`.
- Fixed API configuration/OpenAPI response validation by adding typed API configuration, sample OpenAPI, and pull-definition models.
- Added backend coverage for the redacted API configuration response, sample OpenAPI definition, and `ClientId` pull-definition request.
- Updated `scripts/test-api-configuration-local.ps1` from archived V1 test coverage to active V2 coverage, including bounded Pull ALL job artifacts and preview checks.
- Split V2 API response models into `backend/app/v2/api/models.py` so the active route module stays under the route-size budget while preserving typed FastAPI response validation.

## Historical beta.1 browser and computer use QA

Playwright/Chrome assertions passed against the built local desktop app at `http://127.0.0.1:8030`.

Screenshots saved under:

- `C:/Users/r3developer/AppData/Local/Temp/iz-v2-final-ui-qa/dashboard.png`
- `C:/Users/r3developer/AppData/Local/Temp/iz-v2-final-ui-qa/treatment-plans.png`
- `C:/Users/r3developer/AppData/Local/Temp/iz-v2-final-ui-qa/api-harness.png`
- `C:/Users/r3developer/AppData/Local/Temp/iz-v2-final-ui-qa/mobile-dashboard.png`

Assertions covered:

- Login reaches active V2 app shell.
- Historical UI assertion: header/footer showed `Version 2.0 Beta`, `2.0.0-beta.1`, and `beta-local-desktop-v2`.
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

- Operator-triggered read-only Alleva treatment-plan import remains off by default and requires saved tenant credentials, API/sync enablement, and explicit live-read authorization. The built-in mapping removes the separate mapping-approval form; supervised real-tenant validation and broader production/compliance approval remain external gates.
- The LOC-change treatment-plan update window remains an R3/Marleigh blocker and is intentionally configurable/unvalidated.
- Manual upload production parsing is represented by V2 UI/contract readiness, but production parser hardening remains deferred.
- The exhaustive PDF test matrix is covered by active tests, scripts, docs, and UI evidence at the beta-slice level; it is not yet a full production certification suite.
