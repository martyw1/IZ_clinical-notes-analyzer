# Windows CMD maintenance validation — 2026-09-15

## Candidate identity

This validation note records the immutable beta.4 candidate, not a new build:

- Version: `2.0.0-beta.4`
- Build: `2026.09.14.1`
- Installer revision: `1`
- Source revision: `8fdc8e636e3e9a7123c96a6455f3a1753ea440c5`
- ZIP: [`IZ-Clinical-Notes-Analyzer-v2.0.0-beta.4-build-2026.09.14.1-installer-r1.zip`](../../dist/windows-release/IZ-Clinical-Notes-Analyzer-v2.0.0-beta.4-build-2026.09.14.1-installer-r1.zip)
- ZIP SHA-256: `8072532e8952ad86c033c64050684fb24bf8d0eec0a98dfda1855636a6114eee`
- Receipt: [`...build-receipt.json`](../../dist/windows-release/IZ-Clinical-Notes-Analyzer-v2.0.0-beta.4-build-2026.09.14.1-installer-r1.build-receipt.json)
- Independent verification: `.omo/evidence/windows-cmd-maintenance/resume/final-build-verification.json`

The receipt and independent verification bind the package to the source revision above. The ZIP hash was independently recomputed from the package on disk and matches the receipt.

## Build evidence

The full build completed with the backend suite at **595 passed, 1 warning**, frontend tests at **182 tests across 28 files**, Vite transforming **78 modules**, PyInstaller executable completion, and all **seven named build gates passed**: backend tests, frontend tests, frontend build, repository safety, directory safety, ZIP safety, and frozen-bundle inspection. The build receipt is `dist/windows-release/IZ-Clinical-Notes-Analyzer-v2.0.0-beta.4-build-2026.09.14.1-installer-r1.build-receipt.json`; the independent evidence is `.omo/evidence/windows-cmd-maintenance/resume/final-build-verification.json`.

Two subsequent corrections were harness-only maintenance changes. They were excluded from the ZIP and did not change the packaged runtime artifacts or the immutable source revision recorded above.

## Qualification status

P02 final live lifecycle checks passed for immutable package/ZIP binding, beta.3 HTTP seed, smart upgrade, candidate API upload/readback, normal uninstall retention, reinstall, password rotation, exact-phrase purge, and owned-process/listener/component cleanup. The run still exited `1` (`PLAYWRIGHT_ASSERTION_FAILED`): Edge browser automation failed to launch because DevTools required a non-default data directory, leaving one scenario failed and three unrun. The P02 artifacts are `.omo/evidence/windows-cmd-maintenance/cmd-8fdc8e636e3f/maintenance-run-receipt.json` and `.omo/evidence/windows-cmd-maintenance/cmd-8fdc8e636e3f/case-artifacts/p02/browser/maintenance-browser.json`. This record does not claim full P02 success or final UI qualification.

The following remain unavailable and prevent a client-qualified claim: full Windows Home/default-profile/standard-user qualification, cross-user recovery `R07`, and VM power-loss recovery `R09`. No real client records were accessed or authorized; qualification data remains synthetic-only.

The maintenance contract remains unchanged: beta.3 smart upgrade proceeds without complete uninstall; normal uninstall preserves current-user data; complete purge is separate and requires the exact phrase `REMOVE IZ DATA`. The LOC-change timing rule remains configurable and visibly unvalidated. Live Alleva treatment-plan sync/import remains gated pending the existing authorization, endpoint mapping, compliance, and PHI approvals.

## Release boundary

The package and build evidence are available for the parent release decision. Do not describe this candidate as client-qualified or distribute it as a final client release until P02 and the blocked platform qualification records are complete.
