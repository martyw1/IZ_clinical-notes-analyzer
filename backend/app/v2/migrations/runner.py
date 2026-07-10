from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from app.v2.migrations.backup import (
    BackupEnvelopeError,
    BackupRequest,
    create_backup,
    read_backup,
    validate_sqlite_file,
)
from app.v2.migrations.backfill import backfill_legacy_tables
from app.v2.migrations.registry import LATEST_SCHEMA_VERSION, MIGRATIONS, Migration
from app.v2.migrations.schema_core import USER_EXTENSIONS


class MigrationFailpoint(StrEnum):
    AFTER_BACKUP = "after_backup"
    AFTER_COPY = "after_copy"
    AFTER_SCHEMA = "after_schema"
    BEFORE_REPLACE = "before_replace"


@dataclass(frozen=True, slots=True)
class MigrationStateError(Exception):
    reason: str

    def __str__(self) -> str:
        return f"migration state rejected: {self.reason}"


@dataclass(frozen=True, slots=True)
class MigrationRequest:
    database_path: Path
    local_app_data_dir: Path
    encryption_secret: str
    app_build: str
    dry_run: bool = False
    failpoint: MigrationFailpoint | None = None


@dataclass(frozen=True, slots=True)
class RestoreRequest:
    database_path: Path
    local_app_data_dir: Path
    encryption_secret: str
    backup_path: Path


@dataclass(frozen=True, slots=True)
class ApplyRequest:
    database_path: Path
    local_app_data_dir: Path
    encryption_secret: str
    app_build: str
    pending: tuple[Migration, ...]


@dataclass(frozen=True, slots=True)
class TableCount:
    table: str
    count: int


@dataclass(frozen=True, slots=True)
class MigrationReport:
    source_schema: int
    target_schema: int
    dry_run: bool
    original_sha256: str
    migrated_sha256: str
    applied_versions: tuple[int, ...]
    counts: tuple[TableCount, ...]
    backup_path: Path | None

    def table_count(self, table: str) -> int:
        matches = [entry.count for entry in self.counts if entry.table == table]
        if not matches:
            raise KeyError(table)
        return matches[0]


@dataclass(frozen=True, slots=True)
class RestoreReport:
    database_sha256: str
    source_schema: int
    target_schema: int


REPORT_TABLES = (
    "facilities",
    "patients",
    "patient_assignments",
    "loc_history",
    "treatment_plan_versions",
    "treatment_review_versions",
    "diagnosis_snapshots",
    "source_documents",
    "evaluation_runs",
    "criterion_results",
    "manager_dispositions",
    "correction_work_items",
    "correction_submissions",
    "sync_jobs",
    "sync_checkpoints",
    "sync_failures",
    "reconciliation_outcomes",
)


def run_migrations(request: MigrationRequest) -> MigrationReport:
    database_path, root = _validated_paths(request.database_path, request.local_app_data_dir)
    _cleanup_temporary_databases(database_path)
    _checkpoint(database_path)
    original_sha256 = _file_sha256(database_path)
    source_schema = _current_schema(database_path)
    pending = tuple(migration for migration in MIGRATIONS if migration.version > source_schema)
    if not pending:
        return MigrationReport(
            source_schema=source_schema,
            target_schema=source_schema,
            dry_run=request.dry_run,
            original_sha256=original_sha256,
            migrated_sha256=original_sha256,
            applied_versions=(),
            counts=_table_counts(database_path),
            backup_path=None,
        )
    backup_path: Path | None = None
    temporary_path = database_path.with_name(f"{database_path.name}.migration-{uuid.uuid4().hex}.tmp")
    try:
        if not request.dry_run:
            backup = create_backup(
                BackupRequest(database_path, root, request.encryption_secret, source_schema, LATEST_SCHEMA_VERSION, request.app_build)
            )
            backup_path = backup.path
            _interrupt(request.failpoint, MigrationFailpoint.AFTER_BACKUP)
        shutil.copy2(database_path, temporary_path)
        _interrupt(request.failpoint, MigrationFailpoint.AFTER_COPY)
        _apply_pending(ApplyRequest(temporary_path, root, request.encryption_secret, request.app_build, pending))
        _interrupt(request.failpoint, MigrationFailpoint.AFTER_SCHEMA)
        migrated_sha256 = _file_sha256(temporary_path)
        counts = _table_counts(temporary_path)
        if request.dry_run:
            return MigrationReport(
                source_schema=source_schema,
                target_schema=LATEST_SCHEMA_VERSION,
                dry_run=True,
                original_sha256=original_sha256,
                migrated_sha256=migrated_sha256,
                applied_versions=tuple(item.version for item in pending),
                counts=counts,
                backup_path=None,
            )
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
        os.replace(temporary_path, database_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return RestoreReport(
        database_sha256=payload.database_sha256,
        source_schema=payload.source_schema,
        target_schema=payload.target_schema,
    )


def _apply_pending(request: ApplyRequest) -> None:
    with closing(sqlite3.connect(request.database_path)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
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
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise MigrationStateError("foreign key reconciliation failed")
            if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise MigrationStateError("SQLite integrity check failed")
            connection.commit()
        except (sqlite3.DatabaseError, MigrationStateError):
            connection.rollback()
            raise


def _current_schema(database_path: Path) -> int:
    with closing(sqlite3.connect(database_path)) as connection:
        table = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone()
        if table is None:
            return 0
        rows = connection.execute("SELECT version,name,checksum_sha256 FROM schema_migrations ORDER BY version").fetchall()
    for version, name, checksum in rows:
        expected = next((item for item in MIGRATIONS if item.version == version), None)
        if expected is None or expected.name != name or expected.checksum_sha256 != checksum:
            raise MigrationStateError("applied migration registry does not match application registry")
    return int(rows[-1][0]) if rows else 0


def _validated_paths(database_path: Path, local_app_data_dir: Path) -> tuple[Path, Path]:
    root = local_app_data_dir.resolve()
    resolved_database = database_path.resolve()
    if not resolved_database.is_relative_to(root):
        raise ValueError("database path must resolve inside local application data")
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


def _table_counts(database_path: Path) -> tuple[TableCount, ...]:
    with closing(sqlite3.connect(database_path)) as connection:
        existing = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return tuple(
            TableCount(table=table, count=int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]))
            for table in REPORT_TABLES
            if table in existing
        )


def _interrupt(actual: MigrationFailpoint | None, expected: MigrationFailpoint) -> None:
    if actual == expected:
        raise RuntimeError("injected migration interruption")
