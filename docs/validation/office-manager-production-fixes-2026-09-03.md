# Office-manager production-fixes validation planning record

Validation record prepared: 2026-09-04

Target release metadata: `2.0.0-beta.3` / build `2026.09.03.1` / release date `2026-09-03` / channel `beta-local-desktop-v2` / stability `beta`.

This is the preserved pre-closeout planning record, not the final result. Its pending cells describe the originally proposed scope. See [Final beta3 smoke results](office-manager-final-smoke-2026-09-04.md) for actual build, backend, browser, native-interaction, failure and coverage evidence. Targeted native interaction plus a scripted matrix is not all 62 scenarios independently performed by hand in both browsers. Neither record is production or clinical-production approval.

## Evidence boundary and preservation

- The original user-requested smoke log remains byte-identical at `docs/validation/smoke-test-2026-09-03-edge-office-manager.md` (SHA-256 `c1f76a157ec4e2b745dd36750cba8541e09bed9387644f9b1433511fc54483c6`, 30,260 bytes). Its beta2 results are historical baseline evidence only.
- The isolated backend version regression is `backend/tests/test_v2_release_version_consistency.py`; root's scoped replay passed both that test and the packaging-contract test (`2 passed`, `0 failed/skipped`, `2.35s`) in `.omo/evidence/office-manager-production-fixes/task-9-root-version-replay.xml`. It exercises `/api/version`, sample OpenAPI metadata, isolated `settings.app_version`, and `settings.build_channel`, then checks the preflight/footer source literals. The packaged runtime is intentionally not inferred from this test.
- The existing packaging-contract assertions remain in `backend/tests/test_v2_production_config.py`; they verify the reviewed builder contract without changing dependencies or test fixtures.
- `VERSION`, `VERSION.json`, `frontend/package.json`, and the root `frontend/package-lock.json` package metadata are the release metadata inputs. The lockfile dependency graph is unchanged.
- The builder now validates and copies `VERSION.json` to the runtime staging root and adds it to the PyInstaller data bundle. Task10 must inspect a freshly built archive and call the packaged `/api/version` endpoint to prove the metadata is retained when frozen.
- No live Alleva credentials, real patient records, clinical exports, runtime databases, uploads, or production local-app-data were used or claimed.

## Current implementation status

| Area | Status | Evidence or remaining gate |
| --- | --- | --- |
| Beta3 version metadata | Implemented and focused-test verified | `VERSION`, `VERSION.json`, frontend package/lock metadata, isolated version test |
| Backend/API/UI version consumers | Implemented; scoped fresh-client HTTP regression passed, stable integrated handoff pending Task7 | `backend/app/core/config.py`, sample OpenAPI route, `/api/version`, `frontend/src/v2/components/AppShell.tsx`, `scripts/preflight-windows.ps1`; root replay: `.omo/evidence/office-manager-production-fixes/task-9-root-version-replay.xml` |
| Frozen package metadata | Implemented in source; packaged proof pending | `scripts/build-windows-installer.ps1`; Task10 isolated builder/archive/API receipt required |
| Source-scoped roster/export and exact plan/version identity | Task7 receipt pending | Do not claim final source-membership or UI coverage until Task7 handoff |
| Dashboard metric evidence | Task8 backend subgate independently verified; browser/build metrics pending | `task-8-metrics-receipt.md` records 28/28 backend tests, five raw-source probes, and byte-identical 63-by-42 clinical replay; do not claim final browser/package coverage |
| Reused encrypted source-document membership | Structural v12 associations are approved; detach/erase/removal policy awaits user choice | Approved migration backfills only valid original `(source_document_id, plan_version_id)` pairs. New or repeated imports attach the exact saved version membership and preserve original IDs/FKs/ciphertext; legacy ambiguity remains missing/unlinked evidence. No detach or erase behavior is claimed until the retention decision is answered and validated |
| LOC-change update window | Blocked/unvalidated | Keep configurable and visibly unresolved; do not hard-code a final rule |
| Live Alleva sync and production credentials | Blocked external gate | Requires approved tenant, endpoint mapping, auth, pagination/rate-limit, attachment, PHI, and compliance validation |
| Credential rotation/history remediation | Blocked external gate | R3 approval and downstream inventory/remediation decision required |
| Code signing and retention/legal hold | Blocked external gate | R3 IT/records decisions required |
| Full Windows package, preflight, Edge, and Chrome smoke | Pending Task10 | Run in isolated child environment with fresh local app data; capture binary artifacts |

## U01-U62 native retest matrix

Each row is a separate beta3 retest requirement for both browsers. `PENDING_TASK10` means no current beta3 pass is claimed; the prior report is linked only as a historical baseline. Each completed row must carry a screenshot, console/network or API artifact, and a durable result entry where the scenario produces one.

| ID | Scenario | Edge beta3 | Chrome beta3 | Required observable/artifact |
| --- | --- | --- | --- | --- |
| U01 | Launch and local page | PENDING_TASK10 | PENDING_TASK10 | Browser launch, localhost page, settled UI capture |
| U02 | Empty and valid login | PENDING_TASK10 | PENDING_TASK10 | Validation message plus successful admin/manager/counselor sign-in capture |
| U03 | Bootstrap reset boundary | PENDING_TASK10 | PENDING_TASK10 | Forced-reset screen and action-time confirmation evidence |
| U04 | Sign out and sign back in | PENDING_TASK10 | PENDING_TASK10 | Session transition and browser credential-save handling |
| U05 | Idle-session recovery | PENDING_TASK10 | PENDING_TASK10 | Expired-session response and successful recovery evidence |
| U06 | Dashboard empty state and refresh | PENDING_TASK10 | PENDING_TASK10 | Empty state, refreshed timestamp, readiness/LOC warning capture |
| U07 | Dashboard after imports/review | PENDING_TASK10 | PENDING_TASK10 | Counts after synthetic import/review and metric source evidence |
| U08 | Patient Roster empty state | PENDING_TASK10 | PENDING_TASK10 | Empty state and gated live-pull prerequisites |
| U09 | Patient MRN lookup | PENDING_TASK10 | PENDING_TASK10 | Match, no-match, and cleared-filter captures |
| U10 | Patient names and source identity | PENDING_TASK10 | PENDING_TASK10 | Source identity/name behavior with no PHI; exact source evidence |
| U11 | Open patient record | PENDING_TASK10 | PENDING_TASK10 | MRN/source/lifecycle/LOC/linked-plan detail capture |
| U12 | Unselected record/detail pages | PENDING_TASK10 | PENDING_TASK10 | Safe instruction/navigation state without fabricated data |
| U13 | Patient source-field explorer | PENDING_TASK10 | PENDING_TASK10 | Empty/populated snapshot search state and bounded fields |
| U14 | Single-plan dropdown | PENDING_TASK10 | PENDING_TASK10 | Selected exact plan ID/version and matching detail |
| U15 | Multi-plan dropdown | PENDING_TASK10 | PENDING_TASK10 | Distinct plans and content remain selectable independently |
| U16 | Multiple-patient navigation | PENDING_TASK10 | PENDING_TASK10 | Office-manager finds both synthetic MRNs and exact plans |
| U17 | Clinical content | PENDING_TASK10 | PENDING_TASK10 | Synthetic problem/goal/objective/intervention rendered readably |
| U18 | Timeline and status | PENDING_TASK10 | PENDING_TASK10 | Deterministic status, evidence dates, and unresolved LOC warning |
| U19 | All 42 checklist selectors | PENDING_TASK10 | PENDING_TASK10 | 42/42 controls exercised, matching headings, no page errors |
| U20 | Checklist title search | PENDING_TASK10 | PENDING_TASK10 | Late checklist title found after scrolling |
| U21 | Evidence-value search | PENDING_TASK10 | PENDING_TASK10 | Search match/no-match behavior and evidence capture |
| U22 | Empty comment/override validation | PENDING_TASK10 | PENDING_TASK10 | Required comment/reason feedback |
| U23 | Approve criterion | PENDING_TASK10 | PENDING_TASK10 | Saved action/history with exact plan/version binding |
| U24 | Save manager comment | PENDING_TASK10 | PENDING_TASK10 | Manager attribution and exact plan/version history |
| U25 | Return without counselor | PENDING_TASK10 | PENDING_TASK10 | One-counselor safety validation and no mutation on failure |
| U26 | Return with counselor | PENDING_TASK10 | PENDING_TASK10 | Returned work item and counselor queue entry |
| U27 | Return older plan with two plans | PENDING_TASK10 | PENDING_TASK10 | Older plan action targets the selected plan/version only |
| U28 | Override with reason | PENDING_TASK10 | PENDING_TASK10 | Required reason and persisted manager history |
| U29 | Counselor correction empty resolution | PENDING_TASK10 | PENDING_TASK10 | Blank-resolution rejection |
| U30 | Counselor submits resolution | PENDING_TASK10 | PENDING_TASK10 | Queue/dashboard transition and manager history |
| U31 | Review history | PENDING_TASK10 | PENDING_TASK10 | History type, role, timestamp, explanation, and identity separation |
| U32 | Raw Field Explorer | PENDING_TASK10 | PENDING_TASK10 | Bounded field count, filtering, and redacted preview |
| U33 | Source archive | PENDING_TASK10 | PENDING_TASK10 | Anonymous source ID/type/size/checksum and download control |
| U34 | Source download | PENDING_TASK10 | PENDING_TASK10 | Generated anonymous filename and synthetic bytes |
| U35 | Checklist evidence CSV | PENDING_TASK10 | PENDING_TASK10 | Minimum-necessary 42-criterion CSV content |
| U36 | Treatment Plans Roster refresh/search shell | PENDING_TASK10 | PENDING_TASK10 | Controls plus source-scoped populated rows or explicit gate |
| U37 | Treatment-plan CSV export | PENDING_TASK10 | PENDING_TASK10 | Source-scoped rows, formula safety, and exact identity |
| U38 | Binder native file picker | PENDING_TASK10 | PENDING_TASK10 | Native picker selection and settled dialog evidence |
| U39 | Binder MRN override/confirmation | PENDING_TASK10 | PENDING_TASK10 | Matching and mismatch-confirmation outcomes |
| U40 | Binder import | PENDING_TASK10 | PENDING_TASK10 | Parsed file, source archive, MRN, and review-roster link |
| U41 | No-file binder/aggregate submissions | PENDING_TASK10 | PENDING_TASK10 | Actionable choose-file errors for both forms |
| U42 | Binder remove/clear selection | PENDING_TASK10 | PENDING_TASK10 | Native filename removal and clear/reselection behavior |
| U43 | Normalized JSON import | PENDING_TASK10 | PENDING_TASK10 | Second plan/patient import, exact identity, no filename leakage |
| U44 | Settings display/save | PENDING_TASK10 | PENDING_TASK10 | Unchanged save and visibly unresolved LOC setting |
| U45 | API auth-style dropdown | PENDING_TASK10 | PENDING_TASK10 | Body/basic selection persistence without credentials |
| U46 | Save localhost sample OpenAPI | PENDING_TASK10 | PENDING_TASK10 | Localhost-only URL saved and displayed |
| U47 | Pull/load OpenAPI | PENDING_TASK10 | PENDING_TASK10 | Sample definition title/version/operation loaded |
| U48 | OAuth test without credentials | PENDING_TASK10 | PENDING_TASK10 | Fail-closed missing-credential message and no token |
| U49 | Harness diagnostic pull disabled configuration | PENDING_TASK10 | PENDING_TASK10 | No-job fail-closed response |
| U50 | Operational live pull/sync | PENDING_TASK10 | PENDING_TASK10 | Disabled gate and exact prerequisites; no live call |
| U51 | Saved-profile read-only operation | PENDING_TASK10 | PENDING_TASK10 | Disabled operation test and no vendor request |
| U52 | Users page/role dropdown | PENDING_TASK10 | PENDING_TASK10 | Role controls plus action-time create/reset confirmations |
| U53 | Facility and counselor assignments | PENDING_TASK10 | PENDING_TASK10 | Idempotent assignment responses and audit evidence |
| U54 | Office-manager permissions | PENDING_TASK10 | PENDING_TASK10 | Admin navigation absent, permitted routes allowed, forbidden routes 403 |
| U55 | Counselor permissions | PENDING_TASK10 | PENDING_TASK10 | Assigned work, correction access, and forbidden admin routes |
| U56 | Unauthenticated roster request | PENDING_TASK10 | PENDING_TASK10 | 401 and no patient data |
| U57 | Forensic logs refresh | PENDING_TASK10 | PENDING_TASK10 | Redacted metadata only, no source narrative or credentials |
| U58 | Audit hash verification | PENDING_TASK10 | PENDING_TASK10 | Valid hash chain and event-count artifact |
| U59 | Encrypted source boundary spot-check | PENDING_TASK10 | PENDING_TASK10 | Ciphertext-at-rest sentinel and no plaintext source narrative |
| U60 | Help and version footer | PENDING_TASK10 | PENDING_TASK10 | Help navigation plus exact beta3/build/channel footer |
| U61 | Cross-browser comparison | PENDING_TASK10 | PENDING_TASK10 | Independent settled Edge and Chrome result sets, not one automation shortcut |
| U62 | Closeout | PENDING_TASK10 | PENDING_TASK10 | Signed out, isolated server stopped, evidence preserved |

## Required Task10 completion artifacts

Task10 may replace each `PENDING_TASK10` cell only after capturing all of the following:

- A fresh isolated Windows build and release-folder/zip inventory, including external `app/VERSION.json`, internal PyInstaller `_MEIPASS/VERSION.json`, and the existing forbidden-file scan.
- Packaged runtime `/api/version` JSON showing version `2.0.0-beta.3`, build `2026.09.03.1`, channel `beta-local-desktop-v2`, release date `2026-09-03`, beta stability, and prerelease `true`.
- A settled browser footer capture showing `Version 2.0 Beta | 2.0.0-beta.3 | build 2026.09.03.1 | beta-local-desktop-v2`.
- Separate Edge and Chrome evidence for every U01-U62 row, including native dialogs and role transitions, plus console/page-error results.
- Task7 source-membership and Task8 metrics receipts reconciled against the final behavior; if still running, leave those rows pending.
- The original report hash rechecked and no historical beta2 file or illustrated-guide directory renamed or rewritten.

Until these artifacts exist, this document must retain its pending/blocked classifications and must not be used as a production-readiness sign-off.
