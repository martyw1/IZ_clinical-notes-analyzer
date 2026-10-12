# Documentation, desktop tools and USB handoff — October 12, 2026

## S0 and source scope

Owner requested current HTML guidance, all source/support files on GitHub main, generated-file cleanup to D:, clinical staff wallpaper, shipping insert in source and a timestamped codebase ZIP. Existing source maintenance validation is recorded in current-work-2026-10-12.md (629 backend / 184 frontend tests). Fresh focused backend verification: 26 passed, one existing Starlette deprecation warning. No clinical policy or live-import gate changed.

## Documentation and desktop artifacts

Current HTML describes all nine observed desktop tools, authorized administrator recovery and portable OneDrive ZIP backup/restore. Corrected troubleshooting that incorrectly limited portable ZIP restore to the original account/computer. All 23 references resolve; tools (1)–(9) and the private handoff file (0) are described. The private credential file is not copied into source. Shipping insert copied byte-for-byte from output/pdf/Getting-Started-Guide.pdf to docs/guides/current/Getting-Started-Guide.pdf; confirmed one page and visually reviewed a fresh Poppler rendering. No credentials included.

Added source shortcut recreation script; created and inspected nine test links with valid targets. Backup-task registration remains explicit and separate. Added clinical staff wallpaper matching owner-supplied R3 developer image, with “R3 Clinical Staff Apps” and “Less friction. More focus on care.” The generated asset is tracked; applying it uses the intended account's Windows personalization settings.

## S1 relocation and source backup

See docs/removal-log.md for generated-only relocation scope, retained dependencies and required historical-package build argument. USB archive is under D:/08 Development archives/IZ-cleanup-20261012-171746; per-file manifest/verification stays beside the moved artifacts. Active data and local secrets are excluded from Git and the source ZIP; a source ZIP is distinct from the sensitive OneDrive profile backup and from a runnable installer.

GitHub CLI authenticated through owner device authorization. Remote uses HTTPS; remote main matched local base before committing. Source ZIP is generated using git archive from the final committed tree, with timestamp and commit identity, and verified against Git blob contents plus ZIP CRC and SHA-256. Completion results follow after checks finish.

Fresh frontend follow-up: 184 tests in 28 files passed, TypeScript noEmit passed, Vite production build passed. Release-safety characterization, privacy, malformed-input, directory/ZIP and private-report canaries passed. The shell did not expose npm on PATH, so the installed Vitest/TypeScript/Vite entry points were run with the bundled Node executable.

## Final handoff checks

Fresh checks: 26 backend tests, 184 frontend tests, TypeScript, production frontend build and release-safety canaries passed. Current HTML: 23 references validated and every observed desktop item (0)–(9) documented. Nine recreated source shortcuts validated; PDF rendered and checked. Staged source paths and recognized secret/private-key patterns checked; no runtime databases, upload directories, local env/configuration or credential notes staged. Only local branch is main; authenticated non-force GitHub push access confirmed.

All 9,806 files in the pre-move USB manifest are present at the destination, with final byte-hash verification recorded in its verification.txt. File moves are complete. Automatic approval review rejected deletion of empty source directory shells (“blocked by policy”, no additional reason supplied), so those empty folders remain. Operational source dependencies, frontend build, active local profile and data-backup folders remain on C:. This is project/development-artifact cleanup, not removal of Windows components or unrelated personal files.

After committing this record, push main normally and verify the remote SHA. Create the final git-archive ZIP from that commit on D:, with sidecar SHA-256 and metadata recording the matching local/remote commit, file count and full Git-blob/ZIP-integrity verification. Those sidecars are the exact snapshot completion receipt, avoiding a self-referential commit hash inside its own source tree.

Final tracked-file check found App Credentials Info.md was already tracked in the base commit despite its ignore rule. Its private local copy was preserved on D:; this handoff removes the file from the current source tree. Prior Git history is retained and may still contain the old reference note; no history rewrite or credential rotation was performed. The final source ZIP excludes it. Repo-only author identity uses the authenticated GitHub account's verified numeric-ID noreply address; global Git identity is unchanged.

USB relocation completed: all 9,806 original manifest entries passed final SHA-256 checks, and no files remain in the six generated source folders. Empty directory shells remain because automatic approval blocked their removal.
