from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from contextlib import closing

import pytest
from cryptography.fernet import Fernet

from app.v2.migrations.backfill_types import JsonValue
from app.v2.migrations.backup import MAGIC, BackupEnvelopeError, BackupRequest, create_backup, read_backup
from app.v2.migrations.registry import LATEST_SCHEMA_VERSION
from app.v2.migrations.runner import MigrationRequest, MigrationStateError, RestoreRequest, restore_database, run_migrations
from v2_migration_fixtures import SYNTHETIC_SECRET, create_legacy_database, encrypted_text


def test_backup_rejects_authenticated_noncanonical_header_bytes(tmp_path) -> None:
    # Given: an authenticated backup whose semantic header is valid.
    database_path = create_legacy_database(tmp_path)
    result = create_backup(BackupRequest(database_path, tmp_path, SYNTHETIC_SECRET, 0, 1, "test-build"))
    envelope = result.path.read_bytes()
    header_length = int.from_bytes(envelope[9:13], "big")
    header = json.loads(envelope[13 : 13 + header_length])
    token = envelope[13 + header_length :]

    # When: the same header is encoded with noncanonical whitespace and ordering.
    noncanonical = json.dumps(header, indent=1, sort_keys=False).encode("utf-8")
    result.path.write_bytes(MAGIC + len(noncanonical).to_bytes(4, "big") + noncanonical + token)

    # Then: exact canonical-byte verification rejects the envelope.
    with pytest.raises(BackupEnvelopeError, match="canonical"):
        read_backup(result.path, SYNTHETIC_SECRET)


def test_no_pending_migration_rejects_required_schema_drift(tmp_path) -> None:
    # Given: a current migrated database whose immutable-plan trigger is removed.
    database_path = create_legacy_database(tmp_path)
    report = run_migrations(MigrationRequest(database_path, tmp_path, SYNTHETIC_SECRET, "test-build"))
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("DROP TRIGGER treatment_plan_versions_no_update")
        connection.commit()

    # When/Then: a no-pending migration run still performs exact structure verification.
    with pytest.raises(MigrationStateError, match="required database structure"):
        run_migrations(MigrationRequest(database_path, tmp_path, SYNTHETIC_SECRET, "test-build"))


def test_no_pending_migration_rejects_weakened_same_name_partial_unique_index(tmp_path) -> None:
    # Given: a current database whose required partial unique index is replaced by a weaker same-name index.
    database_path = create_legacy_database(tmp_path)
    run_migrations(MigrationRequest(database_path, tmp_path, SYNTHETIC_SECRET, "test-build"))
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("DROP INDEX uq_patient_assignments_active")
        connection.execute(
            "CREATE INDEX uq_patient_assignments_active ON patient_assignments(counselor_user_id,patient_id)"
        )
        connection.commit()

    # When/Then: exact index semantics verification rejects changed uniqueness, order, and predicate.
    with pytest.raises(MigrationStateError, match="structure"):
        run_migrations(MigrationRequest(database_path, tmp_path, SYNTHETIC_SECRET, "test-build"))


def test_dry_run_does_not_checkpoint_or_modify_wal_files(tmp_path) -> None:
    # Given: a legacy WAL database with committed bytes still present in its WAL file.
    database_path = create_legacy_database(tmp_path)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE wal_probe(id INTEGER PRIMARY KEY, safe_value TEXT)")
        connection.execute("INSERT INTO wal_probe(safe_value) VALUES('synthetic')")
        connection.commit()
        observed_paths = (database_path, database_path.with_name(database_path.name + "-wal"), database_path.with_name(database_path.name + "-shm"))
        before = {path.name: path.read_bytes() for path in observed_paths if path.exists()}

        # When: the full migration is evaluated in dry-run mode.
        report = run_migrations(MigrationRequest(database_path, tmp_path, SYNTHETIC_SECRET, "test-build", dry_run=True))
        after = {path.name: path.read_bytes() for path in observed_paths if path.exists()}

        # Then: source database, WAL, and shared-memory bytes are unchanged.
        assert report.dry_run is True
        assert after == before
    finally:
        connection.close()


def test_restore_rejects_authenticated_decoy_sqlite_and_preserves_current_database(tmp_path) -> None:
    # Given: a valid current database and an authenticated backup containing unrelated SQLite.
    database_path = create_legacy_database(tmp_path)
    original_sha256 = hashlib.sha256(database_path.read_bytes()).hexdigest()
    decoy_path = tmp_path / "decoy.sqlite3"
    with closing(sqlite3.connect(decoy_path)) as connection:
        connection.execute("CREATE TABLE decoy(id INTEGER PRIMARY KEY, safe_value TEXT)")
        connection.commit()
    backup = create_backup(BackupRequest(decoy_path, tmp_path, SYNTHETIC_SECRET, 0, LATEST_SCHEMA_VERSION, "test-build"))

    # When/Then: schema verification rejects the decoy before atomic replacement.
    with pytest.raises(BackupEnvelopeError, match="schema"):
        restore_database(RestoreRequest(database_path, tmp_path, SYNTHETIC_SECRET, backup.path))
    assert hashlib.sha256(database_path.read_bytes()).hexdigest() == original_sha256


def test_unmatched_manager_action_is_reconciled_needs_review_with_balanced_counts(tmp_path) -> None:
    # Given: a legacy manager action whose canonical patient has no treatment-plan import.
    database_path = create_legacy_database(tmp_path)

    # When: legacy clinical data is migrated.
    report = run_migrations(MigrationRequest(database_path, tmp_path, SYNTHETIC_SECRET, "test-build"))

    # Then: the action is preserved as Needs Review and reconciliation counts balance.
    with closing(sqlite3.connect(database_path)) as connection:
        outcome = connection.execute(
            "SELECT outcome FROM reconciliation_outcomes WHERE source_kind='legacy_manager_action'"
        ).fetchone()
        counts = connection.execute(
            "SELECT source_count,target_count FROM migration_reconciliation WHERE category='legacy_manager_actions'"
        ).fetchone()
    assert outcome == ("needs_review",)
    assert counts == (1, 1)
    assert [(item.category, item.source_count, item.target_count) for item in report.reconciliation] == [
        ("legacy_manager_actions", 1, 1)
    ]


def test_backfill_recursively_removes_patient_name_aliases_before_reencryption(tmp_path) -> None:
    # Given: nested legacy plan data containing several patient-name aliases and a privacy canary.
    database_path = create_legacy_database(tmp_path)
    with closing(sqlite3.connect(database_path)) as connection:
        stored = connection.execute("SELECT encrypted_payload FROM treatment_plan_imports").fetchone()[0]
        payload = _decrypt_legacy_text(str(stored))
        plan = payload["treatment_plans"][0]
        plan["patientName"] = "PRIVACY-CANARY-NAME"
        plan["nested"] = {
            "patient_display_label": "PRIVACY-CANARY-NAME",
            "patient_full_name": "PRIVACY-CANARY-NAME",
            "clientFullName": "PRIVACY-CANARY-NAME",
            "safe": "retained",
        }
        connection.execute(
            "UPDATE treatment_plan_imports SET encrypted_payload=?",
            (encrypted_text(json.dumps(payload, sort_keys=True)),),
        )
        connection.commit()

    # When: the legacy snapshot is decrypted, scrubbed recursively, and re-encrypted.
    run_migrations(MigrationRequest(database_path, tmp_path, SYNTHETIC_SECRET, "test-build"))

    # Then: decrypted migrated content retains safe data but no patient-name alias or canary.
    with closing(sqlite3.connect(database_path)) as connection:
        encrypted = connection.execute("SELECT normalized_snapshot_encrypted FROM treatment_plan_versions ORDER BY id LIMIT 1").fetchone()[0]
    migrated = _decrypt_snapshot(bytes(encrypted))
    assert "PRIVACY-CANARY-NAME" not in json.dumps(migrated)
    assert "patientName" not in migrated
    assert migrated["nested"] == {"safe": "retained"}


def test_migration_neutralizes_legacy_plaintext_patient_identity_everywhere(tmp_path) -> None:
    # Given: a legacy plaintext display label containing an identity canary.
    database_path = create_legacy_database(tmp_path)
    canary = "PLAINTEXT-PATIENT-NAME-CANARY"
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("UPDATE treatment_plan_imports SET patient_display_label=?", (canary,))
        connection.commit()

    # When: migration backfills the immutable clinical ledger.
    report = run_migrations(MigrationRequest(database_path, tmp_path, SYNTHETIC_SECRET, "test-build"))

    # Then: only the safe patient-ID label remains and no storage or report output exposes the canary.
    with closing(sqlite3.connect(database_path)) as connection:
        label = connection.execute(
            "SELECT patient_display_label FROM treatment_plan_imports WHERE patient_id='synthetic-client-200'"
        ).fetchone()
        stored_values = _sqlite_storage_bytes(connection)
    encoded_canary = canary.encode("utf-8")
    assert label == ("Patient ID synthetic-client-200",)
    assert all(encoded_canary not in value for value in stored_values)
    assert encoded_canary not in database_path.read_bytes()
    assert canary not in repr(report)


def test_every_persisted_boolean_has_symmetric_insert_and_update_protection(tmp_path) -> None:
    # Given: the current schema with application-owned boolean invariants.
    database_path = create_legacy_database(tmp_path)
    run_migrations(MigrationRequest(database_path, tmp_path, SYNTHETIC_SECRET, "test-build"))

    # When/Then: required INSERT/UPDATE triggers exist and invalid app-settings INSERT is rejected by them.
    with closing(sqlite3.connect(database_path)) as connection:
        triggers = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        assert {
            "users_boolean_insert_check", "users_boolean_update_check",
            "app_settings_boolean_insert_check", "app_settings_boolean_update_check",
            "api_harness_jobs_boolean_insert_check", "api_harness_jobs_boolean_update_check",
            "workflow_profiles_boolean_insert_check", "workflow_profiles_boolean_update_check",
        } <= triggers
        with pytest.raises(sqlite3.IntegrityError, match="invalid application-setting boolean"):
            connection.execute("INSERT INTO app_settings(emr_api_enabled) VALUES(2)")


def test_all_admin_and_office_manager_users_receive_default_facility_mapping(tmp_path) -> None:
    # Given: legacy admin and manager users.
    database_path = create_legacy_database(tmp_path)

    # When: roles and facilities are migrated.
    run_migrations(MigrationRequest(database_path, tmp_path, SYNTHETIC_SECRET, "test-build"))

    # Then: both canonical roles are assigned to the default facility.
    with closing(sqlite3.connect(database_path)) as connection:
        mapped = connection.execute(
            """SELECT u.role FROM user_facilities uf JOIN users u ON u.id=uf.user_id
            JOIN facilities f ON f.id=uf.facility_id WHERE f.facility_key='r3-default' ORDER BY u.role"""
        ).fetchall()
    assert mapped == [("admin",), ("office_manager",)]


def _fernet() -> Fernet:
    digest = hashlib.sha256(SYNTHETIC_SECRET.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _decrypt_legacy_text(stored: str) -> dict[str, JsonValue]:
    framed = base64.urlsafe_b64decode(stored[7:].encode("ascii"))
    return json.loads(_fernet().decrypt(framed[7:]))


def _decrypt_snapshot(stored: bytes) -> dict[str, JsonValue]:
    return json.loads(_fernet().decrypt(stored[7:]))


def _sqlite_storage_bytes(connection: sqlite3.Connection) -> tuple[bytes, ...]:
    tables = tuple(
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    )
    values: list[bytes] = []
    for table in tables:
        quoted = table.replace('"', '""')
        for row in connection.execute(f'SELECT * FROM "{quoted}"'):
            values.extend(_stored_bytes(value) for value in row if isinstance(value, (str, bytes)))
    return tuple(values)


def _stored_bytes(value: str | bytes) -> bytes:
    return value if isinstance(value, bytes) else value.encode("utf-8")
