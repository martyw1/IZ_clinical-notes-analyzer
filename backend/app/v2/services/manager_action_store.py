from __future__ import annotations

from typing import Final, TypedDict

from sqlalchemy import Integer, and_, column, select, table, text
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.v2.models import TreatmentPlanManagerAction, User
from app.v2.services.correction_work_item_store import (
    CorrectionAssignmentError as CorrectionAssignmentError,
    open_correction_counts_by_patient as open_correction_counts_by_patient,
    open_correction_counts_by_version as open_correction_counts_by_version,
    open_correction_dicts as open_correction_dicts,
    save_returned_correction_work_item as save_returned_correction_work_item,
)


class ManagerReview(TypedDict):
    action_id: int
    plan_version_id: int | None
    linkage_status: str
    criterion_id: str
    action: str
    manager_status: str
    comment: str
    override_reason: str
    actor_user_id: str
    actor_username: str
    actor_role: str
    created_at: str


class ManagerOverride(TypedDict):
    criterion_id: str
    override_reason: str
    comment: str
    actor_username: str
    actor_role: str
    created_at: str


ACTION_STATUS_LABELS: Final = {
    "approve": "Approved", "return_for_correction": "Returned",
    "correction_submitted": "Correction submitted", "override": "Override", "comment": "Comment",
}
WORKFLOW_STATE_ACTIONS: Final = {"approve", "return_for_correction", "correction_submitted", "override"}
_ACTION_LINKS: Final = table(
    "manager_action_plan_links", column("action_id", Integer), column("plan_version_id", Integer),
).alias("link")


def save_manager_action_record(
    db: Session,
    *,
    patient_id: str,
    criterion_id: str,
    action: str,
    comment: str,
    override_reason: str,
    actor: User,
    plan_version_id: int | None = None,
    commit: bool = True,
) -> TreatmentPlanManagerAction:
    row = TreatmentPlanManagerAction(
        patient_id=patient_id, criterion_id=criterion_id, action=action, comment=comment,
        override_reason=override_reason, actor_user_id=str(actor.id),
        actor_username=actor.username, actor_role=actor.role,
    )
    db.add(row)
    db.flush()
    db.execute(
        text("INSERT INTO manager_action_plan_links(action_id,plan_version_id) VALUES(:action_id,:version_id)"),
        {"action_id": row.id, "version_id": plan_version_id},
    )
    if plan_version_id is not None and action in {"approve", "comment", "override", "correction_submitted"}:
        db.execute(text(
            "INSERT INTO manager_dispositions(plan_version_id,criterion_id,status,comment,actor_user_id,created_at) "
            "VALUES(:version_id,:criterion_id,:status,:comment,:actor_id,:created_at)"
        ), {"version_id": plan_version_id, "criterion_id": criterion_id, "status": action,
            "comment": comment, "actor_id": actor.id, "created_at": row.created_at.isoformat()})
    if commit:
        db.commit()
        db.refresh(row)
    return row


def manager_review_dicts_for_patient(db: Session, patient_id: str) -> tuple[ManagerReview, ...]:
    return _manager_reviews(db, TreatmentPlanManagerAction.patient_id == patient_id)


def unassigned_manager_review_dicts_for_patient(db: Session, patient_id: str) -> tuple[ManagerReview, ...]:
    return _manager_reviews(db, and_(
        TreatmentPlanManagerAction.patient_id == patient_id, _ACTION_LINKS.c.plan_version_id.is_(None),
    ))


def manager_review_dicts_for_version(db: Session, plan_version_id: int) -> tuple[ManagerReview, ...]:
    return _manager_reviews(db, _ACTION_LINKS.c.plan_version_id == plan_version_id)


def manager_override_dicts_for_patient(db: Session, patient_id: str) -> tuple[ManagerOverride, ...]:
    return _manager_overrides(manager_review_dicts_for_patient(db, patient_id))


def manager_override_dicts_for_version(db: Session, plan_version_id: int) -> tuple[ManagerOverride, ...]:
    return _manager_overrides(manager_review_dicts_for_version(db, plan_version_id))


def _manager_overrides(reviews: tuple[ManagerReview, ...]) -> tuple[ManagerOverride, ...]:
    return tuple(
        {"criterion_id": review["criterion_id"], "override_reason": review["override_reason"],
         "comment": review["comment"], "actor_username": review["actor_username"],
         "actor_role": review["actor_role"], "created_at": review["created_at"]}
        for review in reviews if review["action"] == "override"
    )


def _manager_reviews(db: Session, predicate: ColumnElement[bool]) -> tuple[ManagerReview, ...]:
    rows = db.execute(
        select(TreatmentPlanManagerAction, _ACTION_LINKS.c.plan_version_id)
        .outerjoin(_ACTION_LINKS, _ACTION_LINKS.c.action_id == TreatmentPlanManagerAction.id)
        .where(predicate)
        .order_by(TreatmentPlanManagerAction.created_at.asc(), TreatmentPlanManagerAction.id.asc())
    ).all()
    return tuple(_manager_review_dict(row, version_id) for row, version_id in rows)


def _manager_review_dict(row: TreatmentPlanManagerAction, plan_version_id: int | None) -> ManagerReview:
    return {
        "action_id": row.id, "plan_version_id": plan_version_id,
        "linkage_status": "assigned" if plan_version_id is not None else "unassigned",
        "criterion_id": row.criterion_id, "action": row.action,
        "manager_status": ACTION_STATUS_LABELS.get(row.action, "Comment"),
        "comment": row.comment, "override_reason": row.override_reason,
        "actor_user_id": row.actor_user_id, "actor_username": row.actor_username,
        "actor_role": row.actor_role, "created_at": row.created_at.isoformat(),
    }
