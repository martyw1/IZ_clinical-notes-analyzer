# Client handoff checklist

Current source: **1.0.2 / build 2026.10.16.1 / installer revision 1 / stable-local-desktop**. Product: **R3 Treatment Plan Audit Application**. Legacy IZ shortcut and storage names remain intentional.

## Release and installation

- Use the [package index](client-release-packages.md) and the validation receipt for the **exact ZIP being delivered**. October 12 source changes do not update the immutable September 21 ZIP.
- Supply a completely built, validated prepared Windows package with its checksum/receipt. Extract All before Install; do not launch from ZIP preview. Ordinary users should not install Python, Node, Git, Docker or PostgreSQL.
- Install for the intended Windows account, then Launch. Normal upgrade/reinstall preserves initialized passwords and local app data. Never use complete uninstall as an upgrade procedure.
- Verify footer and `/api/version` match the delivered identity. An old footer means an old running service or old assets; refresh, stop/start and check the exact installed release with support.
- Normal install root: `%LOCALAPPDATA%\Programs\IZ Clinical Notes Analyzer`. Data root: `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`. This laptop may currently use a source launcher; verify the shortcut target rather than assuming an installed package exists.

## Nontechnical acceptance with synthetic records

1. Start with the intended Windows account and numbered desktop shortcut.
2. Sign in with the assigned account. Replace the temporary password when prompted; save and acknowledge the one-time recovery code privately.
3. Confirm correct role. Office managers review authorized records; administrator-only Settings, API harness and Forensic Logs require an administrator. Do not grant admin solely to follow an obsolete screenshot.
4. Open Dashboard, Patient Roster, Patient Record Detail, an exact saved Treatment Plan Detail version and its 42-step checklist. Check source and MRN rather than matching a name alone.
5. Test an approved synthetic manual upload, inspect parsing warnings and verify the exact stored plan. Opaque storage is not clinical extraction success.
6. Confirm the current HTML guide, video and support shortcut open. Sign out, stop/start and sign in again.
7. Create and verify an encrypted backup and a supervised same-account restore in an isolated synthetic profile. Do not rehearse restore over client data.
8. Record the delivered ZIP hash, app version, Windows edition, browser, account role, acceptance date and any remaining limitations without patient content or secrets.

## Desktop tools

| Name | Purpose |
| --- | --- |
| (1) Start IZ Clinical Notes Analyzer | Launch local service and browser |
| (2) Stop IZ Clinical Notes Analyzer | Stop service; sign-out alone does not stop it |
| (3) Collect IZ Diagnostics | Create redacted support bundle when requested |
| (4) Quick Assist - R3 Support | Assisted support with a trusted R3 person |
| (5) Short Intro Video | October 3 administrator tutorial; role differences apply |
| (6) IZ Clinical Notes Analyzer User Guide | Current offline HTML guide |

Use [current operator help](operator-help-current.md) and [the offline guide](guides/current/Marleigh-Setup-Install-and-User-Guide.html). The guide and any referenced assets must remain together when copied. Repo-based shortcuts are machine-specific and do not install themselves on another laptop.

## Data and security acceptance

- Do not distribute the working repository, `.env`, databases, uploads, logs, raw API reports, credentials, caches, virtual environments, `node_modules`, `tmp/`, developer evidence or private exports. Use the package builder's required-file and forbidden-file gates.
- Keep runtime data outside OneDrive/source folders. OneDrive may sync approved backups only under R3's tenant, BAA, sharing, retention and access policies. Confirm those policies before storing regulated data there.
- Verify disk/device encryption and recovery-key escrow, Windows sign-in/automatic locking, patched supported Windows/browser, antivirus/firewall and restore capability. October 12 assessment could not conclusively verify disk encryption from the unelevated session.
- Current backup is an encrypted `.izcnabackup`, not an ordinary ZIP. Windows CurrentUser DPAPI binds recovery to the same account/computer; cross-device recovery needs a separately tested R3 plan.
- Confirm credential incident containment/rotation, retention/legal hold, clinical LOC policy and live Alleva approval gates in [open blockers](open-blockers.md). Do not treat passing source tests as closure of those decisions.

## Intended workload

The client workload is the app and its browser plus OneDrive; ChatGPT will not run. Preserve Windows protection/update services. Validate realistic patient/plan counts and largest approved upload on that workload before promising capacity. No active vulnerability scan, destructive cleanup, OS policy change or live vendor pull is part of this handoff checklist.

## Shipping insert and source desktop tools — October 12, 2026

Include `docs/guides/current/Getting-Started-Guide.pdf` in the shipping box; it is the existing one-page approved-layout local insert, now retained in source. Credentials are provided separately. The current HTML guide describes tools (1)–(9), including authorized admin recovery and portable OneDrive ZIP backup/restore. Source shortcut recreation is available in `scripts/create-source-desktop-shortcuts.ps1`; task registration remains a separate support action. The clinical staff wallpaper is in `docs/desktop/`.
