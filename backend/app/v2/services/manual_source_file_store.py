from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import quote
from uuid import uuid4
from datetime import timezone

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.v2.domain.schemas import SourceDocumentRef
from app.v2.models import utc_now
from app.v2.services.secure_storage import decrypt_bytes, encrypt_bytes, ensure_private_directory

SOURCE_KIND = "manual_treatment_plan_file"
SOURCE_DOWNLOAD_CONTENT_TYPES: Final = {
    "application/msword",
    "application/pdf",
    "application/rtf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/zip",
    "image/jpeg",
    "image/png",
    "text/plain",
    "text/csv",
    "text/tab-separated-values",
    "text/markdown",
}
SOURCE_EXTENSION_BY_FORMAT: Final = {
    "csv": "csv",
    "doc": "doc",
    "docx": "docx",
    "jpeg": "jpg",
    "pdf": "pdf",
    "png": "png",
    "rtf": "rtf",
    "markdown": "md",
    "text": "txt",
    "tsv": "tsv",
    "xlsx": "xlsx",
    "zip": "zip",
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


@dataclass(frozen=True, slots=True)
class StoredSourceDocument:
    document_id: str
    patient_id: str
    source_kind: str
    source_format: str
    content_type: str
    size_bytes: int
    sha256: str
    encrypted_relative_path: str
    created_at: str
    redaction_status: str = "encrypted_original_file"


def archive_manual_source_file(db: Session, payload: ManualSourceFileArchiveInput) -> StoredSourceDocument:
    content_sha256 = hashlib.sha256(payload.raw_bytes).hexdigest()
    existing = _source_document_by_hash(db, payload.patient_id, content_sha256)
    if existing is not None:
        return existing
    document_id = uuid4().hex
    relative_path = Path("manual-uploads") / f"{document_id}.izcna1"
    encrypted_path = settings.local_app_data_dir / relative_path
    ensure_private_directory(encrypted_path.parent)
    encrypted_path.write_bytes(encrypt_bytes(payload.raw_bytes))
    created_at = utc_now().astimezone(timezone.utc).isoformat()
    row = StoredSourceDocument(
        document_id=document_id,
        patient_id=payload.patient_id,
        source_kind=SOURCE_KIND,
        source_format=payload.source_format,
        content_type=payload.content_type,
        size_bytes=len(payload.raw_bytes),
        sha256=content_sha256,
        encrypted_relative_path=relative_path.as_posix(),
        created_at=created_at,
    )
    try:
        linkage = db.execute(
            text(
                """SELECT p.id,v.id FROM patients p JOIN treatment_plan_versions v ON v.patient_id=p.id
                WHERE p.canonical_client_id=:client_id AND v.source_record_id=:plan_id
                ORDER BY v.version_ordinal DESC,v.id DESC LIMIT 1"""
            ),
            {"client_id": payload.patient_id, "plan_id": payload.plan_id},
        ).one()
        db.execute(
            text(
                """INSERT INTO source_documents(
                    patient_id,plan_version_id,document_id,source_kind,source_format,content_type,size_bytes,sha256,
                    encrypted_relative_path,created_by_user_id,created_at
                ) VALUES(:patient_id,:plan_version_id,:document_id,:source_kind,:source_format,:content_type,:size_bytes,
                    :sha256,:relative_path,:created_by_user_id,:created_at)"""
            ),
            {
                "patient_id": int(linkage[0]),
                "plan_version_id": int(linkage[1]),
                "document_id": row.document_id,
                "source_kind": row.source_kind,
                "source_format": row.source_format,
                "content_type": row.content_type,
                "size_bytes": row.size_bytes,
                "sha256": row.sha256,
                "relative_path": row.encrypted_relative_path,
                "created_by_user_id": int(payload.created_by_user_id),
                "created_at": row.created_at,
            },
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        encrypted_path.unlink(missing_ok=True)
        raise
    return row


def source_documents_for_patient(db: Session, patient_id: str) -> tuple[SourceDocumentRef, ...]:
    rows = db.execute(
        text(
            """SELECT d.document_id,p.canonical_client_id,d.source_kind,d.source_format,d.content_type,d.size_bytes,
                d.sha256,d.encrypted_relative_path,d.created_at
            FROM source_documents d JOIN patients p ON p.id=d.patient_id
            WHERE p.canonical_client_id=:client_id AND d.source_kind=:source_kind ORDER BY d.created_at DESC,d.id DESC"""
        ),
        {"client_id": patient_id, "source_kind": SOURCE_KIND},
    ).all()
    return tuple(_document_ref(_stored_row(row)) for row in rows)


def download_manual_source_file(db: Session, patient_id: str, source_file_id: str) -> ManualSourceFileDownload:
    row = _source_document(db, patient_id, source_file_id)
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
    row = _source_document(db, patient_id, source_file_id)
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
    db.execute(text("DELETE FROM source_documents WHERE document_id=:document_id"), {"document_id": row.document_id})
    db.commit()
    return deleted


def _document_ref(row: StoredSourceDocument) -> SourceDocumentRef:
    patient_id = quote(row.patient_id, safe="")
    return SourceDocumentRef(
        source_file_id=row.document_id,
        source_kind=row.source_kind,
        source_format=row.source_format,
        content_type=_media_type(row),
        size_bytes=row.size_bytes,
        sha256=row.sha256,
        redaction_status=row.redaction_status,
        created_at=row.created_at,
        download_url=f"/api/v2/treatment-plans/{patient_id}/source-documents/{row.document_id}/download",
    )


def _stored_document_path(row: StoredSourceDocument) -> Path:
    relative_path = Path(row.encrypted_relative_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise FileNotFoundError(row.document_id)
    root = settings.local_app_data_dir.resolve()
    stored_path = (root / relative_path).resolve()
    if not stored_path.is_relative_to(root):
        raise FileNotFoundError(row.document_id)
    return stored_path


def _media_type(row: StoredSourceDocument) -> str:
    if row.content_type in SOURCE_DOWNLOAD_CONTENT_TYPES:
        return row.content_type
    return "text/plain"


def _safe_download_filename(row: StoredSourceDocument) -> str:
    extension = SOURCE_EXTENSION_BY_FORMAT.get(row.source_format, "txt")
    return f"manual-treatment-plan-source-{row.document_id[:12]}.{extension}"


def _source_document(db: Session, patient_id: str, source_file_id: str) -> StoredSourceDocument | None:
    row = db.execute(
        text(
            """SELECT d.document_id,p.canonical_client_id,d.source_kind,d.source_format,d.content_type,d.size_bytes,
                d.sha256,d.encrypted_relative_path,d.created_at
            FROM source_documents d JOIN patients p ON p.id=d.patient_id
            WHERE p.canonical_client_id=:client_id AND d.document_id=:document_id AND d.source_kind=:source_kind"""
        ),
        {"client_id": patient_id, "document_id": source_file_id, "source_kind": SOURCE_KIND},
    ).one_or_none()
    return _stored_row(row) if row is not None else None


def _source_document_by_hash(db: Session, patient_id: str, content_sha256: str) -> StoredSourceDocument | None:
    row = db.execute(
        text(
            """SELECT d.document_id,p.canonical_client_id,d.source_kind,d.source_format,d.content_type,d.size_bytes,
                d.sha256,d.encrypted_relative_path,d.created_at
            FROM source_documents d JOIN patients p ON p.id=d.patient_id
            WHERE p.canonical_client_id=:client_id AND d.sha256=:sha256 AND d.source_kind=:source_kind"""
        ),
        {"client_id": patient_id, "sha256": content_sha256, "source_kind": SOURCE_KIND},
    ).one_or_none()
    return _stored_row(row) if row is not None else None


def _stored_row(row) -> StoredSourceDocument:
    return StoredSourceDocument(
        document_id=str(row[0]),
        patient_id=str(row[1]),
        source_kind=str(row[2]),
        source_format=str(row[3]),
        content_type=str(row[4]),
        size_bytes=int(row[5]),
        sha256=str(row[6]),
        encrypted_relative_path=str(row[7]),
        created_at=str(row[8]),
    )
