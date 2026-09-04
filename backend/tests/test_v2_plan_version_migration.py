from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from typing import Final

import pytest

from app.v2.migrations import runner
from app.v2.migrations.backup import read_backup
from app.v2.migrations.registry import MIGRATIONS
from app.v2.migrations.schema_verifier import verify_database
from v2_migration_fixtures import SYNTHETIC_SECRET, create_legacy_database

V10_CHECKSUMS: Final = (
    "fabf8ad5eb02c28a783210bdd5ceffa331899b3e1e98d6199707a59715b80851",
    "22a69ea2cc8aae8ae8f0ad63d41c3ccb07a6cff00d60dc8b71ec46b286fbc156",
    "f91a11611e03bcf66a226af995d764bd8df1173c8936d955905bead1320322e0",
    "80e0fb94d8f34508933ccbba540555f96b87dcf12237049a97dfeb1b9d0f6bc2",
    "f0a7c328ccc33a56b80cb72ee730de4d7bd8fa3e7af22d395af1a14cb5dbd835",
    "1cb45ea44816d2a5c5979ba564d04f80723187e99d379d3b92cbbe8b11d6ca3c",
    "1cb45ea44816d2a5c5979ba564d04f80723187e99d379d3b92cbbe8b11d6ca3c",
    "5993219170633e36e0abba5c41c7925ea9dcbcc08448f7bd962f86ee1b70ec36",
    "667ce83647d45166358925a3269f5de1acc2ebedbf7fda3ee516d68d09f952e4",
    "f2bd026491188a7e1945014fff71283df6923348ec976827b826ba180ace7b9c",
)
HISTORY_TABLES: Final = (
    "treatment_plan_imports", "treatment_plan_versions", "treatment_review_versions",
    "treatment_plan_manager_actions", "manager_dispositions", "reconciliation_outcomes",
    "patient_snapshot_versions", "correction_work_items", "correction_submissions",
)


@pytest.fixture(autouse=True)
def preserve_v11_migration_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "MIGRATIONS", MIGRATIONS[:11])
    monkeypatch.setattr(runner, "LATEST_SCHEMA_VERSION", 11)


def _v10_database(root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    database_path = create_legacy_database(root)
    with monkeypatch.context() as context:
        context.setattr(runner, "MIGRATIONS", MIGRATIONS[:10])
        context.setattr(runner, "LATEST_SCHEMA_VERSION", 10)
        runner.run_migrations(runner.MigrationRequest(database_path, root, SYNTHETIC_SECRET, "v10-test"))
    return database_path


def _history_hash(database_path: Path) -> str:
    with closing(sqlite3.connect(database_path)) as connection:
        rows = tuple(connection.execute(f'SELECT * FROM "{table}" ORDER BY id').fetchall() for table in HISTORY_TABLES)
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def _seed_action(connection: sqlite3.Connection, action_id: int, patient_id: str) -> None:
    connection.execute(
        "INSERT INTO treatment_plan_manager_actions("
        "id,patient_id,criterion_id,action,comment,override_reason,actor_user_id,actor_username,actor_role,created_at) "
        "VALUES(?,?,?,'comment','safe synthetic history','','2','manager','office_manager','2026-08-01T00:00:00+00:00')",
        (action_id, patient_id, f"criterion-{action_id}"),
    )


@pytest.fixture
def version_ten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    database_path = _v10_database(tmp_path, monkeypatch)
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO patients(id,facility_id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at) "
            "VALUES(100,1,'synthetic-unique','manual_upload','active','2026-07-01','2026-07-01'),"
            "(101,1,'synthetic-collision','manual_upload','active','2026-07-01','2026-07-01'),"
            "(102,1,'synthetic-collision','alleva_rest_api','active','2026-07-01','2026-07-01')"
        )
        connection.execute(
            "INSERT INTO treatment_plan_versions("
            "id,patient_id,source_system,source_record_id,version_ordinal,normalized_snapshot_encrypted,"
            "content_sha256,evidence_sha256,imported_at) "
            "SELECT 1000+id,id,source_system,'synthetic-source',1,?,printf('%064d',id),printf('%064d',id),'2026-07-01' "
            "FROM patients WHERE id IN (2,100,101,102)",
            (b"synthetic-encrypted-history",),
        )
        for action_id, patient_id in (
            (101, "synthetic-unique"), (102, "synthetic-client-200"),
            (103, "synthetic-collision"), (104, "synthetic-unique"), (105, "synthetic-missing"),
        ):
            _seed_action(connection, action_id, patient_id)
        connection.execute(
            "INSERT INTO manager_dispositions(plan_version_id,criterion_id,status,comment,actor_user_id,created_at) "
            "VALUES(1,'criterion-104','comment','safe synthetic history',2,'2026-08-01T00:00:00+00:00')"
        )
        connection.commit()
    return database_path


def test_v10_characterization_preserves_original_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the original v1-v10 registry and synthetic encrypted legacy data.
    database_path = _v10_database(tmp_path, monkeypatch)
    # When: version ten is independently verified.
    verify_database(database_path, 10)
    # Then: original SQL checksums and encrypted legacy bytes retain their contract.
    assert tuple(item.checksum_sha256 for item in MIGRATIONS[:10]) == V10_CHECKSUMS
    with closing(sqlite3.connect(database_path)) as connection:
        assert connection.execute("SELECT encrypted_payload FROM treatment_plan_imports").fetchone()[0].startswith("enc:v1:")
        assert connection.execute("SELECT COUNT(*) FROM treatment_plan_versions").fetchone() == (2,)


def test_v11_assigns_only_unique_uncontested_history(version_ten: Path) -> None:
    # Given: unique, ambiguous, cross-source, historically unassigned and known-wrong actions.
    original_history = _history_hash(version_ten)
    # When: the real v10-to-v11 migration runs.
    report = runner.run_migrations(runner.MigrationRequest(version_ten, version_ten.parent, SYNTHETIC_SECRET, "v11-test"))
    # Then: only the provable unique action is linked, with no rewritten or appended old history.
    assert report.applied_versions == (11,)
    with closing(sqlite3.connect(version_ten)) as connection:
        assert connection.execute("SELECT * FROM manager_action_plan_links ORDER BY action_id").fetchall() == [
            (1, None), (101, 1100), (102, None), (103, None), (104, None), (105, None),
        ]
    assert _history_hash(version_ten) == original_history
    verify_database(version_ten, 11)


def test_repeated_v11_startup_keeps_link_history_and_database_bytes(version_ten: Path) -> None:
    # Given: a successfully upgraded version-ten database.
    request = runner.MigrationRequest(version_ten, version_ten.parent, SYNTHETIC_SECRET, "v11-test")
    runner.run_migrations(request)
    original_bytes = version_ten.read_bytes()
    # When: startup repeats.
    report = runner.run_migrations(request)
    # Then: no migration, duplicate links or new backup is produced.
    assert report.target_schema == 11
    assert report.applied_versions == ()
    assert report.backup_path is None
    assert version_ten.read_bytes() == original_bytes


def test_wrong_mechanical_correction_lineage_remains_unassigned(version_ten: Path) -> None:
    # Given: an older plan was reviewed, but the legacy latest-plan path stored the return against a newer version.
    with closing(sqlite3.connect(version_ten)) as connection:
        connection.execute(
            "INSERT INTO treatment_plan_versions(id,patient_id,source_system,source_record_id,version_ordinal,"
            "normalized_snapshot_encrypted,content_sha256,evidence_sha256,imported_at,supersedes_version_id) "
            "SELECT 3,patient_id,source_system,source_record_id,3,normalized_snapshot_encrypted,"
            "'synthetic-newer-content','synthetic-newer-evidence','2026-07-15',id FROM treatment_plan_versions WHERE id=1"
        )
        connection.execute(
            "INSERT INTO users SELECT 3,'synthetic-counselor',full_name,password_hash,'counselor',is_active,"
            "must_reset_password,failed_login_attempts,is_locked,auth_state,locked_until,password_changed_at,"
            "recovery_required,last_login_at,created_at FROM users WHERE id=2"
        )
        connection.execute("UPDATE treatment_plan_manager_actions SET action='return_for_correction' WHERE id=102")
        disposition = connection.execute(
            "INSERT INTO manager_dispositions(plan_version_id,criterion_id,status,comment,actor_user_id,created_at) "
            "VALUES(3,'criterion-102','return_for_correction','safe synthetic history',2,'2026-08-01T00:00:00+00:00')"
        )
        connection.execute(
            "INSERT INTO correction_work_items(plan_version_id,criterion_id,disposition_id,assigned_counselor_user_id,"
            "status,opened_at,idempotency_key) VALUES(3,'criterion-102',?,3,'open','2026-08-01','synthetic-wrong-history')",
            (disposition.lastrowid,),
        )
        connection.commit()
    original_history = _history_hash(version_ten)
    # When: v11 reconciles legacy actions without assuming the stored return target was correct.
    runner.run_migrations(runner.MigrationRequest(version_ten, version_ten.parent, SYNTHETIC_SECRET, "v11-test"))
    # Then: the ambiguous action remains unassigned and the old work item/disposition remain byte-preserved.
    with closing(sqlite3.connect(version_ten)) as connection:
        assert connection.execute("SELECT plan_version_id FROM manager_action_plan_links WHERE action_id=102").fetchone() == (None,)
    assert _history_hash(version_ten) == original_history


@pytest.mark.parametrize("failpoint", tuple(runner.MigrationFailpoint))
def test_interrupted_v11_preserves_recoverable_v10(version_ten: Path, failpoint: runner.MigrationFailpoint) -> None:
    # Given: immutable v10 history and its authoritative original bytes.
    original_bytes = version_ten.read_bytes()
    backup_paths = set((version_ten.parent / "backups").iterdir())
    # When: the real runner is interrupted before replacing the authoritative database.
    with pytest.raises(runner.MigrationInterruptionError):
        runner.run_migrations(runner.MigrationRequest(
            version_ten, version_ten.parent, SYNTHETIC_SECRET, "v11-test", failpoint=failpoint,
        ))
    # Then: v10 bytes and encrypted recovery evidence survive, with no success registry or temporary database.
    assert version_ten.read_bytes() == original_bytes
    verify_database(version_ten, 10)
    assert not tuple(version_ten.parent.glob("*.migration-*.tmp"))
    new_backups = set((version_ten.parent / "backups").iterdir()) - backup_paths
    assert len(new_backups) == 1
    backup = read_backup(new_backups.pop(), SYNTHETIC_SECRET)
    assert (backup.source_schema, backup.target_schema) == (10, 11)
    assert backup.database_bytes == original_bytes


def test_restore_then_retry_v11_recovers_exact_history(version_ten: Path) -> None:
    # Given: a successful upgrade and its encrypted version-ten recovery backup.
    original_history = _history_hash(version_ten)
    request = runner.MigrationRequest(version_ten, version_ten.parent, SYNTHETIC_SECRET, "v11-test")
    first = runner.run_migrations(request)
    assert first.backup_path is not None
    runner.restore_database(runner.RestoreRequest(version_ten, version_ten.parent, SYNTHETIC_SECRET, first.backup_path))
    verify_database(version_ten, 10)
    # When: the restored database is upgraded again.
    retry = runner.run_migrations(request)
    # Then: the full upgrade succeeds without altering original history.
    assert retry.applied_versions == (11,)
    assert _history_hash(version_ten) == original_history
    verify_database(version_ten, 11)


@pytest.mark.parametrize("startup_count", (1, 2))
def test_fresh_app_startup_keeps_link_table_migration_managed(tmp_path: Path, startup_count: int) -> None:
    # Given: fresh synthetic local application data and the shipped application startup entry point.
    environment = {key: value for key, value in os.environ.items() if not key.startswith("IZ_CNA_")}
    environment.update({
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "IZ_CNA_LOCAL_APP_DATA_DIR": str(tmp_path),
        "IZ_CNA_LOCAL_SQLITE_DB_PATH": "clinical-notes-analyzer-v2.sqlite3",
        "IZ_CNA_SECRET_KEY": SYNTHETIC_SECRET,
        "IZ_CNA_DATA_ENCRYPTION_KEY": SYNTHETIC_SECRET,
        "IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD": "SyntheticStartupPassword1",
    })
    # When: a fresh process starts the real application once or starts it again.
    for _ in range(startup_count):
        process = subprocess.run(
            [sys.executable, "-c", "from app.v2.migrations import runner; runner.MIGRATIONS=runner.MIGRATIONS[:11]; "
             "runner.LATEST_SCHEMA_VERSION=11; from app.main import app; from app.v2.db import engine; engine.dispose()"],
            env=environment, capture_output=True, text=True, timeout=60, check=False,
        )
        assert process.returncode == 0, process.stderr
    # Then: migration owns the link table, while the legacy ORM table has no new column.
    database_path = tmp_path / "clinical-notes-analyzer-v2.sqlite3"
    verify_database(database_path, 11)
    with closing(sqlite3.connect(database_path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM manager_action_plan_links").fetchone() == (0,)
        assert "plan_version_id" not in {row[1] for row in connection.execute("PRAGMA table_info(treatment_plan_manager_actions)")}
