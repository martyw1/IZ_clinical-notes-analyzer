from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.v2.api.deps import CurrentUser, DbSession
from app.v2.api.models import TreatmentPlanListItemOut, TreatmentPlanListOut, TreatmentPlanDetailOut
from app.v2.domain.schemas import SourceMode
from app.v2.authorization import accessible_patient_record_ids, resolve_plan_version, PlanVersionSelector
from app.v2.services.audit_store import record_audit_event
from app.v2.services.treatment_plan_types import PlanVersionIdentity
from app.v2.services.treatment_plan_read_model import TreatmentPlanQuery
from app.v2.services.treatment_plan_store import TREATMENT_PLAN_STATUS_ORDER, list_treatment_plan_queue_items, treatment_plan_aggregate_for_version

router = APIRouter()


@router.get("/api/v2/treatment-plans", response_model=TreatmentPlanListOut)
def treatment_plans(
    user: CurrentUser, db: DbSession, source_mode: SourceMode | None = None,
    patient_record_id: int | None = None, treatment_plan_id: str | None = None,
    include_history: bool = False,
) -> TreatmentPlanListOut:
    query = TreatmentPlanQuery(source_mode, patient_record_id, treatment_plan_id, include_history)
    items = list_treatment_plan_queue_items(db, accessible_patient_record_ids(db, user), query)
    return TreatmentPlanListOut(
        items=tuple(TreatmentPlanListItemOut.model_validate(item, from_attributes=True) for item in items),
        status_order=TREATMENT_PLAN_STATUS_ORDER,
    )


@router.get("/api/v2/treatment-plans/{patient_id}")
def treatment_plan_detail(
    patient_id: str,
    user: CurrentUser,
    db: DbSession,
    source_mode: SourceMode | None = None,
    plan_version_id: int | None = None,
    patient_record_id: int | None = None,
    treatment_plan_id: str | None = None,
) -> TreatmentPlanDetailOut:
    identity = resolve_plan_version(db, user, PlanVersionSelector(patient_id, plan_version_id, patient_record_id, source_mode, treatment_plan_id))
    return _selected_detail(db, user, identity)


@router.get("/api/v2/treatment-plans/{patient_id}/{treatment_plan_id}")
def treatment_plan_detail_by_id(
    patient_id: str,
    treatment_plan_id: str,
    user: CurrentUser,
    db: DbSession,
    source_mode: SourceMode | None = None,
    plan_version_id: int | None = None,
    patient_record_id: int | None = None,
) -> TreatmentPlanDetailOut:
    identity = resolve_plan_version(db, user, PlanVersionSelector(patient_id, plan_version_id, patient_record_id, source_mode, treatment_plan_id))
    return _selected_detail(db, user, identity)


def _selected_detail(db: Session, user: CurrentUser, identity: PlanVersionIdentity) -> TreatmentPlanDetailOut:
    from app.v2.services.manager_action_store import unassigned_manager_review_dicts_for_patient
    aggregate = treatment_plan_aggregate_for_version(db, identity.plan_version_id)
    if aggregate is None:
        raise HTTPException(status_code=404, detail="Treatment plan not found")
    same_mrn_records = frozenset(int(row[0]) for row in db.execute(text("SELECT id FROM patients WHERE canonical_client_id=:mrn"), {"mrn": identity.patient_id}).all())
    unassigned = unassigned_manager_review_dicts_for_patient(db, identity.patient_id) if same_mrn_records <= accessible_patient_record_ids(db, user) else ()
    record_audit_event(
        db,
        action="treatment_plan.detail.viewed",
        actor=user,
        target_entity_type="treatment_plan_version",
        target_entity_id=str(identity.plan_version_id),
        details={"patient_row_id": identity.patient_record_id},
    )
    return TreatmentPlanDetailOut(**aggregate.model_dump(), plan_version_id=identity.plan_version_id, patient_record_id=identity.patient_record_id, treatment_plan_id=identity.treatment_plan_id, unassigned_manager_reviews=unassigned)
