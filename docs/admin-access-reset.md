> Beta.4 update (2026-09-10): password setup, changes, and one-time recovery are now in the app. See [password management and beta.3 upgrades](password-management-beta4.md). Earlier version-specific instructions below remain historical.

# Admin Access Reset Guide

Date: 2026-09-08

Applies to: IZ Clinical Notes Analyzer Version `2.0.0-beta.3` / build `2026.09.03.1` on the `beta-local-desktop-v2` Windows desktop runtime.

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

Version 2.0 Beta role-scope reminder:

- Admins can manage admin, manager, and counselor accounts.
- Office managers can manage counselor accounts only.
- Counselors can manage only their own account.

## Client package: standalone recovery when locked out

For the original beta.3 Windows package, send the validated
`output/IZ-Admin-Recovery-beta.3.zip`. It contains the standalone executable
and a short client instruction sheet. See
[validation and compatibility](validation/admin-recovery-beta3-2026-09-08.md).

1. Extract the ZIP using Windows **Extract All**.
2. Double-click **Reset-IZ-Admin.exe** under the same Windows account used for IZ.
3. Type **RESET** and press Enter.
4. Keep the recovery window open and sign in to IZ using the displayed temporary password.
5. Complete the required password change, then close the recovery window.

The app may remain open. No Windows restart, elevation, or Python installation
is required. The tool checks the exact original packaged runtime, backs up
the existing database locally, updates the account and audit chain together,
and clears lockout. It refuses incompatible installations and disabled accounts.
If Windows blocks the unsigned executable, contact R3 without disabling protection.

## Developer checkout utility

The existing script below requires `backend/.venv/Scripts/python.exe`; it is
not a standalone client-package recovery method. It prompts the operator to
enter a temporary password securely.

```powershell
.\scripts\update-local-admin.ps1
```

## Do not reset an existing account by editing .env

The initial generated password is stored in:

```text
%LOCALAPPDATA%\IZ Clinical Notes Analyzer\.env
```

`BOOTSTRAP_ADMIN_PASSWORD` is used only when creating the account. Updating
it or setting `RESET_BOOTSTRAP_ADMIN_ON_STARTUP` does not reset an existing V2
account. The standalone recovery utility deliberately leaves .env unchanged.
Never replace a client's .env with another installation's file: it contains
installation-specific encryption settings.

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

Expected beta version: `2.0.0-beta.3` / build `2026.09.03.1` / channel `beta-local-desktop-v2`.
