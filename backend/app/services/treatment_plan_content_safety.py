from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from app.services.patient_identity_minimization import (
    is_direct_patient_identifier_key,
    redacted_text,
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
SAFE_CONTENT_KINDS = {'problem', 'diagnosis', 'goal', 'objective', 'intervention'}
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


def _compact_scalar(value: Any, *, max_chars: int) -> str:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return ''
    text = ' '.join(redacted_text(str(value)).split())
    if not text or text == '[redacted]' or text_looks_like_direct_patient_identifier(text):
        return ''
    return text[:max_chars]


def safe_content_text(value: Any, *, max_chars: int = 280) -> str:
    return _compact_scalar(value, max_chars=max_chars)


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
