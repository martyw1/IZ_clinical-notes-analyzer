from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.v2.api.deps import AdminUser, DbSession
from app.v2.api.models import AllevaContractApprovalIn, AllevaContractApprovalOut
from app.v2.domain.schemas import ApiHarnessJob
from app.v2.models import AppSetting
from app.v2.services.audit_store import record_audit_event
from app.v2.services.alleva_contracts import ApprovedAllevaContract, active_contract, approve_contract, contract_bound_to_sync_job
from app.v2.services.jobs import job_service

router = APIRouter()


@router.post("/api/v2/alleva-sync/run", response_model=ApiHarnessJob, status_code=202)
def run_alleva_sync(actor: AdminUser, db: DbSession) -> ApiHarnessJob:
    profile = db.execute(select(AppSetting)).scalar_one()
    contract = active_contract(db)
    blockers = _sync_blockers(profile, contract)
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
    try:
        return job_service.create_treatment_plan_sync_job(actor.id, actor.role, contract)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="An approved treatment-plan sync is already running") from exc


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


@router.post("/api/v2/alleva-sync/jobs/{job_id}/resume", response_model=ApiHarnessJob, status_code=202)
def resume_alleva_sync(job_id: str, actor: AdminUser, db: DbSession) -> ApiHarnessJob:
    profile = db.execute(select(AppSetting)).scalar_one()
    contract = active_contract(db)
    historical_contract = contract_bound_to_sync_job(db, job_id)
    blockers = list(_sync_blockers(profile, contract))
    if historical_contract is None:
        blockers.append("the historical sync job has no valid approved contract")
    elif contract is not None and (
        historical_contract.approval_id != contract.approval_id
        or historical_contract.contract_sha256 != contract.contract_sha256
    ):
        blockers.append("the active approved contract does not match the historical sync job")
    if blockers:
        record_audit_event(
            db,
            action="alleva.treatment_plan_sync.resume.blocked",
            actor=actor,
            target_entity_type="integration_sync",
            target_entity_id=job_id,
            outcome_status="blocked",
            details={"blocker_count": len(blockers)},
        )
        db.commit()
        raise HTTPException(status_code=409, detail=f"Alleva treatment-plan sync resume is blocked: {', '.join(blockers)}")
    if contract is None:
        raise HTTPException(status_code=409, detail="Alleva treatment-plan sync resume is blocked: an approved versioned contract is required")
    try:
        resumed = job_service.resume_treatment_plan_sync_job(job_id, actor.id, actor.role, contract)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Sync job not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Sync job cannot be resumed") from exc
    record_audit_event(
        db,
        action="alleva.treatment_plan_sync.resumed",
        actor=actor,
        target_entity_type="integration_sync",
        target_entity_id=resumed.job_id,
        details={"resumed_from_job_id": job_id},
    )
    db.commit()
    return resumed


def _sync_blockers(profile: AppSetting, contract: ApprovedAllevaContract | None) -> tuple[str, ...]:
    blockers = []
    if not profile.emr_api_enabled:
        blockers.append("API testing is not enabled")
    if not profile.alleva_treatment_plan_sync_enabled:
        blockers.append("treatment-plan sync is not enabled")
    if not profile.alleva_treatment_plan_sync_approved:
        blockers.append("R3/Alleva approval is not recorded")
    if not profile.alleva_treatment_plan_endpoint_mapping_validated:
        blockers.append("the treatment-plan endpoint mapping is not validated")
    if contract is None:
        blockers.append("an approved versioned contract is required")
    elif profile.api_base_url != contract.payload.api_base_url or profile.api_oauth_token_url != contract.payload.oauth.token_url:
        blockers.append("saved connection settings do not match the approved contract")
    elif profile.api_token_auth_style != contract.payload.oauth.token_auth_style or profile.api_scopes != contract.payload.oauth.scope:
        blockers.append("saved OAuth settings do not match the approved contract")
    if not profile.api_client_secret:
        blockers.append("encrypted client secret is not configured")
    return tuple(blockers)
