from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.core.config import RESTRICTED_ENVIRONMENTS, settings
from app.v2.api.deps import AdminUser, DbSession
from app.v2.domain.schemas import ApiHarnessJob
from app.v2.models import AppSetting
from app.v2.services.audit_store import record_audit_event
from app.v2.services.alleva_contracts import (
    ApprovedAllevaContract,
    contract_matches_profile,
    contract_bound_to_sync_job,
    ensure_builtin_contract,
)
from app.v2.services.jobs import job_service

router = APIRouter()


@router.post("/api/v2/alleva-sync/run", response_model=ApiHarnessJob, status_code=202)
def run_alleva_sync(actor: AdminUser, db: DbSession) -> ApiHarnessJob:
    profile = db.execute(select(AppSetting)).scalar_one()
    configuration_blockers = _configuration_blockers(profile)
    if configuration_blockers:
        _record_blocked_sync(db, actor, configuration_blockers)
        raise HTTPException(status_code=409, detail=f"Alleva treatment-plan sync is blocked: {', '.join(configuration_blockers)}")
    try:
        contract, created = ensure_builtin_contract(db, profile, actor.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Alleva treatment-plan sync is blocked: the saved API profile is incomplete") from exc
    if created:
        record_audit_event(
            db,
            action="alleva.mapping.automatic",
            actor=actor,
            target_entity_type="alleva_contract_approval",
            target_entity_id=contract.contract_version,
            details={"contract_sha256": contract.contract_sha256, "endpoint_count": len(contract.payload.endpoints)},
        )
    blockers = _sync_blockers(profile, contract)
    if blockers:
        _record_blocked_sync(db, actor, blockers)
        raise HTTPException(status_code=409, detail=f"Alleva treatment-plan sync is blocked: {', '.join(blockers)}")
    record_audit_event(
        db,
        action="alleva.treatment_plan_sync.job.started",
        actor=actor,
        target_entity_type="integration_sync",
        target_entity_id="alleva_treatment_plan_sync",
    )
    try:
        return job_service.create_treatment_plan_sync_job(actor.id, actor.role, contract)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="A treatment-plan sync is already running") from exc


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
    configuration_blockers = list(_configuration_blockers(profile))
    if configuration_blockers:
        blockers = configuration_blockers
        contract = None
    else:
        try:
            contract, _created = ensure_builtin_contract(db, profile, actor.id)
            blockers = list(_sync_blockers(profile, contract))
        except ValueError:
            contract = None
            blockers = ["the built-in Alleva v1 mapping is unavailable"]
    historical_contract = contract_bound_to_sync_job(db, job_id)
    if historical_contract is None:
        blockers.append("the historical sync job has no valid versioned mapping")
    elif contract is not None and (
        historical_contract.approval_id != contract.approval_id
        or historical_contract.contract_sha256 != contract.contract_sha256
    ):
        blockers.append("the current built-in mapping does not match the historical sync job")
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
        raise HTTPException(status_code=409, detail="Alleva treatment-plan sync resume is blocked: a versioned built-in mapping is required")
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
    blockers = list(_configuration_blockers(profile))
    if contract is None:
        blockers.append("the built-in Alleva v1 mapping is unavailable")
    elif not contract_matches_profile(contract, profile):
        blockers.append("saved API settings do not match the versioned import mapping")
    return tuple(blockers)


def _configuration_blockers(profile: AppSetting) -> tuple[str, ...]:
    blockers = []
    if not profile.emr_api_enabled:
        blockers.append("API testing is not enabled")
    if not profile.alleva_treatment_plan_sync_enabled:
        blockers.append("treatment-plan sync is not enabled")
    if not profile.alleva_treatment_plan_sync_approved:
        blockers.append("live treatment-plan import is not authorized for this tenant")
    if not profile.api_client_id.strip():
        blockers.append("OAuth client ID is not configured")
    if not profile.api_client_secret:
        blockers.append("encrypted client secret is not configured")
    if settings.environment.strip().lower() in RESTRICTED_ENVIRONMENTS and not _trusted_alleva_origins(profile):
        blockers.append("saved Alleva API and OAuth URLs are not trusted production origins")
    return tuple(blockers)


def _trusted_alleva_origins(profile: AppSetting) -> bool:
    api = urlsplit(profile.api_base_url)
    oauth = urlsplit(profile.api_oauth_token_url)
    return (
        api.scheme == "https"
        and api.hostname == "api.allevasoft.com"
        and api.username is None
        and api.password is None
        and oauth.scheme == "https"
        and oauth.hostname == "authorization.allevasoft.com"
        and oauth.username is None
        and oauth.password is None
    )


def _record_blocked_sync(db: DbSession, actor: AdminUser, blockers: tuple[str, ...]) -> None:
    record_audit_event(
        db,
        action="alleva.treatment_plan_sync.blocked",
        actor=actor,
        target_entity_type="integration_sync",
        target_entity_id="alleva_treatment_plan_sync",
        outcome_status="blocked",
        details={"blocker_count": len(blockers)},
    )
