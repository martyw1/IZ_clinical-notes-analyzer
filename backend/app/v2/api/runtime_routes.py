from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
from typing import Final

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.core.config import BUILD_CHANNEL, settings
from app.services.version import JsonValue, build_version_payload
from app.v2.api.deps import AdminUser, CurrentUser, DbSession, ManagerUser
from app.v2.api.models import (
    ApiHarnessJobStart,
    DashboardOut,
    ManagerActionInput,
    PatientRosterOut,
    ReadinessCheck,
    ReadinessOut,
    TreatmentPlanListOut,
)
from app.v2.domain.schemas import ApiHarnessJob, JobPreview, SourceMode, TreatmentPlanAggregate
from app.v2.models import AppSetting
from app.v2.services.audit_store import record_audit_event
from app.v2.services.dashboard_data import dashboard_payload
from app.v2.services.jobs import HarnessConnection, job_service
from app.v2.services.manager_action_store import (
    CorrectionAssignmentError,
    open_correction_counts_by_patient,
    save_manager_action_record,
    save_returned_correction_work_item,
)
from app.v2.services.patient_roster import list_patient_roster
from app.v2.services.treatment_plan_store import (
    TREATMENT_PLAN_STATUS_ORDER,
    list_treatment_plan_imports,
    list_treatment_plan_queue_items,
    treatment_plan_aggregate_for_patient,
)
from app.v2.services.secure_storage import decrypt_text_secret
from app.v2.authorization import accessible_patient_ids, require_patient_manager, require_patient_read

router = APIRouter()
SPREADSHEET_FORMULA_PREFIXES: Final = ("=", "+", "-", "@")


@router.get("/api/health")
def api_health() -> dict[str, str]:
    return {"status": "ok", "runtime": "v2"}


@router.get("/health")
def health() -> dict[str, str]:
    return api_health()


@router.get("/api/readiness")
def readiness(db: DbSession) -> ReadinessOut:
    profile = _app_setting(db)
    api_status = "ok" if profile.api_client_secret and profile.emr_api_enabled else "warn"
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
    items = ["Status Dashboard", "Treatment Plans", "Patient Roster", "Manual Upload"]
    if user.role == "counselor":
        items.append("Corrections")
    if user.role == "admin":
        items.extend(["API Testing Harness", "Users", "Forensic Logs", "Settings"])
    items.append("Help")
    return {"items": items, "active_runtime": "v2"}


@router.get("/api/v2/dashboard", response_model=DashboardOut)
def dashboard(user: CurrentUser, db: DbSession) -> dict[str, JsonValue]:
    profile = _app_setting(db)
    allowed_ids = accessible_patient_ids(db, user)
    imports = tuple(item for item in list_treatment_plan_imports(db) if item.patient_id in allowed_ids)
    correction_counts = open_correction_counts_by_patient(db)
    return dashboard_payload(
        imports,
        api_configured=bool(profile.api_client_secret),
        api_client_id_configured=bool(profile.api_client_id.strip()),
        api_enabled=profile.emr_api_enabled,
        sync_enabled=profile.alleva_treatment_plan_sync_enabled,
        sync_authorized=profile.alleva_treatment_plan_sync_approved,
        loc_change_window_validated=profile.treatment_plan_loc_change_window_validated,
        returned_count=sum(count for patient_id, count in correction_counts.items() if patient_id in allowed_ids),
    )


def _app_setting(db: DbSession) -> AppSetting:
    return db.execute(select(AppSetting)).scalar_one()


@router.get("/api/v2/treatment-plans", response_model=TreatmentPlanListOut)
def treatment_plans(user: CurrentUser, db: DbSession) -> dict[str, JsonValue]:
    allowed_ids = accessible_patient_ids(db, user)
    items = tuple(item for item in list_treatment_plan_queue_items(db) if item.patient_id in allowed_ids)
    return {
        "items": [
            {
                "patient_id": item.patient_id,
                "patient_display_label": item.patient_display_label,
                "treatment_plan_id": item.treatment_plan_id,
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


@router.get("/api/v2/patient-roster", response_model=PatientRosterOut)
def patient_roster(user: CurrentUser, db: DbSession) -> PatientRosterOut:
    allowed_ids = accessible_patient_ids(db, user)
    items = tuple(item for item in list_patient_roster(db) if item.patient_id in allowed_ids)
    return PatientRosterOut(
        items=tuple(
            {
                "patient_id": item.patient_id,
                "source_mode": item.source_mode,
                "lifecycle_state": item.lifecycle_state,
                "current_level_of_care": item.current_level_of_care,
                "treatment_plan_id": item.treatment_plan_id,
                "treatment_plan_status": item.treatment_plan_status,
                "first_seen_at": item.first_seen_at,
                "last_seen_at": item.last_seen_at,
                "reconciled_at": item.reconciled_at,
            }
            for item in items
        )
    )


@router.get("/api/v2/treatment-plans/{patient_id}")
def treatment_plan_detail(
    patient_id: str,
    user: CurrentUser,
    db: DbSession,
    source_mode: SourceMode | None = None,
) -> TreatmentPlanAggregate:
    require_patient_read(db, user, patient_id)
    aggregate = treatment_plan_aggregate_for_patient(db, patient_id, source_system=source_mode)
    if aggregate is None:
        raise HTTPException(status_code=404, detail="Treatment-plan aggregate not found")
    record_audit_event(db, action="treatment_plan.detail.viewed", actor=user, target_entity_type="treatment_plan", target_entity_id=patient_id)
    return aggregate


@router.get("/api/v2/treatment-plans/{patient_id}/{treatment_plan_id}")
def treatment_plan_detail_by_id(
    patient_id: str,
    treatment_plan_id: str,
    user: CurrentUser,
    db: DbSession,
    source_mode: SourceMode | None = None,
) -> TreatmentPlanAggregate:
    require_patient_read(db, user, patient_id)
    aggregate = treatment_plan_aggregate_for_patient(
        db,
        patient_id,
        treatment_plan_id,
        source_system=source_mode,
    )
    if aggregate is None:
        raise HTTPException(status_code=404, detail="Treatment plan not found")
    record_audit_event(
        db,
        action="treatment_plan.detail.viewed",
        actor=user,
        target_entity_type="treatment_plan",
        target_entity_id=f"{patient_id}:{source_mode or 'any'}:{treatment_plan_id}",
    )
    return aggregate


@router.post("/api/v2/treatment-plans/{patient_id}/manager-actions")
def save_manager_action(patient_id: str, payload: ManagerActionInput, user: CurrentUser, db: DbSession) -> dict[str, JsonValue]:
    require_patient_manager(db, user, patient_id)
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
        commit=False,
    )
    if payload.action == "return_for_correction":
        try:
            save_returned_correction_work_item(
                db,
                patient_id=patient_id,
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
def create_api_harness_job(payload: ApiHarnessJobStart, actor: AdminUser, db: DbSession) -> ApiHarnessJob:
    if payload.job_type != "pull_all_treatment_plans_all_fields":
        raise HTTPException(status_code=400, detail="Unsupported V2 job type")
    profile = _app_setting(db)
    if not profile.emr_api_enabled:
        raise HTTPException(status_code=409, detail="Enable API testing before starting the configured harness job.")
    connection = HarnessConnection(
        api_base_url=profile.api_base_url, token_url=profile.api_oauth_token_url, client_id=profile.api_client_id,
        client_secret=decrypt_text_secret(profile.api_client_secret), scope=profile.api_scopes,
        token_auth_style=profile.api_token_auth_style, timeout_seconds=profile.emr_api_timeout_seconds,
        page_size=profile.api_pagination_limit,
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


@router.get("/api/v2/exports/{patient_id}/checklist-evidence.csv")
def redacted_checklist_export(patient_id: str, user: ManagerUser, db: DbSession) -> Response:
    require_patient_manager(db, user, patient_id)
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


@router.get("/api/v2/exports/treatment-plans.csv")
def treatment_plan_list_export(user: ManagerUser, db: DbSession) -> Response:
    allowed_ids = accessible_patient_ids(db, user)
    items = tuple(item for item in list_treatment_plan_queue_items(db) if item.patient_id in allowed_ids)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        (
            "patient_id",
            "treatment_plan_id",
            "status",
            "current_level_of_care",
            "admission_date",
            "next_due_date",
            "source_mode",
            "missing_criteria_count",
            "returned_criteria_count",
        )
    )
    for item in items:
        writer.writerow(
            tuple(
                _safe_csv_cell(str(value))
                for value in (
                    item.patient_id,
                    item.treatment_plan_id,
                    item.status,
                    item.current_level_of_care,
                    item.admission_date,
                    item.next_due_date,
                    item.source_mode,
                    item.missing_criteria_count,
                    item.returned_criteria_count,
                )
            )
        )
    record_audit_event(
        db,
        action="export.treatment_plan_list",
        actor=user,
        target_entity_type="treatment_plan_queue",
        target_entity_id="current",
        details={"treatment_plan_count": len(items)},
    )
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"content-disposition": "attachment; filename=treatment-plans.csv"},
    )


def _safe_csv_cell(value: str) -> str:
    if value.startswith(SPREADSHEET_FORMULA_PREFIXES):
        return f"'{value}"
    return value
