from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.v2.models import User
from app.v2.services.audit_store import record_audit_event
from app.v2.services.correction_work_item_store import linked_correction_work_item_predicate
from app.v2.services.treatment_plan_types import PlanVersionIdentity


class Role(StrEnum):
    ADMIN = "admin"
    OFFICE_MANAGER = "office_manager"
    COUNSELOR = "counselor"
    VIEWER = "viewer"


CANONICAL_ROLES: Final = tuple(role.value for role in Role)


@dataclass(frozen=True, slots=True)
class PatientScope:
    patient_row_id: int
    facility_id: int
    canonical_client_id: str


@dataclass(frozen=True, slots=True)
class PlanVersionSelector:
    patient_id: str
    plan_version_id: int | None = None
    patient_record_id: int | None = None
    source_mode: str | None = None
    treatment_plan_id: str | None = None


def deny(db: Session, user: User, *, family: str, target_id: str = "") -> None:
    record_audit_event(
        db,
        action="authorization.denied",
        actor=user,
        target_entity_type="route_family",
        target_entity_id=target_id,
        outcome_status="denied",
        details={"family": family},
    )
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def require_role(db: Session, user: User, allowed: frozenset[Role], family: str) -> User:
    if user.role not in {role.value for role in allowed}:
        deny(db, user, family=family)
    return user


def facility_ids_for_user(db: Session, user_id: int) -> tuple[int, ...]:
    rows = db.execute(
        text("SELECT facility_id FROM user_facilities WHERE user_id=:user_id ORDER BY facility_id"),
        {"user_id": user_id},
    ).all()
    return tuple(int(row[0]) for row in rows)


def accessible_patient_record_ids(db: Session, user: User) -> frozenset[int]:
    if user.role in {Role.ADMIN.value, Role.OFFICE_MANAGER.value, Role.VIEWER.value}:
        rows = db.execute(
            text(
                """SELECT DISTINCT patient.id
                FROM patients patient
                JOIN user_facilities mapping ON mapping.facility_id=patient.facility_id
                WHERE mapping.user_id=:user_id"""
            ),
            {"user_id": user.id},
        ).all()
        return frozenset(int(row[0]) for row in rows)
    if user.role == Role.COUNSELOR.value:
        rows = db.execute(
            text(
                f"""SELECT DISTINCT patient.id
                FROM patients patient
                JOIN user_facilities mapping ON mapping.facility_id=patient.facility_id AND mapping.user_id=:user_id
                LEFT JOIN patient_assignments assignment
                    ON assignment.patient_id=patient.id
                    AND assignment.counselor_user_id=:user_id
                    AND assignment.is_active=1
                LEFT JOIN treatment_plan_versions plan ON plan.patient_id=patient.id
                LEFT JOIN correction_work_items correction
                    ON correction.plan_version_id=plan.id
                    AND correction.assigned_counselor_user_id=:user_id
                    AND correction.status IN ('open','returned')
                    AND {linked_correction_work_item_predicate()}
                WHERE assignment.patient_id IS NOT NULL OR correction.id IS NOT NULL"""
            ),
            {"user_id": user.id},
        ).all()
        return frozenset(int(row[0]) for row in rows)
    deny(db, user, family="patient_read")


def accessible_patient_ids(db: Session, user: User) -> frozenset[str]:
    allowed = accessible_patient_record_ids(db, user)
    rows = db.execute(text("SELECT id,canonical_client_id FROM patients")).all()
    return frozenset(str(row[1]) for row in rows if int(row[0]) in allowed)


def require_patient_row_read(db: Session, user: User, patient_record_id: int) -> PatientScope:
    row = db.execute(text("SELECT id,facility_id,canonical_client_id FROM patients WHERE id=:id"), {"id": patient_record_id}).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Patient record not found")
    if patient_record_id not in accessible_patient_record_ids(db, user):
        deny(db, user, family="patient_read", target_id=str(patient_record_id))
    return PatientScope(int(row[0]), int(row[1]), str(row[2]))


def resolve_plan_version(
    db: Session, user: User, selector: PlanVersionSelector, *, manager: bool = False,
) -> PlanVersionIdentity:
    rows = db.execute(text(
        "SELECT v.id,p.id,p.canonical_client_id,v.source_system,v.source_record_id "
        "FROM treatment_plan_versions v JOIN patients p ON p.id=v.patient_id "
        "WHERE p.canonical_client_id=:patient_id "
        "AND (:version_id IS NULL OR v.id=:version_id) "
        "AND (:record_id IS NULL OR p.id=:record_id) "
        "AND (:source IS NULL OR v.source_system=:source) "
        "AND (:plan IS NULL OR v.source_record_id=:plan) ORDER BY v.id"
    ), {"patient_id": selector.patient_id, "version_id": selector.plan_version_id,
        "record_id": selector.patient_record_id, "source": selector.source_mode,
        "plan": selector.treatment_plan_id}).all()
    if not rows:
        raise HTTPException(status_code=404, detail="Treatment plan not found")
    if manager:
        require_role(db, user, frozenset({Role.ADMIN, Role.OFFICE_MANAGER}), "patient_manager")
    allowed = accessible_patient_record_ids(db, user)
    eligible = tuple(row for row in rows if int(row[1]) in allowed)
    if not eligible:
        deny(db, user, family="patient_read", target_id=str(rows[0][1]))
    if len(eligible) != 1:
        raise HTTPException(status_code=409, detail="Select a specific treatment-plan version.")
    row = eligible[0]
    return PlanVersionIdentity(int(row[0]), int(row[1]), str(row[2]), str(row[3]), str(row[4]))


def require_manual_patient_manager(db: Session, user: User, patient_id: str) -> PatientScope | None:
    require_role(db, user, frozenset({Role.ADMIN, Role.OFFICE_MANAGER}), "patient_manager")
    facility_id = int(db.execute(text("SELECT id FROM facilities WHERE facility_key='r3-default'")).scalar_one())
    if facility_id not in facility_ids_for_user(db, user.id):
        deny(db, user, family="patient_manager")
    row = db.execute(text(
        "SELECT id FROM patients WHERE facility_id=:facility AND source_system='manual_upload' AND canonical_client_id=:mrn"
    ), {"facility": facility_id, "mrn": patient_id}).first()
    return require_patient_row_read(db, user, int(row[0])) if row else None


def patient_scope(db: Session, patient_id: str) -> PatientScope | None:
    row = db.execute(
        text(
            """SELECT id,facility_id,canonical_client_id FROM patients
            WHERE canonical_client_id=:patient_id ORDER BY id LIMIT 1"""
        ),
        {"patient_id": patient_id},
    ).first()
    if row is None:
        return None
    return PatientScope(int(row[0]), int(row[1]), str(row[2]))


def require_patient_read(db: Session, user: User, patient_id: str) -> PatientScope:
    scope = patient_scope(db, patient_id)
    if scope is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Treatment-plan aggregate not found")
    if scope.canonical_client_id not in accessible_patient_ids(db, user):
        deny(db, user, family="patient_read", target_id=str(scope.patient_row_id))
    return scope


def require_patient_manager(db: Session, user: User, patient_id: str) -> PatientScope:
    require_role(db, user, frozenset({Role.ADMIN, Role.OFFICE_MANAGER}), "patient_manager")
    return require_patient_read(db, user, patient_id)
