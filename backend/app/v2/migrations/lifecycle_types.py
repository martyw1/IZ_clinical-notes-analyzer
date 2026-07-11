from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from app.v2.migrations.registry import Migration
from app.v2.migrations.schema_verifier import ReconciliationCount


class MigrationFailpoint(StrEnum):
    AFTER_BACKUP = "after_backup"
    AFTER_COPY = "after_copy"
    AFTER_SCHEMA = "after_schema"
    BEFORE_REPLACE = "before_replace"


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
    reconciliation: tuple[ReconciliationCount, ...]
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
