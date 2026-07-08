from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Response
from fastapi.responses import FileResponse

from app.core.config import BUILD_CHANNEL, settings
from app.services.audit import log_event
from app.services.version import JsonValue, build_version_payload
from app.v2.api.models import (
    ApiConfigurationOut,
    ApiConfigurationUpdate,
    ApiHarnessJobStart,
    DefinitionSummaryOut,
    LoginInput,
    ManagerActionInput,
    PullDefinitionsInput,
    PullDefinitionsOut,
    ReadinessCheck,
    ReadinessOut,
    SampleOpenApiInfo,
    SampleOpenApiOperation,
    SampleOpenApiOut,
    SampleOpenApiPathItem,
    TokenOut,
    UserOut,
)
from app.v2.domain.schemas import ApiHarnessJob, JobPreview, TreatmentPlanAggregate
from app.v2.services.dashboard_data import dashboard_payload
from app.v2.services.jobs import job_service
from app.v2.services.sample_data import treatment_plan_aggregate

router = APIRouter()


def _admin_user() -> UserOut:
    return UserOut(id=1, username="admin", full_name="System Administrator", role="admin", is_active=True)


@router.get("/api/health")
def api_health() -> dict[str, str]:
    return {"status": "ok", "runtime": "v2"}


@router.get("/health")
def health() -> dict[str, str]:
    return api_health()


@router.get("/api/readiness")
def readiness() -> ReadinessOut:
    return ReadinessOut(
        status="warn",
        runtime="v2",
        checks=(
            ReadinessCheck(name="local_app_data", status="ok", path=str(settings.local_app_data_dir)),
            ReadinessCheck(name="build_channel", status="ok", value=BUILD_CHANNEL),
            ReadinessCheck(
                name="loc_change_blocker",
                status="warn",
                message="LOC-change update window remains unvalidated.",
            ),
        ),
    )


@router.get("/api/version")
def version() -> dict[str, JsonValue]:
    return build_version_payload()


@router.post("/api/auth/login")
def login(payload: LoginInput) -> TokenOut:
    if payload.username.strip().lower() != "admin":
        log_event(action="auth.login.failed", entity_type="user", entity_reference=payload.username, outcome="failure")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    log_event(action="auth.login.success", entity_type="user", entity_reference="admin", actor_id="1", actor_role="admin")
    return TokenOut(access_token="v2-local-admin-token")


@router.get("/api/users/me")
def current_user() -> UserOut:
    return _admin_user()


@router.get("/api/workflow-definitions")
def workflow_definitions() -> list[dict[str, JsonValue]]:
    return [
        {
            "workflow_key": "treatment_plan_tracking_v2",
            "display_name": "Treatment Plan Tracking V2",
            "status": "published",
            "version": 2,
            "loc_change_blocker": "unvalidated",
        }
    ]


@router.patch("/api/api-configuration")
def save_api_configuration(payload: ApiConfigurationUpdate) -> ApiConfigurationOut:
    log_event(
        action="settings.api_profile.saved",
        entity_type="api_connection_profile",
        entity_reference=payload.vendor_name,
        actor_id="1",
        actor_role="admin",
        details={"vendor_name": payload.vendor_name, "api_base_url": payload.api_base_url, "api_key_configured": bool(payload.api_key)},
    )
    return ApiConfigurationOut(
        vendor_name=payload.vendor_name,
        api_base_url=payload.api_base_url,
        api_key_configured=bool(payload.api_key),
        timeout_seconds=payload.timeout_seconds,
        api_enabled=payload.api_enabled,
    )


@router.get("/api/api-configuration/sample-openapi.json")
def sample_openapi() -> SampleOpenApiOut:
    return SampleOpenApiOut(
        openapi="3.1.0",
        info=SampleOpenApiInfo(title="Connectivity Test Definition", version="2.0.0-beta.1"),
        paths={"/clients": SampleOpenApiPathItem(get=SampleOpenApiOperation(operation_id="listClients"))},
    )


@router.post("/api/api-configuration/pull-definitions")
def pull_definitions(payload: PullDefinitionsInput = Body()) -> PullDefinitionsOut:
    return PullDefinitionsOut(
        status="ok",
        definition_summary=DefinitionSummaryOut(title="Connectivity Test Definition", operation_count=1),
        redaction_status="safe_summary_only",
        request_keys=tuple(sorted(payload.model_fields_set)),
    )


@router.get("/api/v2/navigation")
def navigation() -> dict[str, JsonValue]:
    return {
        "items": [
            "Status Dashboard",
            "Treatment Plans",
            "Manual Upload",
            "API Testing Harness",
            "Users",
            "Forensic Logs",
            "Settings",
            "Help",
        ],
        "active_runtime": "v2",
    }


@router.get("/api/v2/dashboard")
def dashboard() -> dict[str, JsonValue]:
    return dashboard_payload()


@router.get("/api/v2/treatment-plans")
def treatment_plans() -> dict[str, JsonValue]:
    aggregate = treatment_plan_aggregate()
    return {
        "items": [
            {
                "patient_id": aggregate.patient_id,
                "patient_display_label": aggregate.patient_display_label,
                "current_level_of_care": aggregate.current_level_of_care,
                "admission_date": aggregate.admission_date,
                "next_due_date": aggregate.date_clock_due_date,
                "status": aggregate.overall_status,
                "missing_criteria_count": aggregate.evidence_coverage_summary.criteria_missing_evidence,
                "returned_criteria_count": 0,
                "source_mode": aggregate.source_mode,
                "content_completeness_summary": aggregate.content_snapshot_summary,
                "warnings": aggregate.data_quality_warnings,
            }
        ],
        "status_order": ["Missing Data", "Needs Review", "Incomplete", "Within Window", "Late", "Conflicting Evidence", "Unable to Evaluate"],
    }


@router.get("/api/v2/treatment-plans/{patient_id}")
def treatment_plan_detail(patient_id: str) -> TreatmentPlanAggregate:
    aggregate = treatment_plan_aggregate()
    if patient_id != aggregate.patient_id:
        raise HTTPException(status_code=404, detail="Synthetic V2 patient fixture not found")
    log_event(action="treatment_plan.detail.viewed", entity_type="treatment_plan", entity_reference=patient_id, actor_id="1", actor_role="admin")
    return aggregate


@router.post("/api/v2/treatment-plans/{patient_id}/manager-actions")
def save_manager_action(patient_id: str, payload: ManagerActionInput) -> dict[str, JsonValue]:
    if payload.action == "override" and not payload.override_reason.strip():
        raise HTTPException(status_code=400, detail="Override reason is required")
    log_event(
        action=f"manager.criterion.{payload.action}",
        entity_type="treatment_plan_criterion",
        entity_reference=f"{patient_id}:{payload.criterion_id}",
        actor_id="1",
        actor_role="admin",
        details={"criterion_id": payload.criterion_id, "action": payload.action, "has_comment": bool(payload.comment)},
    )
    return {"status": "saved", "patient_id": patient_id, "criterion_id": payload.criterion_id, "action": payload.action}


@router.post("/api/v2/api-harness/jobs")
def create_api_harness_job(payload: ApiHarnessJobStart) -> ApiHarnessJob:
    if payload.job_type != "pull_all_treatment_plans_all_fields":
        raise HTTPException(status_code=400, detail="Unsupported V2 job type")
    return job_service.create_all_fields_job(actor_id="1", actor_role="admin")


@router.get("/api/v2/api-harness/jobs")
def list_api_harness_jobs() -> tuple[ApiHarnessJob, ...]:
    return job_service.list_jobs()


@router.get("/api/v2/api-harness/jobs/{job_id}")
def get_api_harness_job(job_id: str) -> ApiHarnessJob:
    try:
        return job_service.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@router.post("/api/v2/api-harness/jobs/{job_id}/cancel")
def cancel_api_harness_job(job_id: str) -> ApiHarnessJob:
    try:
        return job_service.cancel_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@router.get("/api/v2/api-harness/jobs/{job_id}/artifacts")
def api_harness_job_artifacts(job_id: str) -> tuple[JsonValue, ...]:
    try:
        return tuple(artifact.model_dump() for artifact in job_service.artifacts(job_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@router.get("/api/v2/api-harness/jobs/{job_id}/artifacts/{artifact_id}")
def download_api_harness_artifact(job_id: str, artifact_id: str) -> FileResponse:
    try:
        path = job_service.artifact_path(job_id, artifact_id)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Artifact not found") from exc
    log_event(action="api_harness.job.artifact_downloaded", entity_type="api_harness_job", entity_reference=job_id)
    return FileResponse(path=path, filename=Path(artifact_id).name)


@router.get("/api/v2/api-harness/jobs/{job_id}/preview")
def api_harness_job_preview(job_id: str) -> JobPreview:
    try:
        return job_service.preview(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@router.get("/api/v2/exports/{patient_id}/checklist-evidence.csv")
def redacted_checklist_export(patient_id: str) -> Response:
    aggregate = treatment_plan_aggregate()
    if patient_id != aggregate.patient_id:
        raise HTTPException(status_code=404, detail="Synthetic V2 patient fixture not found")
    rows = ["criterion,status,finding,source_path,safe_preview,manager_action"]
    for criterion in aggregate.criteria_results:
        preview = criterion.evidence_refs[0].safe_preview if criterion.evidence_refs else ""
        path = criterion.source_json_paths[0] if criterion.source_json_paths else ""
        rows.append(f"{criterion.criterion_id},{criterion.result_status},{criterion.finding_message},{path},{preview},review")
    log_event(action="export.redacted_checklist_evidence", entity_type="treatment_plan", entity_reference=patient_id)
    return Response(
        content="\n".join(rows),
        media_type="text/csv",
        headers={"content-disposition": "attachment; filename=redacted-checklist-evidence.csv"},
    )
