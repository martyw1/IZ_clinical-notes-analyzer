from __future__ import annotations

from fastapi import APIRouter

from app.v2.api.deps import CurrentUser, DbSession
from app.v2.api.models import (
    PatientRosterOut, PatientRosterItemOut, PatientRosterTreatmentPlanOut,
    TreatmentPlanRosterOut, TreatmentPlanRosterItemOut, PatientRecordDetailOut,
)
from app.v2.authorization import accessible_patient_record_ids
from app.v2.domain.schemas import SourceMode
from app.v2.services.audit_store import record_audit_event
from app.v2.services.patient_record import PatientRecordSelector, patient_record_detail
from app.v2.services.patient_roster import list_patient_roster, list_treatment_plan_roster

router = APIRouter()


@router.get("/api/v2/patient-roster", response_model=PatientRosterOut)
def patient_roster(user: CurrentUser, db: DbSession, source_mode: SourceMode | None = None) -> PatientRosterOut:
    items = list_patient_roster(db, accessible_patient_record_ids(db, user), source_mode)
    return PatientRosterOut(items=tuple(PatientRosterItemOut.model_validate(item, from_attributes=True) for item in items))


@router.get("/api/v2/treatment-plan-roster", response_model=TreatmentPlanRosterOut)
def treatment_plan_roster(user: CurrentUser, db: DbSession, source_mode: SourceMode | None = None) -> TreatmentPlanRosterOut:
    items = list_treatment_plan_roster(db, accessible_patient_record_ids(db, user), source_mode)
    return TreatmentPlanRosterOut(items=tuple(TreatmentPlanRosterItemOut.model_validate(item, from_attributes=True) for item in items))


@router.get("/api/v2/patients/{patient_id}", response_model=PatientRecordDetailOut)
def patient_detail(
    patient_id: str,
    user: CurrentUser,
    db: DbSession,
    source_mode: SourceMode | None = None,
    patient_record_id: int | None = None,
) -> PatientRecordDetailOut:
    detail = patient_record_detail(db, user, PatientRecordSelector(patient_id, patient_record_id, source_mode))
    record_audit_event(
        db,
        action="patient_record.detail.viewed",
        actor=user,
        target_entity_type="patient",
        target_entity_id=str(detail.patient_row_id),
        details={
            "snapshot_id": detail.snapshot_id,
            "snapshot_version_count": detail.snapshot_version_count,
            "field_count": detail.field_count,
        },
    )
    return PatientRecordDetailOut(
        patient_record_id=detail.patient_row_id,
        mrn=detail.mrn,
        full_name=detail.full_name,
        source_mode=detail.source_mode,
        lifecycle_state=detail.lifecycle_state,
        current_level_of_care=detail.current_level_of_care,
        source_last_updated=detail.source_last_updated,
        first_seen_at=detail.first_seen_at,
        last_seen_at=detail.last_seen_at,
        reconciled_at=detail.reconciled_at,
        treatment_plans=tuple(
            PatientRosterTreatmentPlanOut.model_validate(plan, from_attributes=True)
            for plan in detail.treatment_plans
        ),
        patient_record=detail.patient_record,
    )
