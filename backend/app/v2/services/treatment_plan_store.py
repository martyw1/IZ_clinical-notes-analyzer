from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.v2.domain.schemas import TreatmentPlanAggregate
from app.v2.models import TreatmentPlanImport, User, utc_now
from app.v2.services.manager_action_store import manager_override_dicts_for_patient, manager_review_dicts_for_patient
from app.v2.services.manual_source_file_store import source_documents_for_patient
from app.v2.services.secure_storage import decrypt_text_secret, encrypt_text_secret

TREATMENT_PLAN_STATUS_ORDER: Final = (
    "Missing Data",
    "Needs Review",
    "Incomplete",
    "Within Window",
    "Late",
    "Conflicting Evidence",
    "Unable to Evaluate",
)


@dataclass(frozen=True, slots=True)
class TreatmentPlanQueueItem:
    patient_id: str
    patient_display_label: str
    current_level_of_care: str
    admission_date: str
    next_due_date: str
    status: str
    missing_criteria_count: int
    returned_criteria_count: int
    source_mode: str
    content_completeness_summary: dict[str, int]
    warnings: tuple[str, ...]


def list_treatment_plan_imports(db: Session) -> tuple[TreatmentPlanImport, ...]:
    result = db.execute(select(TreatmentPlanImport).order_by(TreatmentPlanImport.updated_at.desc()))
    return tuple(result.scalars().all())


def list_treatment_plan_queue_items(db: Session) -> tuple[TreatmentPlanQueueItem, ...]:
    return tuple(_queue_item_from_import(row) for row in list_treatment_plan_imports(db))


def save_treatment_plan_aggregate(db: Session, aggregate: TreatmentPlanAggregate, actor: User) -> TreatmentPlanImport:
    encrypted_payload = encrypt_text_secret(aggregate.model_dump_json())
    existing = db.execute(select(TreatmentPlanImport).where(TreatmentPlanImport.patient_id == aggregate.patient_id)).scalar_one_or_none()
    row = existing or TreatmentPlanImport(patient_id=aggregate.patient_id, encrypted_payload=encrypted_payload)
    row.patient_display_label = aggregate.patient_display_label
    row.plan_id = aggregate.content_snapshot.plan_id
    row.source_mode = aggregate.source_mode
    row.current_level_of_care = aggregate.current_level_of_care
    row.admission_date = aggregate.admission_date
    row.next_due_date = aggregate.date_clock_due_date
    row.overall_status = aggregate.overall_status
    row.missing_criteria_count = aggregate.evidence_coverage_summary.criteria_missing_evidence
    row.returned_criteria_count = _returned_criteria_count(aggregate)
    row.content_summary_json = _content_summary_json(aggregate)
    row.warnings_json = json.dumps(list(aggregate.data_quality_warnings), sort_keys=True)
    row.content_hash = aggregate.content_snapshot.content_hash
    row.encrypted_payload = encrypted_payload
    row.created_by_user_id = str(actor.id)
    row.updated_at = utc_now()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def treatment_plan_aggregate_for_patient(db: Session, patient_id: str) -> TreatmentPlanAggregate | None:
    row = db.execute(select(TreatmentPlanImport).where(TreatmentPlanImport.patient_id == patient_id)).scalar_one_or_none()
    if row is None:
        return None
    aggregate = TreatmentPlanAggregate.model_validate_json(decrypt_text_secret(row.encrypted_payload))
    source_documents = source_documents_for_patient(db, patient_id)
    persisted_reviews = manager_review_dicts_for_patient(db, patient_id)
    if not persisted_reviews and not source_documents:
        return aggregate
    return aggregate.model_copy(
        update={
            "manager_reviews": aggregate.manager_reviews + persisted_reviews,
            "overrides": aggregate.overrides + manager_override_dicts_for_patient(db, patient_id),
            "source_documents": source_documents,
        }
    )


def _queue_item_from_import(row: TreatmentPlanImport) -> TreatmentPlanQueueItem:
    return TreatmentPlanQueueItem(
        patient_id=row.patient_id,
        patient_display_label=row.patient_display_label,
        current_level_of_care=row.current_level_of_care,
        admission_date=row.admission_date,
        next_due_date=row.next_due_date,
        status=row.overall_status,
        missing_criteria_count=row.missing_criteria_count,
        returned_criteria_count=row.returned_criteria_count,
        source_mode=row.source_mode,
        content_completeness_summary=_int_map(row.content_summary_json),
        warnings=_string_tuple(row.warnings_json),
    )


def _returned_criteria_count(aggregate: TreatmentPlanAggregate) -> int:
    return sum(1 for review in aggregate.manager_reviews if review.get("manager_status") == "Returned")


def _content_summary_json(aggregate: TreatmentPlanAggregate) -> str:
    summary = {
        key: value
        for key, value in aggregate.content_snapshot_summary.items()
        if isinstance(value, int)
    }
    return json.dumps(summary, sort_keys=True)


def _int_map(raw_json: str) -> dict[str, int]:
    payload = json.loads(raw_json or "{}")
    if not isinstance(payload, dict):
        return {}
    return {str(key): value for key, value in payload.items() if isinstance(value, int)}


def _string_tuple(raw_json: str) -> tuple[str, ...]:
    payload = json.loads(raw_json or "[]")
    if not isinstance(payload, list):
        return ()
    return tuple(value for value in payload if isinstance(value, str))
