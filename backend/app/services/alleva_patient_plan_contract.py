from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Final, Literal
from urllib.parse import unquote, urlparse

from app.services.alleva_retrieval import bool_value, content_counts, date_text, first_text, parse_date, text_value
from app.services.treatment_plan_content_safety import content_value_assessment, structured_content_items
from app.services.treatment_plan_content_tree import content_tree_from_items

REVIEW_DATA_STATUS_UNAVAILABLE: Final = 'unavailable_via_rest_without_known_review_id'
NEXT_REVIEW_DUE_SOURCE_UNAVAILABLE: Final = 'unavailable'
ACTIVE_STATUS_ID: Final = '1049'
DISCHARGED_STATUS_ID: Final = '1356'

PatientStatusScope = Literal['active', 'discharged', 'other', 'unknown']


@dataclass(frozen=True, slots=True)
class JoinValidation:
    raw_client_ref: str
    extracted_patient_id: str
    join_validated: bool
    join_warning: str


def scalar_text(value: Any) -> str:
    if isinstance(value, dict | list):
        return ''
    return text_value(value)


def patient_status(raw: dict[str, Any]) -> dict[str, str]:
    status_value = raw.get('status')
    status_id = first_text(status_value, 'id') if isinstance(status_value, dict) else scalar_text(raw.get('statusId') or raw.get('status_id'))
    if isinstance(status_value, dict):
        status_label = first_text(status_value, 'name', 'label', 'statusName', 'description', 'value')
    else:
        status_label = scalar_text(status_value) or scalar_text(raw.get('statusName'))
    return {
        'status_id': status_id,
        'status_label': status_label,
        'status_scope': status_scope(status_id=status_id, status_label=status_label),
    }


def status_scope(*, status_id: str, status_label: str) -> PatientStatusScope:
    normalized_id = status_id.strip()
    normalized_label = re.sub(r'[\s_-]+', '', status_label.strip().lower())
    if normalized_id == ACTIVE_STATUS_ID:
        return 'active'
    if normalized_id == DISCHARGED_STATUS_ID:
        return 'discharged'
    if normalized_label == 'active':
        return 'active'
    if 'discharg' in normalized_label or normalized_label in {'closed', 'deceased'}:
        return 'discharged'
    if normalized_label:
        return 'other'
    return 'unknown'


def patient_record(raw: dict[str, Any]) -> dict[str, Any]:
    status = patient_status(raw)
    patient_id = scalar_text(raw.get('id'))
    return {
        'patient_id': patient_id,
        'source_id': first_text(raw, 'chartId', 'externalId', 'clientId', 'uniqueId', 'mrn'),
        'status_id': status['status_id'],
        'status_label': status['status_label'],
        'status_scope': status['status_scope'],
        'admission_date': date_text(raw.get('admissionDateTime') or raw.get('admissionDate')),
        'planned_discharge_date': date_text(raw.get('dischargeDate') or raw.get('dischargeDateTime')),
        'level_of_care': first_text(raw, 'levelOfCare'),
        'facility': first_text(raw, 'facilityName'),
        'primary_clinician': first_text(raw, 'primaryClinician', 'primaryClinicians', 'medicalProviders'),
        'first_contact_date': date_text(raw.get('firstContactDate')),
    }


def is_active_patient(raw: dict[str, Any]) -> bool:
    return patient_status(raw)['status_scope'] == 'active'


def extract_patient_id_from_client_ref(raw_client_ref: str) -> str:
    value = raw_client_ref.strip()
    if not value:
        return ''
    parsed_path = urlparse(value).path if '://' in value else value
    parts = [unquote(part).strip() for part in parsed_path.strip('/').split('/') if part.strip()]
    if len(parts) >= 2 and parts[-2].lower() == 'clients':
        return parts[-1]
    return ''


def raw_client_ref(plan: dict[str, Any]) -> tuple[str, str]:
    client = plan.get('client')
    if isinstance(client, str):
        return client.strip(), ''
    if isinstance(client, dict):
        href = first_text(client, 'href')
        if href:
            return href, 'client field was an object; used client.href instead of the documented string shape'
        return '', 'client field was an object without href'
    if client is None:
        return '', 'client field is missing'
    return '', 'client field is not a string'


def validate_plan_join(plan: dict[str, Any], patient_id: str) -> JoinValidation:
    reference, shape_warning = raw_client_ref(plan)
    extracted = extract_patient_id_from_client_ref(reference)
    if not reference:
        return JoinValidation(reference, extracted, False, shape_warning or 'raw client reference is missing')
    if not extracted:
        return JoinValidation(reference, extracted, False, shape_warning or f'raw client reference {reference!r} is not in /clients/{{id}} format')
    if extracted != patient_id:
        return JoinValidation(reference, extracted, False, f'raw client reference points to patient {extracted}, not queried patient {patient_id}')
    if shape_warning:
        return JoinValidation(reference, extracted, False, shape_warning)
    return JoinValidation(reference, extracted, True, '')


def warning(code: str, message: str, *, source: str, severity: str = 'medium', treatment_plan_id: str = '') -> dict[str, str]:
    return {
        'code': code,
        'severity': severity,
        'source': source,
        'message': message,
        'treatment_plan_id': treatment_plan_id,
    }


def treatment_plan_record(plan: dict[str, Any], *, patient_id: str, endpoint_url: str, today: date) -> dict[str, Any]:
    join = validate_plan_join(plan, patient_id)
    treatment_plan_id = first_text(plan, 'TPId', 'id', 'treatmentPlanId')
    is_active = bool_value(plan.get('isActive'), default=False)
    is_complete = bool_value(plan.get('isComplete'), default=False)
    end_date = parse_date(plan.get('endDate'))
    content_items = structured_content_items(plan)
    plan_warnings = [] if join.join_validated else [warning('join_not_validated', join.join_warning, source='/treatment-plans', treatment_plan_id=treatment_plan_id)]
    if is_active and end_date is not None and end_date < today:
        plan_warnings.append(warning('active_plan_with_past_end_date', f'Active plan endDate {end_date.isoformat()} is before {today.isoformat()}.', source='/treatment-plans', treatment_plan_id=treatment_plan_id))
    if is_active and not is_complete:
        plan_warnings.append(warning('incomplete_active_plan', 'isComplete is false on an active plan; isComplete is EMR submission state, not current-plan state.', source='/treatment-plans', treatment_plan_id=treatment_plan_id))
    if plan.get('isActive') is None:
        plan_warnings.append(warning('missing_isActive', 'isActive is missing; the plan is not counted as active.', source='/treatment-plans', treatment_plan_id=treatment_plan_id))
    return {
        'treatment_plan_id': treatment_plan_id,
        'patient_id': patient_id,
        'raw_client_ref': join.raw_client_ref,
        'extracted_patient_id': join.extracted_patient_id,
        'plan_client_id': join.extracted_patient_id,
        'join_validated': join.join_validated,
        'join_warning': join.join_warning,
        'endpoint_url': endpoint_url,
        'start_date': date_text(plan.get('startDate')),
        'end_date': date_text(plan.get('endDate')),
        'created_date': date_text(plan.get('createdDate') or plan.get('createdDated')),
        'last_modified': date_text(plan.get('lastModified')),
        'is_active': is_active,
        'is_complete': is_complete,
        'is_initial_tp': bool_value(plan.get('isInitialTP'), default=False),
        'is_wiley': bool_value(plan.get('isWiley'), default=False),
        'has_reason_for_admission': bool(text_value(plan.get('reasonForAdmission'))),
        'has_initial_client_needs': bool(text_value(plan.get('initialClientNeeds'))),
        'has_family_education_needs': bool(text_value(plan.get('familyEducationNeeds'))),
        **content_counts(plan),
        'content_items': content_items,
        'content_tree': content_tree_from_items(content_items),
        **content_value_assessment(content_items),
        'warnings': plan_warnings,
    }


def aggregate_patient_treatment_plans(
    *,
    patient: dict[str, Any],
    treatment_plans: list[dict[str, Any]],
    endpoint_urls: list[str],
    today: date,
) -> dict[str, Any]:
    patient_summary = patient_record(patient)
    patient_id = patient_summary['patient_id']
    plan_rows = [
        treatment_plan_record(plan, patient_id=patient_id, endpoint_url=endpoint_urls[index] if index < len(endpoint_urls) else '', today=today)
        for index, plan in enumerate(treatment_plans)
    ]
    active_plans = [plan for plan in plan_rows if plan['is_active']]
    latest_active = max(active_plans, key=latest_plan_sort_key, default=None)
    warnings = [item for plan in plan_rows for item in plan['warnings']]
    if patient_summary['status_scope'] in {'active', 'discharged'} and not patient_summary['status_id']:
        warnings.append(
            warning(
                'missing_patient_status_id',
                (
                    f"Client status label {patient_summary['status_label']!r} mapped to "
                    f"{patient_summary['status_scope']}, but status.id is missing; preserve "
                    'status_id as blank and review the vendor response.'
                ),
                source='/clients',
            )
        )
    if patient_summary['status_scope'] == 'unknown':
        warnings.append(warning('unknown_patient_status', 'Client status is missing or unknown; this patient is not treated as active.', source='/clients'))
    if patient_summary['status_scope'] == 'other':
        warnings.append(warning('other_patient_status', f"Client status {patient_summary['status_label']!r} is not Active or Discharged.", source='/clients'))
    warnings.append(warning('review_data_unavailable', 'nextReviewDue requires a known treatmentPlanReviewId; treatment reviews cannot be listed or joined by patient via REST alone.', source='/treatment-reviews', severity='low'))
    return {
        'patient_id': patient_id,
        'patient': patient_summary,
        'status_id': patient_summary['status_id'],
        'status_label': patient_summary['status_label'],
        'status_scope': patient_summary['status_scope'],
        'total_plan_count': len(plan_rows),
        'active_plan_count': len(active_plans),
        'has_multiple_active_plans': len(active_plans) > 1,
        'treatment_plan_ids': [plan['treatment_plan_id'] for plan in plan_rows if plan['treatment_plan_id']],
        'active_treatment_plan_ids': [plan['treatment_plan_id'] for plan in active_plans if plan['treatment_plan_id']],
        'latest_created_active_plan_id': latest_active['treatment_plan_id'] if latest_active else '',
        'latest_created_active_plan': latest_active,
        'treatment_plans': plan_rows,
        'active_treatment_plans': active_plans,
        'review_data_status': REVIEW_DATA_STATUS_UNAVAILABLE,
        'next_review_due_source': NEXT_REVIEW_DUE_SOURCE_UNAVAILABLE,
        'review_availability': {
            'review_data_status': REVIEW_DATA_STATUS_UNAVAILABLE,
            'next_review_due_source': NEXT_REVIEW_DUE_SOURCE_UNAVAILABLE,
            'message': 'GET /treatment-reviews/{id} is usable only when a trusted treatmentPlanReviewId is already known; do not join reviews by clientName.',
        },
        'warnings': warnings,
    }


def latest_plan_sort_key(plan: dict[str, Any]) -> tuple[int, str]:
    value = text_value(plan.get('treatment_plan_id'))
    try:
        return int(value), value
    except ValueError:
        match = re.search(r'(\d+)(?!.*\d)', value)
        return (int(match.group(1)) if match else -1, value)
