from __future__ import annotations

from fastapi import APIRouter

from app.v2.api.deps import CurrentUser, DbSession
from app.v2.api.models import PatientRosterOut, TreatmentPlanRosterOut
from app.v2.authorization import accessible_patient_ids
from app.v2.services.patient_roster import list_patient_roster, list_treatment_plan_roster

router = APIRouter()


@router.get("/api/v2/patient-roster", response_model=PatientRosterOut)
def patient_roster(user: CurrentUser, db: DbSession) -> PatientRosterOut:
    allowed_ids = accessible_patient_ids(db, user)
    items = tuple(item for item in list_patient_roster(db) if item.mrn in allowed_ids)
    return PatientRosterOut(
        items=tuple(
            {
                "mrn": item.mrn,
                "source_mode": item.source_mode,
                "lifecycle_state": item.lifecycle_state,
                "current_level_of_care": item.current_level_of_care,
                "treatment_plans": tuple(
                    {
                        "treatment_plan_id": plan.treatment_plan_id,
                        "last_updated": plan.last_updated,
                    }
                    for plan in item.treatment_plans
                ),
                "first_seen_at": item.first_seen_at,
                "last_seen_at": item.last_seen_at,
                "reconciled_at": item.reconciled_at,
            }
            for item in items
        )
    )


@router.get("/api/v2/treatment-plan-roster", response_model=TreatmentPlanRosterOut)
def treatment_plan_roster(user: CurrentUser, db: DbSession) -> TreatmentPlanRosterOut:
    allowed_ids = accessible_patient_ids(db, user)
    return TreatmentPlanRosterOut(
        items=tuple(
            {
                "treatment_plan_id": item.treatment_plan_id,
                "mrn": item.mrn,
                "last_updated": item.last_updated,
                "previous_treatment_plan_id": item.previous_treatment_plan_id,
                "initial_treatment_plan_id": item.initial_treatment_plan_id,
                "initial_treatment_plan_date": item.initial_treatment_plan_date,
            }
            for item in list_treatment_plan_roster(db)
            if item.mrn in allowed_ids
        )
    )
