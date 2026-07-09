from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import quote
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.v2.domain.schemas import SourceDocumentRef
from app.v2.models import UploadedDocument
from app.v2.services.secure_storage import decrypt_bytes, encrypt_bytes, ensure_private_directory

SOURCE_KIND = "manual_treatment_plan_file"
SOURCE_DOWNLOAD_CONTENT_TYPES: Final = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
    "text/csv",
    "text/tab-separated-values",
    "text/markdown",
}
SOURCE_EXTENSION_BY_FORMAT: Final = {
    "csv": "csv",
    "pdf": "pdf",
    "markdown": "md",
    "text": "txt",
    "tsv": "tsv",
    "xlsx": "xlsx",
}


@dataclass(frozen=True, slots=True)
class ManualSourceFileArchiveInput:
    raw_bytes: bytes
    patient_id: str
    plan_id: str
    source_format: str
    content_type: str
    created_by_user_id: str


@dataclass(frozen=True, slots=True)
class ManualSourceFileDownload:
    raw_bytes: bytes
    media_type: str
    safe_filename: str
    source_format: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ManualSourceFileDelete:
    source_file_id: str
    source_format: str
    size_bytes: int
    file_removed: bool


def archive_manual_source_file(db: Session, payload: ManualSourceFileArchiveInput) -> UploadedDocument:
    document_id = uuid4().hex
    relative_path = Path("manual-uploads") / f"{document_id}.izcna1"
    encrypted_path = settings.local_app_data_dir / relative_path
    ensure_private_directory(encrypted_path.parent)
    encrypted_path.write_bytes(encrypt_bytes(payload.raw_bytes))
    row = UploadedDocument(
        document_id=document_id,
        patient_id=payload.patient_id,
        plan_id=payload.plan_id,
        source_kind=SOURCE_KIND,
        source_format=payload.source_format,
        content_type=payload.content_type,
        size_bytes=len(payload.raw_bytes),
        sha256=hashlib.sha256(payload.raw_bytes).hexdigest(),
        storage_path=relative_path.as_posix(),
        redaction_status="encrypted_original_file",
        created_by_user_id=payload.created_by_user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def source_documents_for_patient(db: Session, patient_id: str) -> tuple[SourceDocumentRef, ...]:
    rows = db.execute(
        select(UploadedDocument)
        .where(UploadedDocument.patient_id == patient_id)
        .where(UploadedDocument.source_kind == SOURCE_KIND)
        .order_by(UploadedDocument.created_at.desc()),
    ).scalars()
    return tuple(_document_ref(row) for row in rows)


def download_manual_source_file(db: Session, patient_id: str, source_file_id: str) -> ManualSourceFileDownload:
    row = db.execute(
        select(UploadedDocument)
        .where(UploadedDocument.patient_id == patient_id)
        .where(UploadedDocument.document_id == source_file_id)
        .where(UploadedDocument.source_kind == SOURCE_KIND),
    ).scalar_one_or_none()
    if row is None:
        raise FileNotFoundError(source_file_id)
    raw_bytes = decrypt_bytes(_stored_document_path(row).read_bytes())
    if hashlib.sha256(raw_bytes).hexdigest() != row.sha256:
        raise HTTPException(status_code=500, detail="Stored source file hash mismatch")
    return ManualSourceFileDownload(
        raw_bytes=raw_bytes,
        media_type=_media_type(row),
        safe_filename=_safe_download_filename(row),
        source_format=row.source_format,
        size_bytes=row.size_bytes,
    )


def delete_manual_source_file(db: Session, patient_id: str, source_file_id: str) -> ManualSourceFileDelete:
    row = db.execute(
        select(UploadedDocument)
        .where(UploadedDocument.patient_id == patient_id)
        .where(UploadedDocument.document_id == source_file_id)
        .where(UploadedDocument.source_kind == SOURCE_KIND),
    ).scalar_one_or_none()
    if row is None:
        raise FileNotFoundError(source_file_id)
    stored_path = _stored_document_path(row)
    file_removed = stored_path.exists()
    if file_removed:
        stored_path.unlink()
    deleted = ManualSourceFileDelete(
        source_file_id=row.document_id,
        source_format=row.source_format,
        size_bytes=row.size_bytes,
        file_removed=file_removed,
    )
    db.delete(row)
    db.commit()
    return deleted


def _document_ref(row: UploadedDocument) -> SourceDocumentRef:
    patient_id = quote(row.patient_id, safe="")
    return SourceDocumentRef(
        source_file_id=row.document_id,
        source_kind=row.source_kind,
        source_format=row.source_format,
        content_type=_media_type(row),
        size_bytes=row.size_bytes,
        sha256=row.sha256,
        redaction_status=row.redaction_status,
        created_at=row.created_at.isoformat() if row.created_at else "",
        download_url=f"/api/v2/treatment-plans/{patient_id}/source-documents/{row.document_id}/download",
    )


def _stored_document_path(row: UploadedDocument) -> Path:
    relative_path = Path(row.storage_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise FileNotFoundError(row.document_id)
    root = settings.local_app_data_dir.resolve()
    stored_path = (root / relative_path).resolve()
    if not stored_path.is_relative_to(root):
        raise FileNotFoundError(row.document_id)
    return stored_path


def _media_type(row: UploadedDocument) -> str:
    if row.content_type in SOURCE_DOWNLOAD_CONTENT_TYPES:
        return row.content_type
    return "text/plain"


def _safe_download_filename(row: UploadedDocument) -> str:
    extension = SOURCE_EXTENSION_BY_FORMAT.get(row.source_format, "txt")
    return f"manual-treatment-plan-source-{row.document_id[:12]}.{extension}"
