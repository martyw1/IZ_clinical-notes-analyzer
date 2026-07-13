from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.v2.domain.schemas import JsonValue, SourceMode, TreatmentPlanAggregate
from app.v2.services.clinical_snapshot_codec import (
    AggregateSnapshot,
    ClinicalSnapshotCodec,
    PlanRecordSnapshot,
)
from app.v2.services.manual_file_aggregate import build_manual_aggregate
from app.v2.services.manual_file_types import ParsedManualFields


@dataclass(frozen=True, slots=True)
class PlanVersionRow:
    source_system: str
    source_record_id: str
    version_ordinal: int
    admission_date: str
    next_due_date: str
    stored: str | bytes


@dataclass(frozen=True, slots=True)
class ReviewVersionRow:
    source_record_id: str
    version_ordinal: int
    stored: str | bytes


@dataclass(frozen=True, slots=True)
class RecordAggregateSource:
    patient_id: str
    latest: PlanVersionRow
    plans: tuple[dict[str, JsonValue], ...]
    reviews: tuple[dict[str, JsonValue], ...]


def assemble_treatment_plan_aggregate(
    db: Session,
    patient_id: str,
    encryption_secret: str,
    treatment_plan_id: str | None = None,
) -> TreatmentPlanAggregate | None:
    plans = _plan_rows(db, patient_id, treatment_plan_id)
    if not plans:
        return None
    codec = ClinicalSnapshotCodec(encryption_secret)
    decoded_plans = tuple((row, codec.decode_plan(row.stored)) for row in plans)
    reviews = tuple(codec.decode_review(row.stored).record for row in _review_rows(db, patient_id))
    for _, snapshot in reversed(decoded_plans):
        if isinstance(snapshot, AggregateSnapshot):
            records = tuple(item.record for _, item in decoded_plans if isinstance(item, PlanRecordSnapshot))
            return _merge_aggregate(snapshot.aggregate, records, reviews)
    records = tuple(snapshot.record for _, snapshot in decoded_plans if isinstance(snapshot, PlanRecordSnapshot))
    return record_aggregate(RecordAggregateSource(patient_id, plans[-1], records, reviews))


def _plan_rows(db: Session, patient_id: str, treatment_plan_id: str | None = None) -> tuple[PlanVersionRow, ...]:
    rows = db.execute(
        text(
            "SELECT v.source_system,v.source_record_id,v.version_ordinal,v.admission_date,"
            "v.source_next_review_due,v.normalized_snapshot_encrypted FROM patients p "
            "JOIN treatment_plan_versions v ON v.patient_id=p.id WHERE p.canonical_client_id=:client_id "
            "AND (:treatment_plan_id IS NULL OR v.source_record_id=:treatment_plan_id) "
            "ORDER BY v.version_ordinal,v.id"
        ),
        {"client_id": patient_id, "treatment_plan_id": treatment_plan_id},
    ).all()
    return tuple(
        PlanVersionRow(str(row[0]), str(row[1]), int(row[2]), str(row[3] or "Unknown"), str(row[4] or "Unknown"), row[5])
        for row in rows
    )


def _review_rows(db: Session, patient_id: str) -> tuple[ReviewVersionRow, ...]:
    rows = db.execute(
        text(
            "SELECT v.source_record_id,v.version_ordinal,v.normalized_snapshot_encrypted FROM patients p "
            "JOIN treatment_review_versions v ON v.patient_id=p.id WHERE p.canonical_client_id=:client_id "
            "ORDER BY v.version_ordinal,v.id"
        ),
        {"client_id": patient_id},
    ).all()
    return tuple(ReviewVersionRow(str(row[0]), int(row[1]), row[2]) for row in rows)


def record_aggregate(source: RecordAggregateSource) -> TreatmentPlanAggregate:
    latest_record = source.plans[-1]
    parsed = ParsedManualFields(
        patient_id=source.patient_id,
        patient_id_correction_applied=False,
        level_of_care=_record_text(latest_record, "current_level_of_care", "level_of_care", "loc") or "Unknown",
        admission_date=source.latest.admission_date,
        due_date=source.latest.next_due_date,
        reason_for_admission=_record_text(latest_record, "reason_for_admission"),
        initial_client_needs=_record_text(latest_record, "initial_client_needs"),
        family_education_needs=_record_text(latest_record, "family_education_needs"),
        problem_description="",
        diagnosis_description="",
        icd10_code="",
        behavioral_definition="",
        goal_description="",
        objective_description="",
        intervention_description="",
        signature_datetime=_record_text(latest_record, "signature_date", "signatureDate"),
        raw_text=json.dumps(latest_record, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
    )
    aggregate = build_manual_aggregate(parsed)
    plan_id = _record_text(latest_record, "id", "plan_id", "planId") or source.latest.source_record_id
    content_snapshot = aggregate.content_snapshot.model_copy(
        update={"plan_id": plan_id, "source_mode": _source_mode(source.latest.source_system)}
    )
    evidence_coverage = aggregate.evidence_coverage_summary.model_copy(update={"plan_id": plan_id})
    return aggregate.model_copy(
        update={
            "patient_display_label": f"Patient ID {source.patient_id}",
            "source_mode": _source_mode(source.latest.source_system),
            "treatment_plans": source.plans,
            "treatment_reviews": source.reviews,
            "active_treatment_plans": (latest_record,),
            "latest_created_active_plan": latest_record,
            "has_multiple_active_plans": len(source.plans) > 1,
            "current_plan_selection_reason": "Latest immutable migrated plan version by version ordinal.",
            "treatment_review_data_status": f"{len(source.reviews)} immutable migrated review versions",
            "content_snapshot_summary": {
                **aggregate.content_snapshot_summary,
                "plan_version_count": len(source.plans),
                "review_version_count": len(source.reviews),
            },
            "content_snapshot": content_snapshot,
            "evidence_coverage_summary": evidence_coverage,
        }
    )


def _merge_aggregate(
    aggregate: TreatmentPlanAggregate,
    record_plans: tuple[dict[str, JsonValue], ...],
    reviews: tuple[dict[str, JsonValue], ...],
) -> TreatmentPlanAggregate:
    if not record_plans and not reviews:
        return aggregate
    return aggregate.model_copy(
        update={
            "treatment_plans": record_plans + aggregate.treatment_plans,
            "treatment_reviews": aggregate.treatment_reviews + reviews,
        }
    )


def _record_text(record: dict[str, JsonValue], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()
    return ""


def _source_mode(value: str) -> SourceMode:
    if value in {"manual_upload", "alleva_rest_api", "synthetic_fixture"}:
        return value
    return "manual_upload"
