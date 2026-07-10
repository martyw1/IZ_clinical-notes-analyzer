from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing

import pytest

from app.v2.migrations.runner import (
    MigrationFailpoint,
    MigrationRequest,
    RestoreRequest,
    restore_database,
    run_migrations,
)
from app.v2.migrations.backup import BackupEnvelopeError
from v2_migration_fixtures import SYNTHETIC_SECRET, create_legacy_database


def test_backfill_preserves_multi_plan_review_documents_and_role_mapping(tmp_path) -> None:
    # Given: a synthetic legacy patient aggregate with two plans, two reviews, and one source document.
    database_path = create_legacy_database(tmp_path)

    # When: the production migration lifecycle runs.
    report = run_migrations(MigrationRequest(database_path, tmp_path, SYNTHETIC_SECRET, "test-build"))

    # Then: version history, exact source linkage, canonical roles, and counts are preserved without names.
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM patients").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM treatment_plan_versions").fetchone() == (2,)
        assert connection.execute("SELECT COUNT(*) FROM treatment_review_versions").fetchone() == (2,)
        assert connection.execute("SELECT role FROM users WHERE username='manager'").fetchone() == ("office_manager",)
        assert connection.execute("SELECT plan_version_id FROM source_documents").fetchone()[0] is not None
        patient_columns = tuple(row[1] for row in connection.execute("PRAGMA table_info('patients')"))
        assert all("name" not in column for column in patient_columns)
    assert report.table_count("treatment_plan_versions") == 2
    assert report.table_count("treatment_review_versions") == 2


def test_ambiguous_manager_linkage_is_needs_review_and_migration_is_idempotent(tmp_path) -> None:
    # Given: a legacy manager action for a patient with multiple plan versions and no plan key.
    database_path = create_legacy_database(tmp_path, ambiguous_actions=True)

    # When: migration runs twice.
    first = run_migrations(MigrationRequest(database_path, tmp_path, SYNTHETIC_SECRET, "test-build"))
    second = run_migrations(MigrationRequest(database_path, tmp_path, SYNTHETIC_SECRET, "test-build"))

    # Then: linkage is not guessed, the needs-review outcome is stable, and no rows duplicate.
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM manager_dispositions").fetchone() == (0,)
        assert connection.execute("SELECT outcome FROM reconciliation_outcomes").fetchone() == ("needs_review",)
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone() == (1,)
    assert first.target_schema == second.target_schema
    assert second.applied_versions == ()


def test_dry_run_reports_counts_and_hashes_without_writing(tmp_path) -> None:
    # Given: an unmigrated synthetic legacy database.
    database_path = create_legacy_database(tmp_path)
    original_hash = hashlib.sha256(database_path.read_bytes()).hexdigest()

    # When: migration is requested in dry-run mode.
    report = run_migrations(MigrationRequest(database_path, tmp_path, SYNTHETIC_SECRET, "test-build", dry_run=True))

    # Then: report hashes/counts are populated while the database and backup directory remain untouched.
    assert report.dry_run is True
    assert report.original_sha256 == original_hash
    assert report.migrated_sha256 != original_hash
    assert hashlib.sha256(database_path.read_bytes()).hexdigest() == original_hash
    assert not (tmp_path / "backups").exists()
    assert not tuple(tmp_path.glob("*.migration-*.tmp"))


@pytest.mark.parametrize("failpoint", tuple(MigrationFailpoint))
def test_interrupted_migration_keeps_original_authoritative_and_cleans_temp(tmp_path, failpoint) -> None:
    # Given: an unmigrated synthetic legacy database and an injected lifecycle interruption.
    database_path = create_legacy_database(tmp_path)
    original_hash = hashlib.sha256(database_path.read_bytes()).hexdigest()

    # When: migration is interrupted at the selected failpoint.
    with pytest.raises(RuntimeError, match="injected migration interruption"):
        run_migrations(MigrationRequest(database_path, tmp_path, SYNTHETIC_SECRET, "test-build", failpoint=failpoint))

    # Then: the original database remains usable and temporary copies are removed.
    assert hashlib.sha256(database_path.read_bytes()).hexdigest() == original_hash
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM treatment_plan_imports").fetchone() == (1,)
    assert not tuple(tmp_path.glob("*.migration-*.tmp"))


def test_verified_restore_replaces_current_database_and_wrong_key_preserves_it(tmp_path) -> None:
    # Given: a migrated database, its pre-migration backup, and a post-migration sentinel mutation.
    database_path = create_legacy_database(tmp_path)
    report = run_migrations(MigrationRequest(database_path, tmp_path, SYNTHETIC_SECRET, "test-build"))
    backup_path = report.backup_path
    assert backup_path is not None
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("CREATE TABLE post_migration_sentinel(id INTEGER PRIMARY KEY)")
        connection.commit()
    mutated_hash = hashlib.sha256(database_path.read_bytes()).hexdigest()

    # When/Then: a wrong key fails closed without replacement, then the correct key restores the legacy bytes.
    with pytest.raises(BackupEnvelopeError):
        restore_database(RestoreRequest(database_path, tmp_path, "wrong-secret", backup_path))
    assert hashlib.sha256(database_path.read_bytes()).hexdigest() == mutated_hash
    restored = restore_database(RestoreRequest(database_path, tmp_path, SYNTHETIC_SECRET, backup_path))
    assert hashlib.sha256(database_path.read_bytes()).hexdigest() == restored.database_sha256
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM treatment_plan_imports").fetchone() == (1,)
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='post_migration_sentinel'").fetchone() is None


def test_path_outside_local_app_data_is_rejected(tmp_path) -> None:
    # Given: a database path outside the declared local application data directory.
    database_path = create_legacy_database(tmp_path)
    other_root = tmp_path / "other-root"
    other_root.mkdir()

    # When/Then: migration rejects the unsafe runtime path before creating artifacts.
    with pytest.raises(ValueError, match="local application data"):
        run_migrations(MigrationRequest(database_path, other_root, SYNTHETIC_SECRET, "test-build"))
