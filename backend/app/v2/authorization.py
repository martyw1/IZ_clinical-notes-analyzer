from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.v2.models import User
from app.v2.services.audit_store import record_audit_event


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


def accessible_patient_ids(db: Session, user: User) -> frozenset[str]:
    if user.role in {Role.ADMIN.value, Role.OFFICE_MANAGER.value, Role.VIEWER.value}:
        rows = db.execute(
            text(
                """SELECT DISTINCT patient.canonical_client_id
                FROM patients patient
                JOIN user_facilities mapping ON mapping.facility_id=patient.facility_id
                WHERE mapping.user_id=:user_id"""
            ),
            {"user_id": user.id},
        ).all()
        return frozenset(str(row[0]) for row in rows)
    if user.role == Role.COUNSELOR.value:
        rows = db.execute(
            text(
                """SELECT DISTINCT patient.canonical_client_id
                FROM patients patient
                LEFT JOIN patient_assignments assignment
                    ON assignment.patient_id=patient.id
                    AND assignment.counselor_user_id=:user_id
                    AND assignment.is_active=1
                LEFT JOIN treatment_plan_versions plan ON plan.patient_id=patient.id
                LEFT JOIN correction_work_items correction
                    ON correction.plan_version_id=plan.id
                    AND correction.assigned_counselor_user_id=:user_id
                    AND correction.status IN ('open','returned')
                WHERE assignment.patient_id IS NOT NULL OR correction.id IS NOT NULL"""
            ),
            {"user_id": user.id},
        ).all()
        return frozenset(str(row[0]) for row in rows)
    deny(db, user, family="patient_read")


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
        deny(db, user, family="patient_read", target_id=patient_id)
    return scope


def require_patient_manager(db: Session, user: User, patient_id: str) -> PatientScope:
    require_role(db, user, frozenset({Role.ADMIN, Role.OFFICE_MANAGER}), "patient_manager")
    return require_patient_read(db, user, patient_id)
