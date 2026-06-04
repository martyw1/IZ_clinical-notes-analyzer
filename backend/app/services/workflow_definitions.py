from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import WorkflowDefinition, WorkflowDefinitionVersion, WorkflowDefinitionVersionStatus

DEFAULT_TREATMENT_PLAN_WORKFLOW_KEY = 'treatment_plan_timeliness'


DEFAULT_TREATMENT_PLAN_DEFINITION = {
    'steps': [
        {'key': 'active_client_scope', 'label': 'Active client scope'},
        {'key': 'initial_treatment_plan', 'label': 'Initial Treatment Plan'},
        {'key': 'master_treatment_plan', 'label': 'Master Treatment Plan'},
        {'key': 'ongoing_review', 'label': 'Ongoing Treatment Plan Review'},
        {'key': 'loc_change_review', 'label': 'Level-of-care change review'},
        {'key': 'manual_override', 'label': 'Manual override review'},
    ],
    'owner_roles': ['admin', 'manager'],
    'source': 'docs/prd-treatment-plan-timeliness-mvp-2026-06-01.md',
}


DEFAULT_TREATMENT_PLAN_TRANSITIONS = [
    {'from': 'draft', 'to': 'active', 'roles': ['admin']},
    {'from': 'active', 'to': 'archived', 'roles': ['admin']},
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
        definition_snapshot=stable_json(DEFAULT_TREATMENT_PLAN_DEFINITION),
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
