from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.v2.services.patient_snapshot_store import (
    PatientSourceSnapshotInput,
    patient_source_snapshot_for_record,
    persist_patient_source_snapshots,
)


@dataclass(frozen=True, slots=True)
class ManualPatientNameInput:
    patient_record_id: int
    patient_id: str
    full_name: str


def persist_manual_patient_name(db: Session, entry: ManualPatientNameInput, captured_at: str) -> int:
    """Append an encrypted explicit name within the caller's authorized import transaction; omission is a no-op."""
    row = db.execute(
        text(
            "SELECT source_patient_id FROM patients WHERE id=:patient_record_id "
            "AND canonical_client_id=:mrn AND source_system='manual_upload'"
        ),
        {"patient_record_id": entry.patient_record_id, "mrn": entry.patient_id},
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Manual patient record not found")
    full_name = " ".join(entry.full_name.split())
    if not full_name:
        return 0
    latest = patient_source_snapshot_for_record(db, entry.patient_record_id, "manual_upload")
    if latest is not None and latest.full_name == full_name:
        return 0
    snapshot = PatientSourceSnapshotInput(
        mrn=entry.patient_id,
        source_patient_id=str(row[0] or entry.patient_id),
        source_system="manual_upload",
        source_last_updated="",
        record={"patient_full_name": full_name, "manual_name_revision": latest.version_ordinal + 1 if latest else 1},
        patient_record_id=entry.patient_record_id,
    )
    return persist_patient_source_snapshots(db, (snapshot,), captured_at)
