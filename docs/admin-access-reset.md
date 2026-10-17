# Administrator access recovery

Current source: **1.0.2 / build 2026.10.16.1 / stable-local-desktop**. First use, password changes and one-time recovery are in the app; see [password management](password-management-beta4.md). Use Forgot password with the saved code first. Historical beta.3 standalone recovery below is compatible only with its original validated package, not a universal current reset tool.

## Purpose

This guide explains how an authorized R3 administrator can restore access to the local bootstrap admin account or reset another user account. Do not place credential values in Git, screenshots, email, support tickets, chat, or other unsecured channels.

## Preferred path inside the app

Use this path when at least one working admin account can sign in.

1. Open `http://localhost:8000`.
2. Sign in with an active admin account.
3. Open `Users`.
4. Select the user who needs access reset.
5. Use the user reset action.
6. Require the user to choose a new credential at next sign-in when the UI offers that option.
7. Communicate any one-time credential only through an R3-approved secure channel.
8. Confirm the action appears in `Forensic logs` without exposing the credential value.

Current role-scope reminder:

- Admins can manage admin, manager, and counselor accounts.
- Office managers can manage counselor accounts only.
- Counselors can manage only their own account.

## Historical beta.3 package: standalone recovery when locked out

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

## Authorized current source-checkout recovery

If no administrator or recovery code is available, R3 support must verify ownership and deployment compatibility before recovery. Do not use the historical executable on the current version. The existing source script below requires `backend/.venv/Scripts/python.exe`; it is
not a standalone client-package recovery method. It prompts the operator to
enter a temporary password securely.

```powershell
.\scripts\update-local-admin.ps1
```

## Do not reset an existing account by editing .env

Local initialization configuration may be stored in:

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

Expected current source identity: `1.0.1` / build `2026.10.12.1` / channel `stable-local-desktop`; compare against the exact installed release receipt. Historical beta recovery procedures keep their original compatibility limits.
