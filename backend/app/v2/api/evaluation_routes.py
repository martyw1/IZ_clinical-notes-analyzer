from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from app.v2.api.deps import DbSession, ManagerUser
from app.v2.authorization import resolve_plan_version, PlanVersionSelector
from app.v2.domain.schemas import SourceMode
from app.v2.services.audit_store import record_audit_event
from app.v2.services.evaluation_store import refresh_plan_version
from app.v2.services.rule_package import RuleConfigurationError

router = APIRouter()


class EvaluationRefreshOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["evaluated"]
    patient_id: str
    plan_version_id: int
    patient_record_id: int
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
    plan_version_id: int | None = None,
    patient_record_id: int | None = None,
    source_mode: SourceMode | None = None,
    treatment_plan_id: str | None = None,
) -> EvaluationRefreshOut:
    identity = resolve_plan_version(db, user, PlanVersionSelector(patient_id, plan_version_id, patient_record_id, source_mode, treatment_plan_id), manager=True)
    try:
        refreshed = refresh_plan_version(db, identity.plan_version_id, "authorized_refresh", commit=False)
    except RuleConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    record_audit_event(
        db, action="treatment_plan.evaluation.refreshed", actor=user,
        target_entity_type="treatment_plan_version", target_entity_id=str(identity.plan_version_id),
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
        plan_version_id=identity.plan_version_id, patient_record_id=identity.patient_record_id,
        evaluation_date=refreshed.evaluation_date, facility_timezone=refreshed.facility_timezone,
        checklist_version=refreshed.checklist_version, rules_version=refreshed.rules_version,
    )
