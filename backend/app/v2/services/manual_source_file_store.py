from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.v2.domain.schemas import SourceDocumentRef
from app.v2.models import User
from app.v2.authorization import PlanVersionSelector, resolve_plan_version
from app.v2.services.treatment_plan_types import PlanVersionIdentity
from app.v2.services.secure_storage import decrypt_bytes
from app.v2.services.manual_binder import ManualBinderSource
from app.v2.services.manual_source_batch import (
    ManualSourcePersistenceRequest, cleanup_staged_manual_sources,
    persist_staged_manual_sources, stage_manual_sources,
)

from app.v2.services.manual_source_types import (
    SOURCE_KIND,
    SOURCE_DOWNLOAD_CONTENT_TYPES,
    SOURCE_EXTENSION_BY_FORMAT,
    ManualSourceFileArchiveInput,
    ManualSourceFileDownload,
    ManualSourceFileDelete,
    StoredSourceDocument,
)


def archive_manual_source_file(db: Session, payload: ManualSourceFileArchiveInput) -> StoredSourceDocument:
    actor = db.get(User, int(payload.created_by_user_id))
    if actor is None or not actor.is_active:
        raise HTTPException(status_code=403, detail="Access denied")
    identity = resolve_plan_version(db, actor, PlanVersionSelector(
        payload.patient_id, payload.plan_version_id, payload.patient_record_id, "manual_upload", payload.plan_id,
    ), manager=True)
    staged = stage_manual_sources((ManualBinderSource(
        payload.raw_bytes, payload.source_format, payload.content_type, hashlib.sha256(payload.raw_bytes).hexdigest(),
    ),))
    completed = False
    try:
        stored = persist_staged_manual_sources(db, ManualSourcePersistenceRequest(identity, actor, staged))
        db.commit()
        completed = True
    finally:
        if not completed:
            db.rollback()
            cleanup_staged_manual_sources(staged)
    return stored[0]


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


def source_documents_for_version(db: Session, identity: PlanVersionIdentity) -> tuple[SourceDocumentRef, ...]:
    rows = db.execute(text(
        "SELECT d.document_id,p.canonical_client_id,d.source_kind,d.source_format,d.content_type,d.size_bytes,"
        "d.sha256,d.encrypted_relative_path,d.created_at FROM source_document_plan_memberships m "
        "JOIN source_documents d ON d.id=m.source_document_id JOIN patients p ON p.id=d.patient_id "
        "JOIN treatment_plan_versions v ON v.id=m.plan_version_id AND v.patient_id=d.patient_id "
        "WHERE m.plan_version_id=:version AND p.id=:patient AND v.source_system='manual_upload' "
        "AND p.source_system='manual_upload' AND d.source_kind=:kind AND m.detached_at IS NULL "
        "ORDER BY d.created_at DESC,d.id DESC"
    ), {"version": identity.plan_version_id, "patient": identity.patient_record_id, "kind": SOURCE_KIND}).all()
    refs = tuple(_document_ref(_stored_row(row)) for row in rows)
    selector = f"?plan_version_id={identity.plan_version_id}&patient_record_id={identity.patient_record_id}&source_mode=manual_upload"
    return tuple(ref.model_copy(update={"download_url": ref.download_url + selector}) for ref in refs)


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
    protected = db.execute(text(
        "SELECT 1 FROM source_documents d WHERE d.document_id=:document AND (d.plan_version_id IS NOT NULL "
        "OR d.review_version_id IS NOT NULL OR EXISTS (SELECT 1 FROM source_document_plan_memberships m "
        "WHERE m.source_document_id=d.id))"
    ), {"document": source_file_id}).first()
    if protected is not None:
        raise HTTPException(status_code=409, detail="Source removal is unavailable while the archive retention policy is unresolved.")
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
