from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
from typing import Final

from fastapi import APIRouter, Body, HTTPException, Response
from fastapi.responses import FileResponse

from app.core.config import BUILD_CHANNEL, settings
from app.services.version import JsonValue, build_version_payload
from app.v2.api.deps import AdminUser, CurrentUser, DbSession, ManagerUser
from app.v2.api.models import (
    ApiHarnessJobStart,
    DashboardOut,
    DefinitionSummaryOut,
    ManagerActionInput,
    PullDefinitionsInput,
    PullDefinitionsOut,
    ReadinessCheck,
    ReadinessOut,
    SampleOpenApiInfo,
    SampleOpenApiOperation,
    SampleOpenApiOut,
    SampleOpenApiPathItem,
    TreatmentPlanListOut,
)
from app.v2.domain.schemas import ApiHarnessJob, JobPreview, TreatmentPlanAggregate
from app.v2.services.audit_store import record_audit_event
from app.v2.services.dashboard_data import dashboard_payload
from app.v2.services.jobs import job_service
from app.v2.services.manager_action_store import save_manager_action_record
from app.v2.services.treatment_plan_store import (
    TREATMENT_PLAN_STATUS_ORDER,
    list_treatment_plan_imports,
    list_treatment_plan_queue_items,
    treatment_plan_aggregate_for_patient,
)

router = APIRouter()
SPREADSHEET_FORMULA_PREFIXES: Final = ("=", "+", "-", "@")


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
            ReadinessCheck(name="database", status="ok", path=str(settings.sqlite_db_path)),
            ReadinessCheck(name="build_channel", status="ok", value=BUILD_CHANNEL),
            ReadinessCheck(name="loc_change_blocker", status="warn", message="LOC-change update window remains unvalidated."),
        ),
    )


@router.get("/api/version")
def version() -> dict[str, JsonValue]:
    return build_version_payload()


@router.get("/api/workflow-definitions")
def workflow_definitions(_: CurrentUser) -> list[dict[str, JsonValue]]:
    return [
        {
            "workflow_key": "treatment_plan_tracking_v2",
            "display_name": "Treatment Plan Tracking V2",
            "status": "published",
            "version": 2,
            "loc_change_blocker": "unvalidated",
        }
    ]


@router.get("/api/api-configuration/sample-openapi.json")
def sample_openapi() -> SampleOpenApiOut:
    return SampleOpenApiOut(
        openapi="3.1.0",
        info=SampleOpenApiInfo(title="Connectivity Test Definition", version="2.0.0-beta.1"),
        paths={"/clients": SampleOpenApiPathItem(get=SampleOpenApiOperation(operation_id="listClients"))},
    )


@router.post("/api/api-configuration/pull-definitions")
def pull_definitions(_: AdminUser, payload: PullDefinitionsInput = Body()) -> PullDefinitionsOut:
    return PullDefinitionsOut(
        status="ok",
        definition_summary=DefinitionSummaryOut(title="Connectivity Test Definition", operation_count=1),
        redaction_status="safe_summary_only",
        request_keys=tuple(sorted(payload.model_fields_set)),
    )


@router.get("/api/v2/navigation")
def navigation(user: CurrentUser) -> dict[str, JsonValue]:
    items = ["Status Dashboard", "Treatment Plans", "Manual Upload"]
    if user.role == "admin":
        items.extend(["API Testing Harness", "Users", "Forensic Logs", "Settings"])
    if user.role in {"office_manager", "manager"}:
        items.extend(["Forensic Logs"])
    items.append("Help")
    return {"items": items, "active_runtime": "v2"}


@router.get("/api/v2/dashboard", response_model=DashboardOut)
def dashboard(_: CurrentUser, db: DbSession) -> dict[str, JsonValue]:
    return dashboard_payload(list_treatment_plan_imports(db))


@router.get("/api/v2/treatment-plans", response_model=TreatmentPlanListOut)
def treatment_plans(_: CurrentUser, db: DbSession) -> dict[str, JsonValue]:
    items = list_treatment_plan_queue_items(db)
    return {
        "items": [
            {
                "patient_id": item.patient_id,
                "patient_display_label": item.patient_display_label,
                "current_level_of_care": item.current_level_of_care,
                "admission_date": item.admission_date,
                "next_due_date": item.next_due_date,
                "status": item.status,
                "missing_criteria_count": item.missing_criteria_count,
                "returned_criteria_count": item.returned_criteria_count,
                "source_mode": item.source_mode,
                "content_completeness_summary": item.content_completeness_summary,
                "warnings": item.warnings,
            }
            for item in items
        ],
        "status_order": TREATMENT_PLAN_STATUS_ORDER,
    }


@router.get("/api/v2/treatment-plans/{patient_id}")
def treatment_plan_detail(patient_id: str, user: CurrentUser, db: DbSession) -> TreatmentPlanAggregate:
    aggregate = treatment_plan_aggregate_for_patient(db, patient_id)
    if aggregate is None:
        raise HTTPException(status_code=404, detail="Treatment-plan aggregate not found")
    record_audit_event(db, action="treatment_plan.detail.viewed", actor=user, target_entity_type="treatment_plan", target_entity_id=patient_id)
    return aggregate


@router.post("/api/v2/treatment-plans/{patient_id}/manager-actions")
def save_manager_action(patient_id: str, payload: ManagerActionInput, user: ManagerUser, db: DbSession) -> dict[str, JsonValue]:
    if payload.action == "override" and not payload.override_reason.strip():
        raise HTTPException(status_code=400, detail="Override reason is required")
    if treatment_plan_aggregate_for_patient(db, patient_id) is None:
        raise HTTPException(status_code=404, detail="Treatment-plan aggregate not found")
    saved = save_manager_action_record(
        db,
        patient_id=patient_id,
        criterion_id=payload.criterion_id,
        action=payload.action,
        comment=payload.comment,
        override_reason=payload.override_reason,
        actor=user,
    )
    record_audit_event(
        db,
        action=f"manager.criterion.{payload.action}",
        actor=user,
        target_entity_type="treatment_plan_criterion",
        target_entity_id=f"{patient_id}:{payload.criterion_id}",
        details={"criterion_id": payload.criterion_id, "action": payload.action, "has_comment": bool(payload.comment)},
    )
    return {
        "status": "saved",
        "patient_id": patient_id,
        "criterion_id": payload.criterion_id,
        "action": payload.action,
        "created_at": saved.created_at.isoformat(),
    }


@router.post("/api/v2/api-harness/jobs")
def create_api_harness_job(payload: ApiHarnessJobStart, _: AdminUser) -> ApiHarnessJob:
    if payload.job_type != "pull_all_treatment_plans_all_fields":
        raise HTTPException(status_code=400, detail="Unsupported V2 job type")
    return job_service.create_all_fields_job(actor_id="1", actor_role="admin")


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


@router.get("/api/v2/exports/{patient_id}/checklist-evidence.csv")
def redacted_checklist_export(patient_id: str, user: ManagerUser, db: DbSession) -> Response:
    aggregate = treatment_plan_aggregate_for_patient(db, patient_id)
    if aggregate is None:
        raise HTTPException(status_code=404, detail="Treatment-plan aggregate not found")
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(("criterion", "status", "finding", "source_path", "safe_preview", "manager_action"))
    for criterion in aggregate.criteria_results:
        preview = criterion.evidence_refs[0].safe_preview if criterion.evidence_refs else ""
        path = criterion.source_json_paths[0] if criterion.source_json_paths else ""
        writer.writerow(tuple(_safe_csv_cell(value) for value in (criterion.criterion_id, criterion.result_status, criterion.finding_message, path, preview, "review")))
    record_audit_event(db, action="export.redacted_checklist_evidence", actor=user, target_entity_type="treatment_plan", target_entity_id=patient_id)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"content-disposition": "attachment; filename=redacted-checklist-evidence.csv"},
    )


def _safe_csv_cell(value: str) -> str:
    if value.startswith(SPREADSHEET_FORMULA_PREFIXES):
        return f"'{value}"
    return value
