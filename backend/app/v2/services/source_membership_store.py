from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.v2.models import utc_now
from app.v2.services.treatment_plan_types import PlanVersionIdentity


@dataclass(frozen=True, slots=True)
class SourceAttachment:
    document_id: str
    identity: PlanVersionIdentity
    actor_id: int


def attach_manual_source(db: Session, attachment: SourceAttachment) -> Literal["attached", "unchanged", "reattached"]:
    identity = attachment.identity
    source_id = db.execute(text(
        "SELECT d.id FROM source_documents d JOIN treatment_plan_versions v ON v.id=:version "
        "JOIN patients p ON p.id=d.patient_id WHERE d.document_id=:document AND d.patient_id=:patient "
        "AND v.patient_id=d.patient_id AND p.canonical_client_id=:mrn AND p.source_system='manual_upload' "
        "AND d.source_kind='manual_treatment_plan_file' AND v.source_system=:source "
        "AND v.source_system='manual_upload' AND v.source_record_id=:plan"
    ), {"version": identity.plan_version_id, "document": attachment.document_id, "patient": identity.patient_record_id,
        "mrn": identity.patient_id, "source": identity.source_mode, "plan": identity.treatment_plan_id}).scalar_one_or_none()
    if source_id is None:
        raise HTTPException(status_code=404, detail="Source file does not belong to the selected manual record")
    pair = {"document": int(source_id), "version": identity.plan_version_id}
    existing = db.execute(text(
        "SELECT detached_at FROM source_document_plan_memberships WHERE source_document_id=:document AND plan_version_id=:version"
    ), pair).first()
    if existing is None:
        db.execute(text(
            "INSERT INTO source_document_plan_memberships(source_document_id,plan_version_id,attached_at,attached_by_user_id) "
            "VALUES(:document,:version,:timestamp,:actor)"
        ), pair | {"timestamp": utc_now().isoformat(), "actor": attachment.actor_id})
        return "attached"
    if existing[0] is not None:
        db.execute(text(
            "UPDATE source_document_plan_memberships SET detached_at=NULL,detached_by_user_id=NULL "
            "WHERE source_document_id=:document AND plan_version_id=:version"
        ), pair)
        return "reattached"
    return "unchanged"
