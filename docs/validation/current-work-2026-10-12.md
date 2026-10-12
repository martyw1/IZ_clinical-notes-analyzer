# Single-user maintenance validation — October 12, 2026

Target: **1.0.1 / 2026.10.12.1 / stable-local-desktop / installer revision 1**.

This ledger records current work; dated earlier package acceptance remains historical evidence for its exact artifact. Target workload is the application and OneDrive with normal Windows services. ChatGPT/Codex development overhead is excluded from client capacity claims.

## Stations

1. S0 baseline — completed: source metadata and current documentation inspected; baseline backend 618 passed / 1 failed (old browser-title assertion), frontend 184 passed, TypeScript passed. Existing unrelated `tmp/` preserved. No client data changed.
2. Code and version consistency — completed: response privacy headers, bounded upload/extraction safeguards, consistent patch identity and branding assertion; preserve audit/application diagnostics and clinical gates.
3. Documentation — completed: current offline guide, operator/technical troubleshooting, current-versus-historical inventory and assessment.
4. Verification — completed for the source candidate: targeted and full backend/frontend checks, production frontend build, synthetic desktop browser walkthrough, audit chain and access checks, local documentation link checks.
5. Handoff — completed for source guidance: numbered desktop guide link and final evidence/review. Published installer is subject to existing clean-checkout build contract; no historical package will be overwritten.

## Boundaries

No real patient records, secrets or configuration are used as test fixtures. No Windows security policy, cloud configuration, vendor endpoint or client database is changed. No security scanner is used. Software verification does not certify HIPAA compliance or resolve owner-controlled deployment gates.

## Verified maintenance evidence

- Release identity regression: 2 passed, including R3 browser branding and API/config/package/lock metadata.
- Response privacy + recovery targeted run: 19 passed; final privacy boundary run 6 passed. API no-store covers successful/error responses; static cache behavior and exception propagation remain intact.
- Upload targeted binder integration/bounds run: 9 passed; final four bounds tests passed including a real synthetic PDF. Existing per-file bounded reads were already present; the new bound accounts for remaining aggregate allowance. Text overflow rejects evidence rather than truncating it; single-page parser resource consumption remains a residual limitation.
- Frontend: 184 tests in 28 files passed; TypeScript noEmit passed; production Vite build passed (291.31 kB JS, 21.53 kB CSS before gzip).
- Live isolated desktop: office-manager sign-in, required recovery creation/acknowledgment, dashboard, exact patient/source record, selected saved plan, 42 criteria, Help anchor and sign-out verified. API reported 1.0.1/build2026.10.12.1 and no-store/nosniff. Synthetic audit chain verified 6/6 events with minimum-necessary redaction. This does not certify every possible access event is audited.
- Independent code review: PASS. Independent visual functional/design and focused visual reviews: PASS on fourteen fresh JPEGs, including responsive Help/login at 375/768/1280 and all seven office-manager pages. Screenshot extension/compositor evidence issues were corrected before review.
- Current HTML: 21 references, 9 anchors, zero broken local targets. Original historical HTML: 31 references, zero broken targets; it forwards readers to current guidance. Current entry-document links resolve. Six current screenshots contain synthetic training records only.
- Desktop (6) IZ Clinical Notes Analyzer User Guide shortcut created; COM target and target existence verified. Browser file-protocol policy prevented direct offline HTML rendering; no workaround was attempted. Static document/link validation and current app screenshot review are recorded separately.
- Synthetic QA service stopped; no port 8767 or 8000 listener remained after browser QA. Synthetic evidence/profile preserved outside source; client runtime untouched.

## Validation events and remaining scope

The initial long Git Bash call lost its connection at the tool's 300-second limit while pytest continued. That run was stopped by its verified process IDs and restarted with local stdout/stderr capture; only the completed captured run will be used for final full-suite evidence. A broad PowerShell maintenance run also exposed test-only fixture/module-scope interactions; test-only fixture/module-scope isolation repairs and the combined rerun are completed.

The current uncommitted checkout includes pre-existing unrelated tmp/ evidence. The release builder intentionally requires a clean, reviewed source revision for publication. No new release-ready ZIP or build receipt is claimed, and no historical ZIP was overwritten. This source validation does not replace exact-package/client-account qualification.

Owner gates remain as recorded in docs/open-blockers.md and docs/security/appliance-assessment-2026-10-12.md, including incident disposition, host encryption/lock/clock evidence, approved cloud configuration, device-loss restoration and clinical/live-vendor approvals.
## Completed final reviews and maintenance checks

- Independent documentation review: PASS after source-confirmed stale module, route, roster, recovery and version references were corrected. Current technical maps point to V2 implementation; historical evidence remains separate.
- Incremental code review: PASS for final test-only fixture isolation and removal of stale beta wording from parser size errors.
- Final upload/binder targeted verification after wording updates: 10 passed, 1 existing Starlette TestClient deprecation warning (17.91 seconds).
- Maintenance contracts All: 117 assertions passed, exit 0; backup roundtrip 9 and backup-negative 30 assertions passed. Separate core run: 103 assertions passed. Test fixtures restore caller module imports, isolate component roots and stage source dependencies outside the reparse-backed OneDrive checkout; production path/ownership guards are unchanged.
- Earlier installer checks: version 33 assertions, harness 46 assertions, synthetic installer packaging and release-safety boundaries passed. These are synthetic checks, not acceptance of a published 1.0.1 installer.
- Full backend captured run: **629 passed, 3 existing deprecation warnings, 941.30 seconds (15m41s)**; process completed. No failures. Command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend backend/.venv/Scripts/python.exe -m pytest backend/tests -q -p no:cacheprovider`.
## Final station disposition

S0 baseline, code/version fixes, current documentation, source verification and desktop-guide handoff are complete. No production deployment or operating-system configuration change was performed. Exact-package publication is not qualified: the builder requires a reviewed clean committed source revision, while this checkout contains the current uncommitted work plus unrelated pre-existing tmp/. Client-account and owner-controlled deployment gates remain explicit, not silently accepted.

Final tests comprise 629 backend and 184 frontend cases. TypeScript and production frontend build pass. Targeted safeguards, maintenance/backup assertions and independent code/documentation/visual reviews pass. No client PHI, live vendor import or existing client database was used for verification. Optional LLM behavior and clinical evaluation gates were not enabled or changed. Detailed logging capabilities remain; retention and independent audit protection need R3 policy.

Work accounting: shell/file changes, tests, static documentation checks, shortcut creation and synthetic browser QA ran locally on this device. Public HHS pages were retrieved remotely for regulatory guidance; no remote-support session or vendor/client-data call was used. OpenAI LLM reasoning drafted and reviewed source/documentation and synthetic evidence. Exact service messages/tokens/inference-memory telemetry is unavailable; estimates must not be treated as billing measurements.

Portable ZIP backup follow-up: see [station evidence](portable-zip-backup-2026-10-12.md). This owner-requested unencrypted workflow is separate from release-package and DPAPI backup qualification.
