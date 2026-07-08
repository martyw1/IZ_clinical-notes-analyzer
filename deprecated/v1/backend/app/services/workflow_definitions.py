from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import WorkflowDefinition, WorkflowDefinitionVersion, WorkflowDefinitionVersionStatus
from app.services.treatment_plan_checklist import treatment_plan_workflow_snapshot

DEFAULT_TREATMENT_PLAN_WORKFLOW_KEY = 'treatment_plan_timeliness'


DEFAULT_TREATMENT_PLAN_TRANSITIONS = [
    {'from': 'not_reviewed', 'to': 'ready_for_review', 'roles': ['admin', 'manager']},
    {'from': 'ready_for_review', 'to': 'in_review', 'roles': ['admin', 'manager']},
    {'from': 'in_review', 'to': 'current_compliant', 'roles': ['admin', 'manager']},
    {'from': 'in_review', 'to': 'due_soon', 'roles': ['admin', 'manager']},
    {'from': 'in_review', 'to': 'urgent', 'roles': ['admin', 'manager']},
    {'from': 'in_review', 'to': 'overdue', 'roles': ['admin', 'manager']},
    {'from': 'in_review', 'to': 'needs_review', 'roles': ['admin', 'manager']},
    {'from': 'in_review', 'to': 'missing_data', 'roles': ['admin', 'manager']},
    {'from': 'in_review', 'to': 'conflicting_evidence', 'roles': ['admin', 'manager']},
    {'from': 'in_review', 'to': 'unable_to_evaluate', 'roles': ['admin', 'manager']},
    {'from': 'in_review', 'to': 'returned_for_correction', 'roles': ['admin', 'manager'], 'reason_required': True},
    {'from': 'current_compliant', 'to': 'approved_finalized', 'roles': ['admin', 'manager']},
    {'from': 'due_soon', 'to': 'approved_finalized', 'roles': ['admin', 'manager']},
    {'from': 'urgent', 'to': 'approved_finalized', 'roles': ['admin', 'manager']},
    {'from': 'overdue', 'to': 'returned_for_correction', 'roles': ['admin', 'manager'], 'reason_required': True},
    {'from': 'needs_review', 'to': 'returned_for_correction', 'roles': ['admin', 'manager'], 'reason_required': True},
    {'from': 'missing_data', 'to': 'returned_for_correction', 'roles': ['admin', 'manager'], 'reason_required': True},
    {'from': 'conflicting_evidence', 'to': 'returned_for_correction', 'roles': ['admin', 'manager'], 'reason_required': True},
    {'from': 'unable_to_evaluate', 'to': 'returned_for_correction', 'roles': ['admin', 'manager'], 'reason_required': True},
    {'from': 'returned_for_correction', 'to': 'ready_for_review', 'roles': ['admin', 'manager']},
    {'from': 'approved_finalized', 'to': 'ready_for_review', 'roles': ['admin'], 'reason_required': True},
    {'from': 'finalized', 'to': 'ready_for_review', 'roles': ['admin'], 'reason_required': True},
]


def stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def validate_workflow_version_payload(definition_snapshot: Any, transition_rules: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(definition_snapshot, dict):
        errors.append('definition_snapshot must be a JSON object')
        return errors
    steps = definition_snapshot.get('steps', [])
    if steps is not None and not isinstance(steps, list):
        errors.append('definition_snapshot.steps must be a list when provided')
    elif isinstance(steps, list):
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                errors.append(f'definition_snapshot.steps[{index}] must be an object')
                continue
            if not str(step.get('key') or '').strip():
                errors.append(f'definition_snapshot.steps[{index}].key is required')
            if not str(step.get('label') or '').strip():
                errors.append(f'definition_snapshot.steps[{index}].label is required')

    if not isinstance(transition_rules, list):
        errors.append('transition_rules must be a JSON array')
        return errors
    for index, transition in enumerate(transition_rules, start=1):
        if not isinstance(transition, dict):
            errors.append(f'transition_rules[{index}] must be an object')
            continue
        if not str(transition.get('from') or '').strip():
            errors.append(f'transition_rules[{index}].from is required')
        if not str(transition.get('to') or '').strip():
            errors.append(f'transition_rules[{index}].to is required')
        roles = transition.get('roles', [])
        if not isinstance(roles, list) or not all(isinstance(role, str) and role.strip() for role in roles):
            errors.append(f'transition_rules[{index}].roles must be a list of role names')
    return errors


def ensure_default_workflow_definitions(db: Session, *, actor_id: int) -> WorkflowDefinition | None:
    existing = db.execute(
        select(WorkflowDefinition).where(WorkflowDefinition.workflow_key == DEFAULT_TREATMENT_PLAN_WORKFLOW_KEY)
    ).scalar_one_or_none()
    if existing is not None:
        return None

    now = datetime.now(timezone.utc)
    definition = WorkflowDefinition(
        workflow_key=DEFAULT_TREATMENT_PLAN_WORKFLOW_KEY,
        display_name='Treatment Plan Timeliness Tracker',
        description='Default MVP workflow profile for treatment-plan due-date tracking.',
        category='treatment_plan',
        is_active=True,
        created_by_id=actor_id,
        updated_by_id=actor_id,
        created_at=now,
        updated_at=now,
    )
    db.add(definition)
    db.flush()
    version = WorkflowDefinitionVersion(
        workflow_definition_id=definition.id,
        version=1,
        status=WorkflowDefinitionVersionStatus.published,
        definition_snapshot=stable_json(treatment_plan_workflow_snapshot()),
        transition_rules=stable_json(DEFAULT_TREATMENT_PLAN_TRANSITIONS),
        version_notes='Seeded default Treatment Plan Timeliness Tracker workflow profile.',
        created_by_id=actor_id,
        published_by_id=actor_id,
        created_at=now,
        published_at=now,
    )
    db.add(version)
    db.flush()
    definition.current_version_id = version.id
    return definition


def current_treatment_plan_workflow_context(db: Session) -> dict[str, Any]:
    definition = db.execute(
        select(WorkflowDefinition).where(WorkflowDefinition.workflow_key == DEFAULT_TREATMENT_PLAN_WORKFLOW_KEY)
    ).scalar_one_or_none()
    if definition is None or definition.current_version_id is None:
        return {
            'workflow_key': DEFAULT_TREATMENT_PLAN_WORKFLOW_KEY,
            'workflow_definition_id': None,
            'workflow_version_id': None,
            'workflow_version': None,
            'checklist_version': None,
            'status': 'not_seeded',
        }
    version = db.execute(
        select(WorkflowDefinitionVersion).where(WorkflowDefinitionVersion.id == definition.current_version_id)
    ).scalar_one_or_none()
    snapshot: dict[str, Any] = {}
    if version is not None:
        try:
            loaded = json.loads(version.definition_snapshot or '{}')
            if isinstance(loaded, dict):
                snapshot = loaded
        except json.JSONDecodeError:
            snapshot = {}
    return {
        'workflow_key': definition.workflow_key,
        'workflow_definition_id': definition.id,
        'workflow_version_id': version.id if version is not None else None,
        'workflow_version': version.version if version is not None else None,
        'checklist_version': snapshot.get('checklist_version') or snapshot.get('version'),
        'status': version.status.value if version is not None else 'missing_current_version',
    }
