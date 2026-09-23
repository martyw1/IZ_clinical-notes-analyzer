# Release Notes

## Script workflow consolidation — 2026-09-23

Consolidated Windows source startup, grouped developer tests and Alleva diagnostics, and archived superseded startup/setup and beta support tools. Top-level scripts reduced from 42 to 25. Client package entry points and the published Production 1.0 ZIP remain unchanged. See [move inventory and validation](validation/script-consolidation-2026-09-23.md).

## Source script organization — 2026-09-23

Build and source launch entry points now live in `scripts/`, with standalone Alleva tools in `scripts/diag-build-tools/` and the metadata verifier in `scripts/security/`. Callers, CI filters, tests and operator documentation follow the new paths. The developer builder accepts `-PreservedArchiveDirectory` and can use the locally archived immutable beta ZIPs without restoring them to the repo. Production 1.0 application behavior, version metadata and the previously published ZIP are unchanged. See [the script guide](../scripts/README.md).


## Production 1.0 - build 2026.09.21.2

Production qualification evidence: [production 1.0 validation](validation/production-1-0-2026-09-21.md).

Current candidate: `1.0.0` / build `2026.09.21.2` / installer revision `1`. The installer stages and verifies a prepared package when it is run from a relocated normal folder or a OneDrive-backed folder, while retaining strict installed-app and local-data path checks. A truly fresh install uses the same R3-supplied starter administrator credential on supported devices and requires an immediate personal password change; upgrades and reinstalls preserve existing account passwords and password state.

The final ZIP passed 799 tests, seven build gates, two fresh-profile browser password/recovery/restart flows, packaged upgrade/reinstall and 13 normal/OneDrive source checks on the Windows 11 host. The client laptop, Windows 10 and full platform qualification remain unverified. See [installer portability validation](validation/installer-portability-2026-09-21.md). No clinical rules, LOC-change validation status, or live Alleva gates changed.


Production 1.0 adds safe forensic correlation for login attempts and Alleva jobs: categorical failure reasons, job/stage identifiers, request attempts, HTTP status, elapsed time, and record counts. Passwords, token values, raw vendor responses, and clinical identifiers are excluded from these diagnostic additions. Administrator recovery invalidates prior sessions and recovery codes atomically.

A narrow installer bridge accepts supported beta.3/beta.4 releases into this exact initial production release while retaining ownership, integrity, schema, backup, and rollback checks. General semantic-version ordering and downgrade protection remain unchanged.

## Historical Beta.4 CMD maintenance package - build 2026.09.15.2

The September 15 package and its validation report are immutable historical evidence. Its receipt, hash, and results are not claims about the September 21 candidate. That historical build fixed valid SYSTEM-owned Windows profile roots, absent PowerShell arguments, verified shutdown before removal fingerprints, and cleanup of the bootstrap-owned transaction. Full build and exact-package live HTTP/Edge lifecycle passed in its recorded scope. See [the September 15 validation report](validation/windows-cmd-maintenance-2026-09-15.md).

## Beta.4 stability update — build 2026.09.10.2

- Correct UTC completion times and persistent, safe timeout feedback in Settings.
- Separate failed-record and job-error counts.
- Preserve rapid successive manager actions that share a Windows clock tick. No clinical-rule or schema changes.
- Source and client package validation: [final fix and smoke report](validation/beta4-sync-feedback-fix-2026-09-10.md).

## 2.0.0-beta.4 — 2026-09-10

Build: 2026.09.10.1; channel: beta-local-desktop-v2.

- First-use desktop administrator starter password with mandatory personal password change.
- Account password changes, saved one-time recovery codes, and Forgot password in the app.
- Staff temporary-password reset form; existing account passwords preserved on upgrade.
- Source and rebuilt Windows package share the same password-management flow.
- Clinical logic unchanged. LOC-change window remains unvalidated; live Alleva approval gate remains in place.

See [password management](password-management-beta4.md). Validation is recorded in docs/validation/password-management-beta4-2026-09-10.md after completion.



## Unreleased - Documentation and help alignment (2026-09-08)

- The 2026-09-08 guidance update identified app `2.0.0-beta.3` / build `2026.09.03.1`; checklist content stays `1.2.0`. That identity is historical; the current source candidate is the production 1.0 build recorded above.
- The offline HTML guide and in-app Help now describe source-filtered rosters, exact saved-plan selection, filtered exports, manual processing warnings, expired sessions, and the unresolved LOC-change/live-sync gates.
- Earlier screenshots and V1 procedures are labeled historical and linked to current guidance. Existing guide paths remain valid.
- This checkout help update does not rebuild or revalidate the prepared installer.

Current source candidate: `1.0.0` / build `2026.09.21.2` / installer revision `1`.

Current release channel: `stable-local-desktop`.

Production package completion date: `2026-09-21`; source-bound final receipt and client handoff checksum are recorded in the package index.

Repository snapshot note (2026-08-16): the validated near-final Windows beta source is preserved by the annotated tag `windows-near-final-beta-2026-08-16` on `main`. This repository-state snapshot does not change the app version, build number, release channel, or live Alleva/LOC-change approval gates.

## Unreleased - Checkout repair and UI cleanup (2026-09-04)

- Dashboard failures now offer in-place refresh and retain explicitly marked previous counts after a failed update.
- Compact navigation, product-focused header, keyboard skip navigation, and a risk-first dashboard use the existing clinical design system.
- Combined browser scenarios preserve exact version and authorization checks after earlier scenarios import additional synthetic records.
- That historical source-checkout validation used the beta3 release metadata and prepared installer. LOC-change validation and live Alleva approval remain unresolved.
- See [repair validation and completion record](validation/repair-ui-2026-09-04.md) for current evidence and limits.
## Historical 2.0.0-beta.3 - Office-manager workflow and release-readiness update

Build: `2026.09.03.1`

Version metadata name: `Version 2.0 Beta 3 office-manager workflow update`

Summary:

- Aligned the beta3 metadata in `VERSION`, `VERSION.json`, frontend package metadata, backend settings, sample OpenAPI metadata, Windows preflight, and the visible app footer.
- Implements source-scoped roster/export, exact saved-plan selection, encrypted manual metadata, version-bound review/correction history, safe session/upload state, readable clinical evidence and explicit metric units.
- Preserves exact source-system and treatment-plan identities, immutable plan lineage, deterministic Missing Data/Needs Review/Conflicting Evidence/Unable to Evaluate outcomes, and the existing gated Alleva read-only boundary.
- Bundles `VERSION.json` into the packaged runtime root. The rebuilt beta3 executable, embedded frontend assets, release folder/ZIP, frozen `/api/version` and native Edge/Chrome footer have been verified against build `2026.09.03.1`.
- Keeps standalone historical patient-wide treatment reviews without a reliable plan/version link outside exact raw-plan reads; embedded plan-bound reviews remain preserved and deterministic rules are unchanged. Previously projected recurrence dates for excluded legacy reviews may differ.
- Records the unresolved user retention choice for reused encrypted source documents; no detach or erase behavior is claimed until that choice is answered and validated.
- Keeps the level-of-care-change update window configurable and visibly unvalidated, live Alleva validation disabled, credential rotation/history remediation open, and signing/retention/legal-hold decisions open.
- Preserves pull-completion feedback while either roster refreshes, with controlled regression coverage. The final application commit is `f65b3b7`; later documentation-only changes do not change the tested binary. See [final smoke results](validation/office-manager-final-smoke-2026-09-04.md) for exact test totals, native coverage, runner warnings and operational limits. This remains beta, not production, clinical-production or GA approval.

## 2.0.0-beta.2 - V2 release-readiness update

Build: `2026.07.11.1`

Version metadata name: `Version 2.0 Beta release-readiness update`

Summary:

- Post-build 2026-08-20 documentation update: adds an offline illustrated setup/install/daily-use/troubleshooting guide for Marleigh with synthetic, non-PHI screenshots from the real Windows startup and V2 local UI; aligns README, current documentation state, beta checklist, runbook, admin recovery, installer, and V2 handoff references without changing the app version or release gates.
- Post-build 2026-07-13 update: adds the shared operational pull to Treatment Plans, automatic queue refresh from either pull surface, immutable same-ID update history with exact updated-ID audit details, a patient-name-free Patient Roster tab, and a manager-authorized treatment-plan/status CSV export.
- Post-build 2026-07-13 update: removes the manual Alleva mapping-approval form and applies the published Alleva v1 mapping automatically at pull time while retaining an encrypted mapping payload plus plaintext version/checksum provenance metadata.
- Post-build validation used only a disposable synthetic local profile and local mock Alleva service; the live-import and LOC-change external gates remain unchanged.

- Aligns `VERSION`, `VERSION.json`, frontend package metadata, `/api/version`, the V2 footer, sample OpenAPI metadata, and Windows preflight on the active V2 beta version.
- Adds an explicit synthetic-only isolated-environment final-validation procedure and a single release-readiness record for operator, security, and support handoff.
- Records the remaining external gates: supervised approved live Alleva validation; exposed-credential rotation and downstream/history-remediation approval; and R3 IT/records decisions on signing and retention/legal hold.
- Keeps live sync gated and makes no production, history-remediation, signing, retention, or live-Alleva-validation claim.

## 2.0.0-beta.1 - V2 beta local desktop rebuild

Build: `2026.07.08.1`

Version metadata name: `Version 2.0 Beta local desktop rebuild`

Summary:

- Archives the pre-2.0 runtime under `deprecated/v1/`.
- Activates a focused V2 FastAPI and React/Vite local desktop runtime.
- Adds V2 treatment-plan aggregate/content contracts, nested detail viewer, 42-step checklist evidence surface, bounded Raw Field Explorer, and Evidence Coverage Map.
- Adds a local API Harness job model for `Pull ALL Treatment Plans - ALL Fields` with incremental JSONL, TSV/CSV, observed schema, logs, artifacts, compact progress, cancel, and bounded preview.
- Keeps patient names excluded by default and keeps clinical narrative text out of forensic logs.
- Keeps the LOC-change treatment-plan update window unvalidated and configurable.
- Updates Windows preflight, local-stack, API-configuration smoke, and release build validation for the active V2 runtime.
- Records final validation evidence in `docs/v2-beta/validation-report.md` and task-list coverage in `docs/v2-beta/task-coverage-audit.md`.

## 1.4.6-beta.1 - Windows no-admin install readiness

Build: `2026.06.30.1`

Version metadata name: `Beta 1.4.6-beta.1 Windows no-admin install readiness`

Post-build beta-readiness update on 2026-07-06:

- Simplifies the app shell navigation so daily work starts with `Status Dashboard`, `Treatment plans`, `Review queue`, and `Manual upload`, while less-frequent support/admin pages appear as smaller shortcuts.
- Bounds global and Alleva treatment-plan lookup status/results so long progress or diagnostic text scrolls within the status/result areas instead of pushing lower page content below the viewport.
- Adds regression coverage that source-document due-date disagreement without a validated LOC-change explanation remains a `Needs Review` treatment-plan outcome with `TP-DUE-DATE-CONFLICT`.
- Adds `docs\beta-client-test-run-guide.md` for non-technical first beta client install, launch checks, treatment-plan review expectations, lookup status behavior, diagnostics, backup, maintenance, and known beta boundaries.
- Updates release packaging validation and manifest metadata so the beta client test-run guide is included alongside `docs\patient-treatment-plan-handling.md`.

Summary:

- Aligns version metadata and active docs to `1.4.6-beta.1` / build `2026.06.30.1`.
- Adds `docs\patient-treatment-plan-handling.md` as the current implementation map for manual-upload treatment plans, gated Alleva REST sync, patient treatment-plan aggregates, local tables, deterministic timeliness evaluation, selected-client checklist results, content-fact privacy handling, API routes, and Treatment Plans UI code locations.
- Updates the Windows release builder to require that the treatment-plan handling reference is included in the release folder and records it in `release-manifest.json`.
- Adds packaged local-data backup helpers through `scripts\backup-local-data.ps1`, `scripts\Backup-IZ-Clinical-Notes-Analyzer.cmd`, the release-folder backup command, and installed Start Menu/Desktop backup shortcuts.
- Adds a confirmed complete-uninstall path through `scripts\complete-uninstall-local-data.ps1`, `scripts\Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd`, the release-folder complete-uninstall command, and an installed Start Menu shortcut that requires typing `REMOVE IZ DATA`.
- Keeps normal uninstall data-preserving: app files and shortcuts are removed, while `%LOCALAPPDATA%\IZ Clinical Notes Analyzer` stays in place for reinstall/upgrade.
- Rewrites the Windows User Guide for no-admin install, first launch, backup, troubleshooting, diagnostics, data-preserving uninstall, and complete uninstall.
- Updates the Windows Deployment and Test Guide with release-folder contents, installed shortcuts, backup behavior, uninstall behavior, and target-laptop acceptance criteria.
- Makes Patient ID the only patient identifier accepted for upload, Treatment Plans, chart labels, generated review records, exports, downloads, API summaries, and audit context.
- Removes patient names, addresses, contact details, source filenames, source attachment URLs, author/custodian labels, and similar direct identifiers from new upload/import storage and browser payloads; existing local rows are neutralized by schema compatibility startup.
- Rejects deprecated manual `client_name` uploads and chart creates when a patient name is supplied, while preserving compatibility fields by setting them to Patient ID.
- Disables Alleva/API name matching for treatment-plan sync readiness; REST records must map by patient/client ID, and name-only records remain unmapped.
- Tightens Treatment Plan Timeliness dashboard/detail/override access to administrators and office managers because counselor ownership is not explicit in that table.
- Blocks unsafe bootstrap-admin defaults in production-like/local-client startup readiness and changes default reset-on-startup to off unless a recovery script explicitly enables it.
- Adds a disabled-by-default `Import and display Alleva patient names` App settings control. Alleva treatment-plan sync stores generated redacted display labels by default and redacts existing Alleva-sourced names again when the setting is saved off.
- Keeps validation-only name fallback separate from patient-name import/display and verifies both settings persist after save/readback.
- Adds an admin-only `Pull / refresh treatment plans` button directly on the Treatment Plans tab.
- Moves documented unused/legacy code files into `depricated/` with a manifest and excludes deprecated folders from Windows release packaging.
- Adds redacted diagnostics collection through `scripts\collect-diagnostics.ps1`, `Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd`, and installer-created Start Menu/Desktop Diagnostics shortcuts.
- Hardens the standalone API configuration page against OpenAPI/schema text injection by building generated operation fields with DOM APIs rather than markup strings.
- Adds CSV formula injection protection and keeps saved API client credentials write-only in browser responses.
- Validation evidence for the redaction cleanup is recorded in `docs/validation/validation-report-2026-06-28-treatment-plan-redaction-cleanup.md`; target-laptop packaged install/backup/uninstall validation remains listed in `docs/Windows-Deployment-and-Test-Guide-Version-1.md`.

## 1.4.5-beta.1 - R3 beta-client readiness

Build: `2026.06.23.1`

Version metadata name: `Beta 1.4.5-beta.1 R3 beta-client readiness`

Summary:

- Renames the primary dashboard tab to `Status Dashboard`, moves `Treatment plans` immediately after it, and adds bundled R3 Recovery Services header-logo support via `/api/branding/header-logo` with an overrideable filesystem setting.
- Removes the desktop floating oval shortcuts and the obsolete intake-guide page. Manual upload remains in normal navigation; API testing remains available through App Settings and `/api-configuration`.
- Adds admin-only `Clear All Patient Data` actions in Status Dashboard Quick Actions and App Settings. The action requires the exact phrase `CLEAR ALL PATIENT DATA`, clears local patient/chart/treatment-plan/manual-upload/review rows and encrypted upload files, and preserves settings, API credentials, user accounts, audit logs, docs, and rules.
- Moves manual `Retrieve Active Treatment Plans` to the Status Dashboard EMR/API card and keeps startup sync off by default behind the existing approval and endpoint-mapping gates.
- Adds saved manager status/comment notes for each selected-client Treatment Plan checklist criterion plus a selected-client counselor action CSV export.
- Fixes due-date classification so due today is `Urgent`, 1 day out is `Urgent`, 2-7 days out is `Due Soon`, 8+ days out is `Compliant`, and only dates before the evaluation date are `Overdue`.
- Hardens manual upload errors so unexpected 500s return non-PHI JSON detail, roll back partial rows, and clean up encrypted files written before failure.
- Keeps Review Queue as the generated/manual chart-review workbench and Treatment Plans as the timeliness/due-date work queue.
- Documents that Alleva mapping exports were not present in the repo during this readiness pass; conservative REST review-date/signature/due-date aliases were added without opening live import.
- Validation evidence is recorded in `docs/validation/validation-report-2026-06-23-beta-client-readiness.md`.

## 1.4.4-beta.1 - Beta treatment-plan checklist detail visibility

Build: `2026.06.21.1`

Version metadata name: `Beta 1.4.4-beta.1 treatment-plan checklist detail visibility`

Summary:

- Converts the current local Windows desktop app metadata to beta: app version `1.4.4-beta.1`, channel `beta-local-desktop`, stability `beta`, and prerelease metadata enabled.
- Keeps Treatment Plan Checklist content version separate at `1.2.0`; the checklist JSON content version did not change.
- Adds selected-client `42-Step Checklist Evaluation` results to the Treatment Plans detail payload and UI so a manager can inspect every canonical checklist step for the selected treatment-plan client/item.
- Adds checklist results to selected treatment-plan CSV/JSON exports.
- Keeps the global Checklist tab as the canonical rule reference and exposes finding examples, remediation suggestions, and evidence fields.
- Preserves the gated Alleva REST treatment-plan sync path, including required `/clients` and `/treatment-plans` behavior and optional `/treatment-reviews` warning behavior.
- Keeps LOC-change timing visibly unvalidated until R3/Marleigh confirms the exact rule.

## 1.4.4 - Documentation and metadata alignment

Build: `2026.06.20.1`

Version metadata name: `Version 1.4.4 current documentation and metadata alignment`

Summary:

- Promotes the current app version metadata and documentation references to `1.4.4` on `main`.
- Keeps the Version 1 local Windows desktop runtime, FastAPI desktop service, built React/Vite frontend assets, SQLite local data, encrypted uploaded-file storage, encrypted saved API-secret storage, role-based access control, deterministic Treatment Plan Tracking rules, Workflow profiles, in-app Help, readiness checks, and forensic audit logging.
- Preserves the gated Alleva REST treatment-plan sync readiness boundary and manual-upload binder deletion usability behavior.
- Replaces generic manual Alleva treatment-plan sync failure text with stage-specific user messages for token, endpoint permission, endpoint mapping/version, timeout, empty-result, warning, and success states.
- Simplifies the API Testing Harness into a step-by-step flow and keeps one Alleva quick action: `ALL Patient Records`, backed by `GET /clients` with Excel-ready TSV output.
- Lets approved Alleva treatment-plan sync continue when the optional `/treatment-reviews` endpoint is unauthorized or unavailable, while keeping `/clients` and `/treatment-plans` required.
- Adds an admin-only Review Queue button to pull active treatment plans through the same approved sync path and then open the Treatment Plans queue.

## 1.4.2 - Manual upload button usability

Build: `2026.06.18.2`

Version metadata name: `Version 1.4.2 manual upload button usability`

Summary:

- Fixes manual-upload binder deletion usability.
- The delete-binder action remains clickable enough to show exact patient-ID confirmation guidance when clicked before the confirmation value matches.
- The app no longer presents unavailable delete buttons with a Windows busy cursor in the manual-upload workflow.
- Keeps the gated Alleva REST treatment-plan sync readiness work from Version 1.4.1.
- Keeps Version 1 local Windows desktop runtime, built React/Vite frontend assets, FastAPI desktop service, SQLite local data, encrypted uploaded-file storage, encrypted saved API-secret storage, role-based access control, deterministic Treatment Plan Tracking rules, Workflow profiles, in-app Help, readiness checks, and forensic audit logging.

## 1.4.1 - Alleva REST treatment-plan sync readiness

Summary:

- Added a separate Alleva REST treatment-plan sync configuration path that does not require a FHIR root.
- Kept live startup sync disabled by default.
- Required explicit R3/Alleva live-sync approval and validated endpoint mapping before any live patient treatment-plan data can be imported.
- Preserved the boundary that Alleva is the source system while R3's deterministic local timeliness engine performs compliance decisions.

## 1.4.0 - Treatment-plan hardening and generated-name fallback

Summary:

- Hardened Treatment Plan Timeliness behavior, evidence handling, and export details.
- Superseded earlier generated/patient-ID fallback naming with:
  - `no-name-found_YYYY-MM-DD_HHMMSS` when no name is found in source evidence.
  - `no-value-found_YYYY-MM-DD_HHMMSS` when an empty or unusable value is found.

## Current implementation boundaries

- Operator-triggered read-only Alleva treatment-plan import is off by default and requires saved tenant credentials, API/sync enablement, and explicit live-read authorization. The published Alleva v1 mapping is applied automatically; supervised validation of real tenant response shapes and broader production/compliance rollout remain external release gates.
- The LOC-change treatment-plan update window remains unvalidated by R3/Marleigh. The app ships a manager-editable 7-calendar-day preset, but this must stay configurable and visibly unresolved until confirmed.
- Manual upload remains an upload-time snapshot. Use the monthly compliance-check fallback when API refresh is unavailable.
- Optional LLM setup exists but is disabled by default and is not the primary review path.
- Docker, PostgreSQL, and nginx are not ordinary Windows desktop requirements for the current R3 beta-local-desktop path.
- The package is still not a signed MSI/MSIX with repair/modify support; the release-folder builder is the current packaging path.

## Version metadata files

Current version values must stay aligned in:

- `VERSION`
- `VERSION.json`
- `frontend/package.json`
- `frontend/package-lock.json`
- README and primary docs
- `/api/version`
- UI footer
- release metadata

## Primary current docs

- `README.md`
- `docs\Windows-User-Guide-Version-1.md`
- `docs\Windows-Deployment-and-Test-Guide-Version-1.md`
- `docs\UAT-Version-1-Marleigh.md`
- `docs\treatment-plan-checklist-v1.md`
- `docs\open-blockers.md`
- `docs\api-configuration-and-connectivity.md`
- `docs\architecture.md`
- `docs\runbook.md`
- `docs\codebase-map.md`
- `docs\admin-access-reset.md`

Historical validation reports keep their original tested version numbers and should not be read as the current app version unless they explicitly say they were updated for `2.0.0-beta.1`.
