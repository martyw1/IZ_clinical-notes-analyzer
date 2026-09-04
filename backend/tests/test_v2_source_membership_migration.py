from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from app.v2.migrations import runner
from app.v2.migrations.backup import read_backup
from app.v2.migrations.errors import MigrationStateError
from app.v2.migrations.registry import MIGRATIONS
from app.v2.migrations.schema_verifier import verify_database
from v2_migration_fixtures import SYNTHETIC_SECRET, create_legacy_database


@pytest.fixture
def version_eleven(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    database = create_legacy_database(tmp_path)
    with monkeypatch.context() as context:
        context.setattr(runner, "MIGRATIONS", MIGRATIONS[:11])
        context.setattr(runner, "LATEST_SCHEMA_VERSION", 11)
        runner.run_migrations(runner.MigrationRequest(database, tmp_path, SYNTHETIC_SECRET, "synthetic-v11"))
    return database


def _request(database: Path) -> runner.MigrationRequest:
    return runner.MigrationRequest(database, database.parent, SYNTHETIC_SECRET, "synthetic-v12")


def _history_fingerprint(database: Path) -> str:
    with closing(sqlite3.connect(database)) as db:
        tables = ("source_documents", "treatment_plan_versions", "treatment_review_versions", "treatment_plan_imports",
                  "treatment_plan_manager_actions", "manager_action_plan_links", "manager_dispositions", "reconciliation_outcomes")
        rows = tuple(db.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall() for table in tables)
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def test_v11_upgrade_preserves_history_and_backfills_exact_original_pairs(version_eleven: Path) -> None:
    # Given: immutable v11 history with an original source FK.
    history = _history_fingerprint(version_eleven)
    # When: the real next migration runs.
    report = runner.run_migrations(_request(version_eleven))
    # Then: v12 adds the original exact pair and changes no historical rows.
    assert report.applied_versions == (12,)
    with closing(sqlite3.connect(version_eleven)) as db:
        original = db.execute("SELECT id,plan_version_id FROM source_documents WHERE plan_version_id IS NOT NULL").fetchall()
        assert db.execute("SELECT source_document_id,plan_version_id FROM source_document_plan_memberships").fetchall() == original
    assert _history_fingerprint(version_eleven) == history
    verify_database(version_eleven, 12)


def test_repeat_startup_preserves_tombstone_and_extra_valid_memberships(version_eleven: Path) -> None:
    # Given: one historical tombstone and an additional legitimate runtime association.
    runner.run_migrations(_request(version_eleven))
    with closing(sqlite3.connect(version_eleven)) as db:
        db.execute("UPDATE source_document_plan_memberships SET detached_at='2026-09-04',detached_by_user_id=1")
        db.execute("INSERT INTO source_document_plan_memberships(source_document_id,plan_version_id,attached_at,attached_by_user_id) "
                   "SELECT id,2,'2026-09-04',1 FROM source_documents LIMIT 1")
        db.commit()
    before = version_eleven.read_bytes()
    # When: startup verifies the already upgraded database.
    report = runner.run_migrations(_request(version_eleven))
    # Then: no startup fallback reactivates the original or rejects a valid extra pair.
    assert report.applied_versions == ()
    assert version_eleven.read_bytes() == before


@pytest.mark.parametrize("corruption", ["missing_pair", "swapped_pair", "missing_reconciliation", "guard", "index"])
def test_verifier_rejects_membership_corruption(version_eleven: Path, corruption: str) -> None:
    # Given: a migrated database with one deliberately damaged membership invariant.
    runner.run_migrations(_request(version_eleven))
    with closing(sqlite3.connect(version_eleven)) as db:
        if corruption in {"missing_pair", "swapped_pair"}:
            db.execute("DELETE FROM source_document_plan_memberships")
            if corruption == "swapped_pair":
                db.execute("INSERT INTO source_document_plan_memberships(source_document_id,plan_version_id,attached_at) "
                           "SELECT id,2,'2026-09-04' FROM source_documents LIMIT 1")
        elif corruption == "missing_reconciliation":
            db.execute("DELETE FROM migration_reconciliation WHERE migration_version=12 AND category='source_document_original_pairs'")
        elif corruption == "guard":
            db.execute("DROP TRIGGER source_membership_validate_insert")
        else:
            db.execute("DROP INDEX ix_source_membership_plan_active")
        db.commit()
    # When: startup independently verifies the schema and exact original-pair presence.
    with pytest.raises(MigrationStateError):
        verify_database(version_eleven, 12)
    # Then: equal counts cannot substitute for the correct original association.


@pytest.mark.parametrize("failpoint", tuple(runner.MigrationFailpoint))
def test_interrupted_v12_preserves_v11_and_encrypted_recovery(version_eleven: Path, failpoint: runner.MigrationFailpoint) -> None:
    # Given: verified v11 bytes and the pre-existing backup inventory.
    original = version_eleven.read_bytes()
    backups = set((version_eleven.parent / "backups").iterdir())
    # When: the migration is interrupted before atomic replacement.
    with pytest.raises(runner.MigrationInterruptionError):
        runner.run_migrations(runner.MigrationRequest(version_eleven, version_eleven.parent, SYNTHETIC_SECRET,
                                                      "synthetic-v12", failpoint=failpoint))
    # Then: authoritative bytes survive and the new encrypted backup restores exactly v11.
    assert version_eleven.read_bytes() == original
    assert not tuple(version_eleven.parent.glob("*.migration-*.tmp"))
    new_backups = set((version_eleven.parent / "backups").iterdir()) - backups
    assert len(new_backups) == 1
    backup = read_backup(new_backups.pop(), SYNTHETIC_SECRET)
    assert (backup.source_schema, backup.target_schema) == (11, 12)
    assert backup.database_bytes == original
