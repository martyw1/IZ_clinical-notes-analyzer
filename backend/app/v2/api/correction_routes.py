from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.v2.api.deps import CurrentUser, DbSession
from app.v2.api.models import CorrectionQueueItemOut, CorrectionQueueOut, CorrectionSubmissionInput
from app.v2.domain.schemas import JsonValue
from app.v2.services.audit_store import record_audit_event
from app.v2.services.manager_action_store import correction_is_open, open_correction_dicts, save_manager_action_record
from app.v2.services.treatment_plan_store import treatment_plan_aggregate_for_patient

router = APIRouter()


@router.get("/api/v2/corrections", response_model=CorrectionQueueOut)
def correction_queue(_: CurrentUser, db: DbSession) -> CorrectionQueueOut:
    items = []
    for correction in open_correction_dicts(db):
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
    if user.role != "counselor":
        record_audit_event(
            db, action="correction.submission.denied", actor=user, target_entity_type="treatment_plan_criterion",
            target_entity_id=f"{patient_id}:{payload.criterion_id}", outcome_status="denied", details={"criterion_id": payload.criterion_id},
        )
        raise HTTPException(status_code=403, detail="Counselor access required")
    if treatment_plan_aggregate_for_patient(db, patient_id) is None:
        raise HTTPException(status_code=404, detail="Treatment-plan aggregate not found")
    if not correction_is_open(db, patient_id=patient_id, criterion_id=payload.criterion_id):
        raise HTTPException(status_code=409, detail="No open correction return exists for this criterion")
    saved = save_manager_action_record(
        db, patient_id=patient_id, criterion_id=payload.criterion_id, action="correction_submitted",
        comment=payload.comment.strip(), override_reason="", actor=user,
    )
    record_audit_event(
        db, action="correction.submitted", actor=user, target_entity_type="treatment_plan_criterion",
        target_entity_id=f"{patient_id}:{payload.criterion_id}", details={"criterion_id": payload.criterion_id, "has_comment": True},
    )
    return {"status": "submitted", "patient_id": patient_id, "criterion_id": payload.criterion_id, "created_at": saved.created_at.isoformat()}
