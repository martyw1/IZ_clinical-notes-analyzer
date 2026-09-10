# Beta.4 password management validation — 2026-09-10

Release: 2.0.0-beta.4 / build 2026.09.10.1 / beta-local-desktop-v2.

## Scope and preservation

Implemented first-use desktop administrator setup, personal password changes, current-password-verified recovery-code creation/rotation, single-use sign-in recovery, and masked staff reset forms. Password recovery hashes are stored locally; recovery consumes the code, invalidates sessions, and does not reactivate disabled accounts. Password rules retain the existing minimum 12 characters with letters and numbers and enforce the hashing length boundary. The shared starter password cannot be selected as a permanent password.

Existing clinical logic, rules, uploads, API integration gates and timeliness behavior were not changed. Existing user documentation/Help edits were preserved. No personal runtime or patient data was used in validation. Existing beta.3 archives remain historical; the new beta.4 installer upgrades those installations while preserving their data and chosen passwords.

## Validation receipts

- Frontend: 178 tests across 27 files passed; production browser build passed; TypeScript noEmit passed.
- Focused backend: 18 bootstrap/configuration checks passed; 24 authentication/recovery checks plus 3 supplemental upgrade/reset/throttle checks passed.
- Full backend suite: 506 tests passed in one complete run (15 minutes); one existing Starlette/httpx deprecation warning.
- Clinical browser smoke: all 31 scenarios were exercised. First run passed 30; the session-reset test expected navigation before the newly required recovery setup. Updated the test to exercise that setup, then all 4 session cases passed in the checkout harness. No clinical app change was needed.
- Packaged session cases: all 4 passed; the older general harness hit a teardown error after tests. The independent prepared password runner subsequently verified process-tree shutdown and closed listeners. The affected synthetic runtimes were identified by their exact test-only local data directories and cleaned up; personal processes were not targeted.
- Password browser smoke: source and packaged beta.4 exercised initial login/forced change, recovery save acknowledgment, Account changes, staff reset, forgotten password, old-session invalidation, single-use rejection, and replacement code generation. All assertions passed. Zero unhandled browser errors. Eight password-related states were captured at 375, 768 and 1280 pixels (24 masked captures per runtime); no horizontal overflow.
- Upgrade: original beta.3 executable initialized an isolated account with a chosen password; version-verified beta.4 executable used that same data. Chosen password preserved, no forced reset of it, starter rejected, and recovery setup available. Both listeners closed after owned process-tree shutdown.
- Packaging: self-contained Windows executable built; required-file, release folder and ZIP safety scans passed. Builder used SkipTests/SkipFrontendBuild because those checks were run separately; this avoided repeating the complete suites.
- Final UI correction: rendered account status labels in plain sentence case; 5 focused UI tests, TypeScript and refreshed browser build passed. Final 24-screen capture set is in .omo/evidence/beta4-password-final-browser. Both independent visual reviews passed with no remaining blockers. Final rebuilt executable password smoke also passed with 24 fresh captures, zero browser errors, closed listener and stopped process tree (.omo/evidence/beta4-password-final-prepared).
- Basedpyright LSP unavailable (previously declined installation). TypeScript and runtime test checks were used; no claim of Python LSP validation.

Evidence lives locally under .omo/evidence/beta4-passwords, beta4-office-manager, beta4-office-manager-session-checkout, beta4-password-browser, beta4-password-prepared-browser and beta4-password-upgrade. These are synthetic validation artifacts, excluded from distribution.

## Stations and remaining clinical blocker

S0 inspection/preservation complete. S1 password implementation and documentation complete; no source deletions. Packaging excludes generated output, unrelated black-hole-lab and historical scripts/admin_recovery, without deleting those originals. S2 validation and S3 release packaging complete. All requested password behaviors are delivered; no remaining password-management blocker. Final release directory and ZIP were scanned after synchronizing the completed validation documentation.

The LOC-change treatment-plan update window remains configurable and unvalidated pending R3/Marleigh confirmation. Live Alleva sync approval requirements remain unchanged. See ../open-blockers.md.

## Execution and usage accounting

File edits, compilation, browser operation, test databases and release packaging ran locally on this Windows device. OpenAI models performed reasoning and generated edits using local tool results. Remote package-registry access was used by build dependency checks and an isolated test process-inspection helper; no clinical/vendor service calls were used for these tests.

Usage is not exactly metered here. Rough order-of-magnitude estimate across this task and its workers: 150–300 tool/message exchanges and 100,000–200,000 tokens including context and review. Local full-backend-test process peak working set observed at 165.8 MiB (launcher 4.2 MiB); this is not combined browser/build memory. OpenAI model memory and total device peak are unavailable.
