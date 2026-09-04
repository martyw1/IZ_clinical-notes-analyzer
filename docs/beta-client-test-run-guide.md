# Beta Client Test Run Guide

Date: 2026-09-04

Applies to: IZ Clinical Notes Analyzer Version `2.0.0-beta.3` / build `2026.09.03.1` on the `beta-local-desktop-v2` Windows desktop runtime.

This guide is for a first near-production beta test run with non-technical users. It assumes R3 provides a prepared release folder or zip. Ordinary users should not need Windows administrator access, Docker, PostgreSQL, Git, Node.js, or command-line work.

Marleigh's primary non-technical handoff is the illustrated `docs\guides\Version 2.0 Beta  2.0.0-beta.2  beta-local-desktop-v2\Marleigh-Setup-Install-and-User-Guide.html`. Use this file as the shorter test-session checklist.

## What The Tester Should Receive

- A folder or zip named `IZ-Clinical-Notes-Analyzer-v2.0.0-beta.3`.
- The R3-approved first sign-in instructions through a secure channel.
- This checklist and the illustrated Marleigh guide.
- Only synthetic or approved beta-test data. Do not use real PHI until R3 has approved the beta data-handling plan.

## Install

1. Extract the zip if R3 supplied a zip file.
2. Open the release folder.
3. Double-click `Install-IZ-Clinical-Notes-Analyzer.cmd`.
4. Wait for the install window to finish.
5. Start the app from the Start Menu shortcut named `IZ Clinical Notes Analyzer`.

The app installs for the current Windows user under `%LOCALAPPDATA%\Programs\IZ Clinical Notes Analyzer`. Runtime data is stored separately under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.

## First Launch Checks

After sign-in, confirm these items before doing test work:

1. The footer says `Version 2.0 Beta | 2.0.0-beta.3 | build 2026.09.03.1 | beta-local-desktop-v2`.
2. The administrator navigation shows `Status Dashboard`, `Patient Roster`, `Patient Record Detail`, `Treatment Plan Detail`, `Treatment Plans Roster`, `Manual Upload`, `API Testing Harness`, `Users`, `Forensic Logs`, `Settings`, and `Help`.
3. The top-right runtime badge says `Active runtime: V2 | admin`.
4. `Status Dashboard` opens without a browser error.
5. `Treatment Plans Roster` opens and either shows imported rows or the exact Settings requirements that keep live import blocked.

## Daily Beta Workflow

1. Open `Status Dashboard` to confirm the app is running and the footer shows the current beta version.
2. Use `Treatment Plans Roster` for the gated operational pull and exact-plan list.
3. Use `Patient Roster` and `Treatment Plan Detail` for MRN-centered review, evidence, and checklist decisions.
4. Use `Manual Upload` only for synthetic or approved test files.
5. Use `Help` for role permissions, setup notes, and support guidance.
6. Run `Backup IZ Clinical Notes Analyzer` before and after a meaningful test session.

## Treatment Plan Checks

For each synthetic or approved test client, compare the screen to the source evidence:

- Patient ID and source ID mapping are correct.
- Select and review the exact patient/source/plan/version identity; do not merge same-looking IDs across source systems.
- For a synthetic manual metadata check, use only the supported explicit fields: `patient_name`/`patient_full_name`, optional `service_date`/`serviceDate`, optional `original_plan_reference`, and explicit `signature_date`/`signature_datetime`. Do not rely on combined signature prose. Omitted values stay omitted, conflicts stay `Conflicting Evidence`, and service/reference values do not supply admission, signature, or identity fields. See the Task 4 metadata receipt for the verified parser/storage contract.
- For roster/export checks, the pending Task 7 target is exact `patient_record_id` + source + external plan ID + immutable `plan_version_id` selection. `All sources` and source-filtered views should return their exact matching current rows; name/reference search remains local UI state, while export sends every filtered result ID, including off-screen matches, and returns the complete filtered set (no pagination feature) with safe immutable IDs. Full names, original references, search text, narrative, credentials, URLs, and logs/audit details stay out of CSV. Record the actual result as pass or failure after Task 7's receipt is available; do not assume this behavior from the guide.
- Treat roster/export source membership as a Task7 validation item. Task8 backend metric evidence is independently verified, but browser/build metric evidence still requires the current Task10 run; record a failure rather than assuming completion.
- Review only plan-bound treatment-review evidence. Standalone patient-wide legacy reviews without a reliable plan/version link are outside exact raw-plan reads; embedded plan-bound reviews remain visible.
- Admission date and current level of care are present or clearly marked missing.
- The latest valid treatment-plan review/update date is correct.
- Source-document `Next Review Due`, staff-signature cadence due date, and LOC-effective due date are shown separately when available.
- Status is one of the explicit outcomes: `Overdue`, `Urgent`, `Due Soon`, `Compliant`, `Needs Review`, `Missing Data`, `Conflicting Evidence`, `Unable to Evaluate`, `Returned`, or `Approved`.
- If dates disagree, the app should show `Needs Review` or another review/error state instead of silently guessing compliance.
- LOC-change timing remains unvalidated and should stay visibly marked unresolved until R3/Marleigh confirms the rule.

## Lookup Status Behavior

When an admin performs an Alleva/API lookup or treatment-plan pull:

- The status message appears in a bounded status area.
- Long status messages or lookup details should scroll inside that area instead of pushing the rest of the page below the screen.
- Lookup result rows should stay inside the lookup results section.
- Do not paste screenshots that include credentials, tokens, real patient IDs, or PHI into email or chat.

## Diagnostics

Use diagnostics when the app fails to open, a page shows an error, a lookup behaves unexpectedly, or R3 support requests evidence.

1. Close the browser tab if the app is stuck.
2. Open the Start Menu.
3. Run `IZ Clinical Notes Analyzer Diagnostics`.
4. Send the created zip to R3 support only through an approved secure channel.

Diagnostics are written under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\diagnostics`. They are redacted, but still treat them as sensitive.

## Backup

Back up local data before upgrades, before a long beta session, and after a meaningful test session.

1. Open the Start Menu.
2. Run `Backup IZ Clinical Notes Analyzer`.
3. Type `BACKUP` when asked.
4. Keep the created zip secure.

Backups can contain local settings, the local database, encrypted uploads, audit logs, and encryption material. Keep backup zips out of email and cloud folders unless R3 explicitly approves that transfer.

## Maintenance

- Use normal uninstall when upgrading or reinstalling. It keeps local app data.
- Use complete uninstall only on disposable synthetic data or when R3 support confirms all local data can be removed.
- Do not move `%LOCALAPPDATA%\IZ Clinical Notes Analyzer` into OneDrive or another synced folder.
- Do not manually delete random files from the local data folder. Use the app's backup, diagnostics, clear-data, uninstall, and complete-uninstall flows.
- Do not enable live Alleva patient sync unless R3/Alleva approval and endpoint mapping validation are complete.

## Known Beta Boundaries

- The package is not a signed MSI/MSIX.
- Live Alleva patient import remains gated off until approved.
- The LOC-change treatment-plan update window is not final.
- Optional LLM behavior is disabled by default and is not required for treatment-plan timeliness decisions.
- Any beta evidence shared outside the laptop must be synthetic or approved, redacted, and sent through an approved secure channel.
