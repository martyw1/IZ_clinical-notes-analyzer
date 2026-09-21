# Client release packages

Current candidate: **1.0.0**, build **2026.09.21.2**, installer revision **1**.

Production qualification evidence: [production 1.0 validation](validation/production-1-0-2026-09-21.md).

## Candidate package under validation

Expected filename: `IZ-Clinical-Notes-Analyzer-v1.0.0-build-2026.09.21.2-installer-r1.zip`.

The portable ZIP, clean-source build receipt, hash, relocated normal-folder and OneDrive-backed package tests, fresh-install credential check, upgrade password-preservation check, and Windows 10/11 lifecycle evidence are pending. Track them in [installer portability validation](validation/installer-portability-2026-09-21.md). Do not distribute this candidate as client-ready until those criteria are filled with passing evidence.

## Historical verified package: build 2026.09.15.2

Filename: `IZ-Clinical-Notes-Analyzer-v2.0.0-beta.4-build-2026.09.15.2-installer-r1.zip`.

The clean-source build receipt, ZIP hash, live package tests, standard-account results, and remaining qualification limits are recorded in the [validation report](validation/windows-cmd-maintenance-2026-09-15.md). The receipt remains bound to its source commit; subsequent documentation updates do not rebuild or replace the immutable ZIP.

The final core-acceptance P02 rerun passed all nine live HTTP/Edge/executable lifecycle steps for install, beta.3 smart upgrade with preserved data, live local API/browser operation, data-preserving uninstall, reinstall, typed complete purge, and cleanup with zero owned processes or listeners. Receipt: `.omo/evidence/windows-cmd-maintenance/cmd-9ac37e50b421/maintenance-run-receipt.json`, SHA-256 `cda9db5e33682d4940ba1d7dc357b495524e142f7a0a7ac2be527e6f944ca9df`; case SHA-256 `7f6e40146b1f65a68b120d699579904e2dec36737532d640e55c305c5364f034`.

Distribution status: **Accepted for the user-defined core deployment scope; not approved as fully client-qualified.** The broader Windows Home matrix, VM power-loss tests, and process-isolation edge cases remain unverified and are deferred by the user. They are not critical blockers for the accepted core deployment.

Use [Windows CMD maintenance](windows-cmd-maintenance.md) for smart upgrade, data-preserving uninstall, separate complete purge, backup and recovery. Beta.3 does not need a complete uninstall before upgrade.

## Historical packages

The hashes below belong to archives that were actually preserved and verified in their original validation scope. They remain historical and are not the current candidate.

| Package | SHA-256 |
| --- | --- |
| [IZ-Clinical-Notes-Analyzer-v1.4.6-beta.1.zip](../dist/windows-release/IZ-Clinical-Notes-Analyzer-v1.4.6-beta.1.zip) | `2a6487bc6550919a64100bdb5cc246f31f13c9575639bf3974945a7e7753e317` |
| [IZ-Clinical-Notes-Analyzer-v2.0.0-beta.1.zip](../dist/windows-release/IZ-Clinical-Notes-Analyzer-v2.0.0-beta.1.zip) | `7bffa8a0b09ed43154f4d8e7ab45dadcfd1bcee6ea1af526933f065856916c1d` |
| [IZ-Clinical-Notes-Analyzer-v2.0.0-beta.2.zip](../dist/windows-release/IZ-Clinical-Notes-Analyzer-v2.0.0-beta.2.zip) | `0dd87ba68fef6598c6d9dee9eaeffcfee65cf54b132766710cce67eee2324cb8` |
| [IZ-Clinical-Notes-Analyzer-v2.0.0-beta.3.zip](../dist/windows-release/IZ-Clinical-Notes-Analyzer-v2.0.0-beta.3.zip) | `9c5fd47203242e1a21df612f719f1c14fa4240c86ba869f924ec4690834fc89c` |
| [IZ-Clinical-Notes-Analyzer-v2.0.0-beta.4.zip](../dist/windows-release/IZ-Clinical-Notes-Analyzer-v2.0.0-beta.4.zip) | `67b83eea402566658dea6d64ac6cba37a192a7d1bd670cf560541324c0092b14` |
| [IZ-Admin-Recovery-beta.3.zip](../output/IZ-Admin-Recovery-beta.3.zip) | `2d53a941c8d9b6ec4d3b2d49613ef07c9a0a33275889bf0503a66395b1632600` |

All six archives passed the repository release safety scanner on September 10, 2026. Expanded release folders are represented by their complete ZIP packages.

Old archives named only v1.0.0 and v1.1.1 are excluded (they are unrelated to the new build-qualified production 1.0.0 package): v1.0.0 contains caches and repository metadata; v1.1.1 also contains files classified as credentials and clinical exports. They have not been modified or uploaded.

Videos, private runtime data, local credentials, databases, and raw clinical exports remain excluded.
