# V2 Beta Recovery Status

Date: 2026-07-09

## Completed checkpoint

- Created the V1-to-V2 capability gap matrix in `docs/v2-beta/v1-to-v2-gap-matrix.md`.
- Replaced the V2 demo shell path with real protected backend APIs for login, current user, role-aware navigation, dashboard data, treatment-plan list/detail, manager actions, settings, API configuration, users, audit logs, and API harness jobs.
- Added local SQLite-backed V2 foundation models for users, app settings, encrypted API configuration state, and hash-chain audit events.
- Added local SQLite-backed treatment-plan aggregate imports. The default protected V2 queue is empty until a real normalized aggregate is imported.
- Added `POST /api/v2/manual-uploads/treatment-plan-aggregate` for role-gated normalized V2 aggregate import. The full aggregate payload is encrypted at rest; queue metadata stores patient ID, status, LOC, dates, and non-secret counts only.
- Wired the Manual Upload page to import a JSON aggregate file through the backend and then render the imported patient in Treatment Plans queue/detail.
- Added `POST /api/v2/manual-uploads/treatment-plan-file` for role-gated UTF-8 text, Markdown, CSV, TSV, readable PDF, and XLSX treatment-plan uploads. The parser accepts labeled treatment-plan fields, supports a Patient ID override fallback, builds a canonical 42-step V2 aggregate with nested problem/diagnosis/goal/objective/intervention/signature content, encrypts the persisted aggregate, archives the original source file encrypted under OS-local app data, and audits only redacted metadata.
- Wired the Manual Upload page to post supported files as `FormData` through the backend, report encrypted source-file archival, and then render the parsed patient in Treatment Plans queue/detail.
- Added Treatment Plan detail source-file archive controls. Archived manual source files now render as safe metadata, and manager/admin users can download the decrypted original bytes through an audited, role-gated, path-safe route with a generated filename rather than the original upload name.
- Added readable PDF and XLSX manual parsing. PDF text extraction uses bundled `pypdf`; XLSX extraction uses bounded standard-library OpenXML parsing for labeled cells, with archived source downloads preserving generated `.pdf` and `.xlsx` filenames.
- Added manager/admin source-file lifecycle delete controls. Deleting an archived source file removes only the encrypted original source bytes and source metadata, preserves the normalized treatment-plan aggregate, refreshes the Treatment Plan detail panel, and writes a redacted audit row.
- Added durable V2 manager-action persistence. Manager approve/comment/return/override payloads are stored in SQLite, merged back into Treatment Plan detail as `manager_reviews` and `overrides`, survive app restart, and continue to create audit rows.
- Added a Treatment Plan detail history panel showing persisted manager actions from backend detail data after reload/navigation.
- Hardened V2 checklist evidence export and API harness artifact downloads. CSV export now uses the standard CSV writer plus spreadsheet-formula neutralization for text cells; API harness downloads are limited to known generated artifact filenames instead of raw path joins.
- Added frontend coverage proving invalid login is rejected, login fetches the protected app shell, non-admin roles do not see admin-only navigation, treatment-plan review actions call the backend, write-only API secrets are not echoed, and API harness jobs/artifacts use backend endpoints.
- Verified the desktop app visually at desktop and narrow mobile widths through normalized JSON upload, parsed text upload, Treatment Plans queue/detail, and manager-review surfaces using synthetic non-PHI evidence.

## Boundaries preserved

- Alleva live treatment-plan sync remains disabled by default and gated until R3/Alleva approval, tenant endpoint mapping, pagination/rate-limit behavior, attachment behavior, auth requirements, vendor documentation, and compliance approval are complete.
- The LOC-change treatment-plan update window remains configurable and marked unvalidated until R3/Marleigh confirms the rule.
- Synthetic fixture data remains isolated to fixture/helper modules; production V2 treatment-plan pages now load persisted imports through backend APIs.
- Current manual upload support accepts normalized V2 aggregate JSON plus UTF-8 text, Markdown, CSV, TSV, readable PDF, and XLSX files with labeled treatment-plan fields. Supported source files are archived encrypted at rest without storing original filenames and can be downloaded or deleted later by manager/admin users through audited source archive controls. Scanned/non-extractable PDFs, multi-document binders, and patient ID correction UI remain open implementation stations.
- No PHI, credentials, local runtime files, uploaded notes, databases, logs, tokens, or vendor secrets are documented here.

## Live vs mocked coverage

- Live Alleva sync/import: not claimed; still gated off.
- Mocked Alleva/manual coverage: verified with a synthetic normalized V2 aggregate JSON file plus synthetic text, PDF, and XLSX treatment-plan uploads that all flow through the same persisted `TreatmentPlanAggregate` contract.
- Local storage coverage: verified that the imported aggregate survives restart and the stored DB payload is encrypted text, not plaintext JSON. Also verified that supported manual uploads write encrypted original source files under local app data, store only safe metadata in SQLite, keep original filenames/source text out of audit details, and remove archived source bytes/metadata through manager/admin delete controls while preserving the aggregate.
- Manager review coverage: verified manager override persistence, audit creation, detail reload, and restart behavior with backend tests; verified persisted manager history appears in the UI after browser reload/navigation.
- Export/download coverage: verified synthetic aggregate import over HTTP, CSV export over HTTP with comma/newline/quote parsing plus formula neutralization, valid API harness artifact download, unknown artifact rejection, audited manager/admin manual source-file downloads for text/PDF/XLSX source bytes, and audited manager/admin source-file deletion. Richer export scopes remain open.
- Browser coverage: verified login, normalized Manual Upload import, parsed text Manual Upload import with encrypted source-file archival status, Treatment Plans queue/detail source archive metadata/download/delete controls, manager override save, and persisted manager-action display through the running local desktop app. PDF/XLSX coverage is backend/API-level in this station.

## Verification snapshot

- Backend: `PYTHONPATH=backend backend/.venv/Scripts/python.exe -m pytest backend/tests -q`
- Frontend types: `npx tsc --noEmit`
- Frontend tests: `npm run test -- --run`
- Frontend build: `npm run build`
- Fake wiring search: no production imports of `frontend/src/v2/data.ts`; no hardcoded-token strings found in production backend/frontend paths
- Size guard: no changed Python/TypeScript source file exceeded 250 non-comment, non-blank lines
- Parsed-file browser QA screenshots: `.tmp/raw-upload-qa/manual-upload-desktop.png`, `.tmp/raw-upload-qa/treatment-plan-detail-desktop.png`, `.tmp/raw-upload-qa/manual-upload-mobile.png`
- Earlier browser QA screenshots: `.tmp/manual-upload-qa/manual-upload-imported.png`, `.tmp/manual-upload-qa/treatment-plans-after-upload.png`, `.tmp/manual-upload-qa/manual-upload-375.png`, `.tmp/manual-upload-qa/treatment-plans-375-after-upload.png`, `.tmp/manager-action-qa/manual-upload-imported-desktop.png`, `.tmp/manager-action-qa/manager-action-detail-desktop.png`, `.tmp/manager-action-qa/manager-action-detail-mobile.png`
- HTTP export/artifact QA artifacts: `.tmp/export-qa/formula-aggregate-812.json`, `.tmp/export-qa/checklist-evidence.csv`, `.tmp/export-qa/run-summary.download.json`
