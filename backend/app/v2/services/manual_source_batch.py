from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.v2.models import utc_now
from app.v2.services.manual_binder import ManualBinderSource
from app.v2.services.manual_source_file_store import SOURCE_KIND, StoredSourceDocument
from app.v2.services.secure_storage import encrypt_bytes, ensure_private_directory


@dataclass(frozen=True, slots=True)
class StagedManualSource:
    document_id: str
    source_format: str
    content_type: str
    size_bytes: int
    sha256: str
    encrypted_relative_path: str
    encrypted_path: Path


@dataclass(frozen=True, slots=True)
class ManualSourcePersistenceRequest:
    patient_id: str
    plan_id: str
    created_by_user_id: int
    sources: tuple[StagedManualSource, ...]


def stage_manual_sources(sources: tuple[ManualBinderSource, ...]) -> tuple[StagedManualSource, ...]:
    staged: list[StagedManualSource] = []
    try:
        for source in sources:
            document_id = uuid4().hex
            relative_path = Path("manual-uploads") / f"{document_id}.izcna1"
            encrypted_path = settings.local_app_data_dir / relative_path
            temporary_path = encrypted_path.with_name(f".{document_id}.tmp")
            ensure_private_directory(encrypted_path.parent)
            temporary_path.write_bytes(encrypt_bytes(source.raw_bytes))
            temporary_path.replace(encrypted_path)
            staged.append(
                StagedManualSource(
                    document_id=document_id,
                    source_format=source.source_format,
                    content_type=source.content_type,
                    size_bytes=len(source.raw_bytes),
                    sha256=source.sha256,
                    encrypted_relative_path=relative_path.as_posix(),
                    encrypted_path=encrypted_path,
                )
            )
    except OSError:
        cleanup_staged_manual_sources(tuple(staged))
        raise
    return tuple(staged)


def persist_staged_manual_sources(
    db: Session,
    request: ManualSourcePersistenceRequest,
) -> tuple[StoredSourceDocument, ...]:
    linkage = db.execute(
        text(
            """SELECT p.id,v.id FROM patients p JOIN treatment_plan_versions v ON v.patient_id=p.id
            WHERE p.canonical_client_id=:client_id AND p.source_system='manual_upload'
            AND v.source_record_id=:plan_id AND v.source_system='manual_upload'
            ORDER BY v.version_ordinal DESC,v.id DESC LIMIT 1"""
        ),
        {"client_id": request.patient_id, "plan_id": request.plan_id},
    ).one()
    stored: list[StoredSourceDocument] = []
    for source in request.sources:
        existing = _existing_source(db, int(linkage[0]), source.sha256)
        if existing is not None:
            source.encrypted_path.unlink(missing_ok=True)
            if existing.document_id not in {item.document_id for item in stored}:
                stored.append(existing)
            continue
        created_at = utc_now().astimezone(timezone.utc).isoformat()
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
                "document_id": source.document_id,
                "source_kind": SOURCE_KIND,
                "source_format": source.source_format,
                "content_type": source.content_type,
                "size_bytes": source.size_bytes,
                "sha256": source.sha256,
                "relative_path": source.encrypted_relative_path,
                "created_by_user_id": request.created_by_user_id,
                "created_at": created_at,
            },
        )
        stored.append(
            StoredSourceDocument(
                document_id=source.document_id,
                patient_id=request.patient_id,
                source_kind=SOURCE_KIND,
                source_format=source.source_format,
                content_type=source.content_type,
                size_bytes=source.size_bytes,
                sha256=source.sha256,
                encrypted_relative_path=source.encrypted_relative_path,
                created_at=created_at,
            )
        )
    db.flush()
    return tuple(stored)


def cleanup_staged_manual_sources(sources: tuple[StagedManualSource, ...]) -> None:
    for source in sources:
        source.encrypted_path.unlink(missing_ok=True)


def _existing_source(db: Session, patient_row_id: int, sha256: str) -> StoredSourceDocument | None:
    row = db.execute(
        text(
            """SELECT d.document_id,p.canonical_client_id,d.source_kind,d.source_format,d.content_type,d.size_bytes,
                d.sha256,d.encrypted_relative_path,d.created_at
            FROM source_documents d JOIN patients p ON p.id=d.patient_id
            WHERE d.patient_id=:patient_id AND d.sha256=:sha256 AND d.source_kind=:source_kind"""
        ),
        {"patient_id": patient_row_id, "sha256": sha256, "source_kind": SOURCE_KIND},
    ).one_or_none()
    if row is None:
        return None
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
