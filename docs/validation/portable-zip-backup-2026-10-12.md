# Portable profile ZIP backup station — October 12, 2026

Scope: owner-requested unencrypted backups of the configuring Windows user's local app profile to organization OneDrive, with a separate source-checkout restore procedure. Not a new release qualification, not a change to historical packages, and not the existing DPAPI `.izcnabackup` format.

## S0 and implementation

Inspected the dirty working tree, AGENTS instructions, existing encrypted backup/restore, runtime configuration, encryption and migration paths before changes. Existing changes were preserved. No app data or historical backup was deleted. New scripts use current-user LocalAppData and place only ZIP output in the chosen OneDrive folder. Existing backups, diagnostics and transient SQLite journals are excluded. Archives include settings/encryption material, so an unencrypted ZIP exposes clinical data and credentials to its reader. This is explicitly the owner's requested storage choice; approved tenant controls and sharing remain owner responsibilities.

Backup stops the source app, snapshots each SQLite database, verifies hashes, performs an isolated extraction, and applies the app's existing semantic/encryption verifier before publishing. Busy API jobs block the preflight. A source-file inventory change fails the backup. The app restarts without a browser if it had been running. Backup and restore share an exclusive local lock. Restores validate a sibling staging folder, preserve current data under a timestamped sibling, and only then activate the restored profile. They never merge data and require interactive RESTORE. Custom absolute database/profile paths require support migration.

## Evidence

- Focused final synthetic backup/restore tests: 14 passed. Covers a separate-user profile with retained settings, SQLite data and decryptable upload; refusal of existing targets, corrupt content, unsafe/Windows-reserved paths, active jobs and failed app semantics.
- First actual local archive: verified ZIP published to organization OneDrive folder, approximately 61 MB. Last-result status reported success with cloud_sync_verified=false.
- Actual archive extracted into an isolated local profile and checked through existing app resolve_profile/inspect_database: all 2,243 encrypted payloads checked were valid. Live profile was not replaced.
- Both PowerShell entry points parsed successfully. Current-user limited interactive Task Scheduler task registered every three days at 6 PM, first due October 12, 2026. It needs this Windows user signed in; missed executions use StartWhenAvailable. No credentials are stored in the task action.
- Frontend: 184 tests passed; production build passed after final Help text edits. App page and built assets served HTTP 200. Current offline HTML guide was updated at the same desktop-shortcut target.
- Earlier full maintenance backend evidence is in current-work-2026-10-12.md. Fresh follow-up privacy/upload/version/portable-ZIP checks: 26 passed (including all 14 portable-ZIP tests). End-to-end scheduled cloud synchronization remains unverified.

## Limits

Cloud upload completion is not proven by a local successful copy. Check OneDrive web visibility and sync completion. Physical replacement-computer rehearsal remains open; the isolated relocation test establishes local semantic portability without DPAPI, not hardware disaster-recovery qualification. Matching app code/build and runtime must be prepared separately. ZIPs contain neither application installation nor desktop/task registration; those must be recreated on a replacement account. No automatic retention deletion is configured. A running/sleeping/offline computer or signed-out Windows user cannot execute the interactive task. Data in other Windows accounts is not included.
