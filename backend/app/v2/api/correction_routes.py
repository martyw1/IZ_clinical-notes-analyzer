from __future__ import annotations

from typing import Literal, TypedDict

from fastapi import APIRouter, HTTPException

from app.v2.api.deps import CurrentUser, DbSession
from app.v2.api.models import CorrectionQueueItemOut, CorrectionQueueOut, CorrectionSubmissionInput
from app.v2.authorization import (
    Role, accessible_patient_record_ids, deny, facility_ids_for_user,
)
from app.v2.services.audit_store import record_audit_event
from app.v2.services.correction_work_item_store import close_correction_work_item, correction_work_item_for_id
from app.v2.services.manager_action_store import open_correction_dicts, save_manager_action_record
from app.v2.services.evaluation_store import refresh_plan_version
from app.v2.services.treatment_plan_store import treatment_plan_aggregate_for_version

router = APIRouter()


class CorrectionSubmissionResult(TypedDict):
    status: Literal["submitted"]
    patient_id: str
    patient_record_id: int
    plan_version_id: int
    source_mode: str
    treatment_plan_id: str
    criterion_id: str
    created_at: str


@router.get("/api/v2/corrections", response_model=CorrectionQueueOut)
def correction_queue(user: CurrentUser, db: DbSession) -> CorrectionQueueOut:
    if user.role == Role.VIEWER.value:
        deny(db, user, family="correction_queue")
    allowed_ids = accessible_patient_record_ids(db, user)
    items = []
    counselor_id = user.id if user.role == Role.COUNSELOR.value else None
    for correction in open_correction_dicts(db, assigned_counselor_user_id=counselor_id):
        if correction["patient_record_id"] not in allowed_ids:
            continue
        aggregate = treatment_plan_aggregate_for_version(db, correction["plan_version_id"])
        if aggregate is None:
            continue
        title = next(
            (criterion.criterion_title for criterion in aggregate.criteria_results if criterion.criterion_id == correction["criterion_id"]),
            correction["criterion_id"],
        )
        items.append(CorrectionQueueItemOut(
            **correction, patient_display_label=aggregate.patient_display_label, criterion_title=title,
        ))
    return CorrectionQueueOut(items=tuple(items))


@router.post("/api/v2/treatment-plans/{patient_id}/correction-submissions")
def submit_correction(patient_id: str, payload: CorrectionSubmissionInput, user: CurrentUser, db: DbSession) -> CorrectionSubmissionResult:
    item = correction_work_item_for_id(db, payload.work_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Correction work item not found")
    identity = item.identity
    selectors = (
        (patient_id, identity.patient_id), (payload.criterion_id, item.criterion_id),
        (payload.plan_version_id, identity.plan_version_id), (payload.patient_record_id, identity.patient_record_id),
        (payload.source_mode, identity.source_mode), (payload.treatment_plan_id, identity.treatment_plan_id),
    )
    if any(supplied is not None and supplied != expected for supplied, expected in selectors):
        raise HTTPException(status_code=404, detail="Correction work item not found")
    if (user.role != Role.COUNSELOR.value or user.id != item.counselor_user_id
            or item.facility_id not in facility_ids_for_user(db, user.id)):
        deny(db, user, family="correction_submission", target_id=str(identity.patient_record_id))
    if item.status not in {"open", "returned"}:
        raise HTTPException(status_code=409, detail="This correction work item is already closed.")
    if not close_correction_work_item(db, item, commit=False):
        raise HTTPException(status_code=409, detail="This correction work item is already closed.")
    if treatment_plan_aggregate_for_version(db, identity.plan_version_id) is None:
        raise HTTPException(status_code=404, detail="Treatment-plan aggregate not found")
    saved = save_manager_action_record(
        db, patient_id=patient_id, plan_version_id=identity.plan_version_id,
        criterion_id=payload.criterion_id, action="correction_submitted", comment=payload.comment.strip(),
        override_reason="", actor=user, commit=False,
    )
    refresh_plan_version(db, identity.plan_version_id, "correction", commit=False)
    record_audit_event(
        db, action="correction.submitted", actor=user, target_entity_type="treatment_plan_criterion",
        target_entity_id=f"{identity.plan_version_id}:{payload.criterion_id}",
        details={"criterion_id": payload.criterion_id, "plan_version_id": identity.plan_version_id, "has_comment": True},
        commit=False,
    )
    db.commit()
    return {"status": "submitted", "patient_id": patient_id, "patient_record_id": identity.patient_record_id,
            "plan_version_id": identity.plan_version_id, "source_mode": identity.source_mode,
            "treatment_plan_id": identity.treatment_plan_id, "criterion_id": payload.criterion_id,
            "created_at": saved.created_at.isoformat()}
