# cross-platform-desktop-refactor - Work Plan

## TL;DR (For humans)
**What you'll get:** The existing clinical-notes application will keep its business behavior while gaining a properly packaged, double-clickable Windows version and a native Apple Silicon Mac version, each with automatic startup checks, one-instance behavior, browser launch, clean stop, backup/restore, diagnostics, and safe uninstall. After that foundation is proven on both systems, measured bottlenecks will be improved only when repeatable tests show a meaningful benefit without functional or safety regressions.

**Why this approach:** Most of the application is already portable, so the plan isolates only the operating-system-specific paths, lifecycle, security-key handling, and packaging instead of rewriting the backend or React interface. A hard cross-platform verification barrier separates that work from performance changes, preventing speed work from concealing incomplete Mac or Windows wiring.

**What it will NOT do:** It will not change clinical rules, checklist decisions, security roles, live Alleva enablement, or the current Windows folder-and-ZIP distribution model. It will not add Intel Mac, App Store, MSI/MSIX, Docker/PostgreSQL, cross-system backup restore, or speculative optimizations. It will not call an unsigned or untested Mac build production-ready.

**Effort:** XL
**Risk:** High - process ownership, encrypted local data, native packaging, shutdown races, and Apple distribution all require exact cross-platform evidence.
**Decisions to sanity-check:** Windows remains 64-bit and per-user; Mac support is Apple Silicon with a macOS 14 deployment target and a no-admin `~/Applications` install path; a macOS 14 Apple-Silicon run, Apple credentials, and clean downloaded-artifact tests remain external release gates; different data profiles must use distinct configured ports.

Your next move: execute the approved plan in order, preserving the portability barrier before any performance work. Full execution detail follows below.

---

> TL;DR (machine): XL/high-risk two-lane delivery: first a minimally invasive Windows x64/macOS ARM64 desktop portability refactor with executable artifact proof, then measurement-gated performance candidates with semantic equivalence.

## Scope
### Must have
- Execute from clean `main` at `8c1edc460c2af354f74417cf27d26abaf72ccc70`; stop before Task 1 if `git status --short --branch` is not clean or `git rev-parse HEAD` differs. Preserve unrelated user work if the execution environment later becomes dirty.
- Lane 1 changes only portability-required seams: immutable packaged-resource discovery, mutable OS-local data/configuration paths, first-run bootstrap ordering, one side-effect-free application factory, desktop lifecycle/control, job shutdown, operator backup/restore, diagnostics/uninstall, native packaging, and native artifact verification.
- Keep the FastAPI routes, auth/RBAC, audit semantics, SQLAlchemy/SQLite data model, migrations, deterministic rule/checklist behavior, encrypted clinical storage, gated Alleva/API behavior, and React/Vite UI contracts unchanged except where a desktop adapter must call them.
- Support Windows 10/11 x64 using the existing per-user release-folder/ZIP/install-shortcut model and Apple Silicon using native ARM64 `.app` bundles inside a DMG with deployment target `14.0`. The main Mac bundle identifier is `com.r3recoveryservices.izclinicalnotesanalyzer`; the Finder-accessible utilities bundle is `com.r3recoveryservices.izclinicalnotesanalyzer.utilities`. The supported no-elevation Mac install is the Utilities app's `Install/Upgrade for Me` action, which atomically installs the matched app pair under `~/Applications/IZ Clinical Notes Analyzer/`; `/Applications` is optional and never the only documented path.
- In packaged mode, a nontechnical user can double-click the app, have every bundled/runtime/data/configuration prerequisite checked, see a native first-run or failure dialog, reach the default browser only after readiness, launch a second time without starting a duplicate, and stop cleanly through the installed Windows shortcut or macOS Utilities app.
- Resolve mutable data to `%LOCALAPPDATA%/IZ Clinical Notes Analyzer` on Windows and `~/Library/Application Support/IZ Clinical Notes Analyzer` on macOS; preserve `IZ_CNA_LOCAL_APP_DATA_DIR` as the highest-precedence isolated override. Resolve packaged resources separately and never write beneath the repo, CWD, `_MEIPASS`, `.app`, or mounted DMG.
- Bootstrap ordering is fixed: canonicalize the data root using stdlib-only code; acquire/adjudicate the per-data-dir lifetime lock; atomically create or validate `.env` with current-user-private permissions; set `IZ_CNA_ENV_FILE` and the canonical data-root override; only then import configuration, database, routes, or application modules. In packaged mode the private `.env` is authoritative for application configuration: ambient configuration variables other than the two supported user inputs `IZ_CNA_LOCAL_APP_DATA_DIR` and `IZ_CNA_PORT` are ignored and reported safely before settings construction, and internal/test hooks are unavailable in a release artifact.
- One instance is allowed per canonical data directory. Canonical identity uses the normalized absolute path with existing ancestors resolved and Unicode NFC; it case-folds on Windows and on macOS only when the containing volume reports case-insensitive names, then revalidates the created directory's native volume/file identity. Different data directories may run concurrently only on distinct explicitly configured ports. Port precedence is `IZ_CNA_PORT`, then `.env` `BACKEND_PORT`, then `8000`; never auto-increment. A same-data-dir second launch authenticates the existing runtime, opens its URL, and exits 0; an unrelated or other-data-dir port owner is never killed.
- Use a current-user-private runtime state file containing schema version, canonical data-dir ID, run ID, 256-bit control token, PID, process creation time, executable/bundle path, port, start time, and readiness state. "Current-user-private" means owner SID plus Windows SYSTEM/Administrators on Windows, and current EUID with no group/world bits or unexpected ACL grants on macOS. Desktop-only ASGI middleware accepts token-authenticated loopback POST control requests and never exposes the token in a URL, body, log, audit detail, browser JWT, backup, diagnostic bundle, or release artifact.
- Cooperative stop first closes ASGI/job admission, tracks and drains in-flight requests plus outer diagnostic/roster/sync threads and nested sync futures, and spends one absolute 15-second budget on all request/worker/server joins. The stop client has one absolute 30-second budget: cooperative polling through second 20; Windows identity-revalidated `TerminateProcess` at or after second 20 when still alive; macOS identity-revalidated `SIGTERM` at second 20, revalidation plus `SIGKILL` no later than second 25, and exit confirmation by second 30. If any request or worker survives the cooperative budget, the controller persists `stale_or_interrupted`, leaves state and the lease handle intact, skips checkpoint/dispose, and takes the terminal-process path so the OS releases database handles and the lease together; the next launch recovers the stale state. No fallback acts without revalidating PID, creation time, executable/bundle path, run ID, and data-dir ID immediately before each signal/termination.
- Use one streaming, atomically published, versioned operator-backup payload/envelope implementation with a Windows DPAPI current-user/profile key adapter and a macOS Keychain same-user/same-Mac, per-data-profile adapter. Preserve reading and deterministically normalizing legacy Windows operator `IZCNABK2` and preserve the separate database-migration `IZCNABK1:` implementation; the new operator format is `IZCNABK3`. Restore validates keys, configuration, every encrypted object, audit chain, schema/migrations, SQLite integrity/FKs/WAL, and manifest consistency in staging before a rollback-safe swap. Cross-OS restore remains excluded.
- Stage releases from an explicit source-to-destination allowlist, fail on missing or unexpected files, and scan staged trees plus final ZIP/DMG/app contents. Windows artifacts contain no traversal-capable reparse points. macOS permits only a manifest-enumerated, relative, within-bundle PyInstaller framework symlink graph plus the DMG-root `Applications -> /Applications` link; scanners validate link text/resolved containment and content hashes without following any link outside its bundle/DMG root.
- Run the shared suite plus native Windows and ARM64 macOS build-and-execute smoke jobs. An unsigned ARM64 PR/development artifact may pass the automatable engineering gate; Developer ID signing, hardened runtime, notarization, stapling, download quarantine, and clean-real-Mac Finder acceptance remain explicit release-candidate gates.
- A non-bypassable acceptance barrier must produce same-commit Windows and macOS machine-readable receipts plus a direct GitHub attestation of the canonical barrier JSON before Lane 2. The final planning handoff supplies `APPROVED_PLAN_SHA256` outside the implementation branch; before Task 1 the parent executor records that value in protected execution state and verifies it against this exact plan. Task 1 commits a byte-identical tracked copy of the approved plan, a deterministic renderer, and the renderer's complete canonical Task1-36 graph/outcome/path/type/mode policies; every later task is constrained by them. Task 26 reruns the frozen renderer from the approved-plan bytes and may only verify those immutable contracts, record its own commit plus the later trigger identity in protected parent execution state, and pin the verifier hash. Every Lane-2 todo directly depends on Task 26, obtains both independent anchors rather than reading them from an untrusted receipt, binds the attestation certificate to the exact signer workflow/digest/source ref before parsing the subject, fetches the frozen verifier from the GitHub contents API, emits start/post gate receipts, and cannot be accepted, merged, measured, or certified when the exact task delta, chain, online provenance, or cleanup is invalid.
- Lane 2 first commits one measurement foundation, rebuilds receipt-bound Windows/macOS artifacts containing those hooks, then records 7 source runs and 10 packaged cold plus 10 packaged warm runs per target. Each candidate is compared with an immediately preceding control in paired/interleaved runs on the same native runner allocation. Candidates remain strictly ordered: startup reevaluation, packaging mode, endpoint query shape, then frontend splitting only if per-view content-ready timing proves it material.
- Ship a performance candidate only when semantic/privacy/integrity equivalence passes, every precommitted primary cell's paired arithmetic median improves by at least 10% or 250 ms, the exact one-sided paired sign test is `p <= 0.05` with ties counted against the candidate, every primary cell's nearest-rank p95 independently regresses by no more than 5%, and every other protected median/p95/scalar independently regresses by no more than 5%. A complete valid comparison that misses policy is `REJECTED`; missing/failed/incomparable infrastructure is `ERROR` and must be rerun or named as the exact blocker, never mislabeled as a measured rejection.
### Must NOT have (guardrails, anti-slop, scope boundaries)
- No Intel or universal2 Mac build, Mac App Store package, Windows ARM package, MSI/MSIX conversion, Docker/PostgreSQL desktop prerequisite, Node/Python/Git prerequisite for prepared artifacts, auto-update system, or alternate desktop UI framework.
- No business-rule, 42-step checklist, clinical outcome, auth/RBAC, audit, API/Alleva gate, workflow-profile, database-content, or frontend feature change. The unvalidated LOC-change window and live Alleva blockers remain intact.
- No cross-OS restore. Windows-to-Mac or Mac-to-Windows operator backups fail closed with a safe platform-scope error; migration backups remain internal to migration lifecycle code.
- No persistent data, `.env`, database, uploads, logs, reports, API artifacts, runtime tokens/state, credentials, PHI-like samples, virtual environments, dependencies, caches, or `.omo` evidence in a release artifact or commit.
- No unauthenticated shutdown route, browser-visible control token, port-only process ownership, name-only process killing, live-lock stealing by a cooperating app instance, automatic port hunting, or force termination before cooperative shutdown and full identity revalidation. A no-admin per-user macOS app must not claim resistance to a hostile process already running as the same EUID; owner-clearable file flags are hardening/detection only, never the security boundary.
- No weakening or skipping migration checks, schema verification, foreign-key checks, SQLite integrity checks, WAL safety, encryption, redaction, deterministic reevaluation invalidations, or release scans to claim speed.
- No performance refactor in Lane 1 beyond the one-app/one-init correction required for correct wiring. Lane 2 must recapture its own post-barrier baseline and may not count the Lane 1 correction as a Lane 2 gain.
- No benchmark cherry-picking, post-result affected-cell selection, single-run claims, comparison across different hosts/artifacts/fixtures or runner allocations, reuse of a stale baseline after an accepted candidate, source-text/grep-only packaging proof, mocked artifact launch, or `PASS` based only on a command's printed text.
- No production-ready macOS claim when Developer ID credentials, successful notarization/stapling, or exact-artifact clean-Mac quarantine/Finder acceptance is missing.
- No RC/publication claim from this refactor alone. Its outputs retain the existing version/build as engineering candidates; a separately authorized release task must update every required version surface before publication. Missing Windows publisher credentials/SmartScreen proof or Apple release inputs is recorded as an external release blocker, not hidden or treated as engineering PASS.

### External release-candidate gates (separate from automatable engineering completion)
- The exact checksummed, Authenticode-signed/timestamped Windows folder/ZIP must be browser-downloaded with Mark-of-the-Web and pass Task-22 `-ClientSurface` on a Windows 10/11 x64 standard-user, medium-integrity interactive desktop: SmartScreen/publisher identity, Explorer/ShellExecute double-click, real native dialogs through agent-driven UI Automation, default-browser launch, installed stop/maintenance shortcuts, upgrade and uninstall. If publisher credentials are absent, record exactly `RELEASE BLOCKED: Windows Authenticode credentials unavailable`; if no eligible interactive session is available, record exactly `RELEASE BLOCKED: Windows 10/11 standard-user client-surface acceptance unavailable`. Windows Server CI does not satisfy this release claim.
- Apple Developer ID Application identity/team credentials and App Store Connect/notary credentials must be supplied through protected release secrets. If absent, record exactly `RELEASE BLOCKED: Apple Developer ID/notary credentials unavailable`; unsigned technical completion is not a signed release.
- The exact checksummed final stapled DMG must be downloaded through the intended browser/channel onto a clean, non-admin Apple Silicon macOS 14 user account. Before first open, the receipt must prove `com.apple.quarantine` exists on the DMG and propagates to both copied apps; it must prove the launched path is the installed `~/Applications/IZ Clinical Notes Analyzer/` path rather than App Translocation, then pass Gatekeeper, Utilities `Install/Upgrade for Me`, native dialogs, default-browser, Keychain prompt, stop, backup/restore, upgrade, and uninstall QA. If no macOS 14 Apple-Silicon host is available, record exactly `RELEASE BLOCKED: Apple Silicon macOS 14 lower-bound execution unavailable`; if no clean/rented/borrowed Mac is available, record exactly `RELEASE BLOCKED: clean Apple Silicon quarantine acceptance unavailable`.
- These external gates never become false green checks and do not block the Lane 1 automatable barrier or Lane 2 engineering measurements; each blocks only the affected RC/production distribution declaration.

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: TDD. Add characterization/failing boundary tests before each refactor, then implement until pytest, Vitest, Playwright, native PowerShell, native macOS shell, package scanners, and executable artifact smokes pass.
- Execution contract: the final planning handoff records the SHA-256 of this exact approved plan as `APPROVED_PLAN_SHA256` in immutable goal metadata outside the implementation branch. Before editing, set the fixed GitHub identity to `REPOSITORY=martyw1/IZ_clinical-notes-analyzer`, numeric REST/GraphQL database ID `REPOSITORY_ID=1172715348`, GraphQL node ID `REPOSITORY_NODE_ID=R_kgDOReY3VA`, and `GITHUB_REMOTE=origin`; verify the local `origin` URL is exactly the SSH or HTTPS URL for that repository, the GitHub API returns both exact typed IDs/default branch `main`, Actions is enabled, `gh` is authenticated with write access, and a nonce branch can be pushed, resolved to the expected SHA, and deleted. Never compare an API `id` field to the node ID or a `node_id` field to the numeric ID. Task 1 copies this plan byte-for-byte to `config/verification/approved-cross-platform-plan.md`, verifies both files against the external hash, and uses `render_plan_contract.py` to deterministically produce canonical JSON bytes for `cross-platform-plan-contract.json`, `lane1-task-graph.json`, and `lane2-scope.json`. The renderer must parse all 36 task headings, dependency rows, exact Commit file lists, outcome-specific subjects/deltas, the global Git object policy below, evidence IDs, and enumerated directory entries; it fails on an unparsed task/field rather than defaulting. `$ATTEMPT_DIR/execution-contract.json` records the external plan hash, tracked-plan Git blob/content hashes, rendered-policy hashes, both typed repository IDs, base/branch, and UTC time. Task 1 commits the approved-plan copy, renderer, policies, validator, and tests together; Task 26 fetches the frozen Task-1 renderer/plan copy from GitHub, rerenders into a private temp directory, and requires byte identity with the Task-1 Git policy blobs. Later tasks may read but never replace or broaden them. F1/F4 repeat the external-plan-hash, tracked-plan-copy, renderer, contract, graph, and scope checks. Remote workflows consume only the tracked approved-plan copy and rendered machine contracts, never ignored `.omo` content.
- Git object policy: every Task 1-36 Commit path denotes one regular Git blob and no task may delete or rename a listed path. A path already tracked at base `8c1edc460c2af354f74417cf27d26abaf72ccc70` must preserve its base object type and mode exactly. A new path ending in `.sh` must be blob mode `100755`; every other new path must be blob mode `100644`. Source-tree symlinks (`120000`), submodules/gitlinks (`160000`), directories represented as placeholders, hard-link aliases, case/NFC aliases, and any unlisted rename/copy/delete are forbidden. Generated package-internal framework links and the DMG `Applications` link are artifact-manifest entries governed by Task 6, never tracked Git links. Task 1 renders these literal rules once; later validators compare raw `git diff-tree --raw -z`/`git ls-tree -rz` objects and never infer a mode from the local filesystem, `core.filemode`, extension beyond this rule, or platform defaults.
- Commit-chain contract: immediately before and after each Task 1-25 commit, the parent executor writes exclusive, private `$ATTEMPT_DIR/task-N/start.json` and `post.json` receipts containing plan hash, pre/post full commit/tree SHA, the pre-anchored outcome-specific Conventional Commit subject, exact changed path/type/mode/directory-entry list, evidence hashes, and clean-status bytes. Each task is exactly one commit; the next task's `pre_sha` must equal the prior `post_sha`. Task 1's post receipt additionally proves all three committed policy blobs are byte-identical to the pre-Task-1 hashes. Task 26 recomputes the entire chain from Git objects against those immutable Task-1 blobs; local receipts are corroborating evidence and can never expand an allowed path.
- Evidence directory: when `omo ulw-loop status --json` is available, set `ATTEMPT_DIR` to its `currentAttemptDir`; otherwise set it to `.omo/evidence`. Every invocation creates the directory, captures stdout/stderr plus exit status, and writes machine-readable JSON where the todo requires it; lack of the optional `omo` command is never an application/test failure.
- Test data: synthetic-only isolated directories created below the OS temp root. Never point tests at a real `%LOCALAPPDATA%` or `~/Library/Application Support` profile. Each scenario asserts its resolved cleanup target remains under the test temp root before removing it.
- Native proof: Windows package assertions run the built `.exe` from the staged release folder; macOS assertions run the built ARM64 `.app`/Utilities `.app` from the mounted DMG and an installed path with spaces. Source/script inspection may supplement but can never satisfy a packaging or lifecycle criterion.
- Barrier receipt: Task 26's push-triggered authoritative workflow reruns every Task 21-25 validation at its exact target SHA, directly attests canonical `lane1-barrier.json`, and records both typed repository IDs plus workflow blob/action-pin/run/attempt/job/artifact/runner identities and trusted GitHub timestamps. Before parsing that subject, local collection requires the independently retained Task-26 source anchor and post-dispatch trigger anchor, then runs `gh attestation verify` with exact `--repo`, `--signer-workflow`, `--signer-digest`, `--source-digest`, and `--source-ref` values; it validates certificate identity/timestamp plus the subject predicate, fetches the verifier blob through the GitHub contents API through the retained exact-SHA Task-26 anchor tag, checks the independently anchored verifier SHA, and only then atomically publishes byte-identical `$ATTEMPT_DIR/lane1-barrier.json`. Every Lane-2 task repeats that certificate-bound verification and writes `$ATTEMPT_DIR/task-N/barrier-start.json` before work and `$ATTEMPT_DIR/task-N/barrier-post.json` after its commit; every harness/dispatcher requires the start receipt, and the frozen verifier checks the exact outcome-specific subject/delta including file type/mode, directory entries, symlink/submodule, rename, case, and Unicode aliases. Temporary request/source/trigger refs are removed by Task 26, but the one recorded `refs/tags/codex-barrier/task26-<40-lowercase-hex-SHA>` remains immutable and resolves to Task 26 through Tasks 27-36 and F1-F4; the final-wave orchestrator deletes and independently confirms absence only after all four reviewers approve.
- Performance statistics: emit raw paired-run JSON and a deterministic summary containing fixture ID/hash, commit and clean tree hash (`dirty=false`), workflow run/attempt/job/runner IDs, artifact surface plus independent control/candidate artifact IDs/digests/hashes, OS/arch, Python `3.12.10`, PyInstaller `6.16.0`, Node `20.19.4`, Playwright Chromium revision/binary hash, lock-closure hash, timestamps, all samples, arithmetic median (average the middle two for even `n`, no pre-decision rounding), nearest-rank p95 at sorted rank `ceil(0.95*n)`, paired deltas/sign-test result, query/request counts, memory, and artifact bytes. Lower is better for latency/query/memory/bytes; regressions are `(candidate-control)/control`. Functional/security/cleanup failures remain zero; response/order/auth/audit/resource hashes match exactly. Schema hashes match except the one explicitly declared Task-32 migration-11 transformation, whose registry/checksum/columns/triggers/counts must match the fixed contract. A primary cell uses its median only as the improvement metric, but its p95 is independently protected and may regress at most 5%; every other protected median, p95, and scalar has the same 5% ceiling. Never discard an outlier; absent/failed/incomparable evidence is `ERROR`.
- Repetition protocol: source cells use 7 recorded fresh-process pairs; packaged cells use 10 `cold` and 10 `warm` pairs; endpoint/browser cells use 3 untimed warm-ups and 20 recorded pairs. Candidate order is the first `2N` symbols of repeated `ABBA` (`A=control`, `B=candidate`), so seven pairs are exactly `ABBAABBAABBAAB` and ten pairs are `ABBAABBAABBAABBAABBA`; pair the nth occurrence of A with the nth occurrence of B. Fixture/cell traversal is the literal order committed in `cross-platform-v1.json`. No OS cache is flushed and Defender/Spotlight is not disabled; their state is recorded, no sample is discarded for cache/noise, and a fixed 2-second stopped-process interval separates samples. Source `fresh` clones the canonical fixture into a new profile for each timed fresh process. Source `warm-profile` performs one untimed start/readiness/authenticated-stop against a canonical fixture, snapshots the initialized profile only after all owned processes exit and the lease is unheld, and clones that identical snapshot for each timed new process so recorded samples never accumulate mutations. Windows package `cold` creates a fresh validated release extraction, per-user install directory, profile, and unique empty task-owned `TEMP`/`TMP` root, then records the first process launch; a onefile `_MEI*` extraction may exist only below that root and is identity-checked/removed with that sample, while onedir has no extraction cache. Windows `warm` reuses the same validated installed bytes and initialized profile only after one untimed launch/readiness/authenticated-stop, but still starts a new process and uses a fresh empty task-owned `TEMP`/`TMP` root; it never pretends onefile extraction persists. macOS `cold` creates a fresh verified read-only DMG mount, atomically copies both apps to a fresh per-user install, and uses a fresh profile for the first timed process. macOS `warm` reuses that verified app copy and initialized profile after one untimed launch/readiness/authenticated-stop, then starts a new process; neither mode clears global dyld/OS caches. Every timed browser view uses a fresh context with pinned bundled Chromium. Any preexisting extraction/install/profile/process or cleanup outside the task-owned roots is `ERROR`.
- Adversarial classes required across the plan: `dirty_worktree`, `stale_state`, `startup_race`, `pid_reuse`, `other_data_dir`, `unrelated_port`, `wrong_control_token`, `csrf_simple_request`, `path_case_symlink`, `bundle_write`, `backup_token_leak`, `archive_traversal`, `tamper_wrong_key`, `rollback_failure`, `forbidden_release_canary`, `misleading_success_output`, `wrong_architecture`, `missing_release_secret`, `cold_warm_noise`, `semantic_drift`, and `cleanup_escape`.
- External RC evidence is stored separately from engineering receipts and must name the exact artifact SHA-256, Apple team/signing identity metadata without secrets, notarization submission/log ID, staple verification, clean-Mac OS/hardware, and redacted Finder/Gatekeeper results.

## Execution strategy
### Parallel execution waves
> Target 5-8 todos where dependencies permit. The underfilled waves below are mandatory native joins, evidence barriers, or intentionally serial performance decisions; merging them would violate a direct dependency or contaminate a baseline.

- Wave 1: Task 1 alone establishes and commits the independently pre-anchored immutable graph/scope/contracts plus behavior characterization; no other task may start before its post receipt passes.
- Wave 2: Tasks 2, 5, and 6 in parallel after Task 1 (resource, worker, and release-manifest foundations).
- Wave 3: Tasks 3, 4, and 7 after Tasks 2/6 (factory, ownership, and extension of the Task-1 native transport for preflight/later native modes).
- Wave 4: Tasks 8, 9, and 10 after Wave 3 (two native adapters plus backup core).
- Wave 5: Tasks 11, 12, 13, and 14 after Wave 4 (native key adapters, maintenance core, and controller join).
- Wave 6: Tasks 15 and 16 after Task 14 (native launch/stop surfaces).
- Wave 7: Tasks 17 and 18 (native maintenance surfaces).
- Wave 8: Tasks 19 and 20 (native release builders executed through Task 7's push transport).
- Wave 9: Task 21 (full same-commit CI/native artifact workflow join).
- Wave 10: Task 22 (exact Windows artifact lifecycle QA).
- Wave 11: Task 23 after Task 22 (exact macOS artifact lifecycle QA; serializes the shared workflow edit).
- Wave 12: Task 24 (optional release signing/notary plumbing against both exact artifacts).
- Wave 13: Task 25 after Task 24 (receipt-bearing docs and release-state truth).
- Wave 14: Task 26, the non-bypassable Lane 1 barrier.
- Wave 15: Task 27, the post-barrier measurement foundation; no benchmark or optimization starts before it commits and passes.
- Waves 16-18: Tasks 28, 29, and 30 serially; each commits and emits a post-gate receipt before the next task, avoiding shared-worktree/ref ambiguity.
- Wave 19: Task 31 (commit the final baseline harness set, then rebuild and measure every source/package/API/browser baseline at this one control SHA).
- Waves 20-24: Tasks 32, 33, 34, 35, 36 in strict serial order; each candidate recaptures its immediate control in the same runner allocation.

Critical path: Task 2 -> Task 4 -> Task 10 -> Task 14 -> Task 15 -> Task 17 -> Task 19 -> Task 21 -> Task 22 -> Task 23 -> Task 24 -> Task 25 -> Task 26 -> Task 27 -> Task 28 -> Task 29 -> Task 30 -> Task 31 -> Task 32 -> Task 33 -> Task 34 -> Task 35 -> Task 36.

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1 | none | 2, 5-6, 10, 14, 21, 25-26 | none |
| 2 | 1 | 3-4, 7-9, 13-14 | 5-6 |
| 3 | 2 | 14 | 4, 7 |
| 4 | 2 | 8-10, 13-14 | 3, 7 |
| 5 | 1 | 14 | 2, 6 |
| 6 | 1 | 7, 13, 19-21 | 2, 5 |
| 7 | 2, 6 | 8-14 | 3-4 |
| 8 | 2, 4, 7 | 11, 14-15, 21 | 9-10, 13 |
| 9 | 2, 4, 7 | 12, 14, 16, 21 | 8, 10, 13 |
| 10 | 1, 4, 7 | 11-14 | 8-9 |
| 11 | 7-8, 10 | 17 | 12, 14 |
| 12 | 7, 9-10 | 18 | 11, 14 |
| 13 | 2, 4, 6-7, 10 | 17-18 | 11-12, 14 |
| 14 | 1-5, 7-10 | 15-16, 21 | 11-12 |
| 15 | 8, 14 | 17, 19, 22, 25 | 16 |
| 16 | 9, 14 | 18, 20, 23, 25 | 15 |
| 17 | 11, 13, 15 | 19, 22, 25 | 18 |
| 18 | 12-13, 16 | 20, 23, 25 | 17 |
| 19 | 6, 15, 17 | 21-22, 24-25 | 20 |
| 20 | 6, 16, 18 | 21, 23-25 | 19 |
| 21 | 1, 6, 8-9, 14, 19-20 | 22-24, 26 | none |
| 22 | 15, 17, 19, 21 | 23-26 | none |
| 23 | 16, 18, 20-22 | 24-26 | none |
| 24 | 19-23 | 25-26 | none |
| 25 | 1, 15-20, 22-24 | 26 | none |
| 26 | 1, 21-25 | 27-36 | none |
| 27 | 26 | 28, 31-32 | none |
| 28 | 26-27 | 29, 31-32 | none |
| 29 | 26, 28 | 30-32 | none |
| 30 | 26, 29 | 31-32, 34 | none |
| 31 | 26-30 | 32, 35-36 | none |
| 32 | 26-31 | 33, 36 | none |
| 33 | 26, 32 | 34, 36 | none |
| 34 | 26, 30, 33 | 35-36 | none |
| 35 | 26, 31, 34 | 36 | none |
| 36 | 26, 31-35 | F1-F4 | none |
| F1 | 36 | final handoff | F2-F4 |
| F2 | 36 | final handoff | F1, F3-F4 |
| F3 | 36 | final handoff | F1-F2, F4 |
| F4 | 36 | final handoff | F1-F3 |

## Todos
> Implementation + Test = ONE todo. Never separate.
- [ ] 1. Lock portable application behavior with synthetic characterization tests

  What to do:
  - Literal first action: obtain `APPROVED_PLAN_SHA256` from immutable planning-handoff metadata, never from this file, the implementation branch, or a task receipt. Set `REPOSITORY=martyw1/IZ_clinical-notes-analyzer`, numeric `REPOSITORY_ID=1172715348`, `REPOSITORY_NODE_ID=R_kgDOReY3VA`, and `GITHUB_REMOTE=origin`. Verify the current plan bytes, clean base commit, remote URL, API `id` plus `node_id`/default branch/Actions state, authenticated write permission, and a push-resolve-delete nonce ref before editing. If any fixed typed identity/hash/permission differs, stop with `BLOCKED: canonical GitHub execution identity unavailable`; never rewrite a remote or substitute a fork silently.
  - Add `config/verification/approved-cross-platform-plan.md` as a byte-identical copy of the approved `.omo` plan, plus `scripts/verification/render_plan_contract.py`. The renderer accepts exactly `--approved-plan`, `--approved-plan-sha256`, `--repository`, `--repository-id`, `--base-ref`, and `--output-dir`; it hashes before parsing and deterministically emits canonical `config/verification/cross-platform-plan-contract.json`, `config/verification/lane1-task-graph.json`, and `config/performance/lane2-scope.json`. It must consume every Task1-36 heading, dependency-matrix row, Parallelization edge, exact Commit subject/file list, outcome-specific delta, Git type/mode/rename rule, evidence ID, and enumerated directory entry; any unparsed, duplicate, contradictory, wildcard, prefix, or inferred field is fatal. The Lane-2 scope has one subject/delta for Tasks27-31/36; three disjoint `NOT_MATERIAL|REJECTED|ACCEPTED` alternatives for Tasks32,34,35; and exactly two `REJECTED|ACCEPTED` alternatives for always-measured Task33. A non-accepted alternative contains only its named decision document; `ACCEPTED` contains that document plus exact task-listed product/test files.
  - Add `scripts/verification/verify_plan_contract.py` and `backend/tests/test_cross_platform_plan_contract.py`. The validator accepts exactly `--execution-contract`, `--approved-plan`, `--approved-plan-sha256`, `--renderer`, `--plan-contract`, `--task-graph`, `--lane2-scope`, `--git-ref`, and `--output`; it independently hashes the external anchor and tracked approved-plan bytes, reruns the renderer into a private temp directory, requires byte identity with all three committed policies, verifies schemas/graph inverse edges/path uniqueness/outcome subjects/directory inventories plus the literal global Git object policy, rejects deletion/rename/copy, wrong type/mode, aliases/submodules/unlisted links, and proves the Task-1 Git blobs match the externally anchored plan. It never derives or expands policy from the implementation diff or local executable bits.
  - Add exactly `backend/tests/fixtures/desktop_contract/routes.json`, `safe-api-shapes.json`, and `resource-hashes.json`, containing synthetic, secret-free expected route metadata and representative safe shapes for readiness/version, bootstrap auth, RBAC denial, dashboard, patient roster, treatment-plan roster, deterministic evaluation, and live-Alleva-disabled behavior.
  - Add `backend/tests/test_desktop_behavior_characterization.py` that creates an isolated SQLite profile, drives the current ASGI app through `TestClient`, and asserts route/middleware uniqueness, HTTP status/body contracts, audit event counts, canonical 42-checklist length/order, rule version, encryption round-trip, and zero live-network calls.
  - Record a machine-readable contract fingerprint from normalized route tuples and safe response shapes; exclude timestamps, hashes that contain runtime randomness, access tokens, password hashes, encrypted patient bytes, filenames, local paths, and audit-chain values.
  - In this first commit add the bounded native execution transport needed before Tasks 2-7: `.github/workflows/native-desktop-bootstrap.yml`, `scripts/ci/verify-github-preflight.py`, `scripts/ci/dispatch-native-bootstrap.py`, `scripts/ci/write-native-bootstrap-receipt.py`, `backend/tests/test_github_execution_identity.py`, and `backend/tests/test_native_bootstrap_receipt.py`. The preflight accepts exactly `--repository`, `--repository-id`, `--repository-node-id`, `--remote`, `--expected-head`, and `--receipt`; it rejects a local-path/wrong remote, compares API `id` and `node_id` to the matching typed inputs, verifies default branch/Actions/authz, performs one namespaced push-resolve-delete probe, and writes a private receipt only after deletion is independently confirmed. Dispatchers use the numeric ID argument and also compare the API node ID to the immutable Task-1 node-ID constant; every request/receipt records both without conflating them. The workflow runs only on `on.push.branches: ['codex-native/**']`, pins checkout/setup-python/upload/download to the full action SHAs later repeated in Task 21, installs Python `3.12.10`, the existing `backend/requirements-windows-local.txt`, and `pytest==9.0.3`, asserts Windows x64 or explicit `macos-15` arm64, and at the Task-1 commit exposes exactly the hardcoded cross-OS modes `contract`, `bootstrap`, `factory`, `control`, `jobs`, and `release-safety`; Task 7 is the sole later extension point and adds the adapter/maintenance/package modes before Tasks 8-20 invoke them. Each mode maps to the exact task-owned pytest module(s), never shell text; a requested mode whose files do not yet exist fails. `contract` has no forward-file dependency at Task 1.
  - `dispatch-native-bootstrap.py` accepts exactly `--commit`, `--repository`, `--repository-id`, `--remote`, `--mode`, `--output-dir`, and `--receipt`. It requires the passing preflight identity at call time, uses only the named remote, and in an isolated worktree publishes/verifies the full target SHA first, creates canonical `.ci/native-bootstrap-request.json` with repository ID, correlation ID, workflow path/blob, hardcoded mode, target SHA, request hash, and nonce, then publishes the trigger commit/ref last under `codex-native/<correlation>/trigger`. It selects only the push run matching repository ID/trigger SHA/correlation, downloads receipts by artifact ID/API digest, verifies target/workflow/action/runner/command/exit/cleanup fields, and deletes source/trigger refs and the worktree in `finally`. These bootstrap receipts are task-local engineering evidence only and can never satisfy Task 21-26 artifact/barrier contracts.
  - Keep existing tests authoritative. This task adds a refactor tripwire; it does not bless a currently failing contract or change application behavior.

  Must NOT do: Do not start another task before the external approved-plan hash, tracked plan copy, deterministic rerender, committed policy blobs, fixed GitHub repository/remote identity, and Task-1 `contract` native run all pass; do not derive policy from a later diff, use globs/prefixes, omit an outcome-specific subject, authorize `NOT_MATERIAL` for Task33, or permit the approved-plan/renderer/policy files in any Task2-36 delta. Do not rewrite a remote, substitute a repository/fork, let the bootstrap workflow accept arbitrary commands, use `workflow_dispatch`, select latest-by-branch, or claim packaged-artifact/barrier acceptance. Do not snapshot PHI-like names, credentials, ciphertext, local absolute paths, or volatile values; do not update a golden file merely because a later refactor changes output; do not call Alleva or any external endpoint.

  Parallelization: Can parallel: NO | Wave 1 trust bootstrap | Blocked by: none | Blocks: [2, 5, 6, 10, 14, 21, 25, 26]

  References:
  - Plan anchor: Verification strategy `Execution contract` and every task's `Parallelization`/`Commit` line - the exact graph and subjects to encode before implementation.
  - Git object contract: `git diff-tree --raw -z`, `git ls-tree -rz`, and `git cat-file` - authoritative path/type/mode/blob enumeration; never parse human-formatted `git diff`.
  - Pattern: `backend/tests/conftest.py` - isolated settings/database fixture style.
  - API: `backend/app/main.py:14-39` (`create_app`, module `app`) and `backend/app/v2/api/routes.py` - current application/route surface.
  - Security: `backend/tests/test_v2_auth_rbac.py` and `backend/tests/test_v2_alleva_contract_gate.py` - auth and live-sync gate assertions.
  - Rules: `config/checklists/treatment-plan-v1.json` and `backend/app/v2/services/rule_package.py` - deterministic resources that must remain unchanged.
  - Runtime: `backend/tests/test_v2_runtime_readiness.py:15` and `backend/tests/test_v2_operational_workflow.py:32-151` - safe readiness/dashboard/audit behavior.
  - Push-only transport rationale: Task 21 workflow contract and `https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#push`.

  Acceptance criteria:
  - Before the Task-1 commit, `APPROVED_PLAN_SHA256` from the immutable handoff equals `sha256sum .omo/plans/cross-platform-desktop-refactor.md`, and `python scripts/ci/verify-github-preflight.py --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --repository-node-id "$REPOSITORY_NODE_ID" --remote "$GITHUB_REMOTE" --expected-head "$(git rev-parse HEAD)" --receipt "$ATTEMPT_DIR/task-1/github-preflight.json"` exits 0 with API `id=1172715348`, `node_id=R_kgDOReY3VA`, Actions/write permission, exact nonce-ref SHA, and deletion confirmation.
  - After commit, `python scripts/verification/verify_plan_contract.py --execution-contract "$ATTEMPT_DIR/execution-contract.json" --approved-plan config/verification/approved-cross-platform-plan.md --approved-plan-sha256 "$APPROVED_PLAN_SHA256" --renderer scripts/verification/render_plan_contract.py --plan-contract config/verification/cross-platform-plan-contract.json --task-graph config/verification/lane1-task-graph.json --lane2-scope config/performance/lane2-scope.json --git-ref HEAD --output "$ATTEMPT_DIR/task-1/policy-validation.json"` exits 0 and proves the tracked plan is externally anchored, a private rerender is byte-identical, all 36 graph rows/outcome subjects/inverse edges are exact, Task33 has no `NOT_MATERIAL` alternative, and there are zero wildcard/directory-placeholder/alias entries.
  - `python -m pytest backend/tests/test_cross_platform_plan_contract.py backend/tests/test_github_execution_identity.py -q --junitxml="$ATTEMPT_DIR/task-1/policy-tests.xml"` exits 0, including mutations that swap numeric/node IDs, use a local-path remote or omit ref deletion, widen the Task-26 graph, add an unlisted nested file, change an existing mode/type, mark a new `.sh` `100644`, mark another new file `100755`, rename/delete a path, introduce a symlink/gitlink/case/NFC alias, omit a Task32/34/35 outcome subject, add Task33 `NOT_MATERIAL`, omit renderer input, mismatch the approved-plan hash, or self-amend policy.
  - `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode contract --output-dir "$ATTEMPT_DIR/task-1-native" --receipt "$ATTEMPT_DIR/task-1-native-collection.json"` exits 0; its Windows-x64 and macOS15-arm64 jobs run the characterization/auth/readiness/Alleva-gate/deterministic tests at the exact Task-1 SHA, and every receipt proves repository/target/workflow/request/action hashes plus cleanup.
  - The new test asserts exactly 42 canonical checklist steps, no duplicate `(path, method)` routes, live Alleva import disabled, and no socket/network transport outside `TestClient`/mock transports.
  - After the task commit, `git diff --exit-code "$(git rev-parse HEAD^)" HEAD -- backend/app frontend/src config/rules config/checklists` exits 0; exact Git-object enumeration proves the commit contains only the tracked approved-plan copy, three immutable policy JSON files, renderer/validator, GitHub preflight/native-bootstrap workflow and helpers, their four test modules, the characterization test, and three fixtures listed in the Commit line.

  QA scenarios:
  ```text
  Scenario: Portable contract fixture passes on both native runner architectures
    Tool:     GitHub Actions CLI
    Steps:    Run `set -euo pipefail; python scripts/ci/verify-github-preflight.py --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --repository-node-id "$REPOSITORY_NODE_ID" --remote "$GITHUB_REMOTE" --expected-head "$(git rev-parse HEAD)" --receipt "$ATTEMPT_DIR/task-1/github-preflight.json"; python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode contract --output-dir "$ATTEMPT_DIR/task-1-native" --receipt "$ATTEMPT_DIR/task-1-native-collection.json"`.
    Expected: Exit 0; exact Windows x64 and macOS arm64 push jobs run the complete Task-1 contract set, both JUnit files have zero failures/errors, receipts bind the exact target/workflow/request/action hashes, and `git ls-remote --heads origin 'codex-native/*'` contains no correlation ref.
    Evidence: $ATTEMPT_DIR/task-1-native-collection.json and $ATTEMPT_DIR/task-1-native/{windows,macos}/{receipt.json,junit.xml}

  Scenario: Semantic drift, arbitrary command, stale run, and misleading output fail closed
    Tool:     pytest
    Steps:    Run `PYTHONPATH=backend python -m pytest backend/tests/test_desktop_behavior_characterization.py::test_contract_rejects_duplicate_route backend/tests/test_desktop_behavior_characterization.py::test_contract_rejects_changed_safe_shape backend/tests/test_desktop_behavior_characterization.py::test_contract_does_not_trust_pass_text_when_assertion_fails backend/tests/test_native_bootstrap_receipt.py -q --junitxml="$ATTEMPT_DIR/task-1-contract-adversarial.xml"`.
    Expected: Exit 0 only because injected duplicate/shape/nonzero-exit/arbitrary-command/stale-correlation/cleanup mutations are rejected; no golden file or success receipt is written.
    Evidence: $ATTEMPT_DIR/task-1-contract-adversarial.xml

  Scenario: A retrospective scope expansion cannot be committed or accepted
    Tool:     bash
    Steps:    Run `set -euo pipefail; python -m pytest backend/tests/test_cross_platform_plan_contract.py backend/tests/test_github_execution_identity.py -q -k "repository_id_type or local_remote or undeleted_ref or approved_plan or renderer_omission or widened_graph or unlisted_nested or mode_type or new_shell_mode or rename_delete or symlink_gitlink or unicode_alias or missing_outcome_subject or task33_not_material or policy_self_amendment" --junitxml="$ATTEMPT_DIR/task-1-policy-adversarial.xml"`.
    Expected: Exit 0 only because every isolated forged graph/scope/subject mutation is rejected; the committed policy blobs and execution contract remain byte-identical.
    Evidence: $ATTEMPT_DIR/task-1-policy-adversarial.xml
  ```

  Adversarial classes: `semantic_drift`, `misleading_success_output`, `privacy_canary`, `dirty_worktree`, `path_case_symlink`.

  Cleanup: Tests use `tmp_path`; assert no file remains outside pytest temp roots and delete only those roots. GitHub preflight/native dispatchers delete only their exact nonce/source/trigger refs in `finally`, independently confirm absence, and retain a failed cleanup receipt rather than claiming PASS.

  Commit: YES | Message: `test(desktop): anchor portability contracts and behavior` | Files: [`config/verification/approved-cross-platform-plan.md`, `config/verification/cross-platform-plan-contract.json`, `config/verification/lane1-task-graph.json`, `config/performance/lane2-scope.json`, `scripts/verification/render_plan_contract.py`, `scripts/verification/verify_plan_contract.py`, `scripts/ci/verify-github-preflight.py`, `backend/tests/test_cross_platform_plan_contract.py`, `backend/tests/test_github_execution_identity.py`, `backend/tests/test_desktop_behavior_characterization.py`, `backend/tests/fixtures/desktop_contract/routes.json`, `backend/tests/fixtures/desktop_contract/safe-api-shapes.json`, `backend/tests/fixtures/desktop_contract/resource-hashes.json`, `.github/workflows/native-desktop-bootstrap.yml`, `scripts/ci/dispatch-native-bootstrap.py`, `scripts/ci/write-native-bootstrap-receipt.py`, `backend/tests/test_native_bootstrap_receipt.py`]

- [ ] 2. Split immutable resource discovery from mutable data bootstrap

  What to do:
  - Create stdlib-only `backend/app/core/platform_paths.py` with pure `resolve_resource_root(...)`, `resolve_local_app_data_dir(...)`, `canonical_data_dir_id(...)`, and `assert_mutable_path_outside_resources(...)`. `canonical_data_dir_id` accepts a bootstrap-safe volume-identity provider: Windows always case-folds; macOS case-folds only when the deepest existing ancestor's volume reports case-insensitive naming, and both revalidate native identity after creation. Windows default is `%LOCALAPPDATA%/IZ Clinical Notes Analyzer`; macOS default is `~/Library/Application Support/IZ Clinical Notes Analyzer`; `IZ_CNA_LOCAL_APP_DATA_DIR` wins but must be absolute in packaged mode so it never depends on CWD. Unsupported source/development environments retain the existing resolved repo-local test fallback only when not frozen.
  - Create `backend/app/desktop/ownership.py` with the stdlib-only `DataDirLease` protocol: canonical data-dir ID, `is_held_by_current_process()`, and idempotent `release()`. The protocol owns no native acquisition; Task 4 coordinates it and Tasks 8/9 implement it.
  - Create `backend/app/desktop/__init__.py` and stdlib-only `backend/app/desktop/bootstrap.py`. Define a bootstrap-safe `PrivateStorageProvider` protocol implemented natively by Tasks 8/9. `bootstrap_desktop(data_root, held_lease, private_storage)` never acquires a lock; it rejects a missing/unheld/mismatched lease, asks the provider to create and verify the directory with current-user-only access, and only then atomically creates `.env` using a restrictive descriptor from the first open (`CreateFileW` security attributes on Windows; `os.open(..., O_CREAT|O_EXCL, 0o600)` on macOS), fsyncs the file/parent, and sets `IZ_CNA_ENV_FILE`/`IZ_CNA_LOCAL_APP_DATA_DIR`. No credential byte may exist before directory/file privacy is established. Task 14 is the only normal-launch owner of `resolve -> acquire lease -> bootstrap`; Task 13 owns the analogous maintenance sequence after a confirmed stop.
  - Generated `.env` uses canonical names: `ENVIRONMENT=local-client`, `BACKEND_PORT`, `IZ_CNA_LOCAL_SQLITE_DB_PATH`, random 64-character `IZ_CNA_SECRET_KEY`, random 64-character `IZ_CNA_DATA_ENCRYPTION_KEY`, `IZ_CNA_BOOTSTRAP_ADMIN_USERNAME=admin`, random policy-valid `IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD`, localhost origins/hosts, `LLM_ENABLED=false`, `EMR_API_ENABLED=false`, and `ALLEVA_TREATMENT_PLAN_SYNC_ENABLED=false`. Preserve an existing safe `.env` byte-for-byte; fail closed on missing/unsafe required values rather than silently replacing encryption material.
  - Define configuration precedence explicitly. In packaged mode, the only ambient environment overrides accepted before bootstrap are `IZ_CNA_LOCAL_APP_DATA_DIR` and `IZ_CNA_PORT`; after bootstrap, the selected private `.env` is authoritative. Strip or ignore every other inherited IZ/application/configuration/credential variable before importing config, and emit only the safe reason code `desktop_ambient_configuration_ignored` with the variable name omitted. Source/developer mode retains its documented environment behavior. Test-only injection is constructor-based and absent from release bytecode/CLI surfaces.
  - Return a candidate credential object in memory only. After database startup, Task 14 displays it whenever the bootstrap admin still has `must_reset_password=true`; this makes a crash after env publication or admin creation recoverable without a second secret store. Stop displaying only after the existing password-reset flow succeeds. Never write a credential note, acknowledgement secret, or log the value.
  - Refactor `backend/app/core/config.py` so `RESOURCE_ROOT` and `Settings.local_app_data_dir` use the pure resolver and cannot both point to `_MEIPASS`. Update `backend/app/services/version.py`, `backend/app/v2/services/rule_package.py`, and `backend/app/v2/services/manual_file_criteria.py` to use `RESOURCE_ROOT`; leave a deprecated read-only `REPO_ROOT` alias only where source-checkout compatibility still requires it.
  - Add fresh-subprocess tests in `backend/tests/test_desktop_bootstrap.py`; subprocesses use a fake held lease and prove bootstrap occurs before configuration/database module presence in `sys.modules` and before the SQLite engine is constructed. Race the atomic env writer directly in two subprocesses; the real two-launch ownership race belongs to Task 14.

  Must NOT do: Do not acquire/release a lease inside bootstrap, import Pydantic/FastAPI/SQLAlchemy in `platform_paths.py` or before bootstrap completes, write secrets before restrictive directory/file security exists, overwrite existing secrets, expose generated credentials, or resolve mutable paths beneath resources/CWD in frozen mode.

  Parallelization: Can parallel: YES | Wave 2 | Blocked by: [1] | Blocks: [3, 4, 7, 8, 9, 13, 14]

  References:
  - Current paths: `backend/app/core/config.py:14-21,44-61,96-103,150-187` - frozen `REPO_ROOT`, import-time env load, unsafe non-Windows fallback, global settings.
  - Resource consumers: `backend/app/desktop_main.py:13-17`, `backend/app/services/version.py`, `backend/app/v2/services/rule_package.py`, `backend/app/v2/services/manual_file_criteria.py`.
  - Current bootstrap: `scripts/preflight-windows.ps1:145-177` - random secret and `.env` fields to preserve semantically.
  - Tests: `backend/tests/test_v2_production_config.py:188-309` - frozen-root, env precedence, and restricted-configuration patterns.

  Acceptance criteria:
  - Platform-unit tests assert the exact Windows/macOS/override roots and a distinct immutable resource root for frozen executions.
  - A fresh subprocess with a matching fake held lease and no `.env` first records a successful private-directory/private-file check, then creates one before importing config/db; two simultaneous atomic-writer subprocesses yield one valid file with identical secret values and no partial/temp file; an existing file's SHA-256 is unchanged.
  - Frozen-path tests assert zero writes under `_MEIPASS`, `.app/Contents`, mounted DMG, repo root, and CWD; rules, checklist, version, and frontend resource probes still resolve.
  - The generated file is `0600` on macOS; Windows ACL enforcement is completed by Task 8 and is not falsely claimed here.

  QA scenarios:
  ```text
  Scenario: Fresh bootstrap resolves both target platforms without early imports
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode bootstrap --output-dir "$ATTEMPT_DIR/task-2-native" --receipt "$ATTEMPT_DIR/task-2-native-collection.json"`.
    Expected: Exit 0; exact Windows x64 and macOS arm64 jobs confirm config/db absent before bootstrap, environment set afterward, platform path/permission assertions pass, all mutable files remain in synthetic OS-local roots, and nonce refs are deleted.
    Evidence: $ATTEMPT_DIR/task-2-native-collection.json and $ATTEMPT_DIR/task-2-native/{windows,macos}/{receipt.json,junit.xml,run.log}

  Scenario: Unsafe existing env and bundle-write attempt fail without mutation
    Tool:     pytest
    Steps:    Run `PYTHONPATH=backend python -m pytest backend/tests/test_desktop_bootstrap.py::test_bootstrap_rejects_unsafe_existing_env_without_replacement backend/tests/test_desktop_bootstrap.py::test_bootstrap_rejects_resource_descendant_data_root backend/tests/test_desktop_bootstrap.py::test_concurrent_bootstrap_is_atomic backend/tests/test_desktop_bootstrap.py::test_bootstrap_requires_matching_held_lease backend/tests/test_desktop_bootstrap.py::test_no_secret_bytes_written_before_private_storage backend/tests/test_desktop_bootstrap.py::test_pending_password_handoff_survives_crash -q --junitxml="$ATTEMPT_DIR/task-2-bootstrap-adversarial.xml"`.
    Expected: Each canary raises the documented safe configuration error, preserves original bytes, produces no database, writes no secret under permissive security, recovers the in-memory handoff after simulated crash, and leaves no temp file.
    Evidence: $ATTEMPT_DIR/task-2-bootstrap-adversarial.xml
  ```

  Adversarial classes: `startup_race`, `path_case_symlink`, `bundle_write`, `cleanup_escape`.

  Cleanup: Subprocess tests close handles, validate temp-root containment, and remove only their synthetic roots.

  Commit: YES | Message: `refactor(desktop): separate resources from local bootstrap` | Files: [`backend/app/core/platform_paths.py`, `backend/app/desktop/__init__.py`, `backend/app/desktop/ownership.py`, `backend/app/desktop/bootstrap.py`, `backend/app/core/config.py`, `backend/app/services/version.py`, `backend/app/v2/services/rule_package.py`, `backend/app/v2/services/manual_file_criteria.py`, `backend/tests/test_desktop_bootstrap.py`, `backend/tests/test_v2_production_config.py`]

- [ ] 3. Make application construction side-effect-free and initialize exactly once

  What to do:
  - Add `backend/app/application.py` containing `create_application()` and an async lifespan. Factory construction registers middleware/routes and performs no directory creation, database initialization, reevaluation, or startup audit write. Lifespan startup performs required directory creation, `init_database()`, and one `app.start` audit; lifespan shutdown exposes hooks consumed by Task 14.
  - Add `backend/app/desktop_application.py` containing `create_desktop_application()` that calls the base factory once and mounts the packaged React/static/fallback routes using `RESOURCE_ROOT` without constructing a second base app.
  - Reduce `backend/app/main.py` to compatibility exports `create_app = create_application` and `app = create_application()`. Reduce `backend/app/desktop_main.py` to `create_desktop_app = create_desktop_application` and `app = create_desktop_application()` for legacy ASGI consumers. Task 14 must import `desktop_application`, not the compatibility module, so it never triggers a second global app construction.
  - Preserve every public `create_app`/`app.main:app`/`app.desktop_main:app` entry point. Update `scripts/test-local-app-stack.ps1` only where its source smoke must enter the new lifespan and update `backend/tests/test_v2_production_config.py` only where its desktop runtime invocation assertion changes. Add `backend/tests/test_application_factory.py` with spies around init/migration/reevaluation/audit and route fingerprint comparison to Task 1.

  Must NOT do: Do not alter route paths, models, response shapes, auth/RBAC, audit fields, rules, DB schema, or frontend; do not move initialization into module import or factory construction; do not count this correctness fix again as a Lane 2 optimization.

  Parallelization: Can parallel: YES | Wave 3 | Blocked by: [2] | Blocks: [14]

  References:
  - Duplicate path: `backend/app/main.py:14-39` and `backend/app/desktop_main.py:9-10,74-75` - importing `app.main` constructs once and desktop constructs again.
  - DB work: `backend/app/v2/db.py:36-65` - migrations, interrupted-job marking, facility setup, and startup reevaluation.
  - Compatibility: `scripts/test-local-app-stack.ps1:148` and `backend/tests/test_v2_auth_rbac.py` - existing ASGI/factory consumers.
  - Static app: `backend/app/desktop_main.py:13-71` - asset and fallback route behavior to move intact.

  Acceptance criteria:
  - Importing `app.application` and calling `create_application()` twice produces no SQLite file, migration, reevaluation, or `app.start` event.
  - Entering one desktop application's lifespan invokes `init_database`, startup reevaluation through it, and `app.start` exactly once; route/middleware fingerprints equal Task 1 and contain no duplicates.
  - `app.main:app` and `app.desktop_main:app` remain importable and existing backend/source smoke tests pass.

  QA scenarios:
  ```text
  Scenario: Desktop lifespan initializes one app exactly once
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode factory --output-dir "$ATTEMPT_DIR/task-3-native" --receipt "$ATTEMPT_DIR/task-3-native-collection.json"`.
    Expected: Exit 0 on Windows x64 and macOS arm64; spies report factory_constructed=1, lifespan_started=1, init_database=1, app_start_audit=1, and no duplicate routes; receipts bind exact target/workflow hashes and cleanup.
    Evidence: $ATTEMPT_DIR/task-3-native-collection.json and $ATTEMPT_DIR/task-3-native/{windows,macos}/{receipt.json,junit.xml}

  Scenario: Import/factory-only paths cannot initialize storage
    Tool:     pytest
    Steps:    Run `PYTHONPATH=backend python -m pytest backend/tests/test_application_factory.py::test_factory_import_and_construction_have_no_persistence_side_effects -q --junitxml="$ATTEMPT_DIR/task-3-factory-adversarial.xml"`.
    Expected: Subprocess exits 0 and asserts the root/database/audit log do not exist until lifespan entry.
    Evidence: $ATTEMPT_DIR/task-3-factory-adversarial.xml
  ```

  Adversarial classes: `stale_state`, `semantic_drift`, `misleading_success_output`.

  Cleanup: Test lifespans close clients/engines and remove only `tmp_path` profiles.

  Commit: YES | Message: `refactor(app): initialize one desktop application in lifespan` | Files: [`backend/app/application.py`, `backend/app/desktop_application.py`, `backend/app/main.py`, `backend/app/desktop_main.py`, `backend/tests/test_application_factory.py`, `backend/tests/test_v2_production_config.py`, `scripts/test-local-app-stack.ps1`]

- [ ] 4. Define secure runtime state, ownership, and desktop-control primitives

  What to do:
  - Add `backend/app/desktop/runtime_state.py` with versioned `DesktopRuntimeState`, atomic `runtime/desktop-state.json` read/write/remove, canonical data-dir ID, run ID, 256-bit URL-safe token, PID, process creation time in UTC/epoch form, normalized executable/bundle path, port, start time, and readiness. Reject unknown schema versions, invalid permissions, symlinks, wrong data-dir IDs, and files outside the runtime directory.
  - Add `backend/app/desktop/instance_lock.py` using Task2's `DataDirLease`. `InstanceCoordinator.acquire(data_root)` is the sole acquisition boundary used by Task14/13; bootstrap never acquires. The native lock lives outside the deletable data root and is keyed by `sha256(canonical_data_dir_id)`: Windows opens `%LOCALAPPDATA%/R3 Recovery Services/IZ CNA Locks/<hash>.lock` with `CreateFileW(OPEN_ALWAYS, dwShareMode=0)` and a current-user/SYSTEM/Administrators DACL. macOS first-creates `~/Library/Application Support/R3 Recovery Services/IZ CNA Locks/<hash>.lock` with `os.open(O_CREAT|O_EXCL|O_RDWR|O_NOFOLLOW|O_CLOEXEC, 0o600)`, writes/fsyncs a nonsecret schema/data-dir ID, sets owner-settable `UF_IMMUTABLE`, closes it, then every owner reopens it `O_RDONLY|O_NOFOLLOW|O_CLOEXEC`, rejects wrong EUID/mode/extended ACL/cleared flag, acquires `flock(LOCK_EX|LOCK_NB)`, and compares `fstat(fd)` with `lstat(path)` device/inode before use. The flag/read-only FD reduce accidental cooperating-app replacement but are not a same-EUID security boundary: a hostile process with the same EUID can clear the flag and replace the inode. Both platforms provide handle-lifetime exclusion between cooperating application instances; the persistent file is never unlinked during normal cleanup. Hold the same lease object without reacquisition through bootstrap/preflight/runtime or maintenance commit/rollback.
  - Define lease handoff as duplicate/inherit of the exact open file handle/FD plus a nonce-bound `adopted` handshake. Windows uses `DuplicateHandle`/an explicit inherited-handle list; macOS uses an inherited non-`CLOEXEC` FD passed only to the fixed child. The parent retains its handle until the child proves the canonical data-dir ID, lock-file native identity, handle identity, and nonce, then closes its duplicate; exclusion remains continuously held until the child finishes. Owner crash closes its handles automatically without deleting the lock file.
  - Lock semantics: one owner per canonical data dir; second launch polls authenticated status for up to 30 seconds; a live-not-ready owner is never evicted; an acquired lease permits stale-state removal only after process-identity failure. Complete uninstall can delete the data root while retaining the outside-root lease, then release it after the target no longer exists. Re-open tests prove the persistent file is unheld, never absent.
  - On macOS, call `validate_native_identity()` before every runtime-state write/removal, status/stop response, and maintenance mutation, plus from a one-second controller watchdog. A cleared flag or `lstat`/`fstat` device/inode mismatch rejects new work, persists only the safe in-memory reason when possible, requests cooperative shutdown, and never signals another process. The supported guarantee is correct exclusion among cooperating app/Utilities instances; resistance to a malicious same-EUID process is explicitly out of scope because it would require a privileged/system-owned broker and violate no-admin scope.
  - Add `backend/app/desktop/process_identity.py` defining `ProcessIdentityProvider` and exact match rules for PID + creation time + executable/bundle path. Native implementations may use only documented OS APIs and must not fall back to process name or port.
  - Add `backend/app/desktop/control.py` implementing desktop-only ASGI middleware. Accept only loopback `POST /_desktop/control/status` and `POST /_desktop/control/stop`, Host for the active local port, `Content-Type: application/json`, body `{}` no larger than 1 KiB, `X-IZ-Desktop-Control` token compared with `hmac.compare_digest`, and `X-IZ-Data-Dir-ID`. Stop returns `202` after setting the injected shutdown request. The client uses one monotonic 30-second total budget: authenticated status polling through second 20; at or after second 20, only after complete process-identity revalidation, Windows may call `TerminateProcess`, while macOS sends `SIGTERM`, waits/revalidates, and may send `SIGKILL` at or after second 25; both must confirm owner exit by second 30. Return safe 400/401/403/409 errors. Never register these paths in the business router or include them in OpenAPI.
  - Add `request_maintenance_lease(data_root, operation)` to the coordinator: authenticate/POST stop when an owner exists, wait for verified process exit, acquire the same lease, revalidate canonical root and stale state, and retain the lease through backup/restore/uninstall. If ownership cannot be obtained within 30 seconds, return `desktop_maintenance_owner_timeout`; never operate unlocked.
  - Add `backend/tests/test_desktop_runtime_state.py` and `backend/tests/test_desktop_control.py` with fake process/lock providers plus real loopback ASGI calls.

  Must NOT do: Do not place the token in URL/body/log/audit/browser storage; do not trust PID, port, name, or state file alone; do not break a live lock; do not add a business API route that collides with route classification; do not describe `UF_IMMUTABLE`, mode bits, ACLs, or `flock` as protection from a hostile process already running under the same macOS EUID.

  Parallelization: Can parallel: YES | Wave 3 | Blocked by: [2] | Blocks: [8, 9, 10, 13, 14]

  References:
  - Current runtime: `backend/app/desktop_runtime.py:8-30` - fixed host/port and no ownership/control.
  - Current forced discovery: `scripts/stop-windows-local.ps1:49-240,261-292` - port/process-name heuristics to retire for packaged runtime.
  - Route guard: `backend/app/v2/route_registry.py:10-122` - reason control stays middleware-only.
  - Existing stop adversary: `scripts/test-windows-stop.ps1:78-102` - unrelated listener survival pattern.

  Acceptance criteria:
  - State round-trips only with correct data-dir identity/permissions; corrupt, symlinked, cross-dir, stale, and PID-reuse-like states fail closed without touching a live process.
  - Missing/wrong/cross-dir tokens, non-loopback clients, wrong Host, GET/simple-form requests, oversized bodies, and status/stop replay from an old run receive safe denial; correct status succeeds and correct stop signals only the injected coordinator.
  - Route-classification tests pass unchanged and business OpenAPI/route fingerprints contain no control path.
  - Provider-neutral lease/controller tests prove one acquisition/one release, no bootstrap reacquisition, the outside-data-root path contract, gap-free duplicate-handle/FD handoff protocol, the exact 0/20/25/30-second stop-client state machine, maintenance retention through data-root deletion, persistent-but-unheld lock-file contract, and no unlocked backup/restore/uninstall callback. Tasks 8/9 own the real Windows/macOS handle, DACL/mode/flag/inode and native-process assertions; Task 4 cannot pass by pretending its fake providers are native proof.

  QA scenarios:
  ```text
  Scenario: Authenticated loopback control targets one synthetic runtime
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode control --output-dir "$ATTEMPT_DIR/task-4-native" --receipt "$ATTEMPT_DIR/task-4-native-collection.json"`.
    Expected: Exit 0 on Windows x64 and macOS arm64; valid status returns matching run/data IDs, valid stop signals once, token text is absent, fake-provider contracts agree, and receipts prove cleanup.
    Evidence: $ATTEMPT_DIR/task-4-native-collection.json and $ATTEMPT_DIR/task-4-native/{windows,macos}/{receipt.json,junit.xml}

  Scenario: Decoy, stale, cross-dir, and CSRF-like requests are harmless
    Tool:     pytest
    Steps:    Run `PYTHONPATH=backend python -m pytest backend/tests/test_desktop_runtime_state.py backend/tests/test_desktop_control.py -k "wrong_token or cross_data_dir or stale or pid_reuse or simple_request or unrelated_listener or maintenance_owner_timeout or lease_outside_data_root or inherited_handoff or persistent_lock_file or unicode_case_alias" -q --junitxml="$ATTEMPT_DIR/task-4-control-adversarial.xml"`.
    Expected: All provider-neutral attacks are rejected, decoy/listener remains alive, modeled handoff has no gap, equivalent path spellings map per the injected volume policy, persistent-lock contract remains unheld after cleanup, and middleware logs only safe reason codes; real clear/replace-inode behavior remains mandatory in Task 9.
    Evidence: $ATTEMPT_DIR/task-4-control-adversarial.xml
  ```

  Adversarial classes: `stale_state`, `pid_reuse`, `wrong_control_token`, `csrf_simple_request`, `other_data_dir`, `unrelated_port`, `same_euid_tamper`.

  Cleanup: Close test servers/listeners, verify decoy liveness before terminating the test-owned decoy, then delete only synthetic runtime roots.

  Commit: YES | Message: `feat(desktop): secure runtime ownership and control state` | Files: [`backend/app/desktop/runtime_state.py`, `backend/app/desktop/instance_lock.py`, `backend/app/desktop/process_identity.py`, `backend/app/desktop/control.py`, `backend/tests/test_desktop_runtime_state.py`, `backend/tests/test_desktop_control.py`]

- [ ] 5. Track, cancel, drain, and persist every background worker

  What to do:
  - Add `WorkerRegistry` in `backend/app/v2/services/jobs.py`. All diagnostic, approved treatment-plan sync, and roster-pull outer threads are created through one `_start_worker(...)` path, retained by job ID under the existing lock, and removed only in a worker `finally` block. Refactor `backend/app/v2/services/alleva_sync.py:490-496` so every `ThreadPoolExecutor` future and executor is registered under its outer job, shares the same cancellation event, and is fenced from new submission after shutdown.
  - Add `accepting_jobs` state. Every create/resume method rejects after shutdown begins with HTTP/service error `desktop_shutdown_in_progress`; existing jobs remain queryable/cancellable.
  - Add `request_shutdown()` and `drain(timeout_seconds=15.0)`: atomically stop admissions and nested submissions, mark cancellation requested in memory/database/sync ledger, cancel queued futures, request running-fetch cancellation, and join every registered future/thread against one shared monotonic deadline. Return `DrainResult(cooperative, survivors)`; persist completed cancellations as `cancelled` and survivors as `stale_or_interrupted` with a safe timestamp/reason. Threads remain daemonized only so Task 14's terminal-process path can end a noncooperative call; this task never reports them drained.
  - Make `_mark_interrupted_jobs_stale` in `backend/app/v2/db.py` idempotent with the same terminal state on next startup. Expose `reset_for_test_or_new_process()` only in test construction, not as a production endpoint.
  - Add `backend/tests/test_desktop_job_shutdown.py` covering all three outer worker kinds, the nested detail executor/futures, admission/submission rejection, cooperative cancellation, a deterministic noncooperative nested fetch, one shared 15-second budget via an injectable clock, restart persistence, and a late-database-write sentinel consumed by Task 14's real-process test.

  Must NOT do: Do not leave an unregistered `ThreadPoolExecutor`/future, shorten production job semantics, lose audit/sync ledger records, wait 15 seconds per worker, log vendor material, mark a survivor completed, or let a survivor authorize SQLite teardown/lease release.

  Parallelization: Can parallel: YES | Wave 2 | Blocked by: [1] | Blocks: [14]

  References:
  - Starts: `backend/app/v2/services/jobs.py:127-254` (`ApiHarnessJobService`, daemon starts at 182, 222, 254).
  - Cancellation/workers: `backend/app/v2/services/jobs.py:290-313,366-566`.
  - Startup recovery: `backend/app/v2/db.py:95-100` (`_mark_interrupted_jobs_stale`).
  - Persistence tests: `backend/tests/test_v2_harness_job_persistence.py:83-176`.
  - Sync gate/audit: `backend/app/v2/api/alleva_sync_routes.py` and `backend/app/v2/services/alleva_contracts.py`.

  Acceptance criteria:
  - No direct `threading.Thread(...).start()` or unregistered executor submission remains outside `WorkerRegistry`; service introspection reports zero tracked work after cooperative drain.
  - New/resumed jobs and nested detail submissions are rejected after shutdown begins; all three job types observe cancellation and retain safe audit/persistence state.
  - The noncooperative nested fixture consumes one simulated 15.0-second total budget, returns `cooperative=false` with the exact survivor, becomes `stale_or_interrupted`, and is recognized idempotently on fresh app startup; it never produces a false zero-worker result.

  QA scenarios:
  ```text
  Scenario: Active diagnostic, roster, and sync workers drain cooperatively
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode jobs --output-dir "$ATTEMPT_DIR/task-5-native" --receipt "$ATTEMPT_DIR/task-5-native-collection.json"`.
    Expected: Exit 0 on Windows x64 and macOS arm64; each worker receives cancellation, terminal rows persist, tracked count reaches zero, no synthetic secret appears, and exact-target receipts prove cleanup.
    Evidence: $ATTEMPT_DIR/task-5-native-collection.json and $ATTEMPT_DIR/task-5-native/{windows,macos}/{receipt.json,junit.xml}

  Scenario: Noncooperative worker takes exactly the bounded fallback path
    Tool:     bash
    Steps:    Run `python -m pytest backend/tests/test_desktop_job_shutdown.py::test_drain_uses_one_fifteen_second_deadline_across_outer_and_nested_workers backend/tests/test_desktop_job_shutdown.py::test_noncooperative_nested_fetch_is_reported_as_survivor backend/tests/test_desktop_job_shutdown.py::test_interrupted_worker_is_terminal_after_restart -q --junitxml="$ATTEMPT_DIR/task-5-job-drain-timeout.xml"` using the current task's locked Python 3.12 environment.
    Expected: Drain returns after one 15-second budget, survivor state is `stale_or_interrupted`, no job is accepted during shutdown, and fresh startup does not duplicate the transition.
    Evidence: $ATTEMPT_DIR/task-5-job-drain-timeout.xml
  ```

  Adversarial classes: `stale_state`, `semantic_drift`, `misleading_success_output`.

  Cleanup: Every test calls drain in `finally`, closes DB sessions, then removes only its isolated profile.

  Commit: YES | Message: `refactor(jobs): drain tracked workers during desktop shutdown` | Files: [`backend/app/v2/services/jobs.py`, `backend/app/v2/services/alleva_sync.py`, `backend/app/v2/db.py`, `backend/tests/test_desktop_job_shutdown.py`, `backend/tests/test_v2_alleva_sync.py`, `backend/tests/test_v2_distinct_alleva_jobs.py`, `backend/tests/test_v2_harness_job_persistence.py`]

- [ ] 6. Replace broad release mirroring with a shared allowlist and fail-closed scanner

  What to do:
  - Add `config/release/desktop-package-manifest.json` as the single source of staging truth. Every row has exactly `platform`, `profile`, `source`, `destination`, `kind` (`static`, `generated`, `pyinstaller-toc`, or `symlink`), `cardinality`, `introduced_by_task`, `generator`, `invocation_target`, and `sha_policy`; reject unknown keys, duplicate destinations, ambiguous globs, and generated rows whose named generator is not in the same manifest. Add the fixed `packaging/macos/IZ Clinical Notes Analyzer - Read Me.txt` now so packaging does not depend on a later documentation task.
  - Enumerate common source-to-destination mappings, not just labels: `VERSION -> pyi://VERSION`; `VERSION.json -> pyi://VERSION.json`; `frontend/dist/index.html -> pyi://frontend/dist/index.html`; every Vite asset reached recursively through HTML `src`/`href`, JavaScript static/dynamic imports, and CSS `url()` under `pyi://frontend/dist/assets/`; `config/rules/alleva_treatment_plan_completeness_rules.yaml -> pyi://config/rules/alleva_treatment_plan_completeness_rules.yaml`; `config/checklists/treatment-plan-v1.json -> pyi://config/checklists/treatment-plan-v1.json`; and exactly `README.md`, `docs/Windows-User-Guide-Version-1.md`, `docs/Windows-Deployment-and-Test-Guide-Version-1.md`, `docs/beta-client-test-run-guide.md`, and `docs/patient-treatment-plan-handling.md` to same-basename `docs/` destinations. The scanner rejects unresolved references, assets outside the transitive graph, and extras. No recursive repo-root, free-form docs/tools, or basename inference is allowed.
  - Enumerate Windows generated destinations exactly: one archive-root directory `IZ Clinical Notes Analyzer/` containing `release-manifest.json`, detached `release-manifest.sha256`, exactly `Install-IZ-Clinical-Notes-Analyzer.cmd`, `Launch-IZ-Clinical-Notes-Analyzer.cmd`, `Stop-IZ-Clinical-Notes-Analyzer.cmd`, `Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd`, `Backup-IZ-Clinical-Notes-Analyzer.cmd`, `Restore-IZ-Clinical-Notes-Analyzer.cmd`, `Uninstall-IZ-Clinical-Notes-Analyzer.cmd`, and `Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd`; `installer/install-windows-release.ps1`; `installer/uninstall-windows-release.ps1`; `app/runtime/IZClinicalNotesAnalyzer.exe`; and exactly `app/tools/launch-packaged-runtime.cmd`, `app/tools/stop-windows-local.ps1`, `app/tools/backup-local-data.ps1`, `app/tools/restore-local-data.ps1`, `app/tools/collect-diagnostics.ps1`, and `app/tools/complete-uninstall-local-data.ps1`; plus common resources. The canonical manifest lists every payload entry except itself and its detached digest; `release-manifest.sha256` is lowercase SHA-256 plus two spaces plus `release-manifest.json` and LF. There is no nonexistent runtime `--install` substitute for the installer helper.
  - Enumerate macOS DMG roots exactly: `IZ Clinical Notes Analyzer.app`, `IZ Clinical Notes Analyzer Utilities.app`, `IZ Clinical Notes Analyzer - Read Me.txt`, and `Applications -> /Applications`. Utilities embeds the Python `Install/Upgrade for Me`, stop, backup, restore, diagnostics, and complete-uninstall operations plus exactly `Resources/uninstall-macos-release.sh` for deferred self-removal; nothing executable is loose at DMG root.
  - Add `scripts/release_safety.py` with `stage`, `scan-tree`, `scan-zip`, `scan-pyinstaller-toc`, `scan-dmg-manifest`, and `verify-git-source`. Canonicalize every input/output; inspect PyInstaller's actual archive/COLLECT inventory with `pyi-archive_viewer` plus filesystem inventory; reject traversal, duplicate raw ZIP names, drive/UNC/device/ADS paths, trailing-dot/space aliases, Unicode-NFC/case-fold collisions, paths outside roots, missing/extra files, dirty tracked state, unexpected untracked staging inputs, forbidden names/extensions, and credential/PHI canaries before extraction. On Windows, build in a verified non-cloud `%TEMP%` staging root; allow a OneDrive cloud-placeholder source only after hydration and byte/hash verification, but reject every name-surrogate reparse tag and require final staging/ZIP entries to be regular. On macOS, permit only manifest-enumerated relative framework symlinks whose lexical and resolved targets stay in the same `.app`, plus the exact DMG-root `Applications -> /Applications`; record link text and target content hash and never traverse outside the containing root.
  - Convert `scripts/release-safety.ps1`, `scripts/scan-release-safety.ps1`, and `scripts/test-release-safety.ps1` into Windows shims/test drivers over the Python implementation while retaining their public command names. Add `backend/tests/test_release_safety_cross_platform.py` that exercises real directories and ZIPs; DMG extraction is exercised on macOS in Task 23.
  - `verify-git-source` requires exact expected HEAD and a clean tracked worktree for release builds. `-AllowDirty` may remain only for a diagnostic scan that cannot emit/stage an artifact; builders may not pass it.

  Must NOT do: Do not copy the repo with exclusions, reject safe OneDrive placeholders merely for having a cloud tag, follow a link outside its declared root, merge duplicate/aliased ZIP names, package `.env`, databases, uploads, logs, reports, caches, dependencies, test output, `.omo`, or local credentials, or pass based on script-text assertions.

  Parallelization: Can parallel: YES | Wave 2 | Blocked by: [1] | Blocks: [7, 13, 19, 20, 21]

  References:
  - Broad copy: `scripts/build-windows-installer.ps1:96-177,915` (`Copy-RepoContent`).
  - Current scanners: `scripts/build-windows-installer.ps1:392-451`, `scripts/release-safety.ps1`, `scripts/scan-release-safety.ps1:1-28`.
  - Current canaries: `scripts/test-release-safety.ps1:25-143`.
  - Security boundaries: repository `AGENTS.md` Security / PHI rules and `.gitignore`.

  Acceptance criteria:
  - A safe synthetic manifest stages exactly the named source/destination inventory, actual PyInstaller TOC/COLLECT entries, wrapper/helper inventory, and transitive Vite asset graph and emits SHA-256/size/type/link metadata; one missing/extra/unreferenced asset, absent Windows installer helper, basename-only mapping, or free-form manifest entry fails.
  - Tree and ZIP scanners reject every forbidden-category/content/unlisted-link/traversal/raw-duplicate/drive/UNC/device/ADS/trailing-alias/Unicode-case-collision/dirty-source canary and redact values; hydrated OneDrive source bytes stage into a non-reparse temp tree; a manifest-valid in-bundle framework link and DMG-root Applications link pass, while escape/absolute/cycle/unlisted links fail.
  - The Task-6 staging CLI has no repo-mirroring or dirty artifact-emission mode; its execution test places a deliberately unlisted benign file beside allowed sources and proves the emitted staged tree/ZIP inventory excludes it. Tasks 19/20 separately prove their builders invoke only this boundary.

  QA scenarios:
  ```text
  Scenario: Explicit safe payload stages and scans deterministically
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode release-safety --output-dir "$ATTEMPT_DIR/task-6-native" --receipt "$ATTEMPT_DIR/task-6-native-collection.json"`.
    Expected: Exit 0 on Windows x64 and macOS arm64; expected inventories/hashes match, ZIP extraction scan passes, platform alias/link policies execute, no repo-local runtime data is read, and receipts prove exact target plus cleanup.
    Evidence: $ATTEMPT_DIR/task-6-native-collection.json and $ATTEMPT_DIR/task-6-native/{windows,macos}/{receipt.json,junit.xml}

  Scenario: Secret/PHI, raw-name aliases, unsafe links, dirty source, and fake PASS text are rejected
    Tool:     bash
    Steps:    Run `python -m pytest backend/tests/test_release_safety_cross_platform.py -k "secret_canary or phi_canary or unlisted_file or dirty_source or traversal or raw_duplicate or drive_name or unc_name or device_name or ads_name or trailing_alias or nfc_collision or case_collision or unlisted_symlink or absolute_symlink or symlink_cycle or applications_symlink_wrong_parent or misleading_exit23" -q --junitxml="$ATTEMPT_DIR/task-6-release-safety-adversarial.xml"` against real temp trees/ZIPs using the current task's locked Python 3.12 environment.
    Expected: Every case fails for the expected safe category, markers/paths are absent from logs, and no output package is retained.
    Evidence: $ATTEMPT_DIR/task-6-release-safety-adversarial.xml
  ```

  Adversarial classes: `dirty_worktree`, `forbidden_release_canary`, `path_case_symlink`, `misleading_success_output`, `cleanup_escape`.

  Cleanup: Scanner tests assert staging/extraction roots are temp descendants before removal and leave the repo/worktree untouched.

  Commit: YES | Message: `build(release): stage desktop artifacts from an allowlist` | Files: [`config/release/desktop-package-manifest.json`, `packaging/macos/IZ Clinical Notes Analyzer - Read Me.txt`, `scripts/release_safety.py`, `scripts/release-safety.ps1`, `scripts/scan-release-safety.ps1`, `scripts/test-release-safety.ps1`, `backend/tests/test_release_safety_cross_platform.py`]

- [ ] 7. Implement shared packaged preflight and native-dialog contracts

  What to do:
  - Add `backend/app/desktop/preflight.py` with ordered checks and stable safe reason codes for supported OS/architecture, immutable resource inventory/hash readability, canonical data-root writability, `.env` safety/permissions, at least 512 MiB free space, valid configured port, lock/state consistency, SQLite directory/create/delete capability, migration-readiness preconditions, browser-launch capability, and log directory writability.
  - Distinguish `packaged` and `source` modes. Packaged mode must never check/install Python, Node, Git, npm, PowerShell modules, Docker, or PostgreSQL. Source mode reports missing developer tools but does not mutate/install them; existing checkout setup scripts remain a separate developer surface.
  - Add `backend/app/desktop/dialogs.py` with a `DesktopDialogAdapter` protocol for first-run credential display, preflight failure, already-starting, unrelated-port conflict, startup timeout, stop result, backup/restore result, diagnostics result, and uninstall confirmation. Dialog payloads contain safe codes/user actions only; while `must_reset_password=true`, the first-run password is re-read only from the private `.env` into the current in-memory dialog call (never a second handoff store) and is never included in the JSON report/log.
  - Write a redacted `logs/desktop-preflight-latest.json` atomically after data-root validation. Each check records name/status/duration/safe detail; failures name the diagnostic path without local secrets or clinical content.
  - Add `backend/app/desktop/runtime_logging.py` and a packaged Uvicorn logging configuration that is private from the first byte. Disable access logs and trace-local/body/query/header/URL serialization. Permit only timestamp, fixed event code, severity, component/function allowlist, exception class, and safe reason code in `logs/desktop-runtime.jsonl`; rotate at 1 MiB with five files and remove files older than 30 days during held-lease startup. Native dialogs receive a safe code plus a generic action, never raw exception text. Unit tests raise exceptions containing password/token/PHI/path/filename canaries and assert none appears in current/rotated logs, stderr, dialogs, diagnostics, or evidence.
  - Add `backend/tests/test_desktop_preflight.py` using fake platform/dialog adapters and actual temp files/resources.
  - Extend Task 1's already-executed `.github/workflows/native-desktop-bootstrap.yml`, dispatcher, writer, and receipt tests for Tasks 7-20. Preserve its six hardcoded cross-OS modes and add exactly the cross-OS modes `preflight`, `operator-backup`, `maintenance`, and `controller`; the Windows-only modes `windows-adapter`, `windows-key`, `windows-lifecycle`, `windows-maintenance`, and `windows-package`; and the macOS-only modes `macos-adapter`, `macos-key`, `macos-lifecycle`, `macos-maintenance`, and `macos-package`. Pin setup-node in addition to Task 1's pinned actions, keep the exact `windows-2022` x64/`macos-15` arm64 guards, and map each new mode to its exact task-owned test/build command without accepting shell text. A mode whose target files do not yet exist fails, while Task 7's `preflight` mode has no forward-file dependency.
  - Preserve `dispatch-native-bootstrap.py`'s exact Task-1 CLI and source-first/trigger-last selection/cleanup contract. Extend only its closed mode-to-target/expected-artifact table and strict receipt schema; every mode has one fixed ordered happy-plus-adversarial command list and exact output inventory, so changing only an output directory cannot select or omit cases. Do not add a generic command, workflow name, runner label, artifact name, or latest-run selector. This transport remains task-local engineering bootstrap evidence only and cannot issue Task21-26 artifact/barrier receipts.

  Must NOT do: Do not perform package installation, network calls, database migration, process termination, or secret logging during application preflight; do not treat a missing default browser as backend failure when the local URL can be shown. The CI transport must not weaken or remove a Task1-6 mode, use `workflow_dispatch`, accept arbitrary commands, select latest-by-branch, claim packaged-artifact/barrier acceptance, or let a missing future mode file break the Task-7 `preflight` run.

  Parallelization: Can parallel: YES | Wave 3 | Blocked by: [2, 6] | Blocks: [8, 9, 10, 11, 12, 13, 14]

  References:
  - Current Windows preflight: `scripts/preflight-windows.ps1:1-230` - checks/bootstrap that must split into packaged versus checkout behavior.
  - Config fail-closed rules: `backend/app/core/config.py:71-93`.
  - Readiness: `backend/app/v2/api/runtime_routes.py:60-76` and `backend/tests/test_v2_runtime_readiness.py:15`.
  - Release resources: `config/release/desktop-package-manifest.json` from Task 6.
  - Existing CI trigger baseline: `.github/workflows/ci.yml:1-33`; new-workflow bootstrap uses a push event because a not-yet-default-branch workflow cannot be manually dispatched.
  - Pinned action identities: Task 21 exact checkout/setup/upload/download SHAs; Task 7 establishes the same immutable pins early.

  Acceptance criteria:
  - Packaged preflight executes every named check, emits one redacted report, and has no code path that invokes package managers or external network transports.
  - Missing resource, unwritable data root, unsafe env, low disk, bad port, inconsistent state, and unavailable SQLite path each yield a stable distinct safe reason; report contains no injected password/token/PHI marker.
  - Browser-unavailable result is a warning with the exact local URL and does not mark an otherwise healthy backend unstartable.
  - At the Task-7 commit, `dispatch-native-bootstrap.py --mode preflight` produces schema-valid Windows-x64 and macOS15-arm64 receipts bound to the exact target/workflow/request/action hashes; both run the real preflight test, cleanup is true, and all nonce refs are absent afterward. A future mode requested before its files exist fails safely and cannot emit a success receipt.

  QA scenarios:
  ```text
  Scenario: Complete packaged preflight passes without external prerequisites
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode preflight --output-dir "$ATTEMPT_DIR/task-7-native" --receipt "$ATTEMPT_DIR/task-7-native-collection.json"`.
    Expected: Exit 0 on exact Windows x64 and macOS arm64 jobs; checks execute in order, safe reports parse, fake package/application-network adapters record zero calls, receipts bind target/workflow hashes, and nonce refs are deleted.
    Evidence: $ATTEMPT_DIR/task-7-native-collection.json and $ATTEMPT_DIR/task-7-native/{windows,macos}/{receipt.json,junit.xml,run.log}

  Scenario: Every prerequisite failure is safe, distinct, and non-mutating
    Tool:     pytest
    Steps:    Run `PYTHONPATH=backend python -m pytest backend/tests/test_desktop_preflight.py -k "missing_resource or unwritable or low_disk or unsafe_env or port_conflict or bad_state or browser_unavailable" -q --junitxml="$ATTEMPT_DIR/task-7-preflight-adversarial.xml"`.
    Expected: Blocking cases fail before config/db import; browser-only case warns; injected secret/PHI markers are absent from report/log/dialog captures.
    Evidence: $ATTEMPT_DIR/task-7-preflight-adversarial.xml

  Scenario: Extended mode table preserves early modes and rejects forward/arbitrary commands
    Tool:     pytest
    Steps:    Run `PYTHONPATH=backend python -m pytest backend/tests/test_native_bootstrap_receipt.py -q -k "preserves_task1_modes or exact_mode_targets or arbitrary_command or stale_run or wrong_workflow_blob or missing_future_file or misleading_pass or cleanup" --junitxml="$ATTEMPT_DIR/task-7-native-transport-adversarial.xml"`.
    Expected: Exit 0 only because all six Task1-6 modes remain mapped, every new mode has the fixed OS/command/artifact contract, and arbitrary/missing/stale/unclean requests cannot emit success or Task21-26 evidence.
    Evidence: $ATTEMPT_DIR/task-7-native-transport-adversarial.xml
  ```

  Adversarial classes: `bundle_write`, `unrelated_port`, `privacy_canary`, `misleading_success_output`, `stale_state`, `cleanup_escape`.

  Cleanup: Close filesystem handles and delete only validated temp profiles; retain evidence only under `ATTEMPT_DIR`.

  Commit: YES | Message: `feat(desktop): add preflight and native bootstrap transport` | Files: [`backend/app/desktop/preflight.py`, `backend/app/desktop/dialogs.py`, `backend/app/desktop/runtime_logging.py`, `backend/tests/test_desktop_preflight.py`, `.github/workflows/native-desktop-bootstrap.yml`, `scripts/ci/dispatch-native-bootstrap.py`, `scripts/ci/write-native-bootstrap-receipt.py`, `backend/tests/test_native_bootstrap_receipt.py`]

- [ ] 8. Implement the Windows x64 desktop platform adapter

  What to do:
  - Add `backend/app/desktop/windows.py` implementing Task 4 lock/process APIs and Task 7 dialog/permissions/browser/fallback APIs. Create the outside-root lease with `CreateFileW` share mode zero on Task 4's fixed lock path and an explicit current-user/SYSTEM/Administrators security descriptor; implement duplicate/inherit/adopt through documented handle APIs. Use Kernel32 APIs through `ctypes` for PID creation time/full executable path, `MessageBoxW` for safe dialogs, `webbrowser.open`, and termination only after full identity revalidation.
  - Implement Task 2's `PrivateStorageProvider`: create the data/root directories with restrictive security before secrets, create `.env`/state/restore trees with restrictive handles from their first byte, then verify current-user/SYSTEM/Administrators ACLs and reject broad access. `icacls.exe` may be used only as a post-create verifier/repair for pre-existing nonsecret directories, never as a later fix for a just-written secret. Never print an ACL-bearing path when it contains injected privacy canaries.
  - Add `backend/requirements-desktop.txt` containing the current local desktop runtime dependencies from `requirements-windows-local.txt`; change `requirements-windows-local.txt` to include it for compatibility. Pin the native builder/runtime interpreter to CPython `3.12.10`; keep PostgreSQL/`uvicorn[standard]` out. Use only stdlib/installed Windows APIs for adapter code, so no new native process/GUI dependency is required.
  - Generate and commit `backend/requirements-lock/windows-x64.txt` with hashes for the exact CPython-3.12.10 Windows x64 union of `requirements-desktop.txt` and `requirements-build.txt`, including PyInstaller. It is generated only on Windows by the documented lock command, includes every transitive wheel hash/version, and installs with `--require-hashes`; Task21 verifies the closure.
  - Add `backend/requirements-lock/windows-x64-test.txt` as a separately hashed native-test closure containing pytest and only test dependencies. Both locks state `python_full_version == '3.12.10'`; their generation scripts and CI abort unless the interpreter reports exactly `3.12.10` and `AMD64` before creating the venv.
  - Add `backend/tests/test_desktop_windows_adapter.py`, guarded to Windows, with a real child process, lock contention, ACL inspection, dialog/browser fakes, and revalidated test-owned fallback termination.

  Must NOT do: Do not kill by process name/port, widen ACLs, require administrator elevation, install prerequisites, or use WMI/CIM as the only identity proof.

  Parallelization: Can parallel: YES | Wave 4 | Blocked by: [2, 4, 7] | Blocks: [11, 14, 15, 21]

  References:
  - Current process logic: `scripts/stop-windows-local.ps1:77-240,261-292`.
  - Current dependency set: `backend/requirements-windows-local.txt:1-14`; contrast server/developer `backend/requirements.txt:1-17`.
  - Current normal-user target: repository `AGENTS.md` Repo purpose and Windows launch expectations.
  - Existing lifecycle tests: `scripts/test-windows-stop.ps1:20-112`.

  Acceptance criteria:
  - Native Windows tests prove cross-process exclusive file-handle leasing keyed by data-dir identity, continuous duplicate/inherit/adopt handoff after parent exit, exact PID/creation-time/exe lookup, case/Unicode-equivalent path identity, and refusal to terminate a PID with any mismatched identity field.
  - A generated `.env` and runtime state are readable/writable only by the current user, SYSTEM, and Administrators as required by Windows; ordinary unrelated user grants are absent.
  - A newly created temp-root Windows x64 venv installs `backend/requirements-desktop.txt` plus build requirements, records the complete wheel/version/hash closure, and imports every packaged module without Docker/PostgreSQL/Node.

  QA scenarios:
  ```text
  Scenario: Real Windows adapter owns and stops only its test process
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode windows-adapter --output-dir "$ATTEMPT_DIR/task-8-native" --receipt "$ATTEMPT_DIR/task-8-native-collection.json"`.
    Expected: Exit 0; fresh locked install, handle/identity/ACL tests, parent-exit handoff, and test-owned child termination all pass.
    Evidence: $ATTEMPT_DIR/task-8-native-collection.json and $ATTEMPT_DIR/task-8-native/windows/{receipt.json,junit.xml}

  Scenario: PID-reuse-like state, wrong executable, and broad ACL fail closed
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode windows-adapter --output-dir "$ATTEMPT_DIR/task-8-native-adversarial" --receipt "$ATTEMPT_DIR/task-8-native-adversarial-collection.json"`; the hardcoded mode must run `python -m pytest backend/tests/test_desktop_windows_adapter.py -q` including the named mismatched-identity/ACL/handoff/lock-contention cases and publish their JUnit file.
    Expected: Every decoy remains alive, exclusive handle remains continuously owned through handoff, no secret is written under a broad ACL, and no force action is issued.
    Evidence: $ATTEMPT_DIR/task-8-native-adversarial-collection.json and $ATTEMPT_DIR/task-8-native-adversarial/windows/{receipt.json,junit.xml}
  ```

  Adversarial classes: `pid_reuse`, `path_case_symlink`, `startup_race`, `cleanup_escape`.

  Cleanup: Revalidate each test child before terminating it in `finally`; remove only temp ACL/lock files.

  Commit: YES | Message: `feat(desktop): add Windows lifecycle adapter` | Files: [`backend/app/desktop/windows.py`, `backend/requirements-desktop.txt`, `backend/requirements-windows-local.txt`, `backend/requirements-lock/windows-x64.txt`, `backend/requirements-lock/windows-x64-test.txt`, `backend/tests/test_desktop_windows_adapter.py`]

- [ ] 9. Implement the Apple Silicon macOS platform adapter

  What to do:
  - Add `backend/app/desktop/macos.py` implementing Task 4 lock/process APIs and Task 7 permissions/browser/fallback APIs. Use `fcntl.flock` on the persistent immutable Task-4 lock file, implement FD inherit/adopt without unlink, use `libproc`/`proc_pidinfo`/`proc_pidpath` through `ctypes` for process identity, `webbrowser.open`, identity-revalidated SIGTERM at second 20, and only after another full identity check identity-revalidated SIGKILL at/after second 25.
  - Add `backend/app/desktop/macos_dialogs.py` as an in-process AppKit adapter through a fixed `ctypes` Objective-C/AppKit bridge; values are assigned directly to `NSAlert`/`NSSecureTextField` objects and never placed in a child process, AppleScript source, argv, environment, log, or exception. Provide headless injectable fakes for CI; Finder-visible prompt usability remains an external clean-Mac release gate.
  - Implement Task2's private-storage and volume-identity providers. Query the deepest existing ancestor with `getattrlist`/`ATTR_VOL_CAPABILITIES` and `VOL_CAP_FMT_CASE_SENSITIVE` through `ctypes`; normalize Unicode NFC and case-fold only on a case-insensitive volume. Create directories with `mkdir(..., 0o700)` under restrictive umask and ordinary private files with `os.open(..., O_CREAT|O_EXCL, 0o600)`. Implement Task4's lock-specific first-create/write/fsync/`UF_IMMUTABLE`/close then `O_RDONLY|O_NOFOLLOW|O_CLOEXEC` reopen flow; use `fstat`/`lstat` plus `acl_get_file`/`acl_get_entry` to enforce current EUID/no extended ACL, directory `0700`, file `0600`, contained roots, flag state, and device/inode identity at every declared validation point. Treat `UF_IMMUTABLE` as cooperating-instance hardening/detection only.
  - Require `platform.machine() == "arm64"` and macOS 14.0+ for packaged mode. Source tests may run elsewhere through fakes but may not claim native support.
  - Generate and commit `backend/requirements-lock/macos-arm64.txt` with hashes for the exact CPython-3.12.10 macOS ARM64 union of `requirements-desktop.txt` and `requirements-build.txt`, including PyInstaller. It is generated only on native ARM64, installs with `--require-hashes`, and Task21 verifies the closure.
  - Add `backend/requirements-lock/macos-arm64-test.txt` as a separately hashed pytest/native-test closure. Both locks state `python_full_version == '3.12.10'`; generation and CI abort unless Python reports exactly `3.12.10` and `arm64` before venv creation.
  - Add `backend/tests/test_desktop_macos_adapter.py`, guarded to Darwin ARM64, with real `flock`, child identity, chmod, dialog/browser fakes, and test-owned termination. Add unit fakes runnable on all hosts for error mapping.

  Must NOT do: Do not use `ps` text parsing, process name, or port as identity; do not pass secret/user data to `osascript`, a child process, or argv; do not claim Intel or macOS-14-on-hardware validation from a macOS 15 runner; do not require Homebrew/Xcode for end-user execution; do not claim an owner-clearable flag prevents a hostile same-EUID process from replacing a pathname.

  Parallelization: Can parallel: YES | Wave 4 | Blocked by: [2, 4, 7] | Blocks: [12, 14, 16, 21]

  References:
  - Platform contract: Task 4 files and `backend/app/desktop_runtime.py:8-30`.
  - Data default: Apple File System Programming Guide convention for `~/Library/Application Support`; implementation must use the fixed Scope path.
  - Packaging target: PyInstaller macOS notes, `https://pyinstaller.org/en/stable/usage.html#building-macos-app-bundles`.
  - Tests: Task 8 adapter tests are the behavioral twin; macOS uses native primitives instead of Windows APIs.

  Acceptance criteria:
  - On the native ARM64 macOS 15 engineering runner, real lock/identity/permission/termination tests pass, `uname -m`/Python both report arm64, and the build declares a macOS 14 deployment target. Actual macOS 14 Apple-Silicon installation remains the separate external release gate and is not claimed here.
  - The adapter refuses Intel, unsupported OS, escaping symlink roots, permissive files, and identity mismatches without changing target process/data. On a case-insensitive APFS volume case/Unicode aliases share one lease; on a user-mounted case-sensitive APFS test image `Profile` and `profile` have distinct IDs/leases. Cooperating contenders remain excluded; clear-flag/replace-inode is detected by the next validation/watchdog and triggers safe shutdown without touching the replacement process. Cleanup leaves the immutable mode-0600 lock file reopenable read-only.
  - AppKit dialog invocation stays in-process and keeps values out of argv/environment/logs/exceptions; browser failure returns the exact safe localhost URL.

  QA scenarios:
  ```text
  Scenario: Native ARM64 macOS adapter controls one test-owned process
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode macos-adapter --output-dir "$ATTEMPT_DIR/task-9-native" --receipt "$ATTEMPT_DIR/task-9-native-collection.json"`; the hardcoded job asserts `uname -m=arm64` and Python `3.12.10|arm64`, installs both committed hash locks, and runs the complete adapter module.
    Expected: Exit 0; native flock/libproc/mode assertions pass and only the exact child is stopped.
    Evidence: $ATTEMPT_DIR/task-9-native-collection.json and $ATTEMPT_DIR/task-9-native/macos/{receipt.json,junit.xml,run.log}

  Scenario: Intel/old-OS, symlink, broad mode, and decoy identity are rejected
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode macos-adapter --output-dir "$ATTEMPT_DIR/task-9-native-adversarial" --receipt "$ATTEMPT_DIR/task-9-native-adversarial-collection.json"`; the hardcoded mode creates its user-owned case-sensitive APFS image and runs the named unsupported-arch/version, symlink, mode, identity, Unicode/case, persistent-lock, clear-flag/replace-inode, and private-first-open cases before unmounting it in `finally`.
    Expected: Every failure yields its safe code; aliases contend only on insensitive volumes, case-distinct paths remain distinct on the case-sensitive image, ordinary cooperating contention is exclusive, deliberate same-EUID clear/replace is detected rather than claimed prevented and signals no decoy, persistent lock is unheld after exit, no secret is briefly broad, and no write occurs in `.app`, DMG, repo, or CWD.
    Evidence: $ATTEMPT_DIR/task-9-native-adversarial-collection.json and $ATTEMPT_DIR/task-9-native-adversarial/macos/{receipt.json,junit.xml,run.log}
  ```

  Adversarial classes: `wrong_architecture`, `pid_reuse`, `path_case_symlink`, `bundle_write`, `same_euid_tamper`.

  Cleanup: Revalidate test PIDs and stop only test-owned children. In the adversarial case, unmount in `finally` only the case-sensitive APFS image created by this invocation after matching its recorded device node, volume UUID, mount path, and temp-image path; never unmount a pre-existing or identity-mismatched volume. Delete only validated task temp roots.

  Commit: YES | Message: `feat(desktop): add Apple Silicon lifecycle adapter` | Files: [`backend/app/desktop/macos.py`, `backend/app/desktop/macos_dialogs.py`, `backend/requirements-lock/macos-arm64.txt`, `backend/requirements-lock/macos-arm64-test.txt`, `backend/tests/test_desktop_macos_adapter.py`]

- [ ] 10. Implement the common versioned operator backup and rollback-safe restore core

  What to do:
  - Add `backend/app/desktop/operator_backup.py` for operator full-data backups only; do not change `backend/app/v2/migrations/backup.py` or its `IZCNABK1:` migration format. Every create/restore/recovery call requires a matching held Task-4 maintenance `DataDirLease` and rechecks it before snapshot, old-root move, new-root commit, rollback, and cleanup; an unlocked call fails `operator_backup_maintenance_lease_required` before reading mutable data.
  - Require the operator backup destination to be outside the canonical data root and outside every restore/journal/rollback root. Build the payload as a streaming ZIP directly into the encryptor at a mode-`0600`/private-DACL sibling `<destination>.partial`; never create a plaintext ZIP or aggregate the declared 50-GiB payload in memory. Flush and fsync the encrypted partial, revalidate the destination parent/native identity, atomically replace the final path, fsync the parent, and remove only the validated partial on failure. Inject failpoints after each header/ciphertext/tag write, file fsync, rename, and parent fsync; a crash leaves either the old final backup or one authenticated complete new backup, never a published partial.
  - Define a narrow `OperatorBackupKeyProtection` protocol in `operator_backup.py`: `wrap_content_key(data_dir_id, source_os, 64-byte-key) -> KeyWrapRecord`, `unwrap_content_key(data_dir_id, header) -> 64-byte-key`, and `zeroize()`. The common core validates the returned header fields but never imports DPAPI, Security.framework, or a native module. Task-10 tests use only a deterministic in-memory contract adapter that emits independently constructed, syntactically valid records for each declared OS/header shape but performs no native protection; Task 11 supplies/tests the real Windows provider and Task 12 supplies/tests the real macOS provider. A Task-10 pass therefore proves the provider boundary and envelope semantics, not native key protection.
  - Define the exact V3 byte grammar: 8 ASCII bytes `IZCNABK3`; unsigned 4-byte big-endian canonical-header length `H` (`2 <= H <= 65536`); `H` bytes canonical UTF-8 JSON (sorted keys, separators `,`/`:`, no BOM); unsigned 8-byte big-endian ciphertext length `C`; exactly `C` ciphertext bytes; exactly 32 HMAC bytes; EOF. Generate a random 64-byte content key and random 16-byte IV per backup; bytes `0:32` are the AES-256 key and `32:64` the HMAC-SHA-256 key; use CBC with PKCS#7 padding. The injected key-protection provider wraps all 64 key bytes. Compute HMAC over every byte from magic through ciphertext, append the tag, and verify with `hmac.compare_digest` before decrypting or parsing ZIP content.
  - The canonical header has exactly these typed fields and bounds: `format` string exactly `IZCNABK3`; `version` integer exactly `3` (JSON booleans rejected); `kind` string exactly `operator-full-data`; `source_os` enum `windows-x64|macos-arm64`; `restore_scope` respectively `same-windows-user|same-macos-user-and-keychain`; `key_wrap_id` respectively `dpapi-current-user-v1|macos-keychain-aeskw-v1`; `key_reference` respectively exact `current-user` or `com.r3recoveryservices.izclinicalnotesanalyzer.operator-backup/operator-backup-master-v1:<64-lowercase-hex-data-dir-id>`; `wrapped_key_b64` canonical RFC-4648 Base64 decoding to 64..16384 bytes for DPAPI or exactly 72 bytes for RFC-3394; `iv_b64` canonical Base64 decoding to exactly 16 nonzero bytes; `app_version` 1..64 ASCII characters matching `[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?`; `app_build` 1..32 ASCII digits/dots matching `[0-9]+(?:\.[0-9]+)*`; `created_at_utc` exactly `YYYY-MM-DDTHH:MM:SSZ` and a real UTC instant; `plaintext_length` integer `1..53687091200`; `plaintext_sha256` 64 lowercase hex; and `ciphertext_length` integer `16..53687091216`, divisible by 16, equal to outer `C`, and equal to PKCS#7-padded plaintext length. Reject duplicate/unknown keys, noncanonical Base64/JSON, username/path/patient/archive/secret fields, length disagreement, trailing bytes, an all-zero IV, and out-of-bound wrapped keys before allocation/decryption. Do not retain IV history; instead a deterministic RNG-injection test proves two consecutive backups receive different content keys and IVs.
  - Parse the held profile's private `.env` before snapshot and require every configured mutable path, including `IZ_CNA_LOCAL_SQLITE_DB_PATH`, to be relative and resolve within the canonical data root. Snapshot that configured database with SQLite's online-backup API regardless of basename; also include a supported legacy DB only when independently configured/present. The encrypted ZIP contains canonical `backup-manifest.json`, `.env`, the online snapshot(s), `manual-uploads/**`, legacy `uploads/**`, audit log, API/configuration reports, exports, allowlisted job artifacts, routine operator backups under `backups/**`, and migration rollback artifacts matching the existing `migration-*.izcnabackup` policy. `backup-manifest.json` is canonical JSON with exactly `format="iz-cna-operator-payload-v1"`, `source_os`, `created_at_utc`, `file_count`, `total_size`, and `files`; rows are sorted by UTF-8 POSIX relative path and have exactly `path`, `class`, `size`, and lowercase `sha256`. Header/payload OS and timestamps match. Fail creation on any unknown non-ephemeral entry. Explicitly exclude `runtime/**`, lifecycle state/token/PID/nonce, the outside-root lock/journal tree, preflight/diagnostic logs, WAL/SHM, restore/rollback/temp/partial paths, caches, and all links.
  - Define legacy Windows V2 normalization before restore: authenticate/decrypt the historical whole-root ZIP; map only the same current stable classes above, map the database path through the restored `.env`, drop only the named ephemeral classes, and reject unknown classes, links, aliases, traversal, or extra roots. Never silently reclassify an arbitrary V2 file. Preserve migration V1 as a separate format.
  - Validate magic/framing/HMAC/header/platform/key wrap, maximum 100,000 entries, maximum 10 GiB per entry, maximum 50 GiB declared total, traversal/absolute/case-collision/link entries, all hashes, SQLite integrity/foreign keys/schema, and manifest completeness before touching current data. A backup whose schema is newer than the packaged migration registry fails `operator_backup_future_schema`; an older supported schema is migrated inside staging only. Load the staged `.env` keys and prove every encrypted database field, saved API configuration, and encrypted upload decrypts/authenticates; validate the audit-chain root/head/count and all referenced upload/job rows before commit.
  - Restore into securely created sibling `.<name>.restore-new-<run-id>` and preserve current data as `.<name>.restore-old-<run-id>`. Before mutation, parse restored `.env` with the bootstrap parser and reject any mutable path outside the selected canonical target; encryption/auth values remain byte-identical. Store the journal outside the replaceable data root at the Task-4 private lock root under `restore-journals/<data-dir-id>/journal.json`; it contains schema/run/data-dir IDs, owner UID/SID, native parent identity, exact three paths, old/new tree manifests, and state. Reject zero, multiple, foreign-owner, cross-data-dir, or mismatched journals rather than guessing. The write-ahead states are `prepared`, `move_old_intent`, `old_moved`, `commit_new_intent`, `new_committed`, `cleanup_intent`, `cleanup_complete`; fsync journal and parent before/after each rename/delete. Recovery under the same lease validates actual path native IDs/tree hashes at every state, deterministically rolls back/finalizes, and retains all trees with `operator_backup_recovery_ambiguous` on mismatch. Task 14 invokes recovery immediately after lease acquisition and before bootstrap/config import. Cross-OS restore raises `operator_backup_platform_scope_mismatch` before key unwrap or mutation.
  - Add `backend/tests/test_operator_backup.py` and independent fixed-vector fixture `backend/tests/fixtures/operator-backup-v3-vector.json`. The vector fixes every header value, content key, IV, payload bytes, ciphertext, HMAC, and complete envelope; its test independently parses/HMACs/decrypts with direct primitives rather than product serialization helpers. Cover wrong types/enums/bounds/canonicalization, corruption, oversized/traversal, every before/after journal fsync/rename/delete crash boundary, outside-path `.env`, rollback failpoints, lease loss, private-from-first-byte restore staging, and runtime-token leak canaries.

  Must NOT do: Do not alter migration backups, copy a live SQLite/WAL byte set directly, restore runtime state, follow symlinks, support cross-OS restore, or expose archive entry names on a privacy error.

  Parallelization: Can parallel: YES | Wave 4 | Blocked by: [1, 4, 7] | Blocks: [11, 12, 13, 14]

  References:
  - Migration format: `backend/app/v2/migrations/backup.py:65-167` and `backend/tests/test_v2_backup_envelope.py:13-60` - preserve unchanged.
  - Operator V2: `scripts/backup-local-data.ps1:61-122` and `scripts/restore-local-data.ps1:35-110`.
  - Rollback/migration checks: `backend/tests/test_v2_migration_lifecycle.py:155-193`, `backend/tests/test_v2_migration_regressions.py:67-105`.
  - Runtime exclusions: Task 4 `runtime/desktop-state.json` and lock contract.

  Acceptance criteria:
  - V3 independent vector plus the in-memory contract provider prove exact provider call order, framing/key split/IV/padding/HMAC coverage/tag placement/constant-time verification; two consecutive backups have distinct keys/IVs; a custom in-root configured DB plus routine/migration backups round-trip with every allowed byte/hash, `integrity_check=ok`, empty `foreign_key_check`, decryptable encrypted fields/uploads/config, and a valid audit chain; runtime state/token/WAL/temp canaries are absent. No Task-10 result claims DPAPI or Keychain execution.
  - Tamper, wrong key, wrong platform, malformed length, traversal, symlink, case collision, oversized declaration, hash mismatch, invalid SQLite, future schema, invalid encrypted field/upload/config, invalid audit chain, ambiguous/multiple journal, and injected restore failure leave current data byte-for-byte unchanged.
  - Every create/restore/crash-recovery path refuses a missing/lost/wrong-root lease; exhaustive failpoints before/after every journal fsync/rename/delete deterministically restore or finalize without losing the canonical root or exposing a concurrent-launch window; outside-root mutable configuration is rejected before mutation.
  - Existing migration backup tests remain green and the new core never imports/calls the migration backup implementation as an operator format.

  QA scenarios:
  ```text
  Scenario: Synthetic full-data V3 backup round-trips transactionally
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode operator-backup --output-dir "$ATTEMPT_DIR/task-10-native" --receipt "$ATTEMPT_DIR/task-10-native-collection.json"`.
    Expected: Exit 0 on Windows x64 and macOS arm64 using only the identical in-memory contract provider; allowed hashes match, SQLite/encrypted-field/audit checks pass, provider call/zeroization assertions and migration-envelope tests remain green, ephemeral canaries are absent, and exact-target receipts prove cleanup. Real DPAPI/Keychain round-trips are explicitly absent until Tasks 11/12.
    Evidence: $ATTEMPT_DIR/task-10-native-collection.json and $ATTEMPT_DIR/task-10-native/{windows,macos}/{receipt.json,junit.xml}

  Scenario: Malicious archive and restore failpoint preserve current data
    Tool:     pytest
    Steps:    Run `PYTHONPATH=backend python -m pytest backend/tests/test_operator_backup.py -k "tamper or platform_scope or traversal or symlink or oversized or rollback or crash_boundary or lease_required or lease_lost or token_leak or independent_vector or canonical_header or outside_mutable_path or private_from_first_byte" -q --junitxml="$ATTEMPT_DIR/task-10-operator-backup-adversarial.xml"`.
    Expected: Each fails or recovers to the exact specified old/new state, the canonical root is never lost, rejected pre/post tree hashes match, and no archive path/secret marker appears in output.
    Evidence: $ATTEMPT_DIR/task-10-operator-backup-adversarial.xml
  ```

  Adversarial classes: `backup_token_leak`, `archive_traversal`, `tamper_wrong_key`, `rollback_failure`, `cleanup_escape`.

  Cleanup: Close ZIP/SQLite handles, validate sibling temp/rollback locations, and remove only test-created roots.

  Commit: YES | Message: `feat(backup): add cross-platform operator backup core` | Files: [`backend/app/desktop/operator_backup.py`, `backend/tests/test_operator_backup.py`, `backend/tests/fixtures/operator-backup-v3-vector.json`]

- [ ] 11. Preserve Windows DPAPI backups through the new operator core

  What to do:
  - Add `backend/app/desktop/windows_key_protection.py` implementing current-user DPAPI wrapping/unwrapping through `CryptProtectData`/`CryptUnprotectData` with `CRYPTPROTECT_UI_FORBIDDEN`, zeroing plaintext key buffers after use, and stable safe errors. V3 header key-wrap ID is `dpapi-current-user-v1`.
  - Port the existing operator `IZCNABK2` reader/validator into a Windows-only legacy adapter so existing same-user backups restore through the validate-first/rollback-safe Task 10 path. Do not emit new V2 files. Continue to recognize `IZCNABK1:` only through migration tooling, never this adapter.
  - Add `backend/tests/test_windows_operator_backup.py` and independent helper `backend/tests/helpers/generate_operator_v2_fixture.ps1`. At test runtime, the helper creates a synthetic ZIP and real `IZCNABK2` envelope using that runner account's `ProtectedData.Protect(CurrentUser)`, AES-CBC, and HMAC framing without importing/calling product backup code; the product legacy reader must restore it. Checked-in bytes may test V2 framing/tamper only and must never be claimed decryptable on arbitrary accounts.

  Must NOT do: Do not add machine-wide DPAPI scope, export raw keys, weaken V2 authentication, allow V2 on macOS, or overwrite current data before legacy validation completes.

  Parallelization: Can parallel: YES | Wave 5 | Blocked by: [7, 8, 10] | Blocks: [17]

  References:
  - Existing DPAPI writer: `scripts/backup-local-data.ps1:77-122`.
  - Existing DPAPI reader/rollback: `scripts/restore-local-data.ps1:41-105`.
  - Common core: Task 10 `backend/app/desktop/operator_backup.py`.

  Acceptance criteria:
  - On Windows, a V3 backup created with real current-user DPAPI restores; corrupted and foreign-wrapped keys fail before data mutation.
  - The current runner generates a real current-user-DPAPI V2 envelope at runtime and the product reader restores its exact allowed hashes; a copied/foreign-wrapper envelope fails. New backups begin with `IZCNABK3`, never V2.
  - Plaintext content-key canaries are absent from process output, files other than transient protected memory, and evidence.

  QA scenarios:
  ```text
  Scenario: DPAPI V3 and legacy V2 restore for the current Windows user
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode windows-key --output-dir "$ATTEMPT_DIR/task-11-native" --receipt "$ATTEMPT_DIR/task-11-native-collection.json"`; the hardcoded Windows job runs the complete DPAPI/V2 module under its actual current user.
    Expected: Exit 0; V3 and V2 allowed hashes round-trip, current data remains transactionally protected, and output is secret-free.
    Evidence: $ATTEMPT_DIR/task-11-native-collection.json and $ATTEMPT_DIR/task-11-native/windows/{receipt.json,junit.xml}

  Scenario: Wrong-user simulation and corrupt protected blob cannot mutate data
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode windows-key --output-dir "$ATTEMPT_DIR/task-11-native-adversarial" --receipt "$ATTEMPT_DIR/task-11-native-adversarial-collection.json"`; the hardcoded job runs the denied/corrupt/foreign-wrapper tests and records before/after tree hashes.
    Expected: Both return safe failure, before/after tree hashes match, and no rollback/temp remains.
    Evidence: $ATTEMPT_DIR/task-11-native-adversarial-collection.json and $ATTEMPT_DIR/task-11-native-adversarial/windows/{receipt.json,junit.xml}
  ```

  Adversarial classes: `tamper_wrong_key`, `rollback_failure`, `privacy_canary`.

  Cleanup: Zero test key buffers, close handles, and remove only isolated profiles/backup fixtures copied to temp.

  Commit: YES | Message: `feat(backup): retain Windows DPAPI operator restores` | Files: [`backend/app/desktop/windows_key_protection.py`, `backend/tests/test_windows_operator_backup.py`, `backend/tests/helpers/generate_operator_v2_fixture.ps1`]

- [ ] 12. Add macOS Keychain same-user backup key protection

  What to do:
  - Add `backend/app/desktop/macos_key_protection.py` implementing Security.framework `SecItemAdd`, `SecItemCopyMatching`, and `SecItemDelete` through `ctypes`, never command-line secret arguments. Use service `com.r3recoveryservices.izclinicalnotesanalyzer.operator-backup`, account `operator-backup-master-v1:<canonical-data-dir-id-sha256>`, `kSecUseDataProtectionKeychain=true` on every add/copy/delete query, `kSecAttrAccessibleWhenUnlockedThisDeviceOnly`, and `kSecAttrSynchronizable=false`; V3 `key_wrap_id` is `macos-keychain-aeskw-v1`, and header `key_reference` contains that exact profile-scoped service/account pair.
  - Generate one random 32-byte wrapping key only when the current user's item is absent during backup creation, store it in that login Keychain, and use RFC 3394 AES Key Wrap for each 64-byte V3 content key. Restore only reads the existing item; it never creates/replaces it. Zero copied buffers. Locked, denied, missing, duplicate/inconsistent, or a disposable foreign-user/search-list item yields a stable safe failure before HMAC/decryption or restore mutation.
  - Expose `delete_exact_operator_backup_key(data_dir_id)` for confirmed complete uninstall only. It matches exactly one profile-scoped service/account, requires the held matching data-dir lease plus exact complete-uninstall confirmation, returns an auditable safe result, and verifies that item absent. Normal uninstall/upgrade retain it. If data deletion succeeds but Keychain deletion fails, report `complete_uninstall_keychain_cleanup_failed` with the precise partial state; never claim complete removal. A two-profile test proves deleting profile A leaves profile B's item and backups intact.
  - Add `backend/tests/test_macos_operator_backup.py`. Native CI uses a unique injected test service/account namespace in the runner's data-protection Keychain, asserts the exact test item is absent before starting, exercises actual add/copy/delete and V3 round-trip, and deletes/verifies only that item in `finally`. It must not create a file Keychain, mutate the user's Keychain search list, or use a production service/account. Unit fakes run on non-Darwin hosts.

  Must NOT do: Do not place keys in argv/environment/files/logs, use iCloud-synchronizable items, silently create a new key during restore, allow another UID/platform, or claim a GUI Keychain-prompt experience from headless CI.

  Parallelization: Can parallel: YES | Wave 5 | Blocked by: [7, 9, 10] | Blocks: [18]

  References:
  - Common format: Task 10 `backend/app/desktop/operator_backup.py`.
  - Apple contract: `https://developer.apple.com/documentation/security/keychain_services`.
  - External prompt gate: Scope `External release-candidate gates`.

  Acceptance criteria:
  - On ARM64 macOS, V3 backup/restore succeeds with a disposable unlocked Keychain and no key bytes in argv/environment/log/evidence.
  - Locked/denied/missing/foreign account paths fail before mutation; restore never auto-generates a replacement key.
  - Keychain item attributes equal the fixed service/profile-account/data-protection/accessibility/synchronizable policy; native tests leave the search list byte-for-byte unchanged and remove the unique test item.
  - Normal uninstall preserves the exact profile item; confirmed complete uninstall deletes/verifies only that profile's item, a second profile remains usable, and denied deletion produces the explicit partial-failure result without touching unrelated Keychain items.

  QA scenarios:
  ```text
  Scenario: Real disposable-Keychain V3 round-trip on Apple Silicon
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode macos-key --output-dir "$ATTEMPT_DIR/task-12-native" --receipt "$ATTEMPT_DIR/task-12-native-collection.json"`; the hardcoded ARM64 job runs the complete actual data-protection-Keychain module and deletes only its unique item in `finally`.
    Expected: Exit 0; backup/restore hashes match, attributes include the data-protection Keychain and profile account policy, and the Keychain search list never changes.
    Evidence: $ATTEMPT_DIR/task-12-native-collection.json and $ATTEMPT_DIR/task-12-native/macos/{receipt.json,junit.xml,run.log}

  Scenario: Locked/denied/missing/foreign Keychain item preserves current data
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode macos-key --output-dir "$ATTEMPT_DIR/task-12-native-adversarial" --receipt "$ATTEMPT_DIR/task-12-native-adversarial-collection.json"`; the hardcoded job runs the locked/denied/missing/wrong-profile/duplicate/synchronizable/data-protection/two-profile cases and records before/after hashes.
    Expected: Safe failure before extraction/replacement, identical hashes, no replacement item, and no key/token text in output.
    Evidence: $ATTEMPT_DIR/task-12-native-adversarial-collection.json and $ATTEMPT_DIR/task-12-native-adversarial/macos/{receipt.json,junit.xml,run.log}
  ```

  Adversarial classes: `tamper_wrong_key`, `rollback_failure`, `privacy_canary`, `cleanup_escape`.

  Cleanup: Delete and verify only the unique injected test service/account item, assert the Keychain search list is unchanged, zero buffers, and remove isolated profiles.

  Commit: YES | Message: `feat(backup): protect Mac operator backups with Keychain` | Files: [`backend/app/desktop/macos_key_protection.py`, `backend/tests/test_macos_operator_backup.py`]

- [ ] 13. Implement shared redacted diagnostics and guarded uninstall operations

  What to do:
  - Add `backend/app/desktop/maintenance.py` with platform-neutral `collect_diagnostics`, `acquire_maintenance_lease`, `prepare_uninstall_plan`, and `complete_uninstall_data`. `acquire_maintenance_lease` uses Task 4's authenticated stop/30-second verified-exit path, acquires the same per-data-dir lease, and retains it until the maintenance operation commits/rolls back; backup, restore, normal uninstall, and complete uninstall reject a missing/mismatched/lost lease.
  - Diagnostics includes app/version/build/channel, OS/arch, redacted preflight/readiness, safe directory counts/sizes, migration schema/version/check results, audit-chain verification summary, job status counts, and release manifest hash.
  - Exclude `.env`, database contents, uploads, exports, report bodies, API artifacts, original filenames, runtime state/lock/token/PID/run ID, Keychain/DPAPI material, local usernames, and absolute paths. Reuse safe-category redaction from Task 6 and produce a ZIP with a machine-readable inventory/hash.
  - Normal uninstall creates and validates a user-only deferred-plan/handoff protocol containing run ID, install-manifest SHA, canonical install root, exact manifest-owned relative files/shortcuts, owner PID/creation-time/executable, data-dir ID, persistent lock-file native identity, inherited open file-handle/FD descriptor, and handoff nonce. Task 13 owns only this platform-neutral schema/state machine and tests it with an injected disposable child that acknowledges adoption without deleting a native install. Native Task 17 owns the real Windows copied helper/duplicated handle and Task 18 owns the real macOS copied helper/inherited FD; each must require the nonce-bound `adopted` handshake before the parent closes its duplicate, wait for verified owner exit, revalidate paths/manifest/lease identity, remove only manifest-owned entries, release the child handle, and delete its temp plan/helper. No release/reacquire gap is allowed.
  - Complete uninstall requires the exact in-memory confirmation `DELETE IZ CLINICAL NOTES ANALYZER LOCAL DATA`, verified stop, held outside-root lease, canonical expected/override data root, matching data-dir ID, no symlink/reparse point, and a second containment check immediately before deletion. Hold the outside-root lease until the data root is absent, then release.
  - Route every non-server writer to the shared maintenance lease boundary: `scripts/update-local-admin.ps1`/`backend/app/v2/local_admin_recovery.py`, legacy preflight report writing retained for source checkout, and `scripts/test-alleva-api-connectivity.ps1` report publication must acquire or be passed the same canonical data-dir lease before mutating an operator profile. A writer already running under the owned server process receives an explicit owner lease capability; no helper independently reacquires it. Add a race test for each writer against backup/restore/uninstall and prove exactly one side receives the lease without a partial report/admin mutation.
  - Add `backend/tests/test_desktop_maintenance.py` with synthetic directories, the injected platform-neutral disposable-child handshake, concurrent-launch attempt, symlink/path-swap failpoints, runtime-token/PHI canaries, normal-versus-complete uninstall plan validation, simulated inherited-lease loss, and cleanup escape checks. Do not require either future native helper at this commit.

  Must NOT do: Do not operate without retaining the data-dir lease, include sensitive contents/state, let a concurrent launch enter maintenance, delete data during normal uninstall, delete a running executable from itself, accept a loose confirmation, follow a link, delete a repo/workspace/home root, or force-stop an unverified process.

  Parallelization: Can parallel: YES | Wave 5 | Blocked by: [2, 4, 6, 7, 10] | Blocks: [17, 18]

  References:
  - Current diagnostics: `scripts/collect-diagnostics.ps1:16-197`.
  - Current complete uninstall: `scripts/complete-uninstall-local-data.ps1` and `scripts/Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd`.
  - Redaction/safety: Task 6 `scripts/release_safety.py`; repository Security / PHI rules.
  - Migration verification: `backend/tests/test_v2_schema_contract.py:80-112`.

  Acceptance criteria:
  - Diagnostics ZIP inventory contains only the fixed safe files/fields; injected token/password/patient/path markers are absent from both archive bytes and output.
  - The platform-neutral deferred-plan/state-machine test preserves the entire data-tree hash, proves the injected child cannot acknowledge without the exact nonce/lease descriptor, and proves parent-crash-before/after simulated adoption leaves exactly one modeled lease owner and never authorizes a concurrent same-root launch. Real helper copying, native handle/FD inheritance, installed-file deletion, and parent-crash process proof are mandatory in Tasks 17/18, not claimed here.
  - Complete uninstall removes exactly the validated synthetic data root while the outside-root lease remains held, only after exact confirmation and verified stop.
  - Symlink/reparse/path-swap, wrong data ID, wrong confirmation, running app, home/repo root, and outside-root attempts fail without deletion.

  QA scenarios:
  ```text
  Scenario: Redacted diagnostics and preserve-data uninstall succeed
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode maintenance --output-dir "$ATTEMPT_DIR/task-13-native" --receipt "$ATTEMPT_DIR/task-13-native-collection.json"`.
    Expected: Exit 0 on Windows x64 and macOS arm64; diagnostic inventory is safe, the provider-neutral deferred-plan/adoption protocol preserves data hash and exclusive ownership, confirmed complete uninstall removes only its isolated target, native path/permission assertions pass, and receipts prove cleanup. No future Windows/macOS uninstall helper is invoked.
    Evidence: $ATTEMPT_DIR/task-13-native-collection.json and $ATTEMPT_DIR/task-13-native/{windows,macos}/{receipt.json,junit.xml}

  Scenario: Privacy canary and path-swap deletion attacks fail closed
    Tool:     pytest
    Steps:    Run `PYTHONPATH=backend python -m pytest backend/tests/test_desktop_maintenance.py -k "token_leak or phi_canary or symlink or path_swap or wrong_confirmation or home_root or lease_loss or concurrent_launch or owner_still_running" -q --junitxml="$ATTEMPT_DIR/task-13-maintenance-adversarial.xml"`.
    Expected: Markers never appear in diagnostics/output, outside sentinel survives, and no rejected target changes.
    Evidence: $ATTEMPT_DIR/task-13-maintenance-adversarial.xml
  ```

  Adversarial classes: `backup_token_leak`, `path_case_symlink`, `cleanup_escape`, `privacy_canary`.

  Cleanup: Tests remove only validated temp installs/data roots; preserve outside sentinels until assertions finish.

  Commit: YES | Message: `feat(desktop): share redacted maintenance operations` | Files: [`backend/app/desktop/maintenance.py`, `backend/app/v2/local_admin_recovery.py`, `scripts/update-local-admin.ps1`, `scripts/preflight-windows.ps1`, `scripts/test-alleva-api-connectivity.ps1`, `backend/tests/test_desktop_maintenance.py`]

- [ ] 14. Wire the shared desktop controller from bootstrap through clean shutdown

  What to do:
  - Add `backend/app/desktop/controller.py` with `DesktopController` and async `run()`. Keep `backend/app/desktop_runtime.py` as a tiny argparse/exit-code entrypoint that imports only stdlib plus bootstrap-safe modules until ownership/bootstrap completes.
  - Enforce this order: resolve/canonicalize data root from only the two permitted packaged ambient variables; strip/ignore all other inherited application/configuration/credential variables; call `InstanceCoordinator.acquire` once; if unavailable, wait/poll up to 30 seconds for authenticated same-data-dir control status; if valid, open its ready URL and exit 0; if live-not-ready at deadline, report `desktop_owner_startup_timeout` without eviction; if acquired, retain that exact `DataDirLease`, revalidate/remove stale runtime state, invoke Task 10 restore-journal recovery before reading `.env`, pass the lease/private-storage provider to atomic bootstrap, then preflight/runtime. Only after recovery/bootstrap/preflight lazily import settings/database/routes and call `create_desktop_application()` once.
  - Instantiate `uvicorn.Config`/`uvicorn.Server` directly with the ASGI object, host `127.0.0.1`, selected port, `access_log=False`, Task-7 safe `log_config`, and a bounded graceful-shutdown hook controlled by the controller. Write non-ready state, run `Server.serve()` as a retained task, poll real `/api/readiness`, mark ready, query the bootstrap admin's `must_reset_password`, display the in-memory credential on every launch through the native Task8/Task9 in-process adapter while it remains true, then open the browser. Simulated crashes after env publication and after admin creation but before successful display must redisplay on restart; successful existing password-reset semantics ends the handoff. Browser failure shows the URL and leaves the healthy server running.
  - Add desktop-only ASGI admission/in-flight middleware around business requests: after stop begins, reject new business requests/jobs with `503 desktop_shutdown_in_progress` while allowing authenticated control status; count every admitted request until response-body completion/dependency cleanup. Bind control/signal callbacks to this run ID and `server.should_exit`; map SIGINT/SIGTERM into one shutdown path (the supported Mac user stop surface is Utilities, not an untested Dock-Quit claim). Use one monotonic 15-second budget across in-flight requests, workers, and Uvicorn graceful completion: set `should_exit`, close admissions, cancel jobs, await request/worker drains and `Server.serve()`/lifespan completion. Only when all finish may checkpoint WAL, dispose the engine, remove runtime state, release the lease, and return 0. Any surviving request/worker or incomplete server/lifespan records `stale_or_interrupted`, leaves state/lease open, skips checkpoint/dispose, and invokes top-level immediate process exit so OS death releases DB/lease together.
  - Stop clients accept `202` and share Task 4's one 30-second monotonic state machine: poll authenticated status/identity through second 20; Windows may revalidate and `TerminateProcess` at/after second 20, macOS may revalidate/SIGTERM at second 20 and revalidate/SIGKILL at/after second 25; confirm exit by second 30. Test a survivor that attempts a database write after 15 seconds; the process must be dead, the write absent, the stale state recoverable, and no second owner may acquire before process death.
  - Port behavior: explicit env, then env-file port, then 8000. Different data roots with different ports may run; same port for another data root/unrelated service fails `desktop_port_owned_by_other_process` and never stops it.
  - Add `backend/tests/test_desktop_controller.py` with fresh real subprocesses and isolated roots/ports covering first run, hostile inherited configuration/credential variables, both credential-handoff crash points, simultaneous first launch, second launch, different roots, every restore-journal crash state before config import, stale runtime state, live-not-ready owner, unrelated listener, readiness/browser ordering, correct stop, slow in-flight read/write requests, active jobs, server/lifespan timeout, crash cleanup, and restart persistence. Add real failpoints that kill the owner during an admitted request, during a WAL transaction, and while a registered worker is writing; each next launch must recover SQLite/audit/job state without double ownership or late writes.

  Must NOT do: Do not import config/db/app before bootstrap; do not call `uvicorn.run`; do not open browser before readiness; do not auto-select another port; do not evict live locks or force-kill from the controller's normal path.

  Parallelization: Can parallel: YES | Wave 5 | Blocked by: [1, 2, 3, 4, 5, 7, 8, 9, 10] | Blocks: [15, 16, 21]

  References:
  - Current entrypoint: `backend/app/desktop_runtime.py:12-30`.
  - Factory: Tasks 2/3 `backend/app/desktop/bootstrap.py`, `backend/app/desktop_application.py`.
  - Job drain: Task 5 `ApiHarnessJobService.request_shutdown/drain`.
  - SQLite engine: `backend/app/v2/db.py:16-65`.
  - Current packaged readiness: `scripts/launch-packaged-runtime.cmd:16-32`.

  Acceptance criteria:
  - Fresh-process import sentinel proves no `app.core.config`, `app.v2.db`, route, SQLAlchemy engine, or SQLite file exists before bootstrap result.
  - In packaged mode, hostile inherited `DATABASE_URL`, secret/encryption/admin/API/Alleva/LLM/path variables cannot alter the selected private profile; only data-root and port overrides apply, and no variable name/value or injected exception marker reaches logs/dialogs/evidence. Source mode compatibility tests remain green.
  - One real launch creates one env, one app, one DB init/migration/reevaluation/start audit, becomes ready, opens browser after readiness, and after authenticated stop removes state/frees port while leaving the outside-root lock file present and demonstrably unheld.
  - Concurrent same-root launch opens the original URL and exits 0; different-root/different-port runs concurrently; different-root/same-port and unrelated listeners survive with safe failure.
  - Cooperative in-flight-request/job/server drain uses one 15-second budget and only then checkpoints/releases. A slow cooperative request completes safely before teardown. A noncooperative request or nested worker takes the terminal-process path: stop completes within the 30-second client deadline, scheduled late database writes never land, state remains stale until next-launch recovery, and the lease is never concurrently acquirable.

  QA scenarios:
  ```text
  Scenario: Two real launches converge on one ready instance and stop cleanly
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode controller --output-dir "$ATTEMPT_DIR/task-14-native" --receipt "$ATTEMPT_DIR/task-14-native-collection.json"`.
    Expected: Exit 0 on Windows x64 and macOS arm64; one PID/one init owns each synthetic root, second launch opens the same URL/exits 0, authenticated stop drains and releases port/state/lease, persistent lock file is unheld, restart preserves data, and receipts prove cleanup.
    Evidence: $ATTEMPT_DIR/task-14-native-collection.json and $ATTEMPT_DIR/task-14-native/{windows,macos}/{receipt.json,junit.xml}

  Scenario: Startup race, stale state, live-not-ready owner, and unrelated port cannot be hijacked
    Tool:     pytest
    Steps:    Run `PYTHONPATH=backend python -m pytest backend/tests/test_desktop_controller.py -k "simultaneous or stale or live_not_ready or other_data_dir or unrelated_listener or restore_journal_before_bootstrap or credential_handoff_crash or hostile_inherited_env or inflight_request or wal_crash or worker_crash or lifespan_timeout or noncooperative_late_write or thirty_second_stop_deadline" -q --junitxml="$ATTEMPT_DIR/task-14-controller-adversarial.xml"`.
    Expected: Env is never partial, inherited hostile values are ignored safely, every restore/request/WAL/worker crash recovers before config import, pending credential redisplays, live owner/decoy survives, no DB teardown races an active request, no unrelated PID receives a signal, and each failure leaves a restartable profile without canary leakage.
    Evidence: $ATTEMPT_DIR/task-14-controller-adversarial.xml
  ```

  Adversarial classes: `startup_race`, `stale_state`, `other_data_dir`, `unrelated_port`, `misleading_success_output`.

  Cleanup: Each test uses authenticated stop first; fallback cleanup revalidates test PID identity and temp-root containment before termination/removal.

  Commit: YES | Message: `feat(desktop): wire shared lifecycle controller` | Files: [`backend/app/desktop/controller.py`, `backend/app/desktop_runtime.py`, `backend/app/application.py`, `backend/tests/test_desktop_controller.py`]

- [ ] 15. Rewire Windows double-click launch and stop to the shared controller

  What to do:
  - Change `scripts/launch-packaged-runtime.cmd` to invoke the bundled runtime controller only; it no longer parses `.env`, probes a port, starts a raw process, or owns readiness/browser logic. Preserve exit code and no-pause support.
  - Change `scripts/Start-IZ-Clinical-Notes-Analyzer.cmd`, `scripts/start-windows-local.ps1`, and `scripts/startup-windows-local.ps1` so prepared-package and source-checkout paths both enter `app.desktop_runtime`; source mode may still validate developer tools through source preflight but must use shared ownership/readiness/browser semantics.
  - Change `scripts/Stop-IZ-Clinical-Notes-Analyzer.cmd` and `scripts/stop-windows-local.ps1` so normal/package stop invokes controller `--stop`, authenticates from user-only state, waits for state/port disappearance, and returns 0 when already stopped. Keep old process/Vite discovery only behind explicit `-LegacyCheckoutCleanup`; never run it for installed/package stop.
  - Update `scripts/test-windows-lifecycle.ps1` and `scripts/test-windows-stop.ps1` to launch actual source controller subprocesses, not synthetic command-line-shaped listeners, and assert browser ordering through an injected browser capture.

  Must NOT do: Do not preserve port-only prechecks or `Stop-Process -Force` on the normal path; do not require admin, Python, Node, or Git for the prepared release; do not open browser from CMD/PowerShell before controller readiness.

  Parallelization: Can parallel: YES | Wave 6 | Blocked by: [8, 14] | Blocks: [17, 19, 22, 25]

  References:
  - Packaged launch: `scripts/launch-packaged-runtime.cmd:1-33`.
  - User launcher: `scripts/Start-IZ-Clinical-Notes-Analyzer.cmd:1-42`.
  - Forced stop: `scripts/stop-windows-local.ps1:261-292` and wrapper `scripts/Stop-IZ-Clinical-Notes-Analyzer.cmd:1-29`.
  - Existing tests: `scripts/test-windows-lifecycle.ps1`, `scripts/test-windows-stop.ps1:43-112`.

  Acceptance criteria:
  - Source and packaged Windows double-click paths enter the controller, wait for actual readiness, open the browser exactly once, and a second launch opens the existing instance without a duplicate PID.
  - Normal stop uses authenticated control and leaves unrelated Python/Node/listeners alive; already-stopped is idempotent; the fallback follows Task4's exact identity-revalidated second-20 termination point and confirms exit within the one 30-second end-to-end budget.
  - Source/controller shims require no elevation and preserve exact wrapper switches/exit codes. Prepared-artifact/no-runtime proof belongs to Task 22, after Task 19 creates those bytes.

  QA scenarios:
  ```text
  Scenario: Windows double-click-equivalent start, second start, and clean stop
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode windows-lifecycle --output-dir "$ATTEMPT_DIR/task-15-native" --receipt "$ATTEMPT_DIR/task-15-native-collection.json"`.
    Expected: Exit 0 on Windows x64; real controller becomes ready, browser capture follows readiness, second launch exits 0 with one owner, stop drains, port/state clear, persistent lease file is unheld, restart preserves data, and receipt proves cleanup.
    Evidence: $ATTEMPT_DIR/task-15-native-collection.json and $ATTEMPT_DIR/task-15-native/windows/{receipt.json,lifecycle.json}

  Scenario: Unrelated listener and stale/PID-reuse-like state survive stop
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode windows-lifecycle --output-dir "$ATTEMPT_DIR/task-15-native-adversarial" --receipt "$ATTEMPT_DIR/task-15-native-adversarial-collection.json"`; the fixed mode runs the controller lifecycle plus unrelated-listener/stale/PID-reuse suite.
    Expected: Decoy remains alive/listening, stale state is cleaned only with acquired lock, wrong identity is refused, and no normal path invokes force.
    Evidence: $ATTEMPT_DIR/task-15-native-adversarial-collection.json and $ATTEMPT_DIR/task-15-native-adversarial/windows/{receipt.json,stop-adversarial.json}
  ```

  Adversarial classes: `unrelated_port`, `pid_reuse`, `stale_state`, `misleading_success_output`.

  Cleanup: Scripts call authenticated stop, then revalidate and terminate only their own test processes and remove only synthetic `%TEMP%`/`LOCALAPPDATA` roots.

  Commit: YES | Message: `refactor(windows): route launch and stop through desktop controller` | Files: [`scripts/launch-packaged-runtime.cmd`, `scripts/Start-IZ-Clinical-Notes-Analyzer.cmd`, `scripts/start-windows-local.ps1`, `scripts/startup-windows-local.ps1`, `scripts/Stop-IZ-Clinical-Notes-Analyzer.cmd`, `scripts/stop-windows-local.ps1`, `scripts/test-windows-lifecycle.ps1`, `scripts/test-windows-stop.ps1`]

- [ ] 16. Add Finder-accessible Apple Silicon launch and Utilities lifecycle surfaces

  What to do:
  - Add `backend/app/desktop_utilities.py` as a separate frozen entrypoint. With no arguments it asks the in-process macOS dialog adapter to choose exactly one operation: Install/Upgrade for Me, Stop, Backup, Restore, Collect Diagnostics, Uninstall App, or Complete Uninstall Data; headless CI may pass an explicit operation flag. `Install/Upgrade for Me` treats the two apps adjacent to the running Utilities app as one version/hash-matched suite; if an installed owner exists it performs authenticated stop and obtains/retains the matching maintenance lease, then atomically installs both under `~/Applications/IZ Clinical Notes Analyzer/`, releases the lease, and relaunches only when the prior verified owner was running. It refuses mixed-version source, source equal to target, `/Applications` mutation, or either app outside the verified suite.
  - Main `IZ Clinical Notes Analyzer.app` invokes `app.desktop_runtime:main`; `IZ Clinical Notes Analyzer Utilities.app` invokes `app.desktop_utilities:main`. Utilities Stop reads user-only state, authenticates status/stop, follows Task4's shared 30-second state machine (15-second cooperative drain, SIGTERM at second 20 after revalidation, SIGKILL at/after second 25 only after revalidation, exit by second 30), then shows success/already-stopped/safe failure through the in-process native dialog.
  - Make entrypoints/resource resolution support `/Applications/IZ Clinical Notes Analyzer.app`, paths containing spaces, and read-only mounted DMGs without using CWD. Map SIGTERM to controller shutdown; reopening while ready opens the existing browser URL. Do not claim Dock Quit Apple-event support; Utilities Stop is the supported nontechnical clean-stop surface.
  - Add `scripts/test-macos-lifecycle.sh` and `backend/tests/test_desktop_utilities.py`; headless tests call adapters directly and install both synthetic suite apps into an isolated fake home, while Task 23 launches the actual bundles.

  Must NOT do: Do not ship terminal-only `.sh` as the nontechnical surface, start a second server from Utilities, store the control token outside state, or write within the app/DMG.

  Parallelization: Can parallel: YES | Wave 6 | Blocked by: [9, 14] | Blocks: [18, 20, 23, 25]

  References:
  - Shared entrypoint: Task 14 `backend/app/desktop_runtime.py`.
  - Windows parity: Task 15 launch/stop wrappers.
  - macOS bundle contract: `https://developer.apple.com/documentation/bundleresources/information-property-list`.

  Acceptance criteria:
  - The Utilities Stop contract uses authenticated control, is idempotent, and never exposes state/token; actual Finder accessibility/execution is proven only after Task 20 builds and Task 23 opens the bundle.
  - Source entrypoints under read-only/path-with-spaces fixtures reach readiness and resolve resources/data correctly; second launch reuses it; SIGTERM drains/removes state.
  - Utilities operation selection maps to exactly one shared operation and safe dialog result; cancellation performs no action. Install/upgrade replaces both matched apps as one transaction under the current user's Applications directory and preserves the Application Support profile byte-for-byte.

  QA scenarios:
  ```text
  Scenario: Headless Mac lifecycle exercises main and Utilities entrypoints
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode macos-lifecycle --output-dir "$ATTEMPT_DIR/task-16-native" --receipt "$ATTEMPT_DIR/task-16-native-collection.json"`.
    Expected: Exit 0 on macOS15 arm64; one server starts, second launch reuses it, Utilities stop drains, read-only/path-with-spaces sentinels remain unchanged, and receipt proves exact target plus cleanup.
    Evidence: $ATTEMPT_DIR/task-16-native-collection.json and $ATTEMPT_DIR/task-16-native/macos/{receipt.json,junit.xml,lifecycle.json}

  Scenario: Cancelled operation, wrong token, and read-only bundle cannot mutate state/resources
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode macos-lifecycle --output-dir "$ATTEMPT_DIR/task-16-native-adversarial" --receipt "$ATTEMPT_DIR/task-16-native-adversarial-collection.json"`; the fixed mode runs the named cancellation/token/read-only/second-launch/deadline cases on ARM64 macOS.
    Expected: No unintended operation occurs, owner remains alive where expected, resource tree hash is unchanged, and safe dialog codes are emitted.
    Evidence: $ATTEMPT_DIR/task-16-native-adversarial-collection.json and $ATTEMPT_DIR/task-16-native-adversarial/macos/{receipt.json,junit.xml,adversarial.json}
  ```

  Adversarial classes: `bundle_write`, `wrong_control_token`, `startup_race`, `cleanup_escape`.

  Cleanup: Use authenticated stop and remove only isolated test profiles; never delete mounted/system Applications content in this task.

  Commit: YES | Message: `feat(macos): add Finder lifecycle utilities entrypoint` | Files: [`backend/app/desktop_utilities.py`, `backend/tests/test_desktop_utilities.py`, `scripts/test-macos-lifecycle.sh`]

- [ ] 17. Route Windows backup, restore, diagnostics, and uninstall through shared operations

  What to do:
  - Extend `backend/app/desktop_runtime.py` with one closed `maintenance --request-file <path>` command in addition to normal start/stop. The request is canonical JSON with exactly `schema`, `operation` (`backup|restore|diagnostics|uninstall|complete-uninstall`), the operation-specific selected input/output path, optional exact complete-uninstall confirmation, canonical data-dir ID, and nonce; reject unknown/unused fields or operations. The entrypoint opens a current-user-private, non-link request file by native identity, verifies the contained data-dir ID after canonical resolution, deletes/fsyncs that file before dispatch, then invokes Task 13's authenticated-stop/held-lease operation. It imports no config/database/FastAPI module before the lease and bootstrap/recovery boundary, exposes no arbitrary module/function/command execution, redacts paths from output, and returns fixed operation exit codes. Add `backend/tests/test_desktop_runtime_maintenance.py` for the real source entrypoint and the frozen-argument contract.
  - Replace implementation bodies of `scripts/backup-local-data.ps1`, `scripts/restore-local-data.ps1`, `scripts/collect-diagnostics.ps1`, and `scripts/complete-uninstall-local-data.ps1` with thin argument/dialog shims that create that private request atomically, invoke the bundled runtime (or the same source entrypoint in checkout mode), and verify request deletion. Preserve existing CMD filenames and public switches needed by current test/install flows.
  - Backup/restore/uninstall call Task 13's `acquire_maintenance_lease`: authenticated stop, verified exit, acquire/retain the exclusive lock-file handle, then invoke the common operation. `-NoStop` is removed; tests may inject only a real already-held temp-root lease descriptor. Add explicit `-BackupOutputRoot`/`-RestoreInputPath` test hooks and a dialog-selected destination provider so tests never redirect or touch the real Windows Known Folder Documents; production default still uses the actual Documents known folder. Create V3 with DPAPI. Restore accepts V3/runtime-generated current-user V2, validates fully, rejects outside-root mutable config, performs journaled rollback-safe replace under the lease, restarts only after release/success, and refuses cross-OS.
  - Diagnostics and uninstall use Task 13. Add fixed `scripts/uninstall-windows-release.ps1`; normal uninstall copies it and a private manifest plan to validated `%TEMP%/iz-cna-uninstall-<run-id>`, inherits/duplicates the held exclusive file handle, completes nonce-bound adoption before the parent closes, then removes only manifest-owned app/shortcut entries, preserves data, releases the child handle, and self-cleans. Complete uninstall retains the outside-root handle through data-root deletion. Task 19, which owns the installer builder, wires the generated installer's pre-upgrade leased V3 backup and abort-on-failure behavior; Task 17 exposes/tests the shared maintenance operation it will call but does not edit or claim the generated installer.
  - Update `scripts/test-windows-lifecycle.ps1` to execute real V3/runtime-generated V2 backup/restore, diagnostic scan, deferred normal uninstall preservation, complete-uninstall deletion, and a concurrent-launch attempt against synthetic data.

  Must NOT do: Do not retain a second crypto/archive implementation in PowerShell, operate without a held lease, release/reacquire during deferred uninstall, package runtime state, print credentials, restore cross-OS, delete a running helper from inside the install root, or delete local data during normal uninstall.

  Parallelization: Can parallel: YES | Wave 7 | Blocked by: [11, 13, 15] | Blocks: [19, 22, 25]

  References:
  - Current operator tools: `scripts/backup-local-data.ps1:1-124`, `scripts/restore-local-data.ps1:1-110`, `scripts/collect-diagnostics.ps1:1-197`.
  - Installer upgrade: `scripts/build-windows-installer.ps1:645-800` generated install semantics.
  - Common implementations: Tasks 10, 11, 13.

  Acceptance criteria:
  - The actual frozen/source `desktop_runtime maintenance --request-file` command accepts only the five fixed operations and exact per-operation schema, deletes the private request before execution, acquires/retains the Task-13 lease before mutation, and returns stable exit codes; arbitrary command/module names, extra fields/arguments, wrong data ID, permissive/link/swapped requests, early config/db import, and reused requests fail without mutation.
  - Windows CMD/PowerShell tools invoke that owned shared Python command only while holding the data-dir lease; real V3 DPAPI and runtime-generated V2 round-trip; cross-OS and tampered inputs preserve current data.
  - Diagnostics contains no forbidden canary/runtime token and normal uninstall preserves the profile hash; complete uninstall removes only confirmed synthetic target.
  - Deferred helper adopts the original exclusive file handle before the installed caller exits, removes only manifest-owned entries, cleans its temp plan/script, and rejects a concurrent same-root launch for the whole operation, including parent-exit failpoints.
  - The shared leased V3 backup operation returns a stable nonzero failure before any caller-supplied replacement callback can run; Task 19 proves this against the generated installer and installed app tree.

  QA scenarios:
  ```text
  Scenario: Nontechnical Windows tools complete the full synthetic lifecycle
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode windows-maintenance --output-dir "$ATTEMPT_DIR/task-17-native" --receipt "$ATTEMPT_DIR/task-17-native-collection.json"`.
    Expected: Exit 0 on Windows x64; every wrapper enters the exact bundled/source `desktop_runtime maintenance` request-file boundary, the request is consumed privately, V3 backup/restore, V2 restore, diagnostics, preserve-data uninstall, and confirmed complete uninstall produce asserted filesystem/database results, and receipt proves cleanup.
    Evidence: $ATTEMPT_DIR/task-17-native-collection.json and $ATTEMPT_DIR/task-17-native/windows/{receipt.json,maintenance.json}

  Scenario: Tamper, wrong scope, backup failure, token canary, and path escape are harmless
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode windows-maintenance --output-dir "$ATTEMPT_DIR/task-17-native-adversarial" --receipt "$ATTEMPT_DIR/task-17-native-adversarial-collection.json"`; the fixed mode runs `backend/tests/test_desktop_runtime_maintenance.py` plus the maintenance adversarial suite, including arbitrary-operation, extra-field, wrong-data-ID, link/swap, reused-request, and early-import cases.
    Expected: Current tree hash is unchanged for rejected operations, no arbitrary command is dispatched, the private request is consumed or safely rejected, the injected replacement callback is never called on backup failure, outside sentinel survives, and markers are absent from diagnostics/output. This task makes no generated-installer claim.
    Evidence: $ATTEMPT_DIR/task-17-native-adversarial-collection.json and $ATTEMPT_DIR/task-17-native-adversarial/windows/{receipt.json,maintenance-adversarial.json}
  ```

  Adversarial classes: `tamper_wrong_key`, `rollback_failure`, `backup_token_leak`, `cleanup_escape`.

  Cleanup: Authenticated stop; verify temp/Documents test override containment before removing test backups/profiles.

  Commit: YES | Message: `refactor(windows): use shared maintenance operations` | Files: [`backend/app/desktop_runtime.py`, `backend/tests/test_desktop_runtime_maintenance.py`, `scripts/backup-local-data.ps1`, `scripts/restore-local-data.ps1`, `scripts/collect-diagnostics.ps1`, `scripts/complete-uninstall-local-data.ps1`, `scripts/uninstall-windows-release.ps1`, `scripts/Backup-IZ-Clinical-Notes-Analyzer.cmd`, `scripts/Restore-IZ-Clinical-Notes-Analyzer.cmd`, `scripts/Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd`, `scripts/Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd`, `scripts/test-windows-lifecycle.ps1`]

- [ ] 18. Wire macOS Utilities backup, restore, diagnostics, and uninstall flows

  What to do:
  - Extend `backend/app/desktop_utilities.py` with the Task-9 in-process AppKit dialogs: choose backup destination, choose restore file, confirmation/result dialogs, diagnostics save location, preserve-data uninstall, exact-phrase complete uninstall, and Install/Upgrade for Me. User-selected paths stay in process as NSString/NSURL values and are canonicalized before use; no credential/path/value enters AppleScript, a child argv, environment, log, or exception.
  - Use Task 12 Keychain adapter and Task 10 V3 core only after Task 13 authenticates stop, verifies exit, acquires the outside-root `flock` lease, and retains it through commit/rollback. Restore accepts macOS V3 only, rejects outside-root mutable config, performs journaled validate-first rollback under the lease, and offers restart after release/success. Keychain locked/denied/missing prompts map to safe guidance and no data mutation.
  - Add fixed `packaging/macos/uninstall-macos-release.sh`. Normal uninstall copies it and a mode-`0600` manifest plan to a validated temp directory, inherits the held `flock` FD, completes nonce-bound adoption before parent close, removes both installed bundles only from the matched `~/Applications/IZ Clinical Notes Analyzer/` suite plus manifest-owned support entries while preserving Application Support data and that profile's Task-12 Keychain item, releases the lease, and self-cleans. Complete uninstall retains the lease until the validated data root is absent, then deletes/verifies only that profile-scoped operator-backup Keychain item; denied key deletion reports the explicit partial state. DMG copies and any other profile/key remain untouched.
  - Add `scripts/test-macos-maintenance.sh` that drives explicit headless operations with a unique injected data-protection Keychain test item and synthetic profile, never changing the search list; visible chooser/prompt usability remains the external clean-Mac gate.

  Must NOT do: Do not require Terminal for the shipped user flow, operate unlocked or release/reacquire a lease, support cross-OS/V2 Windows restore, expose Keychain data, delete mounted DMG content, or treat headless CI as proof of Finder/dialog usability.

  Parallelization: Can parallel: YES | Wave 7 | Blocked by: [12, 13, 16] | Blocks: [20, 23, 25]

  References:
  - Utilities: Task 16 `backend/app/desktop_utilities.py`.
  - Keychain/core: Tasks 10/12.
  - Windows behavioral parity: Task 17 scripts/tests.

  Acceptance criteria:
  - On native ARM64 macOS, explicit headless utilities perform actual V3 backup/restore, redacted diagnostics, preserve-data uninstall, and confirmed data uninstall with asserted filesystem/SQLite results.
  - Wrong-platform/tampered/Keychain failure/path escape leaves the profile unchanged and no token/key marker leaks.
  - Deferred helper inherits the original `flock` FD, rejects concurrent launch until cleanup, removes only installed bundles/manifest-owned entries, and deletes its temp plan/script; normal uninstall preserves the exact Keychain item while complete uninstall deletes/verifies it or reports partial failure.
  - Finder-visible operations are present in the Utilities app; final visible usability is labeled external until clean-Mac gate evidence exists.

  QA scenarios:
  ```text
  Scenario: ARM64 macOS Utilities complete synthetic maintenance lifecycle
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode macos-maintenance --output-dir "$ATTEMPT_DIR/task-18-native" --receipt "$ATTEMPT_DIR/task-18-native-collection.json"`.
    Expected: Exit 0 on macOS15 arm64; all real operations and preservation/deletion assertions pass with a disposable test Keychain, no Terminal-only user artifact is required by packaged inventory, and receipt proves cleanup.
    Evidence: $ATTEMPT_DIR/task-18-native-collection.json and $ATTEMPT_DIR/task-18-native/macos/{receipt.json,maintenance.json}

  Scenario: Wrong scope, Keychain denial, archive tamper, and DMG/path escape fail closed
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode macos-maintenance --output-dir "$ATTEMPT_DIR/task-18-native-adversarial" --receipt "$ATTEMPT_DIR/task-18-native-adversarial-collection.json"`; the fixed mode runs the Keychain/tamper/path adversarial suite.
    Expected: Rejected operations preserve tree hash/outside sentinels/DMG contents, leave no rollback temp, and emit only safe codes.
    Evidence: $ATTEMPT_DIR/task-18-native-adversarial-collection.json and $ATTEMPT_DIR/task-18-native-adversarial/macos/{receipt.json,maintenance-adversarial.json}
  ```

  Adversarial classes: `tamper_wrong_key`, `rollback_failure`, `path_case_symlink`, `backup_token_leak`.

  Cleanup: Delete/verify only the unique Task-12 test item without changing the Keychain search list, use authenticated stop, unmount only the test-created DMG, and delete only synthetic profiles.

  Commit: YES | Message: `feat(macos): wire Finder maintenance utilities` | Files: [`backend/app/desktop_utilities.py`, `backend/tests/test_desktop_utilities.py`, `packaging/macos/uninstall-macos-release.sh`, `scripts/test-macos-maintenance.sh`]

- [ ] 19. Build the Windows x64 release folder and ZIP from explicit native inputs

  What to do:
  - Add `packaging/windows/iz-cna-windows.spec` for CPython `3.12.10`/PyInstaller `6.16.0` and retain `onefile` for Lane 1. Entrypoint is `app.desktop_runtime`; include only Task 6 common resources at their declared destinations, required hidden imports/Passlib data, and no local data/config. Do not upgrade PyInstaller in this refactor.
  - Refactor `scripts/build-windows-installer.ps1` to verify clean exact source, run backend/frontend suites/build, invoke Task 6 staging/scans, build the native x64 runtime, generate per-user install/launch/stop/Utilities shortcuts/tools, write a hashed release manifest, and create/scan the release folder and ZIP. `-EvidencePath <path>` also writes adjacent `<stem>-folder-scan.json` and `<stem>-zip-scan.json`. Remove `Copy-RepoContent` from the artifact path and disallow `-AllowDirty` for build.
  - Preserve `%LOCALAPPDATA%/Programs/IZ Clinical Notes Analyzer`, pre-upgrade V3 backup, rollback-on-install-failure, user-data preservation, Start Menu/Desktop shortcuts, no elevation, and existing release-folder/ZIP distribution. The generated installer must call Task 17's shared leased V3 operation after verified stop and before the first install-tree/journal/shortcut mutation; any backup cancel/failure aborts with the old app tree/manifest/shortcuts/profile byte-identical and relaunches the verified old launcher iff it had been running. Implement the subsequent install as a journaled sibling-tree transaction: verify/stage the complete new manifest, record installed old manifest/tree/shortcut hashes, move old install to a rollback sibling, move new into place, create exact shortcuts, and fsync each intent/result; only then delete old. Every failpoint restores the complete old app tree, manifest, shortcuts, and, when it was running, relaunches the verified old launcher before reporting upgrade failure.
  - Support transition only from the exact base release (`2.0.0-beta.2` / build `2026.07.11.1`) or a manifest-compatible build created by this plan. For the legacy base, verify installed root, manifest and executable hashes; enumerate candidate PIDs by full executable path, then revalidate PID + creation time + path + hash before stopping only that installed runtime. Never infer ownership from the fixed port and never stop an unrelated listener. After verified exit, run WAL checkpoint/integrity/foreign-key checks and the held-lease V3 backup before replacing files. Test by building/installing the exact base commit artifact, launching it, upgrading, and injecting rollback after each stop/rename/shortcut state.
  - Required payload inventory is exactly Task 6's Windows list, including `release-manifest.json` plus detached `release-manifest.sha256`; ZIP entries live under the one top-level `IZ Clinical Notes Analyzer/` directory and nowhere else. Validate raw central-directory names before extraction and then compare staged/extracted hashes. Neither final payload may contain source, venv, node_modules, traversal-capable reparse points, cloud placeholders, duplicate/aliased entries, or runtime profile.

  Must NOT do: Do not convert to MSI/MSIX, switch packaging mode in Lane 1, install system-wide, allow dirty builds, mirror the repo, or assert success without launching the built EXE in Task 22.

  Parallelization: Can parallel: YES | Wave 8 | Blocked by: [6, 15, 17] | Blocks: [21, 22, 24, 25]

  References:
  - Current builder: `scripts/build-windows-installer.ps1:1-490,880-971`.
  - Current PyInstaller: `scripts/build-windows-installer.ps1:358-389` (`--onefile`).
  - Manifest/install contract: `scripts/build-windows-installer.ps1:410-437,645-800,919-951`.
  - Dependencies: `backend/requirements-build.txt:1-2`, `backend/requirements-desktop.txt` from Task 8.

  Acceptance criteria:
  - Native Windows x64 build exits 0 from exact clean commit, `dumpbin`/PowerShell PE inspection reports AMD64, required inventory/hashes match, and both folder/ZIP safety scans pass.
  - Extracting the raw-name-validated ZIP into an independent path containing spaces produces the same declared file hashes as the staged folder; root layout and detached manifest digest are exact, and both copies are retained for Task 22 execution.
  - An unlisted benign file and every forbidden canary placed in the repo/staging fixture are absent/rejected; build refuses dirty tracked source.
  - Exact-base running upgrade and every journal failpoint preserve profile bytes; injected pre-upgrade backup cancel/failure occurs before the first replacement mutation and restores/relaunches the prior running state, every later failure restores/relaunches the prior app tree/manifest/shortcuts, and an unrelated fixed-port listener is never signaled. Install/upgrade requires no admin or external runtime.

  QA scenarios:
  ```text
  Scenario: Clean native Windows release folder and ZIP build
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode windows-package --output-dir "$ATTEMPT_DIR/task-19-native" --receipt "$ATTEMPT_DIR/task-19-native-collection.json"`; the hardcoded Windows job invokes the exact builder with expected HEAD and uploads the scanned folder/ZIP plus receipt.
    Expected: Exit 0; real EXE/folder/ZIP exist, hashes/inventory/AMD64 match, scanners pass, and evidence identifies the exact commit.
    Evidence: $ATTEMPT_DIR/task-19-native-collection.json and $ATTEMPT_DIR/task-19-native/windows/{receipt.json,build.json,folder-scan.json,zip-scan.json}

  Scenario: Dirty source, failed pre-upgrade backup, unlisted file, and forbidden payload cannot emit or install a release
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode windows-package --output-dir "$ATTEMPT_DIR/task-19-native-adversarial" --receipt "$ATTEMPT_DIR/task-19-native-adversarial-collection.json"`; the hardcoded mode runs the builder's isolated backup-cancel/backup-fail and `-SafetyCanaryTest` cases after preserving the valid artifact and installed-base hashes.
    Expected: Backup cancel/failure leaves the installed tree/manifest/shortcuts/profile unchanged and relaunches only the verified prior owner; every packaging canary fails before final ZIP publication, the sensitive marker is redacted, and the prior valid release artifact hash remains unchanged.
    Evidence: $ATTEMPT_DIR/task-19-native-adversarial-collection.json and $ATTEMPT_DIR/task-19-native-adversarial/windows/{receipt.json,safety-canary.json}
  ```

  Adversarial classes: `dirty_worktree`, `forbidden_release_canary`, `wrong_architecture`, `misleading_success_output`.

  Cleanup: Builder cleans only validated `dist/windows-release` intermediates it created; retain final artifact/evidence and never touch user data.

  Commit: YES | Message: `build(windows): produce allowlisted per-user release` | Files: [`packaging/windows/iz-cna-windows.spec`, `scripts/build-windows-installer.ps1`, `backend/tests/test_windows_release_manifest.py`]

- [ ] 20. Build native ARM64 macOS app bundles and DMG

  What to do:
  - Add `packaging/macos/iz-cna-macos.spec` for main and Utilities ARM64 `.app` bundles, `packaging/macos/entitlements.plist` as an exact empty `<dict/>` (no sandbox, JIT, unsigned-memory, library-validation, or Keychain-group entitlement), `packaging/macos/dmg-layout.json`, and `scripts/build-macos-release.sh`.
  - Set `MACOSX_DEPLOYMENT_TARGET=14.0`, build natively on the explicit `macos-15` ARM64 runner, and fail unless every Mach-O is arm64 with no x86_64 slice. Main Info.plist uses bundle ID `com.r3recoveryservices.izclinicalnotesanalyzer`; Utilities uses `.utilities`; both use `LSMinimumSystemVersion=14.0` and `CFBundleShortVersionString=2.0.0`. Map build `YYYY.MM.DD.N` to numeric `CFBundleVersion=YYYY.M.(D*3+N-1)` with `1<=N<=3`; fail outside those bounds. Current build `2026.07.11.1` therefore maps to `2026.7.33`; app-visible semver/build remain unchanged from `VERSION.json`.
  - Preserve PyInstaller's required framework symlink structure only when every link is relative, manifest-enumerated, acyclic, resolves within the same `.app`, and its resolved file hash matches; reject absolute/escape/unlisted links. Ad-hoc sign every nested Mach-O/framework/extension inner-to-outer, verify each, then sign/verify each outer app. Create a read-only compressed DMG containing exactly both apps, Task 6's Read Me, and the one `Applications -> /Applications` root link; ad-hoc sign/verify the DMG and scan mounted contents without following an escaping link.
  - Implement `Install/Upgrade for Me` as a two-bundle suite transaction rooted at `~/Applications/IZ Clinical Notes Analyzer/`: verify the mounted/read-only source contains both version/hash-matched apps, stage both as siblings, journal old/new suite inventories, move the existing suite to a rollback sibling, rename the complete new suite into place, fsync parent, and only then remove old. Never merge-copy into an existing `.app`; every crash failpoint leaves either the complete old pair or complete new pair, restores the old pair on declared failure, and preserves the Application Support profile hash. `/Applications` is optional/manual and never required or mutated by the no-admin surface.

  Must NOT do: Do not cross-build from Windows/Linux, emit Intel/universal2, use App Store packaging/sandbox, derive data from bundle/CWD, embed Developer credentials in scripts, or claim notarization here.

  Parallelization: Can parallel: YES | Wave 8 | Blocked by: [6, 16, 18] | Blocks: [21, 23, 24, 25]

  References:
  - PyInstaller macOS: `https://pyinstaller.org/en/stable/usage.html#building-macos-app-bundles`.
  - Apple metadata: `https://developer.apple.com/documentation/bundleresources/information-property-list`.
  - Version sources: `VERSION`, `VERSION.json`, `frontend/package.json:4`.
  - Shared allowlist: Task 6 `config/release/desktop-package-manifest.json`.

  Acceptance criteria:
  - Native build on the macOS 15 ARM64 engineering runner exits 0; `file`/`lipo -info` show ARM64 only; plist IDs/version/minimum OS equal fixed values; resource/inventory hashes match. This proves a 14.0 deployment target, not execution on macOS 14 hardware.
  - `hdiutil verify`, mount, Task 6 scan, ad-hoc `codesign --verify --deep --strict`, and actual bundle launch smoke all pass; app works from a read-only mounted DMG and installed path with spaces without writing there.
  - Mounted DMG has exactly the Applications link plus the manifest-valid internal framework graph; every internal link is relative/contained/hashed/acyclic, every Mach-O is arm64-only, exact empty entitlements are verified, and scanner never dereferences outside a bundle/DMG root.
  - No-admin two-app suite installation/atomic replacement under an isolated `~/Applications` preserves the Application Support tree hash and has rollback proof at every rename boundary; no stale file from the prior app and no local profile/secret/evidence appears in bundles/DMG.

  QA scenarios:
  ```text
  Scenario: Native ARM64 app bundles and mounted DMG are executable and safe
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode macos-package --output-dir "$ATTEMPT_DIR/task-20-native" --receipt "$ATTEMPT_DIR/task-20-native-collection.json"`; the hardcoded explicit `macos-15` ARM64 job invokes the exact builder with expected HEAD and uploads the scanned app pair/DMG plus receipt.
    Expected: Exit 0; both actual apps and DMG exist, ARM/plist/resource/hash/scanner/ad-hoc-sign checks pass, and mounted launch reaches readiness.
    Evidence: $ATTEMPT_DIR/task-20-native-collection.json and $ATTEMPT_DIR/task-20-native/macos/{receipt.json,build.json,app-scan.json,dmg-scan.json,mounted-scan.json}

  Scenario: Wrong architecture, dirty source, unlisted file, and bundle-write canaries fail
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-native-bootstrap.py --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode macos-package --output-dir "$ATTEMPT_DIR/task-20-native-adversarial" --receipt "$ATTEMPT_DIR/task-20-native-adversarial-collection.json"`; the hardcoded ARM64 mode runs `build-macos-release.sh --safety-canary-test` after preserving the valid DMG hash.
    Expected: Each isolated canary is detected before DMG publication; read-only/bundle sentinels do not change; previous valid artifact hash remains unchanged.
    Evidence: $ATTEMPT_DIR/task-20-native-adversarial-collection.json and $ATTEMPT_DIR/task-20-native-adversarial/macos/{receipt.json,safety-canary.json}
  ```

  Adversarial classes: `wrong_architecture`, `dirty_worktree`, `forbidden_release_canary`, `bundle_write`.

  Cleanup: Unmount only the script-created volume, validate `dist/macos-release` before cleanup, retain final DMG/evidence, and restore no user Keychain/profile state.

  Commit: YES | Message: `build(macos): produce native ARM64 app DMG` | Files: [`packaging/macos/iz-cna-macos.spec`, `packaging/macos/entitlements.plist`, `packaging/macos/dmg-layout.json`, `scripts/build-macos-release.sh`]

- [ ] 21. Expand CI into shared and native desktop lanes with real receipts

  What to do:
  - Refactor `.github/workflows/ci.yml` into shared backend/frontend tests on Ubuntu, Windows x64 portability tests on `windows-2022`, Apple Silicon tests on explicit `macos-15` with `uname -m`/Python `arm64` guards, and common dependency/resource/security checks. Do not use the retirement-prone `macos-14` label or `macos-latest`; application deployment target remains macOS 14.
  - Add `.python-version`=`3.12.10`, `.node-version`=`20.19.4`, and `backend/requirements-lock/shared-py312.txt`. Native jobs install Task 8/9 platform locks with `pip --require-hashes`; shared jobs use the shared hashed closure; frontend uses `npm ci`. Receipts record installed distribution/wheel filenames, versions, hashes, and a canonical closure hash; builders fail on any interpreter/tool/closure mismatch.
  - Pin every third-party action by full commit: `actions/checkout@1af3b93b6815bc44a9784bd300feb67ff0d1eeb3`, `actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405`, `actions/setup-node@2028fbc5c25fe9cf00d9f06a71cc4710d4507903`, `actions/upload-artifact@bbbca2ddaa5d8feaa63e36b76fdaad77386f024f`, and `actions/download-artifact@70fc10c6e5e1ce46ad2ea6f2b72d43f7d47b13c3`; the workflow/receipt schema rejects tags or changed pins.
  - Add `scripts/ci/write-desktop-receipt.py` plus `backend/tests/test_desktop_receipt.py` with a strict versioned receipt schema, exit-code/artifact-hash recomputation, required check IDs, and misleading-PASS canaries. Add `frontend/e2e/packaged-artifact-contract.spec.mjs` for real Chromium login/password reset, route navigation, synthetic upload/checklist/dashboard/rosters, unauthenticated denial, persistence, and logout against a packaged runtime.
  - Add `frontend/playwright.desktop.config.mjs` dedicated to packaged QA, with the repository Playwright package's pinned Chromium (no `channel: 'chrome'`, system browser, or moving executable), fixed viewport/locale/timezone/animations policy, and JSON output. Native jobs run `npm exec playwright install chromium`, record Playwright package version, browser revision, and binary SHA-256, and then invoke this config from `frontend/`.
  - Add `.github/workflows/desktop-artifacts.yml` at this task with reusable native builders from Tasks 19/20 and only self-contained basic artifact checks already available now: architecture/inventory/signature scan, process launch to readiness/version/unauthenticated denial, authenticated stop, and cleanup. Tasks 22/23 later add their full lifecycle scripts and extend this workflow. A Task-21 commit must pass without any forward file. Each basic receipt contains commit/tree SHA, `dirty=false`, workflow run/attempt/job IDs, runner identity/image/OS/arch, lock-closure hash, commands/exit codes, artifact IDs/digests/hashes/inventory/architecture, scanner hashes, and cleanup.
  - Configure each new engineering workflow with `on.push.branches: ['codex-ci/**']`; do not rely on a manual-only event, because a newly added workflow cannot use that event until it exists on the default branch. Add `scripts/ci/dispatch-desktop-workflow.py` accepting exactly `--workflow`, `--commit`, `--repository`, `--repository-id`, `--remote`, `--mode {basic,failure-canary,docs,full}`, optional `--failure-canary`, `--output-dir`, and `--receipt`; the canary is required only for failure-canary mode. It reruns the Task-1 fixed-identity preflight and uses only the named remote. In an isolated temporary worktree it creates canonical `.ci/desktop-request.json` containing schema, repository ID, correlation ID, requested workflow path/blob SHA, coordinator/source/control/candidate SHAs, mode, canary, and nonce; publishes every source/control/candidate ref first and verifies it with `git ls-remote`; then creates/publishes the trigger commit/ref under `codex-ci/<correlation-id>/trigger` last. The push workflow reads the request from the event commit, verifies every recorded repository/ref/SHA/blob/request hash, checks out only the requested target SHA into a separate directory, and records event/trigger/target/workflow hashes. The dispatcher selects the exact push-event run by repository ID + trigger SHA + correlation ID, never latest-by-branch, then downloads by artifact ID/digest and deletes all temporary refs in `finally`; authorization/ref-cleanup failure is a failed receipt.
  - Add concurrency cancellation for superseded PR runs, but never cancel protected release jobs. Live Alleva tests remain off and use synthetic/mock transports only.

  Must NOT do: Do not treat Ubuntu as native desktop proof, use `macos-latest`, run Intel macOS, use real credentials/PHI, trust printed PASS without exit/artifact assertions, or allow artifact jobs to skip scanners.

  Parallelization: Can parallel: NO | Wave 9 | Blocked by: [1, 6, 8, 9, 14, 19, 20] | Blocks: [22, 23, 24, 26]

  References:
  - Current Ubuntu-only workflow: `.github/workflows/ci.yml:7-33`.
  - Frontend scripts: `frontend/package.json:6-12`; Playwright: `frontend/playwright.config.mjs:3-16`.
  - Backend commands: repository `AGENTS.md` How to run checks.
  - GitHub ARM64 labels: `https://docs.github.com/en/actions/reference/runners/github-hosted-runners`.

  Acceptance criteria:
  - A PR or nonce push-trigger run executes Ubuntu, Windows x64, and explicit `macos-15`; macOS asserts both `uname -m` and Python `platform.machine()` are arm64; each job has a schema-valid basic receipt and fails on nonzero command, lock-closure drift, request/ref/workflow mismatch, or missing artifact/evidence/hash.
  - Dependency installs use lock/pin files; frontend uses `npm ci`; external network at application runtime and live Alleva credentials are absent.
  - A synthetic job that prints PASS then exits nonzero makes the workflow fail and uploads no approved receipt.

  QA scenarios:
  ```text
  Scenario: Three-OS CI executes real shared/native test commands
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-desktop-workflow.py --workflow desktop-artifacts.yml --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode basic --output-dir "$ATTEMPT_DIR/task-21-ci" --receipt "$ATTEMPT_DIR/task-21-ci-collection.json"`.
    Expected: Ubuntu, Windows x64, and macOS arm64 jobs exit 0; receipts share one commit and contain asserted command/artifact fields.
    Evidence: $ATTEMPT_DIR/task-21-ci-collection.json, $ATTEMPT_DIR/task-21-ci/ubuntu/receipt.json, $ATTEMPT_DIR/task-21-ci/windows/receipt.json, and $ATTEMPT_DIR/task-21-ci/macos/receipt.json

  Scenario: Wrong architecture and misleading-success canary fail the job
    Tool:     GitHub Actions CLI
    Steps:    Run `python -m pytest backend/tests/test_desktop_receipt.py -q --junitxml="$ATTEMPT_DIR/task-21-receipt-adversarial.xml"` and `python scripts/ci/dispatch-desktop-workflow.py --workflow desktop-artifacts.yml --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode failure-canary --failure-canary wrong_arch_and_exit23 --output-dir "$ATTEMPT_DIR/task-21-ci-adversarial" --receipt "$ATTEMPT_DIR/task-21-ci-adversarial-collection.json"`; the second command must exit nonzero.
    Expected: Run is failed, no success receipt/artifact is published, and evidence identifies safe reason codes without marker values.
    Evidence: $ATTEMPT_DIR/task-21-receipt-adversarial.xml and $ATTEMPT_DIR/task-21-ci-adversarial-collection.json
  ```

  Adversarial classes: `wrong_architecture`, `misleading_success_output`, `privacy_canary`, `stale_state`.

  Cleanup: Workflow always stops test runtimes, deletes temp profiles and unique injected Keychain test items without changing search lists, and uploads only redacted evidence before runner teardown; dispatcher deletes the verified temporary refs/worktree in `finally`.

  Commit: YES | Message: `ci(desktop): add Windows and ARM64 Mac lanes` | Files: [`.python-version`, `.node-version`, `backend/requirements-lock/shared-py312.txt`, `.github/workflows/ci.yml`, `.github/workflows/desktop-artifacts.yml`, `scripts/ci/write-desktop-receipt.py`, `scripts/ci/dispatch-desktop-workflow.py`, `backend/tests/test_desktop_receipt.py`, `frontend/playwright.desktop.config.mjs`, `frontend/e2e/packaged-artifact-contract.spec.mjs`]

- [ ] 22. Execute the exact Windows release artifact through its full lifecycle

  What to do:
  - Add `scripts/test-windows-packaged-artifact.ps1`. It consumes Task 19's staged folder/ZIP, validates raw ZIP names/root layout before extraction, verifies detached manifest digest/inventory/AMD64, extracts to a second path with spaces, and executes the lifecycle once from each payload. Install to synthetic per-user paths, pass the explicit Task-17 backup/restore destination hooks (never fake Windows Known Folder Documents), and launch the exact bundled EXE with developer Python/Node/Git removed from PATH.
  - Drive real readiness/version, unauthenticated denial, generated bootstrap credential handoff through an injected dialog sink, first login/password change, synthetic upload/deterministic checklist, dashboard/rosters, persistence restart, second launch, unrelated listener, authenticated stop with active cooperative and noncooperative jobs, V3/runtime-generated V2 backup/restore, diagnostics scan, upgrade rollback, deferred normal uninstall preservation, and complete uninstall deletion.
  - For each payload, the script enters `frontend/`, runs `npm exec playwright install chromium`, verifies the Task-21 revision/binary hash, and invokes `npm exec -- playwright test e2e/packaged-artifact-contract.spec.mjs --config playwright.desktop.config.mjs --reporter=json`; do not use root `npx`, a system Chrome, or an undefined project. Require every visible route/function assertion and zero console/page error before a receipt can pass.
  - Build/install the exact base commit artifact in an isolated checkout, launch its legacy runtime, preserve a decoy on the old fixed port, then execute the new installer. Assert full-path/PID/create-time/hash ownership, V3 backup, SQLite checkpoint/integrity, successful transition, and data persistence. At every installer journal failpoint after legacy stop, old-tree move, new-tree move, manifest write, and shortcut replacement, assert the complete prior app/manifest/shortcuts are restored and the prior app is relaunched iff it was running; the decoy remains alive.
  - Monitor process creation for the whole run with a Windows Job Object plus process-start event subscription so short-lived descendants cannot evade the check; no external Python/Node/prerequisite/elevation child may appear. After every stop assert port/state/owned process clear, persistent lock file unheld, SQLite integrity/foreign keys clean, and interrupted job terminal state.
  - Add `-ClientSurface` mode for an agent-controlled Windows 10/11 x64 desktop session. It verifies OS build and a medium-integrity/non-elevated token, uses Explorer/ShellExecute to open the extracted CMD wrappers, drives the actual first-run/error `MessageBoxW` through Windows UI Automation, and writes a separate exact-commit `windows-client-surface-receipt.json`. When that desktop is unavailable, the CI technical receipt may pass but the Windows client-surface support claim remains explicitly unverified in release status; it does not silently inherit from Windows Server.
  - Emit `windows-artifact-receipt.json` bound to exact commit/folder/ZIP/extracted hashes and a redacted `windows-process-events.jsonl`; the task driver copies them to the scenario's exact `-EvidencePath` and adjacent `task-22-windows-process-events.jsonl`. Include three raw process-create-to-readiness observations for the staged folder and three for the extracted ZIP, with exactly-one-init fields; this is the required post-Lane-1 observation for Task 26, not a Lane-2 comparison baseline.
  - Extend `.github/workflows/desktop-artifacts.yml` `full` mode at this commit to execute the complete Windows script above on `windows-2022` x64 while retaining Task-21 basic macOS proof with no forward reference to Task 23. Task-21's push dispatcher downloads the exact Windows receipt/process/Playwright evidence by artifact ID/digest and rejects any mismatch or cleanup failure.

  Must NOT do: Do not launch source Python or inspect only script text, use real profile/PHI, kill the unrelated listener, skip install/upgrade/uninstall, or declare PASS while any owned process/file handle remains.

  Parallelization: Can parallel: NO | Wave 10 | Blocked by: [15, 17, 19, 21] | Blocks: [23, 24, 25, 26]

  References:
  - Current lifecycle smoke: `scripts/test-local-app-stack.ps1`, `scripts/test-windows-lifecycle.ps1`, `scripts/test-windows-stop.ps1`.
  - Current source-inspection tests: `backend/tests/test_v2_production_config.py:31-185` - replace as sole proof.
  - Artifact: Task 19 output/manifest.

  Acceptance criteria:
  - The staged-folder EXE and independently extracted ZIP EXE each complete every listed lifecycle/API/maintenance and pinned packaged-Chromium assertion under isolated paths with no developer/runtime prerequisites; raw ZIP/root/detached-manifest and declared hashes match.
  - Unrelated listener survives; active jobs drain/persist correctly; stop/restart leaves clean ownership and database integrity.
  - Receipt commit/artifact SHA/inventory match builder receipt and contains binary pass/fail fields for every scenario, not free-form PASS text.

  QA scenarios:
  ```text
  Scenario: Exact Windows ZIP installation completes end-user lifecycle
    Tool:     GitHub Actions CLI
    Steps:    After the Task-22 commit run `python scripts/ci/dispatch-desktop-workflow.py --workflow desktop-artifacts.yml --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode full --output-dir "$ATTEMPT_DIR/task-22-native" --receipt "$ATTEMPT_DIR/task-22-native-collection.json"`.
    Expected: Exit 0; the exact Windows x64 folder/ZIP complete every real lifecycle/Playwright assertion, final owned-process/port/state counts are zero, the macOS basic job remains forward-file independent, receipts bind the Task-22 source/workflow/artifacts, and nonce refs are deleted. Interactive Windows 10/11 `-ClientSurface` remains the separately named external RC gate.
    Evidence: $ATTEMPT_DIR/task-22-native-collection.json and $ATTEMPT_DIR/task-22-native/windows/{receipt.json,windows-artifact-receipt.json,windows-process-events.jsonl,playwright-report.json}

  Scenario: Unrelated port, tampered backup, failed upgrade, and fake PASS cannot produce receipt
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-desktop-workflow.py --workflow desktop-artifacts.yml --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode full --output-dir "$ATTEMPT_DIR/task-22-native-adversarial" --receipt "$ATTEMPT_DIR/task-22-native-adversarial-collection.json"`; the fixed Task-22 Windows job executes its unrelated-port/tamper/upgrade-failpoint/misleading-output cases against isolated artifact copies.
    Expected: App refuses/honors rollback as appropriate, decoy survives, current data hash is preserved, command exits according to assertions, and no success receipt is emitted for a failed subcase.
    Evidence: $ATTEMPT_DIR/task-22-native-adversarial-collection.json and $ATTEMPT_DIR/task-22-native-adversarial/windows/{receipt.json,windows-artifact-adversarial.json}
  ```

  Adversarial classes: `unrelated_port`, `pid_reuse`, `tamper_wrong_key`, `rollback_failure`, `misleading_success_output`.

  Cleanup: Authenticated stop first; revalidate/stop only test-owned processes, preserve decoy until assertion, then remove only isolated install/profile/Documents roots.

  Commit: YES | Message: `test(windows): execute packaged desktop lifecycle` | Files: [`scripts/test-windows-packaged-artifact.ps1`, `.github/workflows/desktop-artifacts.yml`]

- [ ] 23. Execute the exact ARM64 DMG artifact through its full lifecycle

  What to do:
  - Add `scripts/test-macos-packaged-artifact.sh`. It verifies DMG SHA, `hdiutil verify`, mounts read-only, scans mounted inventory, asserts every Mach-O arm64-only and plist metadata, launches the actual main app from DMG, then copies both apps to a synthetic Applications path containing spaces and repeats launch.
  - With isolated Application Support override and a unique injected Task-12 data-protection Keychain item, drive readiness/version, unauthenticated denial, first credential handoff sink, login/password change, synthetic upload/checklist/dashboard/rosters, restart persistence, second launch, other-data-root/different-port, unrelated listener, Utilities authenticated stop with active jobs, V3 backup/restore, diagnostics, `Install/Upgrade for Me` into isolated `~/Applications/IZ Clinical Notes Analyzer/`, two-app replacement rollback, deferred preserve-data uninstall, and complete uninstall/two-profile Keychain isolation.
  - Against both the read-only mounted main app and installed copy, enter `frontend/`, run `npm exec playwright install chromium`, verify the Task-21 revision/binary hash, and run `npm exec -- playwright test e2e/packaged-artifact-contract.spec.mjs --config playwright.desktop.config.mjs --reporter=json`; require every visible route/function assertion plus zero console/page errors.
  - Assert no writes to mounted DMG/app bundles; every permitted symlink remains contained/hashed; browser ordering; no external Python/Node; final port/state/process cleanup with persistent immutable lock unheld; SQLite integrity/foreign keys; unique Keychain test item deletion with unchanged search list; DMG unmount.
  - Emit `macos-artifact-receipt.json` bound to commit/DMG/bundle hashes and adjacent redacted `task-23-macos-process-events.jsonl`. Include three raw process-create-to-readiness observations for mounted and installed copies with exactly-one-init fields; Task 26 treats them as post-Lane-1 observations only. Headless CI proves technical behavior, not quarantine/Finder prompt usability or notarization.
  - Extend `.github/workflows/desktop-artifacts.yml` `full` mode at this commit to execute both Task-22 Windows and this complete macOS lifecycle at the same requested source SHA. Task-21's push dispatcher must validate/download the exact macOS receipt/process/Playwright evidence by run/job/artifact ID/API digest and clean every nonce ref.

  Must NOT do: Do not run source entrypoints, use Intel/Rosetta, mutate mounted apps, use a real user Keychain/profile, skip Utilities/maintenance, or equate headless `open` with external clean-Mac acceptance.

  Parallelization: Can parallel: NO | Wave 11 | Blocked by: [16, 18, 20, 21, 22] | Blocks: [24, 25, 26]

  References:
  - Build contract: Task 20.
  - Lifecycle/tools: `scripts/test-macos-lifecycle.sh`, `scripts/test-macos-maintenance.sh`.
  - Apple verification: `https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution` (verification separation).

  Acceptance criteria:
  - Exact DMG/main/Utilities bundles pass real native lifecycle, packaged-Chromium, no-admin two-app installation, and maintenance operations on the macOS 15 ARM64 engineering runner; artifact/resource tree hashes remain unchanged. The receipt records deployment target 14.0 but does not claim execution on macOS 14 hardware.
  - Receipt fields distinguish `technical_unsigned_or_adhoc_pass=true` from `developer_id_notarized=false` and `clean_mac_quarantine_tested=false` unless external receipts are actually provided.
  - Decoy listener/other root survives; runtime and Keychain/profile cleanup are complete.

  QA scenarios:
  ```text
  Scenario: Exact ARM64 DMG completes mounted and installed lifecycle
    Tool:     GitHub Actions CLI
    Steps:    After the Task-23 commit run `python scripts/ci/dispatch-desktop-workflow.py --workflow desktop-artifacts.yml --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode full --output-dir "$ATTEMPT_DIR/task-23-native" --receipt "$ATTEMPT_DIR/task-23-native-collection.json"`.
    Expected: Exit 0; exact `macos-15` arm64 mounted/installed apps and same-SHA Windows artifacts complete all assertions, Mac receipt says technical pass only and deployment target 14.0, final ownership counts are zero, DMG is unmounted, and nonce refs are deleted.
    Evidence: $ATTEMPT_DIR/task-23-native-collection.json and $ATTEMPT_DIR/task-23-native/macos/{receipt.json,macos-artifact-receipt.json,macos-process-events.jsonl,playwright-report.json}

  Scenario: Wrong architecture, bundle write, unrelated listener, Keychain denial, and fake PASS fail safely
    Tool:     GitHub Actions CLI
    Steps:    Run `python scripts/ci/dispatch-desktop-workflow.py --workflow desktop-artifacts.yml --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode full --output-dir "$ATTEMPT_DIR/task-23-native-adversarial" --receipt "$ATTEMPT_DIR/task-23-native-adversarial-collection.json"`; the fixed Mac job executes wrong-architecture/bundle-write/decoy/Keychain-denial/misleading-output cases against isolated mutated copies.
    Expected: Each canary is caught, valid artifact hash is unchanged, decoy survives, current profile hash survives denied restore, and no technical success receipt is emitted for a failed run.
    Evidence: $ATTEMPT_DIR/task-23-native-adversarial-collection.json and $ATTEMPT_DIR/task-23-native-adversarial/macos/{receipt.json,macos-artifact-adversarial.json}
  ```

  Adversarial classes: `wrong_architecture`, `bundle_write`, `unrelated_port`, `tamper_wrong_key`, `misleading_success_output`.

  Cleanup: Utilities stop, revalidate test PIDs, delete/verify only the unique injected Keychain item while asserting the search list unchanged, unmount the script-created volume, and remove only isolated Applications/profile roots.

  Commit: YES | Message: `test(macos): execute ARM64 DMG lifecycle` | Files: [`scripts/test-macos-packaged-artifact.sh`, `.github/workflows/desktop-artifacts.yml`]

- [ ] 24. Add fail-closed native release signing and notarization plumbing

  What to do:
  - Add `.github/workflows/release-desktop.yml`, protected/manual or release-tag only. Its explicit `macos-15` ARM64 job downloads already-scanned same-commit engineering/ad-hoc bundle inputs, verifies hashes/attestations, creates an ephemeral Keychain, imports the Developer ID Application certificate, removes only prior ad-hoc signatures, and signs deterministically inner-to-outer: every Mach-O/dylib/framework/helper/extension with timestamp + `--options runtime` + Task20's exact empty entitlements, verifies each designated requirement/team ID, then signs/verifies Utilities and main `.app` without `--deep` signing. Zip/submit each app separately to `xcrun notarytool`; require `Accepted`, staple/validate each `.app`, and only then build the exact four-root DMG from those stapled app bytes. Sign/submit the DMG separately, require `Accepted`, staple/validate, remount/scan, and rerun Task23's complete lifecycle against the final signed hash. Strict `codesign`, `stapler`, and `spctl` receipts bind final bytes.
  - Require protected Apple inputs `APPLE_DEVELOPER_ID_P12`, `APPLE_DEVELOPER_ID_P12_PASSWORD`, `APPLE_TEAM_ID`, and either notary key ID/issuer/private key or an approved Keychain profile. Require protected Windows inputs `WINDOWS_CODESIGN_PFX`, `WINDOWS_CODESIGN_PFX_PASSWORD`, and allowlisted HTTPS `WINDOWS_TIMESTAMP_URL` (or one explicitly configured equivalent hardware/provider identity with the same receipt fields). Missing/empty/mismatched inputs fail `release_signing_credentials_unavailable` before changing/publishing artifacts.
  - Add `scripts/sign-notarize-macos.sh` with `--verify-input`, `--adhoc-test`, and protected real modes. It enumerates exact nested code, rejects unexpected entitlements/identities/unsigned nodes, and records app-pre/app-signed/app-stapled/DMG-signed/DMG-stapled/final-lifecycle hashes. PR CI exercises nested ad-hoc signing and the missing-secret path; only the protected job may set `developer_id_notarized=true` after separate app accept/staple, DMG accept/staple, mounted assessment, and final-hash Task-23 lifecycle.
  - Add `scripts/sign-windows-release.ps1` with exact parameter sets `-VerifyInput`, `-TestCertificate`, and protected `-Release`, plus a protected Windows x64 job. Release requires an approved Authenticode certificate/private-key provider and timestamp URL, verifies Task19 ZIP/folder attestations, signs the EXE and each signable PowerShell helper before rebuilding/re-scanning manifest/ZIP, runs `Get-AuthenticodeSignature`/`signtool verify /pa /all`, and reruns Task22 on final signed hashes. `-TestCertificate` creates/deletes only a current-user ephemeral synthetic certificate and can prove plumbing but can never set release flags. Missing release credentials yields `release_signing_credentials_unavailable` and publishes nothing. SmartScreen reputation/clean Windows10/11 remain external.
  - Extend `.github/workflows/desktop-artifacts.yml` `full` mode with unprivileged engineering-only signing jobs at the exact Task-24 target: macOS nested ad-hoc verification plus missing-Apple-secret failure, and Windows current-user ephemeral-test-certificate verification plus missing-Windows-secret failure. Task-21's source-first/trigger-last dispatcher is the only Task-24 QA entrypoint; receipts bind source/workflow/run/job/artifact hashes, prove both missing-secret invocations emitted no release artifact, and can never set real signing/notary flags. The separate `release-desktop.yml` remains protected/manual or release-tag-only for authorized RC work.
  - Publish signed artifacts under a distinct name/hash; never overwrite unsigned inputs or expose secrets/notary fields. Workflow `always()` restores the original Keychain search list, locks/deletes the ephemeral Keychain, removes certificate/private-key/notary temp files, then runs a verification step proving the Keychain/file paths and secret canaries are absent; cleanup failure makes the release job fail.

  Must NOT do: Do not store credentials in repo/artifacts/logs, run protected signing on PRs, treat ad-hoc signing as Developer ID, skip nested code, claim notarization without Apple Accepted + staple + assessment, publish these unchanged-version engineering candidates as a public release, or block automatable Lane1 when credentials are absent.

  Parallelization: Can parallel: NO | Wave 12 | Blocked by: [19, 20, 21, 22, 23] | Blocks: [25, 26]

  References:
  - Apple notarization: `https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution`.
  - Hardened runtime/signing: `https://developer.apple.com/documentation/security/hardened_runtime`.
  - Artifact inputs: Tasks 19/20/23 receipts.

  Acceptance criteria:
  - Ad-hoc nested signing/verification passes on the unsigned dev artifact; missing protected inputs produce the exact blocked code and no release artifact.
  - Offline receipt/parser tests prove that only Accepted notarization plus exact empty entitlements, strict inner/outer signatures/team IDs, stapled DMG validation, mounted Gatekeeper assessments, matching commit/input hashes, and verified ephemeral-Keychain cleanup can set `developer_id_notarized=true`; missing or contradictory fields publish nothing.
  - Windows offline/parser tests require valid final-file Authenticode signatures/timestamps plus Task-22 rerun hashes before `windows_authenticode_signed=true`; missing credentials, invalid chain/timestamp, post-sign byte changes, or absent SmartScreen evidence cannot produce a release-ready receipt.
  - Logs/artifacts contain no certificate password/private key/notary credential marker.

  External release handoff (not an implementation acceptance criterion): when authorized credentials exist, an agent dispatches the protected workflow for the latest exact fully scanned Task26/Task36 commit artifacts and reruns the Task22/23 lifecycle contracts on the final signed hashes; stale task-local pre-doc/pre-barrier bytes cannot be an RC. Record Apple Developer-ID/notary and Windows Authenticode under external gates. Until then use the exact independent statuses `RELEASE BLOCKED: Apple Developer ID/notary credentials unavailable`, `RELEASE BLOCKED: Windows Authenticode credentials unavailable`, and, when no eligible interactive client exists, `RELEASE BLOCKED: Windows 10/11 standard-user client-surface acceptance unavailable`.

  QA scenarios:
  ```text
  Scenario: Engineering signing plumbing verifies both native artifacts and fails closed without secrets
    Tool:     GitHub Actions CLI
    Steps:    After the Task-24 commit run `python scripts/ci/dispatch-desktop-workflow.py --workflow desktop-artifacts.yml --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode full --output-dir "$ATTEMPT_DIR/task-24-native" --receipt "$ATTEMPT_DIR/task-24-native-collection.json"`.
    Expected: Exit 0; macOS ad-hoc and Windows ephemeral-test signatures verify but set no release flags, both protected invocations without credentials return `release_signing_credentials_unavailable`, no release artifact is emitted, receipts bind exact source/workflow/jobs/artifacts, and nonce refs are deleted.
    Evidence: $ATTEMPT_DIR/task-24-native-collection.json and $ATTEMPT_DIR/task-24-native/{windows,macos}/{receipt.json,signing-engineering.json}

  Scenario: Misleading notary receipt and missing credentials fail offline
    Tool:     pytest
    Steps:    Run `PYTHONPATH=backend python -m pytest backend/tests/test_macos_release_signing.py backend/tests/test_windows_release_signing.py -q --junitxml="$ATTEMPT_DIR/task-24-signing-adversarial.xml"` with fixtures for missing credentials, forged Accepted/staple/timestamp/chain/SmartScreen fields, mismatched hashes, and secret-marker logs.
    Expected: Every forged or incomplete receipt is rejected, missing credentials map to the stable blocked code, and no release artifact or release-ready flag is produced.
    Evidence: $ATTEMPT_DIR/task-24-signing-adversarial.xml
  ```

  Adversarial classes: `missing_release_secret`, `misleading_success_output`, `privacy_canary`, `stale_state`.

  Cleanup: In workflow `always()` steps delete/verify the macOS ephemeral Keychain/certificate/private-key files and the exact Windows current-user test certificate/private-key provider entry; retain only redacted signing/notarization metadata and immutable artifact hashes.

  Commit: YES | Message: `ci(release): gate native signing and notarization` | Files: [`.github/workflows/release-desktop.yml`, `.github/workflows/desktop-artifacts.yml`, `scripts/sign-notarize-macos.sh`, `scripts/sign-windows-release.ps1`, `backend/tests/test_macos_release_signing.py`, `backend/tests/test_windows_release_signing.py`]

- [ ] 25. Document cross-platform operation, support, testing, and release-state truthfully

  What to do:
  - Update `docs/architecture.md` with the portable core versus desktop controller/platform adapters, bootstrap import order, resource/data roots, instance/control/shutdown protocol, backup formats/scope, native packaging, and two-lane barrier.
  - Update `docs/windows-installer-build-and-install.md`, `docs/runbook.md`, `docs/Windows-User-Guide-Version-1.md`, and `docs/Windows-Deployment-and-Test-Guide-Version-1.md` for shared launch/stop/preflight/V3 backup behavior while preserving the current release-folder/ZIP and normal-user model.
  - Add `docs/macos-apple-silicon-install-and-test.md` for macOS 14+ ARM64 DMG install, Finder double-click of Utilities `Install/Upgrade for Me` into `~/Applications/IZ Clinical Notes Analyzer/`, first credential dialog/change, launch/Utilities stop, data location, profile-scoped Keychain backup/restore, diagnostics, two-app update/uninstall, external Gatekeeper/Keychain expectations, and exact commands for CI, rented/borrowed Mac, or beta tester verification using synthetic data.
  - Update Task 6's packaged Mac Read Me to a short Finder-oriented subset and add `docs/cross-platform-desktop-validation.md` mapping every automatable receipt and separate RC gate. Update `docs/open-blockers.md`, `docs/release-notes.md`, and `docs/CODEX_COMPLETION_LOG.md` without resolving LOC/live-Alleva/security-incident/signing/clean-Mac blockers falsely.
  - Extend `scripts/validate_docs_commands.py` and add `.github/workflows/docs-validation.yml` with `on.push.branches: ['codex-ci/**']` and the Task-21 canonical request/ref validation. After committing this task, use Task 21's push-trigger dispatcher to run Windows/macOS doc commands at that exact SHA, upload receipts with event/trigger/target/workflow/run/attempt/job/artifact IDs/digests, download them, and aggregate only after recomputing exact doc hashes/platform exits. No local command may pretend it can read a receipt that exists only on another runner.
  - Do not bump `VERSION`, `VERSION.json`, or `frontend/package.json` merely for this refactor. If a later separately authorized release bump occurs, update all version surfaces together and rerun receipts.

  Must NOT do: Do not put credentials/PHI/local paths in docs/screenshots, claim signed/notarized/clean-Mac status without receipts, change business blockers, or document unsupported Intel/App Store/cross-OS restore.

  Parallelization: Can parallel: NO | Wave 13 | Blocked by: [1, 15, 16, 17, 18, 19, 20, 22, 23, 24] | Blocks: [26]

  References:
  - Current docs: `docs/architecture.md`, `docs/windows-installer-build-and-install.md`, `docs/runbook.md`, `docs/open-blockers.md`.
  - First sign-in policy: `docs/admin-access-reset.md:9-76`.
  - Version contract: repository `AGENTS.md` Commit and validation expectations.
  - Mac external testing options: GitHub-hosted runners and AWS EC2 Mac official documentation linked in the validation guide.

  Acceptance criteria:
  - Documentation names exact supported targets/artifacts/data paths/user operations and distinguishes automatable unsigned technical pass from external signed/quarantined release readiness.
  - Link/file/command validator confirms every referenced repo path and CLI switch exists; a synthetic docs secret/PHI scanner finds zero forbidden values.
  - Current version files remain unchanged and all existing LOC/live-Alleva/security blockers remain present.
  - `$ATTEMPT_DIR/task-25-docs-receipt.json` validates against Task-21's versioned collection schema plus Task-25's docs fields, binds one committed SHA plus both native workflow run/job/artifact identities/digests and every exact doc hash, and contains binary command/blocker/privacy results rather than free-form PASS text.

  QA scenarios:
  ```text
  Scenario: Operator follows every documented command against synthetic artifacts
    Tool:     bash and PowerShell
    Steps:    After the Task-25 commit run `python scripts/ci/dispatch-desktop-workflow.py --workflow docs-validation.yml --commit "$(git rev-parse HEAD)" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --mode docs --output-dir "$ATTEMPT_DIR/task-25-docs-native" --receipt "$ATTEMPT_DIR/task-25-docs-collection.json"`; then run `python scripts/validate_docs_commands.py --aggregate-dir "$ATTEMPT_DIR/task-25-docs-native" --collection-receipt "$ATTEMPT_DIR/task-25-docs-collection.json" --commit "$(git rev-parse HEAD)" --receipt "$ATTEMPT_DIR/task-25-docs-receipt.json"`.
    Expected: Every path/switch/command resolves and its dry-run or synthetic execution exits as documented; no unsupported prerequisite appears.
    Evidence: $ATTEMPT_DIR/task-25-docs-receipt-windows.json, $ATTEMPT_DIR/task-25-docs-receipt-macos.json, and $ATTEMPT_DIR/task-25-docs-receipt.json

  Scenario: Docs cannot hide blocked gates or leak private markers
    Tool:     bash
    Steps:    Run `python -m pytest backend/tests/test_validate_docs_commands.py -q --junitxml="$ATTEMPT_DIR/task-25-docs-adversarial.xml"` with its secret/PHI, missing-LOC/live-Alleva/Developer-ID/clean-Mac blocker, nonexistent switch, and misleading-PASS fixtures using the current task's locked Python 3.12 environment.
    Expected: Marker fixture is rejected/redacted, required blockers are found semantically, and no status is inferred from a plain word PASS.
    Evidence: $ATTEMPT_DIR/task-25-docs-adversarial.xml
  ```

  Adversarial classes: `privacy_canary`, `misleading_success_output`, `stale_state`, `semantic_drift`.

  Cleanup: Documentation tests use temp fixture copies and remove only them; do not modify actual version/blocker state during QA.

  Commit: YES | Message: `docs(desktop): document Windows and Apple Silicon operation` | Files: [`docs/architecture.md`, `docs/windows-installer-build-and-install.md`, `docs/runbook.md`, `docs/Windows-User-Guide-Version-1.md`, `docs/Windows-Deployment-and-Test-Guide-Version-1.md`, `packaging/macos/IZ Clinical Notes Analyzer - Read Me.txt`, `docs/macos-apple-silicon-install-and-test.md`, `docs/cross-platform-desktop-validation.md`, `docs/open-blockers.md`, `docs/release-notes.md`, `docs/CODEX_COMPLETION_LOG.md`, `.github/workflows/docs-validation.yml`, `scripts/validate_docs_commands.py`, `backend/tests/test_validate_docs_commands.py`]

- [ ] 26. Enforce the non-bypassable Lane 1 portability barrier

  What to do:
  - Treat Task 1's externally anchored `config/verification/approved-cross-platform-plan.md`, frozen `scripts/verification/render_plan_contract.py`, and committed `config/verification/cross-platform-plan-contract.json`, `config/verification/lane1-task-graph.json`, and `config/performance/lane2-scope.json` as immutable inputs. Fetch the approved plan and renderer at the Task-1 SHA through the GitHub Contents API, verify their Git blob/content hashes plus `APPROVED_PLAN_SHA256` against protected execution state, rerender into a private temp directory, and require byte identity with the Task-1 Git policy blobs. Task 26 must not rewrite, regenerate in place, normalize, or broaden any byte. Tasks32/34/35 have `NOT_MATERIAL|REJECTED|ACCEPTED`; always-measured Task33 has only `REJECTED|ACCEPTED`, and any Task33 `NOT_MATERIAL` or no-collection decision is fatal. Reject submodules, undeclared links/files/directory entries, case/NFC aliases, unexpected modes/types/renames, and any Task2-36 edit to the approved-plan/renderer/policy blobs.
  - Add `scripts/verify-lane1-barrier.py`, `scripts/ci/collect-lane1-barrier.py`, `scripts/ci/download-desktop-receipts.py`, `scripts/verification/verify_instrumentation_only.py`, and `backend/tests/test_lane1_barrier.py`. The barrier verifier has `get-field`, `verify-receipt`, `start-task`, and `finish-task` subcommands; `get-field` reads only a named non-secret scalar from an already schema-validated local receipt and never authorizes work. It validates the externally anchored plan/rerender, certificate-bound direct attestation, and both independently supplied Task-26 source/trigger anchors before trusting any subject field; recomputes base-to-Task26 Task1-26 commit/delta/mode/directory-entry chain; and for Lane 2 requires a clean direct descendant whose commits form the exact pre-anchored outcome-specific chain. `start-task N` writes exclusive `$ATTEMPT_DIR/task-N/barrier-start.json`; `finish-task N` requires the exact subject/delta/evidence and writes `barrier-post.json`. A missing predecessor post receipt, extra commit, path/type/mode/rename/directory mismatch, mutable approved plan/renderer/verifier/policy, invalid Task33 outcome, or dirty tree is fatal.
  - Freeze one narrowly machine-verifiable Task-27 instrumentation exception in `lane2-scope.json`: new `backend/app/desktop/timing.py` plus edits to `backend/app/desktop/controller.py`, `backend/app/application.py`, and `backend/app/v2/db.py` may only add the exact `mark_benchmark_stage` import and expression calls with the predeclared literal stage names at predeclared existing call boundaries. `verify_instrumentation_only.py` strips only those import/call AST nodes and requires the remaining normalized Python AST to equal the Task-26 blob exactly; it also rejects changed arguments/control flow/assignments/exception handling and any normal-run output. The exact Task-27 frontend mark paths remain separately enumerated in its pre-anchored scope. No other lifecycle/security/auth/rules/comparator/policy file appears in a later row.
  - `collect-lane1-barrier.py` accepts exactly `--commit`, `--approved-plan-sha256`, `--repository`, `--repository-id`, `--remote`, `--workflow`, `--attempt-dir`, and `--receipt`. It is the single executable orchestration path: validate fixed typed GitHub identity; require clean exact commit/tree; create without force the previously absent durable tag `refs/tags/codex-barrier/task26-<40-lowercase-hex-commit>` pointing directly to the Task-26 commit, verify through both `git ls-remote` and the GitHub ref/commit APIs that it resolves to that commit, and exclusively record its full ref/SHA/API object IDs in the source anchor and protected parent state; call the Task21 dispatcher with explicit repository ID/remote; independently query the API for exact request/trigger/temporary-source/workflow/run/job/artifact identities and exclusively write the trigger anchor; download the exact barrier subject by artifact ID/API digest; download exactly one offline attestation bundle; invoke `download-desktop-receipts.py`; fetch/hash/run the frozen verifier and Task-1 renderer through that durable tag; retain the API-fetched verifier at a random current-user-private path whose path/hash are recorded in protected parent state and `task-26-collection.json`; atomically publish the verified root barrier; and verify cleanup of only temporary request/source/trigger refs in `finally`. It emits a non-PASS receipt on any failed stage, never asks the caller to supply `RUN_ID`, `TRIGGER_SHA`, or values derived from the subject, never force-updates/reuses an existing tag, and does not delete the durable tag before final-wave approval.
  - Commit Task-26 code before the gate. The collector captures Task26 commit/tree, numeric repository `id=1172715348`, repository `node_id=R_kgDOReY3VA`, durable tag ref/object/commit, external plan hash, Task-1 approved-plan/renderer/contract/graph/scope Git blob+content hashes, Task-26 barrier/instrumentation/collector verifier blob+content hashes, workflow blob hash, and clean status directly into exclusive/private `$ATTEMPT_DIR/task-26-source-anchor.json` and the protected parent ledger; none is read from `lane1-barrier.json`. It publishes/verifies the exact temporary Task26 source ref and durable Task26 tag before dispatch. Task21's dispatcher creates the canonical request trigger commit/ref last; the collector independently resolves its remote trigger SHA/ref, request bytes/hash, correlation ID, temporary source SHA/ref, durable tag, signer workflow path/blob SHA, and selected push run ID and exclusively writes `$ATTEMPT_DIR/task-26-trigger-anchor.json`. `.github/workflows/desktop-artifacts.yml` runs only from `on.push.branches: ['codex-ci/**']`, verifies event/trigger/source/workflow hashes, and executes `full` mode against the Task26 source SHA. No manual-only workflow event is used.
  - That authoritative push run reruns every shared/native Task21 check, Windows Task22 folder+ZIP lifecycle including exact-base running upgrade, macOS Task23 mounted/installed/no-admin suite lifecycle, Task24 ad-hoc/missing-secret engineering checks, and Task25 native docs commands at the Task26 target. Earlier task-local receipts cannot satisfy it. The barrier job consumes only same-run `needs` artifacts and recomputes every run/job/artifact/receipt digest, command exit, checkout target, action pin, and cleanup assertion.
  - Generate canonical UTF-8 `lane1-barrier.json` (sorted keys, compact separators, LF, no volatile path/secret) as its own immutable subject. It records schema, engineering pass, Task26 commit/tree, both typed repository IDs, durable Task26 tag ref/SHA, plan/verifier/task-graph/scope hashes, GitHub event/trigger/temporary-source/workflow/run/attempt/job/runner IDs, action pins, artifact IDs/digests/hashes, required check IDs, OS/arch/tool/lock/browser closures, completion time from the trusted run, startup observations, and separate external RC statuses. Use `actions/attest@59d89421af93a897026c735860bf21b6eb4f7b26` with `id-token: write`/`attestations: write` to attest that exact JSON file directly; separately upload the JSON and evidence ZIP with pinned `actions/upload-artifact@bbbca2ddaa5d8feaa63e36b76fdaad77386f024f`. Pin checkout/setup/download actions to the exact SHAs listed in the tracked contract. An attestation of only a ZIP does not authorize Lane 2.
  - `download-desktop-receipts.py` accepts exactly `--run-id`, `--commit`, `--repository`, `--source-anchor`, `--trigger-anchor`, `--signer-workflow`, `--subject`, `--attestation-bundle`, `--output-dir`, and `--receipt`. Before parsing `--subject`, it verifies the private anchors, loads `ATTESTATION_BUNDLE`, `TRIGGER_SHA`, `TRIGGER_REF`, and the durable Task26 tag only from collector-owned protected values, requires the explicit signer workflow to equal `martyw1/IZ_clinical-notes-analyzer/.github/workflows/desktop-artifacts.yml`, and runs trusted installed `gh attestation verify "$ATTEMPT_DIR/lane1-inputs/lane1-barrier.json" --bundle "$ATTESTATION_BUNDLE" --repo martyw1/IZ_clinical-notes-analyzer --signer-workflow martyw1/IZ_clinical-notes-analyzer/.github/workflows/desktop-artifacts.yml --signer-digest "$TRIGGER_SHA" --source-digest "$TRIGGER_SHA" --source-ref "$TRIGGER_REF" --format json`. It validates the certificate OIDC issuer, numeric repository ID plus node ID, workflow ref/path, signer/source digest/ref, push event, and transparency timestamp against that independent anchor; only then may it parse the predicate and require exact Task26 target/tree/verifier/contracts/run/attempt/job/artifact identities. It downloads remaining artifacts by exact run/artifact ID, verifies API digests before extraction, revalidates the durable tag by GitHub ref/commit API, fetches `scripts/verify-lane1-barrier.py` through the GitHub Contents API with that tag ref, requires the returned commit and blob/content hashes to equal the independent source anchor, and runs that frozen file online. Only after all checks pass does it atomically write/fsync a byte-identical copy to `$ATTEMPT_DIR/lane1-barrier.json` and fsync the parent. `lane1-inputs/lane1-barrier.json` is only the downloaded subject and never the Lane-2 path.
  - Preserve the three raw Task-22/23 process-to-readiness observations per artifact surface as `lane1_startup_observations` and assert exactly one app/init in each. They document post-refactor state only: the barrier makes no speed claim, and Tasks 27-31 must rebuild instrumented artifacts and recapture formal baselines without counting the Lane-1 one-app/one-init fix.
  - Missing Windows client-surface, publisher/SmartScreen, Apple credentials, macOS14-hardware, or clean-Mac evidence may be `blocked` without changing `engineering_pass`; absent Windows x64/macOS15-arm64 engineering evidence may not. Every Task27-36 literal first action receives `FROZEN_LANE1_VERIFIER`, both independent anchors, the external approved-plan hash, fixed typed repository identity, durable Task26 tag, and the offline attestation bundle from protected parent state. The API-fetched verifier first proves that tag still resolves to the anchored Task26 commit, validates its own bytes against the source anchor and GitHub Contents API online through that tag, rerenders the approved plan, repeats exact signer/digest/source/ref certificate verification before parsing the root receipt, and invokes `start-task N`; its last action after the task commit/evidence invokes `finish-task N`. Missing/moved tag is fatal. No task reads commit/trigger/signer/tag values from an unverified subject, no mutable descendant script can authorize work, and Task36 plus F1/F4 repeat approved-plan and certificate-bound verification through completed Task36 against a frozen final HEAD.

  Must NOT do: Do not accept transitive/partial/grep-only/local-only evidence, derive repository/run/trigger identity from the subject, select newest-by-branch, merge different commits, permit an un-attested or descendant-edited approved plan/renderer/verifier, authorize Task33 `NOT_MATERIAL`, call arbitrary descendants “performance-only,” include external Developer/notary/clean-Mac availability as engineering pass requirements, emit before cleanup, or start Lane 2 before online PASS.

  Parallelization: Can parallel: NO | Wave 14 barrier | Blocked by: [1, 21, 22, 23, 24, 25] | Blocks: [27, 28, 29, 30, 31, 32, 33, 34, 35, 36]

  References:
  - Receipts: Tasks 21-25 output contracts.
  - Scope: `External release-candidate gates` and strict two-lane requirements above.
  - CI: `.github/workflows/desktop-artifacts.yml` and `.github/workflows/release-desktop.yml`.
  - Artifact attestations: `https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations`.

  Acceptance criteria:
  - `python scripts/ci/collect-lane1-barrier.py --commit "$(git rev-parse HEAD^{commit})" --approved-plan-sha256 "$APPROVED_PLAN_SHA256" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --workflow desktop-artifacts.yml --attempt-dir "$ATTEMPT_DIR" --receipt "$ATTEMPT_DIR/task-26-collection.json"` exits 0 without any caller-supplied run/trigger value. For that independently anchored exact Task-26 SHA, authoritative same-run Windows staged-folder/ZIP and macOS mounted/installed receipts plus every shared/docs/signing-engineering check validate; directly attested canonical JSON has `engineering_pass=true`, correct repository/trigger/source/workflow/action-pin/provenance/arch/artifact hashes, complete observations, packaged Playwright, cleanup=true, and truthful external statuses.
  - Certificate-bound `gh attestation verify` passes with the exact offline bundle, signer workflow/digest, source digest/ref, both typed repository IDs, push event, and trusted timestamp before any subject field is parsed; the durable tag exists at the exact Task26 commit; the verifier fetched from the GitHub Contents API through that tag matches the independent source anchor and passes online. The published `$ATTEMPT_DIR/lane1-barrier.json` is byte-identical to the attested subject. Removing/editing a receipt, flipping a result, changing bytes, swapping repository `id`/`node_id`, moving/deleting the durable tag early, supplying another source/trigger anchor, signer/workflow/ref/SHA/arch/run/job/artifact, dirtying the tree, changing Task-1 policy/verifier, editing an earlier comparator, adding an out-of-scope path/type/mode/directory/commit, violating the instrumentation-only AST rule, or leaving process/volume/Keychain/temp state makes verification nonzero and cannot write replacement PASS.
  - `rg -n "Blocked by:.*26" config/verification/approved-cross-platform-plan.md` finds every Task 27-36 entry, but this structural check supplements rather than replaces executing the verifier.

  QA scenarios:
  ```text
  Scenario: Same-commit native evidence produces the Lane 1 barrier receipt
    Tool:     bash
    Steps:    After the Task-26 commit run `set -euo pipefail; TASK26_COMMIT=$(git rev-parse HEAD^{commit}); test -n "$APPROVED_PLAN_SHA256"; test "$REPOSITORY" = "martyw1/IZ_clinical-notes-analyzer"; test "$REPOSITORY_ID" = "1172715348"; test "$REPOSITORY_NODE_ID" = "R_kgDOReY3VA"; test "$GITHUB_REMOTE" = "origin"; python scripts/ci/collect-lane1-barrier.py --commit "$TASK26_COMMIT" --approved-plan-sha256 "$APPROVED_PLAN_SHA256" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --workflow desktop-artifacts.yml --attempt-dir "$ATTEMPT_DIR" --receipt "$ATTEMPT_DIR/task-26-collection.json"; python scripts/verify-lane1-barrier.py verify-receipt --receipt "$ATTEMPT_DIR/lane1-barrier.json" --source-anchor "$ATTEMPT_DIR/task-26-source-anchor.json" --trigger-anchor "$ATTEMPT_DIR/task-26-trigger-anchor.json" --attestation-bundle "$(python scripts/verify-lane1-barrier.py get-field --receipt "$ATTEMPT_DIR/task-26-collection.json" --field attestation_bundle_path)" --signer-workflow "$REPOSITORY/.github/workflows/desktop-artifacts.yml" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --approved-plan-sha256 "$APPROVED_PLAN_SHA256" --current-head "$TASK26_COMMIT" --online`.
    Expected: Both commands exit 0; the collector—not shell prose—creates and binds source/trigger anchors, both typed repository IDs, durable Task26 tag, exact run/artifact IDs, direct JSON attestation, frozen approved-plan rerender/verifier, task chain, and cleanup; `$ATTEMPT_DIR/lane1-barrier.json` equals the attested downloaded bytes; Windows x64/macOS arm64 engineering evidence is same-commit; external gates are separate; every temporary ref is deleted while the one exact durable tag remains and resolves to Task26.
    Evidence: $ATTEMPT_DIR/task-26-source-anchor.json, $ATTEMPT_DIR/task-26-trigger-anchor.json, $ATTEMPT_DIR/task-26-collection.json, $ATTEMPT_DIR/task-26-dispatch.json, $ATTEMPT_DIR/task-26-download-receipt.json, $ATTEMPT_DIR/lane1-inputs/lane1-barrier.json, $ATTEMPT_DIR/lane1-barrier.json, and the exact bundle path recorded in task-26-collection.json

  Scenario: Mixed SHA, edited receipt, wrong arch, stale artifact, and cleanup failure cannot cross the barrier
    Tool:     bash
    Steps:    Run `python -m pytest backend/tests/test_lane1_barrier.py -q -k "repository_identity or repository_id_type or approved_plan or renderer or anchor_tag or moved_anchor_tag or early_anchor_delete or signer or source_ref or source_digest or bundle or retrospective_graph or outcome_subject or task33_not_material or missing_task33_collection or directory_entry or instrumentation or mixed_sha or edited_receipt or wrong_arch or stale_artifact or cleanup" --junitxml="$ATTEMPT_DIR/task-26-barrier-adversarial.xml"` against isolated mutated receipts plus a temp git repository containing in-scope/out-of-scope descendant commits.
    Expected: Every mutation exits/rejects with its exact safe reason and cannot create engineering_pass=true.
    Evidence: $ATTEMPT_DIR/task-26-barrier-adversarial.xml
  ```

  Adversarial classes: `stale_state`, `wrong_architecture`, `misleading_success_output`, `cleanup_escape`, `dirty_worktree`.

  Cleanup: Barrier never deletes evidence inputs; native jobs own target cleanup. The collector deletes only its exact nonce/temporary-source/trigger refs and isolated worktree in `finally`, confirms their absence, and retains the exact durable Task26 tag plus private frozen verifier/anchors/bundle needed by Lane 2 and final review. It records the tag as intentionally retained, not leaked. Tests mutate only temp copies and remove those copies after assertions; Task36/final reviewers may not delete the tag before all four approve.

  Commit: YES | Message: `ci(desktop): enforce lane one portability barrier` | Files: [`scripts/ci/collect-lane1-barrier.py`, `scripts/ci/download-desktop-receipts.py`, `scripts/verify-lane1-barrier.py`, `scripts/verification/verify_instrumentation_only.py`, `backend/tests/test_lane1_barrier.py`, `.github/workflows/desktop-artifacts.yml`]

- [ ] 27. Commit the shared measurement foundation and validate native harness contracts

  What to do:
  - Literal first action: obtain `FROZEN_LANE1_VERIFIER`, both Task26 anchors, `ATTESTATION_BUNDLE`, `APPROVED_PLAN_SHA256`, and the fixed repository identity from protected parent state, never from the barrier subject. Before any import/edit/dispatch run `python "$FROZEN_LANE1_VERIFIER" start-task 27 --completed-through 26 --receipt "$ATTEMPT_DIR/lane1-barrier.json" --source-anchor "$ATTEMPT_DIR/task-26-source-anchor.json" --trigger-anchor "$ATTEMPT_DIR/task-26-trigger-anchor.json" --attestation-bundle "$ATTESTATION_BUNDLE" --signer-workflow "$REPOSITORY/.github/workflows/desktop-artifacts.yml" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --approved-plan-sha256 "$APPROVED_PLAN_SHA256" --current-head "$(git rev-parse HEAD)" --output "$ATTEMPT_DIR/task-27/barrier-start.json" --online`; it self-hashes against the source anchor/API, rerenders the approved plan, and verifies the certificate before parsing the subject. After the exact Task-27 commit and evidence, literal last action runs `python "$FROZEN_LANE1_VERIFIER" finish-task 27 --completed-through 27 --receipt "$ATTEMPT_DIR/lane1-barrier.json" --source-anchor "$ATTEMPT_DIR/task-26-source-anchor.json" --trigger-anchor "$ATTEMPT_DIR/task-26-trigger-anchor.json" --attestation-bundle "$ATTESTATION_BUNDLE" --signer-workflow "$REPOSITORY/.github/workflows/desktop-artifacts.yml" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --approved-plan-sha256 "$APPROVED_PLAN_SHA256" --current-head "$(git rev-parse HEAD)" --evidence-dir "$ATTEMPT_DIR/task-27" --output "$ATTEMPT_DIR/task-27/barrier-post.json" --online`.
  - Add `scripts/performance/benchmark_source_startup.py` and `backend/tests/performance/synthetic_startup_profiles.py`. Generate deterministic encrypted synthetic fixtures with fixed seed and no person-like data: `empty` (0 patients/versions), `small` (100 patients/300 plan versions), and `scale` (2,000 patients/6,000 plan versions), each with the same rules/checklist/settings shape and recorded fixture SHA.
  - Add `config/performance/cross-platform-v1.json` before any candidate runs. It fixes candidate primary/protected cells and exact activation: startup selects every source/package `small|scale` cell whose reevaluation stage is at least 250 ms or 10% of process-to-readiness on either OS; packaging primary is always Windows `cold-install` `small|scale`; endpoint query selects an endpoint/role only when its `scale` median is at least 250 ms or at least 10% of the same OS/role/`scale` mapped navigation-to-content-ready median and it also executes more than 50 SQL statements or grows by more than 10 statements from the same endpoint/role's `small` cell; frontend may select only `settings-ready|logs-ready` administrator cells whose frontend work is at least 25% of process-to-interactive and whose view median exceeds 250 ms. The immutable endpoint mapping is `/api/v2/dashboard -> dashboard-ready`; `/api/v2/patient-roster -> patient-roster-ready`; `/api/v2/treatment-plan-roster` and `/api/v2/treatment-plans -> treatment-plans-ready`; and `/api/v2/treatment-plans/{patient_id}`, `/api/v2/treatment-plans/{patient_id}/{treatment_plan_id}`, and `/api/v2/patients/{patient_id} -> checklist-detail-ready`. No aggregation/substitution is allowed: each endpoint's administrator or office-manager cell uses the matching browser role, fixture, OS, view, and arithmetic median. Task 31 must therefore measure both roles for the four mapped clinical views; unauthorized/missing mapped cells are `ERROR`, not silently dropped. Every selected cell is mirrored onto both OSes except Windows-only packaging. For every selected cell, median is primary but that same cell's nearest-rank p95 is independently protected at the 5% ceiling. Empty fixtures, unselected cells, all other roles/views/modes, warm packaging, artifact size/memory, and exact-zero safety/semantic fields are also protected. Selection is computed once from Task-31 control data and cannot be edited per result.
  - Add `scripts/performance/evaluate_activation.py` with exactly `--candidate-type {startup-reevaluation,endpoint-query,frontend-splitting}`, `--control-receipt`, `--policy`, and `--output`. It validates the Task-31 control/provenance, applies only the fixed matrix/materiality rule, and writes one machine-readable `ACTIVATED` or `NOT_MATERIAL` outcome plus selected cells; later tasks must branch on this receipt before creating a candidate worktree.
  - `benchmark_source_startup.py` accepts exactly `--lane1-receipt`, `--mode {baseline,candidate}`, `--candidate-id`, `--runs`, `--fixtures`, `--profile-modes {fresh,warm-profile}`, `--target-os {windows,macos}`, and `--output-dir`.
  - Add safe monotonic stage marks in `backend/app/desktop/timing.py` and only the Task-26 pre-anchored instrumentation calls in controller/application/db for process entry, lock acquired, bootstrap complete, preflight complete, app lifespan start, migrations complete, reevaluation complete, Uvicorn started, readiness 200, and browser dispatch. Before the Task-27 commit, run Task-26 `verify_instrumentation_only.py` against Task26..candidate; after stripping only the declared import/call nodes, the three normalized ASTs must match exactly. Emit durations/counts only to an explicit benchmark JSON sink; normal runs emit nothing new.
  - Add `scripts/performance/contracts.py`, `scripts/performance/compare_candidate.py`, and `scripts/verification/verify_scope_fidelity.py` as frozen Lane-2 contracts. `contracts.py get-field` validates before printing an allowlisted nonsensitive field. The comparator accepts exactly candidate type, control/candidate dirs, `--collection-receipt`, policy, and output. It validates workflow/run/attempt/job/runner IDs, control/candidate commit+tree SHAs, distinct artifact IDs/digests, raw-file hashes, lock closure, `dirty=false`, and pairing by runner allocation/target/fixture/mode/slot/role plus equal `artifact_surface` (`source`, `windows-folder`, `windows-zip`, `macos-mounted`, or `macos-installed`); it must not require unequal control/candidate artifact hashes to be equal. `verify_scope_fidelity.py` requires the tracked plan through `--plan config/verification/approved-cross-platform-plan.md` plus `--approved-plan-sha256`, rehashes it before parsing, and never reads ignored `.omo` content in a candidate/final worktree.
  - Freeze the complete formal cell inventory in `cross-platform-v1.json`; every row has the exact key tuple `(target_os, artifact_surface, fixture, profile_mode, package_mode, endpoint, view, role)` and uses JSON `null` for an inapplicable dimension. Source-startup rows are `windows|macos x source x empty|small|scale x fresh|warm-profile`. Packaged-startup rows are `windows x windows-folder|windows-zip x empty|small|scale x cold-install|warm-install` and `macos x macos-mounted|macos-installed x empty|small|scale x cold-copy|warm-copy`. Endpoint rows are `windows|macos x source x small|scale x every Task-30 endpoint x administrator|office-manager`. Browser rows are each target's two native artifact surfaces x `small|scale` x the four mapped clinical views for both roles, plus `login-ready|settings-ready|logs-ready` for administrator. There is no cross-surface aggregation, substitution, default, or omitted dimension; a missing or duplicate declared row is `ERROR`.
  - Encode decision math once: arithmetic median averages the middle two values for even `n`; p95 is nearest-rank sorted index `ceil(0.95*n)`; no input or result is rounded before the decision. Every precommitted primary cell must improve median by `(control-candidate)/control >= 0.10` OR `control-candidate >= 250 ms`; paired deltas also pass an exact one-sided binomial sign test at `p <= 0.05` with zero/tied deltas counted against the candidate (7/7, at least 9/10, at least 15/20). Independently, every primary cell's p95 and every other protected median/p95/scalar may regress at most 5%; zero stays zero; failures/privacy/process/lease/mount/Keychain/external-request/unauthorized-decrypt/semantic/audit/schema/hash/omission fields stay exactly zero. Never average cells or post-select affected cells.
  - Add `scripts/performance/run_paired_candidate.py`, `scripts/performance/dispatch_paired_candidate.py`, and `.github/workflows/desktop-performance-candidate.yml` with `on.push.branches: ['codex-ci/**']`. The dispatcher accepts exactly `--lane1-receipt`, `--candidate-type`, `--workflow-ref`, `--control-ref`, `--candidate-ref`, `--repository`, `--repository-id`, `--remote`, `--targets`, and `--output-dir`; refs are full SHAs and the Task-1 identity preflight is mandatory. `candidate-type` is the closed enum `foundation-smoke|windows-package-smoke|macos-package-smoke|endpoint-smoke|startup-reevaluation|packaging-mode|endpoint-query|frontend-splitting`. Smoke types require `workflow_ref=control_ref=candidate_ref`, run one non-comparative exact-target checkout, and may select only their fixed target OS/command/artifact schema; each fixed smoke command executes the task's happy and adversarial harness checks and emits both exact inventories, independent of the caller's output-directory name. At Task 27 only `foundation-smoke` exists and every future smoke type fails on its absent file. Real candidate types require distinct control/candidate SHAs and run same-allocation sibling checkouts in exact ABBA order. The dispatcher publishes/verifies its task-local workflow/control/candidate refs through only the named remote first, then publishes the Task-21 canonical request trigger commit last; the push workflow verifies repository ID/request/event/trigger/workflow/target hashes. It selects the exact push run/correlation, downloads by artifact ID/digest, produces `collection-receipt.json`, and deletes every ref created by that invocation in `finally`; it must neither update nor delete the separately recorded Task26 durable tag. Infrastructure/auth/ref/run/cleanup failures are `ERROR`, never measured rejection.
  - Add benchmark-only content-ready marks in `frontend/src/v2/performanceMarks.ts` and the exact completion sites in `frontend/src/v2/AppV2.tsx`, `pages/DashboardPage.tsx`, `pages/TreatmentPlansRosterPage.tsx`, `pages/PatientRosterPage.tsx`, `pages/TreatmentPlanDetailPage.tsx`, `pages/SettingsPage.tsx`, and `pages/ForensicLogsPage.tsx`. Canonical marks are `login-ready`, `dashboard-ready`, `treatment-plans-ready`, `patient-roster-ready`, `checklist-detail-ready`, `settings-ready`, and `logs-ready`; each fires only after that view's required data/render state. A root-render mark is informational and never satisfies content readiness.
  - At this task commit, run two-sample native smoke matrices per fixture/profile mode only to prove the harness, marks, receipt/provenance, cleanup, and deterministic summarizer work. Task 31 reruns the required formal 7 source samples at one immutable control SHA after every baseline harness has committed. These Task-27 smoke timings are not activation/control evidence.
  - Emit raw JSON plus median and nearest-rank p95 with every sample retained. Record commit, barrier SHA, fixture/artifact/dependency hashes, OS/arch, Python version, stage durations, init/reevaluation counts, exit/cleanup, and exactly one app init.

  Must NOT do: Do not optimize code, reuse pre-Lane-2 timings, omit failed/outlier runs, use a real profile, write PHI/credentials/path values, enable timing outside an explicit benchmark sink, treat root render as content-ready, infer comparator policy in later tasks, or count the Lane 1 duplicate-init fix as a performance gain.

  Parallelization: Can parallel: NO | Wave 15 | Blocked by: [26] | Blocks: [28, 31, 32]

  References:
  - Barrier: Task 26 receipt/verifier.
  - Startup path: `backend/app/desktop/controller.py`, `backend/app/application.py`, `backend/app/v2/db.py:36-65` after Lane 1.
  - Reevaluation: `backend/app/v2/services/evaluation_store.py:132-163`.
  - Existing synthetic patterns: `backend/tests/v2_migration_fixtures.py` and `backend/tests/test_v2_operational_workflow.py`.
  - UI content boundaries: `frontend/src/v2/AppV2.tsx:42-69,76-118,142-200` and the named page components.

  Acceptance criteria:
  - Certificate-bound frozen online barrier verification passes before harness import; Task-26 instrumentation-only comparison passes before commit; both target smoke sets contain exactly two valid samples per fixture/mode and no discarded sample, and are labeled non-comparative.
  - Every sample reports one init/migration/reevaluation invocation, readiness 200, clean authenticated stop, no owned process/state, the per-data-dir lease unheld (the persistent lock file may remain), and safe stage timings.
  - Re-running summary generation from raw JSON produces byte-identical medians/p95/fixture hashes.
  - `python -m pytest backend/tests/performance/test_contracts.py backend/tests/performance/test_timing_sink.py backend/tests/test_lane1_barrier.py -q --junitxml="$ATTEMPT_DIR/task-27-foundation.xml"` and `npm --prefix frontend test -- --run src/v2/performanceMarks.test.tsx` exit 0, proving exact comparator rules, deterministic fixtures, disabled-sink silence, all seven post-content marks, AST-equivalent instrumentation, and rejection when a primary median/sign passes but its p95 regresses by 5.0000001% or more.

  QA scenarios:
  ```text
  Scenario: Deterministic native source-harness smoke on both target OSes
    Tool:     GitHub Actions CLI
    Steps:    After the Task-27 commit run `set -euo pipefail; SMOKE_SHA=$(git rev-parse HEAD); python scripts/performance/dispatch_paired_candidate.py --lane1-receipt "$ATTEMPT_DIR/lane1-barrier.json" --candidate-type foundation-smoke --workflow-ref "$SMOKE_SHA" --control-ref "$SMOKE_SHA" --candidate-ref "$SMOKE_SHA" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --targets windows,macos --output-dir "$ATTEMPT_DIR/task-27-native"`.
    Expected: Exit 0; exact Windows x64 and macOS arm64 jobs emit complete non-comparative raw/summary schemas, provenance, two samples per fixture/mode, one init per run, matching fixture hashes, cleanup=true, and no activation consumes these files.
    Evidence: $ATTEMPT_DIR/task-27-native/collection-receipt.json and $ATTEMPT_DIR/task-27-native/{windows,macos}/source-startup-smoke.json

  Scenario: Missing barrier, non-instrumentation edit, primary-p95 regression, failed run, secret marker, and sample omission invalidate summary
    Tool:     bash
    Steps:    Run `python -m pytest backend/tests/performance/test_source_startup_harness.py backend/tests/performance/test_contracts.py backend/tests/test_lane1_barrier.py -q -k "missing_barrier or instrumentation or primary_p95 or failed_run or secret or omission" --junitxml="$ATTEMPT_DIR/task-27-source-startup-adversarial.xml"`.
    Expected: Each injected failure makes the gate/harness nonzero with no accepted summary; a fixture whose primary median/sign passes but p95 regresses above 5% is rejected, non-instrumentation lifecycle changes are rejected, raw failed samples remain recorded safely, and marker text is absent.
    Evidence: $ATTEMPT_DIR/task-27-source-startup-adversarial.xml
  ```

  Adversarial classes: `cold_warm_noise`, `misleading_success_output`, `privacy_canary`, `stale_state`, `semantic_drift`.

  Cleanup: Authenticated stop each sample; revalidate before fallback; remove only per-sample fixture copies and retain raw evidence.

  Commit: YES | Message: `perf(desktop): establish native measurement contracts` | Files: [`config/performance/cross-platform-v1.json`, `scripts/performance/contracts.py`, `scripts/performance/evaluate_activation.py`, `scripts/performance/compare_candidate.py`, `scripts/performance/benchmark_source_startup.py`, `scripts/performance/run_paired_candidate.py`, `scripts/performance/dispatch_paired_candidate.py`, `scripts/verification/verify_scope_fidelity.py`, `.github/workflows/desktop-performance-candidate.yml`, `backend/app/desktop/timing.py`, `backend/app/desktop/controller.py`, `backend/app/application.py`, `backend/app/v2/db.py`, `backend/tests/performance/synthetic_startup_profiles.py`, `backend/tests/performance/test_contracts.py`, `backend/tests/performance/test_timing_sink.py`, `backend/tests/performance/test_source_startup_harness.py`, `backend/tests/performance/test_paired_candidate_runner.py`, `backend/tests/verification/test_scope_fidelity.py`, `frontend/src/v2/performanceMarks.ts`, `frontend/src/v2/performanceMarks.test.tsx`, `frontend/src/v2/AppV2.tsx`, `frontend/src/v2/pages/DashboardPage.tsx`, `frontend/src/v2/pages/TreatmentPlansRosterPage.tsx`, `frontend/src/v2/pages/PatientRosterPage.tsx`, `frontend/src/v2/pages/TreatmentPlanDetailPage.tsx`, `frontend/src/v2/pages/SettingsPage.tsx`, `frontend/src/v2/pages/ForensicLogsPage.tsx`]

- [ ] 28. Implement and adversarially validate the Windows packaged startup harness

  What to do:
  - Literal first action: repeat Task26's exact certificate-bound attest-first/API-fetched frozen-verifier procedure using both independent anchors, offline bundle, and signer workflow, then run `start-task 28 --completed-through 27`; make no edit on failure. Add `scripts/performance/benchmark-windows-package.ps1` with exactly `-Lane1Receipt`, `-Mode Baseline|Candidate`, `-CandidateId`, `-Variant Onefile|Onedir`, `-Runs`, `-Fixtures`, and `-OutputDirectory`. After the exact commit/evidence, literal last action runs frozen `finish-task 28` with the same anchor/bundle/signer inputs.
  - At the committed Task-28 SHA, rebuild the folder/ZIP with CPython `3.12.10`, PyInstaller `6.16.0`, Task-27 hooks, and locked dependencies; never reuse Task-22 bytes. Re-run Task-19 scanner plus Task-22 folder/extracted-ZIP smoke and emit a provenance-complete measurement-artifact receipt. This validates the harness only; Task 31 rebuilds again at its single control SHA.
  - Execute two `cold-install` and two `warm-install` smoke samples per fixture. Preserve the exact definitions, metrics, and all raw samples so Task 31 can invoke the same harness with 10 formal samples; do not publish Task-28 numbers as the control baseline.
  - Measure process creation to readiness 200, browser dispatch, onefile extraction-visible pre-Python delay, controller stages, peak working set, executable size, and cleanup. Use ETW only if already available without admin; otherwise derive pre-Python delay from launcher/process/timing-sink timestamps and record method.
  - Preserve all samples and emit deterministic raw/median/p95 JSON bound to barrier/artifact/fixture hashes. PATH excludes developer Python/Node/Git and no elevation/prerequisite installer may run.

  Must NOT do: Do not change PyInstaller mode, optimize code, compare source to package as a candidate, discard Defender/noisy samples, require admin, reuse Task 22's uninstrumented EXE, or measure a source runtime.

  Parallelization: Can parallel: NO | Wave 16 | Blocked by: [26, 27] | Blocks: [29, 31, 32]

  References:
  - Artifact patterns: Task 19 builder and Task 22 folder/extracted-ZIP smoke; the measured bytes are rebuilt after Task 27.
  - Current onefile baseline: `packaging/windows/iz-cna-windows.spec` and original `scripts/build-windows-installer.ps1:358-389`.
  - Stage marks: Task 27 timing sink.

  Acceptance criteria:
  - Freshly rebuilt Windows artifact yields two complete non-comparative samples per fixture/mode with matching hashes, one init, readiness 200, browser-after-readiness, and cleanup=true.
  - Measurement receipt proves Task 27 hooks are inside the EXE and both folder and independently extracted ZIP retain identical inventory/behavior; it rejects Task 22 hashes as stale inputs.
  - Summary uses process-to-readiness median as the primary metric; that same cell's p95 plus pre-Python, stages, memory, size, failure, and cleanup are protected metrics.
  - An artifact mutation, receipt mismatch, missing sample, nonzero child, or remaining owned process invalidates the run.

  QA scenarios:
  ```text
  Scenario: Exact Windows EXE harness executes cold/warm smoke samples
    Tool:     GitHub Actions CLI
    Steps:    After the Task-28 commit run `set -euo pipefail; SMOKE_SHA=$(git rev-parse HEAD); python scripts/performance/dispatch_paired_candidate.py --lane1-receipt "$ATTEMPT_DIR/lane1-barrier.json" --candidate-type windows-package-smoke --workflow-ref "$SMOKE_SHA" --control-ref "$SMOKE_SHA" --candidate-ref "$SMOKE_SHA" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --targets windows --output-dir "$ATTEMPT_DIR/task-28-native"`.
    Expected: Exit 0; exact rebuilt EXE/folder/ZIP passes scanner/lifecycle, all declared two-run cold/warm smoke cells and hashes/stats exist, ownership is zero, provenance is complete, and nonce refs are deleted.
    Evidence: $ATTEMPT_DIR/task-28-native/collection-receipt.json and $ATTEMPT_DIR/task-28-native/windows/{windows-measurement-artifact-v1.json,windows-package-baseline.json}

  Scenario: Mutated EXE, omitted sample, false PASS, and leaked process fail the harness
    Tool:     PowerShell
    Steps:    Run `python -m pytest backend/tests/performance/test_windows_package_harness.py -q -k "stale or mutation or omission or false_pass or leaked" --junitxml="$env:ATTEMPT_DIR/task-28-windows-package-adversarial.xml"`.
    Expected: No accepted summary is produced, failed sample remains in raw evidence, valid artifact is unchanged, and leaked test process is revalidated/cleaned.
    Evidence: $ATTEMPT_DIR/task-28-windows-package-adversarial.xml
  ```

  Adversarial classes: `cold_warm_noise`, `misleading_success_output`, `stale_state`, `cleanup_escape`.

  Cleanup: Authenticated stop, revalidate any fallback PID, remove only per-sample installs/profiles, retain immutable original ZIP and raw evidence.

  Commit: YES | Message: `perf(windows): benchmark rebuilt packaged startup` | Files: [`scripts/performance/benchmark-windows-package.ps1`, `backend/tests/performance/test_windows_package_harness.py`]

- [ ] 29. Implement and adversarially validate the ARM64 macOS package harness

  What to do:
  - Literal first action: repeat Task26's exact certificate-bound attest-first/API-fetched frozen-verifier procedure using both independent anchors, offline bundle, and signer workflow, then run `start-task 29 --completed-through 28`; make no edit on failure. Add `scripts/performance/benchmark-macos-package.sh` with exactly `--lane1-receipt`, `--mode {baseline,candidate}`, `--candidate-id`, `--variant {app}`, `--runs`, `--fixtures`, and `--output-dir`. After the exact commit/evidence, literal last action runs frozen `finish-task 29` with the same anchor/bundle/signer inputs.
  - At the committed Task-29 SHA on explicit `macos-15` ARM64, rebuild app/DMG with CPython `3.12.10`, PyInstaller `6.16.0`, Task-27 hooks, and locked dependencies; never reuse Task-23 bytes. Re-run Task-20 scanner and Task-23 mounted/installed smoke and emit a provenance-complete artifact receipt. Task 31 rebuilds again at its one control SHA.
  - Execute two `cold-copy` and two `warm-copy` smoke samples per fixture using the final definitions. Preserve all raw metrics; label them non-comparative and never use them as candidate control evidence.
  - Measure `open`/process start to readiness, browser dispatch, pre-Python/app-loader delay, controller stages, peak RSS, app/DMG sizes, signature verification time, and cleanup. Run ad-hoc/unsigned technical artifact only; notarization/quarantine is not a performance prerequisite.
  - Preserve all samples and emit deterministic raw/median/p95 JSON bound to barrier/DMG/bundle/fixture hashes; verify no writes to bundles/DMG, delete only the unique injected Keychain test item, and prove the search list never changes.

  Must NOT do: Do not benchmark under Rosetta/Intel, change packaging, discard noisy samples, reuse Task 23's uninstrumented app, compare a notarized remote artifact to local baseline, or label headless CI as Finder/quarantine performance.

  Parallelization: Can parallel: NO | Wave 17 | Blocked by: [26, 28] | Blocks: [30, 31, 32]

  References:
  - Artifact patterns: Tasks 20/23 builder, mounted-app, and installed-app receipts; measured bytes are rebuilt after Task 27.
  - Native target: `packaging/macos/iz-cna-macos.spec`.
  - Stage marks: Task 27 timing sink.

  Acceptance criteria:
  - Freshly rebuilt ARM64 app/DMG yield two complete non-comparative samples per fixture/mode with matching hashes, one init, readiness/browser ordering, unchanged bundle hash, and cleanup=true.
  - Measurement receipt proves Task 27 hooks are inside the ARM64 app, mounted and installed behavior match, and Task 23 hashes are rejected as stale inputs.
  - Summary contains process-to-readiness primary median, independently protected process-to-readiness p95, and loader/stages/memory/size/failure/cleanup protected metrics.
  - Wrong arch, artifact mutation, missing sample, remaining volume/process/Keychain state, or nonzero child invalidates run.

  QA scenarios:
  ```text
  Scenario: Exact ARM64 app harness executes cold/warm smoke samples
    Tool:     GitHub Actions CLI
    Steps:    After the Task-29 commit run `set -euo pipefail; SMOKE_SHA=$(git rev-parse HEAD); python scripts/performance/dispatch_paired_candidate.py --lane1-receipt "$ATTEMPT_DIR/lane1-barrier.json" --candidate-type macos-package-smoke --workflow-ref "$SMOKE_SHA" --control-ref "$SMOKE_SHA" --candidate-ref "$SMOKE_SHA" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --targets macos --output-dir "$ATTEMPT_DIR/task-29-native"`.
    Expected: Exit 0 on `macos-15` arm64; rebuilt mounted/installed app pairs yield all declared two-run cold/warm cells, hashes/stats match, bundles/DMG stay unchanged, process/volume/Keychain state is zero, and nonce refs are deleted.
    Evidence: $ATTEMPT_DIR/task-29-native/collection-receipt.json and $ATTEMPT_DIR/task-29-native/macos/{macos-measurement-artifact-v1.json,macos-package-baseline.json}

  Scenario: Rosetta/wrong arch, mutated bundle, omitted sample, and mount leak fail
    Tool:     GitHub Actions CLI
    Steps:    Run `set -euo pipefail; SMOKE_SHA=$(git rev-parse HEAD); python scripts/performance/dispatch_paired_candidate.py --lane1-receipt "$ATTEMPT_DIR/lane1-barrier.json" --candidate-type macos-package-smoke --workflow-ref "$SMOKE_SHA" --control-ref "$SMOKE_SHA" --candidate-ref "$SMOKE_SHA" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --targets macos --output-dir "$ATTEMPT_DIR/task-29-native-adversarial"`; the fixed smoke job runs `test_macos_package_harness.py -k "architecture or stale or mutation or omission or leaked"` before verified cleanup.
    Expected: Exit 0 only because each isolated mutation is rejected; accepted summary is absent, valid DMG hash is unchanged, leaked test state is reported then cleaned, and no false PASS is accepted.
    Evidence: $ATTEMPT_DIR/task-29-native-adversarial/collection-receipt.json and $ATTEMPT_DIR/task-29-native-adversarial/macos/adversarial-junit.xml
  ```

  Adversarial classes: `wrong_architecture`, `cold_warm_noise`, `misleading_success_output`, `cleanup_escape`.

  Cleanup: Authenticated stop, delete/verify the unique Keychain test item with unchanged search list, unmount only test volumes, remove only per-sample apps/profiles, retain original DMG/raw evidence.

  Commit: YES | Message: `perf(macos): benchmark rebuilt ARM64 package` | Files: [`scripts/performance/benchmark-macos-package.sh`, `backend/tests/performance/test_macos_package_harness.py`]

- [ ] 30. Implement and adversarially validate authenticated endpoint measurement

  What to do:
  - Literal first action: repeat Task26's exact certificate-bound attest-first/API-fetched frozen-verifier procedure using both independent anchors, offline bundle, and signer workflow, then run `start-task 30 --completed-through 29`; make no edit on failure. Add `scripts/performance/benchmark_endpoints.py` and `scripts/performance/run_endpoint_baselines.py` with exactly `--lane1-receipt`, `--target-os {windows,macos}`, `--mode {baseline,candidate}`, `--candidate-id`, `--fixtures`, `--warmups`, `--iterations`, and `--output-dir`; use deterministic Task-27 profiles and reject barrier/foundation/fixture mismatches. After the exact commit/evidence, literal last action runs frozen `finish-task 30` with the same anchor/bundle/signer inputs.
  - Instrument SQLAlchemy `before_cursor_execute` at the harness boundary and safe decrypt-call counters; never log SQL parameter values or decrypted data. Measure `/api/v2/dashboard`, `/api/v2/patient-roster`, `/api/v2/treatment-plan-roster`, `/api/v2/treatment-plans`, `/api/v2/treatment-plans/{patient_id}`, `/api/v2/treatment-plans/{patient_id}/{treatment_plan_id}`, and `/api/v2/patients/{patient_id}` for administrator and facility-restricted office-manager users using deterministic fixture IDs.
  - Validate at this task commit with one warm-up then two recorded requests per endpoint/role/fixture/OS. Record the final fields and label results non-comparative. Task 31 invokes this same harness with 3 warm-ups and 20 formal requests at one control SHA.
  - Emit raw/median/p95 and query-count bounds. Treat any response/auth/order/audit/encryption drift as failure, not a speed result.

  Must NOT do: Do not expose SQL parameters/decrypted fields, use a superuser-only workload, optimize queries yet, discard slow requests, or treat fewer queries as sufficient without latency and semantics.

  Parallelization: Can parallel: NO | Wave 18 | Blocked by: [26, 29] | Blocks: [31, 32, 34]

  References:
  - Query path: `backend/app/v2/services/treatment_plan_store.py:48-90,260-289`.
  - Rosters: `backend/app/v2/services/patient_roster.py:49-139`, `backend/app/v2/api/roster_routes.py:13-59`.
  - Existing semantics: `backend/tests/test_v2_treatment_plan_rosters.py:48-148`, `backend/tests/test_v2_operational_workflow.py:32-68`.
  - Authorization: `backend/app/v2/authorization.py` and RBAC tests.

  Acceptance criteria:
  - Both OSes produce exactly two non-comparative recorded requests per endpoint/role/fixture after one warm-up, with zero failures/discards and identical normalized response hashes/counts/order/authorization/audit deltas.
  - Query/decrypt counters contain no values/PHI and deterministically expose scale growth for candidate evaluation.
  - A response/query/auth/audit mismatch invalidates the baseline.

  QA scenarios:
  ```text
  Scenario: Authenticated endpoint baselines capture latency, queries, and semantics
    Tool:     GitHub Actions CLI
    Steps:    After the Task-30 commit run `set -euo pipefail; SMOKE_SHA=$(git rev-parse HEAD); python scripts/performance/dispatch_paired_candidate.py --lane1-receipt "$ATTEMPT_DIR/lane1-barrier.json" --candidate-type endpoint-smoke --workflow-ref "$SMOKE_SHA" --control-ref "$SMOKE_SHA" --candidate-ref "$SMOKE_SHA" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --targets windows,macos --output-dir "$ATTEMPT_DIR/task-30-native"`.
    Expected: Exit 0; both target jobs emit complete counts/stats after one warm-up and two recorded requests, identical safe semantic hashes by fixture/role, exact provenance, cleanup=true, and no nonce ref.
    Evidence: $ATTEMPT_DIR/task-30-native/collection-receipt.json and $ATTEMPT_DIR/task-30-native/{windows,macos}/endpoint-baseline.json

  Scenario: Authorization drift, SQL-value leak, missing request, and fake fast response fail
    Tool:     bash
    Steps:    Run `python -m pytest backend/tests/performance/test_endpoint_benchmark.py -q --junitxml="$ATTEMPT_DIR/task-30-endpoints-adversarial.xml"`.
    Expected: Each injected drift/leak/omission is rejected, sensitive marker absent, and no accepted baseline is emitted.
    Evidence: $ATTEMPT_DIR/task-30-endpoints-adversarial.xml
  ```

  Adversarial classes: `semantic_drift`, `privacy_canary`, `misleading_success_output`, `cold_warm_noise`.

  Cleanup: Authenticated stop, detach SQLAlchemy listeners/counters, close sessions, and remove only fixture copies.

  Commit: YES | Message: `perf(api): add native endpoint baseline runner` | Files: [`scripts/performance/benchmark_endpoints.py`, `scripts/performance/run_endpoint_baselines.py`, `backend/tests/performance/test_endpoint_benchmark.py`]

- [ ] 31. Commit one immutable control and capture every formal native baseline

  What to do:
  - Literal first action: repeat Task26's exact certificate-bound attest-first/API-fetched frozen-verifier procedure using both independent anchors, offline bundle, and signer workflow, then run `start-task 31 --completed-through 30`; refuse edit/dispatch on failure. After the immutable Task-31 commit and baseline collection, literal last action runs frozen `finish-task 31` with the same anchor/bundle/signer inputs and every collection/raw/summary hash.
  - Add `frontend/e2e/desktop-performance.spec.mjs`, `frontend/e2e/run-desktop-performance.mjs`, `frontend/e2e/summarize-desktop-performance.mjs`, `frontend/e2e/desktop-performance-summary.test.mjs`, `scripts/performance/dispatch_baseline.py`, and `.github/workflows/desktop-performance-baseline.yml` with `on.push.branches: ['codex-ci/**']`. Keeping Node runners under `frontend/e2e/` makes package/config/module resolution unambiguous. Commit all Task-31 harness/workflow files before collecting data; define `CONTROL_SHA` as that exact clean Task-31 commit and never amend it.
  - `dispatch_baseline.py` accepts exactly `--lane1-receipt`, `--workflow-ref`, `--control-ref`, `--repository`, `--repository-id`, `--remote`, `--targets windows,macos`, and `--output-dir`. It reruns the fixed-identity preflight, authorizes/publishes/verifies workflow/control refs through only the named remote first, then publishes the canonical request trigger commit last. The push workflow validates repository ID/request/event/trigger/workflow/control hashes, binds exact run/attempt/job/runner IDs, and runs the control checkout. The dispatcher selects that exact push run/correlation, downloads by immutable ID/API digest, writes `collection-receipt.json`, and deletes refs in `finally`. Any publish/auth/correlation/digest/runner/cleanup failure is `ERROR` and collection-incomplete.
  - On the same `CONTROL_SHA`, explicit Windows 2022 x64 and `macos-15` ARM64 jobs create fresh locked environments, rebuild the instrumented native artifacts, rerun the full release scanner/lifecycle smoke, and collect every Task-27 row without aggregation: 7 source runs for each `windows|macos x source x empty|small|scale x fresh|warm-profile` cell; 10 runs for each Windows `windows-folder|windows-zip x empty|small|scale x cold-install|warm-install` cell and each macOS `macos-mounted|macos-installed x empty|small|scale x cold-copy|warm-copy` cell; 3 unrecorded warmups plus 20 retained requests for each `windows|macos x source x Task-30 endpoint x administrator|office-manager x small|scale` cell; and 3 unrecorded warmups plus 20 retained browser cycles separately on both native artifact surfaces for each target, each mapped clinical view/role/fixture cell, and each administrator-only `login-ready|settings-ready|logs-ready`/fixture cell. An authorization-denied role/view is recorded as the fixed denial semantic cell where declared, never reused as page-ready timing.
  - From `frontend/`, install/verify the pinned Playwright Chromium and invoke the frontend runner with exactly `--lane1-receipt`, `--artifact-receipt`, `--target-os {windows,macos}`, `--mode {baseline,candidate}`, `--candidate-id`, `--fixtures`, `--warmups`, `--iterations`, and `--output-dir`. It starts the exact package and records navigation-to-content-ready, DOM/load, FCP, longest task/total blocking time where available, JS/CSS transfer/decoded bytes, request/chunk counts, API timing, console/page/external-request errors, exact normalized DOM/accessibility snapshots, and a platform-specific fixed-viewport PNG. Fix viewport, Chromium revision, font bundle, locale, timezone, synthetic clock, reduced motion/disabled animations, and dynamic-region masks. Candidate visual equivalence requires exact DOM/accessibility equality and pixelmatch differing pixels <=0.1%; root-render is informational only.
  - Apply `config/performance/cross-platform-v1.json` exactly once to this control data. Persist the precommitted primary/protected cells and activation outcomes without editing the matrix: startup, Windows package-mode, endpoint, and only `settings-ready|logs-ready` frontend cells may activate under Task-27 materiality rules; every other view remains protected.
  - Aggregate validated raw files into `$ATTEMPT_DIR/task-31/control-receipt.json` and `$ATTEMPT_DIR/task-31/control-summary.json`. Both include schema, attested barrier SHA, exact `CONTROL_SHA` commit/tree, `dirty=false`, workflow/run/attempt/job/runner IDs, artifact IDs/API digests, dependency/fixture/native-artifact/raw-file hashes, complete sample counts, activation cells, arithmetic medians, and nearest-rank p95. Regeneration from raw inputs must be byte-identical.

  Must NOT do: Do not optimize, amend or cherry-pick into `CONTROL_SHA`, mix commits/runners/artifacts, reuse Task-27–30 smoke numbers, omit failed/outlier samples, use a dev server/jsdom clock, record PHI/secrets/paths, post-select cells, or let a root-render mark satisfy readiness.

  Parallelization: Can parallel: NO | Wave 19 | Blocked by: [26, 27, 28, 29, 30] | Blocks: [32, 35, 36]

  References:
  - Barrier/foundation: Tasks 26–27 attested receipt, frozen verifier, fixed matrix, comparator, and collection schema.
  - Native harnesses: Tasks 28–30 package and endpoint runners; their two-sample outputs are contract smoke only.
  - Build/test: `frontend/package.json:6-33`, `frontend/playwright.desktop.config.mjs` from Task 21, `frontend/e2e/desktop-global-setup.mjs:1-31`.
  - GitHub runner contract: `https://docs.github.com/en/actions/using-github-hosted-runners/about-github-hosted-runners`.

  Acceptance criteria:
  - Frozen online barrier verification passes before import; `CONTROL_SHA` equals the clean committed Task-31 workflow/harness tree and every workflow/job/artifact/raw receipt is cryptographically and API-provenance-bound to it.
  - Both OSes contain exactly 7 valid source samples per declared `source` fixture/profile cell, 10 valid package samples per declared fixture/mode on each of the two target-specific artifact surfaces, and 20 valid endpoint/browser samples per declared surface-specific cell after exactly 3 unrecorded warmups where specified; missing, duplicate, or cross-surface-aggregated rows and failed samples make the receipt fail.
  - Native release scan/lifecycle, one-init, readiness/browser ordering, semantic/auth/privacy assertions, and cleanup pass for each artifact; frontend samples have matching asset hashes and no console/page/external-request error.
  - `python scripts/performance/contracts.py verify-collection --receipt "$ATTEMPT_DIR/task-31/collection-receipt.json" --control-ref "$(git rev-parse HEAD)" --targets windows,macos` and `python scripts/performance/contracts.py reproduce-summary --receipt "$ATTEMPT_DIR/task-31/control-receipt.json" --expected "$ATTEMPT_DIR/task-31/control-summary.json"` exit 0.

  QA scenarios:
  ```text
  Scenario: One exact control commit produces the complete paired native baseline
    Tool:     bash
    Steps:    After committing Task 31 run `set -euo pipefail; test "$REPOSITORY" = "martyw1/IZ_clinical-notes-analyzer"; test "$REPOSITORY_ID" = "1172715348"; test "$REPOSITORY_NODE_ID" = "R_kgDOReY3VA"; test "$GITHUB_REMOTE" = "origin"; CONTROL_SHA=$(git rev-parse HEAD); python scripts/performance/dispatch_baseline.py --lane1-receipt "$ATTEMPT_DIR/lane1-barrier.json" --workflow-ref "$CONTROL_SHA" --control-ref "$CONTROL_SHA" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --targets windows,macos --output-dir "$ATTEMPT_DIR/task-31"; python scripts/performance/contracts.py reproduce-summary --receipt "$ATTEMPT_DIR/task-31/control-receipt.json" --expected "$ATTEMPT_DIR/task-31/control-summary.json"`.
    Expected: Both commands exit 0; the receipt names one clean `CONTROL_SHA`, exact native jobs/artifacts/digests, every formal cell/sample, deterministic summaries/activation, and confirmed temporary-ref cleanup.
    Evidence: $ATTEMPT_DIR/task-31/collection-receipt.json, $ATTEMPT_DIR/task-31/control-receipt.json, and $ATTEMPT_DIR/task-31/control-summary.json

  Scenario: Mixed commit, omitted slow sample, premature mark, secret canary, digest mismatch, and uncleared ref fail closed
    Tool:     bash
    Steps:    Run `node --test --test-reporter=tap --test-reporter-destination="$ATTEMPT_DIR/task-31/frontend-adversarial.tap" --test-name-pattern="mixed|root-only|premature|omitted|console|external|secret|digest|cleanup" frontend/e2e/desktop-performance-summary.test.mjs`.
    Expected: The test command exits 0 only when every corrupt collection is rejected, every raw failure remains accounted for, secret text is absent, and no accepted receipt is emitted.
    Evidence: $ATTEMPT_DIR/task-31/frontend-adversarial.tap
  ```

  Adversarial classes: `semantic_drift`, `privacy_canary`, `cold_warm_noise`, `stale_provenance`, `cleanup_escape`.

  Cleanup: Authenticated-stop every package, close browser/session/listener state, delete synthetic profiles and nonce refs in `finally`, and retain redacted immutable raw/control receipts.

  Commit: YES | Message: `perf(baseline): freeze native control measurements` | Files: [`frontend/e2e/desktop-performance.spec.mjs`, `frontend/e2e/run-desktop-performance.mjs`, `frontend/e2e/summarize-desktop-performance.mjs`, `frontend/e2e/desktop-performance-summary.test.mjs`, `scripts/performance/dispatch_baseline.py`, `.github/workflows/desktop-performance-baseline.yml`]

- [ ] 32. Evaluate and conditionally optimize deterministic startup reevaluation

  What to do:
  - Literal first action: repeat Task26's exact certificate-bound attest-first/API-fetched frozen-verifier procedure using both independent anchors, offline bundle, and signer workflow, then run `start-task 32 --completed-through 31`; make no edit on failure. Run `evaluate_activation.py` against Task31/fixed policy. If `NOT_MATERIAL`, create no worktree, prove product diff empty, commit only `docs/performance/startup-reevaluation-decision.md`, then run frozen `finish-task 32` with the same anchor/bundle/signer inputs as the literal last action.
  - Only for `ACTIVATED`, capture the clean immediate `CONTROL_SHA`, create one detached candidate worktree at `$ATTEMPT_DIR/worktrees/task32-candidate`, and implement there. Add constant `EVALUATION_ENGINE_VERSION`, `backend/app/v2/migrations/schema_evaluation_fingerprint.py`, and exact migration 11 with only `ALTER TABLE evaluation_runs ADD COLUMN engine_version TEXT NOT NULL DEFAULT 'legacy-unversioned'` and `ALTER TABLE evaluation_runs ADD COLUMN settings_fingerprint_sha256 TEXT NOT NULL DEFAULT '0000000000000000000000000000000000000000000000000000000000000000'`. Register/checksum these exact statements, add both columns to the schema verifier, and update the raw INSERT/SELECT paths to write explicit non-sentinel values. Existing sentinel rows never match a current fingerprint. No ORM model change is required because this ledger uses raw SQL.
  - Compute canonical SHA-256 over exact length-prefixed UTF-8 fields in this order: plan-version/evidence SHA, checklist version plus packaged checklist resource SHA, rules version plus packaged rules resource SHA, facility-local evaluation date, IANA facility timezone, sorted `RULE_SETTING_FIELDS` name/value canonical JSON, evaluator-engine version, latest schema version, and visible app version/build/channel. A call-graph/fixture test mutates each field independently. Fetch latest metadata for all plan versions in one set query before decrypting; decrypt/evaluate only exact-current startup rows while preserving append-only evaluation/criterion ledgers and audit provenance.
  - Permit the fast path only when `trigger_kind == 'startup'` and the latest completed immutable run has an exact non-sentinel fingerprint. `date_rollover`, `migration`, `sync`, `import`, `correction`, `manager_action`, `rule_config_change`, `loc_change`, `new_review`, and `authorized_refresh` always reevaluate regardless of fingerprint; interrupted/incomplete prior work never matches. Full migrations, schema verification, integrity, foreign-key, WAL, interrupted-job recovery, admin/facility, and corruption checks run on every startup before this decision.
  - Commit one scanner-clean candidate SHA in the detached worktree. Dispatch through Task 27 with mandatory exact `--workflow-ref`, immediate `--control-ref`, and `--candidate-ref`. Each native job uses sibling checkouts, identical locks/fixtures/artifacts, one runner allocation, and ABBA pairing across the complete protected startup matrix on both OSes: 7 source pairs for every `empty|small|scale` x `fresh|warm-profile` cell and 10 cold plus 10 warm package pairs for every `empty|small|scale` x declared artifact-surface cell. Selected `small|scale` cells are primaries; empty, unselected, other-profile/mode, and other-surface cells remain protected. The collection receipt must bind every expected cell/run/job/artifact/digest/raw identity and prove temporary-ref cleanup; one missing protected cell is `ERROR`, never `REJECTED`.
  - Compare the fixed Task31-selected mirrored primary cells and every complete protected cell using the unchanged comparator/collection receipt. Before applying, run scope verification for only declared startup files. `ACCEPTED` requires every primary median/sign test, each primary cell's p95 regression independently `<=5%`, every other protected median/p95/scalar within 5%, exact clinical/audit/privacy/invalidation behavior, and exactly the declared migration-10→11 schema transformation/checksum/column defaults/triggers; all other schema objects/row counts match. Otherwise leave product code untouched. Apply accepted diff+decision as one commit; rejected/not-material commits only decision. Literal last action after the final Task32 commit is frozen `finish-task 32` with both anchors/bundle/signer inputs.

  Must NOT do: Do not create/read a candidate worktree on `NOT_MATERIAL`, skip integrity/migration/FK/WAL checks, use mtime or clean-shutdown alone, mutate immutable rows, miss an invalidation input, compare different hosts/fixtures/artifacts, post-select cells, or claim Task-3 one-init work as a gain.

  Parallelization: Can parallel: NO | Wave 20 | Blocked by: [26, 27, 28, 29, 30, 31] | Blocks: [33, 36]

  References:
  - Activation/control: Tasks 27 and 31 fixed matrix, evaluator, formal control receipt, and comparator.
  - Startup: `backend/app/v2/db.py:36-65`; evaluation: `backend/app/v2/services/evaluation_store.py:47-65,132-218`.
  - Settings: `backend/app/v2/api/foundation_routes.py:27-35` (`RULE_SETTING_FIELDS`).
  - Migration: `backend/app/v2/migrations/registry.py:34-67`, `backend/app/v2/migrations/schema_verifier.py`; raw ledger SQL is `backend/app/v2/services/evaluation_store.py:181-218`.
  - Integrity tests: `backend/tests/test_v2_migration_regressions.py:38-105`, `backend/tests/test_v2_schema_contract.py:80-112`.

  Acceptance criteria:
  - Frozen verifier and activation evaluator pass; `NOT_MATERIAL` creates no worktree/product diff, while any candidate/control/collection receipt is exact-SHA, same-allocation, digest-bound, complete, and clean.
  - An accepted path recomputes on every enumerated invalidation and skips decryption/evaluation only for exact fingerprints; append-only ledgers, audit, authorization, and clinical outputs are identical.
  - Every selected mirrored primary cell meets the median plus sign-test policy on both target OSes; the receipt contains every `empty|small|scale` source/profile/package-mode/artifact-surface protected cell; every primary-cell p95 and every other protected median/p95/scalar stays within 5%; and scope verification passes before product application. Missing protected data is `ERROR`; a measured rejection leaves only the decision document.
  - The final Task-32 commit contains exactly the decision document plus the allowlisted candidate files when `ACCEPTED`, and `python scripts/performance/contracts.py verify-decision --candidate-type startup-reevaluation --receipt "$ATTEMPT_DIR/task-32/decision.json" --main-ref HEAD` exits 0.

  QA scenarios:
  ```text
  Scenario: Activation branches safely and an activated candidate is paired on both native targets
    Tool:     PowerShell
    Steps:    Run `python scripts/performance/evaluate_activation.py --candidate-type startup-reevaluation --control-receipt "$env:ATTEMPT_DIR/task-31/control-receipt.json" --policy config/performance/cross-platform-v1.json --output "$env:ATTEMPT_DIR/task-32/activation.json"`; if the receipt says `NOT_MATERIAL`, assert `Test-Path "$env:ATTEMPT_DIR/worktrees/task32-candidate"` is false and run `python scripts/performance/contracts.py verify-no-candidate --activation "$env:ATTEMPT_DIR/task-32/activation.json" --control-ref "$(git rev-parse HEAD)" --output "$env:ATTEMPT_DIR/task-32/decision.json"`; otherwise run `python scripts/performance/dispatch_paired_candidate.py --lane1-receipt "$env:ATTEMPT_DIR/lane1-barrier.json" --candidate-type startup-reevaluation --workflow-ref "$(git rev-parse HEAD)" --control-ref "$env:CONTROL_SHA" --candidate-ref "$env:CANDIDATE_SHA" --repository "$env:REPOSITORY" --repository-id "$env:REPOSITORY_ID" --remote "$env:GITHUB_REMOTE" --targets windows,macos --output-dir "$env:ATTEMPT_DIR/task-32"` followed by `python scripts/performance/compare_candidate.py --candidate-type startup-reevaluation --control-dir "$env:ATTEMPT_DIR/task-32/controls" --candidate-dir "$env:ATTEMPT_DIR/task-32/candidates" --collection-receipt "$env:ATTEMPT_DIR/task-32/collection-receipt.json" --policy config/performance/cross-platform-v1.json --output "$env:ATTEMPT_DIR/task-32/decision.json"`.
    Expected: `NOT_MATERIAL` exits 0 with no candidate/product diff; `ACTIVATED` exits 0 only with exact paired provenance, fixed-cell decision, safe cleanup, and truthful ACCEPTED/REJECTED result.
    Evidence: $ATTEMPT_DIR/task-32/activation.json, $ATTEMPT_DIR/task-32/collection-receipt.json when activated, and $ATTEMPT_DIR/task-32/decision.json

  Scenario: Corruption, schema/FK/WAL drift, incomplete invalidation, sample omission, and forged activation fail closed
    Tool:     bash
    Steps:    If activated, run `python -m pytest backend/tests/test_startup_evaluation_fingerprint.py backend/tests/test_v2_migration_regressions.py backend/tests/test_v2_schema_contract.py backend/tests/performance/test_paired_candidate_runner.py -q --junitxml="$ATTEMPT_DIR/task-32/startup-adversarial.xml"` in the candidate worktree; otherwise run `python -m pytest backend/tests/performance/test_contracts.py -q -k "activation or forged or omission" --junitxml="$ATTEMPT_DIR/task-32/startup-adversarial.xml"` on main.
    Expected: Exit 0 only because every corrupt/forged/incomplete case is rejected, required full checks cannot hit the fast path, and the real branch/evidence remain unchanged.
    Evidence: $ATTEMPT_DIR/task-32/startup-adversarial.xml
  ```

  Adversarial classes: `semantic_drift`, `cold_warm_noise`, `misleading_success_output`, `stale_provenance`, `dirty_worktree`.

  Cleanup: Authenticated-stop all benchmark instances; require the collection receipt to prove temporary refs deleted; if a candidate exists, archive its diff/receipt, require clean status after the intended temporary commit, then remove only that exact worktree; retain raw decisions and never reset shared changes.

  Commit: YES | Message: `perf(startup): gate reevaluation with complete fingerprints` if accepted, otherwise `docs(perf): record startup reevaluation decision` | Files: [`docs/performance/startup-reevaluation-decision.md`; accepted only: `backend/app/v2/services/evaluation_store.py`, `backend/app/v2/migrations/registry.py`, `backend/app/v2/migrations/schema_evaluation_fingerprint.py`, `backend/app/v2/migrations/schema_verifier.py`, `backend/tests/test_startup_evaluation_fingerprint.py`, `backend/tests/test_v2_migration_regressions.py`, `backend/tests/test_v2_schema_contract.py`]

- [ ] 33. Compare Windows onefile versus onedir and conditionally select the measured mode

  What to do:
  - Literal first action: repeat Task26's exact certificate-bound attest-first/API-fetched frozen-verifier procedure using both independent anchors, offline bundle, and signer workflow, run `start-task 33 --completed-through 32`, then validate Task32's committed decision; make no edit on failure. Capture the clean immediate `CONTROL_SHA`, create one detached candidate worktree at `$ATTEMPT_DIR/worktrees/task33-candidate`, and make a Windows-only onedir candidate; macOS files are out of scope. Literal last action after commit/evidence is frozen `finish-task 33` with the same anchor/bundle/signer inputs.
  - Before building the candidate, make `config/release/desktop-package-manifest.json` explicitly variant-aware: both variants retain the same required resources/version/frontend/config inventory, while the executable/runtime-file cardinality is declared separately. Update the manifest verifier/tests in the candidate so neither a onefile assertion nor an unbounded onedir tree can pass. Change only PyInstaller collection mode, its manifest inventory, scanner expectation, builder copy step, and matching Windows deployment text; dependencies, application code, compression policy, outer release folder, one-root ZIP, installer/shortcut/maintenance semantics remain identical.
  - Commit one scanner-clean candidate SHA. Dispatch with mandatory exact workflow/control/candidate refs. On one Windows x64 allocation, sibling locked checkouts build both variants and run ABBA-paired 10 samples for every exact `(artifact_surface, fixture, package_mode)` key in `{windows-folder,windows-zip} x {empty,small,scale} x {cold-install,warm-install}`. The four exact primary keys are `(windows-folder,small,cold-install)`, `(windows-folder,scale,cold-install)`, `(windows-zip,small,cold-install)`, and `(windows-zip,scale,cold-install)`; every other declared key is protected. Both variants must pass raw-name ZIP validation, manifest hash/inventory, scanner, install, first run, browser ordering, second launch, stop/drain, restart/persistence, diagnostics, backup/restore, deferred/normal uninstall, and folder/extracted-ZIP parity before comparison. A missing/duplicate key or any surface aggregation is `ERROR`, so the always-measured task still ends only `REJECTED|ACCEPTED` after a complete collection.
  - Use the immediate onefile SHA as control; Task-28 smoke and Task-31 control establish contracts only. Each of the four named primary keys has its own median/sign-test decision and protected p95; never combine folder with ZIP or small with scale. Protected cells/fields include every remaining surface/fixture/mode median and p95, failures, working set, executable/folder/ZIP size, extraction residue, lifecycle, resource hashes, scanner, and nontechnical surfaces.
  - Run the unchanged comparator with its collection receipt, then Task-27 scope verification allowing only the declared packaging files. Apply the candidate plus decision document as one main commit only on `ACCEPTED`; otherwise commit only `docs/performance/packaging-mode-decision.md`. In both outcomes, the decision records every sample/hash/job, threshold/sign-test result, every primary-cell p95, every other protected result, and cleanup proof. Literal last action after the final Task33 commit is frozen `finish-task 33` with both anchors/bundle/signer inputs.

  Must NOT do: Do not change macOS, application semantics, dependencies, release-folder/ZIP distribution, installer behavior, or unrelated docs; do not accept size alone, omit a sample, reuse extraction directories, use stale controls, or claim a Mac gain.

  Parallelization: Can parallel: NO | Wave 21 | Blocked by: [26, 32] | Blocks: [34, 36]

  References:
  - Windows spec/build: `packaging/windows/iz-cna-windows.spec`, `scripts/build-windows-installer.ps1`, Task 19.
  - Manifest/scanner: `config/release/desktop-package-manifest.json`, `scripts/release-safety.ps1`, `backend/tests/test_windows_release_manifest.py` after Lane 1.
  - Deployment guide: `docs/windows-installer-build-and-install.md`.
  - PyInstaller modes: `https://pyinstaller.org/en/stable/operating-mode.html`.

  Acceptance criteria:
  - Both variants have exact declared inventories and identical required resource/version/frontend/config hashes, pass the full lifecycle/scanner, and use the same commit inputs except the allowlisted collection-mode diff.
  - `ACCEPTED` occurs only when all four exact cold primary surface/fixture keys independently pass median plus sign test, every corresponding p95 regresses no more than 5%, and every other surface/mode/size/memory/p95/lifecycle/safety field passes; otherwise the production spec/builder/manifest/docs remain unchanged.
  - The decision receipt binds 10 cold and 10 warm samples for every `empty|small|scale` x staged-folder/extracted-ZIP x variant cell to one Windows runner/job and exact artifact/raw hashes; temporary refs and build roots are accounted for.
  - ARM64 app/DMG paths are absent from the Task-33 product diff, and `python scripts/verification/verify_scope_fidelity.py --candidate-type packaging-mode --control-ref "$CONTROL_SHA" --candidate-ref "$CANDIDATE_SHA" --decision "$ATTEMPT_DIR/task-33/decision.json"` exits 0 before application.

  QA scenarios:
  ```text
  Scenario: Same-allocation onefile/onedir A/B preserves the Windows release contract
    Tool:     PowerShell
    Steps:    Run `python scripts/performance/dispatch_paired_candidate.py --lane1-receipt "$env:ATTEMPT_DIR/lane1-barrier.json" --candidate-type packaging-mode --workflow-ref "$(git rev-parse HEAD)" --control-ref "$env:CONTROL_SHA" --candidate-ref "$env:CANDIDATE_SHA" --repository "$env:REPOSITORY" --repository-id "$env:REPOSITORY_ID" --remote "$env:GITHUB_REMOTE" --targets windows --output-dir "$env:ATTEMPT_DIR/task-33"`; then run `python scripts/performance/compare_candidate.py --candidate-type packaging-mode --control-dir "$env:ATTEMPT_DIR/task-33/controls" --candidate-dir "$env:ATTEMPT_DIR/task-33/candidates" --collection-receipt "$env:ATTEMPT_DIR/task-33/collection-receipt.json" --policy config/performance/cross-platform-v1.json --output "$env:ATTEMPT_DIR/task-33/decision.json"`.
    Expected: Commands exit 0; decision follows fixed policy, both variants have complete scanner/lifecycle evidence, and Mac artifacts/diffs are absent.
    Evidence: $ATTEMPT_DIR/task-33/collection-receipt.json and $ATTEMPT_DIR/task-33/decision.json

  Scenario: Stale extraction, missing resource, unbounded onedir file, size regression, and unequal inputs fail
    Tool:     PowerShell
    Steps:    Run `python -m pytest backend/tests/performance/test_paired_candidate_runner.py backend/tests/performance/test_windows_package_harness.py backend/tests/test_windows_release_manifest.py -q -k "stale_extraction or missing_resource or unexpected_runtime_file or unequal_input_hash or size_regression or lifecycle_failure" --junitxml="$env:ATTEMPT_DIR/task-33/packaging-adversarial.xml"` in the candidate worktree.
    Expected: Exit 0 only because every corrupt comparison/artifact is rejected; the valid control remains unchanged and no rejected candidate reaches main.
    Evidence: $ATTEMPT_DIR/task-33/packaging-adversarial.xml
  ```

  Adversarial classes: `stale_state`, `forbidden_release_canary`, `cold_warm_noise`, `semantic_drift`, `scope_drift`.

  Cleanup: Authenticated-stop instances; require remote-ref cleanup in the receipt; remove only verified variant build/extract roots; archive the clean candidate diff/receipt and remove only its detached worktree; retain immutable evidence and touch no Mac state.

  Commit: YES | Message: `perf(windows): select measured onedir runtime` if accepted, otherwise `docs(perf): retain measured Windows runtime` | Files: [`docs/performance/packaging-mode-decision.md`; accepted only: `packaging/windows/iz-cna-windows.spec`, `config/release/desktop-package-manifest.json`, `scripts/build-windows-installer.ps1`, `backend/tests/test_windows_release_manifest.py`, `docs/windows-installer-build-and-install.md`]

- [ ] 34. Measure and conditionally batch treatment-plan/roster query paths

  What to do:
  - Literal first action: repeat Task26's exact certificate-bound attest-first/API-fetched frozen-verifier procedure using both independent anchors, offline bundle, and signer workflow, run `start-task 34 --completed-through 33`, then validate Task33's decision; make no edit on failure. Run the fixed activation evaluator on Task31. If `NOT_MATERIAL`, create no worktree, prove no service/route diff, commit only `docs/performance/endpoint-query-decision.md`, and run frozen `finish-task 34` with the same anchor/bundle/signer inputs last.
  - Only for `ACTIVATED`, create a detached candidate from the clean immediate `CONTROL_SHA`. Add set-based reads in `migrated_treatment_plan.py`/`treatment_plan_store.py` for selected version/evaluation/criterion/snapshot rows; group deterministically by `(canonical_client_id, source_system, source_record_id)`, decrypt each required snapshot at most once per request, and preserve exact `StoredTreatmentPlan` shapes/order. Pass the already-authorized patient-ID set through roster/record routes so unauthorized rows are neither fetched nor decrypted.
  - If Task 32 was accepted, bulk reuse only exact-current fingerprints; otherwise preserve the original evaluation path. In both cases preserve date rollover, manager actions, sources, corrections, lineage/tie-breaks, facility filters, audit counts, error behavior, and encrypted-field boundaries.
  - Commit one scanner-clean candidate SHA. Dispatch with mandatory exact workflow/control/candidate refs to both native OSes. Each job uses sibling locked checkouts on one allocation and ABBA pairs 3 warmups plus 20 retained requests for every selected and protected endpoint/role/fixture cell; full auth, roster, record, evaluation, encryption, and audit suites run on both revisions.
  - Compare only immutable selected cells with the collection receipt. `ACCEPTED` requires median/sign-test policy on every mirrored primary, each primary-cell p95 regression independently `<=5%`, every other protected median/p95/query/decrypt/memory scalar within policy, bounded query growth, exact normalized payload/order/auth/audit hashes, and zero unauthorized decrypts. Run scope verification before applying. Accepted code+decision become one main commit; rejected/not-material commits only decision. Literal last action after the final Task34 commit is frozen `finish-task 34` with both anchors/bundle/signer inputs.

  Must NOT do: Do not create/read a candidate on `NOT_MATERIAL`, cache decrypted PHI across requests, weaken facility/RBAC filtering, reorder results, skip rollover/evaluation, expose SQL values, accept query-count alone, post-select endpoints, or refactor unrelated routes.

  Parallelization: Can parallel: NO | Wave 22 | Blocked by: [26, 30, 33] | Blocks: [35, 36]

  References:
  - Activation/control: Tasks 27/30/31 contracts and formal endpoint data.
  - Store path: `backend/app/v2/services/treatment_plan_store.py:48-90,260-289`.
  - Consumers: `backend/app/v2/services/patient_roster.py:49-139`, `backend/app/v2/services/patient_record.py:42-101`.
  - Authorization: `backend/app/v2/api/roster_routes.py:13-59`, `backend/app/v2/api/runtime_routes.py`, `backend/app/v2/authorization.py`.
  - Semantics: `backend/tests/test_v2_treatment_plan_rosters.py:48-148`, `backend/tests/test_v2_auth_rbac.py`, Task-1 contract.

  Acceptance criteria:
  - Frozen verification/activation pass; `NOT_MATERIAL` produces no candidate/service/route diff, and any activated collection is exact-SHA, digest-bound, complete, same-allocation, and cleaned.
  - Accepted code has bounded scale query/decrypt counts, identical payload/order/auth/audit/encryption/error behavior, zero unauthorized fetch/decrypt, and all fixed cross-platform performance rules pass.
  - Scope verifier permits only the declared service/route/tests plus decision document; rejected/not-material paths leave those product files unchanged.
  - `python scripts/performance/contracts.py verify-decision --candidate-type endpoint-query --receipt "$ATTEMPT_DIR/task-34/decision.json" --main-ref HEAD` exits 0 after the Task-34 commit.

  QA scenarios:
  ```text
  Scenario: Activation branches safely and paired endpoint evidence governs acceptance
    Tool:     bash
    Steps:    Run `python scripts/performance/evaluate_activation.py --candidate-type endpoint-query --control-receipt "$ATTEMPT_DIR/task-31/control-receipt.json" --policy config/performance/cross-platform-v1.json --output "$ATTEMPT_DIR/task-34/activation.json"`; for `NOT_MATERIAL`, run `test ! -e "$ATTEMPT_DIR/worktrees/task34-candidate" && python scripts/performance/contracts.py verify-no-candidate --activation "$ATTEMPT_DIR/task-34/activation.json" --control-ref "$(git rev-parse HEAD)" --output "$ATTEMPT_DIR/task-34/decision.json"`; for `ACTIVATED`, run `python scripts/performance/dispatch_paired_candidate.py --lane1-receipt "$ATTEMPT_DIR/lane1-barrier.json" --candidate-type endpoint-query --workflow-ref "$(git rev-parse HEAD)" --control-ref "$CONTROL_SHA" --candidate-ref "$CANDIDATE_SHA" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --targets windows,macos --output-dir "$ATTEMPT_DIR/task-34"` followed by `python scripts/performance/compare_candidate.py --candidate-type endpoint-query --control-dir "$ATTEMPT_DIR/task-34/controls" --candidate-dir "$ATTEMPT_DIR/task-34/candidates" --collection-receipt "$ATTEMPT_DIR/task-34/collection-receipt.json" --policy config/performance/cross-platform-v1.json --output "$ATTEMPT_DIR/task-34/decision.json"`.
    Expected: Inactive flow exits 0 without a candidate; activated flow exits 0 only with complete fixed-cell provenance and a truthful ACCEPTED/REJECTED decision.
    Evidence: $ATTEMPT_DIR/task-34/activation.json, $ATTEMPT_DIR/task-34/collection-receipt.json when activated, and $ATTEMPT_DIR/task-34/decision.json

  Scenario: Authorization, ordering, rollover, decrypt, omitted-sample, and forged-activation drift fail
    Tool:     bash
    Steps:    If activated, run `python -m pytest backend/tests/performance/test_query_candidate_equivalence.py backend/tests/test_v2_auth_rbac.py backend/tests/test_v2_treatment_plan_rosters.py backend/tests/performance/test_paired_candidate_runner.py -q --junitxml="$ATTEMPT_DIR/task-34/query-adversarial.xml"` in the candidate worktree; otherwise run `python -m pytest backend/tests/performance/test_contracts.py -q -k "activation or endpoint or omission" --junitxml="$ATTEMPT_DIR/task-34/query-adversarial.xml"` on main.
    Expected: Exit 0 only because every fast-but-wrong/forged case is rejected, unauthorized decrypt count stays zero, and main product code remains unchanged unless accepted.
    Evidence: $ATTEMPT_DIR/task-34/query-adversarial.xml
  ```

  Adversarial classes: `semantic_drift`, `privacy_canary`, `cold_warm_noise`, `stale_provenance`, `authorization_bypass`.

  Cleanup: Authenticated-stop runtimes, detach query hooks, require remote-ref cleanup, archive clean candidate diff/receipt, remove only its detached worktree and contained fixtures, and retain immutable evidence.

  Commit: YES | Message: `perf(api): batch authorized treatment-plan reads` if accepted, otherwise `docs(perf): record endpoint-query decision` | Files: [`docs/performance/endpoint-query-decision.md`; accepted only: `backend/app/v2/services/migrated_treatment_plan.py`, `backend/app/v2/services/treatment_plan_store.py`, `backend/app/v2/services/patient_roster.py`, `backend/app/v2/services/patient_record.py`, `backend/app/v2/api/runtime_routes.py`, `backend/app/v2/api/roster_routes.py`, `backend/tests/performance/test_query_candidate_equivalence.py`, `backend/tests/test_v2_auth_rbac.py`, `backend/tests/test_v2_treatment_plan_rosters.py`]

- [ ] 35. Defer or conditionally introduce measured frontend route splitting

  What to do:
  - Literal first action: repeat Task26's exact certificate-bound attest-first/API-fetched frozen-verifier procedure using both independent anchors, offline bundle, and signer workflow, run `start-task 35 --completed-through 34`, then validate Task34's decision; make no edit on failure. Run the fixed activation evaluator on Task31. If `NOT_MATERIAL`, create no worktree, prove AppV2/Vite product diff empty, commit only `docs/performance/frontend-splitting-decision.md`, and run frozen `finish-task 35` with the same anchor/bundle/signer inputs last.
  - Only for `ACTIVATED`, create a detached candidate at the clean immediate `CONTROL_SHA`. Add `frontend/src/v2/lazyPages.tsx` and change `AppV2.tsx` so exactly `SettingsPage` and `ForensicLogsPage` use `React.lazy` with one deterministic accessible `Suspense` fallback. Do not change Vite configuration or split any other page; both pages are the fixed candidate, selected cells are primary, and the other page/cells remain protected.
  - Commit one scanner-clean candidate SHA. Dispatch with mandatory exact workflow/control/candidate refs to both native OSes. Sibling locked checkouts on each allocation rebuild the complete artifact, pass scanner/lifecycle/offline checks, and ABBA pair 3 warmups plus 20 retained content-ready samples for both settings/logs fixtures; all seven Task-31 views remain protected functional/performance coverage.
  - Verify dynamic chunks are locally packaged, hashed, manifest-listed and load after network denial; fallback is never blank/stuck; focus/accessibility and content-ready-after-data semantics remain. Under Task31's fixed Chromium/viewport/font/locale/timezone/clock/motion/mask contract, normalized DOM/accessibility snapshots remain exact and pixelmatch differing pixels are <=0.1%; requests, console/page errors, API hashes, and external requests stay within protected rules.
  - Run the unchanged comparator/collection receipt and scope verifier allowing only the three frontend files plus decision. Every selected view's primary median/sign must pass while that same view's p95 independently stays within 5%; all other view/size/DOM/accessibility/pixel metrics remain protected. Apply code+decision as one main commit only on `ACCEPTED`; rejected/not-material commits only decision. Literal last action after the final Task35 commit is frozen `finish-task 35` with both anchors/bundle/signer inputs.

  Must NOT do: Do not create/read a candidate on `NOT_MATERIAL`, split unmeasured/unrouted pages, modify Vite, redesign UI, add dependencies/features, fetch CDN/network chunks, defer login/dashboard/clinical pages, accept jsdom timing, post-select cells, or retain rejected code.

  Parallelization: Can parallel: NO | Wave 23 | Blocked by: [26, 31, 34] | Blocks: [36]

  References:
  - Routes: `frontend/src/v2/AppV2.tsx`, `frontend/src/v2/pages/SettingsPage.tsx`, `frontend/src/v2/pages/ForensicLogsPage.tsx`.
  - Build/test: `frontend/vite.config.ts:1-19`, `frontend/package.json:6-33`, `frontend/src/App.test.tsx`, `frontend/e2e/*.spec.mjs`.
  - Measurement: Tasks 27 and 31 fixed marks, cells, formal receipt, and comparator.

  Acceptance criteria:
  - Frozen verification/activation pass; `NOT_MATERIAL` creates no candidate/frontend product diff, and activated collection is exact-SHA, digest-bound, complete, same-allocation, and cleaned.
  - Accepted artifact contains only the expected settings/logs dynamic chunks, works with network denied on both OSes, preserves all seven views' semantics/visual/accessibility/API behavior, and has zero chunk/console/page/external-request errors.
  - Every selected mirrored primary cell passes median plus sign test and its own p95 stays within 5% on both OSes; all other view medians/p95, API, bytes, request, normalized DOM/accessibility, <=0.1% pixel-diff and exact-zero fields pass; scope verification excludes Vite and every other page.
  - `python scripts/performance/contracts.py verify-decision --candidate-type frontend-splitting --receipt "$ATTEMPT_DIR/task-35/decision.json" --main-ref HEAD` exits 0 after the Task-35 commit.

  QA scenarios:
  ```text
  Scenario: Activation branches safely and exact settings/logs chunks face native paired gates
    Tool:     PowerShell plus Playwright real Chromium
    Steps:    Run `python scripts/performance/evaluate_activation.py --candidate-type frontend-splitting --control-receipt "$env:ATTEMPT_DIR/task-31/control-receipt.json" --policy config/performance/cross-platform-v1.json --output "$env:ATTEMPT_DIR/task-35/activation.json"`; for `NOT_MATERIAL`, assert `Test-Path "$env:ATTEMPT_DIR/worktrees/task35-candidate"` is false and run `python scripts/performance/contracts.py verify-no-candidate --activation "$env:ATTEMPT_DIR/task-35/activation.json" --control-ref "$(git rev-parse HEAD)" --output "$env:ATTEMPT_DIR/task-35/decision.json"`; for `ACTIVATED`, run `python scripts/performance/dispatch_paired_candidate.py --lane1-receipt "$env:ATTEMPT_DIR/lane1-barrier.json" --candidate-type frontend-splitting --workflow-ref "$(git rev-parse HEAD)" --control-ref "$env:CONTROL_SHA" --candidate-ref "$env:CANDIDATE_SHA" --repository "$env:REPOSITORY" --repository-id "$env:REPOSITORY_ID" --remote "$env:GITHUB_REMOTE" --targets windows,macos --output-dir "$env:ATTEMPT_DIR/task-35"` followed by `python scripts/performance/compare_candidate.py --candidate-type frontend-splitting --control-dir "$env:ATTEMPT_DIR/task-35/controls" --candidate-dir "$env:ATTEMPT_DIR/task-35/candidates" --collection-receipt "$env:ATTEMPT_DIR/task-35/collection-receipt.json" --policy config/performance/cross-platform-v1.json --output "$env:ATTEMPT_DIR/task-35/decision.json"`.
    Expected: Inactive flow exits 0 without candidate code; activated flow exits 0 only with complete paired native/offline evidence and truthful ACCEPTED/REJECTED result.
    Evidence: $ATTEMPT_DIR/task-35/activation.json, $ATTEMPT_DIR/task-35/collection-receipt.json when activated, and $ATTEMPT_DIR/task-35/decision.json

  Scenario: Missing chunk, network fetch, visual/accessibility drift, erroring page, and extra split fail
    Tool:     bash plus Playwright real Chromium
    Steps:    If activated, run `npm --prefix frontend test -- --run src/v2/AppV2.lazy.test.tsx --reporter=json --outputFile="$ATTEMPT_DIR/task-35/lazy-adversarial.json"` and `node --test --test-reporter=tap --test-reporter-destination="$ATTEMPT_DIR/task-35/browser-adversarial.tap" --test-name-pattern="missing chunk|external request|visual drift|page error|extra split|stuck fallback" frontend/e2e/desktop-performance-summary.test.mjs`; otherwise run `python -m pytest backend/tests/performance/test_contracts.py -q -k "activation or frontend" --junitxml="$ATTEMPT_DIR/task-35/no-candidate-adversarial.xml"`.
    Expected: Commands exit 0 only because every invalid candidate/activation is rejected; traces contain synthetic data only and rejected code never reaches main.
    Evidence: $ATTEMPT_DIR/task-35/lazy-adversarial.json and $ATTEMPT_DIR/task-35/browser-adversarial.tap when activated; otherwise $ATTEMPT_DIR/task-35/no-candidate-adversarial.xml
  ```

  Adversarial classes: `semantic_drift`, `forbidden_release_canary`, `misleading_success_output`, `privacy_canary`, `scope_drift`.

  Cleanup: Close browser/runtimes, require remote-ref cleanup, remove contained candidate dist, archive clean diff/receipt, remove only its detached worktree, and retain accepted artifacts or immutable rejection evidence.

  Commit: YES | Message: `perf(frontend): lazy-load measured settings and logs` if accepted, otherwise `docs(perf): record frontend-splitting decision` | Files: [`docs/performance/frontend-splitting-decision.md`; accepted only: `frontend/src/v2/AppV2.tsx`, `frontend/src/v2/lazyPages.tsx`, `frontend/src/v2/AppV2.lazy.test.tsx`]

- [ ] 36. Certify the final cross-platform performance lane without semantic drift

  What to do:
  - Literal first action: repeat Task26's exact externally anchored approved-plan rerender plus certificate-bound attest-first/API-fetched frozen-verifier procedure using both independent anchors, offline bundle, and signer workflow, run `start-task 36 --completed-through 35`, validate Tasks32/34/35 decision plus conditional raw/collection hashes, and require Task33's `REJECTED|ACCEPTED` decision with complete paired raw/collection hashes; make no edit on failure. Add `.github/workflows/desktop-performance.yml` with `on.push.branches: ['codex-ci/**']`, `scripts/verification/run_final_certification.py`, `dispatch_manual_surface_qa.py`, `run_manual_surface_qa.py`, `build_evidence_index.py`, `verify_plan_compliance.py`, `run_final_diagnostics.py`, `run_agent_review.py`, `run_final_wave.py`, `scripts/performance/verify_final_performance.py`, four strict reviewer schemas, and boundary tests/fixtures.
  - Commit all Task-36 code first and set immutable `FINAL_SHA` to that exact clean commit. Read immutable `CONTROL_SHA` from Task31's control receipt. `run_final_certification.py` accepts exactly `--lane1-receipt`, `--workflow-ref`, `--control-ref`, `--final-ref`, `--repository`, `--repository-id`, `--remote`, and `--output-dir`; it reruns fixed-identity preflight, publishes/verifies workflow/control/final refs through only the named remote first, publishes the canonical request trigger last, validates exact repository/push event/request/trigger/workflow/target/run/attempt/job correlation, downloads by artifact ID/API digest, and atomically writes exactly `$OUTPUT_DIR/collection-receipt.json`, `$OUTPUT_DIR/windows/artifact-receipt.json`, and `$OUTPUT_DIR/macos/artifact-receipt.json` before cleaning refs in `finally`. Each platform job is the sole producer of its platform receipt; the collector verifies and copies those exact bytes rather than synthesizing them locally. The collection schema names both child receipt artifact IDs/API digests/content SHA-256 values; each platform schema contains target OS/architecture, `FINAL_SHA` commit/tree, workflow/run/attempt/job/runner, artifact ID/API digest/content SHA-256, release-inventory SHA-256, scanner/lifecycle receipt SHA-256 values, and the complete native artifact-surface inventory (`windows-folder|windows-zip` or `macos-mounted|macos-installed`). Missing/extra fields, a child not named by the collection, or two receipts from different runs is fatal.
  - On one Windows x64 allocation and one `macos-15` ARM64 allocation, sibling locked checkouts rebuild/scan/smoke control and final artifacts and ABBA pair every exact Task-27 cell with no aggregation: 7 source runs per target/`source`/fixture/profile; 10 package runs per Windows `windows-folder|windows-zip` fixture/`cold-install|warm-install` key and per macOS `macos-mounted|macos-installed` fixture/`cold-copy|warm-copy` key; 3 warmups plus 20 endpoint samples per target/`source`/endpoint/role/fixture; and 3 warmups plus 20 browser samples separately for each target-specific artifact surface/view/declared role/fixture. Missing, duplicate, or substituted surfaces are `ERROR`. Re-run full backend/frontend/browser/migration/security/lifecycle/scanner suites on `FINAL_SHA`; do not certify archived measurements alone.
  - Verify every accepted candidate's original decision/product diff and prove rejected/not-material candidates have no product diff. With accepted candidates, the final stack preserves the union of precommitted primary median/sign-test gains, every primary-cell p95 ceiling, and every other protected median/p95/scalar/equivalence rule versus Task31. With zero accepted, if product and packaged-artifact hashes equal Task31 after excluding declared decision/final-harness files, record `NO_PRODUCT_CHANGE` and permit Task31 values; otherwise the full final rerun is mandatory and records `ZERO_ACCEPTED_REMEASURED`, requiring every protected median/p95/scalar/equivalence rule but no nonexistent primary gain. An incomplete/mismatched native run is `ERROR` and must rerun, never `REJECTED`.
  - Generate after certification and outside git `$ATTEMPT_DIR/task-36/final-performance.json`, `$ATTEMPT_DIR/task-36/performance-report.md`, and `$ATTEMPT_DIR/task-36/evidence-index.json` containing raw hashes, commits/trees/dirty=false, workflow/jobs/runners/artifacts, the Task-36 collection plus both exact platform-receipt hashes, arithmetic median/nearest-rank p95 for every surface-specific cell, decisions, zero-accepted branch, limits, cleanup, and separate external gates. `verify_final_performance.py` must receive both `--output <json>` and `--report <md>` and reproduce both byte-for-byte. Then run the API-fetched Task-26 verifier `finish-task 36 --completed-through 36` online against `FINAL_SHA` with the source anchor, trigger anchor, offline bundle, exact signer workflow, evidence-index hash, final-performance hash, report hash, final-collection hash, and both platform-artifact-receipt hashes; exclusively write `$ATTEMPT_DIR/task-36/barrier-post.json`. F1-F4 refuse to start without verifying that post receipt and all three Task-36 native receipt hashes.
  - `dispatch_manual_surface_qa.py` accepts exactly `--lane1-receipt`, `--workflow-ref`, `--final-ref`, `--final-collection-receipt`, `--windows-artifact-receipt`, `--macos-artifact-receipt`, `--repository`, `--repository-id`, `--remote`, `--scenarios`, and `--output-dir`. Before dispatch it schema-validates the three Task-36 inputs, recomputes their hashes, requires one exact final workflow run/attempt and `FINAL_SHA`, requires each platform receipt's artifact ID/API digest/content SHA/inventory to be a named child of that collection, and rejects duplicate/stale/same-SHA-but-different-run artifacts. It then launches the final workflow's Windows and ARM64 macOS manual-surface jobs with those exact IDs/digests, correlates repository/run/attempt/jobs, downloads only by the supplied IDs/digests, writes a collection receipt containing the three input hashes and every selected artifact identity, and cleans nonce refs through only the named remote in `finally`. Native jobs call `run_manual_surface_qa.py` with exactly `--target-os`, `--artifact-receipt`, `--scenarios`, and `--output-dir`; the artifact receipt passed is byte-identical to its supplied Task-36 platform receipt.
  - `run_agent_review.py` provides the exact F1-F4 reviewer contract: accept `--review {plan-compliance,code-quality,manual-surface-qa,scope-fidelity}`, `--base-ref`, `--head-ref`, `--evidence-index`, one or more `--machine-receipt`, `--schema`, and `--output`; create an isolated clean review worktree and `CODEX_HOME`, invoke Codex CLI read-only with `gpt-5.6-sol` at `xhigh`, require schema-valid JSON with verdict `APPROVE|REJECT` and evidence-backed findings, and delete the worktree/home in `finally`. The reviewer must receive each just-created machine receipt, not merely a stale pre-review index. For `manual-surface-qa`, the schema additionally requires `engineering_verdict` exactly `APPROVE|REJECT`; `windows_release_statuses` is exactly `["APPROVE"]` only when both Windows external receipts pass, otherwise it is the sorted unique complete set of the two exact Windows Scope blockers whose corresponding receipt is missing/failing; `macos_release_statuses` is exactly `["APPROVE"]` only when all three Mac external receipts pass, otherwise it is the sorted unique complete set of the three exact Apple/macOS Scope blockers whose corresponding receipt is missing/failing. Omitting an applicable blocker, adding a blocker whose receipt passes, mixing `APPROVE` with a blocker, or using an unknown string is schema failure. The review also binds exact final SHA, evidence-index hash, both F3 collection hashes, all four native-receipt hashes, Task-36 final-collection hash, and both Task-36 artifact-receipt hashes. No blocker array changes `engineering_verdict`; tool absence/nonzero/invalid JSON is `REJECT`.
  - `run_final_wave.py` accepts exactly `--base-ref`, `--head-ref`, `--evidence-index`, `--source-anchor`, `--trigger-anchor`, `--attestation-bundle`, `--signer-workflow`, `--task36-post-receipt`, `--final-collection-receipt`, `--windows-artifact-receipt`, `--macos-artifact-receipt`, `--output-dir`, `--repository`, `--repository-id`, and `--remote`; before spawning, it schema-validates and hashes the three explicit Task-36 native receipts against the post receipt/evidence index, repeats fixed typed GitHub identity, proves the retained Task26 tag resolves to the anchored commit, rerenders the tracked `config/verification/approved-cross-platform-plan.md`, performs Task26 certificate-bound subject verification, and runs the frozen verifier through Task36, then launches F1-F4 simultaneously in four isolated worktrees/caches. It passes both anchors/bundle/signer/post receipt to F1/F4, passes those exact three Task-36 receipt paths to F3, records process IDs/start/end monotonic timestamps and proves all four intervals overlap before any completes, and terminates the other lanes on orchestration failure. Only after every subprocess exits zero, all four schema verdicts are `APPROVE`, and F3's `engineering_verdict=APPROVE` with valid separate platform status arrays, it revalidates the durable tag name/object/SHA, deletes exactly that tag through the named remote without force, independently confirms it absent through Git and GitHub APIs, and writes `final-wave.json` with the four receipt hashes, structured platform statuses, and anchor-cleanup proof. Failure to delete/confirm the exact tag fails final wave. Each lane uses fail-fast subprocess execution; shell command concatenation may not hide an earlier nonzero exit.

  Must NOT do: Do not certify before the Task-36 commit, edit/amend `FINAL_SHA` afterward, average platforms, hide failed/tied samples, compare different hosts, reopen rejected candidates, require a speedup when zero candidates were accepted, commit generated final reports, weaken safety, or claim signed/quarantined clean-Mac readiness from CI.

  Parallelization: Can parallel: NO | Wave 24 | Blocked by: [26, 31, 32, 33, 34, 35] | Blocks: [F1, F2, F3, F4]

  References:
  - Control/contracts: Tasks 26–31 attested barrier, exact Task-31 control receipt, fixed policy and harnesses.
  - Trust inputs: `$ATTEMPT_DIR/task-26-source-anchor.json`, `$ATTEMPT_DIR/task-26-trigger-anchor.json`, the exact offline attestation bundle, `$ATTEMPT_DIR/lane1-barrier.json`, and the Task-26 verifier fetched by anchored GitHub blob/content hash.
  - Final trust output: `$ATTEMPT_DIR/task-36/barrier-post.json` binds `FINAL_SHA`, evidence-index hash, final-performance hash, and performance-report hash before F1-F4.
  - Decisions: `docs/performance/*-decision.md` from Tasks 32–35.
  - Scope verifier: Task-27 `scripts/verification/verify_scope_fidelity.py` (do not recreate it here).
  - Portability artifacts: Tasks 22/23/26; full suites: repository `AGENTS.md` and Task-1 contract.
  - Codex noninteractive CLI: `https://developers.openai.com/codex/noninteractive`.

  Acceptance criteria:
  - The frozen verifier passes first; `FINAL_SHA` is the committed clean Task-36 tree; exact native control/final siblings complete every formal surface-specific sample and full suite with correct architecture, locks, hashes, provenance, no omissions, and cleanup. `run_final_certification.py` produces the exact collection/Windows/macOS receipt paths and schemas above, with both child hashes named by the collection; after evidence generation frozen `finish-task 36` passes and binds those three native receipts plus the final report/index hashes in `$ATTEMPT_DIR/task-36/barrier-post.json`.
  - `verify_final_performance.py` validates the collection, candidate decisions, changed-file classification and either the accepted-union branch or exact zero-accepted branch; rejected candidate code is absent.
  - `python -m pytest backend/tests/performance/test_final_performance_verifier.py backend/tests/verification/test_final_review_tools.py -q --junitxml="$ATTEMPT_DIR/task-36/verifiers.xml"` exits 0 and covers forged receipts, missing jobs or platform artifact receipt, stale refs, moved/deleted durable Task26 tag, cross-host/surface pairing, ties/omissions, primary-median/sign pass with 6% p95 regression, policy/scope drift, zero-accepted outcomes, Task-36 artifact-ID/digest substitution, omitted applicable blocker, spurious blocker, invalid/mixed external status arrays, missing/forged Task36 post receipt, reviewer failure, and cleanup.
  - The generated evidence index, JSON, and `performance-report.md` reproduce from raw inputs, name external release gates separately, and agree byte-for-byte on commits/outcomes/hashes; no generated report is in the Task-36 commit. The final frozen post verifier passes through Task36.

  QA scenarios:
  ```text
  Scenario: Committed final SHA receives complete same-allocation native certification
    Tool:     PowerShell
    Steps:    After committing Task36 run a fail-fast PowerShell block: `$ErrorActionPreference='Stop'; $finalSha=(git rev-parse HEAD); if ($LASTEXITCODE) { exit $LASTEXITCODE }; $controlSha=(python scripts/performance/contracts.py get-field --receipt "$env:ATTEMPT_DIR/task-31/control-receipt.json" --field control_commit); if ($LASTEXITCODE) { exit $LASTEXITCODE }; python scripts/verification/run_final_certification.py --lane1-receipt "$env:ATTEMPT_DIR/lane1-barrier.json" --workflow-ref "$finalSha" --control-ref "$controlSha" --final-ref "$finalSha" --repository "$env:REPOSITORY" --repository-id "$env:REPOSITORY_ID" --remote "$env:GITHUB_REMOTE" --output-dir "$env:ATTEMPT_DIR/task-36/native"; if ($LASTEXITCODE) { exit $LASTEXITCODE }; python scripts/performance/verify_final_performance.py --lane1 "$env:ATTEMPT_DIR/lane1-barrier.json" --control-ref "$controlSha" --final-ref "$finalSha" --collection-receipt "$env:ATTEMPT_DIR/task-36/native/collection-receipt.json" --decision-dir docs/performance --policy config/performance/cross-platform-v1.json --output "$env:ATTEMPT_DIR/task-36/final-performance.json" --report "$env:ATTEMPT_DIR/task-36/performance-report.md"; if ($LASTEXITCODE) { exit $LASTEXITCODE }; python scripts/verification/build_evidence_index.py --plan config/verification/approved-cross-platform-plan.md --evidence-dir "$env:ATTEMPT_DIR" --git-range "8c1edc460c2af354f74417cf27d26abaf72ccc70..$finalSha" --output "$env:ATTEMPT_DIR/task-36/evidence-index.json"; if ($LASTEXITCODE) { exit $LASTEXITCODE }; python $env:FROZEN_LANE1_VERIFIER finish-task 36 --completed-through 36 --receipt "$env:ATTEMPT_DIR/lane1-barrier.json" --source-anchor "$env:ATTEMPT_DIR/task-26-source-anchor.json" --trigger-anchor "$env:ATTEMPT_DIR/task-26-trigger-anchor.json" --attestation-bundle $env:ATTESTATION_BUNDLE --signer-workflow "$env:REPOSITORY/.github/workflows/desktop-artifacts.yml" --repository $env:REPOSITORY --repository-id $env:REPOSITORY_ID --approved-plan-sha256 $env:APPROVED_PLAN_SHA256 --current-head $finalSha --evidence-index "$env:ATTEMPT_DIR/task-36/evidence-index.json" --final-performance "$env:ATTEMPT_DIR/task-36/final-performance.json" --performance-report "$env:ATTEMPT_DIR/task-36/performance-report.md" --final-collection-receipt "$env:ATTEMPT_DIR/task-36/native/collection-receipt.json" --windows-artifact-receipt "$env:ATTEMPT_DIR/task-36/native/windows/artifact-receipt.json" --macos-artifact-receipt "$env:ATTEMPT_DIR/task-36/native/macos/artifact-receipt.json" --output "$env:ATTEMPT_DIR/task-36/barrier-post.json" --online; exit $LASTEXITCODE`.
    Expected: All commands exit 0; the collection receipt names and hashes the exact Windows/macOS artifact receipts from one final run, receipts name exact control/final commits and every surface-specific paired sample, the correct accepted-union or zero-accepted rule passes, `barrier-post.json` binds the clean Task36 commit, all three native receipts, and all three generated evidence hashes, and temporary refs are deleted.
    Evidence: $ATTEMPT_DIR/task-36/native/collection-receipt.json, $ATTEMPT_DIR/task-36/native/windows/artifact-receipt.json, $ATTEMPT_DIR/task-36/native/macos/artifact-receipt.json, $ATTEMPT_DIR/task-36/final-performance.json, $ATTEMPT_DIR/task-36/performance-report.md, $ATTEMPT_DIR/task-36/evidence-index.json, and $ATTEMPT_DIR/task-36/barrier-post.json

  Scenario: Hidden/tied sample, platform averaging, stale control, semantic mismatch, leftover rejected diff, and forged reviewer output fail
    Tool:     bash
    Steps:    Run `python -m pytest backend/tests/performance/test_final_performance_verifier.py backend/tests/verification/test_final_review_tools.py -q -k "hidden or tie or primary_p95 or platform_average or stale or semantic or rejected_diff or missing_post_receipt or forged_post_receipt or reviewer" --junitxml="$ATTEMPT_DIR/task-36/final-adversarial.xml"`.
    Expected: Exit 0 only because every mutation is rejected, no certification/review approval is forged, and original evidence stays immutable.
    Evidence: $ATTEMPT_DIR/task-36/final-adversarial.xml
  ```

  Adversarial classes: `cold_warm_noise`, `semantic_drift`, `stale_provenance`, `misleading_success_output`, `cleanup_escape`, `zero_candidate_false_failure`.

  Cleanup: Native jobs authenticated-stop and target-clean; Task-36 dispatchers/reviewers remove only nonce refs and isolated worktrees/homes after identity checks; retain exact artifacts, immutable reports/evidence, and the validated Task26 tag for F1-F4. Only `run_final_wave.py`, after all four approvals, deletes that exact tag and proves absence.

  Commit: YES | Message: `perf(desktop): add final cross-platform certification` | Files: [`.github/workflows/desktop-performance.yml`, `scripts/verification/run_final_certification.py`, `scripts/verification/dispatch_manual_surface_qa.py`, `scripts/verification/run_manual_surface_qa.py`, `scripts/verification/build_evidence_index.py`, `scripts/verification/verify_plan_compliance.py`, `scripts/verification/run_final_diagnostics.py`, `scripts/verification/run_agent_review.py`, `scripts/verification/run_final_wave.py`, `config/verification/review-schemas/plan-compliance.json`, `config/verification/review-schemas/code-quality.json`, `config/verification/review-schemas/manual-surface-qa.json`, `config/verification/review-schemas/scope-fidelity.json`, `scripts/performance/verify_final_performance.py`, `backend/tests/performance/test_final_performance_verifier.py`, `backend/tests/verification/test_final_review_tools.py`, `backend/tests/verification/fixtures/forged-barrier.json`, `backend/tests/verification/fixtures/missing-native-job.json`, `backend/tests/verification/fixtures/stale-provenance.json`, `backend/tests/verification/fixtures/cross-host-pairing.json`, `backend/tests/verification/fixtures/primary-p95-regression.json`, `backend/tests/verification/fixtures/zero-accepted.json`, `backend/tests/verification/fixtures/reviewer-invalid.json`, `backend/tests/verification/fixtures/scope-unclassified.patch`]

## Final verification wave
> After Task36's frozen post receipt passes, invoke `run_final_wave.py` once to run F1-F4 concurrently in four isolated worktrees/caches. Its overlap receipt and all four schema-valid `APPROVE` results are mandatory; surface them to the caller and pause for the caller's explicit okay before declaring the execution handoff closed. That okay authorizes closure only: it is not an implementation acceptance criterion and can never turn a failed/missing review or check green.
> Exact invocation: `python scripts/verification/run_final_wave.py --base-ref 8c1edc460c2af354f74417cf27d26abaf72ccc70 --head-ref "$(git rev-parse HEAD)" --evidence-index "$ATTEMPT_DIR/task-36/evidence-index.json" --source-anchor "$ATTEMPT_DIR/task-26-source-anchor.json" --trigger-anchor "$ATTEMPT_DIR/task-26-trigger-anchor.json" --attestation-bundle "$ATTESTATION_BUNDLE" --signer-workflow "$REPOSITORY/.github/workflows/desktop-artifacts.yml" --task36-post-receipt "$ATTEMPT_DIR/task-36/barrier-post.json" --final-collection-receipt "$ATTEMPT_DIR/task-36/native/collection-receipt.json" --windows-artifact-receipt "$ATTEMPT_DIR/task-36/native/windows/artifact-receipt.json" --macos-artifact-receipt "$ATTEMPT_DIR/task-36/native/macos/artifact-receipt.json" --output-dir "$ATTEMPT_DIR/final-wave" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE"`; require exit 0 and `$ATTEMPT_DIR/final-wave/final-wave.json` with verified fixed typed-repository/approved-plan/anchor/bundle/post/final-collection/platform-artifact hashes, four overlapping intervals, four `APPROVE` verdicts, F3 engineering/platform status fields, and exact durable-tag deletion/absence proof.
- [ ] F1. Plan compliance and two-lane barrier audit

  What to do:
  - Consume the immutable `$ATTEMPT_DIR/task-36/evidence-index.json`, both Task26 independent anchors, offline attestation bundle, and `$ATTEMPT_DIR/task-36/barrier-post.json`; do not regenerate/modify them. Before parsing the barrier, repeat the exact certificate-bound signer/digest/source/ref verification and API-fetched frozen verifier through Task36. Run `verify_plan_compliance.py` against all 36 task commits, the Task1 pre-anchored graph/scopes/outcome subjects, Task26 direct-attested barrier/source+trigger anchors, Task36 post/final receipts, native artifact receipts, and every criterion/QA evidence entry.
  - Recompute task/matrix dependencies and commit ancestry; prove every Lane-2 action descends from and timestamps after Task-26 PASS, every implementation task landed with its tests, all scenarios ran on the declared surface, and rejected/not-material candidates left no product diff.
  - Invoke Task-36 `run_agent_review.py` with the plan-compliance schema. The isolated reviewer receives the plan, base..HEAD diff/history, evidence index, just-created compliance receipt, both independent anchors, and Task36 post receipt; `APPROVE` requires zero missing/contradictory tasks, criteria, QA, evidence, barrier edges, signer/provenance findings, or retrospective policy changes.

  Must NOT do: Do not modify the branch/evidence, accept self-reported PASS text, waive a missing task/scenario/receipt, or turn an unavailable external Apple RC gate into engineering failure or PASS.

  Parallelization: Can parallel: YES | Final wave | Blocked by: [36] | Blocks: [final handoff]

  References: this entire plan; Task-36 `scripts/verification/verify_plan_compliance.py`, `scripts/verification/run_agent_review.py`, and plan-compliance schema; `$ATTEMPT_DIR/task-26-source-anchor.json`; `$ATTEMPT_DIR/task-26-trigger-anchor.json`; exact offline attestation bundle; `$ATTEMPT_DIR/lane1-barrier.json`; `$ATTEMPT_DIR/task-36/barrier-post.json`; `$ATTEMPT_DIR/task-36/final-performance.json`; `$ATTEMPT_DIR/task-36/evidence-index.json`; native receipts.

  Acceptance criteria:
  - `verify_plan_compliance.py` exits 0 and the isolated schema-bound reviewer exits 0 with verdict exactly `APPROVE` and empty findings; both receipts bind the same base/head/index, source-anchor, trigger-anchor, attestation-bundle, signer-workflow, and Task36-post hashes.
  - If any external release gate is unavailable, reviewer reports its exact Scope `RELEASE BLOCKED` status separately and does not convert it to engineering PASS or plan failure.

  QA scenarios:
  ```text
  Scenario: Every planned result is traceable to executable evidence
    Tool:     bash
    Steps:    Run `set -euo pipefail; python scripts/verification/verify_plan_compliance.py --plan config/verification/approved-cross-platform-plan.md --approved-plan-sha256 "$APPROVED_PLAN_SHA256" --base-ref 8c1edc460c2af354f74417cf27d26abaf72ccc70 --head-ref HEAD --lane1-receipt "$ATTEMPT_DIR/lane1-barrier.json" --source-anchor "$ATTEMPT_DIR/task-26-source-anchor.json" --trigger-anchor "$ATTEMPT_DIR/task-26-trigger-anchor.json" --attestation-bundle "$ATTESTATION_BUNDLE" --signer-workflow "$REPOSITORY/.github/workflows/desktop-artifacts.yml" --task36-post-receipt "$ATTEMPT_DIR/task-36/barrier-post.json" --final-receipt "$ATTEMPT_DIR/task-36/final-performance.json" --evidence-index "$ATTEMPT_DIR/task-36/evidence-index.json" --output "$ATTEMPT_DIR/f1/plan-compliance.json"; python scripts/verification/run_agent_review.py --review plan-compliance --base-ref 8c1edc460c2af354f74417cf27d26abaf72ccc70 --head-ref HEAD --evidence-index "$ATTEMPT_DIR/task-36/evidence-index.json" --machine-receipt "$ATTEMPT_DIR/f1/plan-compliance.json" --machine-receipt "$ATTEMPT_DIR/task-26-source-anchor.json" --machine-receipt "$ATTEMPT_DIR/task-26-trigger-anchor.json" --machine-receipt "$ATTEMPT_DIR/task-36/barrier-post.json" --schema config/verification/review-schemas/plan-compliance.json --output "$ATTEMPT_DIR/f1/reviewer.json"`.
    Expected: Both exit 0; reviewer verdict is exactly APPROVE with no findings, hashes/edges agree, and no task passes from prose or source-text inspection alone.
    Evidence: $ATTEMPT_DIR/f1/plan-compliance.json and $ATTEMPT_DIR/f1/reviewer.json

  Scenario: Removed receipt and pre-barrier Lane 2 canaries are rejected
    Tool:     pytest
    Steps:    Run `python -m pytest backend/tests/verification/test_final_review_tools.py -q -k "missing_receipt or missing_anchor or wrong_signer or wrong_source_ref or forged_post_receipt or pre_barrier_lane2 or retrospective_graph or self_report_only or invalid_reviewer_json" --junitxml="$ATTEMPT_DIR/f1/plan-compliance-adversarial.xml"`.
    Expected: Exit 0 because every isolated invalid fixture is rejected; original evidence/branch remains unchanged.
    Evidence: $ATTEMPT_DIR/f1/plan-compliance-adversarial.xml
  ```

  Adversarial classes: `misleading_success_output`, `stale_state`, `dirty_worktree`.

  Cleanup: Read-only except temp metadata copies under `ATTEMPT_DIR`.

  Commit: NO | Message: n/a | Files: []

- [ ] F2. Code quality, diagnostics, security, and migration-integrity review

  What to do:
  - Run read-only code review over the complete diff from `8c1edc460c2af354f74417cf27d26abaf72ccc70` to final HEAD. Check bootstrap import boundaries, type/error contracts, lock/process identity, token secrecy, lifecycle cleanup, archive crypto/framing, path containment, native adapter correctness, release scripts, CI secret handling, benchmark validity, and dead/duplicate Windows logic.
  - Run Task-36 diagnostics, which must execute and receipt exactly: `git diff --check`; `python -m compileall -q backend/app backend/tests scripts`; full `python -m pytest backend/tests -q`; `npm --prefix frontend ci`; `npm --prefix frontend test -- --run`; `npm --prefix frontend run build`; PowerShell parser checks for every `.ps1`; `bash -n` for every shipped `.sh`; migration/schema/integrity/FK/WAL and route-classification tests; secret/PHI/release scanners; and validation of both exact Task-36 native packaged-smoke receipts. Do not invent ruff/mypy/type gates absent from repository configuration.
  - Invoke `run_agent_review.py` with the code-quality schema. It must inspect the diff plus diagnostic/native receipts and reject broad abstractions, unreachable fallbacks, duplicated archive logic, weakened checks, hidden performance drift, ignored errors, or out-of-scope files.

  Must NOT do: Do not edit code during review, suppress diagnostics, skip a configured suite, replace native artifact execution with mocks/source inspection, or downgrade a correctness/security finding to make the gate pass.

  Parallelization: Can parallel: YES | Final wave | Blocked by: [36] | Blocks: [final handoff]

  References: final diff; repository `AGENTS.md`; Task-36 diagnostics/reviewer and code-quality schema; Task-1 contract; Tasks 4/6/10/26/36 security/verifier files; migration registry/tests.

  Acceptance criteria:
  - Diagnostics exit 0 with every exact command/native validation marked executed/pass, and the isolated schema-bound reviewer exits 0 with verdict exactly `APPROVE` and no findings.
  - Every platform conditional has native coverage or an explicit safe unsupported failure; no Mac claim is based only on mocks.

  QA scenarios:
  ```text
  Scenario: Complete diff and diagnostics are clean
    Tool:     bash
    Steps:    Run `set -euo pipefail; python scripts/verification/run_final_diagnostics.py --base-ref 8c1edc460c2af354f74417cf27d26abaf72ccc70 --head-ref HEAD --lane1-receipt "$ATTEMPT_DIR/lane1-barrier.json" --native-evidence-dir "$ATTEMPT_DIR/task-36/native" --output-dir "$ATTEMPT_DIR/f2/diagnostics"; python scripts/verification/run_agent_review.py --review code-quality --base-ref 8c1edc460c2af354f74417cf27d26abaf72ccc70 --head-ref HEAD --evidence-index "$ATTEMPT_DIR/task-36/evidence-index.json" --machine-receipt "$ATTEMPT_DIR/f2/diagnostics/receipt.json" --schema config/verification/review-schemas/code-quality.json --output "$ATTEMPT_DIR/f2/reviewer.json"`.
    Expected: Both exit 0, reviewer verdict is APPROVE with no findings, every declared suite/native receipt actually ran, and scanners report zero forbidden payloads.
    Evidence: $ATTEMPT_DIR/f2/diagnostics/receipt.json and $ATTEMPT_DIR/f2/reviewer.json

  Scenario: Token-log and skipped-integrity canaries are caught
    Tool:     pytest
    Steps:    Run `python -m pytest backend/tests/verification/test_final_review_tools.py -q -k "token_log or skipped_integrity or skipped_native_job or reviewer_tool_failure" --junitxml="$ATTEMPT_DIR/f2/code-quality-adversarial.xml"`.
    Expected: Exit 0 because all canaries are blocking; production tree is not modified.
    Evidence: $ATTEMPT_DIR/f2/code-quality-adversarial.xml
  ```

  Adversarial classes: `privacy_canary`, `semantic_drift`, `misleading_success_output`.

  Cleanup: Remove only scanner/parser temp fixtures; leave build/evidence artifacts needed by F3.

  Commit: NO | Message: n/a | Files: []

- [ ] F3. Real end-user surface QA on exact Windows and macOS artifacts

  What to do:
  - Use Task-36 `dispatch_manual_surface_qa.py` so this parallel review never assumes both OSes are local. Supply the exact Task-36 final collection receipt plus its Windows and ARM64 macOS artifact receipts on every invocation; jobs consume only those already-scanned artifact IDs/digests and run every happy/adverse scenario. The dispatcher produces one cross-host collection receipt binding all three supplied receipt hashes and proves temporary-ref cleanup.
  - Windows invokes the staged/extracted CMD launch, stop, backup, restore, diagnostics and uninstall surfaces through `Start-Process`/ShellExecute, then uses packaged Playwright real Chromium for synthetic first-password-change, login, upload, checklist, persistence and browser-ordering assertions. Include second launch, cooperative/15-second forced-drain, restart, normal uninstall and complete uninstall.
  - macOS mounts/copies the exact DMG, invokes main/Utilities with `open -n`, drives `Install/Upgrade for Me` into isolated `~/Applications`, and runs packaged browser plus backup/restore/diagnostics/two-app upgrade/uninstall and profile-scoped Keychain cleanup. It proves the search list unchanged. This is engineering exact-artifact QA, not a clean downloaded-Mac/Finder claim.
  - Report external release gates independently and mechanically: evaluate the two Windows and three Mac Scope gates one by one against their exact receipt schema/hash. A platform array is `["APPROVE"]` only when every gate for that platform passes; otherwise it is the sorted unique complete set of every exact Scope `RELEASE BLOCKED` value whose gate receipt is missing/failing. Task-22 Windows `-ClientSurface` supplies the eligible Windows 10/11 interactive standard-user evidence; Task-24 supplies signing/notary evidence; the clean macOS14 lower-bound and quarantine/Finder receipts remain external. Missing environments/credentials do not change engineering `APPROVE`, but no applicable blocker may be omitted.
  - After both native collections complete, invoke Task-36 `run_agent_review.py --review manual-surface-qa` with `config/verification/review-schemas/manual-surface-qa.json`, both just-created collection receipts, all four native receipts, the Task-36 final collection plus exact Windows/macOS artifact receipts, and the immutable evidence index. `engineering_verdict=APPROVE` requires complete exact-artifact provenance, every required happy/adverse surface observation, and zero process/data/volume/Keychain residue. The two platform status arrays follow the Task-36 exact schema: `["APPROVE"]` only with all affected external evidence, otherwise the sorted applicable exact Scope blocker strings. Missing/invalid reviewer output is `REJECT`; external blockers never change engineering approval.

  Must NOT do: Do not use real patient data/credentials, substitute source/dev-server behavior for the exact package, kill an unrelated listener/process, require a human action for engineering approval, or claim clean-Mac quarantine/Finder evidence from headless CI.

  Parallelization: Can parallel: YES | Final wave | Blocked by: [36] | Blocks: [final handoff]

  References: Task-36 final Windows/macOS artifact receipts, both manual-surface scripts, `run_agent_review.py`, and `config/verification/review-schemas/manual-surface-qa.json`; Task-22 `-ClientSurface`; Task-24 RC gate; `docs/cross-platform-desktop-validation.md`; Scope external gates.

  Acceptance criteria:
  - Dispatcher/native scripts exit 0; both F3 collection receipts reproduce the supplied Task-36 final-collection/Windows/macOS receipt hashes and bind exact `FINAL_SHA`, run/jobs/runners and artifact IDs/digests; all scenarios pass without external runtime/admin/terminal prerequisites; and final owned process/port/state/profile/mount/Keychain/search-list state is clean (persistent lock files are unheld).
  - The schema-bound isolated reviewer exits 0 and `$ATTEMPT_DIR/f3/reviewer.json` has top-level verdict and `engineering_verdict` exactly `APPROVE`, empty findings, hashes matching both collection receipts, all native receipts, Task-36 final collection/artifact receipts, final SHA, and evidence index, plus schema-valid Windows/macOS release-status arrays. Windows `["APPROVE"]` requires Authenticode plus the standard-user client-surface receipt; Mac `["APPROVE"]` requires Developer-ID/notary, macOS14 lower-bound, and clean quarantine/Finder receipts. Otherwise each array contains exactly every applicable fixed blocker and no inapplicable/unknown blocker; omission, overstatement, or PASS/blocker mixing fails review.

  QA scenarios:
  ```text
  Scenario: Nontechnical double-click lifecycle is observable on both target artifacts
    Tool:     bash dispatcher; native PowerShell `Start-Process` / macOS `open -n`; Playwright real Chromium
    Steps:    Run `set -euo pipefail; FINAL_SHA=$(git rev-parse HEAD); python scripts/verification/dispatch_manual_surface_qa.py --lane1-receipt "$ATTEMPT_DIR/lane1-barrier.json" --workflow-ref "$FINAL_SHA" --final-ref "$FINAL_SHA" --final-collection-receipt "$ATTEMPT_DIR/task-36/native/collection-receipt.json" --windows-artifact-receipt "$ATTEMPT_DIR/task-36/native/windows/artifact-receipt.json" --macos-artifact-receipt "$ATTEMPT_DIR/task-36/native/macos/artifact-receipt.json" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --scenarios all --output-dir "$ATTEMPT_DIR/f3/happy"`.
    Expected: Exit 0; exact Windows/macOS job/artifact provenance, launch/preflight/browser/second-launch/stop/backup/restore/diagnostics/upgrade/uninstall and synthetic clinical flows pass with no sensitive output or residue.
    Evidence: $ATTEMPT_DIR/f3/happy/collection-receipt.json, $ATTEMPT_DIR/f3/happy/windows/receipt.json, and $ATTEMPT_DIR/f3/happy/macos/receipt.json

  Scenario: User cancels, wrong backup, unrelated listener, and browser failure remain recoverable
    Tool:     bash dispatcher plus native surface runners and Playwright real Chromium
    Steps:    Run `set -euo pipefail; FINAL_SHA=$(git rev-parse HEAD); python scripts/verification/dispatch_manual_surface_qa.py --lane1-receipt "$ATTEMPT_DIR/lane1-barrier.json" --workflow-ref "$FINAL_SHA" --final-ref "$FINAL_SHA" --final-collection-receipt "$ATTEMPT_DIR/task-36/native/collection-receipt.json" --windows-artifact-receipt "$ATTEMPT_DIR/task-36/native/windows/artifact-receipt.json" --macos-artifact-receipt "$ATTEMPT_DIR/task-36/native/macos/artifact-receipt.json" --repository "$REPOSITORY" --repository-id "$REPOSITORY_ID" --remote "$GITHUB_REMOTE" --scenarios cancel,tampered-backup,wrong-platform-backup,unrelated-listener,browser-failure --output-dir "$ATTEMPT_DIR/f3/adversarial"; python scripts/verification/run_agent_review.py --review manual-surface-qa --base-ref 8c1edc460c2af354f74417cf27d26abaf72ccc70 --head-ref "$FINAL_SHA" --evidence-index "$ATTEMPT_DIR/task-36/evidence-index.json" --machine-receipt "$ATTEMPT_DIR/f3/happy/collection-receipt.json" --machine-receipt "$ATTEMPT_DIR/f3/happy/windows/receipt.json" --machine-receipt "$ATTEMPT_DIR/f3/happy/macos/receipt.json" --machine-receipt "$ATTEMPT_DIR/f3/adversarial/collection-receipt.json" --machine-receipt "$ATTEMPT_DIR/f3/adversarial/windows/receipt.json" --machine-receipt "$ATTEMPT_DIR/f3/adversarial/macos/receipt.json" --machine-receipt "$ATTEMPT_DIR/task-36/native/collection-receipt.json" --machine-receipt "$ATTEMPT_DIR/task-36/native/windows/artifact-receipt.json" --machine-receipt "$ATTEMPT_DIR/task-36/native/macos/artifact-receipt.json" --schema config/verification/review-schemas/manual-surface-qa.json --output "$ATTEMPT_DIR/f3/reviewer.json"`.
    Expected: Both commands exit 0 because every adverse flow fails safely; no outside-scope data/process changes, safe guidance/URL appears, a subsequent valid restart passes, temporary refs are gone, and reviewer top-level plus engineering verdicts are exactly APPROVE with empty findings and valid separate platform status arrays across both exact-artifact collections.
    Evidence: $ATTEMPT_DIR/f3/adversarial/collection-receipt.json, $ATTEMPT_DIR/f3/adversarial/windows/receipt.json, $ATTEMPT_DIR/f3/adversarial/macos/receipt.json, and $ATTEMPT_DIR/f3/reviewer.json
  ```

  Adversarial classes: `unrelated_port`, `tamper_wrong_key`, `rollback_failure`, `bundle_write`, `cleanup_escape`.

  Cleanup: Use installed clean-stop/uninstall surfaces first; revalidate any test-owned fallback PID/volume/path; retain only redacted evidence and exact artifacts.

  Commit: NO | Message: n/a | Files: []

- [ ] F4. Scope fidelity and minimal-portability/performance review

  What to do:
  - Repeat the exact Task26 certificate-bound/frozen-verifier procedure through `$ATTEMPT_DIR/task-36/barrier-post.json` using both independent anchors, offline bundle, and exact signer workflow. Then run Task-27 `verify_scope_fidelity.py` from the fixed base through HEAD using Task-36's immutable evidence index (never F1 output). It classifies every changed file/hunk against the pre-Task1 graph/outcome scope as required Lane-1 portability wiring, the exact Task27 instrumentation-only exception, an accepted Lane-2 optimization tied to its receipt, test/harness, packaging/CI, or documentation. Any unclassified path/hunk is blocking.
  - Prove business routes/models/rules/checklist/frontend behavior stayed identical except accepted measured Task32's exact migration-11 columns or Task35 frontend candidate; Windows outer distribution remained release-folder/ZIP; Mac stayed ARM64 DMG; no excluded platform/deployment/live integration/cross-OS restore/version bump appeared.
  - Confirm every accepted change cites fixed-cell threshold/equivalence evidence including primary-cell p95 ceilings and every rejected/not-material candidate left only its pre-anchored decision artifact. Invoke Task-36 `run_agent_review.py` with the scope-fidelity schema and pass the just-created scope receipt, both independent anchors, and Task36 post receipt; `APPROVE` requires a complete hunk map and zero unexplained/disallowed changes or retrospective policy edits.

  Must NOT do: Do not reclassify an excluded feature as portability, accept an unmeasured optimization, permit a version/live-gate/business-rule drift, or edit/revert files while auditing.

  Parallelization: Can parallel: YES | Final wave | Blocked by: [36] | Blocks: [final handoff]

  References: Task-27 scope verifier; Task-36 reviewer/schema/evidence index/post receipt; both Task26 independent anchors and attestation bundle; base commit; final diff; Task-1 immutable graph/scope/contract fingerprint; Tasks 32–35 decisions; Scope guardrails.

  Acceptance criteria:
  - Scope verifier exits 0 and the isolated schema-bound reviewer exits 0 with verdict exactly `APPROVE`, empty findings, a complete changed-hunk classification, and matching base/head/index/source-anchor/trigger-anchor/bundle/signer/Task36-post hashes.
  - Task 1 contract, 42-step checklist/rule hashes, live Alleva gates, LOC blocker, version metadata, and release models match allowed state.

  QA scenarios:
  ```text
  Scenario: Every final diff path maps to an authorized outcome
    Tool:     bash
    Steps:    Run `set -euo pipefail; python scripts/verification/verify_scope_fidelity.py --plan config/verification/approved-cross-platform-plan.md --approved-plan-sha256 "$APPROVED_PLAN_SHA256" --base-ref 8c1edc460c2af354f74417cf27d26abaf72ccc70 --head-ref HEAD --lane1-receipt "$ATTEMPT_DIR/lane1-barrier.json" --source-anchor "$ATTEMPT_DIR/task-26-source-anchor.json" --trigger-anchor "$ATTEMPT_DIR/task-26-trigger-anchor.json" --attestation-bundle "$ATTESTATION_BUNDLE" --signer-workflow "$REPOSITORY/.github/workflows/desktop-artifacts.yml" --task36-post-receipt "$ATTEMPT_DIR/task-36/barrier-post.json" --decision-dir docs/performance --evidence-index "$ATTEMPT_DIR/task-36/evidence-index.json" --output "$ATTEMPT_DIR/f4/scope-fidelity.json"; python scripts/verification/run_agent_review.py --review scope-fidelity --base-ref 8c1edc460c2af354f74417cf27d26abaf72ccc70 --head-ref HEAD --evidence-index "$ATTEMPT_DIR/task-36/evidence-index.json" --machine-receipt "$ATTEMPT_DIR/f4/scope-fidelity.json" --machine-receipt "$ATTEMPT_DIR/task-26-source-anchor.json" --machine-receipt "$ATTEMPT_DIR/task-26-trigger-anchor.json" --machine-receipt "$ATTEMPT_DIR/task-36/barrier-post.json" --schema config/verification/review-schemas/scope-fidelity.json --output "$ATTEMPT_DIR/f4/reviewer.json"`.
    Expected: Both exit 0; reviewer verdict is APPROVE with no findings, zero hunks are unclassified, and all contract/rule/version/gate hashes/statuses match.
    Evidence: $ATTEMPT_DIR/f4/scope-fidelity.json and $ATTEMPT_DIR/f4/reviewer.json

  Scenario: Simulated version bump/live-gate change/unmeasured optimization is rejected
    Tool:     pytest
    Steps:    Run `python -m pytest backend/tests/verification/test_final_review_tools.py -q -k "version_bump or live_gate or unmeasured_optimization or primary_p95 or unclassified_hunk or instrumentation_escape or retrospective_graph or wrong_signer or forged_post_receipt or reviewer_scope_waiver" --junitxml="$ATTEMPT_DIR/f4/scope-fidelity-adversarial.xml"`.
    Expected: Exit 0 because all forbidden fixtures are blocking; actual worktree/branch remains unchanged.
    Evidence: $ATTEMPT_DIR/f4/scope-fidelity-adversarial.xml
  ```

  Adversarial classes: `semantic_drift`, `stale_state`, `dirty_worktree`.

  Cleanup: Read-only except evidence metadata copies.

  Commit: NO | Message: n/a | Files: []

## Commit strategy
- Start only from clean `main` at `8c1edc460c2af354f74417cf27d26abaf72ccc70`. Record the base in Task 1 evidence. Never rewrite, reset, or overwrite unrelated user work.
- One logical task per conventional commit using the exact task Commit line. Implementation and its tests land together; every commit must build and pass its targeted tests independently.
- Lane 1 commits precede Task 26. Commit the barrier verifier before running the same-commit native gate. No `perf(...)` product commit may precede a valid Task 26 receipt.
- Lane 2 candidate implementation happens in a disposable worktree from the current accepted commit. Apply/cherry-pick a candidate only after its fixed threshold and equivalence gates pass; on rejection discard only that worktree and commit the task-specific decision document. Never use `git reset --hard` or revert user-owned edits.
- For an accepted candidate, use `git cherry-pick --no-commit CANDIDATE_SHA`, add its decision document, and create the task's one final commit. The decision receipt records the tested candidate commit/tree SHA; before committing, `verify_scope_fidelity.py` must prove the staged product-file tree/diff is byte-identical to that tested candidate (the decision document is the only allowed addition). Rejected candidates stage no candidate product path.
- Do not commit benchmark raw output, `.omo` evidence, runtime profiles, Keychains, `.env`, databases, uploads, logs, build intermediates, node_modules, venvs, or secrets. Commit deterministic harnesses and decision summaries only.
- Keep histories reviewable: no WIP/fixup/"make tests pass" commits on the final branch. If an atomic task needed local fixups, squash them into that task before its post receipt and before the successor starts, then rerun its gates. Never rewrite any task after a successor start receipt; never rewrite Task 1 after its policy/graph/scope anchor is published, and never rewrite Tasks 1-26 after the independent Task-26 source anchor/barrier exists.
- Do not bump release version metadata in this effort. If separately authorized later, update `VERSION`, `VERSION.json`, `frontend/package.json`, `/api/version`, UI, Windows/mac manifests, docs, and receipts together.
- The final implementation commit body footer is `Plan: .omo/plans/cross-platform-desktop-refactor.md`.

## Success criteria
- Tasks 1-36 and F1-F4 are complete with executable evidence and all four final reviewers return engineering APPROVE; no human action or acknowledgment is an engineering acceptance criterion.
- Lane1: the Windows x64 release-folder/ZIP builds/runs on the Windows native engineering runner and the ARM64 `.app`/DMG builds/runs on macOS15 with deployment target14.0; both scan cleanly, execute exact-artifact lifecycle QA, and require no admin/Docker/PostgreSQL/Git/Node/Python/CLI work for prepared use. Windows10/11 interactive and actual macOS14 lower-bound claims remain the named external gates until their receipts exist.
- The portable FastAPI/SQLite/rules/encryption/React core retains Task1's contract, except only the exactly declared migration-11 columns if Task32 is measured and accepted; mutable data/resources are separated; bootstrap precedes config/db imports; one app initializes once; startup/preflight/browser/single-instance behavior is correct.
- Same-root second launch reuses the owner; different roots require distinct configured ports; stale state recovers; unrelated processes/ports are never killed; authenticated stop drains all jobs within one 15-second budget or persists safe interrupted state and revalidates any fallback.
- Windows DPAPI and macOS Keychain V3 operator backup/restore, legacy Windows V2 read, diagnostics, upgrade, preserve-data uninstall, complete uninstall, rollback, privacy, and runtime-state exclusions pass. Cross-OS restore fails closed; migration `IZCNABK1:` remains intact.
- Task 26 same-commit native barrier passes before any Lane 2 work; receipt hashes/architectures/artifacts/cleanup verify and no external Apple status is falsely promoted.
- Lane 2 runs every fixed workload/sample count on both targets, evaluates candidates in order, accepts only threshold/equivalent changes, removes rejected product patches, and passes final combined performance certification. Zero accepted optimizations is a valid truthful outcome; an unmeasured or regressing optimization is not.
- Full backend/frontend/native/package/security/migration/integrity/foreign-key/WAL/artifact suites pass with synthetic data; release artifacts/evidence contain no PHI, credentials, runtime tokens/state, local profiles, or forbidden files.
- Engineering completion and RC release readiness are reported separately. Production macOS readiness additionally requires Developer ID/notarization/stapling and exact downloaded clean-Apple-Silicon Finder/Gatekeeper/Keychain QA; absence is reported with the exact external blocker, never hidden or called PASS.
