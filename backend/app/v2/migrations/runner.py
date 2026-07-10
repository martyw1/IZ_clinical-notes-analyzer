from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import tempfile
import uuid
from contextlib import closing
from pathlib import Path

from app.v2.migrations.backup import (
    BackupEnvelopeError,
    BackupRequest,
    create_backup,
    read_backup,
    validate_sqlite_file,
)
from app.v2.migrations.backfill import backfill_legacy_tables
from app.v2.migrations.errors import MigrationInterruptionError, MigrationPathError, MigrationStateError
from app.v2.migrations.lifecycle_types import (
    ApplyRequest,
    MigrationFailpoint,
    MigrationReport,
    MigrationRequest,
    RestoreReport,
    RestoreRequest,
)
from app.v2.migrations.registry import LATEST_SCHEMA_VERSION, MIGRATIONS
from app.v2.migrations.reporting import table_counts, table_counts_database
from app.v2.migrations.schema_core import USER_EXTENSIONS
from app.v2.migrations.schema_verifier import (
    reconciliation_counts,
    reconciliation_counts_database,
    record_reconciliation,
    verify_connection,
    verify_database,
)

def run_migrations(request: MigrationRequest) -> MigrationReport:
    database_path, root = _validated_paths(request.database_path, request.local_app_data_dir)
    if request.dry_run:
        return _run_dry_migration(request, database_path, root)
    _cleanup_temporary_databases(database_path)
    _checkpoint(database_path)
    original_sha256 = _file_sha256(database_path)
    source_schema = _current_schema(database_path)
    pending = tuple(migration for migration in MIGRATIONS if migration.version > source_schema)
    if not pending:
        verify_database(database_path, source_schema)
        return MigrationReport(
            source_schema=source_schema,
            target_schema=source_schema,
            dry_run=False,
            original_sha256=original_sha256,
            migrated_sha256=original_sha256,
            applied_versions=(),
            counts=table_counts_database(database_path),
            reconciliation=reconciliation_counts_database(database_path),
            backup_path=None,
        )
    backup_path: Path | None = None
    temporary_path = database_path.with_name(f"{database_path.name}.migration-{uuid.uuid4().hex}.tmp")
    try:
        backup = create_backup(
            BackupRequest(database_path, root, request.encryption_secret, source_schema, LATEST_SCHEMA_VERSION, request.app_build)
        )
        backup_path = backup.path
        _interrupt(request.failpoint, MigrationFailpoint.AFTER_BACKUP)
        shutil.copy2(database_path, temporary_path)
        _interrupt(request.failpoint, MigrationFailpoint.AFTER_COPY)
        with closing(sqlite3.connect(temporary_path)) as connection:
            _apply_pending(connection, ApplyRequest(root, request.encryption_secret, request.app_build, pending))
            verify_connection(connection, LATEST_SCHEMA_VERSION)
        _interrupt(request.failpoint, MigrationFailpoint.AFTER_SCHEMA)
        migrated_sha256 = _file_sha256(temporary_path)
        counts = table_counts_database(temporary_path)
        with closing(sqlite3.connect(temporary_path)) as connection:
            reconciliation = reconciliation_counts(connection)
        _interrupt(request.failpoint, MigrationFailpoint.BEFORE_REPLACE)
        os.replace(temporary_path, database_path)
        return MigrationReport(
            source_schema=source_schema,
            target_schema=LATEST_SCHEMA_VERSION,
            dry_run=False,
            original_sha256=original_sha256,
            migrated_sha256=migrated_sha256,
            applied_versions=tuple(item.version for item in pending),
            counts=counts,
            reconciliation=reconciliation,
            backup_path=backup_path,
        )
    finally:
        temporary_path.unlink(missing_ok=True)


def restore_database(request: RestoreRequest) -> RestoreReport:
    database_path, root = _validated_paths(request.database_path, request.local_app_data_dir)
    backup_path = request.backup_path.resolve()
    backup_root = (root / "backups").resolve()
    if not backup_path.is_relative_to(backup_root):
        raise BackupEnvelopeError("backup path is outside local application data")
    payload = read_backup(backup_path, request.encryption_secret)
    temporary_path = database_path.with_name(f"{database_path.name}.migration-restore-{uuid.uuid4().hex}.tmp")
    try:
        temporary_path.write_bytes(payload.database_bytes)
        validate_sqlite_file(temporary_path)
        try:
            verify_database(temporary_path, payload.source_schema)
        except MigrationStateError as exc:
            raise BackupEnvelopeError("backup schema verification failed") from exc
        os.replace(temporary_path, database_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return RestoreReport(
        database_sha256=payload.database_sha256,
        source_schema=payload.source_schema,
        target_schema=payload.target_schema,
    )


def _run_dry_migration(request: MigrationRequest, database_path: Path, root: Path) -> MigrationReport:
    with tempfile.TemporaryDirectory(prefix="izcna-dry-run-") as temporary_root:
        rehearsal_path = Path(temporary_root) / database_path.name
        shutil.copyfile(database_path, rehearsal_path)
        wal_path = database_path.with_name(database_path.name + "-wal")
        if wal_path.exists():
            shutil.copyfile(wal_path, rehearsal_path.with_name(rehearsal_path.name + "-wal"))
        with closing(sqlite3.connect(rehearsal_path)) as source, closing(sqlite3.connect(":memory:")) as target:
            source.backup(target)
            source_schema = _current_schema_connection(target)
            verify_connection(target, source_schema)
            pending = tuple(migration for migration in MIGRATIONS if migration.version > source_schema)
            if pending:
                _apply_pending(target, ApplyRequest(root, request.encryption_secret, request.app_build, pending))
            target_schema = LATEST_SCHEMA_VERSION if pending else source_schema
            verify_connection(target, target_schema)
            migrated_sha256 = hashlib.sha256(target.serialize()).hexdigest()
            counts = table_counts(target)
            reconciliation = reconciliation_counts(target)
    original_sha256 = _file_sha256(database_path)
    return MigrationReport(
        source_schema=source_schema,
        target_schema=target_schema,
        dry_run=True,
        original_sha256=original_sha256,
        migrated_sha256=migrated_sha256,
        applied_versions=tuple(item.version for item in pending),
        counts=counts,
        reconciliation=reconciliation,
        backup_path=None,
    )


def _apply_pending(connection: sqlite3.Connection, request: ApplyRequest) -> None:
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA secure_delete=ON")
    connection.execute("BEGIN IMMEDIATE")
    try:
        existing_user_columns = {str(row[1]) for row in connection.execute("PRAGMA table_info('users')")}
        for name, definition in USER_EXTENSIONS:
            if name not in existing_user_columns:
                connection.execute(f'ALTER TABLE users ADD COLUMN "{name}" {definition}')
        connection.execute("UPDATE users SET role='office_manager' WHERE role='manager'")
        invalid_role = connection.execute(
            "SELECT 1 FROM users WHERE role NOT IN ('admin','office_manager','counselor','viewer') LIMIT 1"
        ).fetchone()
        if invalid_role is not None:
            raise MigrationStateError("legacy user role cannot be mapped to a canonical role")
        for migration in request.pending:
            for statement in migration.statements:
                connection.execute(statement)
            backfill_legacy_tables(connection, request.encryption_secret, request.local_app_data_dir)
            connection.execute(
                "INSERT INTO schema_migrations(version,name,checksum_sha256,applied_at,app_build) VALUES(?,?,?,?,?)",
                (migration.version, migration.name, migration.checksum_sha256, "2026-07-10T00:00:00+00:00", request.app_build),
            )
            if migration.version >= 2:
                record_reconciliation(connection, migration.version)
        connection.commit()
    except (sqlite3.DatabaseError, MigrationStateError):
        connection.rollback()
        raise


def _current_schema_connection(connection: sqlite3.Connection) -> int:
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if table is None:
        return 0
    version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
    return int(version) if version is not None else 0


def _current_schema(database_path: Path) -> int:
    uri = f"file:{database_path.as_posix()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        return _current_schema_connection(connection)


def _validated_paths(database_path: Path, local_app_data_dir: Path) -> tuple[Path, Path]:
    root = local_app_data_dir.resolve()
    resolved_database = database_path.resolve()
    if not resolved_database.is_relative_to(root):
        raise MigrationPathError("database path must resolve inside local application data")
    if not resolved_database.is_file():
        raise FileNotFoundError(resolved_database)
    return resolved_database, root


def _cleanup_temporary_databases(database_path: Path) -> None:
    for path in database_path.parent.glob(f"{database_path.name}.migration-*.tmp"):
        path.unlink(missing_ok=True)


def _checkpoint(database_path: Path) -> None:
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _interrupt(actual: MigrationFailpoint | None, expected: MigrationFailpoint) -> None:
    if actual == expected:
        raise MigrationInterruptionError("injected migration interruption")
