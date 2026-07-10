from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.v2.api.deps import AdminUser, DbSession
from app.v2.domain.schemas import ApiHarnessJob
from app.v2.models import AppSetting
from app.v2.services.audit_store import record_audit_event
from app.v2.services.jobs import job_service

router = APIRouter()


@router.post("/api/v2/alleva-sync/run", response_model=ApiHarnessJob, status_code=202)
def run_alleva_sync(actor: AdminUser, db: DbSession) -> ApiHarnessJob:
    profile = db.execute(select(AppSetting)).scalar_one()
    blockers = _sync_blockers(profile)
    if blockers:
        record_audit_event(
            db,
            action="alleva.treatment_plan_sync.blocked",
            actor=actor,
            target_entity_type="integration_sync",
            target_entity_id="alleva_treatment_plan_sync",
            outcome_status="blocked",
            details={"blocker_count": len(blockers)},
        )
        raise HTTPException(status_code=409, detail=f"Alleva treatment-plan sync is blocked: {', '.join(blockers)}")
    record_audit_event(
        db,
        action="alleva.treatment_plan_sync.job.started",
        actor=actor,
        target_entity_type="integration_sync",
        target_entity_id="alleva_treatment_plan_sync",
    )
    return job_service.create_treatment_plan_sync_job(actor.id, actor.role)


@router.get("/api/v2/alleva-sync/jobs/{job_id}", response_model=ApiHarnessJob)
def alleva_sync_job(job_id: str, _: AdminUser) -> ApiHarnessJob:
    try:
        job = job_service.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Sync job not found") from exc
    if job.job_type != "approved_treatment_plan_sync":
        raise HTTPException(status_code=404, detail="Sync job not found")
    return job


def _sync_blockers(profile: AppSetting) -> tuple[str, ...]:
    blockers = []
    if not profile.emr_api_enabled:
        blockers.append("API testing is not enabled")
    if not profile.alleva_treatment_plan_sync_enabled:
        blockers.append("treatment-plan sync is not enabled")
    if not profile.alleva_treatment_plan_sync_approved:
        blockers.append("R3/Alleva approval is not recorded")
    if not profile.alleva_treatment_plan_endpoint_mapping_validated:
        blockers.append("endpoint mapping is not validated")
    if not profile.api_client_secret:
        blockers.append("encrypted client secret is not configured")
    return tuple(blockers)
