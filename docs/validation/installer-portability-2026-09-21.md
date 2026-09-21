# Installer Portability Validation - 2026-09-21

## Package identity and status

**Production 1.0 core acceptance passed.** Version `1.0.0`, build `2026.09.21.2`, installer revision `1`, channel `stable-local-desktop`, schema `12`.

Client file: `dist/windows-release/IZ-Clinical-Notes-Analyzer-v1.0.0-build-2026.09.21.2-installer-r1.zip` in the original project workspace. Size: 39,220,133 bytes.

SHA-256: `91d08cd08d01dfff121a3823fd6a62cb93b91ef33e7d1ab7f3adc8cf78be17ec`.

Clean build source: `f5d32d30a2aa88d48776694545dd7ba48351c3af`. The same basename `.build-receipt.json`, `.build-gates.json` and `.sha256` accompany the ZIP; `Production-1.0-START-HERE.txt` gives the client sequence. The receipt stays bound to this source even when final validation documentation is committed later. Historical packages remain unchanged.

## Client contract

Extract the entire ZIP, run `Install-IZ-Clinical-Notes-Analyzer.cmd`, then `Launch-IZ-Clinical-Notes-Analyzer.cmd`. Package-root Launch delegates to the installed current-user launcher; it does not create a new account or installation by itself.

The prepared runtime includes its frontend and backend; normal use requires no administrator elevation, Python, Node.js, Git, Docker or PostgreSQL. Source staging accepts relocated normal folders and OneDrive-backed package locations and validates all manifest members. Installed application and data paths retain strict current-user ownership and containment checks. A blocked, incomplete or internally linked package fails closed rather than bypassing verification.

A truly fresh install uses the device-independent R3 starter account and requires immediate personal password change and recovery-code setup. Each fresh instance creates its own password hash. The ZIP contains bootstrap defaults, not the development computer's saved accounts, database or credentials. Upgrade and data-preserving reinstall keep existing accounts, passwords, settings, encrypted uploads and supported local data. A previously changed password therefore remains necessary after upgrade. The specifically authorized reset of this development laptop is a separate verified action.

Fresh API configurations default to 30 seconds. An upgrade preserves an explicitly saved timeout; the client should verify the request timeout is 30 seconds if the older connection used 10 seconds. Fresh Alleva sync remains disabled until authorized tenant configuration is supplied.

## Observed build and lifecycle evidence

Host: Windows 11 Home, build 10.0.26200, standard-user execution, 8 GB RAM. Fresh and P02 package tests used isolated synthetic component profiles. They ran the actual packaged EXE and HTTP/browser surfaces without touching the real clinical profile. They do not represent separate Windows sign-ins or an actual-default-profile CMD double-click test.

| Check | Result and evidence |
| --- | --- |
| Normal clean-source build, no skipped gates | 617 backend and 182 frontend tests passed; frontend build and frozen runtime passed. All seven build/safety gates passed. `production-1-0/full-build-4-result.json` and detached build receipt. |
| Final ZIP integrity and bootstrap | 340 entries passed CRC; frozen bootstrap defaults verified; no local `.env`; exact SHA and size verified after client-folder copy. `production-1-0/final-zip-password-verification.json` and `client-copy-verification.json`. |
| Two independent fresh profiles | Starter login, workspace 403 before change, forced change, recovery setup/save, starter rejection after change, new password after managed restart all passed. `production-1-0-fresh-profile-qa/runs/cmd-62e30b5c1f6e/fresh-profile-qa-receipt.json`. |
| Packaged upgrade and removal lifecycle | P02 nine steps passed: beta.3 upgrade, actual EXE/HTTP/Edge, API roundtrip, data-preserving uninstall/reinstall, password rotation, typed complete purge and cleanup. `windows-cmd-maintenance/cmd-c4dcc5bdf8fe/maintenance-run-receipt.json`. |
| Normal/OneDrive source handling and relocation | 13 source-controller assertions passed against the final payload; original cloud-source rejection reproduced and corrected; staged hashes/file set verified. `production-1-0/final-package-portability.json`. This is source staging evidence, not a full OneDrive default-profile double-click run. |
| Long installation paths | 268-character staged file copied/verified; injected junction rejected as `PATH_REPARSE_POINT`, outside sentinel preserved. `windows-cmd-maintenance/install/component/transaction-cae617f3cb6b/task-09-upgrade.json`. |
| Destination, transitions and failure safety | 50 strict-path assertions, 23 production-version bridge assertions, and six installer regression cases passed; internal links/tamper/missing/extra package members fail closed. |
| Browser and forensic visibility | Both profiles displayed Production 1.0 / build .2, timeout 30, account/help and redacted verified forensic chain; zero browser page errors. All 18 masked screenshots inspected; two independent reviews recorded in `production-1-0/final-ui-review.json`. |
| Clinical profile preservation | Authorized local reset passed after authenticated encrypted DB/environment snapshot; 45 clinical-table counts preserved. Live final sync passed with 401 vendor clients / 591 vendor plans, zero errors/warnings or duplicate writes. |

Evidence paths in the table are relative to the build worktree's ignored `.omo/evidence/`. Complete provenance and retry details are in [production validation](production-1-0-2026-09-21.md). Full frontend verification used two Vitest workers; no assertions were relaxed.

## Privacy and cleanup

Release folder and ZIP safety scans passed. Saved tenant material, local databases, uploads, logs and encryption keys are excluded. Diagnostic additions record safe categories, timings and counts without clinical narrative or credentials. Screenshot masks intentionally hide temporary passwords and recovery codes. Focused authentication/recovery tests verify session and recovery-code invalidation; packaged tests verify the account lifecycle.

Owned synthetic profiles were purged and owned test processes/listeners stopped. Three local temporary full-profile backup staging directories remain because automatic approval review rejected deletion as blocked by policy; they are not in the package. The actual-account reset backup was independently verified as an encrypted database/environment snapshot; full-profile backup is not claimed.

## Qualification limits

- The client laptop was not connected; deployment there has not been observed.
- Windows 10, actual-default-profile install/shortcut double-click, separate Windows sign-ins, the broader Home/browser matrix and VM power-loss boundaries were not qualified for this archive. Component-profile evidence must not be represented as those tests.
- A 1.0 version label does not establish code signing, credential rotation or R3 retention/legal-hold approval. These organizational decisions remain open.
- LOC-change timing stays configurable and visibly unvalidated. Deterministic missing/conflicting evidence outcomes remain unchanged. Authorized live tenant configuration is still required; startup sync is disabled.

## Final determination

The exact archive is the completed handoff artifact for the tested core scope. It contains portable starter-account initialization and updated password management, and passes the available local package/lifecycle checks. Full platform and client-site qualification remain limited as stated above; no promise that every Windows environment was tested is made.
