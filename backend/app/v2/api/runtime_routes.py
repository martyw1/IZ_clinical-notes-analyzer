from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.core.config import BUILD_CHANNEL
from app.services.version import JsonValue, build_version_payload
from app.v2.api.deps import AdminUser, CurrentUser, DbSession
from app.v2.api.models import (
    ApiHarnessJobStart,
    DashboardOut,
    ManagerActionInput,
    ReadinessCheck,
    ReadinessOut,
)
from app.v2.domain.schemas import ApiHarnessJob, JobPreview
from app.v2.models import AppSetting
from app.v2.services.audit_store import record_audit_event
from app.v2.services.dashboard_data import dashboard_payload
from app.v2.services.jobs import HarnessConnection, job_service
from app.v2.services.manager_action_store import (
    CorrectionAssignmentError,
    open_correction_dicts,
    save_manager_action_record,
    save_returned_correction_work_item,
)
from app.v2.services.treatment_plan_store import (
    list_treatment_plan_imports,
    treatment_plan_aggregate_for_version,
)
from app.v2.services.secure_storage import decrypt_api_client_id, decrypt_text_secret
from app.v2.authorization import accessible_patient_record_ids, resolve_plan_version, PlanVersionSelector

router = APIRouter()


@router.get("/api/health")
def api_health() -> dict[str, str]:
    return {"status": "ok", "runtime": "v2"}


@router.get("/health")
def health() -> dict[str, str]:
    return api_health()


@router.get("/api/readiness")
def readiness(db: DbSession) -> ReadinessOut:
    profile = _app_setting(db)
    client_id = decrypt_api_client_id(profile.api_client_id)
    api_status = "ok" if client_id and profile.api_client_secret and profile.emr_api_enabled else "warn"
    api_message = "Encrypted credentials are saved and API testing is enabled." if api_status == "ok" else "Configure encrypted API credentials and enable API testing before connectivity checks."
    return ReadinessOut(
        status="warn",
        runtime="v2",
        checks=(
            ReadinessCheck(name="local_app_data", status="ok"),
            ReadinessCheck(name="database", status="ok"),
            ReadinessCheck(name="build_channel", status="ok", value=BUILD_CHANNEL),
            ReadinessCheck(name="api_profile", status=api_status, message=api_message),
            ReadinessCheck(name="loc_change_blocker", status="ok" if profile.treatment_plan_loc_change_window_validated else "warn", message="LOC-change update window remains unvalidated." if not profile.treatment_plan_loc_change_window_validated else "LOC-change update window is validated."),
        ),
    )


@router.get("/api/version")
def version() -> dict[str, JsonValue]:
    return build_version_payload()


@router.get("/api/v2/navigation")
def navigation(user: CurrentUser) -> dict[str, JsonValue]:
    items = [
        "Status Dashboard",
        "Patient Roster",
        "Patient Record Detail",
        "Treatment Plan Detail",
        "Treatment Plans Roster",
        "Manual Upload",
    ]
    if user.role == "counselor":
        items.append("Corrections")
    if user.role == "admin":
        items.extend(["API Testing Harness", "Users", "Forensic Logs", "Settings"])
    items.append("Help")
    return {"items": items, "active_runtime": "v2"}


@router.get("/api/v2/dashboard", response_model=DashboardOut)
def dashboard(user: CurrentUser, db: DbSession) -> dict[str, JsonValue]:
    profile = _app_setting(db)
    client_id = decrypt_api_client_id(profile.api_client_id)
    allowed_ids = accessible_patient_record_ids(db, user)
    imports = list_treatment_plan_imports(db, allowed_ids)
    return dashboard_payload(
        imports,
        api_configured=bool(profile.api_client_secret),
        api_client_id_configured=bool(client_id.strip()),
        api_enabled=profile.emr_api_enabled,
        sync_enabled=profile.alleva_treatment_plan_sync_enabled,
        sync_authorized=profile.alleva_treatment_plan_sync_approved,
        loc_change_window_validated=profile.treatment_plan_loc_change_window_validated,
        returned_count=sum(1 for correction in open_correction_dicts(db) if correction["patient_record_id"] in allowed_ids),
    )


def _app_setting(db: DbSession) -> AppSetting:
    return db.execute(select(AppSetting)).scalar_one()


from app.v2.api.plan_read_routes import router as plan_read_router
from app.v2.api.plan_export_routes import router as plan_export_router

router.include_router(plan_read_router)
router.include_router(plan_export_router)




@router.post("/api/v2/treatment-plans/{patient_id}/manager-actions")
def save_manager_action(patient_id: str, payload: ManagerActionInput, user: CurrentUser, db: DbSession) -> dict[str, JsonValue]:
    identity = resolve_plan_version(db, user, PlanVersionSelector(patient_id, payload.plan_version_id, payload.patient_record_id, payload.source_mode, payload.treatment_plan_id), manager=True)
    if payload.action == "override" and not payload.override_reason.strip():
        raise HTTPException(status_code=400, detail="Override reason is required")
    aggregate = treatment_plan_aggregate_for_version(db, identity.plan_version_id)
    if aggregate is None or payload.criterion_id not in {criterion.criterion_id for criterion in aggregate.criteria_results}:
        raise HTTPException(status_code=404, detail="Treatment-plan criterion not found")
    saved = save_manager_action_record(
        db,
        patient_id=patient_id,
        plan_version_id=identity.plan_version_id,
        criterion_id=payload.criterion_id,
        action=payload.action,
        comment=payload.comment,
        override_reason=payload.override_reason,
        actor=user,
        commit=False,
    )
    if payload.action == "return_for_correction":
        try:
            save_returned_correction_work_item(
                db,
                patient_id=patient_id,
                plan_version_id=identity.plan_version_id,
                manager_action_id=saved.id,
                criterion_id=payload.criterion_id,
                comment=payload.comment,
                counselor_username=payload.assigned_counselor_username.strip(),
                actor=user,
                commit=False,
            )
        except CorrectionAssignmentError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    record_audit_event(
        db,
        action=f"manager.criterion.{payload.action}",
        actor=user,
        target_entity_type="treatment_plan_criterion",
        target_entity_id=f"{identity.plan_version_id}:{payload.criterion_id}",
        details={"plan_version_id": identity.plan_version_id, "patient_row_id": identity.patient_record_id, "criterion_id": payload.criterion_id, "action": payload.action, "has_comment": bool(payload.comment)},
    )
    return {
        "status": "saved",
        "patient_id": patient_id,
        "plan_version_id": identity.plan_version_id,
        "patient_record_id": identity.patient_record_id,
        "criterion_id": payload.criterion_id,
        "action": payload.action,
        "created_at": saved.created_at.isoformat(),
    }


@router.post("/api/v2/api-harness/jobs")
def create_api_harness_job(payload: ApiHarnessJobStart, actor: AdminUser, db: DbSession) -> ApiHarnessJob:
    if payload.job_type != "pull_all_treatment_plans_all_fields":
        raise HTTPException(status_code=400, detail="Unsupported V2 job type")
    profile = _app_setting(db)
    if not profile.emr_api_enabled:
        raise HTTPException(status_code=409, detail="Enable API testing before starting the configured harness job.")
    connection = HarnessConnection(
        api_base_url=profile.api_base_url, token_url=profile.api_oauth_token_url,
        client_id=decrypt_api_client_id(profile.api_client_id),
        client_secret=decrypt_text_secret(profile.api_client_secret), scope=profile.api_scopes,
        token_auth_style=profile.api_token_auth_style, timeout_seconds=profile.emr_api_timeout_seconds,
        page_size=profile.api_pagination_limit, api_version=profile.alleva_api_version,
        treatment_plan_start_date=profile.alleva_treatment_plan_start_date,
    )
    return job_service.create_all_fields_job(connection, actor_id=str(actor.id), actor_role=actor.role)


@router.get("/api/v2/api-harness/jobs")
def list_api_harness_jobs(_: AdminUser) -> tuple[ApiHarnessJob, ...]:
    return job_service.list_jobs()


@router.get("/api/v2/api-harness/jobs/{job_id}")
def get_api_harness_job(job_id: str, _: AdminUser) -> ApiHarnessJob:
    try:
        return job_service.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@router.post("/api/v2/api-harness/jobs/{job_id}/cancel")
def cancel_api_harness_job(job_id: str, _: AdminUser) -> ApiHarnessJob:
    try:
        return job_service.cancel_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@router.get("/api/v2/api-harness/jobs/{job_id}/artifacts")
def api_harness_job_artifacts(job_id: str, _: AdminUser) -> tuple[JsonValue, ...]:
    try:
        return tuple(artifact.model_dump() for artifact in job_service.artifacts(job_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@router.get("/api/v2/api-harness/jobs/{job_id}/artifacts/{artifact_id}")
def download_api_harness_artifact(job_id: str, artifact_id: str, _: AdminUser) -> FileResponse:
    try:
        path = job_service.artifact_path(job_id, artifact_id)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Artifact not found") from exc
    return FileResponse(path=path, filename=Path(artifact_id).name)


@router.get("/api/v2/api-harness/jobs/{job_id}/preview")
def api_harness_job_preview(job_id: str, _: AdminUser) -> JobPreview:
    try:
        return job_service.preview(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
