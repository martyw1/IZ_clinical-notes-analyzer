from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal, TypedDict

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.v2.models import User, utc_now
from app.v2.services.treatment_plan_types import PlanVersionIdentity


@dataclass(frozen=True, slots=True)
class CorrectionAssignmentError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class CorrectionWorkItem:
    work_item_id: int
    identity: PlanVersionIdentity
    criterion_id: str
    counselor_user_id: int
    facility_id: int
    status: str


class OpenCorrection(TypedDict):
    work_item_id: int
    plan_version_id: int
    patient_record_id: int
    patient_id: str
    source_mode: str
    treatment_plan_id: str
    criterion_id: str
    return_comment: str
    returned_by_username: str
    returned_at: str


def linked_correction_work_item_predicate(alias: Literal["correction", "c"] = "correction") -> str:
    return f"""EXISTS (
        SELECT 1 FROM manager_action_plan_links action_link
        JOIN treatment_plan_manager_actions linked_action ON linked_action.id=action_link.action_id
        JOIN manager_dispositions linked_disposition ON linked_disposition.id={alias}.disposition_id
        JOIN treatment_plan_versions linked_version ON linked_version.id=action_link.plan_version_id
        JOIN patients linked_patient ON linked_patient.id=linked_version.patient_id
        WHERE action_link.plan_version_id={alias}.plan_version_id
            AND linked_action.patient_id=linked_patient.canonical_client_id
            AND linked_action.action='return_for_correction'
            AND linked_action.criterion_id={alias}.criterion_id
            AND linked_disposition.plan_version_id={alias}.plan_version_id
            AND linked_disposition.status='return_for_correction'
            AND linked_disposition.criterion_id={alias}.criterion_id
            AND linked_disposition.comment=linked_action.comment
            AND linked_disposition.actor_user_id=CAST(linked_action.actor_user_id AS INTEGER)
            AND (
                {alias}.idempotency_key='manager-action:' || linked_action.id
                OR (
                    {alias}.idempotency_key NOT LIKE 'manager-action:%'
                    AND julianday(linked_action.created_at)<=julianday({alias}.opened_at)
                    AND 1=(SELECT COUNT(*) FROM treatment_plan_manager_actions candidate
                        WHERE candidate.patient_id=linked_patient.canonical_client_id
                            AND candidate.criterion_id={alias}.criterion_id
                            AND candidate.action='return_for_correction'
                            AND candidate.comment=linked_disposition.comment
                            AND CAST(candidate.actor_user_id AS INTEGER)=linked_disposition.actor_user_id
                            AND julianday(candidate.created_at)<=julianday({alias}.opened_at))
                )
            )
    )"""


def open_correction_dicts(
    db: Session, *, assigned_counselor_user_id: int | None = None,
) -> tuple[OpenCorrection, ...]:
    rows = db.execute(text(
        "SELECT c.id,c.plan_version_id,p.id,p.canonical_client_id,v.source_system,v.source_record_id,"
        "c.criterion_id,d.comment,u.username,c.opened_at FROM correction_work_items c "
        "JOIN treatment_plan_versions v ON v.id=c.plan_version_id JOIN patients p ON p.id=v.patient_id "
        "JOIN manager_dispositions d ON d.id=c.disposition_id JOIN users u ON u.id=d.actor_user_id "
        "WHERE c.status IN ('open','returned') AND (:counselor_id IS NULL OR c.assigned_counselor_user_id=:counselor_id) "
        f"AND {linked_correction_work_item_predicate('c')} "
        "ORDER BY c.opened_at,c.id"
    ), {"counselor_id": assigned_counselor_user_id}).all()
    return tuple(
        {"work_item_id": int(row[0]), "plan_version_id": int(row[1]), "patient_record_id": int(row[2]),
         "patient_id": str(row[3]), "source_mode": str(row[4]), "treatment_plan_id": str(row[5]),
         "criterion_id": str(row[6]), "return_comment": str(row[7]),
         "returned_by_username": str(row[8]), "returned_at": str(row[9])}
        for row in rows
    )


def open_correction_counts_by_patient(db: Session) -> Counter[str]:
    return Counter(item["patient_id"] for item in open_correction_dicts(db))


def open_correction_counts_by_version(db: Session) -> Counter[int]:
    return Counter(item["plan_version_id"] for item in open_correction_dicts(db))


def correction_work_item_for_id(db: Session, work_item_id: int) -> CorrectionWorkItem | None:
    row = db.execute(text(
        "SELECT c.id,v.id,p.id,p.canonical_client_id,v.source_system,v.source_record_id,"
        "c.criterion_id,c.assigned_counselor_user_id,p.facility_id,c.status FROM correction_work_items c "
        "JOIN treatment_plan_versions v ON v.id=c.plan_version_id JOIN patients p ON p.id=v.patient_id "
        f"WHERE c.id=:work_item_id AND {linked_correction_work_item_predicate('c')}"
    ), {"work_item_id": work_item_id}).first()
    if row is None:
        return None
    return CorrectionWorkItem(
        int(row[0]), PlanVersionIdentity(int(row[1]), int(row[2]), str(row[3]), str(row[4]), str(row[5])),
        str(row[6]), int(row[7]), int(row[8]), str(row[9]),
    )


def close_correction_work_item(db: Session, item: CorrectionWorkItem, *, commit: bool = True) -> bool:
    result = db.execute(text(
        "UPDATE correction_work_items SET status='submitted',closed_at=:closed_at "
        "WHERE id=:work_item_id AND plan_version_id=:version_id AND criterion_id=:criterion_id "
        "AND assigned_counselor_user_id=:counselor_id AND status IN ('open','returned')"
    ), {"closed_at": utc_now().isoformat(), "work_item_id": item.work_item_id,
        "version_id": item.identity.plan_version_id, "criterion_id": item.criterion_id,
        "counselor_id": item.counselor_user_id})
    if commit:
        db.commit()
    return result.rowcount == 1


def save_returned_correction_work_item(
    db: Session,
    *,
    patient_id: str,
    plan_version_id: int,
    manager_action_id: int,
    criterion_id: str,
    comment: str,
    counselor_username: str,
    actor: User,
    commit: bool = True,
) -> None:
    rows = db.execute(text(
        "SELECT DISTINCT counselor.id FROM treatment_plan_versions plan "
        "JOIN patients patient ON patient.id=plan.patient_id "
        "JOIN manager_action_plan_links action_link ON action_link.plan_version_id=plan.id AND action_link.action_id=:action_id "
        "JOIN treatment_plan_manager_actions action ON action.id=action_link.action_id "
        "AND action.action='return_for_correction' AND action.patient_id=patient.canonical_client_id "
        "AND action.criterion_id=:criterion_id AND action.comment=:comment AND CAST(action.actor_user_id AS INTEGER)=:actor_id "
        "JOIN user_facilities mapping ON mapping.facility_id=patient.facility_id "
        "JOIN users counselor ON counselor.id=mapping.user_id AND counselor.role='counselor' AND counselor.is_active=1 "
        "LEFT JOIN patient_assignments assignment ON assignment.patient_id=patient.id "
        "AND assignment.counselor_user_id=counselor.id AND assignment.is_active=1 "
        "WHERE plan.id=:version_id AND patient.canonical_client_id=:patient_id "
        "AND ((:username<>'' AND counselor.username=:username) OR (:username='' AND assignment.patient_id IS NOT NULL)) "
        "ORDER BY counselor.id LIMIT 2"
    ), {"version_id": plan_version_id, "patient_id": patient_id, "username": counselor_username,
        "action_id": manager_action_id, "criterion_id": criterion_id, "comment": comment, "actor_id": actor.id}).all()
    if len(rows) != 1:
        raise CorrectionAssignmentError("Exactly one assigned counselor is required")
    counselor_id = int(rows[0][0])
    created_at = utc_now().isoformat()
    disposition = db.execute(text(
        "INSERT INTO manager_dispositions(plan_version_id,criterion_id,status,comment,actor_user_id,created_at) "
        "VALUES(:version_id,:criterion_id,'return_for_correction',:comment,:actor_id,:created_at)"
    ), {"version_id": plan_version_id, "criterion_id": criterion_id, "comment": comment,
        "actor_id": actor.id, "created_at": created_at})
    db.execute(text(
        "INSERT INTO correction_work_items(plan_version_id,criterion_id,disposition_id,assigned_counselor_user_id,"
        "status,opened_at,idempotency_key) "
        "VALUES(:version_id,:criterion_id,:disposition_id,:counselor_id,'open',:opened_at,:idempotency_key)"
    ), {"version_id": plan_version_id, "criterion_id": criterion_id, "disposition_id": disposition.lastrowid,
        "counselor_id": counselor_id, "opened_at": created_at, "idempotency_key": f"manager-action:{manager_action_id}"})
    if commit:
        db.commit()
