from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict

from app.v2.api.deps import DbSession, ManagerUser
from app.v2.authorization import patient_scope, require_patient_manager
from app.v2.domain.schemas import TreatmentPlanAggregate
from app.v2.services.audit_store import record_audit_event
from app.v2.services.manual_file_parser import aggregate_from_manual_file
from app.v2.services.manual_file_types import ManualFileParseError, ManualFilePatientIdCorrectionRequired
from app.v2.services.manual_source_file_store import (
    ManualSourceFileArchiveInput,
    archive_manual_source_file,
    delete_manual_source_file,
    download_manual_source_file,
)
from app.v2.services.treatment_plan_store import save_treatment_plan_aggregate

router = APIRouter()


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


@dataclass(frozen=True, slots=True)
class ManualFileUploadInput:
    patient_id: str
    confirm_patient_id_correction: bool
    file: UploadFile


def manual_file_upload_input(
    file: Annotated[UploadFile, File()],
    patient_id: Annotated[str, Form()] = "",
    confirm_patient_id_correction: Annotated[bool, Form()] = False,
) -> ManualFileUploadInput:
    return ManualFileUploadInput(
        patient_id=patient_id,
        confirm_patient_id_correction=confirm_patient_id_correction,
        file=file,
    )


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
    record_audit_event(
        db,
        action="manual_upload.treatment_plan_aggregate.imported",
        actor=user,
        target_entity_type="treatment_plan",
        target_entity_id=row.patient_id,
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


@router.post(
    "/api/v2/manual-uploads/treatment-plan-file",
    response_model=ManualTreatmentPlanImportOut,
    status_code=status.HTTP_201_CREATED,
)
def import_treatment_plan_file(
    payload: Annotated[ManualFileUploadInput, Depends(manual_file_upload_input)],
    user: ManagerUser,
    db: DbSession,
) -> ManualTreatmentPlanImportOut:
    raw_bytes = payload.file.file.read()
    try:
        parsed = aggregate_from_manual_file(
            raw_bytes,
            payload.patient_id,
            payload.file.filename or "",
            payload.confirm_patient_id_correction,
        )
    except ManualFilePatientIdCorrectionRequired as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except ManualFileParseError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc
    if patient_scope(db, parsed.aggregate.patient_id) is not None:
        require_patient_manager(db, user, parsed.aggregate.patient_id)
    row = save_treatment_plan_aggregate(db, parsed.aggregate, user)
    source_file = archive_manual_source_file(
        db,
        ManualSourceFileArchiveInput(
            raw_bytes=raw_bytes,
            patient_id=row.patient_id,
            plan_id=row.plan_id,
            source_format=parsed.source_format,
            content_type=payload.file.content_type or "",
            created_by_user_id=str(user.id),
        ),
    )
    record_audit_event(
        db,
        action="manual_upload.source_file.archived",
        actor=user,
        target_entity_type="treatment_plan",
        target_entity_id=row.patient_id,
        details={
            "source_file_id": source_file.document_id,
            "source_format": source_file.source_format,
            "size_bytes": source_file.size_bytes,
            "redaction_status": source_file.redaction_status,
        },
    )
    if parsed.patient_id_correction_applied:
        record_audit_event(
            db,
            action="manual_upload.patient_id.corrected",
            actor=user,
            target_entity_type="treatment_plan",
            target_entity_id=row.patient_id,
            details={
                "patient_id_correction_applied": True,
                "source_patient_id_present": True,
                "correction_confirmed": True,
            },
        )
    record_audit_event(
        db,
        action="manual_upload.treatment_plan_file.imported",
        actor=user,
        target_entity_type="treatment_plan",
        target_entity_id=row.patient_id,
        details={
            "source_mode": row.source_mode,
            "source_format": parsed.source_format,
            "criteria_total": len(parsed.aggregate.criteria_results),
            "parsed_fields_count": parsed.parsed_fields_count,
            "source_file_archived": True,
            "source_file_id": source_file.document_id,
            "patient_id_correction_applied": parsed.patient_id_correction_applied,
        },
    )
    return ManualTreatmentPlanImportOut(
        status="imported",
        patient_id=row.patient_id,
        patient_display_label=row.patient_display_label,
        source_mode="manual_upload",
        criteria_total=len(parsed.aggregate.criteria_results),
        encrypted_at_rest=True,
        source_file_archived=True,
        source_file_id=source_file.document_id,
        patient_id_correction_applied=parsed.patient_id_correction_applied,
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
    require_patient_manager(db, user, patient_id)
    try:
        deleted = delete_manual_source_file(db, patient_id, source_file_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Source file not found") from exc
    record_audit_event(
        db,
        action="manual_upload.source_file.deleted",
        actor=user,
        target_entity_type="treatment_plan",
        target_entity_id=patient_id,
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
    require_patient_manager(db, user, patient_id)
    try:
        download = download_manual_source_file(db, patient_id, source_file_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Source file not found") from exc
    record_audit_event(
        db,
        action="manual_upload.source_file.downloaded",
        actor=user,
        target_entity_type="treatment_plan",
        target_entity_id=patient_id,
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
