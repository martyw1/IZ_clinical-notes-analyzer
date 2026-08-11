from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict

from app.v2.api.manual_binder_routes import router as manual_binder_router
from app.v2.api.deps import DbSession, ManagerUser
from app.v2.authorization import patient_scope, require_patient_manager
from app.v2.domain.schemas import TreatmentPlanAggregate
from app.v2.services.audit_store import record_audit_event
from app.v2.services.manual_source_file_store import (
    delete_manual_source_file,
    download_manual_source_file,
)
from app.v2.services.treatment_plan_store import save_treatment_plan_aggregate

router = APIRouter()
router.include_router(manual_binder_router)


class ManualTreatmentPlanImportOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["imported"]
    patient_id: str
    patient_display_label: str
    source_mode: Literal["manual_upload"]
    criteria_total: int
    encrypted_at_rest: bool
    source_file_archived: bool = False
    source_file_id: str | None = None
    patient_id_correction_applied: bool = False


class ManualSourceFileDeleteOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["deleted"]
    source_file_id: str
    file_removed: bool


@router.post(
    "/api/v2/manual-uploads/treatment-plan-aggregate",
    response_model=ManualTreatmentPlanImportOut,
    status_code=status.HTTP_201_CREATED,
)
def import_treatment_plan_aggregate(
    aggregate: TreatmentPlanAggregate,
    user: ManagerUser,
    db: DbSession,
) -> ManualTreatmentPlanImportOut:
    if patient_scope(db, aggregate.patient_id) is not None:
        require_patient_manager(db, user, aggregate.patient_id)
    if aggregate.source_mode != "manual_upload":
        raise HTTPException(status_code=400, detail="Manual aggregate uploads must use source_mode=manual_upload")
    row = save_treatment_plan_aggregate(db, aggregate, user)
    saved_scope = patient_scope(db, row.patient_id)
    if saved_scope is None:
        raise HTTPException(status_code=500, detail="Stored patient identity is unavailable")
    record_audit_event(
        db,
        action="manual_upload.treatment_plan_aggregate.imported",
        actor=user,
        target_entity_type="treatment_plan",
        target_entity_id=str(saved_scope.patient_row_id),
        details={"source_mode": row.source_mode, "criteria_total": len(aggregate.criteria_results)},
    )
    return ManualTreatmentPlanImportOut(
        status="imported",
        patient_id=row.patient_id,
        patient_display_label=row.patient_display_label,
        source_mode="manual_upload",
        criteria_total=len(aggregate.criteria_results),
        encrypted_at_rest=True,
    )


@router.delete(
    "/api/v2/treatment-plans/{patient_id}/source-documents/{source_file_id}",
    response_model=ManualSourceFileDeleteOut,
)
def delete_treatment_plan_source_document(
    patient_id: str,
    source_file_id: str,
    user: ManagerUser,
    db: DbSession,
) -> ManualSourceFileDeleteOut:
    scope = require_patient_manager(db, user, patient_id)
    try:
        deleted = delete_manual_source_file(db, patient_id, source_file_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Source file not found") from exc
    record_audit_event(
        db,
        action="manual_upload.source_file.deleted",
        actor=user,
        target_entity_type="treatment_plan",
        target_entity_id=str(scope.patient_row_id),
        details={
            "source_file_id": deleted.source_file_id,
            "source_format": deleted.source_format,
            "size_bytes": deleted.size_bytes,
            "file_removed": deleted.file_removed,
            "redaction_status": "encrypted_source_removed",
        },
    )
    return ManualSourceFileDeleteOut(status="deleted", source_file_id=deleted.source_file_id, file_removed=deleted.file_removed)


@router.get("/api/v2/treatment-plans/{patient_id}/source-documents/{source_file_id}/download")
def download_treatment_plan_source_document(
    patient_id: str,
    source_file_id: str,
    user: ManagerUser,
    db: DbSession,
) -> Response:
    scope = require_patient_manager(db, user, patient_id)
    try:
        download = download_manual_source_file(db, patient_id, source_file_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Source file not found") from exc
    record_audit_event(
        db,
        action="manual_upload.source_file.downloaded",
        actor=user,
        target_entity_type="treatment_plan",
        target_entity_id=str(scope.patient_row_id),
        details={
            "source_file_id": source_file_id,
            "source_format": download.source_format,
            "size_bytes": download.size_bytes,
            "redaction_status": "decrypted_for_authorized_download",
        },
    )
    return Response(
        content=download.raw_bytes,
        media_type=download.media_type,
        headers={"content-disposition": f'attachment; filename="{download.safe_filename}"'},
    )
