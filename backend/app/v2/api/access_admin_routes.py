from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.v2.api.deps import AdminUser, CurrentUser, DbSession
from app.v2.api.models import AssignmentOut, FacilityOut
from app.v2.authorization import Role, facility_ids_for_user, require_role
from app.v2.models import User
from app.v2.services.audit_store import record_audit_event

router = APIRouter()


@router.get("/api/facilities", response_model=tuple[FacilityOut, ...])
def list_facilities(actor: CurrentUser, db: DbSession) -> tuple[FacilityOut, ...]:
    require_role(db, actor, frozenset({Role.ADMIN, Role.OFFICE_MANAGER}), "facility_summary")
    if actor.role == Role.ADMIN.value:
        rows = db.execute(
            text("SELECT id,facility_key,display_name,timezone,is_active FROM facilities ORDER BY display_name")
        ).all()
    else:
        rows = db.execute(
            text(
                """SELECT facility.id,facility.facility_key,facility.display_name,facility.timezone,facility.is_active
                FROM facilities facility JOIN user_facilities mapping ON mapping.facility_id=facility.id
                WHERE mapping.user_id=:user_id ORDER BY facility.display_name"""
            ),
            {"user_id": actor.id},
        ).all()
    return tuple(
        FacilityOut(
            id=int(row[0]),
            facility_key=str(row[1]),
            display_name=str(row[2]),
            timezone=str(row[3]),
            is_active=bool(row[4]),
        )
        for row in rows
    )


@router.put("/api/users/{user_id}/facilities/{facility_id}", response_model=tuple[int, ...])
def assign_user_facility(user_id: int, facility_id: int, actor: AdminUser, db: DbSession) -> tuple[int, ...]:
    target = db.get(User, user_id)
    facility = db.execute(text("SELECT id FROM facilities WHERE id=:facility_id"), {"facility_id": facility_id}).first()
    if target is None or facility is None:
        raise HTTPException(status_code=404, detail="User or facility not found")
    db.execute(
        text(
            """INSERT OR IGNORE INTO user_facilities(user_id,facility_id,assigned_by_user_id,assigned_at)
            VALUES(:user_id,:facility_id,:actor_id,:assigned_at)"""
        ),
        {
            "user_id": target.id,
            "facility_id": facility_id,
            "actor_id": actor.id,
            "assigned_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    db.commit()
    record_audit_event(
        db,
        action="user.facility.assigned",
        actor=actor,
        target_entity_type="user",
        target_entity_id=str(target.id),
        details={"facility_id": facility_id},
    )
    return facility_ids_for_user(db, target.id)


@router.put("/api/patient-assignments/{patient_id}/{counselor_username}", response_model=AssignmentOut)
def assign_patient(
    patient_id: str,
    counselor_username: str,
    actor: AdminUser,
    db: DbSession,
) -> AssignmentOut:
    counselor = db.execute(
        text("SELECT id,role FROM users WHERE username=:username"), {"username": counselor_username}
    ).first()
    patient = db.execute(
        text("SELECT id FROM patients WHERE canonical_client_id=:patient_id ORDER BY id LIMIT 1"),
        {"patient_id": patient_id},
    ).first()
    if counselor is None or patient is None:
        raise HTTPException(status_code=404, detail="Counselor or patient not found")
    if str(counselor[1]) != Role.COUNSELOR.value:
        raise HTTPException(status_code=400, detail="Patient assignments require a counselor")
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        text(
            """INSERT OR IGNORE INTO patient_assignments(
                patient_id,counselor_user_id,assigned_by_user_id,assigned_at,is_active
            ) VALUES(:patient_id,:counselor_id,:actor_id,:assigned_at,1)"""
        ),
        {"patient_id": int(patient[0]), "counselor_id": int(counselor[0]), "actor_id": actor.id, "assigned_at": now},
    )
    db.commit()
    record_audit_event(
        db,
        action="patient.assignment.created",
        actor=actor,
        target_entity_type="patient",
        target_entity_id=patient_id,
        details={"counselor_user_id": int(counselor[0])},
    )
    return AssignmentOut(patient_id=patient_id, counselor_username=counselor_username, is_active=True)
