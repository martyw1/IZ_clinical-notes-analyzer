# Password management and recovery

Applies to current source 1.0.2 / build 2026.10.16.1 / stable-local-desktop, retaining the recovery workflow introduced in beta.4. Verify the actual delivered package/version.

## First use

1. Launch the app and sign in as admin using the starter password supplied by R3.
2. Set your own password and confirm it. Use at least 12 characters with a letter and a number; a longer unique passphrase is recommended. The starter password cannot be your permanent password.
3. Set up account recovery in the app using your new password. Save the generated recovery code in your approved password manager or another secure place, then acknowledge that you saved it.

The starter password works only while the administrator account is being initialized. It is never a fallback after a password change. Passwords and recovery codes must not be sent in ordinary email/chat or included in screenshots.

## Change a password

Select Account in the app header. Enter your current password, new password, and confirmation. Changing a password invalidates older sessions. Each user can change their own password.

## Forgot a password

Select Forgot password on the sign-in screen. Enter your username, saved recovery code, and a new password with confirmation. A successful recovery uses up that code and signs out old sessions. Sign in with the new password and save a replacement recovery code. No separate reset tool, command prompt, email service, or internet connection is needed.

Account recovery does not reactivate a disabled account. Invalid recovery attempts are limited. Keep the code as carefully as the password: anyone with the code can recover that account.

## Help another user

An administrator can use Users to assign a temporary password to a staff account. Give it to the user through an approved secure channel. The user changes it on their next sign-in. Staff can also use their own saved recovery code.

## Upgrade and historical beta.3 boundary

Use the approved current installer from its verified release folder. The installer preserves the existing local data and creates its existing pre-upgrade encrypted backup. Chosen passwords remain valid; the upgrade does not reset existing accounts to the starter password. On first sign-in after upgrading, users without a recovery code set one up in the app.

Previously distributed beta.3 executables cannot gain this feature without installing beta.4. Historical beta.3 archives remain unchanged. If an existing beta.3 account is already inaccessible and no other administrator can assist, contact R3 for authorized recovery before completing account recovery setup in beta.4. The new starter password does not unlock an already initialized account.

If both your password and recovery code are lost, contact your administrator or R3. There is deliberately no universal password that bypasses account ownership.

## Unchanged clinical boundary

This update changes password management only. Deterministic clinical workflows remain in place. The LOC-change seven-day candidate remains unvalidated and Settings clinical intervals are read-only pending a reviewed R3/Marleigh rule update; live Alleva sync remains gated.
