# Deployment archive cleanup — 2026-09-23

The user authorized moving superseded deployment packages and background material into a local `not-required-for-deployment` archive. No runtime source, active application data, credentials, or current production package was removed.

Six historical ZIP files are removed from the tracked working tree:

- `dist/windows-release/IZ-Clinical-Notes-Analyzer-v1.4.6-beta.1.zip`
- `dist/windows-release/IZ-Clinical-Notes-Analyzer-v2.0.0-beta.1.zip`
- `dist/windows-release/IZ-Clinical-Notes-Analyzer-v2.0.0-beta.2.zip`
- `dist/windows-release/IZ-Clinical-Notes-Analyzer-v2.0.0-beta.3.zip`
- `dist/windows-release/IZ-Clinical-Notes-Analyzer-v2.0.0-beta.4.zip`
- `output/IZ-Admin-Recovery-beta.3.zip`

These are generated historical distribution/recovery packages, not runtime dependencies. Copies were archived from the main checkout, production worktree, and older beta checkout; Git history remains intact. Any historical documentation references remain historical evidence, not deployment instructions.

The complete local archive contains 11,389 files across 689 top-level moves (2,926,116,223 bytes). Each file was verified using SHA-256 before and after relocation, with zero move failures. The absolute-path manifest and verification records remain outside Git because they describe local support and runtime material.

The current production 1.0.0 build 2026.09.21.2 ZIP remains local and unchanged, with SHA-256 `91d08cd08d01dfff121a3823fd6a62cb93b91ef33e7d1ab7f3adc8cf78be17ec`. Production acceptance results are recorded in [the release validation](production-1-0-2026-09-21.md). This cleanup changes no application source or behavior, so the already-passed release tests were not repeated.

Active data and configuration, source dependencies, Git/linked temporary workspaces, and unrelated untracked files were retained. Background videos were not found in the inspected locations and remain pending identification by the user.
