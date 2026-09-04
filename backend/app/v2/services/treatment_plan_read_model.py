from __future__ import annotations

import json
from dataclasses import dataclass, replace

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.v2.domain.schemas import SourceMode, TreatmentPlanAggregate
from app.v2.services.evaluation_store import evaluated_plan_version
from app.v2.services.manual_source_file_store import source_documents_for_version
from app.v2.services.patient_snapshot_store import patient_source_snapshot_for_record
from app.v2.services.treatment_plan_types import PlanVersionIdentity, StoredTreatmentPlan, TreatmentPlanQueueItem, stored_plan


@dataclass(frozen=True, slots=True)
class TreatmentPlanQuery:
    source_mode: SourceMode | None = None
    patient_record_id: int | None = None
    treatment_plan_id: str | None = None
    include_history: bool = False
    plan_version_ids: frozenset[int] | None = None


class PlanVersionHeader(BaseModel):
    model_config = ConfigDict(frozen=True)
    plan_version_id: int = Field(gt=0)
    patient_record_id: int = Field(gt=0)
    patient_id: str
    source_mode: SourceMode
    treatment_plan_id: str
    imported_at: str
    plan_date: str | None
    version_ordinal: int = Field(gt=0)
    is_current: bool

    def identity(self) -> PlanVersionIdentity:
        return PlanVersionIdentity(self.plan_version_id, self.patient_record_id, self.patient_id,
                                   self.source_mode, self.treatment_plan_id)


def list_treatment_plan_imports(
    db: Session, allowed_patient_record_ids: frozenset[int] | None = None,
    query: TreatmentPlanQuery = TreatmentPlanQuery(),
) -> tuple[StoredTreatmentPlan, ...]:
    rows = db.execute(text(
        "SELECT p.canonical_client_id AS patient_id,v.source_record_id AS treatment_plan_id,"
        "v.source_system AS source_mode,v.imported_at,v.id AS plan_version_id,v.plan_date,"
        "p.id AS patient_record_id,v.version_ordinal,NOT EXISTS (SELECT 1 FROM treatment_plan_versions newer "
        "WHERE newer.patient_id=v.patient_id AND newer.source_system=v.source_system "
        "AND newer.source_record_id=v.source_record_id AND newer.version_ordinal>v.version_ordinal) AS is_current "
        "FROM patients p JOIN treatment_plan_versions v ON v.patient_id=p.id "
        "WHERE (:source IS NULL OR v.source_system=:source) AND (:patient IS NULL OR p.id=:patient) "
        "AND (:plan IS NULL OR v.source_record_id=:plan) ORDER BY v.imported_at DESC,v.id DESC"
    ), {"source": query.source_mode, "patient": query.patient_record_id, "plan": query.treatment_plan_id}).all()
    result: list[StoredTreatmentPlan] = []
    for row in rows:
        header = PlanVersionHeader.model_validate(row._mapping)
        if allowed_patient_record_ids is not None and header.patient_record_id not in allowed_patient_record_ids:
            continue
        if query.plan_version_ids is not None and header.plan_version_id not in query.plan_version_ids:
            continue
        if not query.include_history and not header.is_current:
            continue
        aggregate = evaluated_plan_version(db, header.plan_version_id)
        if aggregate is not None:
            snapshot = patient_source_snapshot_for_record(db, header.patient_record_id, header.source_mode)
            result.append(replace(stored_plan(aggregate, identity=header.identity(), plan_date=header.plan_date or ""),
                                  version_ordinal=header.version_ordinal, is_current=header.is_current,
                                  full_name=snapshot.full_name if snapshot is not None else ""))
    return tuple(result)


def list_treatment_plan_queue_items(
    db: Session, allowed_patient_record_ids: frozenset[int] | None = None,
    query: TreatmentPlanQuery = TreatmentPlanQuery(),
) -> tuple[TreatmentPlanQueueItem, ...]:
    from app.v2.services.manager_action_store import open_correction_counts_by_version
    correction_counts = open_correction_counts_by_version(db)
    return tuple(_queue_item_from_import(row, correction_counts.get(row.plan_version_id, 0))
                 for row in list_treatment_plan_imports(db, allowed_patient_record_ids, query))


def treatment_plan_aggregate_for_patient(
    db: Session,
    patient_id: str,
    treatment_plan_id: str | None = None,
    *,
    source_system: str | None = None,
) -> TreatmentPlanAggregate | None:
    rows = db.execute(text(
        "SELECT v.id FROM treatment_plan_versions v JOIN patients p ON p.id=v.patient_id "
        "WHERE p.canonical_client_id=:mrn AND (:plan IS NULL OR v.source_record_id=:plan) "
        "AND (:source IS NULL OR v.source_system=:source)"
    ), {"mrn": patient_id, "plan": treatment_plan_id, "source": source_system}).all()
    if not rows:
        return None
    if len(rows) != 1:
        raise HTTPException(status_code=409, detail="Select a specific treatment-plan version.")
    return treatment_plan_aggregate_for_version(db, int(rows[0][0]))


def treatment_plan_aggregate_for_version(db: Session, plan_version_id: int) -> TreatmentPlanAggregate | None:
    from app.v2.services.manager_action_store import manager_override_dicts_for_version, manager_review_dicts_for_version
    from app.v2.services.patient_snapshot_store import patient_source_snapshot_for_record
    aggregate = evaluated_plan_version(db, plan_version_id)
    if aggregate is None:
        return None
    patient_record_id = int(db.execute(text("SELECT patient_id FROM treatment_plan_versions WHERE id=:id"), {"id": plan_version_id}).scalar_one())
    snapshot = patient_source_snapshot_for_record(db, patient_record_id, aggregate.source_mode)
    aggregate = aggregate.model_copy(update={"patient_full_name": snapshot.full_name if snapshot is not None else ""})
    identity = PlanVersionIdentity(plan_version_id, patient_record_id, aggregate.patient_id, aggregate.source_mode, aggregate.content_snapshot.plan_id)
    source_documents = source_documents_for_version(db, identity)
    persisted_reviews = manager_review_dicts_for_version(db, plan_version_id)
    return aggregate.model_copy(
        update={
            "manager_reviews": aggregate.manager_reviews + persisted_reviews,
            "overrides": aggregate.overrides + manager_override_dicts_for_version(db, plan_version_id),
            "source_documents": source_documents,
        }
    )


def _queue_item_from_import(row: StoredTreatmentPlan, returned_criteria_count: int) -> TreatmentPlanQueueItem:
    return TreatmentPlanQueueItem(
        patient_id=row.patient_id,
        patient_display_label=row.patient_display_label,
        treatment_plan_id=row.plan_id,
        current_level_of_care=row.current_level_of_care,
        admission_date=row.admission_date,
        next_due_date=row.next_due_date,
        status=row.overall_status,
        missing_criteria_count=row.missing_criteria_count,
        returned_criteria_count=returned_criteria_count,
        source_mode=row.source_mode,
        content_completeness_summary=_int_map(row.content_summary_json),
        warnings=_string_tuple(row.warnings_json),
        plan_version_id=row.plan_version_id,
        patient_record_id=row.patient_record_id,
        full_name=row.full_name,
        original_plan_reference=row.original_plan_reference,
        service_date=row.service_date,
        version_ordinal=row.version_ordinal,
        last_updated=row.last_updated,
        is_current=row.is_current,
    )


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
