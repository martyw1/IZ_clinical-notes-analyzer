from pathlib import Path
import sqlite3
from contextlib import closing

import pytest
from passlib.hash import pbkdf2_sha256
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.v2.models import Base, User
from app.v2.services.audit_store import verify_audit_chain
import recovery_core


def fixture_database(root: Path) -> Path:
    path = root / 'existing.sqlite3'
    engine = create_engine(f'sqlite:///{path.as_posix()}')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(username='admin', password_hash=pbkdf2_sha256.hash('OldSynthetic123'), role='admin', is_active=True, is_locked=True, failed_login_attempts=5, auth_state='locked_until'))
        session.commit()
    engine.dispose()
    return path


def test_recovery_unlocks_existing_account_and_preserves_backup(tmp_path: Path) -> None:
    # Given: an existing locked administrator.
    path = fixture_database(tmp_path)
    # When: local recovery runs.
    result = recovery_core.reset_account(path, 'admin')
    # Then: the generated credential verifies and the audit chain remains valid.
    engine = create_engine(f'sqlite:///{path.as_posix()}')
    with Session(engine) as session:
        user = session.scalar(select(User).where(User.username == 'admin'))
        assert user is not None
        assert pbkdf2_sha256.verify(result.password, user.password_hash)
        assert not user.is_locked and user.failed_login_attempts == 0
        assert user.must_reset_password and user.recovery_required
        assert user.auth_state == 'password_change_required'
        assert verify_audit_chain(session)[0]
    engine.dispose()
    with closing(sqlite3.connect(result.backup)) as backup:
        assert backup.execute('SELECT failed_login_attempts FROM users').fetchone()[0] == 5


def test_missing_database_is_never_created(tmp_path: Path) -> None:
    # Given: the wrong Windows profile has no existing database.
    path = tmp_path / 'missing.sqlite3'
    # When / Then: recovery refuses without creating an empty replacement.
    with pytest.raises(recovery_core.RecoveryError):
        recovery_core.reset_account(path, 'admin')
    assert not path.exists()


def test_missing_admin_does_not_modify_database(tmp_path: Path) -> None:
    # Given: an existing database and a different requested account.
    path = fixture_database(tmp_path)
    original = path.read_bytes()
    # When / Then: no new account is inserted or existing account changed.
    with pytest.raises(recovery_core.RecoveryError):
        recovery_core.reset_account(path, 'absent')
    assert path.read_bytes() == original


def test_audit_failure_rolls_back_password_reset(tmp_path: Path) -> None:
    path = fixture_database(tmp_path)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TRIGGER reject_audit BEFORE INSERT ON audit_logs BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
        connection.commit()
        original = connection.execute('SELECT password_hash FROM users').fetchone()[0]
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        recovery_core.reset_account(path, 'admin')
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute('SELECT password_hash FROM users').fetchone()[0] == original
        assert connection.execute('SELECT failed_login_attempts FROM users').fetchone()[0] == 5


@pytest.mark.parametrize('role,active', [('admin', 0), ('staff', 1)])
def test_recovery_refuses_disabled_or_non_admin_account(tmp_path: Path, role: str, active: int) -> None:
    path = fixture_database(tmp_path)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute('UPDATE users SET role=?,is_active=?', (role, active))
        connection.commit()
    before = path.read_bytes()
    with pytest.raises(recovery_core.RecoveryError):
        recovery_core.reset_account(path, 'admin')
    assert before == path.read_bytes()


def test_wrong_package_refused_before_reading_settings(tmp_path: Path) -> None:
    runtime = tmp_path / 'Programs/IZ Clinical Notes Analyzer/runtime/IZClinicalNotesAnalyzer.exe'
    runtime.parent.mkdir(parents=True)
    runtime.write_bytes(b'synthetic-unsupported-runtime')
    with pytest.raises(recovery_core.RecoveryError):
        recovery_core.locate_installation(tmp_path)
    assert not (tmp_path / 'IZ Clinical Notes Analyzer').exists()


def test_busy_database_refused_without_reset(tmp_path: Path) -> None:
    from sqlalchemy.exc import OperationalError
    path = fixture_database(tmp_path)
    with closing(sqlite3.connect(path)) as writer:
        writer.execute('BEGIN IMMEDIATE')
        with pytest.raises(OperationalError):
            recovery_core.reset_account(path, 'admin')
        writer.rollback()
        assert writer.execute('SELECT failed_login_attempts FROM users').fetchone()[0] == 5
    assert not (tmp_path / 'admin-recovery-backups').exists()
