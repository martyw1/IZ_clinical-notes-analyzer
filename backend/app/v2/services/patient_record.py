from __future__ import annotations

from dataclasses import dataclass

from pydantic import JsonValue
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.v2.services.patient_snapshot_store import (
    latest_patient_source_snapshot,
    patient_current_level_of_care,
)
from app.v2.services.patient_roster import plans_by_source_update
from app.v2.services.treatment_plan_store import list_treatment_plan_imports


@dataclass(frozen=True, slots=True)
class PatientRecordPlan:
    treatment_plan_id: str
    last_updated: str


@dataclass(frozen=True, slots=True)
class PatientRecordDetail:
    patient_row_id: int
    snapshot_id: int | None
    snapshot_version_count: int
    field_count: int
    mrn: str
    full_name: str
    source_mode: str
    lifecycle_state: str
    current_level_of_care: str
    source_last_updated: str
    first_seen_at: str
    last_seen_at: str
    reconciled_at: str
    treatment_plans: tuple[PatientRecordPlan, ...]
    patient_record: dict[str, JsonValue]


def patient_record_detail(
    db: Session,
    patient_key: str,
    source_system: str | None = None,
) -> PatientRecordDetail | None:
    if source_system is None:
        row = db.execute(
            text(
                "SELECT id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at,reconciled_at "
                "FROM patients WHERE canonical_client_id=:patient_key "
                "ORDER BY CASE WHEN source_system='alleva_rest_api' THEN 0 ELSE 1 END,id LIMIT 1"
            ),
            {"patient_key": patient_key},
        ).first()
    else:
        row = db.execute(
            text(
                "SELECT id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at,reconciled_at "
                "FROM patients WHERE canonical_client_id=:patient_key AND source_system=:source_system "
                "ORDER BY id LIMIT 1"
            ),
            {"patient_key": patient_key, "source_system": source_system},
        ).first()
    if row is None:
        return None
    effective_source_system = str(row[2])
    snapshot = latest_patient_source_snapshot(db, patient_key, effective_source_system)
    plans = tuple(
        plan
        for plan in list_treatment_plan_imports(db)
        if plan.patient_id == patient_key and plan.source_mode == effective_source_system
    )
    ordered_plans = plans_by_source_update(plans)
    current_level_of_care = (
        patient_current_level_of_care(snapshot.record)
        if snapshot is not None
        else ""
    )
    if not current_level_of_care and ordered_plans:
        current_level_of_care = ordered_plans[0].current_level_of_care
    return PatientRecordDetail(
        patient_row_id=int(row[0]),
        snapshot_id=snapshot.snapshot_id if snapshot is not None else None,
        snapshot_version_count=snapshot.version_ordinal if snapshot is not None else 0,
        field_count=_field_count(snapshot.record) if snapshot is not None else 0,
        mrn=str(row[1]),
        full_name=snapshot.full_name if snapshot is not None else "",
        source_mode=effective_source_system,
        lifecycle_state=str(row[3]),
        current_level_of_care=current_level_of_care or "Unknown",
        source_last_updated=snapshot.source_last_updated if snapshot is not None else "",
        first_seen_at=str(row[4]),
        last_seen_at=str(row[5]),
        reconciled_at=str(row[6] or ""),
        treatment_plans=tuple(
            PatientRecordPlan(plan.plan_id, plan.last_updated)
            for plan in ordered_plans
        ),
        patient_record=snapshot.record if snapshot is not None else {},
    )


def _field_count(value: object) -> int:
    if isinstance(value, dict):
        return sum((_field_count(item) for item in value.values()), start=0) or 1
    if isinstance(value, list):
        return sum((_field_count(item) for item in value), start=0) or 1
    return 1
