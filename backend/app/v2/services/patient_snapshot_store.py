from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json

from fastapi import HTTPException
from pydantic import JsonValue, TypeAdapter, ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.v2.services.alleva_contracts import SyncImportProvenance
from app.v2.services.secure_storage import decrypt_bytes, encrypt_bytes


PATIENT_RECORD_ADAPTER = TypeAdapter(dict[str, JsonValue])


@dataclass(frozen=True, slots=True)
class PatientSourceSnapshotInput:
    mrn: str
    source_patient_id: str
    source_system: str
    source_last_updated: str
    record: dict[str, object]


@dataclass(frozen=True, slots=True)
class PatientSourceSnapshot:
    snapshot_id: int
    version_ordinal: int
    patient_key: str
    source_system: str
    full_name: str
    source_last_updated: str
    record: dict[str, JsonValue]


def persist_patient_source_snapshots(
    db: Session,
    snapshots: tuple[PatientSourceSnapshotInput, ...],
    captured_at: str,
    provenance: SyncImportProvenance | None = None,
) -> int:
    created_count = 0
    for snapshot in snapshots:
        patient_row = db.execute(
            text(
                "SELECT id,source_patient_id FROM patients "
                "WHERE canonical_client_id=:mrn AND source_system=:source_system ORDER BY id LIMIT 1"
            ),
            {"mrn": snapshot.mrn, "source_system": snapshot.source_system},
        ).first()
        if patient_row is None:
            continue
        stored_source_patient_id = str(patient_row[1] or "")
        if stored_source_patient_id and stored_source_patient_id != snapshot.source_patient_id:
            continue
        canonical = _canonical_record(snapshot.record)
        content_sha256 = hashlib.sha256(canonical).hexdigest()
        patient_row_id = int(patient_row[0])
        existing = db.execute(
            text(
                "SELECT id FROM patient_snapshot_versions "
                "WHERE patient_id=:patient_id AND source_system=:source_system "
                "AND source_record_id=:source_record_id AND content_sha256=:content_sha256 LIMIT 1"
            ),
            {
                "patient_id": patient_row_id,
                "source_system": snapshot.source_system,
                "source_record_id": snapshot.source_patient_id,
                "content_sha256": content_sha256,
            },
        ).first()
        if existing is not None:
            continue
        latest = db.execute(
            text(
                "SELECT id,version_ordinal FROM patient_snapshot_versions "
                "WHERE patient_id=:patient_id ORDER BY version_ordinal DESC,id DESC LIMIT 1"
            ),
            {"patient_id": patient_row_id},
        ).first()
        db.execute(
            text(
                """INSERT INTO patient_snapshot_versions(
                    patient_id,source_system,source_record_id,version_ordinal,source_last_updated,
                    snapshot_schema_version,snapshot_encrypted,content_sha256,captured_at,supersedes_snapshot_id,
                    sync_job_id,approval_record_id,contract_version,contract_sha256
                ) VALUES(
                    :patient_id,:source_system,:source_record_id,:version_ordinal,:source_last_updated,
                    1,:encrypted_snapshot,:content_sha256,:captured_at,:supersedes_snapshot_id,
                    :sync_job_id,:approval_record_id,:contract_version,:contract_sha256
                )"""
            ),
            {
                "patient_id": patient_row_id,
                "source_system": snapshot.source_system,
                "source_record_id": snapshot.source_patient_id,
                "version_ordinal": int(latest[1]) + 1 if latest else 1,
                "encrypted_snapshot": encrypt_bytes(canonical),
                "content_sha256": content_sha256,
                "source_last_updated": snapshot.source_last_updated,
                "captured_at": captured_at,
                "supersedes_snapshot_id": int(latest[0]) if latest else None,
                **_provenance_values(provenance),
            },
        )
        created_count += 1
    db.flush()
    return created_count


def latest_patient_source_snapshots(db: Session) -> dict[tuple[str, str], PatientSourceSnapshot]:
    rows = db.execute(
        text(
            "SELECT s.id,s.version_ordinal,p.canonical_client_id,s.source_system,s.snapshot_encrypted,"
            "s.content_sha256,s.source_last_updated FROM patient_snapshot_versions s "
            "JOIN patients p ON p.id=s.patient_id "
            "WHERE s.id=(SELECT latest.id FROM patient_snapshot_versions latest "
            "WHERE latest.patient_id=s.patient_id ORDER BY latest.version_ordinal DESC,latest.id DESC LIMIT 1)"
        )
    ).all()
    snapshots = (_snapshot_from_row(row) for row in rows)
    return {(snapshot.patient_key, snapshot.source_system): snapshot for snapshot in snapshots}


def latest_patient_source_snapshot(
    db: Session,
    patient_key: str,
    source_system: str | None = None,
) -> PatientSourceSnapshot | None:
    snapshots = latest_patient_source_snapshots(db)
    if source_system is not None:
        return snapshots.get((patient_key, source_system))
    return next(
        (snapshot for key, snapshot in snapshots.items() if key[0] == patient_key),
        None,
    )


def patient_full_name(record: Mapping[str, object]) -> str:
    preferred = _first_text(
        record,
        (
            "fullName", "clientName", "displayName", "name",
            "name.fullName", "name.clientName", "name.displayName",
        ),
    )
    if preferred:
        return preferred
    first = _first_text(record, ("name.legalFirstName", "name.firstName", "name.first", "legalFirstName", "firstName", "first_name"))
    middle = _first_text(record, ("name.middleName", "name.middle", "middleName", "middle_name"))
    last = _first_text(record, ("name.legalLastName", "name.lastName", "name.last", "legalLastName", "lastName", "last_name"))
    suffix = _first_text(record, ("name.suffix", "suffix"))
    assembled = " ".join(value for value in (first, middle, last, suffix) if value)
    if assembled:
        return assembled
    return "Name unavailable"


def patient_current_level_of_care(record: Mapping[str, object]) -> str:
    return _first_text(
        record,
        (
            "levelOfCare.name", "levelOfCare.displayName", "levelOfCare",
            "currentLevelOfCare.name", "currentLevelOfCare", "level_of_care",
        ),
    )


def _snapshot_from_row(row: Sequence[object]) -> PatientSourceSnapshot:
    values = tuple(row)
    encrypted = bytes(values[4])
    canonical = decrypt_bytes(encrypted)
    if hashlib.sha256(canonical).hexdigest() != str(values[5]):
        raise HTTPException(status_code=500, detail="Stored patient snapshot failed integrity verification")
    try:
        record = PATIENT_RECORD_ADAPTER.validate_json(canonical)
    except ValidationError as exc:
        raise HTTPException(status_code=500, detail="Stored patient snapshot is invalid") from exc
    return PatientSourceSnapshot(
        snapshot_id=int(values[0]),
        version_ordinal=int(values[1]),
        patient_key=str(values[2]),
        source_system=str(values[3]),
        full_name=patient_full_name(record),
        source_last_updated=str(values[6] or ""),
        record=record,
    )


def _canonical_record(record: dict[str, object]) -> bytes:
    try:
        validated = PATIENT_RECORD_ADAPTER.validate_python(record)
    except ValidationError as exc:
        raise ValueError("Alleva patient record is not valid JSON") from exc
    return json.dumps(validated, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _first_text(record: Mapping[str, object], paths: tuple[str, ...]) -> str:
    for path in paths:
        value: object = record
        for part in path.split("."):
            if not isinstance(value, Mapping):
                value = None
                break
            value = value.get(part)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
    return ""


def _provenance_values(provenance: SyncImportProvenance | None) -> dict[str, int | str | None]:
    if provenance is None:
        return {"sync_job_id": None, "approval_record_id": None, "contract_version": None, "contract_sha256": None}
    return {
        "sync_job_id": provenance.sync_job_id,
        "approval_record_id": provenance.approval_record_id,
        "contract_version": provenance.contract_version,
        "contract_sha256": provenance.contract_sha256,
    }
