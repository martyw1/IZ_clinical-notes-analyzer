# Source script organization validation — 2026-09-23

## Scope and preservation

Production 1.0 source entry points were consolidated under `scripts/`; standalone Alleva tools moved to `scripts/diag-build-tools/`, and the historical metadata verifier moved to `scripts/security/`. See [the relocation map and commands](../../scripts/README.md). Caller paths, existing regression tests, CI filters, packaging exclusions and operator documentation were updated together. Historical evidence retains its original paths with relocation notes.

The move manifest verified all 38 relocated files by SHA-256: seven tracked source files and 31 ignored local settings/log/export files. All 31 private files remain ignored. No application runtime code, version metadata, authentication behavior or live API integration changed. No live vendor API request was made. Existing unrelated `tmp/` contents were left alone.

The earlier archive cleanup had moved the builder's pinned beta.3/beta.4 inputs out of `dist/windows-release`. The builder now accepts `-PreservedArchiveDirectory` and recognizes the current user's canonical local archive. Exact pinned sizes and hashes remain mandatory; an explicit missing archive directory still fails closed. These inputs are developer build prerequisites, not client runtime requirements.

## Checks

| Check | Result |
|---|---|
| Existing Alleva guided-tool Pester suite before and after move | 58 passed each run; synthetic providers only |
| Focused production configuration/version tests before move | 20 passed |
| Updated CMD path-quoting test | Failed before relocation, passed afterward |
| Moved PowerShell scripts, builder and caller syntax | Parsed successfully |
| Historical metadata verifier | Four self-test canaries passed; full `-AllowDirty` verification passed |
| Raw API tester | Offline `-Mode Version -NoLocalSettings` passed |
| Actual Windows build CMD, synthetic sibling | Correct repository working directory, spaced argument forwarding and exit-code propagation in a path containing spaces and `&` |
| Actual Windows build CMD, missing pinned archive input | Expected exit 1 and `PRESERVED_ARCHIVE_CHANGED` |
| macOS wrapper | Bash syntax and synthetic sibling forwarding/exit propagation passed from a path containing spaces |
| Independent active caller/path review | No broken active references or package-exclusion gaps found |
| Release-safety regression suite after relocation commit | PASS, including forbidden-category, malformed-input, misleading-success, privacy, directory, ZIP and private-report canaries; moved tester remains tracked, private state remains ignored |

The actual moved CMD was run with `-ValidationOnly`, without either skip flag: **617 backend tests passed** (three dependency deprecation warnings), **182 frontend tests passed**, and the TypeScript/Vite frontend build passed. Packaging then exited 1 at the existing `Copy-SafeDataTree` guard: `config/checklists` in this OneDrive checkout carries reparse tag `0x9000e01a`. The failing function is byte-equivalent after newline normalization to pre-change main. This is a pre-existing OneDrive developer-build limitation, not a moved-script caller failure; no new package or passing package-safety result is claimed. The guard was not weakened.

The dependency installer reported eight npm audit findings (three moderate, five high) in the existing dependency set. No dependency manifest or lockfile changed; dependency remediation is outside this relocation.

The immutable client ZIP still has SHA-256 `91d08cd08d01dfff121a3823fd6a62cb93b91ef33e7d1ab7f3adc8cf78be17ec`. Local working evidence is under `.omo/evidence/script-organization/` and is intentionally excluded from Git.

## Limits

The macOS check is a shell fixture on Windows, not a macOS platform qualification. The configured Python language server was unavailable (installation had previously been declined); pytest supplies the executable check for the changed existing Python test. Actual client-laptop and Windows 10 qualification remain open as documented for Production 1.0. This source organization does not create a new client release or replace the previously published ZIP.
