from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.v2.domain.schemas import JsonValue, TreatmentPlanAggregate
from app.v2.services.clinical_snapshot_codec import ClinicalSnapshotCodec
from app.v2.services.alleva_contracts import SyncImportProvenance
from app.v2.services.secure_storage import encrypt_bytes


@dataclass(frozen=True, slots=True)
class ClinicalEvidenceEvents:
    loc_change: bool
    new_review: bool


def persist_clinical_evidence(
    db: Session,
    aggregate: TreatmentPlanAggregate,
    patient_row_id: int,
    plan_version_id: int,
    recorded_at: str,
    sync_provenance: SyncImportProvenance | None = None,
) -> ClinicalEvidenceEvents:
    had_loc_evidence = bool(db.execute(
        text("SELECT 1 FROM loc_history WHERE patient_id=:patient_id LIMIT 1"),
        {"patient_id": patient_row_id},
    ).first())
    loc_insertions = _persist_loc_history(db, aggregate, patient_row_id, recorded_at)
    review_insertions = _persist_reviews(db, aggregate, patient_row_id, recorded_at, sync_provenance)
    _persist_diagnoses(db, aggregate, plan_version_id, recorded_at, sync_provenance)
    return ClinicalEvidenceEvents(
        loc_change=loc_insertions > 1 or (had_loc_evidence and loc_insertions > 0),
        new_review=review_insertions > 0,
    )


def _persist_loc_history(
    db: Session,
    aggregate: TreatmentPlanAggregate,
    patient_row_id: int,
    recorded_at: str,
) -> int:
    inserted = 0
    for ordinal, row in enumerate(aggregate.loc_history, start=1):
        loc_code = _text(row, "level_of_care", "loc_code")
        effective_date = _text(row, "effective_date")
        if not loc_code or not effective_date:
            continue
        canonical = _canonical(row)
        evidence_sha256 = hashlib.sha256(canonical).hexdigest()
        source_id = _source_id(row, f"loc-{ordinal}-{evidence_sha256[:12]}")
        result = db.execute(
            text(
                "INSERT OR IGNORE INTO loc_history(patient_id,loc_code,source_system,source_record_id,effective_date,"
                "recorded_at,reconciliation_state,evidence_sha256) VALUES(:patient_id,:loc_code,:source_system,"
                ":source_record_id,:effective_date,:recorded_at,'observed',:evidence_sha256)"
            ),
            {
                "patient_id": patient_row_id, "loc_code": loc_code, "source_system": aggregate.source_mode,
                "source_record_id": source_id, "effective_date": effective_date,
                "recorded_at": recorded_at, "evidence_sha256": evidence_sha256,
            },
        )
        inserted += max(result.rowcount, 0)
    return inserted


def _persist_reviews(
    db: Session,
    aggregate: TreatmentPlanAggregate,
    patient_row_id: int,
    imported_at: str,
    sync_provenance: SyncImportProvenance | None,
) -> int:
    latest = db.execute(
        text(
            "SELECT id,version_ordinal FROM treatment_review_versions WHERE patient_id=:patient_id "
            "ORDER BY version_ordinal DESC,id DESC LIMIT 1"
        ),
        {"patient_id": patient_row_id},
    ).first()
    previous_id = int(latest[0]) if latest else None
    ordinal = int(latest[1]) + 1 if latest else 1
    codec = ClinicalSnapshotCodec(settings.effective_data_encryption_secret)
    inserted = 0
    for row in aggregate.treatment_reviews:
        canonical = _canonical(row)
        content_sha256 = hashlib.sha256(canonical).hexdigest()
        source_id = _source_id(row, f"review-{content_sha256[:12]}")
        evidence_sha256 = hashlib.sha256(
            f"{aggregate.patient_id}:{aggregate.source_mode}:{source_id}:{content_sha256}".encode("utf-8")
        ).hexdigest()
        result = db.execute(
            text(
                """INSERT OR IGNORE INTO treatment_review_versions(
                    patient_id,source_system,source_record_id,version_ordinal,review_date,signature_date,
                    normalized_snapshot_encrypted,content_sha256,evidence_sha256,imported_at,supersedes_version_id,
                    sync_job_id,approval_record_id,contract_version,contract_sha256
                ) VALUES(:patient_id,:source_system,:source_record_id,:ordinal,:review_date,:signature_date,
                    :snapshot,:content_sha256,:evidence_sha256,:imported_at,:supersedes_version_id,
                    :sync_job_id,:approval_record_id,:contract_version,:contract_sha256)"""
            ),
            {
                "patient_id": patient_row_id, "source_system": aggregate.source_mode, "source_record_id": source_id,
                "ordinal": ordinal, "review_date": _text(row, "review_date", "reviewDate") or None,
                "signature_date": _text(row, "signature_date", "signatureDate") or None,
                "snapshot": codec.encode_review(row), "content_sha256": content_sha256,
                "evidence_sha256": evidence_sha256, "imported_at": imported_at,
                "supersedes_version_id": previous_id,
                **_provenance_values(sync_provenance),
            },
        )
        if result.rowcount == 1:
            inserted += 1
            previous_id = int(result.lastrowid)
            ordinal += 1
    return inserted


def _persist_diagnoses(
    db: Session,
    aggregate: TreatmentPlanAggregate,
    plan_version_id: int,
    captured_at: str,
    sync_provenance: SyncImportProvenance | None,
) -> None:
    snapshot = aggregate.content_snapshot.model_dump(mode="json")
    diagnoses = [
        diagnosis
        for problem in snapshot.get("problems", [])
        if isinstance(problem, dict)
        for diagnosis in problem.get("diagnoses", [])
        if isinstance(diagnosis, dict)
    ]
    for ordinal, diagnosis in enumerate(diagnoses, start=1):
        if not isinstance(diagnosis, dict):
            continue
        canonical = _canonical(diagnosis)
        content_sha256 = hashlib.sha256(canonical).hexdigest()
        source_id = _source_id(diagnosis, f"diagnosis-{ordinal}-{content_sha256[:12]}")
        db.execute(
            text(
                """INSERT OR IGNORE INTO diagnosis_snapshots(
                    plan_version_id,review_version_id,source_record_id,normalized_snapshot_encrypted,content_sha256,captured_at,
                    sync_job_id,approval_record_id,contract_version,contract_sha256
                ) VALUES(:plan_version_id,NULL,:source_record_id,:snapshot,:content_sha256,:captured_at,
                    :sync_job_id,:approval_record_id,:contract_version,:contract_sha256)"""
            ),
            {
                "plan_version_id": plan_version_id,
                "source_record_id": source_id,
                "snapshot": encrypt_bytes(canonical),
                "content_sha256": content_sha256,
                "captured_at": captured_at,
                **_provenance_values(sync_provenance),
            },
        )


def _canonical(record: dict[str, JsonValue]) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _source_id(record: dict[str, JsonValue], fallback: str) -> str:
    value = _text(record, "source_record_id", "id")
    return value[:160] if value else fallback


def _text(record: dict[str, JsonValue], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, (str, int, float, bool)):
            return str(value).strip()
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
