from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from app.v2.models import AppSetting, OverduePlanAcknowledgement
from app.v2.services.deterministic_evaluator import facility_local_date
from app.v2.services.patient_roster import TreatmentPlanRosterItem, list_treatment_plan_roster
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.v2.api.deps import CurrentUser, DbSession, ManagerUser
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


@router.post("/api/v2/treatment-plans/{patient_id}/{treatment_plan_id}/overdue-review")
def acknowledge_overdue_plan(
    patient_id: str, treatment_plan_id: str, user: ManagerUser, db: DbSession,
    source_mode: SourceMode, plan_version_id: int, patient_record_id: int,
) -> dict[str, str]:
    identity = resolve_plan_version(db, user, PlanVersionSelector(
        patient_id, plan_version_id, patient_record_id, source_mode, treatment_plan_id,
    ))
    existing = db.get(OverduePlanAcknowledgement, identity.plan_version_id)
    if existing is not None:
        return {"reviewed_at_utc": existing.reviewed_at_utc}
    item = _tracking_item(db, identity)
    if item is None or item.deadline_status != "Overdue":
        raise HTTPException(status_code=409, detail="Only current overdue plans can be marked reviewed.")
    statement = insert(OverduePlanAcknowledgement).values(
        plan_version_id=identity.plan_version_id,
        reviewer_user_id=user.id,
        reviewed_at_utc=datetime.now(timezone.utc).isoformat(),
    ).on_conflict_do_nothing(index_elements=["plan_version_id"])
    result = db.execute(statement)
    if result.rowcount:
        record_audit_event(
            db, action="treatment_plan.overdue_acknowledged", actor=user,
            target_entity_type="treatment_plan_version", target_entity_id=str(identity.plan_version_id),
            commit=False,
        )
    db.commit()
    saved = db.get(OverduePlanAcknowledgement, identity.plan_version_id)
    return {"reviewed_at_utc": saved.reviewed_at_utc}


def _tracking_item(db: Session, identity: PlanVersionIdentity) -> TreatmentPlanRosterItem | None:
    facility_timezone = db.execute(select(AppSetting.facility_timezone)).scalar_one()
    today = facility_local_date(datetime.now(timezone.utc), facility_timezone)
    items = list_treatment_plan_roster(db, frozenset({identity.patient_record_id}), identity.source_mode, today)
    return next((item for item in items if item.plan_version_id == identity.plan_version_id), None)


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
    from app.v2.services.deadline_calendar import computed_deadline_details
    from app.v2.services.rule_package import load_rule_package
    from datetime import date
    computed_status, explanation = computed_deadline_details(
        aggregate, load_rule_package(), date.fromisoformat(aggregate.evaluation_date), aggregate.facility_timezone,
    )
    item = _tracking_item(db, identity)
    acknowledgement = db.get(OverduePlanAcknowledgement, identity.plan_version_id)
    from app.v2.services.imported_counselors import primary_counselors_for_records
    clinician = primary_counselors_for_records(db, (identity.patient_record_id,)).get(identity.patient_record_id)
    return TreatmentPlanDetailOut(
        primary_counselor_id=clinician[0] if clinician else None,
        primary_counselor_name=clinician[1] if clinician else "",
        **aggregate.model_dump(),
        computed_deadline_status=computed_status,
        deadline_explanation=explanation,
        tracking_due_date=item.next_due_date if item else "",
        deadline_status=item.deadline_status if item else "Outside current tracking",
        reviewed_at_utc=acknowledgement.reviewed_at_utc if acknowledgement else "",
        plan_version_id=identity.plan_version_id,
        patient_record_id=identity.patient_record_id,
        treatment_plan_id=identity.treatment_plan_id,
        unassigned_manager_reviews=unassigned,
    )
