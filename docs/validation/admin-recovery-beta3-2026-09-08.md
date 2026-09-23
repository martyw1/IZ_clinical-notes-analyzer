# Standalone admin recovery validation

> Script consolidation (2026-09-23): paths below record historical execution. For current startup, diagnostic and test commands, see [the script guide](../../scripts/README.md).

App: 2.0.0-beta.3 / build 2026.09.03.1 / beta-local-desktop-v2.
Recovery utility: 2026-09-08, original Windows x64 package only.

## Deliverable

`output/IZ-Admin-Recovery-beta.3.zip` contains exactly `Reset-IZ-Admin.exe`
and `READ-ME-FIRST.txt`. The client extracts the ZIP, double-clicks the EXE,
types RESET, and uses the locally generated temporary password. The app can
remain running. No Windows restart, elevation, Python installation, pip,
Node.js, network access, or changes to .env are required by the utility.

The EXE is unsigned. Client Windows reputation, antivirus, or organization
policies may block an unsigned executable; these cannot be certified remotely.
Instructions say to contact R3, not disable Windows protection.

## Compatibility and preservation

- Checks installed runtime SHA256 before accessing settings. Supported original
  runtime: `470d4910d7db1401714a48258692370c686418aefc96a56aed06ace17cb5bb01`.
- Resolves the current Windows user's Local AppData; reads only existing
  configuration and refuses an absent database, an external data path, a
  disabled admin, or an account that is not an administrator.
- Does not import application startup, initialize a database, run migrations,
  replace configuration, install dependencies, or stop other processes.
- Opens SQLite in existing-file mode and acquires BEGIN IMMEDIATE with a
  bounded 10-second writer-lock timeout. Other writes wait or cause a safe
  refusal; reads may continue. Online SQLite backup runs before mutation.
- Backup remains in `admin-recovery-backups` beside the existing database.
  It contains sensitive database material and must not be sent to support.
  It is a local SQLite snapshot, not a portable encrypted app backup.
- Updates the selected admin's password hash, password-change timestamp,
  required-change/recovery state, failed-attempt count, and lockout fields.
  Writes the existing audit-chain format in the same transaction.
- Uses PBKDF2-SHA256 with 600,000 rounds, accepted by the original packaged
  authentication implementation. Actual login verification confirms this.
- Generates a different temporary password each time; prints it only to the
  client's console. Does not log it or write it into the ZIP or .env.

## Observed verification

Ten tests cover core behavior and an end-to-end scenario using the original
packaged app EXE plus the standalone recovery EXE in a synthetic profile:

- Invalid credentials (HTTP 401) before recovery, then account lockout (423).
- Cancellation without account changes or creation of a recovery backup.
- Recovery while the original app remains running.
- Successful temporary-password login, enforced password change, successful
  chosen-password login, rejection of the obsolete password and old session.
- A second recovery after the user has changed their password.
- Original settings bytes preserved; synthetic existing database records
  preserved; SQLite integrity and the audit hash chain remain valid.
- Backup contains the original pre-reset account state.
- Missing database never created; missing admin causes no mutation.
- Disabled/non-admin account and incompatible runtime refused.
- Audit insert failure rolls back the password update.
- Busy database refuses without resetting or creating a backup.
- Developer tools removed from the subprocess PATH during the full scenario.

The test host was Windows build 26200 (Windows 11), running without elevated
administrator membership. The EXE manifest specifies `asInvoker`,
`uiAccess=false`, x64. No client laptop was accessed.

An initial test exposed SQLite's sidecar path-length limit during backup.
Shortening the unique backup filename fixed the reproduced failure. The full
long-profile-path test then passed. Native console confirmation, success, and
safe-stop screens were captured from the finished executable. Screenshot
capture harness errors were separate from recovery behavior; only complete
fresh captures are retained for visual review.

During an early read-only compatibility inspection, a helper accidentally
launched the normal local app while probing its unsupported --help flag.
That startup touched the developer profile's default V2 database/startup
artifacts. Both launched processes were identified and stopped. It did not
reset that profile's credentials or access the client. All recovery tests and
screenshots used explicitly isolated synthetic profiles.

Evidence: `.omo/evidence/admin-recovery-2026-09-08/`.
Source and rebuild instructions: `scripts/admin_recovery/`.

## Release checksums

- Recovery EXE SHA256:
  `6fb6292a5ca0337f7f3a7b75ff4b6112c63c3abc1698623f12b2a1d392752c4a`
- ZIP SHA256:
  `2d53a941c8d9b6ec4d3b2d49613ef07c9a0a33275889bf0503a66395b1632600`
- ZIP size: 19,468,240 bytes.
- ZIP integrity, exact two-file allowlist, and packaged/tested EXE byte
  identity verified. No settings, databases, passwords, uploads, logs,
  development environments, or client information are included.
