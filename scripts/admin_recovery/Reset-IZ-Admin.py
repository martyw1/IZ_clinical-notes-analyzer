from __future__ import annotations

import os
import sqlite3
import textwrap
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from recovery_core import RecoveryError, locate_installation, reset_account


def main() -> int:
    print('IZ ADMIN PASSWORD RECOVERY | 2.0.0-beta.3\n')
    print('Use the same Windows account you use to run IZ.')
    print('Administrator rights and software installation are not required.\n')
    try:
        local_app_data = os.environ.get('LOCALAPPDATA', '')
        if not local_app_data:
            raise RecoveryError('Windows Local AppData could not be located. Contact R3.')
        if any(name.startswith('IZ_CNA_') for name in os.environ):
            raise RecoveryError('Custom IZ launch settings are active. Close this window and double-click this recovery tool directly from File Explorer.')
        installation = locate_installation(Path(local_app_data))
        print('Verified: the original beta.3 app and its existing login database.')
        print(f'App username: {installation.username}')
        print('\nThis will replace this app account\'s password and clear its lockout.')
        print('A database backup stays on this laptop. App settings are preserved.')
        print('Your Windows password will not change.\n')
        if input('Type RESET and press Enter to continue (anything else cancels): ').strip() != 'RESET':
            print('\nCancelled. No account changes were made.')
            return 0
        print('\nCreating backup and resetting access. Please wait...')
        result = reset_account(installation.database, installation.username)
        print('\nSUCCESS: The admin password has been reset and the account unlocked.')
        print(f'Username: {installation.username}')
        print(f'Temporary password: {result.password}')
        print('\nKeep this window open while signing in to IZ.')
        print('Type the temporary password exactly, including the hyphens.')
        print('IZ will ask you to choose your own new password after sign-in.')
        print('Use at least 12 characters, including a letter and a number.')
        print('Do not send anyone a screenshot of this password or the backup.')
        input('\nAfter signing in, press Enter to close this window: ')
        return 0
    except RecoveryError as exc:
        print('\nRECOVERY STOPPED:')
        print(textwrap.fill(str(exc), width=72))
    except (OSError, sqlite3.Error, SQLAlchemyError):
        print('\nRECOVERY STOPPED: The database or backup could not be accessed safely.')
        print('If IZ is busy, wait for it to finish and retry. Otherwise contact R3.')
        print('No successful reset was confirmed. Do not delete or replace app files.')
    except (EOFError, KeyboardInterrupt):
        print('\nWindow input ended. If a success message appeared, recovery already completed; run again if you did not save the temporary password.')
        return 1
    input('\nPress Enter to close: ')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
