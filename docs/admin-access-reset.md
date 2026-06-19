# Admin Access Reset Guide

Date: 2026-06-16

Applies to: IZ Clinical Notes Analyzer Version `1.4.3` / build `2026.06.19.1` local Windows desktop runtime.

## Purpose

This guide explains how an authorized R3 administrator can restore access to the local bootstrap admin account or reset another user account. Do not place credential values in Git, screenshots, email, support tickets, chat, or other unsecured channels.

## Preferred path inside the app

Use this path when at least one working admin account can sign in.

1. Open `http://localhost:8000`.
2. Sign in with an active admin account.
3. Open `User management`.
4. Select the user who needs access reset.
5. Use the user reset action.
6. Require the user to choose a new credential at next sign-in when the UI offers that option.
7. Communicate any one-time credential only through an R3-approved secure channel.
8. Confirm the action appears in `Forensic logs` without exposing the credential value.

Version 1.4.3 role scope reminder:

- Admins can manage admin, manager, and counselor accounts.
- Office managers can manage counselor accounts only.
- Counselors can manage only their own account.

## Local utility path when locked out

Use this path when no working admin account can sign in on a local Windows desktop install.

1. Close the app browser tab and app command window.
2. Open PowerShell from the repo root or installed app root.
3. Run:

```powershell
.\scripts\update-local-admin.ps1
```

4. Save the generated value shown in the PowerShell window.
5. Start the app again with:

```powershell
.\scripts\Start-IZ-Clinical-Notes-Analyzer.cmd
```

6. Sign in locally as `admin` using the generated value.
7. Immediately set the desired long-term admin access state according to R3 policy.
8. Confirm `Forensic logs` show the bootstrap admin reset event.

## Manual local settings path

If the utility is unavailable, an authorized administrator can edit the local settings file directly:

```text
%LOCALAPPDATA%\IZ Clinical Notes Analyzer\.env
```

Update the bootstrap admin credential value, confirm the reset-on-startup setting is enabled, save the file, restart the app, and sign in locally as `admin`.

Relevant settings:

```text
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=<secure-local-value>
RESET_BOOTSTRAP_ADMIN_ON_STARTUP=true
```

## Security notes

- The local settings file must not be committed to Git.
- Do not paste credentials, API keys, encryption keys, bearer tokens, or real PHI into GitHub, screenshots, email, chat, or support notes.
- Keep the local settings file and the local SQLite database together when backing up or moving an install.
- If R3 later deploys a signed installer or managed production configuration, follow the managed reset procedure for that deployment instead of editing local files manually.

## Validation after reset

After resetting access, confirm these endpoints respond locally:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/readiness
Invoke-RestMethod http://127.0.0.1:8000/api/version
```

Expected patch version: `1.4.3` / build `2026.06.19.1`.
