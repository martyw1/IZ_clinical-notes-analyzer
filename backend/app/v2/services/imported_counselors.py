"""Current assignments from explicitly mapped source evidence."""
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import case, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.v2.models import ImportedCounselor, ImportedCounselorObservation, ImportedPrimaryCounselor, LocalClinicianAssignment


@dataclass(frozen=True, slots=True)
class PrimaryCounselorEvidence:
    source_scope: str
    staff_id: str
    display_name: str


def save_primary_counselor(
    db: Session, patient_record_id: int, evidence: PrimaryCounselorEvidence, source_updated_at: str,
) -> None:
    try:
        observed = datetime.fromisoformat(source_updated_at.replace("Z", "+00:00"))
    except ValueError:
        return
    if observed.tzinfo is None or not evidence.source_scope:
        return
    updated = observed.astimezone(timezone.utc).isoformat(timespec="microseconds")
    counselor_id = None
    if evidence.staff_id and evidence.display_name:
        statement = insert(ImportedCounselor).values(
            source_scope=evidence.source_scope, staff_id=evidence.staff_id, display_name=evidence.display_name,
        ).on_conflict_do_nothing(index_elements=["source_scope", "staff_id"])
        db.execute(statement)
        counselor_id = db.scalar(select(ImportedCounselor.id).where(
            ImportedCounselor.source_scope == evidence.source_scope,
            ImportedCounselor.staff_id == evidence.staff_id,
        ))

    if counselor_id is not None:
        db.execute(insert(ImportedCounselorObservation).values(
            patient_record_id=patient_record_id, counselor_id=counselor_id,
        ).on_conflict_do_nothing())

    statement = insert(ImportedPrimaryCounselor).values(
        patient_record_id=patient_record_id, counselor_id=counselor_id, source_updated_at=updated,
    )
    db.execute(statement.on_conflict_do_update(
        index_elements=["patient_record_id"],
        set_={
            "counselor_id": case(
                (ImportedPrimaryCounselor.source_updated_at < updated, counselor_id),
                (ImportedPrimaryCounselor.counselor_id.is_(counselor_id), counselor_id),
                else_=None,
            ),
            "source_updated_at": updated,
        },
        where=ImportedPrimaryCounselor.source_updated_at <= updated,
    ))


def primary_counselors_for_records(db: Session, patient_ids: tuple[int, ...]) -> dict[int, tuple[int, str]]:
    result = {}
    for start in range(0, len(patient_ids), 400):
        rows = db.execute(select(
            ImportedPrimaryCounselor.patient_record_id, ImportedCounselor.id, ImportedCounselor.display_name,
        ).join(ImportedCounselor, ImportedCounselor.id == ImportedPrimaryCounselor.counselor_id).where(
            ImportedPrimaryCounselor.patient_record_id.in_(patient_ids[start:start + 400]),
        ))
        result.update({patient_id: (counselor_id, name) for patient_id, counselor_id, name in rows})
        overrides = db.execute(select(LocalClinicianAssignment.patient_record_id, LocalClinicianAssignment.counselor_id, ImportedCounselor.display_name)
            .outerjoin(ImportedCounselor, ImportedCounselor.id == LocalClinicianAssignment.counselor_id)
            .where(LocalClinicianAssignment.patient_record_id.in_(patient_ids[start:start+400]), LocalClinicianAssignment.is_active.is_(True)))
        for patient_id, counselor_id, name in overrides:
            result.pop(patient_id, None)
            if counselor_id is not None:
                result[patient_id] = (counselor_id, name)
    return result


def counselor_directory_for_records(db: Session, patient_ids: tuple[int, ...]) -> dict[int, str]:
    result = {}
    for start in range(0, len(patient_ids), 400):
        result.update(db.execute(select(ImportedCounselor.id, ImportedCounselor.display_name)
            .join(ImportedCounselorObservation, ImportedCounselorObservation.counselor_id == ImportedCounselor.id)
            .where(ImportedCounselorObservation.patient_record_id.in_(patient_ids[start:start + 400]))
            .distinct()).all())
    return result
