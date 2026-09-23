# Which script should I use?

For the development checkout, use the CMD entry points below. Their PowerShell files are implementations, not alternative workflows. For a client installation, use the Install/Launch/maintenance commands in the prepared ZIP instead. Client commands and installed paths have not changed.

| I want to… | Use this |
|---|---|
| Start the source app | `Start-IZ-Clinical-Notes-Analyzer.cmd` |
| Stop the source app | `Stop-IZ-Clinical-Notes-Analyzer.cmd` |
| Build a Windows release | `Build-IZ-Windows-Installer.cmd` |
| Back up / restore local data | `Backup-IZ-Clinical-Notes-Analyzer.cmd` / `Restore-IZ-Clinical-Notes-Analyzer.cmd` |
| Collect support diagnostics | `Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd` |
| Set up or check the development environment | `preflight-windows.ps1`; Start already runs it automatically |
| Diagnose Alleva connectivity or run approved vendor checks | [diag-build-tools/](diag-build-tools/README.md) |
| Run developer regression checks | [tests/](tests/README.md) |
| Locate historical beta tooling | [deprecated/](deprecated/README.md); not for normal use |

## How the files fit together

Windows startup has one implementation: `start-windows-local.ps1`. By default it starts a hidden copy of itself with `-Foreground` and waits for readiness. That foreground process runs preflight once, starts and supervises the server, and opens the browser only after readiness. Port validation and readiness checking each have one implementation. Use `-Foreground` explicitly only when you need a supervised console session.

The matching filenames in `installer/templates/` are necessary package templates. They delegate to installed commands; the root CMD files delegate to their PowerShell implementations. They are not older copies. Keep these package-contract filenames stable.

## Directory map

| Location | Purpose |
|---|---|
| `Start-IZ-Clinical-Notes-Analyzer.cmd` | Start the Windows source checkout through the consolidated `start-windows-local.ps1` |
| `Build-IZ-Windows-Installer.cmd` | Build through `build-windows-installer.ps1`; outputs remain in the repository's `dist/windows-release` |
| `Start-IZ-Clinical-Notes-Analyzer.command` | macOS Finder launcher, delegating to sibling `start-macos-local.sh` |
| `Backup-*.cmd`, `Restore-*.cmd`, `Stop-*.cmd`, `Collect-*.cmd`, `Complete-Uninstall-*.cmd` | Existing local data and maintenance workflows; use their documented safeguards |
| `installer/` | Package construction, installed maintenance implementation and generated client-entry templates |
| `diag-build-tools/` | Standalone Alleva diagnostics, guided exports and their operator README |
| `security/verify-s0-incident-metadata.ps1` | Metadata-only historical privacy-incident verifier |
| `deprecated/` | Superseded startup/setup snapshots and historical beta recovery/upgrade tools; excluded from client releases |
| `tests/` | Test harnesses and synthetic regression checks, including `test-password-browser.mjs` |
| `ci/`, `validate-maintenance-ci-receipt.py` | CI qualification support |
| Other root PS1/SH files | Setup, preflight, platform launch, release safety and local maintenance helpers |

Frontend browser tests and Playwright configuration stay under `frontend/` because they are part of that test suite, not operator tools.

## Windows commands from the repository root

```powershell
.\scripts\Start-IZ-Clinical-Notes-Analyzer.cmd
.\scripts\Build-IZ-Windows-Installer.cmd
.\scripts\diag-build-tools\Run-AllevaEndUserTools.cmd -Action SelfTest -NoPause
powershell.exe -NoProfile -File .\scripts\security\verify-s0-incident-metadata.ps1 -SelfTestOnly
powershell.exe -NoProfile -File .\scripts\diag-build-tools\Test-AllevaApi.ps1 -Mode Version -NoLocalSettings
```

The standalone raw API tester retains working-directory-relative defaults for `.alleva.local.ps1`, `.alleva.endpoints.csv`, and `alleva-api-test-logs`. Invoke it from the repository root to retain the former defaults, or pass explicit path arguments. Its default diagnostic output is sensitive; use approved private diagnostics and the existing redaction guidance.

The guided Alleva tool retains its settings, `logs` and `exports` next to its script. Relocation preserves existing ignored local files; they remain ignored and are not release inputs. Self-tests use synthetic records and do not require live credentials.

## Build inputs and immutability

The builder still verifies the original beta.3 and beta.4 ZIPs before creating an upgrade-compatible package. It uses `dist/windows-release`, or the current user's `not-required-for-deployment/repo/dist/windows-release` archive when the old ZIPs have been moved. Supply `-PreservedArchiveDirectory "C:/path/to/preserved-zips"` for another location. Pinning and hash verification are unchanged. These ZIPs are needed by the developer build, not the installed client.

A released version/build cannot be overwritten. For a local validation build without publishing a replacement release, use `-ValidationOnly`; any skip flags are limited to that diagnostic mode. See [the full build guide](../docs/windows-installer-build-and-install.md).

## Relocation map

| Previous location | Current location |
|---|---|
| `Build-IZ-Windows-Installer.cmd` | `scripts/Build-IZ-Windows-Installer.cmd` |
| `Start-IZ-Clinical-Notes-Analyzer.command` | `scripts/Start-IZ-Clinical-Notes-Analyzer.command` |
| `Test-AllevaApi.ps1` | `scripts/diag-build-tools/Test-AllevaApi.ps1` |
| `diag-build-tools/` | `scripts/diag-build-tools/` |
| `docs/security/verify-s0-incident-metadata.ps1` | `scripts/security/verify-s0-incident-metadata.ps1` |

Historical validation/removal reports retain their original file paths as evidence. The incident verifier’s pinned historical Git tree paths also remain unchanged. The [consolidation record](../docs/validation/script-consolidation-2026-09-23.md) lists the subsequent moves and validation.
