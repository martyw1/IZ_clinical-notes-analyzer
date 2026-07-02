from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import unquote, urlparse

from app.services.alleva_retrieval import (
    bool_value,
    content_counts,
    date_text,
    parse_date,
    text_value,
    treatment_plan_identifier_summary,
    treatment_plan_status_scope,
)
from app.services.treatment_plan_content_safety import content_value_assessment, structured_content_items
from app.services.treatment_plan_content_tree import content_tree_from_items


def _client_reference_values(record: dict[str, Any]) -> list[str]:
    values: list[str] = []
    client = record.get('client')
    if isinstance(client, dict):
        for key in ('href', 'clientId', 'id', 'leadId', 'uniqueId', 'mrn'):
            value = text_value(client.get(key))
            if value:
                values.append(value)
    if isinstance(client, str):
        values.append(client.strip())
    for key in ('clientHref', 'clientUrl', 'clientId', 'patientId', 'leadId', 'sourceClientId'):
        value = text_value(record.get(key))
        if value:
            values.append(value)
    return values


def _reference_matches(candidate: str, patient_id: str) -> bool:
    target = patient_id.strip().lower()
    value = candidate.strip()
    if not value:
        return False
    if value.lower() == target:
        return True
    parsed_path = urlparse(value).path if '://' in value else value
    path_parts = [unquote(part).lower() for part in parsed_path.strip('/').split('/') if part]
    return len(path_parts) >= 2 and path_parts[-2] == 'clients' and path_parts[-1] == target


def filtered_records(records: list[dict[str, Any]], patient_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    matches: list[dict[str, Any]] = []
    matched_references: list[str] = []
    for record in records:
        references = _client_reference_values(record)
        if any(_reference_matches(reference, patient_id) for reference in references):
            matches.append(record)
            matched_references.extend(reference for reference in references if _reference_matches(reference, patient_id))
    return matches, matched_references[:25]


def _safe_content_counts(record: dict[str, Any]) -> dict[str, Any]:
    counts = content_counts(record)
    return {
        'plan_field_count': counts.get('plan_field_count', 0),
        'problem_count': counts.get('problem_count', 0),
        'diagnosis_count': counts.get('diagnosis_count', 0),
        'active_diagnosis_count': counts.get('active_diagnosis_count', 0),
        'behavioral_definition_count': counts.get('behavioral_definition_count', 0),
        'goal_count': counts.get('goal_count', 0),
        'objective_count': counts.get('objective_count', 0),
        'intervention_count': counts.get('intervention_count', 0),
    }


def _content_value_preview(items: list[dict[str, Any]]) -> str:
    values = [text_value(item.get('text')) for item in items if text_value(item.get('text'))]
    return ' | '.join(values)[:2000]


def safe_treatment_plan_row(record: dict[str, Any], *, today: date) -> dict[str, Any]:
    ids = treatment_plan_identifier_summary(record)
    scope, reason = treatment_plan_status_scope(record)
    end_date = parse_date(record.get('endDate'))
    start_date = parse_date(record.get('startDate'))
    is_complete = bool_value(record.get('isComplete'), default=False)
    content_items = structured_content_items(record)
    value_assessment = content_value_assessment(content_items)
    content_tree = content_tree_from_items(content_items)
    reasons = [reason]
    if end_date is None:
        reasons.append('endDate missing; due status needs review')
    elif end_date < today:
        reasons.append(f'endDate {end_date.isoformat()} is before {today.isoformat()}')
    else:
        reasons.append(f'endDate {end_date.isoformat()} is not overdue as of {today.isoformat()}')
    if not is_complete:
        reasons.append('isComplete is false or missing')
    return {
        'treatment_plan_id': ids['treatment_plan_id'],
        'patient_id': ids['app_patient_id'],
        'client_id': ids['client_id'],
        'source_client_id': ids['source_client_id'],
        'description_present': bool(text_value(record.get('description'))),
        'description_length': len(text_value(record.get('description'))),
        'start_date': start_date.isoformat() if start_date else date_text(record.get('startDate')),
        'end_date': end_date.isoformat() if end_date else date_text(record.get('endDate')),
        'status_scope': scope,
        'is_active': scope == 'active',
        'is_complete': is_complete,
        'last_modified': date_text(record.get('lastModified')),
        'is_initial_tp': bool_value(record.get('isInitialTP'), default=False),
        'is_wiley': bool_value(record.get('isWiley'), default=False),
        'has_reason_for_admission': bool(text_value(record.get('reasonForAdmission'))),
        'has_initial_client_needs': bool(text_value(record.get('initialClientNeeds'))),
        'has_family_education_needs': bool(text_value(record.get('familyEducationNeeds'))),
        'content_value_preview': _content_value_preview(content_items),
        **_safe_content_counts(record),
        'content_items': content_items,
        'content_tree': content_tree,
        **value_assessment,
        'why': '; '.join(reasons),
    }


def _json_shape(value: Any) -> str:
    if isinstance(value, list):
        return 'list'
    if isinstance(value, dict):
        return 'object'
    if value is None:
        return 'none'
    return type(value).__name__


def safe_response_json_preview(
    *,
    parsed_json: Any,
    total_records_seen: int,
    selected_rows: list[dict[str, Any]],
    single_patient_filter: bool,
) -> dict[str, Any]:
    return {
        'preview_omitted_reason': 'raw upstream treatment-plan payload is omitted from browser/report preview; structured redacted treatment-plan element values are included in sample_rows and the full raw response is saved to response_body_file.',
        'json_shape': _json_shape(parsed_json),
        'total_records_seen': total_records_seen,
        'selected_record_count': len(selected_rows),
        'sample_rows': selected_rows[:10],
        'sample_rows_truncated': max(0, len(selected_rows) - 10),
        'single_patient_filter_applied': single_patient_filter,
    }
