from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from app.v2.migrations.errors import MigrationStateError
from app.v2.migrations.app_settings_migration import verify_app_setting_extensions
from app.v2.migrations.registry import APP_SETTINGS_MIGRATION_VERSION, MIGRATIONS
from app.v2.migrations.schema_contract import verify_required_schema
from app.v2.migrations.schema_core import APP_SETTING_NORMALIZED_EXTENSIONS, APP_SETTING_PROTOCOL_EXTENSIONS

LEGACY_COLUMNS = {
    "users": {"id", "username", "role", "password_hash"},
    "app_settings": {"id", "organization_name", "facility_timezone"},
    "treatment_plan_imports": {"id", "patient_id", "plan_id", "encrypted_payload"},
    "uploaded_documents": {"id", "patient_id", "plan_id", "storage_path", "sha256"},
    "treatment_plan_manager_actions": {"id", "patient_id", "criterion_id", "action"},
}

CURRENT_COLUMNS = {
    "users": {"id", "username", "role", "is_active", "must_reset_password", "is_locked", "auth_state", "recovery_required"},
    "app_settings": {"id", "emr_api_enabled", "treatment_plan_loc_change_window_validated", "alleva_treatment_plan_sync_enabled", "alleva_treatment_plan_sync_approved", "alleva_treatment_plan_endpoint_mapping_validated"},
    "api_harness_jobs": {"id", "job_id", "raw_sensitive_mode_used", "cancel_requested"},
    "workflow_profiles": {"id", "workflow_key", "is_active"},
    "schema_migrations": {"version", "name", "checksum_sha256", "applied_at", "app_build"},
    "facilities": {"id", "facility_key", "display_name", "timezone", "is_active", "created_at", "updated_at"},
    "user_facilities": {"user_id", "facility_id", "assigned_by_user_id", "assigned_at"},
    "patients": {"id", "facility_id", "canonical_client_id", "source_system", "lifecycle_state", "first_seen_at", "last_seen_at", "reconciled_at"},
    "patient_assignments": {"patient_id", "counselor_user_id", "assigned_by_user_id", "assigned_at", "ended_at", "is_active"},
    "loc_history": {"id", "patient_id", "loc_code", "source_system", "source_record_id", "effective_date", "recorded_at", "reconciliation_state", "evidence_sha256"},
    "treatment_plan_versions": {"id", "patient_id", "source_system", "source_record_id", "version_ordinal", "normalized_snapshot_encrypted", "content_sha256", "evidence_sha256", "imported_at", "sync_job_id", "approval_record_id", "contract_version", "contract_sha256"},
    "treatment_review_versions": {"id", "patient_id", "source_system", "source_record_id", "version_ordinal", "normalized_snapshot_encrypted", "content_sha256", "evidence_sha256", "imported_at", "sync_job_id", "approval_record_id", "contract_version", "contract_sha256"},
    "diagnosis_snapshots": {"id", "plan_version_id", "review_version_id", "source_record_id", "normalized_snapshot_encrypted", "content_sha256", "captured_at", "sync_job_id", "approval_record_id", "contract_version", "contract_sha256"},
    "source_documents": {"id", "patient_id", "plan_version_id", "review_version_id", "document_id", "sha256", "encrypted_relative_path"},
    "evaluation_runs": {"id", "plan_version_id", "checklist_version", "rules_version", "evaluation_date", "evidence_sha256", "run_sequence", "sync_job_id", "approval_record_id", "contract_version", "contract_sha256"},
    "criterion_results": {"id", "evaluation_run_id", "criterion_id", "result_status", "evidence_sha256"},
    "manager_dispositions": {"id", "plan_version_id", "criterion_id", "status", "actor_user_id", "created_at"},
    "correction_work_items": {"id", "plan_version_id", "disposition_id", "idempotency_key"},
    "correction_submissions": {"id", "work_item_id", "submission_encrypted", "idempotency_key"},
    "alleva_contract_approvals": {"id", "contract_version", "encrypted_contract_json", "contract_sha256"},
    "sync_jobs": {"id", "external_job_id", "approval_record_id", "idempotency_key", "cancel_requested"},
    "sync_checkpoints": {"id", "job_id", "endpoint_key", "page_number", "cursor_hash", "encrypted_records_json"},
    "sync_failures": {"id", "job_id", "error_class", "retryable", "attempt"},
    "reconciliation_outcomes": {"id", "job_id", "patient_id", "source_kind", "source_record_id", "outcome"},
}

@dataclass(frozen=True, slots=True)
class ReconciliationCount:
    category: str
    source_count: int
    target_count: int
    source_sha256: str
    target_sha256: str


def verify_database(path: Path, expected_version: int) -> None:
    uri = f"file:{path.as_posix()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        verify_connection(connection, expected_version)


def verify_connection(connection: sqlite3.Connection, expected_version: int) -> None:
    if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
        raise MigrationStateError("SQLite integrity check failed")
    connection.execute("PRAGMA foreign_keys=ON")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise MigrationStateError("foreign key reconciliation failed")
    if expected_version == 0:
        _verify_columns(connection, LEGACY_COLUMNS)
        if _table_exists(connection, "schema_migrations"):
            raise MigrationStateError("legacy schema contains an unexpected registry")
        return
    expected_registry = tuple(
        (migration.version, migration.name, migration.checksum_sha256)
        for migration in MIGRATIONS[:expected_version]
    )
    actual_registry = tuple(
        connection.execute("SELECT version,name,checksum_sha256 FROM schema_migrations ORDER BY version").fetchall()
    )
    if actual_registry != expected_registry:
        raise MigrationStateError("checksummed ordered migration registry mismatch")
    required_columns = {table: set(columns) for table, columns in CURRENT_COLUMNS.items()}
    if expected_version >= APP_SETTINGS_MIGRATION_VERSION:
        required_columns["app_settings"].update(name for name, _definition in APP_SETTING_NORMALIZED_EXTENSIONS)
    if expected_version >= 6:
        required_columns["app_settings"].add("api_requests_per_minute")
    if expected_version >= 7:
        required_columns["app_settings"].update(name for name, _definition in APP_SETTING_PROTOCOL_EXTENSIONS)
    if expected_version >= 2:
        required_columns["migration_reconciliation"] = {
            "migration_version", "category", "source_count", "target_count",
            "source_sha256", "target_sha256", "verified_at",
        }
    _verify_columns(connection, required_columns)
    if expected_version >= APP_SETTINGS_MIGRATION_VERSION:
        verify_app_setting_extensions(connection)
    verify_required_schema(connection, expected_version)
    if expected_version >= 2:
        _verify_reconciliation(connection)


def count_sha256(category: str, count: int) -> str:
    return hashlib.sha256(f"{category}:{count}".encode("utf-8")).hexdigest()


def reconciliation_counts(connection: sqlite3.Connection) -> tuple[ReconciliationCount, ...]:
    if not _table_exists(connection, "migration_reconciliation"):
        return ()
    return tuple(
        ReconciliationCount(str(row[0]), int(row[1]), int(row[2]), str(row[3]), str(row[4]))
        for row in connection.execute(
            "SELECT current.category,current.source_count,current.target_count,current.source_sha256,current.target_sha256 "
            "FROM migration_reconciliation current WHERE current.migration_version=("
            "SELECT MAX(history.migration_version) FROM migration_reconciliation history "
            "WHERE history.category=current.category) ORDER BY current.category"
        )
    )


def reconciliation_counts_database(path: Path) -> tuple[ReconciliationCount, ...]:
    uri = f"file:{path.as_posix()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        return reconciliation_counts(connection)


def record_reconciliation(connection: sqlite3.Connection, migration_version: int) -> None:
    category = "legacy_manager_actions"
    source_count = int(connection.execute("SELECT COUNT(*) FROM treatment_plan_manager_actions").fetchone()[0])
    dispositions = int(connection.execute("SELECT COUNT(*) FROM manager_dispositions").fetchone()[0])
    needs_review = int(connection.execute(
        "SELECT COUNT(*) FROM reconciliation_outcomes WHERE source_kind='legacy_manager_action'"
    ).fetchone()[0])
    target_count = dispositions + needs_review
    connection.execute(
        "INSERT OR REPLACE INTO migration_reconciliation("
        "migration_version,category,source_count,target_count,source_sha256,target_sha256,verified_at"
        ") VALUES(?,?,?,?,?,?,?)",
        (
            migration_version, category, source_count, target_count,
            count_sha256(category, source_count), count_sha256(category, target_count),
            "2026-07-10T00:00:00+00:00",
        ),
    )


def _verify_columns(connection: sqlite3.Connection, required: dict[str, set[str]]) -> None:
    for table, columns in required.items():
        if not _table_exists(connection, table):
            raise MigrationStateError("required database structure is missing a table")
        actual = {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')}
        if not columns <= actual:
            raise MigrationStateError("required database structure is missing columns")


def _verify_reconciliation(connection: sqlite3.Connection) -> None:
    rows = reconciliation_counts(connection)
    if not rows or "legacy_manager_actions" not in {row.category for row in rows}:
        raise MigrationStateError("source/target reconciliation is missing")
    for row in rows:
        if row.target_count < row.source_count:
            raise MigrationStateError("source/target reconciliation lost rows")
        if row.source_sha256 != count_sha256(row.category, row.source_count):
            raise MigrationStateError("source reconciliation hash mismatch")
        if row.target_sha256 != count_sha256(row.category, row.target_count):
            raise MigrationStateError("target reconciliation hash mismatch")


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None
