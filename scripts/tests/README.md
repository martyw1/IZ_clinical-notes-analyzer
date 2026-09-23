# Developer validation

These scripts test the app; they are not launch/install commands. Run from the repository root. Client packages exclude this directory.

| Purpose | Entry point |
|---|---|
| Guided Alleva tools using synthetic records | `test-alleva-end-user-tools.ps1` (Pester) |
| Source application / API configuration smoke | `test-local-app-stack.ps1`, `test-api-configuration-local.ps1` |
| Password browser regression against current source or explicit runtime | `test-password-browser.mjs` |
| Office-manager workflow | `test-office-manager-smoke.ps1` |
| Maintenance qualification | `test-cmd-maintenance.ps1` (requires package, tier, case and evidence inputs) |
| Packaging, archive and lifecycle checks | `test-windows-installer-packaging.ps1`, `test-windows-release-archive.ps1`, `test-windows-lifecycle.ps1` |
| Stop/process ownership | `test-windows-stop.ps1` |
| Release scanner regression | `test-release-safety.ps1` |
| CI receipt contract | `test_validate_maintenance_ci_receipt.py` |
| Existing running app / macOS checks | `smoke.sh`, `test-macos-local-launch.sh`, `test-preflight-macos.sh` |

`maintenance-*.Tests.ps1` are parameterized harness scripts, not all Pester suites. Do not invoke Pester indiscriminately against this directory. Follow the maintenance qualification guide for their required arguments.

Examples:

```powershell
powershell.exe -NoProfile -Command "Invoke-Pester -Script './scripts/tests/test-alleva-end-user-tools.ps1'"
powershell.exe -NoProfile -File ./scripts/tests/test-release-safety.ps1
node ./scripts/tests/test-password-browser.mjs
```

Direct Alleva network probes and approved live workflow verification are under `../diag-build-tools/`. They are separate from synthetic regression tests. Historical beta.3-to-beta.4 upgrade testing is under `../deprecated/`.
