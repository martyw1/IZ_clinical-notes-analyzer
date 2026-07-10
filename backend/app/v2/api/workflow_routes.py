from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.v2.api.deps import AdminUser, DbSession
from app.v2.api.models import WorkflowProfileCreate, WorkflowProfileOut, WorkflowProfileVersionOut
from app.v2.models import WorkflowProfile, WorkflowProfileVersion
from app.v2.services.audit_store import record_audit_event

router = APIRouter()


@router.get("/api/workflow-definitions", response_model=tuple[WorkflowProfileOut, ...])
def list_workflow_profiles(_: AdminUser, db: DbSession) -> tuple[WorkflowProfileOut, ...]:
    profiles = db.execute(select(WorkflowProfile).where(WorkflowProfile.is_active.is_(True)).order_by(WorkflowProfile.display_name)).scalars().all()
    return tuple(_profile_out(profile, db) for profile in profiles)


@router.post("/api/workflow-definitions", response_model=WorkflowProfileOut, status_code=status.HTTP_201_CREATED)
def create_workflow_profile(payload: WorkflowProfileCreate, actor: AdminUser, db: DbSession) -> WorkflowProfileOut:
    existing = db.execute(select(WorkflowProfile).where(WorkflowProfile.workflow_key == payload.workflow_key)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Workflow key already exists")
    now = datetime.now(timezone.utc)
    profile = WorkflowProfile(workflow_key=payload.workflow_key, display_name=payload.display_name, description=payload.description, created_by_user_id=str(actor.id), updated_by_user_id=str(actor.id), created_at=now, updated_at=now)
    db.add(profile)
    db.flush()
    version = WorkflowProfileVersion(workflow_profile_id=profile.id, version=1, created_by_user_id=str(actor.id))
    db.add(version)
    db.commit()
    record_audit_event(db, action="workflow_profile.created", actor=actor, target_entity_type="workflow_profile", target_entity_id=profile.workflow_key, details={"version": 1})
    return _profile_out(profile, db)


@router.post("/api/workflow-definitions/{profile_id}/versions/{version_id}/publish", response_model=WorkflowProfileOut)
def publish_workflow_profile(profile_id: int, version_id: int, actor: AdminUser, db: DbSession) -> WorkflowProfileOut:
    profile = db.get(WorkflowProfile, profile_id)
    version = db.get(WorkflowProfileVersion, version_id)
    if profile is None or version is None or version.workflow_profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Workflow profile version not found")
    versions = db.execute(select(WorkflowProfileVersion).where(WorkflowProfileVersion.workflow_profile_id == profile.id)).scalars().all()
    for item in versions:
        if item.status == "published":
            item.status = "archived"
    version.status = "published"
    version.published_at = datetime.now(timezone.utc)
    profile.current_version_id = version.id
    profile.updated_by_user_id = str(actor.id)
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    record_audit_event(db, action="workflow_profile.published", actor=actor, target_entity_type="workflow_profile", target_entity_id=profile.workflow_key, details={"version": version.version})
    return _profile_out(profile, db)


def _profile_out(profile: WorkflowProfile, db: DbSession) -> WorkflowProfileOut:
    rows = db.execute(select(WorkflowProfileVersion).where(WorkflowProfileVersion.workflow_profile_id == profile.id).order_by(WorkflowProfileVersion.version.desc())).scalars().all()
    versions = tuple(WorkflowProfileVersionOut(id=row.id, version=row.version, status=row.status, version_notes=row.version_notes) for row in rows)
    current = next((row for row in versions if row.id == profile.current_version_id), None)
    return WorkflowProfileOut(id=profile.id, workflow_key=profile.workflow_key, display_name=profile.display_name, description=profile.description, is_active=profile.is_active, current_version=current, versions=versions)
