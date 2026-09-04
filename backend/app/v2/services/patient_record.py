from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

from fastapi import HTTPException
from pydantic import JsonValue
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.v2.authorization import accessible_patient_record_ids, require_patient_row_read
from app.v2.domain.schemas import SourceMode
from app.v2.models import User
from app.v2.services.patient_snapshot_store import patient_source_snapshot_for_record, patient_current_level_of_care
from app.v2.services.patient_roster import PatientRow, PatientRosterTreatmentPlan, plans_by_source_update, roster_plan
from app.v2.services.treatment_plan_store import list_treatment_plan_imports
from app.v2.services.treatment_plan_read_model import TreatmentPlanQuery


@dataclass(frozen=True, slots=True)
class PatientRecordSelector:
    patient_id: str
    patient_record_id: int | None = None
    source_mode: SourceMode | None = None


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
    treatment_plans: tuple[PatientRosterTreatmentPlan, ...]
    patient_record: dict[str, JsonValue]


def patient_record_detail(db: Session, user: User, selector: PatientRecordSelector) -> PatientRecordDetail:
    rows = db.execute(text(
        "SELECT id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at,reconciled_at "
        "FROM patients WHERE canonical_client_id=:mrn AND (:record IS NULL OR id=:record) "
        "AND (:source IS NULL OR source_system=:source) ORDER BY id"
    ), {"mrn": selector.patient_id, "record": selector.patient_record_id, "source": selector.source_mode}).all()
    if not rows:
        raise HTTPException(status_code=404, detail="Patient record not found")
    allowed = accessible_patient_record_ids(db, user)
    eligible = tuple(raw for raw in rows if int(raw[0]) in allowed)
    if len(eligible) > 1:
        raise HTTPException(status_code=409, detail="Select a specific patient record.")
    row = PatientRow.model_validate((eligible[0] if eligible else rows[0])._mapping)
    require_patient_row_read(db, user, row.id)
    snapshot = patient_source_snapshot_for_record(db, row.id, row.source_system)
    plans = plans_by_source_update(list_treatment_plan_imports(db, frozenset({row.id}),
        TreatmentPlanQuery(source_mode=row.source_system, patient_record_id=row.id)))
    level_of_care = patient_current_level_of_care(snapshot.record) if snapshot is not None else ""
    if not level_of_care and plans:
        level_of_care = plans[0].current_level_of_care
    return PatientRecordDetail(
        patient_row_id=row.id, snapshot_id=snapshot.snapshot_id if snapshot else None,
        snapshot_version_count=snapshot.version_ordinal if snapshot else 0,
        field_count=_field_count(snapshot.record) if snapshot else 0,
        mrn=row.canonical_client_id, full_name=snapshot.full_name if snapshot else "",
        source_mode=row.source_system, lifecycle_state=row.lifecycle_state, current_level_of_care=level_of_care or "Unknown",
        source_last_updated=snapshot.source_last_updated if snapshot else "",
        first_seen_at=row.first_seen_at, last_seen_at=row.last_seen_at, reconciled_at=row.reconciled_at or "",
        treatment_plans=tuple(roster_plan(plan) for plan in plans), patient_record=snapshot.record if snapshot else {},
    )


def _field_count(value: JsonValue) -> int:
    match value:
        case dict():
            return sum((_field_count(item) for item in value.values()), start=0) or 1
        case list():
            return sum((_field_count(item) for item in value), start=0) or 1
        case str() | int() | float() | bool() | None:
            return 1
        case unreachable:
            assert_never(unreachable)
