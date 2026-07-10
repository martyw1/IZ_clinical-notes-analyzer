from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.v2.api.deps import AdminUser, DbSession
from app.v2.api.models import AllevaContractApprovalIn, AllevaContractApprovalOut
from app.v2.domain.schemas import ApiHarnessJob
from app.v2.models import AppSetting
from app.v2.services.audit_store import record_audit_event
from app.v2.services.alleva_contracts import active_contract, approve_contract
from app.v2.services.jobs import job_service

router = APIRouter()


@router.post("/api/v2/alleva-sync/run", response_model=ApiHarnessJob, status_code=202)
def run_alleva_sync(actor: AdminUser, db: DbSession) -> ApiHarnessJob:
    profile = db.execute(select(AppSetting)).scalar_one()
    contract = active_contract(db)
    blockers = _sync_blockers(profile, contract is not None)
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
    if contract is None:
        raise HTTPException(status_code=409, detail="Alleva treatment-plan sync is blocked: an approved versioned contract is required")
    return job_service.create_treatment_plan_sync_job(actor.id, actor.role, contract)


@router.post("/api/v2/alleva-sync/contracts", response_model=AllevaContractApprovalOut, status_code=201)
def approve_alleva_contract(payload: AllevaContractApprovalIn, actor: AdminUser, db: DbSession) -> AllevaContractApprovalOut:
    try:
        approved = approve_contract(db, payload, actor.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="The Alleva contract is incomplete or invalid") from exc
    record_audit_event(
        db,
        action="alleva.contract.approved",
        actor=actor,
        target_entity_type="alleva_contract_approval",
        target_entity_id=approved.contract_version,
        details={"contract_sha256": approved.contract_sha256, "endpoint_count": len(approved.payload.endpoints)},
    )
    return AllevaContractApprovalOut(
        contract_version=approved.contract_version,
        contract_sha256=approved.contract_sha256,
        effective_at=approved.effective_at,
        approved_at=approved.approved_at,
    )


@router.get("/api/v2/alleva-sync/jobs/{job_id}", response_model=ApiHarnessJob)
def alleva_sync_job(job_id: str, _: AdminUser) -> ApiHarnessJob:
    try:
        job = job_service.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Sync job not found") from exc
    if job.job_type != "approved_treatment_plan_sync":
        raise HTTPException(status_code=404, detail="Sync job not found")
    return job


def _sync_blockers(profile: AppSetting, has_approved_contract: bool) -> tuple[str, ...]:
    blockers = []
    if not profile.emr_api_enabled:
        blockers.append("API testing is not enabled")
    if not profile.alleva_treatment_plan_sync_enabled:
        blockers.append("treatment-plan sync is not enabled")
    if not has_approved_contract:
        blockers.append("an approved versioned contract is required")
    if not profile.api_client_secret:
        blockers.append("encrypted client secret is not configured")
    return tuple(blockers)
