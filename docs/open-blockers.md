# Open Blockers

Date: 2026-06-09

## LOC-Change Treatment-Plan Update Window

Status: unvalidated.

The required treatment-plan update window after a level-of-care change is not confirmed by R3/Marleigh. The Version 1 implementation must keep this value configurable and must visibly mark it as unvalidated in admin/settings UI, the Treatment Plan Checklist, the timeliness dashboard, and operator documentation.

Current implementation state: the setting exists in the database and admin Settings UI, and the timeliness dashboard/detail output marks LOC-change cases as `Needs Review` while this blocker remains unresolved.

Until R3 confirms the rule, do not hard-code a final number of days and do not silently treat a LOC-change case as compliant. If source evidence is incomplete or conflicting, return `Needs Review` or `Missing Data` according to the deterministic rules.

Required resolution evidence:

- R3/Marleigh confirms the exact update window after LOC change.
- R3 confirms whether the window is calendar days or business days.
- R3 confirms whether the trigger date is the LOC-change date, signed review date, admission date, or another source evidence date.
- R3 confirms the user-visible label and default status for overdue LOC-change updates.

## Windows Packaging and Validation

Status: in progress for Version 1.

The recommended long-term end-user path is a packaged signed `.exe` or `.msi` with bundled runtime, built frontend assets, shortcuts, repair/modify support, uninstall support, and local app-data preservation.

Current implementation state: Version 1 adds Windows preflight, setup/start wrappers, a release-folder builder, double-click install/launch/uninstall commands, built frontend assets, Start Menu shortcut creation, and AppData preflight reports. The package is not code-signed and is not a full MSI/MSIX with repair/modify support.

Required resolution evidence:

- Source checkout validation passes on the target Windows 10/11 laptop.
- `/api/version` and the UI footer show `1.0.0` on that machine.
- `scripts\test-local-app-stack.ps1` and `scripts\test-api-configuration-local.ps1` pass with synthetic data only.
- A signed installer or MSI/MSIX exists, bundles runtime/assets, supports repair/modify/uninstall, and preserves `%LOCALAPPDATA%\IZ Clinical Notes Analyzer` by default.

## Frontend Vitest and Direct TypeScript Check

Status: resolved for Vitest on this Windows 11 laptop.

Frontend Vitest and production build completed locally on 2026-06-09 after installing Node.js LTS through `winget`. Direct `tsc --noEmit` is not a defined package script in Version 1; use the supported Vitest/build workflow unless a future TypeScript-only script is added.

Required resolution evidence:

- Keep `npm test -- --run` passing locally and in CI.
- Keep `npm run build` passing locally and in CI.
