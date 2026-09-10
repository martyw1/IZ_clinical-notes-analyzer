# Office-manager smoke test: Edge and Chrome, 2026-09-03

## Outcome

**NEEDS WORK. Local smoke execution is complete; the app does not receive a clean functional or production-readiness pass. No application code was changed.**

Highest-priority confirmed defect: returning an explicitly selected older treatment plan for correction assigns the correction to a different, newer plan for the same patient. The full backend suite also fails consistently.

The run exercised the active V2 user interface in actual Microsoft Edge on Windows 11, primarily with Windows computer use (mouse, keyboard, scrolling, native file dialogs). Supplemental automation used the installed Edge and Chrome binaries. Administrator coverage was followed by actual office_manager and counselor roles. This is an application workflow test using synthetic data, not clinical advice or certification of clinical compliance.

## Environment and boundaries

- Windows 11 Home; Edge 152.0.4191.53; Chrome 152.0.7977.65.
- App 2.0.0-beta.2, build 2026.07.11.1, beta-local-desktop-v2, active runtime v2.
- /api/version reported source commit 438c72644363, branch main, git_dirty=false before this report.
- Isolated development runtime: C:/Users/r3developer/AppData/Local/Temp/IZ-CNA-Edge-Smoke-20260903.
- Local service: http://127.0.0.1:8765. Started for testing, signed out and stopped at closeout.
- Existing Chrome window was preserved. Comparison checks used a separate installed-Chrome automation context.
- Initial worktree was clean. Source/test files, rules, version metadata, and production configuration were not edited.
- Runtime-only changes: synthetic imports, test accounts/assignments, synthetic review actions, unchanged local-settings save, and a localhost sample OpenAPI URL. No real vendor credentials were supplied; API testing/live-sync authorization remained off.
- Synthetic users: admin, smoke-counselor, smoke-manager. Secrets are intentionally omitted.
- Synthetic patients: TEST-PATIENT-001 (two distinct plans), TEST-PATIENT-002 (one plan). No real patient chart was used.
- Primary existing fixture: docs/sample-clinical-notes/treatment_plan_tracking_note.txt. Additional normalized JSON fixtures are in the isolated runtime folder.
- A positive test of “all real patients” is blocked by absent approved live tenant access, credentials, mapping, pagination/attachment validation and compliance approval. This run establishes only the tested synthetic/local behavior.

## Findings, ordered by impact

### F01 HIGH: Return-for-correction targets the wrong plan

**Runtime reproduced with visible Edge computer use and independently corroborated source tracing.**

1. Import the original text fixture as manual-TEST-PATIENT-001-c9e07ffa.
2. Import a second normalized plan, SMOKE-SECOND-PLAN-001, for the same MRN.
3. In Patient Roster, explicitly choose the ORIGINAL manual plan. The page heading confirms that ID.
4. Enter: “Synthetic scoping check: return ORIGINAL manual-TEST-PATIENT-001-c9e07ffa only, not SMOKE-SECOND-PLAN-001.”
5. Click Return for correction.
6. Counselor corrections API returns work_item_id=2, plan_version_id=2.
7. A read-only SQLite identity query maps version 1 to the selected original plan and version 2 to SMOKE-SECOND-PLAN-001.

Observed rows:

```text
1 | manual_upload | manual-TEST-PATIENT-001-c9e07ffa | version_ordinal 1
2 | manual_upload | SMOKE-SECOND-PLAN-001           | version_ordinal 2
```

The original-plan page shows the return in its history, but the correction belongs to the second plan. The synthetic incorrect return is deliberately preserved for reproduction. There was no real clinical workflow change.

Evidence: [original plan after return](C:/Users/r3developer/AppData/Local/Temp/IZ-CNA-Edge-Smoke-20260903/evidence/14-original-plan-wrong-return.png). Independent source tracing: [TreatmentPlanDetailPage.tsx](<C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/frontend/src/v2/pages/TreatmentPlanDetailPage.tsx:59>), [client.ts](<C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/frontend/src/v2/api/client.ts:203>), [manager_action_store.py](<C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/backend/app/v2/services/manager_action_store.py:143>). Writes omit selected-plan identity; the store selects the latest patient version. Other manager actions also use patient-wide review identity in source; only the incorrect return binding was runtime-demonstrated here.

### F02 HIGH: Full backend suite is not green

Two complete runs produced **199 passed, 57 failed, 1 warning**. The second run has durable console and JUnit artifacts. Three representative failures passed when run independently, suggesting test-order/shared-state isolation problems, but that is an inference, not a completed root-cause diagnosis.

Do not treat isolated successes or frontend success as evidence that the full backend is healthy. No tests were edited, skipped or weakened.

### F03 MEDIUM: Evidence search does not search evidence text

Searching “review required,” a phrase present in a criterion's safe evidence preview, returns zero criterion matches. The UI promises “Search checklist evidence” / “Search criteria and evidence,” but source filtering uses criterion titles only. A previously selected evidence panel can remain visible independently of the empty filtered list.

Title search, including “LOC Change Update,” works. All 42 criterion selectors work individually.

Evidence: [no-match evidence search](C:/Users/r3developer/AppData/Local/Temp/IZ-CNA-Edge-Smoke-20260903/evidence/15-evidence-search-no-match.png), [filter implementation](<C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/frontend/src/v2/components/TreatmentPlanDetailViewer.tsx:55>).

### F04 MEDIUM: Manual-source identity/date compatibility limits patient discovery

The supplied text fixture contains a synthetic patient name, service date, original treatment-plan reference, and combined signature/completion prose. Its name is unavailable in Patient Roster/Patient Record Detail; its generated stored plan ID differs from the source reference; signature/plan timeline values remain unknown.

Independent source review found unsupported manual-parser labels rather than a lost live Alleva record. MRN lookup and the generated plan ID still work. Adding patient_full_name to a normalized manual aggregate also did not create a displayed patient-name snapshot in this run.

Important correction to earlier status wording: admission, LOC and due-date fields were NOT present in the source fixture. Unknown/Missing Data for those fields is correct and must not be guessed from service date or a plan-reference suffix. The signature date appears in unsupported combined prose, not a supported signature_date field.

Impact: an office manager cannot find these manual-source charts by the provided full name/source plan reference as the Help/search copy suggests. The UI needs a clearer explanation of supported source fields and source-snapshot boundaries.

Evidence: [patient record](C:/Users/r3developer/AppData/Local/Temp/IZ-CNA-Edge-Smoke-20260903/evidence/04-patient-record-detail.png), [two-patient manager roster](C:/Users/r3developer/AppData/Local/Temp/IZ-CNA-Edge-Smoke-20260903/evidence/17-office-manager-two-patient-roster.png), [manual parser](<C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/backend/app/v2/services/manual_file_parser.py:19>).

### F05 MEDIUM: Treatment Plans Roster and its export have different scopes

Patient Roster shows the manual plan(s). Treatment Plans Roster remains empty and says no Alleva plans match. Its CSV export includes manual plans.

This is an intentional Alleva-only screen filter, not disappearing imported data. The broad description “All treatment plans synchronized into the local encrypted store” and all-source export make the scope confusing. After three manual plans across two MRNs, the same source distinction remains.

Evidence: [empty Alleva roster](C:/Users/r3developer/AppData/Local/Temp/IZ-CNA-Edge-Smoke-20260903/evidence/06-treatment-plans-roster.png), [source filter](<C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/backend/app/v2/services/patient_roster.py:113>), [all-source export](<C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/backend/app/v2/api/runtime_routes.py:443>).

### F06 MEDIUM: Signature metadata runs together

The signature row displays:

```text
parsed_manual_signatureunknownUnknownmanual upload parser stores signature timestamp only
```

Type, role, timestamp and explanation have no visible separation. Confirmed in visible Edge and a settled saved capture.

Evidence: [settled detail](C:/Users/r3developer/AppData/Local/Temp/IZ-CNA-Edge-Smoke-20260903/evidence/05-treatment-plan-detail-settled.png), Clinical review history, and [signature rendering](<C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/frontend/src/v2/components/TreatmentPlanDetailViewer.tsx:214>).

### Smaller defects and clarity issues

| ID | Result / impact | Observation |
|---|---|---|
| F07 | Low, input validation | Blank login password produces generic “The local API request failed” instead of an actionable password message. The API rejects the invalid input. |
| F08 | Low, session recovery | After a long idle period, expired authentication leaves an “Invalid token” page with signed-in navigation. Sign out and sign in recovers; no helpful reauthentication prompt was observed. |
| F09 | Low, upload feedback | Removing the selected binder file clears the app's list but leaves the native file-input filename visible. Clear selection clears both. |
| F10 | Low, upload feedback | Successful normalized aggregate import leaves its selected filename in the native input. Binder submission did clear its filename. |
| F11 | Low, empty-state copy | Patient Record Detail says no patient fields match the current search even with a blank query and no source snapshot. |
| F12 | Low, missing-data presentation | Clinical overview leaves Reason for admission / Initial client needs / Family education needs blank, unlike explicit Unknown markers elsewhere. |
| F13 | Low, metric interpretation | Coverage map shows total 42, with evidence 30, missing 11, conflicting 0, without explaining the remaining criterion. These are not assumed to be mutually exclusive categories; their meaning is unclear. |
| F14 | Low, metric interpretation | Dashboard risk cards omit counting units; Missing data counts exceed patient count. Needs review/Unable can show zero while individual checklist criteria have those states. No incorrect clinical calculation is inferred without a defined metric contract. |
| F15 | Low, readability | Audit/review timestamps lack explicit timezone in several rendered rows; settings/user action spacing is cramped. Independent visual reviewers noted these. |
| F16 | Low, supplemental narrow-screen check | Plan detail at a 375px viewport has document scrollWidth 435px (60px horizontal overflow). At 768 and 1280, scrollWidth matches viewport. This was supplemental; a complete mobile/accessibility audit was not performed. |

No fixes were applied.

## User interaction log

“Pass” means the named observed behavior worked, not that the entire page is defect-free. Safety-blocked/unexecuted controls are separately identified below.

| Check | Surface / action | Result and evidence |
|---|---|---|
| U01 | Edge launch and local page | Pass. Actual installed Edge on Windows 11, localhost service. |
| U02 | Empty and valid login | Invalid empty input rejected; generic message logged F07. Valid admin/counselor/office_manager logins work. |
| U03 | Bootstrap reset boundary | Forced password-reset screen appears. Final Windows password-change action not clicked; isolated credential setup used local API. |
| U04 | Sign out / sign back in | Pass for all tested roles. Browser password-save prompts dismissed; credentials not saved. |
| U05 | Idle-session recovery | Invalid token observed after long idle; manual sign out/in recovers (F08). |
| U06 | Dashboard empty state and refresh | Pass. Refresh timestamp changes; readiness and LOC blocker visible. |
| U07 | Dashboard after imports/review | Counts update after refresh; returned count becomes 1 after return and 0 after counselor submission. Metric clarity caveat F14. |
| U08 | Patient Roster empty state | Pass. Clear empty state, disabled live pull and listed prerequisites. |
| U09 | Patient MRN lookup | Pass. Imported MRN found; no-match query gives empty results; clearing restores. |
| U10 | Patient names and source identity | Limitation/F04. Manual-source names remain unavailable. |
| U11 | Open patient record | Pass. MRN button opens matching patient; source, lifecycle, LOC and linked plans visible. |
| U12 | Unselected record/detail pages | Pass. Provide instructions/navigation instead of fabricated data. |
| U13 | Patient source-field explorer | Empty snapshot displayed, but misleading search empty-state copy F11. |
| U14 | Single-plan dropdown | Pass. Opens matching treatment-plan detail. |
| U15 | Multi-plan dropdown | Pass. Both original and second-plan IDs are selectable for patient 001; distinct content appears. |
| U16 | Multiple-patient navigation | Pass. Actual office_manager finds both MRNs and opens patient 001 and 002 plans. |
| U17 | Clinical content | Pass. Problem, goal, objective and intervention from the text fixture are readable. Missing-source limits remain explicit except F12. |
| U18 | Timeline and status | Unknown/Missing Data retained rather than guessed. LOC-change clock remains unvalidated/configurable. |
| U19 | All 42 checklist selectors | Pass, 42/42 clicked in installed Edge supplemental automation; each matching detail heading appeared. No pageerror emitted. |
| U20 | Checklist title search | Pass. Late checklist title located; list can be scrolled. |
| U21 | Evidence-value search | Fail F03. Preview phrase has zero matches. |
| U22 | Empty comment/override validation | Pass. Actionable “add a comment” / reason-required feedback. |
| U23 | Approve criterion | Pass for single-plan UI action/history persistence. Does not prove multi-plan action identity. |
| U24 | Save manager comment | Pass as admin and actual office_manager. Patient 002 comment appears attributed to smoke-manager. |
| U25 | Return without counselor | Pass safety validation. Exactly one assigned counselor required. |
| U26 | Return with counselor | Single-plan return persisted and appeared in counselor queue. |
| U27 | Return older plan with two plans | FAIL F01. Stored correction targets newer plan. |
| U28 | Override with reason | Pass. Synthetic reason and action persist in manager history. No clinical approval implied. |
| U29 | Counselor correction empty resolution | Pass validation; blank note rejected. |
| U30 | Counselor submits resolution | Pass. Queue becomes empty; dashboard Returned drops; submission appears in manager history. |
| U31 | Review history | Five earlier actions visible including correction submission; later scoping return and manager-role comment also persisted. |
| U32 | Raw Field Explorer | Expand/filter works; five parsed source paths shown, bounded previews and 100-field cap. |
| U33 | Source archive | One encrypted source listed with generated ID, type, size, checksum and download control. |
| U34 | Source download | Pass. Generated anonymous filename; downloaded 907-byte original synthetic source. |
| U35 | Checklist evidence CSV | Pass. 42-criterion minimum-necessary CSV downloaded and inspected. |
| U36 | Treatment Plans Roster refresh/search shell | Controls usable; no authorized Alleva dataset to exercise populated rows. Scope mismatch F05. |
| U37 | Treatment-plan CSV export | Pass download; contains manual plan despite empty Alleva screen (F05). |
| U38 | Binder native file picker | Pass after tool-specific dialog targeting recovery. |
| U39 | Binder MRN override/confirmation | Controls exercised; matching synthetic MRN import succeeds. Mismatch-override positive case not run. |
| U40 | Binder import | Pass. One selected/parsed file, zero opaque; MRN imported, source archived; review-in-roster link works. |
| U41 | No-file binder/aggregate submissions | Pass. Both forms show actionable choose-file errors. |
| U42 | Binder Remove / Clear selection | Remove has stale native filename F09; Clear selection works fully. Same-file reselection succeeds. |
| U43 | Normalized JSON import | Pass via visible Edge for second plan, and installed Edge automation for second patient using actual office_manager. F10 filename retention. |
| U44 | Settings display/save | Pass unchanged save. LOC 7 days remains unchecked/unvalidated; no validated value asserted. |
| U45 | API auth-style dropdown | Body/basic selections exercised and restored. No vendor credential supplied. |
| U46 | Save localhost sample OpenAPI | Pass. Saved sample URL points only to localhost. Credential requirement remains explicit. |
| U47 | Pull / Load OpenAPI | Pass. Local Connectivity Test Definition with one operation loaded. |
| U48 | OAuth test without credentials | Pass fail-closed validation. Missing client ID and secret reported; no live credential test. |
| U49 | Harness diagnostic pull disabled configuration | Pass fail-closed feedback: enable API testing first. No job created. |
| U50 | Operational live pull / sync | Disabled with explicit configuration/approval blockers, preserved. |
| U51 | Saved-profile read-only operation | Pass fail-closed: testing disabled. No vendor operation performed. |
| U52 | Users page / role dropdown | Admin controls render; Counselor/Office manager/Viewer options inspected. Final create/reset UI actions unexecuted. |
| U53 | Facility and counselor assignments | Pass. Idempotent facility assignment and MRN counselor assignment report success. |
| U54 | Actual office_manager permissions | Pass. Admin navigation absent; Users/Settings API 403; permitted facilities/roster/plan requests 200. |
| U55 | Counselor permissions | Pass. Assigned patient visible, corrections available, admin navigation absent; Users API 403. |
| U56 | Unauthenticated roster request | Pass. 401; no unauthenticated patient roster. |
| U57 | Forensic logs refresh | Pass. Redacted action metadata, not narrative comments/source content in log details. |
| U58 | Audit hash verification | Pass at latest verification: valid=true, 82/82 events, all_events, redacted_minimum_necessary. Later comparison logins add events beyond that checkpoint. |
| U59 | Encrypted source boundary spot-check | Generated .izcna1 filename, 1299 stored bytes; source narrative sentinel not plaintext. This is a bounded spot-check, not a cryptographic audit. |
| U60 | Help and version footer | Pass readable/navigation guidance; name/all-plan scope wording caveats F04/F05. Correct beta version/footer. |
| U61 | Chrome comparison | Installed Chrome login; all 11 admin navigation pages reached; settled roster/settings rechecked; selected original plan, 42 controls, evidence download; counselor correction queue loads; zero pageerrors observed. Not a duplicate full Windows click-by-click run. |
| U62 | Closeout | Signed out, isolated server stopped; user browser windows and synthetic artifacts preserved. |

## Automated tests and build

| Run | Result |
|---|---|
| Frontend npm test -- --run | PASS: 11 files, 43 tests, 34.97 seconds. |
| Frontend npm run build | PASS: Vite 8.1.1, 62 modules, 993ms build. JS 250.02kB / 71.73kB gzip; CSS 17.30kB / 4.06kB gzip. No source edit. |
| First full backend pytest | FAIL: 57 failed, 199 passed, 1 warning, 283.80 seconds. |
| Repeated full backend pytest with durable results | FAIL: same 57 failed, 199 passed, 1 warning, 337.35 seconds. JUnit: 256 tests, 57 failures, 0 errors. |
| Independent roster-export representative | PASS: test_patient_roster_is_scoped_and_uses_empty_name_when_no_patient_snapshot_exists, 5.80s. |
| Independent sync-contract representative | PASS: test_sync_requires_client_id_before_mapping_or_job_creation, 5.85s. |
| Independent migrated-HTTP representative | PASS: test_startup_migration_serves_multi_version_plan_and_review_records, 5.11s. |

Warning: Starlette TestClient/httpx integration deprecation. Existing full-suite failures were not fixed.

Failure groups from the durable rerun:

| Backend module | Failed |
|---|---:|
| test_v2_alleva_contract_gate | 4 |
| test_v2_alleva_mrn_sync_regression | 2 |
| test_v2_alleva_sync | 16 |
| test_v2_audit_transactionality | 2 |
| test_v2_auth_rbac | 1 |
| test_v2_distinct_alleva_jobs | 4 |
| test_v2_evaluation_persistence | 4 |
| test_v2_immutable_store_surface | 1 |
| test_v2_legacy_api_settings_migration | 18 |
| test_v2_local_recovery | 1 |
| test_v2_manual_binder | 1 |
| test_v2_migrated_http_contract | 2 |
| test_v2_roster_export | 1 |
| **Total** | **57** |

Observed error families include trusted-production-origin rejection of synthetic/mock URLs, 409 versus expected 202, missing SQLite tables/databases, an already-existing app_settings table, empty-list IndexError, and a TypeError during exception handling. The first run also exposed unsafe-production configuration checks. No definitive common root cause is asserted.

Exact test names and failure traces: [JUnit result](C:/Users/r3developer/AppData/Local/Temp/IZ-CNA-Edge-Smoke-20260903/evidence/backend-full-results.xml), [console log](C:/Users/r3developer/AppData/Local/Temp/IZ-CNA-Edge-Smoke-20260903/evidence/backend-full-console.txt).

## Backend/API coverage

Successful authenticated reads included health/readiness/version, current user, navigation, dashboard, patient roster, treatment-plan list/roster, selected patient/plan, corrections, settings, API configured-state, facilities/users, workflow definitions, audit logs/verification, harness jobs and CSV exports.

Selected plan and checklist export URLs use the MRN, not the database row ID. An early probe using numeric row ID 1 produced 404; correcting the test to TEST-PATIENT-001 produced 200. This was a test-input mistake, not a product failure.

RBAC verified: unauthenticated roster 401; counselor Users 403; office_manager Users and Settings 403; office_manager permitted roster/plan/facility reads 200.

The default vendor base URL was not used for an approved live operation. The positive OpenAPI test used the bundled localhost sample only.

## Explicit coverage limits / safety-blocked actions

These are NOT marked passed:

- No real Alleva roster, production patient import, tenant OAuth success, attachments, pagination, rate limits, job cancellation/resumption against a live server, or approved mapping validation. Credentials/approval/configuration are absent and gates remain off.
- Final Windows UI account creation, password-reset/change submission, source-file deletion, and browser credential storage were not executed. Computer-use confirmation/handoff requirements apply. Local API synthetic-account setup is not claimed as proof of those final UI buttons.
- Runtime was launched directly in a temporary data directory; the purchased-laptop installer, packaging, Windows launcher scripts, Windows default-browser setting and administrator-free installation were not retested.
- Positive upload coverage: labeled text and normalized aggregate JSON. Other declared formats, opaque/image/OCR handling, large binders and conflicting MRN override cases were not manually exercised; backend-suite coverage is not substituted for a green run.
- All active V2 navigation surfaces were visited. Dormant legacy/optional-LLM screens not exposed by this runtime were not manually audited.
- No complete keyboard-only/screen-reader/accessibility, load/performance/Lighthouse, CJK or all-page mobile certification. Desktop manual interaction used approximately 1294px window width; saved main captures use 1440px. Supplemental plan-detail checks covered 375/768/1280.
- Passing review actions establish mechanics using synthetic data, not correctness of clinical decisions, deadline policy or all future combinations.

## Independent visual review and evidence hygiene

Two independent read-only review passes inspected all 13 original page captures plus the settled replacement. Both returned REVISE / rejected clean signoff. They confirmed genuine API-backed components, readable navigation, preserved sync gates, and the signature/empty-state/scope issues.

- [Functional integrity review](<C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/.omo/evidence/edge-smoke-functional-integrity-20260903-gate-review.md>)
- [Visual review](<C:/Users/r3developer/OneDrive - R3 Recovery Services Inc/Development/IZ_clinical-notes-analyzer/.omo/evidence/edge-office-manager-visual-b-gate-review.md>)

Those reviews preceded the final multi-plan reproduction, actual office_manager account, second patient, all-42-selector check and completed backend rerun. Their “not yet verified” notes for those items are superseded by this report. No reviewer PASS is claimed.

Capture 05-treatment-plan-detail.png was loading-only and is INVALID for detail judgment. It is preserved but superseded by 05-treatment-plan-detail-settled.png. Main agent and both reviewers inspected the replacement. There was no supplied pixel reference, so no invented similarity score.

Evidence inventory in [local evidence folder](C:/Users/r3developer/AppData/Local/Temp/IZ-CNA-Edge-Smoke-20260903/evidence):

- 01 login; 02 dashboard; 03 patient roster; 04 patient record.
- 05 original loading capture (superseded), plus 05-treatment-plan-detail-settled.png.
- 06 treatment-plans roster; 07 manual upload; 08 API harness; 09 users; 10 logs; 11 settings; 12 help; 13 counselor corrections.
- 14 original-plan wrong-return state; 15 evidence search failure.
- 16 plan detail at 375, 768, 1280 widths.
- 17 actual office-manager two-patient roster; 18 Chrome selected-plan baseline.
- Backend console and JUnit results.

Downloads preserved in C:/Users/r3developer/Downloads: redacted-checklist-evidence.csv (6454 bytes), manual-treatment-plan-source-adf9da58d14c.txt (907 bytes), treatment-plans (1).csv (254 bytes). An older treatment-plans.csv was pre-existing and not changed. Downloaded source/evidence contains synthetic material only.

## Tool/environment incidents, not product defects

- Initial independent reviewer launches failed with remote Codex HTTP 404. Two fresh independent reviewers subsequently ran successfully.
- Some Windows accessibility updates lagged the visible DOM by one capture. Window activation and fresh observations were used.
- A sleeping/occluded Edge capture initially showed the foreground Codex image despite Edge accessibility content; it was not used as app visual evidence.
- File-dialog coordinate/accessibility targeting failed; waiting for File name focus and using keyboard input recovered.
- An input set-value cache error, offscreen click rejection and malformed scroll argument were recovered with supported click/type/scroll operations.
- Playwright import in the persistent REPL failed under its module loader; using the existing local Node runtime and installed browser channels recovered.
- Original detail capture was taken while loading; explicit settled-content waiting repaired it. Chrome's first broad capture also caught transient loading on four routes; each was rechecked settled.
- Long Git Bash MCP calls timed out at the tool's 300-second boundary. The backend subprocess nevertheless completed in 337.35 seconds and wrote valid final JUnit/console artifacts; no test process remained. A queued read also timed out; local Windows-native checks supplied required evidence.
- A final audit probe used POST and received 405; the correct GET verified 82 events. This was a probe-method mistake.
- No tool incident was counted as a product test pass or product defect.

## Change and access accounting

Local device: Windows Edge mouse/keyboard/file-dialog actions; installed Edge/Chrome browser automation; localhost API calls; synthetic SQLite read-only identity check; test/build execution; screenshots/downloads and Markdown report artifacts. Local runtime data changed only inside the isolated smoke directory (plus the listed synthetic Downloads).

Remote/OpenAI: model reasoning, image interpretation, tool orchestration, and independent reviewer service calls. No external clinical/vendor service was enabled or intentionally used. No report/issue/PR/email was sent externally. Evidence content supplied to the model was synthetic.

Only reporting artifacts were added to the workspace; application source and tests remain unchanged. Independent reports are under ignored .omo/evidence; this report is the user-requested durable log. No commit or destructive cleanup was performed.

Resource accounting is approximate, not billing telemetry: several hundred message/tool events (roughly 300–600 across the continued run and reviewers); roughly 250k–450k tokens of conversation/tool content, with image token accounting and exact model-memory usage unavailable. This is a low-confidence volume estimate, not a measured billable-token total.

Measured local snapshot before shutdown: backend working set 40.6MiB; all Edge processes combined 368.5MiB (not exclusively this tab); isolated runtime artifacts 6.4MiB across 31 files at that checkpoint. Earlier idle Edge tab UI reported 29.3MB. These measurements are not peak RAM and do not estimate model memory.

## Recommended next work, not performed

Fix and regression-test F01 first with two distinct plans and explicit plan/version-bound actions. Restore deterministic full-suite isolation/configuration so the complete backend run is green. Then align evidence search and roster/export scope, clarify manual field support and missing data, and repair the smaller display/input issues. Do not enable live Alleva import as a workaround for these local defects.
