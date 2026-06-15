from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_roles
from app.db.session import get_db
from app.models.models import Role, User, WorkflowDefinition, WorkflowDefinitionVersion, WorkflowDefinitionVersionStatus
from app.schemas.schemas import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionOut,
    WorkflowDefinitionUpdate,
    WorkflowDefinitionVersionInput,
    WorkflowDefinitionVersionOut,
)
from app.services.audit import log_event
from app.services.workflow_definitions import stable_json, validate_workflow_version_payload

router = APIRouter()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _workflow_definition_stmt():
    return select(WorkflowDefinition).options(selectinload(WorkflowDefinition.versions))


def _find_workflow_definition(definition_id: int, db: Session) -> WorkflowDefinition:
    definition = db.execute(_workflow_definition_stmt().where(WorkflowDefinition.id == definition_id)).scalar_one_or_none()
    if definition is None:
        raise HTTPException(status_code=404, detail='Workflow definition not found')
    return definition


def _find_workflow_version(definition: WorkflowDefinition, version_id: int) -> WorkflowDefinitionVersion:
    for version in definition.versions:
        if version.id == version_id:
            return version
    raise HTTPException(status_code=404, detail='Workflow definition version not found')


def _load_json(raw_value: str, fallback: object) -> object:
    try:
        return json.loads(raw_value or '')
    except (TypeError, json.JSONDecodeError):
        return fallback


def _workflow_version_payload(version: WorkflowDefinitionVersion) -> dict[str, object]:
    return {
        'id': version.id,
        'workflow_definition_id': version.workflow_definition_id,
        'version': version.version,
        'status': version.status,
        'definition_snapshot': _load_json(version.definition_snapshot, {}),
        'transition_rules': _load_json(version.transition_rules, []),
        'version_notes': version.version_notes,
        'created_by_id': version.created_by_id,
        'published_by_id': version.published_by_id,
        'archived_by_id': version.archived_by_id,
        'created_at': version.created_at,
        'published_at': version.published_at,
        'archived_at': version.archived_at,
    }


def _workflow_definition_payload(definition: WorkflowDefinition) -> dict[str, object]:
    versions = sorted(definition.versions, key=lambda item: item.version, reverse=True)
    current_version = next((version for version in versions if version.id == definition.current_version_id), None)
    return {
        'id': definition.id,
        'workflow_key': definition.workflow_key,
        'display_name': definition.display_name,
        'description': definition.description,
        'category': definition.category,
        'is_active': definition.is_active,
        'current_version_id': definition.current_version_id,
        'created_by_id': definition.created_by_id,
        'updated_by_id': definition.updated_by_id,
        'created_at': definition.created_at,
        'updated_at': definition.updated_at,
        'current_version': _workflow_version_payload(current_version) if current_version else None,
        'versions': [_workflow_version_payload(version) for version in versions],
    }


def _workflow_definition_snapshot(definition: WorkflowDefinition) -> dict[str, object]:
    return {
        'id': definition.id,
        'workflow_key': definition.workflow_key,
        'display_name': definition.display_name,
        'category': definition.category,
        'is_active': definition.is_active,
        'current_version_id': definition.current_version_id,
        'version_count': len(definition.versions),
    }


def _next_workflow_version_number(definition: WorkflowDefinition) -> int:
    if not definition.versions:
        return 1
    return max(version.version for version in definition.versions) + 1


def _create_workflow_version(definition: WorkflowDefinition, payload: WorkflowDefinitionVersionInput, user: User, db: Session) -> WorkflowDefinitionVersion:
    validation_errors = validate_workflow_version_payload(payload.definition_snapshot, payload.transition_rules)
    if validation_errors:
        raise HTTPException(status_code=400, detail='; '.join(validation_errors))
    version = WorkflowDefinitionVersion(
        workflow_definition_id=definition.id,
        version=_next_workflow_version_number(definition),
        status=WorkflowDefinitionVersionStatus.draft,
        definition_snapshot=stable_json(payload.definition_snapshot),
        transition_rules=stable_json(payload.transition_rules),
        version_notes=payload.version_notes.strip(),
        created_by_id=user.id,
    )
    db.add(version)
    db.flush()
    definition.updated_by_id = user.id
    definition.updated_at = _utc_now()
    definition.versions.append(version)
    return version


@router.get('/workflow-definitions', response_model=list[WorkflowDefinitionOut])
def list_workflow_definitions(
    request: Request,
    include_archived: bool = Query(default=False),
    user: User = Depends(require_roles(Role.admin, Role.manager)),
    db: Session = Depends(get_db),
):
    stmt = _workflow_definition_stmt().order_by(WorkflowDefinition.display_name, WorkflowDefinition.id)
    if not include_archived:
        stmt = stmt.where(WorkflowDefinition.is_active.is_(True))
    definitions = list(db.execute(stmt).scalars().unique().all())
    log_event(
        db,
        request,
        'workflow_definition.list.read',
        actor=user,
        event_category='data_access',
        target_entity='workflow_definitions',
        target_entity_type='workflow_definition',
        details={'count': len(definitions), 'include_archived': include_archived},
        message='Workflow definition list viewed.',
    )
    return [_workflow_definition_payload(definition) for definition in definitions]


@router.post('/workflow-definitions', response_model=WorkflowDefinitionOut)
def create_workflow_definition(
    payload: WorkflowDefinitionCreate,
    request: Request,
    user: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    workflow_key = payload.workflow_key.strip().lower()
    existing = db.execute(select(WorkflowDefinition).where(WorkflowDefinition.workflow_key == workflow_key)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=400, detail='Workflow key already exists')

    definition = WorkflowDefinition(
        workflow_key=workflow_key,
        display_name=payload.display_name.strip(),
        description=payload.description.strip(),
        category=payload.category.strip() or 'clinical_review',
        is_active=payload.is_active,
        created_by_id=user.id,
        updated_by_id=user.id,
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )
    db.add(definition)
    db.flush()
    initial_version = payload.initial_version or WorkflowDefinitionVersionInput(
        definition_snapshot={
            'workflow_key': workflow_key,
            'display_name': definition.display_name,
            'category': definition.category,
        },
        transition_rules=[],
        version_notes='Initial draft created with the workflow definition.',
    )
    _create_workflow_version(definition, initial_version, user, db)
    db.commit()
    definition = _find_workflow_definition(definition.id, db)
    after = _workflow_definition_snapshot(definition)
    log_event(
        db,
        request,
        'workflow_definition.create',
        actor=user,
        event_category='workflow',
        target_entity=f'workflow_definition:{definition.id}',
        target_entity_type='workflow_definition',
        target_entity_id=str(definition.id),
        details={'workflow_key': definition.workflow_key, 'version_count': len(definition.versions)},
        after_state=after,
        message=f'Workflow definition {definition.workflow_key} created.',
    )
    return _workflow_definition_payload(definition)


@router.get('/workflow-definitions/{definition_id}', response_model=WorkflowDefinitionOut)
def get_workflow_definition(
    definition_id: int,
    request: Request,
    user: User = Depends(require_roles(Role.admin, Role.manager)),
    db: Session = Depends(get_db),
):
    definition = _find_workflow_definition(definition_id, db)
    log_event(
        db,
        request,
        'workflow_definition.read',
        actor=user,
        event_category='data_access',
        target_entity=f'workflow_definition:{definition.id}',
        target_entity_type='workflow_definition',
        target_entity_id=str(definition.id),
        details={'workflow_key': definition.workflow_key},
        message=f'Workflow definition {definition.workflow_key} viewed.',
    )
    return _workflow_definition_payload(definition)


@router.patch('/workflow-definitions/{definition_id}', response_model=WorkflowDefinitionOut)
def update_workflow_definition(
    definition_id: int,
    payload: WorkflowDefinitionUpdate,
    request: Request,
    user: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    definition = _find_workflow_definition(definition_id, db)
    before = _workflow_definition_snapshot(definition)
    if payload.display_name is not None:
        definition.display_name = payload.display_name.strip()
    if payload.description is not None:
        definition.description = payload.description.strip()
    if payload.category is not None:
        definition.category = payload.category.strip() or definition.category
    if payload.is_active is not None:
        definition.is_active = payload.is_active
    definition.updated_by_id = user.id
    definition.updated_at = _utc_now()
    db.commit()
    definition = _find_workflow_definition(definition.id, db)
    after = _workflow_definition_snapshot(definition)
    log_event(
        db,
        request,
        'workflow_definition.update',
        actor=user,
        event_category='workflow',
        target_entity=f'workflow_definition:{definition.id}',
        target_entity_type='workflow_definition',
        target_entity_id=str(definition.id),
        details={'workflow_key': definition.workflow_key},
        before_state=before,
        after_state=after,
        message=f'Workflow definition {definition.workflow_key} updated.',
    )
    return _workflow_definition_payload(definition)


@router.post('/workflow-definitions/{definition_id}/versions', response_model=WorkflowDefinitionVersionOut)
def create_workflow_definition_version(
    definition_id: int,
    payload: WorkflowDefinitionVersionInput,
    request: Request,
    user: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    definition = _find_workflow_definition(definition_id, db)
    version = _create_workflow_version(definition, payload, user, db)
    db.commit()
    definition = _find_workflow_definition(definition.id, db)
    version = _find_workflow_version(definition, version.id)
    log_event(
        db,
        request,
        'workflow_definition.version.create',
        actor=user,
        event_category='workflow',
        target_entity=f'workflow_definition_version:{version.id}',
        target_entity_type='workflow_definition_version',
        target_entity_id=str(version.id),
        details={'workflow_key': definition.workflow_key, 'version': version.version, 'status': version.status.value},
        after_state=_workflow_version_payload(version),
        message=f'Workflow definition {definition.workflow_key} version {version.version} created.',
    )
    return _workflow_version_payload(version)


@router.patch('/workflow-definitions/{definition_id}/versions/{version_id}', response_model=WorkflowDefinitionVersionOut)
def update_workflow_definition_version(
    definition_id: int,
    version_id: int,
    payload: WorkflowDefinitionVersionInput,
    request: Request,
    user: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    definition = _find_workflow_definition(definition_id, db)
    version = _find_workflow_version(definition, version_id)
    if version.status != WorkflowDefinitionVersionStatus.draft:
        raise HTTPException(status_code=400, detail='Only draft workflow versions can be edited')
    validation_errors = validate_workflow_version_payload(payload.definition_snapshot, payload.transition_rules)
    if validation_errors:
        raise HTTPException(status_code=400, detail='; '.join(validation_errors))
    before = _workflow_version_payload(version)
    version.definition_snapshot = stable_json(payload.definition_snapshot)
    version.transition_rules = stable_json(payload.transition_rules)
    version.version_notes = payload.version_notes.strip()
    definition.updated_by_id = user.id
    definition.updated_at = _utc_now()
    db.commit()
    definition = _find_workflow_definition(definition.id, db)
    version = _find_workflow_version(definition, version.id)
    log_event(
        db,
        request,
        'workflow_definition.version.update',
        actor=user,
        event_category='workflow',
        target_entity=f'workflow_definition_version:{version.id}',
        target_entity_type='workflow_definition_version',
        target_entity_id=str(version.id),
        details={'workflow_key': definition.workflow_key, 'version': version.version},
        before_state=before,
        after_state=_workflow_version_payload(version),
        message=f'Workflow definition {definition.workflow_key} version {version.version} updated.',
    )
    return _workflow_version_payload(version)


@router.post('/workflow-definitions/{definition_id}/versions/{version_id}/publish', response_model=WorkflowDefinitionOut)
def publish_workflow_definition_version(
    definition_id: int,
    version_id: int,
    request: Request,
    user: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    definition = _find_workflow_definition(definition_id, db)
    version = _find_workflow_version(definition, version_id)
    before = _workflow_definition_snapshot(definition)
    now = _utc_now()
    for existing_version in definition.versions:
        if existing_version.id == version.id:
            continue
        if existing_version.status == WorkflowDefinitionVersionStatus.published:
            existing_version.status = WorkflowDefinitionVersionStatus.archived
            existing_version.archived_by_id = user.id
            existing_version.archived_at = now
    version.status = WorkflowDefinitionVersionStatus.published
    version.published_by_id = user.id
    version.published_at = now
    version.archived_by_id = None
    version.archived_at = None
    definition.current_version_id = version.id
    definition.is_active = True
    definition.updated_by_id = user.id
    definition.updated_at = now
    db.commit()
    definition = _find_workflow_definition(definition.id, db)
    after = _workflow_definition_snapshot(definition)
    log_event(
        db,
        request,
        'workflow_definition.version.publish',
        actor=user,
        event_category='workflow',
        target_entity=f'workflow_definition:{definition.id}',
        target_entity_type='workflow_definition',
        target_entity_id=str(definition.id),
        details={'workflow_key': definition.workflow_key, 'published_version_id': version_id},
        before_state=before,
        after_state=after,
        message=f'Workflow definition {definition.workflow_key} version published.',
    )
    return _workflow_definition_payload(definition)


@router.post('/workflow-definitions/{definition_id}/archive', response_model=WorkflowDefinitionOut)
def archive_workflow_definition(
    definition_id: int,
    request: Request,
    user: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    definition = _find_workflow_definition(definition_id, db)
    before = _workflow_definition_snapshot(definition)
    now = _utc_now()
    definition.is_active = False
    definition.updated_by_id = user.id
    definition.updated_at = now
    for version in definition.versions:
        if version.status == WorkflowDefinitionVersionStatus.published:
            version.status = WorkflowDefinitionVersionStatus.archived
            version.archived_by_id = user.id
            version.archived_at = now
    db.commit()
    definition = _find_workflow_definition(definition.id, db)
    after = _workflow_definition_snapshot(definition)
    log_event(
        db,
        request,
        'workflow_definition.archive',
        actor=user,
        event_category='workflow',
        target_entity=f'workflow_definition:{definition.id}',
        target_entity_type='workflow_definition',
        target_entity_id=str(definition.id),
        details={'workflow_key': definition.workflow_key},
        before_state=before,
        after_state=after,
        message=f'Workflow definition {definition.workflow_key} archived.',
    )
    return _workflow_definition_payload(definition)


@router.delete('/workflow-definitions/{definition_id}')
def delete_unused_workflow_definition(
    definition_id: int,
    request: Request,
    user: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    definition = _find_workflow_definition(definition_id, db)
    if definition.current_version_id is not None or any(version.status != WorkflowDefinitionVersionStatus.draft for version in definition.versions):
        raise HTTPException(status_code=400, detail='Only draft-only workflow profiles that have never been published can be deleted')
    before = _workflow_definition_snapshot(definition)
    workflow_key = definition.workflow_key
    db.delete(definition)
    db.commit()
    log_event(
        db,
        request,
        'workflow_definition.delete',
        actor=user,
        event_category='workflow',
        target_entity=f'workflow_definition:{definition_id}',
        target_entity_type='workflow_definition',
        target_entity_id=str(definition_id),
        details={'workflow_key': workflow_key},
        before_state=before,
        message=f'Unused workflow definition {workflow_key} deleted.',
    )
    return {'status': 'deleted', 'workflow_key': workflow_key}
