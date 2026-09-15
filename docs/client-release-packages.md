# Client release packages

Current candidate: **2.0.0-beta.4**, build **2026.09.15.2**, installer revision **1**.

## Verified package

Filename: `IZ-Clinical-Notes-Analyzer-v2.0.0-beta.4-build-2026.09.15.2-installer-r1.zip`.

The clean-source build receipt, ZIP hash, live package tests, standard-account results, and remaining qualification limits are recorded in the [validation report](validation/windows-cmd-maintenance-2026-09-15.md). The receipt remains bound to its source commit; subsequent documentation updates do not rebuild or replace the immutable ZIP.

Distribution status: **Platform qualification incomplete; not approved as fully client-qualified.** Windows 10 Home and actual VM power-loss evidence are unavailable.

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

Local v1.0.0 and v1.1.1 archives are excluded: v1.0.0 contains caches and repository metadata; v1.1.1 also contains files classified as credentials and clinical exports. They have not been modified or uploaded.

Videos, private runtime data, local credentials, databases, and raw clinical exports remain excluded.
