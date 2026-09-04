from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.v2.models import utc_now
from app.v2.services.manual_binder import ManualBinderSource
from app.v2.services.manual_source_types import SOURCE_KIND, StoredSourceDocument
from app.v2.services.secure_storage import encrypt_bytes, ensure_private_directory
from app.v2.services.source_membership_store import SourceAttachment, attach_manual_source
from app.v2.services.treatment_plan_types import PlanVersionIdentity
from app.v2.services.audit_store import record_audit_event
from app.v2.models import User


@dataclass(frozen=True, slots=True)
class StagedManualSource:
    document_id: str
    source_format: str
    content_type: str
    size_bytes: int
    sha256: str
    encrypted_relative_path: str
    encrypted_path: Path
    owns_encrypted_path: bool = False


@dataclass(frozen=True, slots=True)
class ManualSourcePersistenceRequest:
    identity: PlanVersionIdentity
    actor: User
    sources: tuple[StagedManualSource, ...]


def stage_manual_sources(sources: tuple[ManualBinderSource, ...]) -> tuple[StagedManualSource, ...]:
    staged: list[StagedManualSource] = []
    completed = False
    try:
        for source in sources:
            document_id = uuid4().hex
            relative_path = Path("manual-uploads") / f"{document_id}.izcna1"
            encrypted_path = settings.local_app_data_dir / relative_path
            temporary_path = encrypted_path.with_name(f".{document_id}.tmp")
            ensure_private_directory(encrypted_path.parent)
            with temporary_path.open("xb") as temporary_file:
                staged.append(StagedManualSource(
                    document_id=document_id,
                    source_format=source.source_format,
                    content_type=source.content_type,
                    size_bytes=len(source.raw_bytes),
                    sha256=source.sha256,
                    encrypted_relative_path=relative_path.as_posix(),
                    encrypted_path=encrypted_path,
                ))
                temporary_file.write(encrypt_bytes(source.raw_bytes))
            with encrypted_path.open("xb"):
                staged[-1] = replace(staged[-1], owns_encrypted_path=True)
            temporary_path.replace(encrypted_path)
        completed = True
    finally:
        if not completed:
            cleanup_staged_manual_sources(tuple(staged))
    return tuple(staged)


def persist_staged_manual_sources(
    db: Session,
    request: ManualSourcePersistenceRequest,
) -> tuple[StoredSourceDocument, ...]:
    stored: list[StoredSourceDocument] = []
    for source in request.sources:
        existing = _existing_source(db, request.identity.patient_record_id, source.sha256)
        if existing is not None:
            source.encrypted_path.unlink(missing_ok=True)
            _attach_source(db, request, existing.document_id)
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
                "patient_id": request.identity.patient_record_id,
                "plan_version_id": request.identity.plan_version_id,
                "document_id": source.document_id,
                "source_kind": SOURCE_KIND,
                "source_format": source.source_format,
                "content_type": source.content_type,
                "size_bytes": source.size_bytes,
                "sha256": source.sha256,
                "relative_path": source.encrypted_relative_path,
                "created_by_user_id": request.actor.id,
                "created_at": created_at,
            },
        )
        _attach_source(db, request, source.document_id)
        stored.append(
            StoredSourceDocument(
                document_id=source.document_id,
                patient_id=request.identity.patient_id,
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
        source.encrypted_path.with_name(f".{source.document_id}.tmp").unlink(missing_ok=True)
        if source.owns_encrypted_path:
            source.encrypted_path.unlink(missing_ok=True)


def _attach_source(db: Session, request: ManualSourcePersistenceRequest, document_id: str) -> None:
    outcome = attach_manual_source(db, SourceAttachment(document_id, request.identity, request.actor.id))
    if outcome != "unchanged":
        record_audit_event(db, action=f"manual_upload.source_membership.{outcome}", actor=request.actor,
            target_entity_type="treatment_plan_version", target_entity_id=str(request.identity.plan_version_id),
            details={"patient_row_id": request.identity.patient_record_id, "source_file_id": document_id}, commit=False)


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
