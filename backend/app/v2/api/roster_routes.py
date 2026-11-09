from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal
from sqlalchemy import select

from app.v2.models import AppSetting
from app.v2.services.deterministic_evaluator import facility_local_date

from app.v2.api.plan_models import CounselorDirectoryItemOut
from app.v2.services.imported_counselors import counselor_directory_for_records

from app.v2.api.deps import CurrentUser, DbSession, ManagerUser
from app.v2.api.models import (
    PatientRosterOut, PatientRosterItemOut, PatientRosterTreatmentPlanOut,
    TreatmentPlanRosterOut, TreatmentPlanRosterItemOut, PatientRecordDetailOut,
)
from app.v2.authorization import accessible_patient_record_ids
from app.v2.domain.schemas import SourceMode
from app.v2.services.audit_store import record_audit_event
from app.v2.services.patient_record import PatientRecordSelector, patient_record_detail
from app.v2.services.patient_roster import list_patient_roster, list_treatment_plan_roster

router = APIRouter()


@router.get("/api/v2/patient-roster", response_model=PatientRosterOut)
def patient_roster(user: CurrentUser, db: DbSession, source_mode: SourceMode | None = None, primary_clinician_id: int | None = Query(default=None, ge=0)) -> PatientRosterOut:
    items = list_patient_roster(db, _clinician_scope(db, user, primary_clinician_id), source_mode)
    directory = counselor_directory_for_records(db, tuple(item.patient_record_id for item in items))
    return PatientRosterOut(
        items=tuple(PatientRosterItemOut.model_validate(item, from_attributes=True) for item in items),
        counselors=tuple(CounselorDirectoryItemOut(id=key, name=name) for key, name in sorted(directory.items())),
    )


@router.get("/api/v2/treatment-plan-roster", response_model=TreatmentPlanRosterOut)
def treatment_plan_roster(user: CurrentUser, db: DbSession, source_mode: SourceMode | None = None, primary_clinician_id: int | None = Query(default=None, ge=0)) -> TreatmentPlanRosterOut:
    facility_timezone = db.execute(select(AppSetting.facility_timezone)).scalar_one()
    today = facility_local_date(datetime.now(timezone.utc), facility_timezone)
    items = list_treatment_plan_roster(db, _clinician_scope(db, user, primary_clinician_id), source_mode, today)
    return TreatmentPlanRosterOut(items=tuple(TreatmentPlanRosterItemOut.model_validate(item, from_attributes=True) for item in items))


@router.get("/api/v2/patients/{patient_id}", response_model=PatientRecordDetailOut)
def patient_detail(
    patient_id: str,
    user: CurrentUser,
    db: DbSession,
    source_mode: SourceMode | None = None,
    patient_record_id: int | None = None,
) -> PatientRecordDetailOut:
    detail = patient_record_detail(db, user, PatientRecordSelector(patient_id, patient_record_id, source_mode))
    record_audit_event(
        db,
        action="patient_record.detail.viewed",
        actor=user,
        target_entity_type="patient",
        target_entity_id=str(detail.patient_row_id),
        details={
            "snapshot_id": detail.snapshot_id,
            "snapshot_version_count": detail.snapshot_version_count,
            "field_count": detail.field_count,
        },
    )
    return PatientRecordDetailOut(
        patient_record_id=detail.patient_row_id,
        mrn=detail.mrn,
        full_name=detail.full_name,
        source_mode=detail.source_mode,
        lifecycle_state=detail.lifecycle_state,
        current_level_of_care=detail.current_level_of_care,
        source_last_updated=detail.source_last_updated,
        first_seen_at=detail.first_seen_at,
        last_seen_at=detail.last_seen_at,
        reconciled_at=detail.reconciled_at,
        treatment_plans=tuple(
            PatientRosterTreatmentPlanOut.model_validate(plan, from_attributes=True)
            for plan in detail.treatment_plans
        ),
        patient_record=detail.patient_record,
    )


@router.get("/api/v2/clinicians")
def clinician_directory(user: CurrentUser, db: DbSession) -> dict:
    # Directory reads must not decrypt and reevaluate every saved treatment plan.
    from sqlalchemy import text
    allowed = accessible_patient_record_ids(db, user)
    patient_ids = tuple(int(row[0]) for row in db.execute(text("SELECT id FROM patients"))
                        if allowed is None or int(row[0]) in allowed)
    directory = counselor_directory_for_records(db, patient_ids)
    last_import = None
    if user.role in {"admin", "office_manager"}:
        import json
        from app.v2.models import AuditLog
        event = db.scalar(select(AuditLog).where(AuditLog.action.in_(["alleva.clinicians.pull.started", "alleva.clinicians.pull.completed", "alleva.clinicians.pull.failed"])).order_by(AuditLog.id.desc()).limit(1))
        if event:
            last_import = {"state": event.action.rsplit(".", 1)[-1], "at": event.timestamp_utc.isoformat(), "summary": json.loads(event.details_json)}
    connected = False
    staff_roles = {}
    facility_states = {}
    if user.role in {"admin", "office_manager", "viewer"}:
        rows = db.execute(text(
            "SELECT DISTINCT c.id,c.display_name,f.source_role FROM imported_counselors c "
            "JOIN imported_clinician_facilities f ON f.counselor_id=c.id "
            "JOIN user_facilities u ON u.facility_id=f.facility_id WHERE u.user_id=:user_id"
        ), {"user_id": user.id}).all()
        directory.update({key: name for key, name, role in rows})
        staff_roles = {key: role for key, name, role in rows}
        connected = bool(rows)
    # Incomplete staff are reviewable by admins without granting any facility membership.
    if user.role == "admin":
        incomplete = db.execute(text("SELECT c.id,c.display_name,d.source_role,d.facility_status "
            "FROM imported_counselors c JOIN imported_clinician_directory_records d ON d.counselor_id=c.id "
            "WHERE d.facility_status IN ('missing','unmapped')")).all()
        directory.update({key: name for key, name, role, state in incomplete})
        staff_roles.update({key: role for key, name, role, state in incomplete})
        facility_states.update({key: state for key, name, role, state in incomplete})
        connected = connected or bool(incomplete)
    if directory:
        from app.v2.models import ImportedClinicianDirectoryRecord
        for start in range(0, len(directory), 400):
            keys = tuple(directory)[start:start+400]
            records = db.execute(select(ImportedClinicianDirectoryRecord.counselor_id, ImportedClinicianDirectoryRecord.facility_status, ImportedClinicianDirectoryRecord.source_role).where(ImportedClinicianDirectoryRecord.counselor_id.in_(keys))).all()
            facility_states.update({key: state for key, state, role in records})
            staff_roles.update({key: role for key, state, role in records})

    return {"items": [{"id": key, "name": name, "source_role": staff_roles.get(key, ""), "facility_status": facility_states.get(key, "unknown")} for key, name in sorted(directory.items(), key=lambda row: (row[1].casefold(), row[0]))],
            "coverage": "imported_staff_and_patient_assignments", "master_directory_connected": connected, "last_import": last_import}


def _clinician_scope(db, user, clinician_id):
    from app.v2.services.imported_counselors import primary_counselors_for_records
    allowed = accessible_patient_record_ids(db, user)
    if clinician_id is None:
        return allowed
    assignments = primary_counselors_for_records(db, tuple(allowed))
    return frozenset(patient_id for patient_id in allowed if assignments.get(patient_id, (0, ""))[0] == clinician_id)


class ClinicianAssignmentSearch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(default="", max_length=120)


class ClinicianAssignmentWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["local", "source"] = "local"
    clinician_id: int | None = Field(default=None, strict=True, gt=0)
    expected_revision: int = Field(ge=0, strict=True)


def _assignment_state(db, patient_record_id):
    from app.v2.models import LocalClinicianAssignment, ImportedPrimaryCounselor, ImportedCounselor
    from app.v2.services.imported_counselors import primary_counselors_for_records
    local = db.get(LocalClinicianAssignment, patient_record_id)
    source = db.get(ImportedPrimaryCounselor, patient_record_id)
    effective = primary_counselors_for_records(db, (patient_record_id,)).get(patient_record_id)
    source_clinician = db.get(ImportedCounselor, source.counselor_id) if source and source.counselor_id is not None else None
    return {"patient_record_id": patient_record_id, "clinician_id": effective[0] if effective else None,
        "clinician_name": effective[1] if effective else "", "origin": "local" if local and local.is_active else "source" if effective else "unassigned",
        "source_clinician_id": source.counselor_id if source else None, "source_clinician_name": source_clinician.display_name if source_clinician else "", "revision": local.revision if local else 0}


@router.post("/api/v2/clinician-assignment/patients/search")
def clinician_assignment_patients(payload: ClinicianAssignmentSearch, user: ManagerUser, db: DbSession) -> dict:
    from sqlalchemy import text
    from app.v2.services.patient_snapshot_store import patient_source_snapshots_for_records
    allowed = accessible_patient_record_ids(db, user)
    snapshots = patient_source_snapshots_for_records(db, tuple(allowed))
    query = payload.query.strip().casefold()
    matches = []
    for row in db.execute(text("SELECT id,canonical_client_id,source_system FROM patients ORDER BY canonical_client_id,id")):
        if row.id not in allowed:
            continue
        snapshot = snapshots.get(row.id)
        name = snapshot.full_name if snapshot else ""
        if query and query not in name.casefold() and query not in row.canonical_client_id.casefold():
            continue
        matches.append({"patient_record_id": row.id, "mrn": row.canonical_client_id, "full_name": name,
            "source_mode": row.source_system, **_assignment_state(db, row.id)})
        if len(matches) == 26:
            break
    return {"items": matches[:25], "has_more": len(matches)>25}


@router.get("/api/v2/patient-records/{patient_record_id}/clinician-assignment")
def get_clinician_assignment(patient_record_id: int, user: ManagerUser, db: DbSession) -> dict:
    from app.v2.authorization import require_patient_row_read
    require_patient_row_read(db, user, patient_record_id)
    return _assignment_state(db, patient_record_id)


@router.put("/api/v2/patient-records/{patient_record_id}/clinician-assignment")
def set_clinician_assignment(patient_record_id: int, payload: ClinicianAssignmentWrite, user: ManagerUser, db: DbSession) -> dict:
    from sqlalchemy.dialects.sqlite import insert
    from app.v2.authorization import require_patient_row_read
    from app.v2.models import LocalClinicianAssignment, ImportedCounselorObservation
    require_patient_row_read(db, user, patient_record_id)
    if payload.mode == "source" and payload.clinician_id is not None:
        raise HTTPException(status_code=400, detail="Use Alleva assignment does not accept a local clinician.")
    if payload.clinician_id is not None:
        visible = {item['id'] for item in clinician_directory(user, db)['items']}
        if payload.clinician_id not in visible:
            raise HTTPException(status_code=403, detail="This clinician is not available in your directory.")
    existing = db.get(LocalClinicianAssignment, patient_record_id)
    if (existing.revision if existing else 0) != payload.expected_revision:
        raise HTTPException(status_code=409, detail="This assignment changed. Refresh the patient selection before saving.")
    now = datetime.now(timezone.utc).isoformat()
    values = {"patient_record_id": patient_record_id, "counselor_id": payload.clinician_id,
        "is_active": payload.mode == "local", "revision": payload.expected_revision+1,
        "assigned_by_user_id": user.id, "assigned_at_utc": now}
    statement = insert(LocalClinicianAssignment).values(**values)
    result = db.execute(statement.on_conflict_do_update(index_elements=['patient_record_id'],
        set_={key:value for key,value in values.items() if key != 'patient_record_id'},
        where=LocalClinicianAssignment.revision == payload.expected_revision))
    if not result.rowcount:
        raise HTTPException(status_code=409, detail="This assignment changed. Refresh before saving.")
    if payload.mode == "local" and payload.clinician_id is not None:
        db.execute(insert(ImportedCounselorObservation).values(patient_record_id=patient_record_id,
            counselor_id=payload.clinician_id).on_conflict_do_nothing())
    record_audit_event(db, action="clinician.assignment.local_saved" if payload.mode == "local" else "clinician.assignment.source_restored",
        actor=user, target_entity_type="patient_record", target_entity_id=str(patient_record_id),
        details={"local_assignment": payload.mode == "local", "clinician_record_id": payload.clinician_id,
            "revision": payload.expected_revision+1}, commit=False)
    db.commit()
    db.expire_all()
    return _assignment_state(db, patient_record_id)
