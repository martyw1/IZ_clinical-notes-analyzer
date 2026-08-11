from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from app.v2.api.deps import DbSession, ManagerUser
from app.v2.authorization import require_patient_manager
from app.v2.services.audit_store import record_audit_event
from app.v2.services.evaluation_store import refresh_patient_version
from app.v2.services.rule_package import RuleConfigurationError
from app.v2.services.treatment_plan_store import treatment_plan_aggregate_for_patient

router = APIRouter()


class EvaluationRefreshOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["evaluated"]
    patient_id: str
    versions_evaluated: int
    evaluation_date: str
    facility_timezone: str
    checklist_version: str
    rules_version: str


@router.post("/api/v2/treatment-plans/{patient_id}/evaluations/refresh", response_model=EvaluationRefreshOut)
def refresh_treatment_plan_evaluation(
    patient_id: str,
    user: ManagerUser,
    db: DbSession,
) -> EvaluationRefreshOut:
    scope = require_patient_manager(db, user, patient_id)
    try:
        aggregate = treatment_plan_aggregate_for_patient(db, patient_id)
        if aggregate is None:
            raise HTTPException(status_code=404, detail="Treatment-plan aggregate not found")
        refreshed = refresh_patient_version(db, aggregate, "authorized_refresh")
    except RuleConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    record_audit_event(
        db, action="treatment_plan.evaluation.refreshed", actor=user,
        target_entity_type="patient", target_entity_id=str(scope.patient_row_id),
        details={
            "versions_evaluated": refreshed.versions_evaluated,
            "evaluation_date": refreshed.evaluation_date,
            "facility_timezone": refreshed.facility_timezone,
            "checklist_version": refreshed.checklist_version,
            "rules_version": refreshed.rules_version,
        },
    )
    return EvaluationRefreshOut(
        status="evaluated", patient_id=patient_id, versions_evaluated=refreshed.versions_evaluated,
        evaluation_date=refreshed.evaluation_date, facility_timezone=refreshed.facility_timezone,
        checklist_version=refreshed.checklist_version, rules_version=refreshed.rules_version,
    )
