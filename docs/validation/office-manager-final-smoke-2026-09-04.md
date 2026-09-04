# Office-manager beta3: final smoke evidence

Date: 2026-09-04. Application commit: `f65b3b785447df2a15dea511dd19d214f4b0f550`.
Release: `2.0.0-beta.3`, build `2026.09.03.1`, channel `beta-local-desktop-v2`.

This report separates application tests, actual runner exits, native Computer Use and independently verified cleanup. Only synthetic data and fresh isolated local runtime directories were used. No live Alleva patient import or clinical-production approval is claimed.

## Implemented components

| Area | Components and verified contract |
| --- | --- |
| Exact selection and authorization | Backend plan read/export routes, immutable stores, source-membership migrations and authorization; frontend roster/detail clients and pages. Identical-looking MRNs/plan IDs remain source-scoped; actions, corrections, history, downloads and export bind to the selected saved version |
| Manual metadata | Manual parser, binder/upload routes, encrypted patient snapshots and source memberships. Explicit optional name/reference/service dates; honest omissions/conflicts; no name-based identity |
| Evidence presentation | Detail viewer, clinical sections, review panels, evidence panel, formatting and CSS. Readable hierarchy, separated signatures, UTC dates, safe search and matched selection |
| Session and upload state | Request/session boundary, AppV2, upload page/file-state helper. Current-session expiry clears protected state; stale responses cannot overwrite new selection; empty submission and success/remove/clear state are covered |
| Dashboard and coverage | Dashboard data, source-support/evaluation projection and UI. Patient/plan/criterion/correction units remain distinct; source presence is not compliance |
| Pull feedback | PatientRosterPage and TreatmentPlansRosterPage. Completion status survives roster refresh; two controlled regression cases fail before the fix and pass after |
| Windows release | Version consumers and release-safety/archive/build scripts. Long paths, sensitive-document exclusion, required assets and frozen version metadata |

## Build and regression evidence

- Backend: two complete **492-test passes** during final integration. All **240 backend input hashes** remained unchanged after the last frontend-only fix. Case identities and JUnit evidence are preserved locally.
- Frontend: **173/173 tests**, 26 files, actual exit `0`; TypeScript `--noEmit` and production build exit `0`. No failing assertion was removed or weakened.
- A normal no-skip Windows build passed backend 492/frontend 171 and packaging gates before the final two-test frontend regression. The final repack explicitly used **`-SkipTests`**, reusing the unchanged backend proof and current 173-test frontend proof. It is not another no-skip build.
- Final repack completed 17:14:24 UTC. PyInstaller/build and embedded-archive inspection exited `0`. Required/forbidden-file scans passed for the 497-file folder and 507-entry ZIP. External and embedded frontend asset hashes match.
- EXE SHA-256: `470d4910d7db1401714a48258692370c686418aefc96a56aed06ace17cb5bb01`.
- ZIP SHA-256: `9c5fd47203242e1a21df612f719f1c14fa4240c86ba869f924ec4690834fc89c`.
- Packaged `/api/version` and native browser footer agree on beta3/build/channel. The pre-documentation bookend checked 1,138 source/helper/package entries with zero mismatches. Later documentation-only edits accompany the binary; they are not a rebuild.

## Installed-browser smoke

- Edge `152.0.4191.62`: **7/7 original E2E tests passed**, actual test-process exit `0`, zero test errors.
- Chrome `152.0.7977.76`: **7/7 original E2E tests passed**, actual test-process exit `0`, zero test errors.
- In each original seven-case run, two tests use the real local backend and five use controlled mocks. Mocked sync results/cancellation are not live Alleva evidence.
- The fixed matrix covers display, harness, identity, metadata, metrics, roster, selection, session and upload, each happy/adverse case in each installed browser with a fresh runtime. Dedicated metrics combined-case runs test its shared-seed contract.
- **Bounded matrix result:** 34/38 cells executed. All 70 executed test bodies passed. Twenty-three cells had clean Playwright/outer teardown results; 11 retained runner/reporter warnings after their test bodies passed. Two warning cells had final Playwright report status `failed`/error count 1 after the sole test body passed; no application assertion failed. Per the user's time/token stop, selection adverse and dedicated metrics-combined were not run in Edge or Chrome (four cells, six tests). Preflight-only attempts for the selection-adverse pair failed before runtime because the reset orchestration environment could not find Node; they are not test results. No omitted cell is claimed passed. Receipt: `.omo/evidence/t10p/final-smoke-termination-summary.json`.

## Native Computer Use

| Final-executable interaction | Edge | Chrome |
| --- | --- | --- |
| Dashboard/readiness, manager navigation, beta3 footer | Observed | Observed |
| Actual Windows picker, binder import, filename clearing | Passed | Passed |
| Source-scoped roster, three Manual plans, exact imported version 8 | Passed | Passed |
| Clinical hierarchy, timeline, honest missing dates, separate signatures | Passed | Passed |
| Admission selector matches evidence; manager comment persists on exact version | Passed | Passed |
| Empty binder and empty comment validation | Not repeated in final native session | Passed |
| Checklist CSV download | Not reached before bounded close | Passed: 42 data rows, 9,075 bytes |
| Source archive/download | Not reached before bounded close | Passed: 347 bytes, checksum equals uploaded binder |
| Help, post-import dashboard refresh, sign-out | Not all repeated; bounded browser closed | Passed |

Ten Edge and seventeen Chrome native result records, screenshots and passive request observations are retained. Both native sessions recorded zero page errors, console errors and failed requests. Chrome observed import `201`, authorized read/action/export/download `200`, anonymous suggested download names and successful saved downloads. Chrome ended with outer exit `0` and verified runtime/process/data cleanup. Edge exited `1` after its browser closed; its successful application observations are retained, but its failed runner invocation is not relabeled PASS. Eleven remaining synthetic runtime files were removed only after validating exact ownership, process/port absence and the physical path.

Chrome CSV SHA-256: `3e947f955e3fb2e3a5370897ba1faff02aa7182f9bca41f7fc3bb06032d2d855`.
Source SHA-256: `1249efea9b19b7ce6d8df70dfc6f070a0f98159809818f765b84aba01f3d056e`, equal to the selected binder and displayed archive checksum.

## U01-U62 coverage limits

The [original planning matrix](office-manager-production-fixes-2026-09-03.md) remains a planning record, not 124 native PASS cells. Scripted tests and backend checks are not native hand interaction.

| Original scope | Actual evidence boundary |
| --- | --- |
| U01/U02/U04 | Installed-browser launch/login/roles scripted; native manager sessions both browsers; final native sign-out Chrome |
| U03/U05 | Backend bootstrap/password transitions and scripted revocation/stale-401 recovery. Native password reset/account creation not executed without action-time approval. Natural 60-minute idle expiry not waited out |
| U06/U08 | Seeded dashboard/roster and filter no-match; no-match is not an empty-database test |
| U07/U09-U21/U31/U32/U36/U37 | Matrix targets metrics, source-scoped roster/detail/history, clinical display, evidence search and filtered export. All-42 selector sweeps are scripted, not 42 native clicks |
| U22-U30 | Matrix/backend target version-bound actions, required fields, correction lineage and counselor submission. Final native sessions specifically verify comments; Chrome also blank-comment rejection |
| U33-U43 | Matrix targets archive membership, bytes/CSV, metadata, JSON/binder and file state. Native picker/import both browsers; final native download verification Chrome only |
| U44-U52 | Settings/Users display and role navigation scripted; configuration/OpenAPI/OAuth/live-sync safety and workflow boundaries backend/original-suite covered. Every native configuration/credential/account action was not repeated on the final binary |
| U53-U59 | Backend/matrix target assignment, authorization, unauthenticated denial, audit integrity and encrypted storage; not every administrative action was manually repeated |
| U60-U62 | Footer/Help and independent browser evidence retained; runtime termination/cleanup logged separately, including failures |

Earlier-candidate administrative observations are historical and are not relabeled final-binary native passes.

## Failures and small observations

| Observation | Disposition |
| --- | --- |
| Pull completion disappeared during refresh | Fixed in both roster pages; controlled regressions and original suites pass |
| Eleven of 34 executed matrix cells had runner/reporter warnings after all 70 test bodies passed; two final reports had one post-test error each | Retained as warnings/failures, not clean PASS. Independent process identity/port/owner checks precede cleanup. Precise underlying Windows exception not established; not claimed fixed |
| Four matrix cells (six tests) were stopped before execution | User requested immediate bounded completion. Selection adverse and dedicated combined-metrics cases in both browsers remain explicitly untested; no PASS inferred |
| Expected 401 console entry in intentional session-revocation cases | Classified using matching request evidence, not hidden or called an unexpected app error |
| Computer Use capture timeout, first stale picker screenshot, restored narrow Chrome window | Fresh state before next input; selected file confirmed before import; no duplicate upload |
| Narrow roster wraps MRNs/PHP across lines | Reachable but minor readability limitation |
| Managed browser displays downloaded files under UUID names | Bytes and anonymous suggested names verified; unmanaged-browser filename presentation not inferred |
| Earlier disabled-harness diagnostic gave generic 409 feedback | Historical fail-closed observation; not a newly resolved UX claim |
| Development dependency audit warnings | Earlier production-only audit zero; five high development findings retained. No opportunistic dependency upgrade |

Live tenant/mapping/compliance approval, unvalidated LOC-change timing, credential rotation/history remediation, signing and retention/legal hold remain open. Source removal stays disabled. Fresh end-user install/repair/uninstall and another Dell laptop were not tested. **Software test results do not authorize production deployment.**

## Preservation and local evidence

- Pre-change main `438c72644363133192691c0ac801ce61716d5ca8` has a verified DPAPI CurrentUser-encrypted Git bundle, sanitized source ZIP and original report backup. Recovery matched that commit; DPAPI restoration requires the same Windows account. This is a source/history backup, not a patient-runtime backup.
- The original private smoke log remains local and byte-identical: 30,260 bytes, SHA-256 `c1f76a157ec4e2b745dd36750cba8541e09bed9387644f9b1433511fc54483c6`. It is not published. Old beta2 release artifacts remain preserved.
- Ignored evidence: `.omo/evidence/office-manager-production-fixes/task-10-repackage-result-rp-7c0185a4e3dd.json`, `task-10-roster-status-full-green.json`, `task-10-final-native-closeout.md`; `.omo/evidence/t10p/final-matrix-ledger.json` and final bookend/cleanup receipts. Raw artifacts, runtime data, credentials and screenshots stay out of Git.
- Remote operations for closeout are authorized Git fetch/push. Build, tests, browser control, backup and artifact checks run locally. The model performs reasoning, code/document synthesis and evidence interpretation, not clinical validation. Exact whole-task message/token totals and model memory are not exposed; no fabricated usage total is supplied.
