from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from app.v2.api.manual_binder_routes import router as manual_binder_router
from app.v2.api.deps import DbSession, ManagerUser
from app.v2.authorization import PlanVersionSelector, require_manual_patient_manager, resolve_plan_version
from app.v2.domain.schemas import SourceMode, TreatmentPlanAggregate
from app.v2.services.treatment_plan_types import PlanVersionIdentity
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
    plan_version_id: int
    patient_record_id: int
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
    require_manual_patient_manager(db, user, aggregate.patient_id)
    if aggregate.source_mode != "manual_upload":
        raise HTTPException(status_code=400, detail="Manual aggregate uploads must use source_mode=manual_upload")
    row = save_treatment_plan_aggregate(db, aggregate, user, commit=False)
    record_audit_event(
        db,
        action="manual_upload.treatment_plan_aggregate.imported",
        actor=user,
        target_entity_type="treatment_plan",
        target_entity_id=str(row.patient_record_id),
        details={"source_mode": row.source_mode, "criteria_total": len(aggregate.criteria_results)},
    )
    return ManualTreatmentPlanImportOut(
        status="imported",
        patient_id=row.patient_id,
        plan_version_id=row.plan_version_id,
        patient_record_id=row.patient_record_id,
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
    plan_version_id: int | None = None,
    patient_record_id: int | None = None,
    source_mode: SourceMode | None = None,
) -> ManualSourceFileDeleteOut:
    identity = _source_document_identity(db, user, source_file_id, PlanVersionSelector(patient_id, plan_version_id, patient_record_id, source_mode))
    try:
        deleted = delete_manual_source_file(db, patient_id, source_file_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Source file not found") from exc
    record_audit_event(
        db,
        action="manual_upload.source_file.deleted",
        actor=user,
        target_entity_type="treatment_plan",
        target_entity_id=str(identity.plan_version_id),
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
    plan_version_id: int | None = None,
    patient_record_id: int | None = None,
    source_mode: SourceMode | None = None,
) -> Response:
    identity = _source_document_identity(db, user, source_file_id, PlanVersionSelector(patient_id, plan_version_id, patient_record_id, source_mode))
    try:
        download = download_manual_source_file(db, patient_id, source_file_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Source file not found") from exc
    record_audit_event(
        db,
        action="manual_upload.source_file.downloaded",
        actor=user,
        target_entity_type="treatment_plan",
        target_entity_id=str(identity.plan_version_id),
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


def _source_document_identity(
    db: DbSession, user: ManagerUser, source_file_id: str, selector: PlanVersionSelector,
) -> PlanVersionIdentity:
    row = db.execute(text(
        "SELECT d.patient_id,d.plan_version_id FROM source_documents d JOIN patients p ON p.id=d.patient_id "
        "WHERE d.document_id=:document AND p.canonical_client_id=:patient AND d.source_kind='manual_treatment_plan_file'"
    ), {"document": source_file_id, "patient": selector.patient_id}).first()
    if row is None or row[1] is None:
        raise HTTPException(status_code=404, detail="Source file not found")
    if selector.plan_version_id is not None and selector.plan_version_id != int(row[1]):
        raise HTTPException(status_code=404, detail="Source file not found")
    if selector.patient_record_id is not None and selector.patient_record_id != int(row[0]):
        raise HTTPException(status_code=404, detail="Source file not found")
    return resolve_plan_version(db, user, PlanVersionSelector(selector.patient_id, int(row[1]), int(row[0]), selector.source_mode), manager=True)
