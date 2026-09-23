# Client handoff: what to copy and what to leave out

Current app: `2.0.0-beta.3` / build `2026.09.03.1` / `beta-local-desktop-v2`.
Checked against the source on 2026-09-08. This is a handoff inventory and code review, not a new release build or target-laptop certification.

## Recommended handoff: a prepared Windows release

Give the client a prepared release, not a copy of the entire development repository. A prepared release includes `app/runtime/IZClinicalNotesAnalyzer.exe`, which bundles the Python runtime, backend libraries, browser assets, rules and checklist. The client should not install Python, Node.js, Git, Docker or PostgreSQL to use it. The existing executable is x64 (Intel/AMD 64-bit); use a Windows 10/11 x64 client for this package. ARM or 32-bit compatibility is not established.

The existing candidate is `dist/windows-release/IZ-Clinical-Notes-Analyzer-v2.0.0-beta.3.zip`. Its manifest is dated 2026-09-04. It predates the September 8 Help changes. Rebuilding only `frontend/dist` does not update the frontend embedded inside that executable. Rebuild and validate a current package on the developer machine before promising the latest in-app Help to the client. Do not rename an old ZIP as a new build.

For the existing supported package shape, retain the complete `app/` and `installer/` folders and these eight commands plus the manifest:

```text
IZ-Clinical-Notes-Analyzer-v2.0.0-beta.3/
  Install-IZ-Clinical-Notes-Analyzer.cmd
  Launch-IZ-Clinical-Notes-Analyzer.cmd
  Stop-IZ-Clinical-Notes-Analyzer.cmd
  Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd
  Backup-IZ-Clinical-Notes-Analyzer.cmd
  Restore-IZ-Clinical-Notes-Analyzer.cmd
  Uninstall-IZ-Clinical-Notes-Analyzer.cmd
  Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd
  release-manifest.json
  installer/
    install-windows-release.ps1
    uninstall-windows-release.ps1
  app/
    runtime/IZClinicalNotesAnalyzer.exe
    VERSION
    VERSION.json
    backend/
    frontend/dist/                 (index.html AND all referenced assets)
    config/
    scripts/
    docs/
```

Do not keep only the EXE: installation, initialization, stop, diagnostics, backup and restore use the adjacent scripts. The current installer also explicitly requires `app/backend/` and `app/frontend/dist/index.html`, even though the frozen runtime embeds its executable dependencies. `installer/` is a real dependency of the install/uninstall wrappers although the builder's required-item array does not enumerate it.

Add `IZ-Clinical-Notes-Analyzer-Quick-Start.pdf` from `output/pdf/` next to the package for the client. The longer illustrated guide is the HTML file and all accompanying PNG files (10 referenced screenshots; 11 PNGs in the directory) in `docs/guides/Version 2.0 Beta  2.0.0-beta.2  beta-local-desktop-v2/`; keep that directory intact if supplying the illustrated guide. Its directory name is stable, its text covers beta.3, and its older screenshots are labeled historical.

### If you want a smaller prepared package

The current builder copies most of the repository and then excludes known unsafe/developer categories. That is not a minimum-file packaging strategy: it can still copy unrelated new folders such as `black-hole-lab/`, generic `output/`, `tmp/` and unrelated documentation. A filename safety scan does not prove every remaining file is necessary or free of sensitive content.

The following is the source-reviewed minimum support payload to retain inside `app/` when preparing a smaller candidate. It is a proposed trimming allowlist, not a claim that a newly trimmed package has passed installation testing. Keep the package-root files and `installer/` above. Assemble a separate candidate; never delete files from your working repo or the only release copy.

- `runtime/IZClinicalNotesAnalyzer.exe` from the freshly built release, with every file beside it if the packaging format changes from the present one-file runtime.
- `VERSION`, `VERSION.json`, and the complete built `frontend/dist/`.
- `backend/app/` and `backend/requirements-windows-local.txt`; no virtual environment, caches or tests. These retain the backend directory required by installation and the source used by the existing support/restart fallback. Normal packaged launch uses the EXE.
- `config/` with its rules and checklist, excluding generated/local data.
- The exact run/support scripts listed in the next section, plus `scripts/launch-packaged-runtime.cmd` and `scripts/complete-uninstall-local-data.ps1` for packaged entry points. Keep `scripts/Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd` only if also offering the source-style complete-uninstall wrapper.
- Support docs: `docs/beta-client-test-run-guide.md`, `docs/patient-treatment-plan-handling.md` (both required by the builder), `docs/admin-access-reset.md`, `docs/runbook.md`, `docs/open-blockers.md`, `docs/release-notes.md`, and the illustrated guide directory if wanted. Put the one-page PDF beside the release.

Before distributing any trimmed candidate, verify each retained wrapper's targets, run the folder and ZIP safety scans, and test install, launch, diagnostics, stop, backup/restore and data-preserving upgrade under a standard Windows account with synthetic data. The current run did not construct or certify that trimmed candidate.

## If you specifically copy the source repo

This is the smaller source-copy list for running with a prebuilt frontend and retaining troubleshooting tools. Preserve the following relative paths exactly. Copy all source files inside `backend/app/` and `config/`, but exclude runtime/generated files listed below.

```text
VERSION
VERSION.json
backend/
  app/                            (complete Python source tree; no __pycache__)
  requirements-windows-local.txt
frontend/
  dist/                           (complete successful build, including assets)
config/
  rules/
  checklists/
scripts/
  Start-IZ-Clinical-Notes-Analyzer.cmd
  start-windows-local.ps1
  startup-windows-local.ps1
  preflight-windows.ps1
  Stop-IZ-Clinical-Notes-Analyzer.cmd
  stop-windows-local.ps1
  Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd
  collect-diagnostics.ps1
  Backup-IZ-Clinical-Notes-Analyzer.cmd
  backup-local-data.ps1
  Restore-IZ-Clinical-Notes-Analyzer.cmd
  restore-local-data.ps1
  update-local-admin.ps1           (R3 support only; needs this copy's venv)
docs/
  beta-client-test-run-guide.md
  patient-treatment-plan-handling.md
  admin-access-reset.md
  runbook.md
  open-blockers.md
  release-notes.md
```

Launch this source copy with `scripts/Start-IZ-Clinical-Notes-Analyzer.cmd`, not the prepared-release `Install` command. It creates `backend/.venv` on the client and may install Python 3.12 through winget if no accepted Python exists. An internet connection may be required. Do not copy your own `.venv`: it contains machine-specific paths and is not a portable runtime.

With complete, prebuilt `frontend/dist` and no frontend sources to rebuild, Node/npm are not needed for serving the UI. If the client must rebuild the frontend, also retain `frontend/src/`, `frontend/public/` if present, `frontend/index.html`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/tsconfig.json` and `frontend/vite.config.ts`, and install a compatible Node/npm on that machine. Prefer rebuilding on the developer machine and replacing the complete `dist/` instead. The one-page client PDF deliberately covers the prepared-release route; these are the separate source-copy instructions.

## Do not send

- `.git/`, `.github/`, `.codex/`, `.omo/`, `.agents/`, `.codegraph/` or other agent/editor working state.
- `.env`, `.env.*`, `.alleva.local.ps1`, local configuration files, `App Credentials Info.md`, `scripts/diag-build-tools/Test-AllevaApi.ps1`, credentials, tokens, encryption keys or saved vendor settings. The client must generate its own configuration and keys locally.
- Databases (`*.db`, `*.sqlite`, `*.sqlite3`), uploads, exports, patient examples, raw logs, diagnostics created on your machine, reports, backups (`*.izcnabackup`) or browser traces/screenshots containing private data.
- `.venv/`, `backend/.venv/`, `node_modules/`, Python caches, test/build caches and test reports.
- `scripts/diag-build-tools/`, `scripts/security/`, `deprecated/`, `depricated/`, old release folders/ZIPs, video extraction/walkthrough material, `black-hole-lab/`, local client-testing evidence, generic `tmp/` and unrelated `output/`. Historical `output/pdf/` material is now in the local non-deployment archive; use the current package instructions for client handoff.
- For client-only use: backend/frontend tests, E2E tooling, build/installer authoring scripts, developer analysis, PRDs, Git history and frontend source/build dependencies. Keep these on the development/support machine.

Never copy `%LOCALAPPDATA%/IZ Clinical Notes Analyzer` from your machine as a fresh-client install. That is runtime data and access material, not application distribution content.

## What setup changes on Windows

| Area | Prepared release | Source copy |
| --- | --- | --- |
| Developer tools | Bundled executable; no pip/npm install on ordinary launch/install | May install Python 3.12 per user; creates `.venv`; installs Python packages; may run npm/build |
| App location | `%LOCALAPPDATA%/Programs/IZ Clinical Notes Analyzer` | Folder where the copy was extracted |
| Runtime data | `%LOCALAPPDATA%/IZ Clinical Notes Analyzer` | Same per-user data location |
| Windows changes | Per-user app files, settings and shortcuts | Local app data, repo venv, optionally per-user Python |
| Admin/firewall/services | No elevation, firewall-rule or service installation found in the inspected scripts | No elevation requested; user-scoped Python installer can have its own PATH/registration effects |
| PowerShell | `-ExecutionPolicy Bypass` for that process; no persistent policy change found | Same |
| Startup checks | EXE exists, port is valid/free, localhost readiness responds | Python minimum, module availability, frontend assets/freshness, rules/checklist and free port |

The preflight accepts Python 3.11+ but does not enforce an upper compatibility range. It checks module availability, not every installed package version. Node/npm discovery has no Node-version gate; the locally installed Vite declares Node `^20.19.0 || >=22.12.0`. These are reasons to prefer the bundled release, not a guarantee that any Python/Node version works. No dependency installation or developer-tool upgrade was performed by this handoff task.

## Operational caveats confirmed in code

1. **Open the browser explicitly.** `launch-packaged-runtime.cmd` starts the EXE and checks readiness; `backend/app/desktop_runtime.py` does not open a browser. After starting, open Edge or Chrome to `http://localhost:8000` (or the port supplied by R3 support).
2. **Use the packaged shortcut to restart.** `stop-windows-local.ps1` routes a Yes-to-restart answer through the source launcher. That can create/install developer dependencies even from a release containing those source files. In the client guide, choose **N** if asked to restart, then use the Desktop/Start Menu app shortcut.
3. **Arrange first login.** Setup generates the initial admin password in the client's local configuration; it is not displayed by the installer. R3 support must securely arrange first sign-in on that laptop. Never distribute the developer's `.env` or password. The current `update-local-admin.ps1` recovery utility requires `backend/.venv/Scripts/python.exe`; it is not a bundled-only recovery path.
4. **Protect upgrades.** The installer backs up existing local data before copying and uses `robocopy /MIR` under the app install directory. Keep personal files out of that directory: files absent from an update can be removed. This is not a general atomic rollback guarantee.
5. **Use the right uninstall.** Normal uninstall preserves runtime data. Complete Uninstall intentionally deletes it. Do not use Complete Uninstall for routine updates or troubleshooting.
6. **Backups belong to the Windows user.** The encrypted `.izcnabackup` uses Windows CurrentUser protection. Do not treat it as a portable cross-user/cross-laptop migration file without a separately validated recovery plan.
7. **Security prompts require support.** Do not instruct the client to disable antivirus, firewall, SmartScreen or organization policy. Signing/trust and the exact target-laptop behavior still need release validation.
8. **Keep clinical gates.** LOC-change rules remain configurable/unvalidated; live Alleva import requires explicit approval. Missing Data, Needs Review, Conflicting Evidence and Unable to Evaluate are not compliance approvals.

## Verification and limits

- Read-only code inspection of the launcher, preflight, runtime, installer generation, stop, diagnostics, backup and restore paths; independent dependency audit agreed that the prepared release avoids ordinary developer-tool setup.
- The existing beta.3 directory and ZIP passed `scripts/scan-release-safety.ps1` on 2026-09-08. This is the implemented filename/category scan, not a content/PHI guarantee, a current-source rebuild, or a minimum-payload certification.
- Required-file checks and PDF validation for this handoff are recorded in `docs/validation/client-handoff-2026-09-08.md`.
- A clean standard-user test on the actual client Windows laptop is still required. Code inspection cannot establish that the laptop's antivirus, enterprise policy, disk space, CPU architecture or existing applications will never cause a problem.

Sender commands (run on the developer machine against the candidate, not on client clinical data):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/scan-release-safety.ps1 -Scope Directory -Path <release-folder>
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/scan-release-safety.ps1 -Scope Zip -Path <release-zip>
```

Source references: `scripts/build-windows-installer.ps1` (`Assert-ReleaseRequiredItems`, `Copy-RepoContent`, generated installer), `scripts/preflight-windows.ps1`, `scripts/launch-packaged-runtime.cmd`, `scripts/stop-windows-local.ps1`, `scripts/update-local-admin.ps1`, `backend/app/desktop_runtime.py`.
