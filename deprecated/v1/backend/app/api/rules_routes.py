from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.models.models import User
from app.services.audit import log_event
from app.services.rules_engine import evaluate_rules, load_rules_config, result_as_dict, validate_rules_config

router = APIRouter(prefix='/api/rules', tags=['rules'])


class RuleEvaluationInput(BaseModel):
    """Normalized chart payload for deterministic rules evaluation.

    The Alleva connector should map vendor/API fields into this canonical shape
    before calling the rules engine. The payload may contain PHI, so this endpoint
    requires an authenticated local user and should not be called from unauthenticated
    tooling.
    """

    chart: dict[str, Any]
    evaluation_date: str | None = None


@router.get('/profile')
def rules_profile(request: Request, user: User = Depends(get_current_user)):
    """Return non-PHI metadata about the configured ruleset."""
    config = load_rules_config()
    errors = validate_rules_config(config)
    workflow = config.get('workflow') or {}
    payload = {
        'config_version': config.get('config_version'),
        'config_status': config.get('config_status'),
        'organization': config.get('organization'),
        'workflow': {
            'id': workflow.get('id'),
            'display_name': workflow.get('display_name'),
            'enabled': workflow.get('enabled'),
            'priority': workflow.get('priority'),
        },
        'levels_of_care': sorted((config.get('levels_of_care') or {}).keys()),
        'rules_count': len(config.get('rules') or []),
        'validation_status': 'ok' if not errors else 'fail',
        'validation_errors': errors,
    }
    log_event(
        request=request,
        actor=user,
        action='rules.profile.read',
        event_category='data_access',
        target_entity='rules_config',
        target_entity_type='rules_config',
        message=f'Rules profile read by {user.username}.',
        details={'workflow_id': payload['workflow']['id'], 'rules_count': payload['rules_count']},
    )
    return payload


@router.post('/evaluate')
def evaluate_rules_payload(payload: RuleEvaluationInput, request: Request, user: User = Depends(get_current_user)):
    """Evaluate one normalized chart payload against the configured rules.

    This endpoint does not use an LLM. It returns deterministic findings based on
    the YAML rules and supplied canonical chart fields.
    """
    try:
        result = evaluate_rules(payload.chart, evaluation_date=payload.evaluation_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response = result_as_dict(result)
    log_event(
        request=request,
        actor=user,
        action='rules.evaluate',
        event_category='data_processing',
        target_entity='rules_engine',
        target_entity_type='rules_engine',
        patient_id=str(payload.chart.get('patient_id') or payload.chart.get('chart_id') or ''),
        message=f'Rules evaluation completed by {user.username}.',
        details={
            'workflow_id': result.workflow_id,
            'overall_status': result.overall_status,
            'highest_severity': result.highest_severity,
            'findings_count': len(result.findings),
        },
    )
    return response
