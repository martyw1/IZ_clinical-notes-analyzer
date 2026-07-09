from __future__ import annotations

from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.v2.domain.schemas import JsonValue
from app.v2.models import TreatmentPlanManagerAction, User

ACTION_STATUS_LABELS: Final = {
    "approve": "Approved",
    "return_for_correction": "Returned",
    "override": "Override",
    "comment": "Comment",
}


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
