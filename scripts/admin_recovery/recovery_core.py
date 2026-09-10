from __future__ import annotations

import hashlib
import secrets
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final
from uuid import uuid4

from passlib.hash import pbkdf2_sha256
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.v2.models import User
from app.v2.services.audit_store import record_audit_event

RUNTIME_SHA256: Final = '470d4910d7db1401714a48258692370c686418aefc96a56aed06ace17cb5bb01'
APP_NAME: Final = 'IZ Clinical Notes Analyzer'


@dataclass(frozen=True, slots=True)
class RecoveryError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class Installation:
    database: Path
    username: str


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    password: str
    backup: Path


def locate_installation(local_app_data: Path) -> Installation:
    install = local_app_data / 'Programs' / APP_NAME
    runtime = install / 'runtime' / 'IZClinicalNotesAnalyzer.exe'
    if not runtime.is_file():
        raise RecoveryError('The installed app was not found for this Windows account. Sign in to the Windows account used to install IZ, then run this tool again.')
    with runtime.open('rb') as stream:
        fingerprint = hashlib.file_digest(stream, 'sha256').hexdigest()
    if fingerprint != RUNTIME_SHA256:
        raise RecoveryError('This tool supports the original 2.0.0-beta.3 package only. Contact R3 for a matching recovery tool.')
    root = (local_app_data / APP_NAME).resolve()
    env_file = root / '.env'
    if not env_file.is_file():
        raise RecoveryError('Local app settings were not found. Contact R3; do not create or replace the .env file.')
    values: dict[str, str] = {}
    for raw in env_file.read_text(encoding='utf-8-sig').splitlines():
        line = raw.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            values.setdefault(key.strip(), value.strip().strip('\"\''))
    if values.get('IZ_CNA_LOCAL_APP_DATA_DIR', '').strip():
        if Path(values['IZ_CNA_LOCAL_APP_DATA_DIR']).expanduser().resolve() != root:
            raise RecoveryError('A custom data location is configured. Contact R3 before recovery.')
    configured = values.get('IZ_CNA_LOCAL_SQLITE_DB_PATH', values.get('LOCAL_SQLITE_DB_PATH', 'clinical-notes-analyzer-v2.sqlite3'))
    candidate = Path(configured).expanduser()
    database = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if not database.is_relative_to(root):
        raise RecoveryError('The database is outside this Windows account\'s IZ data folder. Contact R3 before recovery.')
    if not database.is_file():
        raise RecoveryError('The existing login database was not found. Open IZ once, wait for its login screen, and run this tool again under the same Windows account.')
    username = values.get('IZ_CNA_BOOTSTRAP_ADMIN_USERNAME', values.get('BOOTSTRAP_ADMIN_USERNAME', 'admin')).strip() or 'admin'
    return Installation(database=database, username=username)


def reset_account(database: Path, username: str) -> RecoveryResult:
    if not database.is_file():
        raise RecoveryError('The existing database was not found. Nothing was reset.')
    password = 'IZ-' + secrets.token_hex(9) + '-9a'
    credential_hash = pbkdf2_sha256.using(rounds=600_000).hash(password)
    engine = create_engine('sqlite://', creator=lambda: sqlite3.connect(database.as_uri() + '?mode=rw', uri=True, timeout=10))
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql('BEGIN IMMEDIATE')
            with Session(bind=connection) as session:
                admin = session.scalar(select(User).where(User.username == username))
                if admin is None or admin.role != 'admin':
                    raise RecoveryError('The configured administrator account was not found. Nothing was reset. Contact R3.')
                if not admin.is_active:
                    raise RecoveryError('This administrator account is disabled. Contact R3 to review access; nothing was reset.')
                backup_dir = database.parent / 'admin-recovery-backups'
                backup_dir.mkdir(exist_ok=True)
                backup = backup_dir / f'{uuid4().hex[:16]}.sqlite3'
                with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=10)) as source:
                    with closing(sqlite3.connect(backup)) as target:
                        source.backup(target)
                        if target.execute('PRAGMA quick_check').fetchone() != ('ok',):
                            raise RecoveryError('The database backup did not pass its integrity check. Nothing was reset. Contact R3.')
                admin.password_hash = credential_hash
                admin.password_changed_at = datetime.now(timezone.utc)
                admin.must_reset_password = True
                admin.auth_state = 'password_change_required'
                admin.failed_login_attempts = 0
                admin.is_locked = False
                admin.locked_until = None
                admin.recovery_required = True
                record_audit_event(session, action='auth.local_admin.recovered', actor=admin, target_entity_type='user', target_entity_id=str(admin.id), details={'resulting_state': 'password_change_required'}, commit=False)
                session.flush()
                connection.commit()
        return RecoveryResult(password=password, backup=backup)
    finally:
        engine.dispose()
