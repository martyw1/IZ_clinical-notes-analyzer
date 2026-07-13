from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.v2.services.treatment_plan_store import StoredTreatmentPlan, list_treatment_plan_imports


@dataclass(frozen=True, slots=True)
class PatientRosterItem:
    patient_id: str
    source_mode: str
    lifecycle_state: str
    current_level_of_care: str
    treatment_plan_id: str
    treatment_plan_status: str
    first_seen_at: str
    last_seen_at: str
    reconciled_at: str


def list_patient_roster(db: Session) -> tuple[PatientRosterItem, ...]:
    plans_by_patient = {plan.patient_id: plan for plan in list_treatment_plan_imports(db)}
    rows = db.execute(
        text(
            "SELECT canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at,reconciled_at "
            "FROM patients ORDER BY lifecycle_state,canonical_client_id,source_system"
        )
    ).all()
    return tuple(
        _roster_item(
            patient_id=str(row[0]),
            source_mode=str(row[1]),
            lifecycle_state=str(row[2]),
            first_seen_at=str(row[3]),
            last_seen_at=str(row[4]),
            reconciled_at=str(row[5] or ""),
            plan=plans_by_patient.get(str(row[0])),
        )
        for row in rows
    )


def _roster_item(
    *,
    patient_id: str,
    source_mode: str,
    lifecycle_state: str,
    first_seen_at: str,
    last_seen_at: str,
    reconciled_at: str,
    plan: StoredTreatmentPlan | None,
) -> PatientRosterItem:
    return PatientRosterItem(
        patient_id=patient_id,
        source_mode=source_mode,
        lifecycle_state=lifecycle_state,
        current_level_of_care=plan.current_level_of_care if plan else "Unknown",
        treatment_plan_id=plan.plan_id if plan else "",
        treatment_plan_status=plan.overall_status if plan else "No treatment plan",
        first_seen_at=first_seen_at,
        last_seen_at=last_seen_at,
        reconciled_at=reconciled_at,
    )
