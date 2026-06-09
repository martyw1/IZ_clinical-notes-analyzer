from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import REPO_ROOT

CHECKLIST_PATH = REPO_ROOT / 'config' / 'checklists' / 'treatment-plan-v1.json'
REQUIRED_ACRONYMS = {'API', 'EMR', 'PHI', 'PII', 'OCR', 'LLM', 'TP', 'SUD', 'LOC', 'ASAM', 'SMART'}
REQUIRED_STEP_COUNT = 20


def _load_json(path: Path) -> dict[str, Any]:
    with path.open('r', encoding='utf-8') as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f'Checklist file {path} must contain a JSON object.')
    return payload


def validate_treatment_plan_checklist(checklist: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if checklist.get('checklist_id') != 'treatment-plan-v1':
        errors.append('checklist_id must be treatment-plan-v1')
    if not str(checklist.get('version') or '').strip():
        errors.append('version is required')

    acronyms = checklist.get('acronyms')
    if not isinstance(acronyms, list):
        errors.append('acronyms must be a list')
    else:
        terms = {str(item.get('term') or '').strip() for item in acronyms if isinstance(item, dict)}
        missing = sorted(REQUIRED_ACRONYMS - terms)
        if missing:
            errors.append(f'missing acronym definitions: {", ".join(missing)}')

    statuses = checklist.get('review_statuses')
    if not isinstance(statuses, list) or not statuses:
        errors.append('review_statuses must be a non-empty list')

    steps = checklist.get('steps')
    if not isinstance(steps, list):
        errors.append('steps must be a list')
        return errors
    if len(steps) != REQUIRED_STEP_COUNT:
        errors.append(f'steps must contain exactly {REQUIRED_STEP_COUNT} entries')

    seen_keys: set[str] = set()
    for expected_step, item in enumerate(steps, start=1):
        if not isinstance(item, dict):
            errors.append(f'steps[{expected_step}] must be an object')
            continue
        if item.get('step') != expected_step:
            errors.append(f'steps[{expected_step}].step must be {expected_step}')
        key = str(item.get('key') or '').strip()
        if not key:
            errors.append(f'steps[{expected_step}].key is required')
        elif key in seen_keys:
            errors.append(f'duplicate checklist step key: {key}')
        seen_keys.add(key)
        if not str(item.get('title') or '').strip():
            errors.append(f'steps[{expected_step}].title is required')
        source_modes = item.get('source_modes')
        if not isinstance(source_modes, list) or not source_modes:
            errors.append(f'steps[{expected_step}].source_modes must be a non-empty list')
        if not str(item.get('objective') or '').strip():
            errors.append(f'steps[{expected_step}].objective is required')
    return errors


@lru_cache(maxsize=1)
def load_treatment_plan_checklist(path: str | Path | None = None) -> dict[str, Any]:
    checklist_path = Path(path) if path else CHECKLIST_PATH
    payload = _load_json(checklist_path)
    errors = validate_treatment_plan_checklist(payload)
    if errors:
        raise ValueError('; '.join(errors))
    return payload


def treatment_plan_workflow_snapshot() -> dict[str, Any]:
    checklist = load_treatment_plan_checklist()
    return {
        'checklist_id': checklist['checklist_id'],
        'version': checklist['version'],
        'display_name': checklist['display_name'],
        'source_of_truth': checklist['source_of_truth'],
        'acronyms': checklist['acronyms'],
        'review_statuses': checklist['review_statuses'],
        'loc_change_blocker': checklist['loc_change_blocker'],
        'steps': [
            {
                'key': step['key'],
                'label': step['title'],
                'step': step['step'],
                'source_modes': step['source_modes'],
                'automation_level': step['automation_level'],
                'severity_default': step['severity_default'],
            }
            for step in checklist['steps']
        ],
        'owner_roles': checklist.get('review_owner_roles', ['admin', 'manager']),
    }
