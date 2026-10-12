# Current V2 test and acceptance plan

Source **1.0.1 / build 2026.10.12.1 / stable-local-desktop**. Use isolated synthetic profiles/users/records only. Never reuse a client's AppData, `.env`, database, upload, saved credential or vendor payload. [Current validation](../validation/current-work-2026-10-12.md) records actual results; beta `validation-report.md` and task coverage are historical evidence.

## Automated boundaries

- Backend: version/readiness/navigation, authentication/recovery and password epoch, role/facility authorization, source-scoped patient IDs and immutable plan versions, 42 criterion evidence, clinical missing/conflicting/LOC policy behavior, persisted evaluation provenance, manager reasons/corrections, encrypted manual storage and upload/extraction bounds, replay deduplication, job lifecycle, formula-safe exports and redacted audit verification.
- Frontend: first-use password/recovery, login/session cleanup, authorized name display and missing-name fallback, exact `patientRecordId`/`planVersionId` selection across sources, saved-version history, Manual and Alleva roster filtering, nested evidence/checklist, manager actions, safe exports, bounded progress and Help responsiveness.
- Windows/package: launcher/preflight, source and prepared-runtime version identity, maintenance/backup contracts, required guide/assets, package forbidden-file checks and exact ZIP receipt/hash. Historical package results cannot qualify a new build.
- Run complete backend suite, frontend tests, TypeScript and frontend production build. Use the release builder's required gates; record exact blockers rather than disabling failing checks.

## Manual synthetic workflow

1. Launch an isolated local service and use the real browser/API. Exercise temporary-password change when needed and recovery-code save acknowledgment before workspace access. Never capture credentials/codes.
2. As office manager, open Dashboard, Patient Roster, Patient Record Detail and exact saved plan/version/checklist. Confirm authorized synthetic name appears when supplied, missing values remain unavailable and same MRN/plan IDs across sources cannot cross-select.
3. Check Manual and Alleva saved plans in plan roster and source/status filters. Import changed/unchanged synthetic records, verify immutable history/replay behavior and that an open selection stays fixed.
4. Upload approved synthetic formats; inspect warning/opaque outcomes and encrypted archive. Check permitted manager actions/corrections and filtered CSV identity/status; names/narrative must not leak into exports/audit.
5. As administrator, inspect audit chain and safe job details. Verify unauthorized roles receive denied access to administrative functions. Exercise only synthetic/mock vendor contracts; no live production pull for release testing.
6. Inspect current Help/login and key pages on desktop/narrow widths, sign out, stop/restart and verify identity. Check the offline guide and local assets separately; record file-policy/visual limitations honestly.
7. Test backup/restore and install/upgrade/reinstall only in isolated disposable synthetic profiles; preserve real client data. Device-loss and power-loss qualification require separate appropriate environments.

Expected appliance workload is app/browser plus OneDrive and normal Windows services; ChatGPT is excluded. Small-fixture latency is not capacity acceptance. Test realistic synthetic volumes/largest accepted documents before promising throughput. Preserve Missing Data, Needs Review, Conflicting Evidence and Unable to Evaluate outcomes and unresolved external gates.
