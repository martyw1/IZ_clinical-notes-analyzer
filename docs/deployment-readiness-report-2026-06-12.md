# Deployment Readiness Report - 2026-06-12

App: IZ Clinical Notes Analyzer  
Version under test: `1.1.1` / build `2026.06.12.1`  
Goal source: `C:\Users\r3developer\Downloads\R3 Recovery Services Clinical Notes Analyzer Deployment-Readiness Goal.pdf`

## Readiness Decision

Status: ready for local upload-first daily use with synthetic/UAT validation evidence, while live Alleva authenticated operation tests and live patient import remain blocked.

The app is ready for non-technical Windows daily use of the existing local workflow: launch the localhost app, sign in, upload exported clinical-note/treatment-plan binders, review deterministic completeness and timeliness findings, route manager dispositions, inspect forensic logs, configure settings, and run safe API/readiness checks. The app must not be represented as ready for live Alleva patient import.

## Version and Packaging

- `/api/version` source metadata was updated to `1.1.1` / build `2026.06.12.1`.
- The React footer and Treatment Plans `Updated evidence queue` marker read the backend app version dynamically.
- Current release-folder target: `dist\windows-release\IZ-Clinical-Notes-Analyzer-v1.1.1`.
- Final release-folder build passed on 2026-06-12 and created:
  - `dist\windows-release\IZ-Clinical-Notes-Analyzer-v1.1.1`
  - `dist\windows-release\IZ-Clinical-Notes-Analyzer-v1.1.1.zip`
- Long-term packaging blocker remains: the release-folder installer is unsigned and is not a full MSI/MSIX with repair/modify support.

## PDF Issue Disposition

| # | Issue | Disposition |
| --- | --- | --- |
| 1 | Dig Deeper broken | Fixed and browser-verified. |
| 2 | All buttons work or explain | Fixed for tested deployment surfaces with UI feedback plus forensic UI events. |
| 3 | Blocked workflow clicks need feedback | Fixed with explicit status/dialog feedback. |
| 4 | All button presses logged centrally | Fixed through `POST /api/ui-events` and forensic `ui_interaction` audit events. |
| 5 | Criteria Review Workbench layout | Fixed with responsive/focusable workbench styling. |
| 6 | Primary Clinician false negative | Fixed by extracting readable upload/PDF metadata when form fields are blank. |
| 7 | Timezone handling | Fixed with facility timezone settings and local audit timestamp display. |
| 8 | LOC false negative | Fixed by extracting level-of-care metadata from readable upload/PDF text. |
| 9 | Single upload and multi-document | Verified through binder workflow and regression coverage. |
| 10 | Redacted/blank/missing name behavior | Fixed with distinct non-PHI placeholder names and status messages. |
| 11 | Alleva API connectivity harness | Harness fixed; live token request blocked by HTTP 400 pending vendor/R3 auth details. |
| 12 | Real redacted PDFs | Verified by regression tests using `example-treatment-plans` fixtures. |
| 13 | Placeholder name for hidden names | Fixed; hidden/redacted source names are not returned to browser. |
| 14 | Daily Alleva EMR checks | Safe daily readiness check added; live import remains gated. |
| 15 | Tracked live credential file risk | Fixed in working tree by replacing credential file with sanitized placeholder template. |
| 16 | Docker/PostgreSQL doc mismatch | Fixed in current operator/deployment docs; historical reports remain historical. |

## Automated Validation

Commands and results captured on 2026-06-12:

- Backend full suite: `PYTHONPATH=backend backend\.venv\Scripts\python.exe -m pytest backend\tests -q` -> `84 passed, 2 skipped, 1 warning`.
- Frontend tests: `npm run test -- --run` from `frontend` -> `11 passed`.
- Frontend production build: `npm run build` from `frontend` -> PASS.
- Windows preflight: `scripts\preflight-windows.ps1 -AssumeYes` -> PASS.
- Windows local stack smoke: `scripts\test-local-app-stack.ps1 -SkipDependencyInstall` -> PASS.
- Windows API configuration smoke: `scripts\test-api-configuration-local.ps1 -SkipDependencyInstall` -> PASS.
- Release package build: `scripts\build-windows-installer.ps1` -> PASS. It reran Windows preflight, backend tests, `npm install`, frontend tests, frontend build, and created the `v1.1.1` release folder and ZIP.

## UI and Persona Validation

Temporary local browser test covered:

- Admin sign-in.
- Dashboard safe daily source check, returning manual safe-check status.
- Review queue synthetic chart selection.
- Dig Deeper selecting an item, scrolling to `.criterion-workbench`, and focusing evidence details.
- Settings timezone update to `America/New_York`.
- SMART token URL/client-credentials fields present.
- Forensic logs showing `ui.button.click` with local timestamp display and `ui_interaction` category.
- Mobile settings layout at 390px wide with no horizontal overflow.
- Browser console error check returned no errors.

## API Harness Evidence

Safe external Alleva reachability was tested without printing or storing credential values in logs:

- `https://api.allevasoft.com/swagger/index.html`: HTTP 200.
- `https://api.allevasoft.com/swagger/v1/swagger.json`: HTTP 200, 942906 bytes.
- `https://authorization.allevasoft.com/connect/token`: HTTP 400 for provided client ID/secret using form-encoded `grant_type=client_credentials`.
- HTTP Basic client-auth variant with `grant_type=client_credentials`: HTTP 400.
- API root and generic `/swagger.json`/`/openapi.json` paths returned HTTP 401 where authentication is expected.

Sanitized report evidence:

- `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\api-connectivity-reports\alleva-api-connectivity-20260612-104057.json`
- `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\api-connectivity-reports\alleva-api-connectivity-20260612-104201.json`

No bearer token, API key, client secret, password, or encryption secret should appear in those reports.

## Forensic Logging Evidence

Verified forensic coverage:

- Upload/reanalysis paths log non-secret metadata and do not log uploaded note text.
- API configuration and token-test paths log status/source metadata without secrets.
- Dashboard daily safe check logs `review_source.daily_check.run`.
- UI button clicks log `ui.button.click` with allowlisted context.
- Blocked workflow clicks log `ui.button.event`.
- Audit-log responses include UTC evidence plus backend-generated local timestamp/effective timezone fields.

## Security Review

- `App Credentials Info.md` was replaced with a placeholder-only operator template.
- Saved API keys/client secrets are encrypted at rest and exposed to the browser only as configured booleans.
- Client-credentials access tokens are held in memory only for the current pull/test request.
- Browser payloads, audit details, and generated API reports redact secrets and bearer strings.
- A tracked-file secret scan found placeholders/code/test fixtures only after sanitization.

## Remaining Blockers

1. LOC-change treatment-plan update window remains unvalidated by R3/Marleigh. Required input: exact update window, calendar/business-day rule, trigger date, and operator label/default status.
2. Alleva client-credentials token request returns HTTP 400. Required input: confirmed tenant/client ID, secret, token URL, required scopes/audience/tenant fields, and whether credentials belong in form body or HTTP Basic auth.
3. Live Alleva patient import remains disabled. Required input: official tenant credentials, endpoint mapping, scopes, pagination/rate limits, attachment behavior, vendor documentation, and compliance approval.
4. Signed MSI/MSIX remains a long-term deployment improvement. The current release-folder installer supports double-click install/launch/uninstall but is unsigned and not a full repair/modify installer.

## Conclusion

Version `1.1.1` is deployment-ready for the local Windows upload-first workflow. It is not blocked for daily manual upload/review/timeliness use. It is blocked only for live authenticated Alleva operation testing, live patient import, and final signed-installer polish.
