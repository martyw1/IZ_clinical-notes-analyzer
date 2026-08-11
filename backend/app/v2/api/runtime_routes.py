from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
from typing import Final

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import BUILD_CHANNEL, settings
from app.services.version import JsonValue, build_version_payload
from app.v2.api.deps import AdminUser, CurrentUser, DbSession, ManagerUser
from app.v2.api.models import (
    ApiHarnessJobStart,
    DashboardOut,
    ManagerActionInput,
    PatientRecordDetailOut,
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
from app.v2.services.patient_record import patient_record_detail
from app.v2.services.treatment_plan_store import (
    TREATMENT_PLAN_STATUS_ORDER,
    list_treatment_plan_imports,
    list_treatment_plan_queue_items,
    treatment_plan_aggregate_for_patient,
)
from app.v2.services.secure_storage import decrypt_api_client_id, decrypt_text_secret
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
    allowed_ids = accessible_patient_ids(db, user)
    imports = tuple(item for item in list_treatment_plan_imports(db) if item.patient_id in allowed_ids)
    correction_counts = open_correction_counts_by_patient(db)
    return dashboard_payload(
        imports,
        api_configured=bool(profile.api_client_secret),
        api_client_id_configured=bool(client_id.strip()),
        api_enabled=profile.emr_api_enabled,
        sync_enabled=profile.alleva_treatment_plan_sync_enabled,
        sync_authorized=profile.alleva_treatment_plan_sync_approved,
        loc_change_window_validated=profile.treatment_plan_loc_change_window_validated,
        returned_count=sum(count for patient_id, count in correction_counts.items() if patient_id in allowed_ids),
    )


def _app_setting(db: DbSession) -> AppSetting:
    return db.execute(select(AppSetting)).scalar_one()


def _patient_row_id(db: Session, patient_id: str, source_mode: SourceMode | None = None) -> int:
    row = db.execute(
        text(
            "SELECT id FROM patients WHERE canonical_client_id=:patient_id "
            "AND (:source_mode IS NULL OR source_system=:source_mode) "
            "ORDER BY CASE WHEN source_system='alleva_rest_api' THEN 0 ELSE 1 END,id DESC LIMIT 1"
        ),
        {"patient_id": patient_id, "source_mode": source_mode},
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Patient record not found")
    return int(row[0])


def _treatment_plan_version_id(
    db: Session,
    patient_id: str,
    treatment_plan_id: str,
    source_mode: SourceMode | None,
) -> tuple[int, int]:
    row = db.execute(
        text(
            "SELECT v.id,p.id FROM treatment_plan_versions v "
            "JOIN patients p ON p.id=v.patient_id "
            "WHERE p.canonical_client_id=:patient_id AND v.source_record_id=:treatment_plan_id "
            "AND (:source_mode IS NULL OR v.source_system=:source_mode) "
            "ORDER BY v.version_ordinal DESC,v.id DESC LIMIT 1"
        ),
        {
            "patient_id": patient_id,
            "treatment_plan_id": treatment_plan_id,
            "source_mode": source_mode,
        },
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Treatment plan not found")
    return int(row[0]), int(row[1])


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
    plan_version_id, patient_row_id = _treatment_plan_version_id(
        db,
        patient_id,
        aggregate.content_snapshot.plan_id,
        aggregate.source_mode,
    )
    record_audit_event(
        db,
        action="treatment_plan.detail.viewed",
        actor=user,
        target_entity_type="treatment_plan_version",
        target_entity_id=str(plan_version_id),
        details={"patient_row_id": patient_row_id},
    )
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
    plan_version_id, patient_row_id = _treatment_plan_version_id(
        db,
        patient_id,
        treatment_plan_id,
        aggregate.source_mode,
    )
    record_audit_event(
        db,
        action="treatment_plan.detail.viewed",
        actor=user,
        target_entity_type="treatment_plan_version",
        target_entity_id=str(plan_version_id),
        details={"patient_row_id": patient_row_id},
    )
    return aggregate


@router.get("/api/v2/patients/{patient_id}", response_model=PatientRecordDetailOut)
def patient_detail(
    patient_id: str,
    user: CurrentUser,
    db: DbSession,
    source_mode: SourceMode | None = None,
) -> PatientRecordDetailOut:
    require_patient_read(db, user, patient_id)
    detail = patient_record_detail(db, patient_id, source_mode)
    if detail is None:
        raise HTTPException(status_code=404, detail="Patient record not found")
    record_audit_event(
        db,
        action="patient_record.detail.viewed",
        actor=user,
        target_entity_type="patient",
        target_entity_id=str(detail.patient_row_id),
        details={
            "snapshot_id": detail.snapshot_id,
            "snapshot_version_count": detail.snapshot_version_count,
            "field_count": detail.field_count,
        },
    )
    return PatientRecordDetailOut(
        mrn=detail.mrn,
        full_name=detail.full_name,
        source_mode=detail.source_mode,
        lifecycle_state=detail.lifecycle_state,
        current_level_of_care=detail.current_level_of_care,
        source_last_updated=detail.source_last_updated,
        first_seen_at=detail.first_seen_at,
        last_seen_at=detail.last_seen_at,
        reconciled_at=detail.reconciled_at,
        treatment_plans=tuple(
            {"treatment_plan_id": plan.treatment_plan_id, "last_updated": plan.last_updated}
            for plan in detail.treatment_plans
        ),
        patient_record=detail.patient_record,
    )


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
    patient_row_id = _patient_row_id(db, patient_id)
    record_audit_event(
        db,
        action=f"manager.criterion.{payload.action}",
        actor=user,
        target_entity_type="treatment_plan_criterion",
        target_entity_id=f"{patient_row_id}:{payload.criterion_id}",
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
    plan_version_id, patient_row_id = _treatment_plan_version_id(
        db,
        patient_id,
        aggregate.content_snapshot.plan_id,
        aggregate.source_mode,
    )
    record_audit_event(
        db,
        action="export.redacted_checklist_evidence",
        actor=user,
        target_entity_type="treatment_plan_version",
        target_entity_id=str(plan_version_id),
        details={"patient_row_id": patient_row_id},
    )
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
