# Admin Access Reset Guide

Date: 2026-06-09

Applies to: IZ Clinical Notes Analyzer Version 1.0.1 local Windows desktop runtime.

## Purpose

This guide explains how an authorized R3 administrator can restore access to the local bootstrap admin account or reset another user account. Do not place credential values in Git, screenshots, email, support tickets, or chat.

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

## Bootstrap admin path when locked out

Use this only for a local Windows desktop install when no working admin account can sign in.

1. Close the app browser tab and app command window.
2. Open the local settings file in Notepad: `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\.env`.
3. Update the bootstrap admin credential value in that local settings file.
4. Confirm the bootstrap admin reset-on-startup setting is enabled in the same local settings file.
5. Save the file.
6. Start the app again with `scripts\Start-IZ-Clinical-Notes-Analyzer.cmd`.
7. Sign in as `admin` using the updated local value.
8. Immediately set the desired long-term admin access state according to R3 policy.
9. Confirm `Forensic logs` show the bootstrap admin reset event.

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

Expected patch version: `1.0.1`.
