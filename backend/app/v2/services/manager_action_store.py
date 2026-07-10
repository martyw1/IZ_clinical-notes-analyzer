from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.v2.domain.schemas import JsonValue
from app.v2.models import TreatmentPlanManagerAction, User, utc_now


@dataclass(frozen=True, slots=True)
class CorrectionAssignmentError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return self.reason

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


def open_correction_dicts(
    db: Session,
    *,
    assigned_counselor_user_id: int | None = None,
) -> tuple[dict[str, JsonValue], ...]:
    rows = db.execute(
        text(
            """SELECT correction.id,correction.plan_version_id,patient.canonical_client_id,correction.criterion_id,
            disposition.comment,manager.username,correction.opened_at
            FROM correction_work_items correction
            JOIN treatment_plan_versions plan ON plan.id=correction.plan_version_id
            JOIN patients patient ON patient.id=plan.patient_id
            JOIN manager_dispositions disposition ON disposition.id=correction.disposition_id
            JOIN users manager ON manager.id=disposition.actor_user_id
            WHERE correction.status IN ('open','returned')
                AND (:counselor_id IS NULL OR correction.assigned_counselor_user_id=:counselor_id)
            ORDER BY correction.opened_at ASC,correction.id ASC"""
        ),
        {"counselor_id": assigned_counselor_user_id},
    ).all()
    return tuple(
        {
            "work_item_id": int(row[0]),
            "plan_version_id": int(row[1]),
            "patient_id": str(row[2]),
            "criterion_id": str(row[3]),
            "return_comment": str(row[4]),
            "returned_by_username": str(row[5]),
            "returned_at": str(row[6]),
        }
        for row in rows
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


def save_returned_correction_work_item(
    db: Session,
    *,
    patient_id: str,
    criterion_id: str,
    comment: str,
    counselor_username: str,
    actor: User,
) -> None:
    rows = db.execute(
        text(
            """SELECT DISTINCT plan.id,counselor.id FROM treatment_plan_versions plan
            JOIN patients patient ON patient.id=plan.patient_id
            JOIN users counselor ON counselor.role='counselor'
            LEFT JOIN patient_assignments assignment
                ON assignment.patient_id=patient.id AND assignment.counselor_user_id=counselor.id
                AND assignment.is_active=1
            WHERE patient.canonical_client_id=:patient_id
                AND ((:username<>'' AND counselor.username=:username) OR (:username='' AND assignment.patient_id IS NOT NULL))
            ORDER BY plan.version_ordinal DESC,plan.id DESC LIMIT 2"""
        ),
        {"username": counselor_username, "patient_id": patient_id},
    ).all()
    if len(rows) != 1:
        raise CorrectionAssignmentError("Exactly one assigned counselor is required")
    row = rows[0]
    created_at = utc_now().isoformat()
    disposition = db.execute(
        text(
            """INSERT INTO manager_dispositions(
                plan_version_id,criterion_id,status,comment,actor_user_id,created_at
            ) VALUES(:plan_version_id,:criterion_id,'return_for_correction',:comment,:actor_id,:created_at)"""
        ),
        {
            "plan_version_id": int(row[0]),
            "criterion_id": criterion_id,
            "comment": comment,
            "actor_id": actor.id,
            "created_at": created_at,
        },
    )
    idempotency_key = hashlib.sha256(
        f"{row[0]}:{criterion_id}:{row[1]}:{created_at}".encode("utf-8")
    ).hexdigest()
    db.execute(
        text(
            """INSERT INTO correction_work_items(
                plan_version_id,criterion_id,disposition_id,assigned_counselor_user_id,status,opened_at,idempotency_key
            ) VALUES(:plan_version_id,:criterion_id,:disposition_id,:counselor_id,'open',:opened_at,:idempotency_key)"""
        ),
        {
            "plan_version_id": int(row[0]),
            "criterion_id": criterion_id,
            "disposition_id": int(disposition.lastrowid),
            "counselor_id": int(row[1]),
            "opened_at": created_at,
            "idempotency_key": idempotency_key,
        },
    )
    db.commit()


def correction_work_item_is_open_for(
    db: Session,
    *,
    work_item_id: int,
    patient_id: str,
    criterion_id: str,
    counselor_user_id: int,
) -> bool:
    row = db.execute(
        text(
            """SELECT correction.id FROM correction_work_items correction
            JOIN treatment_plan_versions plan ON plan.id=correction.plan_version_id
            JOIN patients patient ON patient.id=plan.patient_id
            WHERE correction.id=:work_item_id AND patient.canonical_client_id=:patient_id
                AND correction.criterion_id=:criterion_id
                AND correction.assigned_counselor_user_id=:counselor_id
                AND correction.status IN ('open','returned') LIMIT 1"""
        ),
        {"work_item_id": work_item_id, "patient_id": patient_id, "criterion_id": criterion_id, "counselor_id": counselor_user_id},
    ).first()
    return row is not None


def close_correction_work_item(
    db: Session,
    *,
    work_item_id: int,
    patient_id: str,
    criterion_id: str,
    counselor_user_id: int,
) -> None:
    db.execute(
        text(
            """UPDATE correction_work_items SET status='submitted',closed_at=:closed_at
            WHERE id IN (
                SELECT correction.id FROM correction_work_items correction
                JOIN treatment_plan_versions plan ON plan.id=correction.plan_version_id
                JOIN patients patient ON patient.id=plan.patient_id
                WHERE correction.id=:work_item_id AND patient.canonical_client_id=:patient_id
                    AND correction.criterion_id=:criterion_id
                    AND correction.assigned_counselor_user_id=:counselor_id
                    AND correction.status IN ('open','returned')
            )"""
        ),
        {
            "closed_at": utc_now().isoformat(),
            "work_item_id": work_item_id,
            "patient_id": patient_id,
            "criterion_id": criterion_id,
            "counselor_id": counselor_user_id,
        },
    )
    db.commit()


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
