from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError

from app.v2.api.deps import DbSession, ManagerUser
from app.v2.authorization import patient_scope, require_patient_manager
from app.v2.services.audit_store import record_audit_event
from app.v2.services.manual_binder import (
    DEFAULT_BINDER_LIMITS,
    ManualBinderFile,
    ManualBinderRequest,
    ManualBinderResult,
    aggregate_from_manual_binder,
)
from app.v2.services.manual_file_types import ManualFileParseError, ManualFilePatientIdCorrectionRequired
from app.v2.services.manual_source_batch import (
    ManualSourcePersistenceRequest,
    cleanup_staged_manual_sources,
    persist_staged_manual_sources,
    stage_manual_sources,
)
from app.v2.services.treatment_plan_store import save_treatment_plan_aggregate

router = APIRouter()


class ManualBinderImportOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["imported", "imported_with_warnings"]
    patient_id: str
    patient_display_label: str
    source_mode: Literal["manual_upload"]
    criteria_total: int
    encrypted_at_rest: bool
    source_file_archived: bool
    source_file_id: str | None
    source_file_ids: tuple[str, ...]
    patient_id_correction_applied: bool
    file_count: int
    parsed_file_count: int
    opaque_file_count: int
    overall_status: str
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ManualBinderUploadInput:
    patient_id: str
    confirm_patient_id_correction: bool
    files: tuple[UploadFile, ...]


@dataclass(frozen=True, slots=True)
class ManualBinderAuditInput:
    parsed: ManualBinderResult
    source_ids: tuple[str, ...]


def manual_binder_upload_input(
    file: Annotated[list[UploadFile], File()],
    patient_id: Annotated[str, Form()] = "",
    confirm_patient_id_correction: Annotated[bool, Form()] = False,
) -> ManualBinderUploadInput:
    return ManualBinderUploadInput(
        patient_id=patient_id,
        confirm_patient_id_correction=confirm_patient_id_correction,
        files=tuple(file),
    )


@router.post(
    "/api/v2/manual-uploads/treatment-plan-file",
    response_model=ManualBinderImportOut,
    status_code=status.HTTP_201_CREATED,
)
def import_treatment_plan_binder(
    payload: Annotated[ManualBinderUploadInput, Depends(manual_binder_upload_input)],
    user: ManagerUser,
    db: DbSession,
) -> ManualBinderImportOut:
    try:
        binder_files = _read_binder_files(payload.files)
        parsed = aggregate_from_manual_binder(
            ManualBinderRequest(
                files=binder_files,
                fallback_patient_id=payload.patient_id,
                confirm_patient_id_correction=payload.confirm_patient_id_correction,
            )
        )
    except ManualFilePatientIdCorrectionRequired as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except ManualFileParseError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    if patient_scope(db, parsed.aggregate.patient_id) is not None:
        require_patient_manager(db, user, parsed.aggregate.patient_id)
    staged = stage_manual_sources(parsed.sources)
    try:
        row = save_treatment_plan_aggregate(db, parsed.aggregate, user, commit=False)
        stored_sources = persist_staged_manual_sources(
            db,
            ManualSourcePersistenceRequest(
                patient_id=row.patient_id,
                plan_id=row.plan_id,
                created_by_user_id=user.id,
                sources=staged,
            ),
        )
        _record_binder_audit(
            db,
            user,
            ManualBinderAuditInput(
                parsed=parsed,
                source_ids=tuple(source.document_id for source in stored_sources),
            ),
        )
        db.commit()
    except (OSError, SQLAlchemyError):
        db.rollback()
        cleanup_staged_manual_sources(staged)
        raise
    source_ids = tuple(source.document_id for source in stored_sources)
    return ManualBinderImportOut(
        status="imported_with_warnings" if parsed.warnings else "imported",
        patient_id=row.patient_id,
        patient_display_label=row.patient_display_label,
        source_mode="manual_upload",
        criteria_total=len(parsed.aggregate.criteria_results),
        encrypted_at_rest=True,
        source_file_archived=bool(source_ids),
        source_file_id=source_ids[0] if source_ids else None,
        source_file_ids=source_ids,
        patient_id_correction_applied=parsed.patient_id_correction_applied,
        file_count=len(payload.files),
        parsed_file_count=parsed.parsed_file_count,
        opaque_file_count=parsed.opaque_file_count,
        overall_status=parsed.aggregate.overall_status,
        warnings=parsed.warnings,
    )


def _read_binder_files(files: tuple[UploadFile, ...]) -> tuple[ManualBinderFile, ...]:
    if len(files) > DEFAULT_BINDER_LIMITS.max_file_count:
        raise ManualFileParseError(
            f"Manual treatment-plan binders are limited to {DEFAULT_BINDER_LIMITS.max_file_count} files.",
            413,
        )
    binder_files: list[ManualBinderFile] = []
    total_bytes = 0
    for upload in files:
        raw_bytes = upload.file.read(DEFAULT_BINDER_LIMITS.max_file_bytes + 1)
        total_bytes += len(raw_bytes)
        if len(raw_bytes) > DEFAULT_BINDER_LIMITS.max_file_bytes:
            raise ManualFileParseError("One manual treatment-plan source exceeds the per-file limit.", 413)
        if total_bytes > DEFAULT_BINDER_LIMITS.max_total_bytes:
            raise ManualFileParseError("Manual treatment-plan binder exceeds the total upload limit.", 413)
        binder_files.append(ManualBinderFile(raw_bytes=raw_bytes, filename=upload.filename or ""))
    return tuple(binder_files)


def _record_binder_audit(db: DbSession, user: ManagerUser, payload: ManualBinderAuditInput) -> None:
    parsed = payload.parsed
    source_ids = payload.source_ids
    scope = patient_scope(db, parsed.aggregate.patient_id)
    if scope is None:
        raise HTTPException(status_code=500, detail="Stored patient identity is unavailable")
    audit_patient_id = str(scope.patient_row_id)
    for source_id, source in zip(source_ids, parsed.sources, strict=False):
        record_audit_event(
            db,
            action="manual_upload.source_file.archived",
            actor=user,
            target_entity_type="treatment_plan",
            target_entity_id=audit_patient_id,
            details={
                "source_file_id": source_id,
                "source_format": source.source_format,
                "size_bytes": len(source.raw_bytes),
                "redaction_status": "encrypted_original_file",
            },
            commit=False,
        )
    if parsed.patient_id_correction_applied:
        record_audit_event(
            db,
            action="manual_upload.patient_id.corrected",
            actor=user,
            target_entity_type="treatment_plan",
            target_entity_id=audit_patient_id,
            details={
                "patient_id_correction_applied": True,
                "source_patient_id_present": True,
                "correction_confirmed": True,
            },
            commit=False,
        )
    record_audit_event(
        db,
        action="manual_upload.treatment_plan_file.imported",
        actor=user,
        target_entity_type="treatment_plan",
        target_entity_id=audit_patient_id,
        details={
            "source_mode": "manual_upload",
            "file_count": len(parsed.sources),
            "parsed_file_count": parsed.parsed_file_count,
            "opaque_file_count": parsed.opaque_file_count,
            "criteria_total": len(parsed.aggregate.criteria_results),
            "parsed_fields_count": parsed.parsed_fields_count,
            "source_file_archived": bool(source_ids),
            "patient_id_correction_applied": parsed.patient_id_correction_applied,
            "warnings_count": len(parsed.warnings),
        },
        commit=False,
    )
