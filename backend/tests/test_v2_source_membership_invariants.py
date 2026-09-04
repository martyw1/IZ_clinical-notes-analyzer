from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from app.v2.migrations import runner
from app.v2.migrations.errors import MigrationStateError
from app.v2.migrations.schema_verifier import verify_database
from test_v2_source_membership_migration import _history_fingerprint, _request, version_eleven


@pytest.mark.parametrize("unassociated", ["null", "review_only", "cross_row", "plan_source", "document_kind"])
def test_backfill_retains_unassociated_originals_without_guessing(version_eleven: Path, unassociated: str, record_property) -> None:
    # Given: one eligible original plus a valid but non-authoritative original association.
    with closing(sqlite3.connect(version_eleven)) as db:
        patient = 1
        plan: int | None = 1
        review: int | None = None
        kind = "manual_treatment_plan_file"
        if unassociated in {"null", "review_only"}:
            plan = None
            review = 1 if unassociated == "review_only" else None
        elif unassociated == "cross_row":
            patient = db.execute("INSERT INTO patients(facility_id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at) "
                "SELECT facility_id,'synthetic-other','manual_upload','active',first_seen_at,last_seen_at FROM patients LIMIT 1").lastrowid
        elif unassociated == "plan_source":
            plan = db.execute("INSERT INTO treatment_plan_versions(patient_id,source_system,source_record_id,version_ordinal,"
                "normalized_snapshot_encrypted,content_sha256,evidence_sha256,imported_at) "
                "SELECT patient_id,'alleva_rest_api','synthetic-other-source',99,normalized_snapshot_encrypted,'other-hash',evidence_sha256,imported_at "
                "FROM treatment_plan_versions LIMIT 1").lastrowid
        else:
            kind = "synthetic-unassociated-kind"
        db.execute("INSERT INTO source_documents(patient_id,plan_version_id,review_version_id,document_id,source_kind,source_format,"
            "content_type,size_bytes,sha256,encrypted_relative_path,created_by_user_id,created_at) "
            "SELECT ?,?,?, 'synthetic-unassociated',?,source_format,content_type,size_bytes,'unassociated-hash',"
            "encrypted_relative_path,created_by_user_id,created_at FROM source_documents LIMIT 1", (patient, plan, review, kind))
        db.commit()
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        original_checksums = db.execute("SELECT version,checksum_sha256 FROM schema_migrations ORDER BY version").fetchall()
    before = _history_fingerprint(version_eleven)
    # When: the real v12 migration backfills only eligible original pairs.
    runner.run_migrations(_request(version_eleven))
    # Then: unassociated rows and ciphertext snapshots survive unchanged and migrations 1–11 retain checksums.
    after = _history_fingerprint(version_eleven)
    assert before == after
    with closing(sqlite3.connect(version_eleven)) as db:
        assert db.execute("SELECT source_document_id,plan_version_id FROM source_document_plan_memberships").fetchall() == [(1, 1)]
        assert db.execute("SELECT version,checksum_sha256 FROM schema_migrations WHERE version<=11 ORDER BY version").fetchall() == original_checksums
        if unassociated in {"cross_row", "plan_source", "document_kind"}:
            with pytest.raises(sqlite3.IntegrityError, match="exact manual patient version"):
                db.execute("INSERT INTO source_document_plan_memberships(source_document_id,plan_version_id,attached_at) VALUES(2,?,'2026-09-04')", (plan,))
    record_property("history_before_sha256", before)
    record_property("history_after_sha256", after)
    verify_database(version_eleven, 12)


def test_broken_original_foreign_key_remains_a_hard_failure(version_eleven: Path) -> None:
    # Given: a source FK that names a genuinely nonexistent parent, not a safe unassociated original.
    with closing(sqlite3.connect(version_eleven)) as db:
        db.execute("UPDATE source_documents SET plan_version_id=999999")
        db.commit()
    before = version_eleven.read_bytes()
    # When: v11 verification and the current upgrader inspect that damaged database.
    with pytest.raises(MigrationStateError):
        verify_database(version_eleven, 11)
    with pytest.raises(MigrationStateError):
        runner.run_migrations(_request(version_eleven))
    # Then: no guessed reparenting changes the original database.
    assert version_eleven.read_bytes() == before


@pytest.mark.parametrize("assignment", [
    "plan_version_id=2", "patient_id=999999", "review_version_id=1", "document_id='reassigned'",
    "source_kind='other'", "sha256='changed'", "encrypted_relative_path='other/path'",
    "created_at='changed'", "created_by_user_id=2",
])
def test_membership_protects_original_source_provenance(version_eleven: Path, assignment: str) -> None:
    # Given: a protected original archive and its v12 association.
    runner.run_migrations(_request(version_eleven))
    with closing(sqlite3.connect(version_eleven)) as db:
        before = db.execute("SELECT * FROM source_documents").fetchall()
        # When: a direct parent update attempts to move protected provenance.
        with pytest.raises(sqlite3.IntegrityError, match="linked source provenance"):
            db.execute(f"UPDATE source_documents SET {assignment}")
        # Then: source identity/provenance remains byte-for-byte unchanged.
        assert db.execute("SELECT * FROM source_documents").fetchall() == before


@pytest.mark.parametrize("assignment", ["source_document_id=999999", "plan_version_id=2", "attached_at='changed'",
                                        "attached_by_user_id=2", "detached_at='partial'"])
def test_membership_rejects_key_provenance_and_partial_tombstone_updates(version_eleven: Path, assignment: str) -> None:
    # Given: an original exact association.
    runner.run_migrations(_request(version_eleven))
    with closing(sqlite3.connect(version_eleven)) as db:
        before = db.execute("SELECT * FROM source_document_plan_memberships").fetchall()
        # When: a direct update attempts a key/provenance move or inconsistent tombstone.
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(f"UPDATE source_document_plan_memberships SET {assignment}")
        # Then: the exact association and initial attachment provenance survive.
        assert db.execute("SELECT * FROM source_document_plan_memberships").fetchall() == before


def test_source_guard_does_not_freeze_unrelated_archive_metadata(version_eleven: Path) -> None:
    # Given: the narrow provenance guard on an associated archive.
    runner.run_migrations(_request(version_eleven))
    with closing(sqlite3.connect(version_eleven)) as db:
        # When: unrelated descriptive metadata changes without source identity or association changes.
        db.execute("UPDATE source_documents SET content_type='application/octet-stream'")
        db.commit()
    # Then: the supported metadata update remains valid and memberships still verify.
    verify_database(version_eleven, 12)
