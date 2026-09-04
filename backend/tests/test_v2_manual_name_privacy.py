from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from v2_test_runtime import fresh_client

NAME_SENTINEL: Final = "SYNTHETIC-NAME-PRIVATE-STORE-5913"
MRN: Final = "META-PRIVATE"
CAPTURED_AT: Final = "2026-09-03T12:00:00+00:00"


@pytest.fixture
def metadata_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Session, Path]]:
    fresh_client(tmp_path, monkeypatch)
    from app.core.config import settings
    from app.v2.db import SessionLocal

    with SessionLocal() as db:
        facility_id = db.execute(text("SELECT id FROM facilities WHERE facility_key='r3-default'")).scalar_one()
        db.execute(text(
            "INSERT INTO facilities(id,facility_key,display_name,timezone,is_active,created_at,updated_at) "
            "VALUES(902,'metadata-test-902','Synthetic facility','UTC',1,:now,:now)"
        ), {"now": CAPTURED_AT})
        for row_id, source, source_id, facility in (
            (501, "manual_upload", "SOURCE-A", facility_id),
            (502, "manual_upload", "SOURCE-B", 902),
            (503, "alleva_rest_api", "SOURCE-A", facility_id),
        ):
            db.execute(text(
                "INSERT INTO patients(id,facility_id,canonical_client_id,source_system,source_patient_id,"
                "lifecycle_state,first_seen_at,last_seen_at) VALUES(:id,:facility,:mrn,:source,:source_id,'active',:now,:now)"
            ), {"id": row_id, "facility": facility, "mrn": MRN, "source": source, "source_id": source_id, "now": CAPTURED_AT})
        db.commit()
        yield db, settings.local_app_data_dir


def test_manual_name_is_encrypted_and_exact_row_roundtrip_is_private(metadata_database, caplog: pytest.LogCaptureFixture) -> None:
    # Given: two facilities and two sources have colliding MRNs.
    db, root = metadata_database
    from app.v2.services import manual_patient_snapshot as names
    from app.v2.services import patient_snapshot_store as snapshots

    # When: an explicit name is persisted against the exact authorized manual patient row.
    created = names.persist_manual_patient_name(db, names.ManualPatientNameInput(502, MRN, NAME_SENTINEL), CAPTURED_AT)
    db.commit()
    recovered = snapshots.patient_source_snapshot_for_record(db, 502, "manual_upload")

    # Then: only that row decrypts the name, while stored bytes, audit, labels and logs exclude it.
    assert created == 1
    assert recovered is not None and recovered.full_name == NAME_SENTINEL
    assert snapshots.patient_source_snapshot_for_record(db, 501, "manual_upload") is None
    assert snapshots.patient_source_snapshot_for_record(db, 503, "manual_upload") is None
    rows = db.execute(text("SELECT patient_id,source_system,source_record_id,snapshot_encrypted FROM patient_snapshot_versions")).all()
    assert [(row[0], row[1], row[2]) for row in rows] == [(502, "manual_upload", "SOURCE-B")]
    assert bytes(rows[0][3]).startswith(b"IZCNA1:")
    assert NAME_SENTINEL not in str(db.execute(text("SELECT details FROM audit_logs")).all())
    assert NAME_SENTINEL not in caplog.text
    assert all(NAME_SENTINEL.encode() not in path.read_bytes() for path in root.rglob("*") if path.is_file())


def test_omitted_name_preserves_existing_snapshot_bytes(metadata_database) -> None:
    # Given: an encrypted manual name snapshot already exists.
    db, _ = metadata_database
    from app.v2.services import manual_patient_snapshot as names
    from app.v2.services import patient_snapshot_store as snapshots

    names.persist_manual_patient_name(db, names.ManualPatientNameInput(501, MRN, NAME_SENTINEL), CAPTURED_AT)
    db.commit()
    original = db.execute(text("SELECT snapshot_encrypted FROM patient_snapshot_versions")).scalar_one()

    # When: a later import omits the name entirely.
    created = names.persist_manual_patient_name(db, names.ManualPatientNameInput(501, MRN, ""), CAPTURED_AT)
    db.commit()

    # Then: omission neither erases nor appends or rewrites the authorized snapshot.
    recovered = snapshots.patient_source_snapshot_for_record(db, 501, "manual_upload")
    assert created == 0
    assert recovered is not None and recovered.full_name == NAME_SENTINEL
    stored = db.execute(text("SELECT snapshot_encrypted FROM patient_snapshot_versions")).scalar_one()
    assert hashlib.sha256(stored).digest() == hashlib.sha256(original).digest()


@pytest.mark.parametrize("row_id,patient_id", [(999, MRN), (503, MRN), (501, "WRONG-MRN")])
def test_manual_name_write_rejects_wrong_row_source_or_mrn(metadata_database, row_id: int, patient_id: str) -> None:
    # Given: caller selectors do not identify the same manual patient row.
    db, _ = metadata_database
    from app.v2.services import manual_patient_snapshot as names

    # When: the helper is given a missing row, non-manual source or mismatched MRN.
    with pytest.raises(HTTPException) as error:
        names.persist_manual_patient_name(db, names.ManualPatientNameInput(row_id, patient_id, NAME_SENTINEL), CAPTURED_AT)

    # Then: the helper fails safely before creating any snapshot.
    assert error.value.status_code == 404
    assert NAME_SENTINEL not in str(error.value)
    assert db.execute(text("SELECT COUNT(*) FROM patient_snapshot_versions")).scalar_one() == 0


def test_changed_name_can_restore_prior_value_without_mutating_history(metadata_database) -> None:
    # Given: two successive explicit names exist and their encrypted history is immutable.
    db, _ = metadata_database
    from app.v2.services import manual_patient_snapshot as names
    from app.v2.services import patient_snapshot_store as snapshots

    names.persist_manual_patient_name(db, names.ManualPatientNameInput(501, MRN, NAME_SENTINEL), CAPTURED_AT)
    names.persist_manual_patient_name(db, names.ManualPatientNameInput(501, MRN, "SYNTHETIC-OTHER-NAME"), CAPTURED_AT)
    original_rows = db.execute(text("SELECT id,snapshot_encrypted FROM patient_snapshot_versions ORDER BY id")).all()

    # When: an explicit correction restores the original spelling at the same capture time.
    created = names.persist_manual_patient_name(db, names.ManualPatientNameInput(501, MRN, NAME_SENTINEL), CAPTURED_AT)
    db.commit()

    # Then: a new latest snapshot is appended and neither existing encrypted version is rewritten.
    recovered = snapshots.patient_source_snapshot_for_record(db, 501, "manual_upload")
    assert created == 1
    assert recovered is not None and recovered.full_name == NAME_SENTINEL and recovered.version_ordinal == 3
    assert db.execute(text("SELECT id,snapshot_encrypted FROM patient_snapshot_versions ORDER BY id LIMIT 2")).all() == original_rows


def test_repeated_identical_name_is_idempotent(metadata_database) -> None:
    # Given: the currently authorized encrypted snapshot already has the supplied name.
    db, _ = metadata_database
    from app.v2.services import manual_patient_snapshot as names

    names.persist_manual_patient_name(db, names.ManualPatientNameInput(501, MRN, NAME_SENTINEL), CAPTURED_AT)

    # When: that same name is supplied again.
    created = names.persist_manual_patient_name(db, names.ManualPatientNameInput(501, MRN, NAME_SENTINEL), CAPTURED_AT)

    # Then: duplicate import does not create redundant history.
    assert created == 0
    assert db.execute(text("SELECT COUNT(*) FROM patient_snapshot_versions")).scalar_one() == 1
