from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.v2.api.deps import CurrentUser, DbSession
from app.v2.authorization import Role, accessible_patient_ids, deny, require_patient_read
from app.v2.api.models import CorrectionQueueItemOut, CorrectionQueueOut, CorrectionSubmissionInput
from app.v2.domain.schemas import JsonValue
from app.v2.services.audit_store import record_audit_event
from app.v2.services.manager_action_store import (
    close_correction_work_item,
    correction_work_item_is_open_for,
    open_correction_dicts,
    save_manager_action_record,
)
from app.v2.services.evaluation_store import refresh_patient_version
from app.v2.services.treatment_plan_store import treatment_plan_aggregate_for_patient

router = APIRouter()


@router.get("/api/v2/corrections", response_model=CorrectionQueueOut)
def correction_queue(user: CurrentUser, db: DbSession) -> CorrectionQueueOut:
    if user.role == Role.VIEWER.value:
        deny(db, user, family="correction_queue")
    allowed_ids = accessible_patient_ids(db, user)
    items = []
    for correction in open_correction_dicts(db):
        if str(correction["patient_id"]) not in allowed_ids:
            continue
        aggregate = treatment_plan_aggregate_for_patient(db, str(correction["patient_id"]))
        if aggregate is None:
            continue
        title = next(
            (criterion.criterion_title for criterion in aggregate.criteria_results if criterion.criterion_id == correction["criterion_id"]),
            str(correction["criterion_id"]),
        )
        items.append(
            CorrectionQueueItemOut(
                patient_id=str(correction["patient_id"]), patient_display_label=aggregate.patient_display_label,
                criterion_id=str(correction["criterion_id"]), criterion_title=title,
                return_comment=str(correction["return_comment"]), returned_by_username=str(correction["returned_by_username"]),
                returned_at=str(correction["returned_at"]),
            )
        )
    return CorrectionQueueOut(items=tuple(items))


@router.post("/api/v2/treatment-plans/{patient_id}/correction-submissions")
def submit_correction(patient_id: str, payload: CorrectionSubmissionInput, user: CurrentUser, db: DbSession) -> dict[str, JsonValue]:
    if user.role != Role.COUNSELOR.value:
        deny(db, user, family="correction_submission", target_id=patient_id)
    require_patient_read(db, user, patient_id)
    if treatment_plan_aggregate_for_patient(db, patient_id) is None:
        raise HTTPException(status_code=404, detail="Treatment-plan aggregate not found")
    if not correction_work_item_is_open_for(
        db,
        patient_id=patient_id,
        criterion_id=payload.criterion_id,
        counselor_user_id=user.id,
    ):
        raise HTTPException(status_code=409, detail="No open correction return exists for this criterion")
    saved = save_manager_action_record(
        db, patient_id=patient_id, criterion_id=payload.criterion_id, action="correction_submitted",
        comment=payload.comment.strip(), override_reason="", actor=user,
    )
    close_correction_work_item(
        db,
        patient_id=patient_id,
        criterion_id=payload.criterion_id,
        counselor_user_id=user.id,
    )
    aggregate = treatment_plan_aggregate_for_patient(db, patient_id)
    if aggregate is not None:
        refresh_patient_version(db, aggregate, "correction")
    record_audit_event(
        db, action="correction.submitted", actor=user, target_entity_type="treatment_plan_criterion",
        target_entity_id=f"{patient_id}:{payload.criterion_id}", details={"criterion_id": payload.criterion_id, "has_comment": True},
    )
    return {"status": "submitted", "patient_id": patient_id, "criterion_id": payload.criterion_id, "created_at": saved.created_at.isoformat()}
