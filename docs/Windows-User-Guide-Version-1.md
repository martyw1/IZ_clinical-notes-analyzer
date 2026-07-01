# Windows User Guide Version 1

This guide is for R3 staff using a normal Windows 10 or Windows 11 laptop.

Current beta version: `1.4.6-beta.1` / build `2026.06.30.1`.

## What This App Is

IZ Clinical Notes Analyzer runs on your own Windows user account. It opens in your web browser at `http://localhost:8000`, but the app and data stay on the laptop.

Normal use from a prepared release folder does not require administrator access, Docker, PostgreSQL, Git, Node.js, or command-line work.

## Before You Start

You need:

- A Windows 10 or Windows 11 laptop.
- The prepared release folder or zip from R3 support.
- Your normal Windows user account.
- Internet access for first setup if Windows needs to download the per-user Python runtime or Python packages.

Do not install from OneDrive, Dropbox, iCloud Drive, Google Drive, or a network share. If you receive a zip, unzip it first to a normal folder such as Downloads or Desktop.

## Install

1. Open the release folder named `IZ-Clinical-Notes-Analyzer-v1.4.6-beta.1`.
2. Double-click `Install-IZ-Clinical-Notes-Analyzer.cmd`.
3. If Windows asks whether to run the file, choose the option that lets it run only if it came from R3 support.
4. Wait for the setup window to finish.
5. When setup is complete, launch the app from the Start Menu shortcut named `IZ Clinical Notes Analyzer`.

The app installs only for your Windows user account under:

```text
%LOCALAPPDATA%\Programs\IZ Clinical Notes Analyzer
```

The app stores local data under:

```text
%LOCALAPPDATA%\IZ Clinical Notes Analyzer
```

## First Launch

1. Open the Start Menu.
2. Select `IZ Clinical Notes Analyzer`.
3. Your browser should open to `http://localhost:8000`.
4. Sign in with the local admin access value provided by R3 support.

If R3 support asks you to find the first generated admin value:

1. Press `Windows` + `R`.
2. Paste `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.
3. Press Enter.
4. Open `.env` with Notepad.
5. Look for `BOOTSTRAP_ADMIN_USERNAME=admin` and `BOOTSTRAP_ADMIN_PASSWORD=...`.
6. Do not send the password in screenshots, chat, email, or tickets unless R3 has approved a secure channel.

## Daily Launch

Use the Start Menu or desktop shortcut named `IZ Clinical Notes Analyzer`.

If the app does not open automatically, open your browser and go to:

```text
http://localhost:8000
```

## Backup

Backups are important because the local settings file, database, and encrypted uploads must stay together.

1. Close the browser tab for the app.
2. Open the Start Menu.
3. Select `Backup IZ Clinical Notes Analyzer`.
4. Read the warning.
5. Type `BACKUP` when asked.
6. The backup zip is created in Documents under `IZ Clinical Notes Analyzer Backups`.

Keep the backup zip secure. It can contain clinical data, audit logs, app settings, saved API configuration, and local encryption material.

## Troubleshooting

Try these steps first:

| Problem | What to do |
| --- | --- |
| The app does not open | Open `http://localhost:8000` in your browser. |
| It says the app is already running or the port is in use | Open the Start Menu, select `Stop IZ Clinical Notes Analyzer` if available, then launch again. If that shortcut is not present, run `Stop-IZ-Clinical-Notes-Analyzer.cmd` from the installed app or release folder. |
| The setup window says preflight failed | Run `IZ Clinical Notes Analyzer Diagnostics`, then send the created zip to R3 support through an approved secure channel. |
| The browser shows an old version | Use the data-preserving uninstall, then install again from the newest release folder. |
| You cannot sign in | Ask an admin to reset your account in User management. If no admin can sign in, follow `docs\admin-access-reset.md` with R3 support. |
| A Windows security prompt appears | Only continue if the release came from R3 support. |

Diagnostics are created under:

```text
%LOCALAPPDATA%\IZ Clinical Notes Analyzer\diagnostics
```

Diagnostics exclude uploaded clinical documents, SQLite databases, generated reports, and raw `.env` values. Logs and configuration summaries are redacted before packaging, but R3 should still treat diagnostics as sensitive.

Useful local pages:

| Page | Address |
| --- | --- |
| App home | `http://localhost:8000` |
| Health check | `http://localhost:8000/api/health` |
| Readiness check | `http://localhost:8000/api/readiness` |
| Version check | `http://localhost:8000/api/version` |

## Uninstall But Keep Local Data

Use this when you are reinstalling or upgrading and want to keep users, settings, audit logs, uploads, and local records.

1. Open the Start Menu.
2. Select `Uninstall IZ Clinical Notes Analyzer`.
3. Wait for the uninstall window to finish.

This removes app files and shortcuts, but keeps:

```text
%LOCALAPPDATA%\IZ Clinical Notes Analyzer
```

## Complete Uninstall And Remove Local Data

Use this only when R3 intentionally wants the laptop cleared for this Windows user.

1. Create a backup first unless R3 says the data should be destroyed.
2. Open the Start Menu.
3. Select `Complete Uninstall IZ Clinical Notes Analyzer`.
4. Read the warning.
5. Type `REMOVE IZ DATA` when asked.

Complete uninstall removes:

- App files under `%LOCALAPPDATA%\Programs\IZ Clinical Notes Analyzer`.
- Start Menu and desktop shortcuts.
- Local app data under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.

After complete uninstall, the local database, encrypted uploads, settings, saved API configuration, audit logs, and local access material are removed for your Windows user account.

## What Not To Do

- Do not put real patient information in screenshots, support tickets, chat, or email.
- Do not move the local data folder into OneDrive or another cloud-synced folder.
- Do not delete only random files from `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`; use the app's delete, clear-data, backup, or uninstall flows.
- Do not treat Docker, PostgreSQL, Git, Node.js, or command-line setup as normal user steps.

## Main Screens

- Status Dashboard: summary, source selection, current queue, checklist version, EMR/API readiness, manual upload entry point, gated `Retrieve Active Treatment Plans`, and admin-only `Clear All Patient Data`.
- Treatment plans: admin/office-manager work queue, date-clock status, source evidence, LOC-change blocker, rule results, overrides, manager notes/actions, and CSV/JSON exports.
- Review queue: generated/manual uploaded-binder chart review workbench.
- Checklist: acronym definitions, review statuses, LOC-change blocker, and the 42 Version 1.2.0 PRD steps.
- Manual upload: upload files, inspect uploaded binders, download stored documents when authorized, and delete a local uploaded binder.
- Help: role permissions, screen guide, setup notes, API/EMR definitions, workflow guidance, and LLM setup notes.
- User management: admins can manage all roles; office managers can manage counselor accounts only; counselors manage only their own account.
- Workflow profiles: admin/manager workflow logic screen.
- App settings: admin-only organization, API/EMR setup, optional LLM setup, LOC-change settings, and `Clear All Patient Data`.
- Forensic logs: admin-only audit trail.

## Important Safety Notes

Live Alleva patient import remains disabled until R3/Alleva approve tenant credentials, endpoint mapping, auth requirements, pagination, rate limits, attachment behavior, vendor documentation, and compliance handling.

The detailed current handling reference for patient treatment plans is `docs\patient-treatment-plan-handling.md`. R3 support can use it to identify where manual uploads, approved Alleva sync, local storage, deterministic status, aggregate diagnostics, and the Treatment Plans screen are implemented.

Optional LLM behavior is disabled by default and is not required for compliance or timeliness decisions.

The level-of-care-change treatment-plan update window remains unvalidated by R3/Marleigh. The app keeps it configurable and visibly marked unresolved until R3 confirms the final rule.
