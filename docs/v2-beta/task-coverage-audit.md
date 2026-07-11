# V2 Beta Task Coverage Audit

Audit refreshed on 2026-07-11 against the V2 Beta PDF task list.

| Task area | Status | Evidence |
|---|---|---|
| V1 archived outside active runtime | Covered | Active code lives in `backend/app/` and `frontend/src/`; V1 is archived under `deprecated/v1/`; active import scan has no `deprecated/v1` references. |
| V2 version/readiness boundary | Covered | `VERSION`, `VERSION.json`, `/api/version`, UI footer, sample OpenAPI metadata, and Windows preflight report `2.0.0-beta.2`, build `2026.07.11.1`, and `beta-local-desktop-v2`. |
| Patient-name minimization | Covered for V2 beta fixture | Backend/frontend tests and browser QA verify `Patient ID 307` and no patient-name-like text in active V2 payload/UI. |
| 42-step checklist | Covered for V2 beta fixture | Backend aggregate returns 42 criteria; frontend and browser QA render `42-STEP CHECKLIST`; coverage map shows 42 total. |
| Deterministic status order | Covered | Frontend tests and browser QA verify exact order: Missing Data, Needs Review, Incomplete, Within Window, Late, Conflicting Evidence, Unable to Evaluate. |
| Treatment-plan nested content | Covered for V2 beta fixture | UI and tests render diagnoses, behavioral definitions, goals, objectives, interventions, signatures metadata, and safe raw-field preview. |
| Signature/base64 exclusion | Covered for V2 beta fixture | Tests verify signature/base64 content does not render in active default browser payloads. |
| Evidence refs and coverage map | Covered for V2 beta fixture | UI renders evidence paths, safe previews, manager action fields, and Evidence Coverage Map. |
| Manager return/override behavior | Covered at beta level | Backend rejects override without reason; frontend blocks and saves with required reason; audit logging path is called. |
| API configuration redaction | Covered at beta level | Backend test and PowerShell smoke save a synthetic API key and verify only configured-state flags are returned. |
| API/OpenAPI sample harness | Covered at beta level | `/api/api-configuration/sample-openapi.json` and pull-definition endpoint pass backend and PowerShell smoke tests with `ClientId`. |
| Large Pull ALL jobs | Covered at beta level | Backend job returns `job_id`, completes asynchronously, writes JSONL/TSV/schema artifacts, exposes bounded preview, supports cancel endpoint, and passes PowerShell smoke. |
| Browser bounded output/no giant JSON | Covered at beta level | Frontend test and browser QA verify bounded artifact list/preview language and no raw signature payload rendering. |
| Forensic logs | Covered at beta level | Browser QA verifies logs page does not show synthetic secret/password strings; backend audit service emits hash-chain safe summaries. |
| User roles and shell navigation | Covered at beta level | Active V2 shell includes Users page and required nav order; deeper RBAC persistence remains future hardening. |
| Manual upload | Partial/deferred | V2 Manual Upload page and docs show supported file types and readiness; production parser hardening and full conversion-to-aggregate workflow remain deferred. |
| LOC-change rule | Blocked by business decision | LOC-change update window remains configurable and visibly unvalidated in readiness, settings, docs, and blockers. |
| Live Alleva import/sync | Intentionally blocked | Live sync remains disabled pending R3/Alleva approval, endpoint mapping, credentials, pagination, rate limits, attachment rules, vendor docs, and compliance approval. |
| Frontend visual QA | Covered | Chrome/Playwright screenshots and Computer Use Windows screenshots cover dashboard, Treatment Plans, API Harness, and mobile dashboard. |
| Windows preflight/local stack/API smoke | Covered | `preflight-windows.ps1`, `test-local-app-stack.ps1`, and `test-api-configuration-local.ps1` all pass in PowerShell. |
| Windows release package | Covered | `Build-IZ-Windows-Installer.cmd` passes and creates release folder/zip after forbidden-file scans. |
| Final commit | Covered | Validated V2 rebuild changes are staged and committed after the PowerShell, browser, Computer Use, and installer gates. |

## Bottom Line

The active V2 beta local-desktop slice is validated and packageable as a prerelease. It is not a production release: supervised approved live Alleva validation, credential rotation/downstream history-remediation approval, and signing/retention decisions remain external gates.
