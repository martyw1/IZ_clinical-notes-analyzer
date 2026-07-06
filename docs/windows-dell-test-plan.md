# Windows Dell Validation and Packaging Path

Date: 2026-06-04

## Packaging Decision

Recommended path for R3 office use: **Option A, packaged non-technical deliverable**.

Option A should ship a signed `.exe` or `.msi`, bundled Python runtime or equivalent executable, built `frontend\dist` assets, startup shortcuts, repair/modify support, uninstall support, and local app-data preservation by default. This is the right target for ordinary Windows 10/11 Home users because it does not require Docker, PostgreSQL, Git, Node.js, or command-line setup.

Current repository state: Option A is the target, but the repo does **not** yet contain a finished installer, bundled runtime, code-signing setup, repair wizard, or uninstaller. Do not claim "no runtime required" until the runtime is actually bundled.

Fallback path for validation: **Option B, source-checkout/dev setup script**.

Option B is acceptable for the purchased Dell validation pass and internal development. It uses `scripts\startup-windows-local.ps1` and `scripts\test-local-app-stack.ps1`; it may install Python packages and build frontend assets from source.

## Dell Validation Prerequisites

- Purchased Dell laptop running Windows 10 Home or Windows 11 Home.
- Local Windows account signed in.
- Microsoft Edge or Google Chrome installed.
- Internet access for first-time Python/npm package installation if using source checkout.
- Git installed, or a ZIP download of this repository.
- No real PHI, real patient notes, production `.env`, API keys, bearer tokens, encryption keys, or passwords copied into the test checkout.

## Copy/Paste PowerShell Validation

Open **Windows PowerShell** as the signed-in user. These commands use a clean validation folder under the user profile.

```powershell
$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/martyw1/IZ_clinical-notes-analyzer.git"
$WorkRoot = Join-Path $env:USERPROFILE "IZ Clinical Notes Analyzer Validation"
New-Item -ItemType Directory -Path $WorkRoot -Force | Out-Null
Set-Location $WorkRoot

if (!(Test-Path ".git")) {
  git clone $RepoUrl .
}

git checkout main
git pull origin main --ff-only
git rev-parse --short HEAD
```

Run the rerunnable local stack test:

```powershell
Set-Location "$env:USERPROFILE\IZ Clinical Notes Analyzer Validation"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-local-app-stack.ps1 -Port 8010
```

Run the API configuration smoke test:

```powershell
Set-Location "$env:USERPROFILE\IZ Clinical Notes Analyzer Validation"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-api-configuration-local.ps1 -Port 8021
```

Start the local app without opening a browser automatically:

```powershell
Set-Location "$env:USERPROFILE\IZ Clinical Notes Analyzer Validation"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\startup-windows-local.ps1 -NoBrowser -AssumeYes
```

In a browser on the Dell, open:

```text
http://localhost:8000
```

The startup script prints the first local admin password the first time it creates `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\.env`. Save that password securely for the validation run. Do not commit or share it.

## Manual UI Checklist

1. Sign in as `admin`.
2. Confirm the footer shows `Beta v1.4.6-beta.1` after the final version bump.
3. Open `Status Dashboard` and confirm the R3 logo, EMR/API source card, Manual upload source card, and `Retrieve Active Treatment Plans` action are visible.
4. Confirm the primary navigation shows `Status Dashboard`, `Treatment plans`, `Review queue`, and `Manual upload`, with support/admin pages shown as smaller shortcuts.
5. Open `Treatment plans`.
6. Confirm the dashboard loads, the updated evidence queue and footer version `Beta v1.4.6-beta.1` are visible, the selected-client 42-step checklist evaluation opens in Treatment Plans, manager notes can be saved on synthetic criteria, and the LOC-change window is visibly unvalidated if not confirmed.
7. Perform a synthetic or approved lookup and confirm long lookup status/result text remains inside the bounded panel areas instead of pushing lower content below the viewport.
8. Open `App settings`.
9. Confirm runtime readiness is not `fail`, startup treatment-plan sync is off by default, and `Clear All Patient Data` requires the exact phrase before deletion.
10. Open `Workflow profiles` and confirm it shows `Treatment Plan Timeliness Tracker` with a published version.
11. Use `Seed draft from 42-step checklist` to create a synthetic editable draft with no PHI.
12. Confirm the draft snapshot and transition rules can be edited before publish and a draft can be edited in place.
13. Publish or discard the synthetic draft according to the validation run plan.
14. Open `Forensic logs` and confirm workflow events are present.
15. Upload only synthetic test files if upload validation is needed.

## Evidence to Save

Save these outputs locally on the Dell, outside the repository if they might contain machine-specific paths:

- PowerShell transcript/log path printed by startup scripts.
- `git rev-parse --short HEAD`
- `.\scripts\test-local-app-stack.ps1 -Port 8010` final PASS output.
- `.\scripts\test-api-configuration-local.ps1 -Port 8021` final PASS output.
- Screenshot of the app footer showing version `Beta v1.4.6-beta.1`.
- Screenshot of the Status Dashboard with R3 logo and source cards.
- Screenshot of the Treatment Plan Timeliness tab showing simplified primary navigation, bounded lookup status/results, the updated evidence queue, selected-client checklist evaluation with manager notes, and footer version `Beta v1.4.6-beta.1`.
- Screenshot of Workflow profiles showing the seeded Treatment Plan Timeliness Tracker profile and 42-step draft action.

Do not save screenshots containing real PHI or real credentials.

## Pass Criteria

- Source checkout starts on Windows 10/11 Home without Docker or PostgreSQL.
- Test scripts pass using local SQLite and synthetic data only.
- Browser opens and authenticated admin flow works.
- Runtime readiness is `ok` or `warn`, not `fail`.
- Workflow profile API/UI loads.
- Treatment Plan Timeliness dashboard loads.
- Generated local data stays under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer` or the test-specific app-data folder.

## Known Not-Yet-Complete Packaging Work

- Build a real signed installer or MSI.
- Bundle Python runtime or package the backend as an executable.
- Include built frontend assets in the packaged artifact.
- Create shortcuts from installer.
- Implement repair/modify flow that preserves SQLite, encrypted uploads, `.env`, encryption keys, and audit logs.
- Implement uninstall flow that preserves local app data by default and requires explicit confirmation before deleting data.
- Decide code-signing certificate and SmartScreen strategy.
