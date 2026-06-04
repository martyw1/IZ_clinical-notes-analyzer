# Open Blockers

Date: 2026-06-04

## LOC-Change Treatment-Plan Update Window

Status: unvalidated.

The required treatment-plan update window after a level-of-care change is not confirmed by R3/Marleigh. The v0.5.0 implementation must keep this value configurable and must visibly mark it as unvalidated in admin/settings UI and operator documentation.

Current implementation state: the setting exists in the database and admin Settings UI, and the timeliness dashboard/detail output marks LOC-change cases as `Needs Review` while this blocker remains unresolved.

Until R3 confirms the rule, do not hard-code a final number of days and do not silently treat a LOC-change case as compliant. If source evidence is incomplete or conflicting, return `Needs Review` or `Missing Data` according to the deterministic rules.

Required resolution evidence:

- R3/Marleigh confirms the exact update window after LOC change.
- R3 confirms whether the window is calendar days or business days.
- R3 confirms whether the trigger date is the LOC-change date, signed review date, admission date, or another source evidence date.
- R3 confirms the user-visible label and default status for overdue LOC-change updates.

## Windows Packaging and Dell Validation

Status: not validated on target Windows hardware.

The recommended end-user path is a packaged signed `.exe` or `.msi` with bundled runtime, built frontend assets, shortcuts, repair/modify support, uninstall support, and local app-data preservation. The current repository still provides source-checkout launch and test scripts, not a finished installer.

Current implementation state: `docs/windows-dell-test-plan.md` gives exact Dell PowerShell validation commands and separates Option A packaged release from Option B source-checkout validation. The macOS validation environment cannot prove Windows 10/11 Home behavior, SmartScreen/code-signing behavior, installer repair/uninstall behavior, or target Dell performance.

Required resolution evidence:

- Source checkout validation passes on the purchased Dell Windows 10/11 Home laptop.
- `/api/version` and the UI footer show `0.5.0` on that machine.
- `scripts\test-local-app-stack.ps1` and `scripts\test-api-configuration-local.ps1` pass with synthetic data only.
- A real installer or MSI exists, bundles runtime/assets, supports repair/modify/uninstall, and preserves `%LOCALAPPDATA%\IZ Clinical Notes Analyzer` by default.

## Frontend Vitest and Direct TypeScript Check

Status: blocked in this OneDrive checkout.

Frontend production builds pass, but local Vitest and direct `tsc --noEmit` checks hang before useful diagnostics in this macOS OneDrive checkout. Treat this as a local toolchain/workspace blocker, not a passing frontend test result.

Required resolution evidence:

- `npm run test -- --run` completes under CI or a repaired local Node/Vitest setup.
- A direct TypeScript check completes or is replaced by the project-supported CI frontend job.
