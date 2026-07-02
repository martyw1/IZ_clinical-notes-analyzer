from __future__ import annotations

import json
import re
import hashlib
from datetime import datetime
from typing import Any

from app.services.patient_identity_minimization import (
    is_direct_patient_identifier_key,
    redacted_text,
    sanitize_patient_payload,
    text_has_direct_patient_identifier_label,
    text_looks_like_direct_patient_identifier,
)


SAFE_CONTENT_METADATA_KEYS = {
    'code',
    'diagnosisCode',
    'icd10Code',
    'icdCode',
    'status',
    'severity',
    'onsetDate',
    'targetDate',
    'startDate',
    'dueDate',
    'frequency',
    'modality',
    'duration',
    'serviceType',
}
SAFE_CONTENT_KINDS = {'problem', 'diagnosis', 'behavioral_definition', 'goal', 'objective', 'intervention'}
REQUIRED_COMPLETENESS_CONTENT_KINDS = ('problem', 'diagnosis', 'goal', 'objective', 'intervention')
SAFE_CONTENT_STATUSES = {
    'active',
    'addressed',
    'complete',
    'completed',
    'current',
    'deferred',
    'discontinued',
    'inactive',
    'in progress',
    'met',
    'new',
    'not met',
    'ongoing',
    'open',
    'partial',
    'partially met',
    'planned',
    'resolved',
    'reviewed',
}
SAFE_CONTENT_SEVERITIES = {'low', 'mild', 'moderate', 'medium', 'high', 'severe', 'critical'}
SAFE_CONTENT_MODALITY_TERMS = {
    'case management',
    'family',
    'group',
    'group therapy',
    'individual',
    'individual therapy',
    'medication management',
    'peer support',
    'psychoeducation',
    'therapy',
}
SAFE_CONTENT_SERVICE_TERMS = SAFE_CONTENT_MODALITY_TERMS | {
    'counseling',
    'iop',
    'iop-5',
    'outpatient',
    'php',
    'residential',
    'treatment planning',
}

SHA256_RE = re.compile(r'^[0-9a-f]{64}$', re.IGNORECASE)
CODE_RE = re.compile(r'^[A-Z0-9][A-Z0-9.\-]{1,39}$', re.IGNORECASE)
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
FREQUENCY_RE = re.compile(
    r'^(?:'
    r'\d+\s*(?:x|times?)\s*(?:per\s*)?(?:day|week|month|year)|'
    r'every\s+\d+\s*(?:days?|weeks?|months?)|'
    r'(?:daily|weekly|biweekly|monthly|quarterly|annually|yearly|as needed|prn|once|twice)'
    r')$',
    re.IGNORECASE,
)
DURATION_RE = re.compile(r'^(?:\d+\s*(?:minutes?|mins?|hours?|hrs?|days?|weeks?|months?)|ongoing|as needed|prn)$', re.IGNORECASE)
CONTENT_TITLE_CASE_PHRASE_RE = re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4}\b')
REDACTED_TOKEN = '[redacted]'
DEFAULT_CONTENT_ITEM_TEXT_CHARS = 2_000
DEFAULT_MAX_CONTENT_ITEMS = 250
SAFE_CONTENT_TITLE_CASE_WORDS = {
    'abstinence',
    'active',
    'addiction',
    'alcohol',
    'anxiety',
    'assessment',
    'behavioral',
    'case',
    'complete',
    'completed',
    'coping',
    'counseling',
    'daily',
    'definition',
    'definitions',
    'depression',
    'diagnosis',
    'discharge',
    'disorder',
    'family',
    'goal',
    'goals',
    'group',
    'individual',
    'intervention',
    'interventions',
    'objective',
    'objectives',
    'outpatient',
    'plan',
    'prevention',
    'program',
    'recovery',
    'relapse',
    'review',
    'skills',
    'substance',
    'therapy',
    'trauma',
    'treatment',
    'use',
    'weekly',
}


def _compact_scalar(value: Any, *, max_chars: int) -> str:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return ''
    text = ' '.join(redacted_text(str(value)).split())
    if not text or text == '[redacted]' or text_looks_like_direct_patient_identifier(text):
        return ''
    return text[:max_chars]


def safe_content_text(value: Any, *, max_chars: int = 280) -> str:
    return _compact_scalar(value, max_chars=max_chars)


def safe_content_display_text(value: Any, *, max_chars: int = DEFAULT_CONTENT_ITEM_TEXT_CHARS) -> str:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return ''
    raw_text = ' '.join(str(value).split())
    if not raw_text:
        return ''
    text = ' '.join(redacted_text(raw_text).split())
    if (
        not text
        or REDACTED_TOKEN in text.lower()
        or text_has_direct_patient_identifier_label(text)
        or _content_text_looks_like_direct_identifier(text)
    ):
        return ''
    return text[:max_chars]


def _content_text_looks_like_direct_identifier(value: str) -> bool:
    for match in CONTENT_TITLE_CASE_PHRASE_RE.finditer(value):
        words = [word.lower() for word in re.findall(r'[A-Z][a-z]+', match.group(0))]
        if words and all(word in SAFE_CONTENT_TITLE_CASE_WORDS for word in words):
            continue
        return True
    return False


def safe_content_status(value: Any) -> str:
    text = _compact_scalar(value, max_chars=40).strip().lower()
    return text if text in {'structured', 'counts_only', 'detail_empty', 'collection_only', 'manual'} else 'counts_only'


def safe_content_warning(value: Any, *, max_chars: int = 500) -> str:
    text = _compact_scalar(value, max_chars=max_chars)
    if not text:
        return ''
    return text


def safe_hash(value: Any) -> str:
    text = str(value or '').strip().lower()
    return text if SHA256_RE.fullmatch(text) else ''


def safe_content_metadata_value(key: str, value: Any, *, max_chars: int = 120) -> str:
    if key not in SAFE_CONTENT_METADATA_KEYS or is_direct_patient_identifier_key(key, (), aggressive=True):
        return ''
    text = _compact_scalar(value, max_chars=max_chars)
    if not text:
        return ''
    if key in {'code', 'diagnosisCode', 'icd10Code', 'icdCode'}:
        return text.upper() if CODE_RE.fullmatch(text) else ''
    if key in {'onsetDate', 'targetDate', 'startDate', 'dueDate'}:
        date_text = text[:10]
        if DATE_RE.fullmatch(date_text):
            try:
                datetime.fromisoformat(date_text)
            except ValueError:
                return ''
            return date_text
        return ''
    if key == 'status':
        normalized = text.lower()
        return text if normalized in SAFE_CONTENT_STATUSES else ''
    if key == 'severity':
        normalized = text.lower()
        return text if normalized in SAFE_CONTENT_SEVERITIES else ''
    if key == 'frequency':
        return text if FREQUENCY_RE.fullmatch(text) else ''
    if key == 'duration':
        return text if DURATION_RE.fullmatch(text) else ''
    if key == 'modality':
        return text if text.lower() in SAFE_CONTENT_MODALITY_TERMS else ''
    if key == 'serviceType':
        return text if text.lower() in SAFE_CONTENT_SERVICE_TERMS else ''
    return ''


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _content_value(payload: dict[str, Any], *keys: str, max_chars: int = DEFAULT_CONTENT_ITEM_TEXT_CHARS) -> str:
    for key in keys:
        if is_direct_patient_identifier_key(key, (), aggressive=True):
            continue
        text = safe_content_display_text(payload.get(key), max_chars=max_chars)
        if text:
            return text
    return ''


def _content_value_present(payload: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        if is_direct_patient_identifier_key(key, (), aggressive=True):
            continue
        value = payload.get(key)
        if value is not None and not isinstance(value, (dict, list, tuple, set)) and str(value).strip():
            return True
    return False


def _content_text_hash(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest() if value else ''


def _content_metadata(payload: dict[str, Any], keys: tuple[str, ...]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for key in keys:
        if is_direct_patient_identifier_key(key, (), aggressive=True):
            continue
        value = safe_content_metadata_value(key, payload.get(key), max_chars=120)
        if value:
            metadata[key] = value
    return metadata


def _append_content_item(
    items: list[dict[str, Any]],
    *,
    kind: str,
    payload: dict[str, Any],
    source_path: str,
    text_keys: tuple[str, ...],
    metadata_keys: tuple[str, ...] = (),
    max_items: int = DEFAULT_MAX_CONTENT_ITEMS,
) -> None:
    if len(items) >= max_items:
        return
    narrative_text = _content_value(payload, *text_keys)
    narrative_present = bool(narrative_text) or _content_value_present(payload, *text_keys)
    metadata = _content_metadata(payload, metadata_keys)
    kind_count = sum(1 for item in items if item.get('kind') == kind) + 1
    item: dict[str, Any] = {
        'kind': kind,
        'label': f'{kind.replace("_", " ").title()} {kind_count}',
        'source_path': source_path,
        'text_present': bool(narrative_present),
    }
    if narrative_text:
        item['text'] = narrative_text
        item['redacted_text_sha256'] = _content_text_hash(narrative_text)
    if metadata:
        item['metadata'] = metadata
    items.append(item)


def structured_content_items(raw: dict[str, Any], *, max_items: int = DEFAULT_MAX_CONTENT_ITEMS) -> list[dict[str, Any]]:
    sanitized = sanitize_patient_payload(raw, aggressive=True, omit_direct=True)
    if not isinstance(sanitized, dict):
        return []
    items: list[dict[str, Any]] = []
    problems = [item for item in _list_value(sanitized.get('problems')) if isinstance(item, dict)]
    top_level_diagnoses = [item for item in _list_value(sanitized.get('diagnoses')) if isinstance(item, dict)]
    top_level_goals = [item for item in _list_value(sanitized.get('goals')) if isinstance(item, dict)]
    top_level_objectives = [item for item in _list_value(sanitized.get('objectives')) if isinstance(item, dict)]
    top_level_interventions = [item for item in _list_value(sanitized.get('interventions')) if isinstance(item, dict)]
    top_level_behavioral_definitions = [
        item
        for item in (
            _list_value(sanitized.get('behavioralDefinitions'))
            or _list_value(sanitized.get('behavioral_definitions'))
            or _list_value(sanitized.get('behavioralDefinitionsForTreatmentPlan'))
        )
        if isinstance(item, dict)
    ]

    for problem_index, problem in enumerate(problems, start=1):
        problem_path = f'problems[{problem_index}]'
        _append_content_item(
            items,
            kind='problem',
            payload=problem,
            source_path=problem_path,
            text_keys=('description', 'problem', 'problemText', 'title', 'summary', 'displayText'),
            metadata_keys=('status', 'severity', 'onsetDate', 'targetDate'),
            max_items=max_items,
        )
        behavioral_definitions = [
            item
            for item in (
                _list_value(problem.get('behavioralDefinitions'))
                or _list_value(problem.get('behavioral_definitions'))
                or _list_value(problem.get('definitions'))
            )
            if isinstance(item, dict)
        ]
        for definition_index, definition in enumerate(behavioral_definitions, start=1):
            _append_content_item(
                items,
                kind='behavioral_definition',
                payload=definition,
                source_path=f'{problem_path}.behavioralDefinitions[{definition_index}]',
                text_keys=('description', 'definition', 'behavioralDefinition', 'title', 'summary', 'displayText'),
                metadata_keys=('status', 'severity'),
                max_items=max_items,
            )
        for diagnosis_index, diagnosis in enumerate([item for item in _list_value(problem.get('diagnoses')) if isinstance(item, dict)], start=1):
            _append_content_item(
                items,
                kind='diagnosis',
                payload=diagnosis,
                source_path=f'{problem_path}.diagnoses[{diagnosis_index}]',
                text_keys=('description', 'diagnosis', 'diagnosisDescription', 'displayText', 'summary'),
                metadata_keys=('code', 'diagnosisCode', 'icd10Code', 'icdCode', 'status'),
                max_items=max_items,
            )
        for goal_index, goal in enumerate([item for item in _list_value(problem.get('goals')) if isinstance(item, dict)], start=1):
            goal_path = f'{problem_path}.goals[{goal_index}]'
            _append_content_item(
                items,
                kind='goal',
                payload=goal,
                source_path=goal_path,
                text_keys=('description', 'goal', 'goalText', 'title', 'summary', 'displayText'),
                metadata_keys=('status', 'targetDate', 'startDate', 'dueDate'),
                max_items=max_items,
            )
            for objective_index, objective in enumerate([item for item in _list_value(goal.get('objectives')) if isinstance(item, dict)], start=1):
                objective_path = f'{goal_path}.objectives[{objective_index}]'
                _append_content_item(
                    items,
                    kind='objective',
                    payload=objective,
                    source_path=objective_path,
                    text_keys=('description', 'objective', 'objectiveText', 'title', 'summary', 'displayText'),
                    metadata_keys=('status', 'targetDate', 'startDate', 'dueDate'),
                    max_items=max_items,
                )
                for intervention_index, intervention in enumerate([item for item in _list_value(objective.get('interventions')) if isinstance(item, dict)], start=1):
                    _append_content_item(
                        items,
                        kind='intervention',
                        payload=intervention,
                        source_path=f'{objective_path}.interventions[{intervention_index}]',
                        text_keys=('description', 'intervention', 'interventionText', 'service', 'title', 'summary', 'displayText'),
                        metadata_keys=('frequency', 'modality', 'duration', 'status', 'serviceType'),
                        max_items=max_items,
                    )

    for definition_index, definition in enumerate(top_level_behavioral_definitions, start=1):
        _append_content_item(
            items,
            kind='behavioral_definition',
            payload=definition,
            source_path=f'behavioralDefinitions[{definition_index}]',
            text_keys=('description', 'definition', 'behavioralDefinition', 'title', 'summary', 'displayText'),
            metadata_keys=('status', 'severity'),
            max_items=max_items,
        )
    for diagnosis_index, diagnosis in enumerate(top_level_diagnoses, start=1):
        _append_content_item(
            items,
            kind='diagnosis',
            payload=diagnosis,
            source_path=f'diagnoses[{diagnosis_index}]',
            text_keys=('description', 'diagnosis', 'diagnosisDescription', 'displayText', 'summary'),
            metadata_keys=('code', 'diagnosisCode', 'icd10Code', 'icdCode', 'status'),
            max_items=max_items,
        )
    for goal_index, goal in enumerate(top_level_goals, start=1):
        _append_content_item(
            items,
            kind='goal',
            payload=goal,
            source_path=f'goals[{goal_index}]',
            text_keys=('description', 'goal', 'goalText', 'title', 'summary', 'displayText'),
            metadata_keys=('status', 'targetDate', 'startDate', 'dueDate'),
            max_items=max_items,
        )
    for objective_index, objective in enumerate(top_level_objectives, start=1):
        _append_content_item(
            items,
            kind='objective',
            payload=objective,
            source_path=f'objectives[{objective_index}]',
            text_keys=('description', 'objective', 'objectiveText', 'title', 'summary', 'displayText'),
            metadata_keys=('status', 'targetDate', 'startDate', 'dueDate'),
            max_items=max_items,
        )
    for intervention_index, intervention in enumerate(top_level_interventions, start=1):
        _append_content_item(
            items,
            kind='intervention',
            payload=intervention,
            source_path=f'interventions[{intervention_index}]',
            text_keys=('description', 'intervention', 'interventionText', 'service', 'title', 'summary', 'displayText'),
            metadata_keys=('frequency', 'modality', 'duration', 'status', 'serviceType'),
            max_items=max_items,
        )
    return items


def content_item_has_value(item: dict[str, Any]) -> bool:
    if safe_content_display_text(item.get('text')):
        return True
    raw_metadata = item.get('metadata')
    if not isinstance(raw_metadata, dict):
        return False
    for raw_key, metadata_value in raw_metadata.items():
        if safe_content_metadata_value(str(raw_key), metadata_value):
            return True
    return False


def content_value_assessment(
    items: Any,
    *,
    required_kinds: tuple[str, ...] = REQUIRED_COMPLETENESS_CONTENT_KINDS,
) -> dict[str, Any]:
    normalized = normalized_content_items(items)
    present = sorted(
        {
            item.get('kind', '')
            for item in normalized
            if item.get('kind') in required_kinds and content_item_has_value(item)
        }
    )
    missing = [kind for kind in required_kinds if kind not in present]
    return {
        'content_value_status': 'complete' if not missing else 'incomplete',
        'present_content_values': present,
        'missing_content_values': missing,
    }


def normalized_content_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value or '[]')
        except (TypeError, ValueError):
            parsed = []
    else:
        parsed = value
    if not isinstance(parsed, list):
        return []
    normalized: list[dict[str, Any]] = []
    kind_counts: dict[str, int] = {}
    for raw_item in parsed:
        if not isinstance(raw_item, dict):
            continue
        raw_kind = _compact_scalar(raw_item.get('kind'), max_chars=40).lower()
        kind = raw_kind if raw_kind in SAFE_CONTENT_KINDS else 'content'
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        source_path = _compact_scalar(raw_item.get('source_path'), max_chars=120)
        item: dict[str, Any] = {
            'kind': kind,
            'label': f'{kind.replace("_", " ").title()} {kind_counts[kind]}',
            'source_path': source_path,
            'text_present': bool(raw_item.get('text_present')),
        }
        text_hash = safe_hash(raw_item.get('redacted_text_sha256'))
        if text_hash:
            item['redacted_text_sha256'] = text_hash
        text = safe_content_display_text(raw_item.get('text'))
        if text:
            item['text'] = text
        raw_metadata = raw_item.get('metadata')
        if isinstance(raw_metadata, dict):
            metadata: dict[str, str] = {}
            for raw_key, metadata_value in raw_metadata.items():
                key = str(raw_key)
                safe_value = safe_content_metadata_value(key, metadata_value)
                if safe_value:
                    metadata[key] = safe_value
            if metadata:
                item['metadata'] = metadata
        normalized.append(item)
    return normalized


def content_items_json(value: Any) -> str:
    return json.dumps(normalized_content_items(value), separators=(',', ':'))
