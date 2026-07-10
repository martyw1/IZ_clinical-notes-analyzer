from __future__ import annotations

from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.v2.domain.schemas import JsonValue
from app.v2.models import TreatmentPlanManagerAction, User

ACTION_STATUS_LABELS: Final = {
    "approve": "Approved",
    "return_for_correction": "Returned",
    "correction_submitted": "Correction submitted",
    "override": "Override",
    "comment": "Comment",
}
WORKFLOW_STATE_ACTIONS: Final = {"approve", "return_for_correction", "correction_submitted", "override"}


def save_manager_action_record(
    db: Session,
    *,
    patient_id: str,
    criterion_id: str,
    action: str,
    comment: str,
    override_reason: str,
    actor: User,
) -> TreatmentPlanManagerAction:
    row = TreatmentPlanManagerAction(
        patient_id=patient_id,
        criterion_id=criterion_id,
        action=action,
        comment=comment,
        override_reason=override_reason,
        actor_user_id=str(actor.id),
        actor_username=actor.username,
        actor_role=actor.role,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def manager_review_dicts_for_patient(db: Session, patient_id: str) -> tuple[dict[str, JsonValue], ...]:
    rows = db.execute(
        select(TreatmentPlanManagerAction)
        .where(TreatmentPlanManagerAction.patient_id == patient_id)
        .order_by(TreatmentPlanManagerAction.created_at.asc(), TreatmentPlanManagerAction.id.asc())
    )
    return tuple(_manager_review_dict(row) for row in rows.scalars().all())


def manager_override_dicts_for_patient(db: Session, patient_id: str) -> tuple[dict[str, JsonValue], ...]:
    return tuple(
        {
            "criterion_id": review["criterion_id"],
            "override_reason": review["override_reason"],
            "comment": review["comment"],
            "actor_username": review["actor_username"],
            "actor_role": review["actor_role"],
            "created_at": review["created_at"],
        }
        for review in manager_review_dicts_for_patient(db, patient_id)
        if review["action"] == "override"
    )


def open_correction_dicts(db: Session) -> tuple[dict[str, JsonValue], ...]:
    rows = db.execute(
        select(TreatmentPlanManagerAction).order_by(TreatmentPlanManagerAction.created_at.asc(), TreatmentPlanManagerAction.id.asc())
    ).scalars()
    latest_by_criterion: dict[tuple[str, str], TreatmentPlanManagerAction] = {}
    for row in rows:
        if row.action in WORKFLOW_STATE_ACTIONS:
            latest_by_criterion[(row.patient_id, row.criterion_id)] = row
    return tuple(
        _open_correction_dict(row)
        for row in latest_by_criterion.values()
        if row.action == "return_for_correction"
    )


def open_correction_counts_by_patient(db: Session) -> dict[str, int]:
    counts: dict[str, int] = {}
    for correction in open_correction_dicts(db):
        patient_id = str(correction["patient_id"])
        counts[patient_id] = counts.get(patient_id, 0) + 1
    return counts


def correction_is_open(db: Session, *, patient_id: str, criterion_id: str) -> bool:
    return any(
        correction["patient_id"] == patient_id and correction["criterion_id"] == criterion_id
        for correction in open_correction_dicts(db)
    )


def _manager_review_dict(row: TreatmentPlanManagerAction) -> dict[str, JsonValue]:
    return {
        "criterion_id": row.criterion_id,
        "action": row.action,
        "manager_status": ACTION_STATUS_LABELS.get(row.action, "Comment"),
        "comment": row.comment,
        "override_reason": row.override_reason,
        "actor_user_id": row.actor_user_id,
        "actor_username": row.actor_username,
        "actor_role": row.actor_role,
        "created_at": row.created_at.isoformat(),
    }


def _open_correction_dict(row: TreatmentPlanManagerAction) -> dict[str, JsonValue]:
    return {
        "patient_id": row.patient_id,
        "criterion_id": row.criterion_id,
        "return_comment": row.comment,
        "returned_by_username": row.actor_username,
        "returned_at": row.created_at.isoformat(),
    }
