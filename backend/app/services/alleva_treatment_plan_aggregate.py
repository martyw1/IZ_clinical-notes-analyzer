from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from app.services.alleva_retrieval import bool_value, content_counts, date_text, diagnosis_records, first_text, list_records, parse_date
from app.services.patient_identity_minimization import sanitize_patient_payload
from app.services.treatment_plan_content_safety import content_value_assessment, structured_content_items

JsonObject = dict[str, Any]

ALLEVA_AGGREGATE_SCHEMA_VERSION = 'patient-treatment-plan-aggregate-v1'
DEFAULT_ONGOING_UPDATE_DAYS = 60
DEFAULT_DUE_SOON_THRESHOLD_DAYS = 14
DEFAULT_PLAN_DUE_DAYS = 30
LOC_UPDATE_INTERVAL_DAYS = {
    'iop': 60,
    'iop 5': 60,
    'php': 30,
    'rtc': 30,
    'residential': 30,
}

IDENTIFIER_FIELDS = (
    ('lead_id', ('leadId', 'lead_id')),
    ('client_id', ('clientId', 'client_id')),
    ('chart_id', ('chartId', 'chart_id', 'chartNumber', 'chart_number')),
    ('mrn', ('mrn', 'MRN')),
    ('unique_id', ('uniqueId', 'unique_id')),
    ('luin', ('luin', 'LUIN')),
    ('source_id', ('id', 'href')),
)
PREFERRED_PATIENT_KEY_ORDER = ('lead_id', 'client_id', 'chart_id', 'mrn', 'unique_id', 'luin', 'source_id')


@dataclass(frozen=True)
class AggregateBuildOptions:
    today: date | None = None
    include_patient_name: bool = False
    allow_name_fallback: bool = False
    active_only: bool = True
    default_ongoing_update_days: int = DEFAULT_ONGOING_UPDATE_DAYS
    default_plan_due_days: int = DEFAULT_PLAN_DUE_DAYS
    due_soon_threshold_days: int = DEFAULT_DUE_SOON_THRESHOLD_DAYS
    loc_update_interval_days: dict[str, int] = field(default_factory=lambda: dict(LOC_UPDATE_INTERVAL_DAYS))


@dataclass(frozen=True)
class AggregateBuildResult:
    aggregates: list[JsonObject]
    diagnostics: JsonObject


@dataclass
class _PatientState:
    raw: JsonObject
    identifiers: dict[str, str]
    patient_key: str
    name_key: str
    issues: list[JsonObject] = field(default_factory=list)
    treatment_plans: list[JsonObject] = field(default_factory=list)
    treatment_reviews: list[JsonObject] = field(default_factory=list)
    diagnoses: list[JsonObject] = field(default_factory=list)
    advanced_forms: list[JsonObject] = field(default_factory=list)
    raw_sources: list[JsonObject] = field(default_factory=list)
    join_confidences: list[str] = field(default_factory=list)


def build_patient_treatment_plan_aggregates(
    *,
    clients_payload: list[JsonObject],
    treatment_plans_payload: list[JsonObject],
    treatment_reviews_payload: list[JsonObject] | None = None,
    client_diagnoses_payload: list[JsonObject] | None = None,
    advanced_form_payloads: list[JsonObject] | None = None,
    options: AggregateBuildOptions | None = None,
) -> list[JsonObject]:
    return build_patient_treatment_plan_aggregate_result(
        clients_payload=clients_payload,
        treatment_plans_payload=treatment_plans_payload,
        treatment_reviews_payload=treatment_reviews_payload or [],
        client_diagnoses_payload=client_diagnoses_payload or [],
        advanced_form_payloads=advanced_form_payloads or [],
        options=options,
    ).aggregates


def build_patient_treatment_plan_aggregate_result(
    *,
    clients_payload: list[JsonObject],
    treatment_plans_payload: list[JsonObject],
    treatment_reviews_payload: list[JsonObject] | None = None,
    client_diagnoses_payload: list[JsonObject] | None = None,
    advanced_form_payloads: list[JsonObject] | None = None,
    options: AggregateBuildOptions | None = None,
) -> AggregateBuildResult:
    build_options = options or AggregateBuildOptions()
    today = build_options.today or date.today()
    states = _patient_states(clients_payload, build_options)
    alias_index, duplicate_aliases = _alias_index(states)
    for duplicate in duplicate_aliases:
        for state in duplicate:
            _add_issue(state.issues, 'duplicate_patient_identifier', 'high', 'A patient identifier matched more than one active Alleva client.', source='clients')

    plan_unmatched = _attach_records(
        records=treatment_plans_payload,
        states=states,
        alias_index=alias_index,
        endpoint='/treatment-plans',
        target='treatment_plan',
        options=build_options,
    )
    review_unmatched = _attach_records(
        records=treatment_reviews_payload or [],
        states=states,
        alias_index=alias_index,
        endpoint='/treatment-reviews',
        target='treatment_review',
        options=build_options,
    )
    diagnosis_unmatched = _attach_records(
        records=client_diagnoses_payload or [],
        states=states,
        alias_index=alias_index,
        endpoint='/clients/{id}/diagnosis',
        target='client_diagnosis',
        options=build_options,
    )
    form_unmatched = _attach_records(
        records=advanced_form_payloads or [],
        states=states,
        alias_index=alias_index,
        endpoint='advanced-forms',
        target='advanced_form',
        options=build_options,
    )

    aggregates = [_aggregate_payload(state, build_options, today=today) for state in states]
    diagnostics = _diagnostics(
        aggregates,
        plan_unmatched=plan_unmatched,
        review_unmatched=review_unmatched,
        diagnosis_unmatched=diagnosis_unmatched,
        form_unmatched=form_unmatched,
    )
    return AggregateBuildResult(aggregates=aggregates, diagnostics=diagnostics)


def _patient_states(clients_payload: list[JsonObject], options: AggregateBuildOptions) -> list[_PatientState]:
    states: list[_PatientState] = []
    for raw in clients_payload:
        if options.active_only and not _is_active_patient(raw):
            continue
        identifiers = _identifiers(raw)
        patient_key = _patient_key(identifiers)
        if not patient_key:
            continue
        state = _PatientState(raw=raw, identifiers=identifiers, patient_key=patient_key, name_key=_name_key(raw))
        if _has_discharge_conflict(raw):
            _add_issue(
                state.issues,
                'active_patient_discharge_conflict',
                'medium',
                'Alleva returned active-compatible status with discharge fields.',
                source='/clients',
            )
        state.raw_sources.append(_raw_source('/clients', raw))
        states.append(state)
    return states


def _alias_index(states: list[_PatientState]) -> tuple[dict[str, _PatientState], list[list[_PatientState]]]:
    index: dict[str, _PatientState] = {}
    duplicates: dict[str, list[_PatientState]] = {}
    for state in states:
        for value in state.identifiers.values():
            if not value:
                continue
            key = _alias_key(value)
            if not key:
                continue
            if key in index and index[key] is not state:
                duplicates.setdefault(key, [index[key]]).append(state)
                continue
            index[key] = state
    for key in duplicates:
        index.pop(key, None)
    return index, list(duplicates.values())


def _attach_records(
    *,
    records: list[JsonObject],
    states: list[_PatientState],
    alias_index: dict[str, _PatientState],
    endpoint: str,
    target: str,
    options: AggregateBuildOptions,
) -> list[JsonObject]:
    unmatched: list[JsonObject] = []
    for raw in records:
        match, confidence, warning = _match_patient(raw, states=states, alias_index=alias_index, options=options)
        if match is None:
            unmatched.append(_unmatched_record(raw, endpoint=endpoint, reason=warning or 'no_approved_identifier_match'))
            continue
        if warning:
            _add_issue(match.issues, warning, 'medium', 'Alleva record matched only through a lower-confidence fallback.', source=endpoint)
        if target == 'treatment_plan':
            normalized = _treatment_plan_payload(raw, confidence=confidence)
            match.treatment_plans.append(normalized)
        elif target == 'treatment_review':
            normalized = _treatment_review_payload(raw, confidence=confidence)
            match.treatment_reviews.append(normalized)
        elif target == 'client_diagnosis':
            normalized = _diagnosis_payload(raw, source='client_diagnosis')
            match.diagnoses.append(normalized)
        else:
            normalized = _advanced_form_payload(raw, confidence=confidence)
            match.advanced_forms.append(normalized)
        match.join_confidences.append(confidence)
        match.raw_sources.append(_raw_source(endpoint, raw))
    return unmatched


def _match_patient(
    raw: JsonObject,
    *,
    states: list[_PatientState],
    alias_index: dict[str, _PatientState],
    options: AggregateBuildOptions,
) -> tuple[_PatientState | None, str, str]:
    aliases = _record_aliases(raw)
    matches: list[_PatientState] = []
    for key in aliases:
        match = alias_index.get(key)
        if match is not None and all(existing is not match for existing in matches):
            matches.append(match)
    if len(matches) == 1:
        return matches[0], 'high', ''
    if len(matches) > 1:
        return None, 'none', 'ambiguous_identifier_match'
    if not options.allow_name_fallback:
        return None, 'none', 'no_approved_identifier_match'
    name_key = _record_name_key(raw)
    if not name_key:
        return None, 'none', 'no_approved_identifier_match'
    name_matches = [state for state in states if state.name_key == name_key]
    if len(name_matches) == 1:
        return name_matches[0], 'name_fallback', 'name_join_fallback_used'
    if len(name_matches) > 1:
        return None, 'none', 'ambiguous_name_match'
    return None, 'none', 'no_approved_identifier_match'


def _aggregate_payload(state: _PatientState, options: AggregateBuildOptions, *, today: date) -> JsonObject:
    plans = sorted(state.treatment_plans, key=_plan_sort_key, reverse=True)
    current = _select_current_plan(plans, today=today)
    reviews = sorted(state.treatment_reviews, key=_review_sort_key, reverse=True)
    diagnoses = _reconciled_diagnoses(state, current)
    issues = [*state.issues]
    if not current:
        _add_issue(issues, 'no_current_active_treatment_plan', 'high', 'No active current treatment plan was found for this active patient.', source='/treatment-plans')
    _add_diagnosis_issues(issues, diagnoses)
    computed_status = _computed_status(state, current, reviews, options, today=today)
    if computed_status.get('api_computed_due_date_disagreement'):
        _add_issue(
            issues,
            'next_review_due_disagreement',
            'medium',
            'Alleva displayed next review due date differs from the deterministic computed due date.',
            source='/treatment-reviews',
        )
    source_confidence = _source_confidence(state.join_confidences)
    return {
        'schema_version': ALLEVA_AGGREGATE_SCHEMA_VERSION,
        'patient_key': state.patient_key,
        'patient': _patient_payload(state, options),
        'episode': _episode_payload(state),
        'current_treatment_plan': current,
        'treatment_plans': plans,
        'treatment_reviews': reviews,
        'diagnoses': diagnoses,
        'advanced_form_captures': state.advanced_forms,
        'computed_status': computed_status,
        'data_quality': issues,
        'raw_sources': _dedupe_raw_sources(state.raw_sources),
        'source_confidence': source_confidence,
        'source_endpoint_count': len({source.get('endpoint') for source in state.raw_sources}),
    }


def _patient_payload(state: _PatientState, options: AggregateBuildOptions) -> JsonObject:
    return {
        'display_name': _patient_name(state.raw) if options.include_patient_name else None,
        'identifiers': state.identifiers,
        'is_active': _is_active_patient(state.raw),
        'status': first_text(state.raw, 'status'),
        'source_system': 'Alleva REST API',
    }


def _episode_payload(state: _PatientState) -> JsonObject:
    return {
        'admission_date': date_text(state.raw.get('admissionDateTime') or state.raw.get('admissionDate') or state.raw.get('firstContactDate')),
        'discharge_date': date_text(state.raw.get('dischargeDateTime') or state.raw.get('actualSysDischargeDateTime')),
        'level_of_care': first_text(state.raw, 'levelOfCare', 'level_of_care'),
        'facility': first_text(state.raw, 'facilityName', 'facility'),
        'primary_clinician': first_text(state.raw, 'primaryClinician', 'primaryClinicians', 'medicalProviders'),
        'loc_history': _level_of_care_history(state.raw),
    }


def _treatment_plan_payload(raw: JsonObject, *, confidence: str) -> JsonObject:
    counts = content_counts(raw)
    content_items = structured_content_items(raw)
    plan_id = first_text(raw, 'id', 'treatmentPlanId', 'href')
    is_initial = bool_value(raw.get('isInitialTP') or raw.get('isInitialTreatmentPlan'), default=False)
    is_complete = bool_value(raw.get('isComplete') or raw.get('complete'), default=False)
    client_signature = raw.get('clientSignature') if isinstance(raw.get('clientSignature'), dict) else {}
    staff_signature = raw.get('staffSignature') if isinstance(raw.get('staffSignature'), dict) else {}
    creator_signature = raw.get('creatorSignature') if isinstance(raw.get('creatorSignature'), dict) else {}
    guardian_signature = raw.get('guardianSignature') if isinstance(raw.get('guardianSignature'), dict) else {}
    return {
        'source_record_id': plan_id,
        'plan_kind': 'initial' if is_initial else 'master',
        'join_confidence': confidence,
        'is_active': bool_value(raw.get('isActive'), default=True),
        'is_complete': is_complete,
        'is_initial': is_initial,
        'start_date': date_text(raw.get('startDate') or raw.get('documentDate') or raw.get('createdDate')),
        'end_date': date_text(raw.get('endDate')),
        'last_modified': date_text(raw.get('lastModified') or raw.get('updatedDate')),
        'staff_signature_date': date_text(
            raw.get('staffSignatureDate')
            or raw.get('creatorSignatureDate')
            or raw.get('therapistSignatureDate')
            or _dict_text(staff_signature, 'signatureDateTime')
            or _dict_text(creator_signature, 'signatureDateTime')
        ),
        'client_signature_date': date_text(raw.get('clientSignatureDate') or _dict_text(client_signature, 'signatureDateTime')),
        'guardian_signature_date': date_text(raw.get('guardianSignatureDate') or _dict_text(guardian_signature, 'signatureDateTime')),
        'content_summary': counts,
        'content_structure': _content_structure(raw),
        'content_items': content_items,
        **content_value_assessment(content_items),
        'diagnosis_codes': _diagnosis_codes(raw),
        'source_endpoint': '/treatment-plans',
        'raw_source_hash': _payload_hash(raw),
        'data_quality': _plan_data_quality(raw, counts, is_complete),
    }


def _treatment_review_payload(raw: JsonObject, *, confidence: str) -> JsonObject:
    counts = content_counts(raw)
    content_items = structured_content_items(raw)
    return {
        'source_record_id': first_text(raw, 'id', 'treatmentPlanReviewId', 'href'),
        'join_confidence': confidence,
        'document_date': date_text(raw.get('createdDated') or raw.get('createdDate') or raw.get('generatedDate') or raw.get('documentDate')),
        'staff_signature_date': date_text(
            raw.get('creatorSignatureDate')
            or raw.get('ceratorSignatureDate')
            or raw.get('staffSignatureDate')
            or raw.get('therapistSignatureDate')
            or raw.get('reviewerSignatureDate')
        ),
        'client_signature_date': date_text(raw.get('clientSignatureDate')),
        'reviewer_signature_date': date_text(raw.get('reviewerSignatureDate') or raw.get('creatorSignatureDate') or raw.get('ceratorSignatureDate')),
        'next_review_due_api': date_text(raw.get('nextReviewDue') or raw.get('nextReviewDueDate') or raw.get('displayedNextReviewDueDate')),
        'content_summary': counts,
        'content_structure': _content_structure(raw),
        'content_items': content_items,
        **content_value_assessment(content_items),
        'source_endpoint': '/treatment-reviews',
        'raw_source_hash': _payload_hash(raw),
        'data_quality': [] if first_text(raw, 'staffSignatureDate', 'creatorSignatureDate', 'reviewerSignatureDate') else [
            _issue('missing_review_signature_date', 'medium', 'Treatment review is missing staff, creator, or reviewer signature date.', source='/treatment-reviews')
        ],
    }


def _diagnosis_payload(raw: JsonObject, *, source: str) -> JsonObject:
    return {
        'source': source,
        'source_record_id': first_text(raw, 'id', 'diagnosisId', 'href'),
        'code': first_text(raw, 'code', 'diagnosisCode', 'icd10Code', 'icdCode'),
        'status': first_text(raw, 'status', 'diagnosisStatus'),
        'is_active': _diagnosis_is_active(raw),
        'is_primary': bool_value(raw.get('isPrimary') or raw.get('primary') or raw.get('isPrimaryDiagnosis'), default=False),
        'raw_source_hash': _payload_hash(raw),
    }


def _advanced_form_payload(raw: JsonObject, *, confidence: str) -> JsonObject:
    return {
        'source_record_id': first_text(raw, 'id', 'formId', 'sourceKey', 'href'),
        'form_key': first_text(raw, 'formKey', 'formId', 'templateId'),
        'source_key': first_text(raw, 'sourceKey', 'treatmentPlanId', 'documentId'),
        'join_confidence': confidence,
        'captured_at': date_text(raw.get('capturedAt') or raw.get('createdDate') or raw.get('updatedDate')),
        'values': _advanced_values(raw.get('values') if isinstance(raw.get('values'), dict) else raw),
        'source_endpoint': 'advanced-forms',
        'raw_source_hash': _payload_hash(raw),
    }


def _advanced_values(values: Any) -> JsonObject:
    if not isinstance(values, dict):
        return {}
    safe_values: JsonObject = {}
    for key, value in values.items():
        if key in {'clientId', 'leadId', 'patientId', 'id', 'href'}:
            continue
        safe_values[str(key)] = _advanced_value(value)
    return safe_values


def _advanced_value(value: Any) -> JsonObject:
    if isinstance(value, bool):
        return {'type': 'boolean', 'value': value}
    if isinstance(value, int) and not isinstance(value, bool):
        return {'type': 'integer', 'value': value}
    if isinstance(value, float):
        return {'type': 'decimal', 'value': value}
    if isinstance(value, dict):
        if any(str(key).lower() in {'filename', 'file', 'url', 'signature', 'image', 'attachment'} for key in value):
            return {'type': 'file_or_signature', 'value_present': True, 'metadata_keys': sorted(str(key) for key in value)}
        return {'type': 'json', 'value_hash': _payload_hash(value), 'metadata_keys': sorted(str(key) for key in value)}
    if isinstance(value, list):
        return {'type': 'json', 'value_hash': _payload_hash(value), 'item_count': len(value)}
    text = str(value or '').strip()
    if parse_date(text):
        return {'type': 'dateTime', 'value': date_text(text)}
    if text:
        return {'type': 'string', 'value_present': True, 'value_hash': _payload_hash(text)}
    return {'type': 'empty', 'value_present': False}


def _computed_status(
    state: _PatientState,
    current: JsonObject | None,
    reviews: list[JsonObject],
    options: AggregateBuildOptions,
    *,
    today: date,
) -> JsonObject:
    latest_review = reviews[0] if reviews else None
    anchor_text = ''
    if latest_review:
        anchor_text = (
            str(latest_review.get('staff_signature_date') or '')
            or str(latest_review.get('reviewer_signature_date') or '')
            or str(latest_review.get('document_date') or '')
        )
    if not anchor_text and current:
        anchor_text = str(current.get('staff_signature_date') or current.get('start_date') or '')
    interval_days = _interval_days(first_text(state.raw, 'levelOfCare', 'level_of_care'), options)
    computed_due = _add_days(anchor_text, interval_days)
    api_due = str(latest_review.get('next_review_due_api') or '') if latest_review else ''
    selected_due = api_due or computed_due
    status = _due_status(selected_due, today=today, due_soon_threshold_days=options.due_soon_threshold_days)
    if api_due and computed_due and api_due != computed_due:
        status = 'Needs Review'
    missing_items = _missing_items(state, current)
    if missing_items:
        status = 'Missing Data'
    return {
        'status': status,
        'as_of_date': today.isoformat(),
        'next_review_due_api': api_due or None,
        'next_review_due_computed': computed_due or None,
        'next_review_due_selected': selected_due or None,
        'api_computed_due_date_disagreement': bool(api_due and computed_due and api_due != computed_due),
        'anchor_date': anchor_text or None,
        'interval_days': interval_days,
        'due_soon_threshold_days': options.due_soon_threshold_days,
        'completion_api': current.get('is_complete') if current else None,
        'completion_computed': _completion_computed(current),
        'missing_items': missing_items,
    }


def _diagnostics(
    aggregates: list[JsonObject],
    *,
    plan_unmatched: list[JsonObject],
    review_unmatched: list[JsonObject],
    diagnosis_unmatched: list[JsonObject],
    form_unmatched: list[JsonObject],
) -> JsonObject:
    issues = [issue for aggregate in aggregates for issue in aggregate.get('data_quality', []) if isinstance(issue, dict)]
    return {
        'aggregate_count': len(aggregates),
        'unmatched_treatment_plan_count': len(plan_unmatched),
        'unmatched_treatment_review_count': len(review_unmatched),
        'unmatched_diagnosis_count': len(diagnosis_unmatched),
        'unmatched_advanced_form_count': len(form_unmatched),
        'unmatched_treatment_plans': plan_unmatched,
        'unmatched_treatment_reviews': review_unmatched,
        'data_quality_summary': _count_by(issues, 'severity'),
        'data_quality_codes': _count_by(issues, 'code'),
        'endpoint_coverage_summary': _endpoint_summary(aggregates),
        'identifier_matching_diagnostics': _identifier_diagnostics(aggregates),
        'diagnosis_reconciliation_summary': _diagnosis_summary(aggregates),
        'completeness_summary': _computed_summary(aggregates, 'completion_computed'),
        'due_date_summary': _computed_summary(aggregates, 'status'),
    }


def _identifiers(raw: JsonObject) -> dict[str, str]:
    identifiers: dict[str, str] = {}
    for canonical, keys in IDENTIFIER_FIELDS:
        value = first_text(raw, *keys)
        if value:
            identifiers[canonical] = value
    return identifiers


def _patient_key(identifiers: dict[str, str]) -> str:
    for key in PREFERRED_PATIENT_KEY_ORDER:
        value = identifiers.get(key, '')
        if value:
            return f'{key.removesuffix("_id")}:{value}'
    return ''


def _record_aliases(raw: JsonObject) -> set[str]:
    aliases = {_alias_key(value) for value in _identifiers(raw).values()}
    for container_key in ('client', 'patient', 'lead', 'member'):
        nested = raw.get(container_key)
        if isinstance(nested, dict):
            aliases.update(_alias_key(value) for value in _identifiers(nested).values())
    for key in ('patientId', 'patient_id', 'treatmentPlanClientId', 'sourcePatientResourceId'):
        value = first_text(raw, key)
        if value:
            aliases.add(_alias_key(value))
    return {alias for alias in aliases if alias}


def _alias_key(value: str) -> str:
    return str(value or '').strip().lower()


def _name_key(raw: JsonObject) -> str:
    return _normalize_name(_patient_name(raw))


def _record_name_key(raw: JsonObject) -> str:
    return _normalize_name(first_text(raw, 'clientName', 'patientName', 'memberName') or _patient_name(raw))


def _patient_name(raw: JsonObject) -> str:
    direct = first_text(raw, 'clientName', 'patientName', 'clientFullName', 'fullName')
    if direct:
        return direct
    for key in ('name', 'client', 'patient', 'lead'):
        nested = raw.get(key)
        if isinstance(nested, dict):
            text = first_text(nested, 'clientFullName', 'patientFullName', 'fullName', 'displayName', 'name')
            if text:
                return text
    return ''


def _normalize_name(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', value.lower())


def _is_active_patient(raw: JsonObject) -> bool:
    status = first_text(raw, 'status').lower()
    if status and any(word in status for word in ('inactive', 'discharge', 'closed', 'deceased')):
        return False
    status_is_active = bool(status and 'active' in status)
    if bool_value(raw.get('isDischarge'), default=False) and not status_is_active:
        return False
    if not status and first_text(raw, 'dischargeDateTime', 'actualSysDischargeDateTime'):
        return False
    if raw.get('isClient') is not None and not bool_value(raw.get('isClient'), default=True):
        return False
    return True


def _has_discharge_conflict(raw: JsonObject) -> bool:
    status = first_text(raw, 'status').lower()
    discharge_date = date_text(raw.get('dischargeDateTime') or raw.get('actualSysDischargeDateTime'))
    return bool(status and 'active' in status and (discharge_date or bool_value(raw.get('isDischarge'), default=False)))


def _level_of_care_history(raw: JsonObject) -> list[JsonObject]:
    history = [item for item in list_records(raw.get('levelOfCareHistory') or raw.get('levelsOfCare'))]
    if history:
        return [
            {
                'level_of_care': first_text(item, 'levelOfCare', 'name'),
                'effective_date': date_text(item.get('effectiveDate') or item.get('startDate')),
                'discharge_date': date_text(item.get('dischargeDate') or item.get('endDate')),
                'facility': first_text(item, 'facilityName', 'facility'),
            }
            for item in history
        ]
    loc = first_text(raw, 'levelOfCare')
    if not loc:
        return []
    return [
        {
            'level_of_care': loc,
            'effective_date': date_text(raw.get('admissionDateTime') or raw.get('admissionDate') or raw.get('firstContactDate')),
            'discharge_date': date_text(raw.get('dischargeDateTime') or raw.get('actualSysDischargeDateTime')),
            'facility': first_text(raw, 'facilityName', 'facility'),
        }
    ]


def _dict_text(raw: JsonObject, key: str) -> str:
    return str(raw.get(key) or '').strip() if isinstance(raw, dict) else ''


def _content_structure(raw: JsonObject) -> JsonObject:
    safe = _safe_mapping(raw)
    problems = list_records(safe.get('problems'))
    structure = []
    for index, problem in enumerate(problems, start=1):
        diagnoses = list_records(problem.get('diagnoses'))
        goals = list_records(problem.get('goals'))
        structure.append(
            {
                'problem_index': index,
                'text_present': bool(first_text(problem, 'description', 'status', 'name', 'problem')),
                'diagnosis_count': len(diagnoses),
                'goal_count': len(goals),
                'goal_summaries': [
                    {
                        'goal_index': goal_index,
                        'text_present': bool(first_text(goal, 'description', 'name', 'goal')),
                        'objective_count': len(list_records(goal.get('objectives'))),
                    }
                    for goal_index, goal in enumerate(goals, start=1)
                ],
            }
        )
    return {'problems': structure}


def _diagnosis_codes(raw: JsonObject) -> list[str]:
    return sorted({code for code in (first_text(item, 'code', 'diagnosisCode', 'icd10Code', 'icdCode') for item in diagnosis_records(raw)) if code})


def _plan_data_quality(raw: JsonObject, counts: JsonObject, is_complete: bool) -> list[JsonObject]:
    issues: list[JsonObject] = []
    if not is_complete:
        _add_issue(issues, 'plan_not_marked_complete', 'medium', 'Alleva did not mark the treatment plan complete.', source='/treatment-plans')
    if is_complete and not first_text(raw, 'staffSignatureDate', 'creatorSignatureDate', 'therapistSignatureDate'):
        _add_issue(issues, 'complete_plan_missing_staff_signature_date', 'high', 'Complete treatment plan is missing staff signature date.', source='/treatment-plans')
    if is_complete and not counts.get('problem_count') and not counts.get('diagnosis_count'):
        _add_issue(issues, 'complete_plan_missing_content_counts', 'high', 'Complete treatment plan has no problems or diagnoses in the mapped schema.', source='/treatment-plans')
    return issues


def _select_current_plan(plans: list[JsonObject], *, today: date) -> JsonObject | None:
    active = [plan for plan in plans if bool(plan.get('is_active'))]
    if not active:
        return None
    return sorted(active, key=lambda plan: _plan_sort_key(plan, today=today), reverse=True)[0]


def _plan_sort_key(plan: JsonObject, today: date | None = None) -> tuple[int, date, date, str]:
    today = today or date.today()
    end_date = parse_date(plan.get('end_date'))
    current_window = 1 if end_date is None or end_date >= today else 0
    return (
        current_window,
        parse_date(plan.get('start_date')) or date.min,
        parse_date(plan.get('last_modified')) or date.min,
        str(plan.get('source_record_id') or ''),
    )


def _review_sort_key(review: JsonObject) -> tuple[date, date, str]:
    return (
        parse_date(review.get('staff_signature_date')) or parse_date(review.get('reviewer_signature_date')) or date.min,
        parse_date(review.get('document_date')) or date.min,
        str(review.get('source_record_id') or ''),
    )


def _reconciled_diagnoses(state: _PatientState, current: JsonObject | None) -> list[JsonObject]:
    plan_codes = set(current.get('diagnosis_codes') or []) if current else set()
    diagnoses = list(state.diagnoses)
    for code in plan_codes:
        diagnoses.append({'source': 'current_treatment_plan', 'code': code, 'is_active': True, 'is_primary': False})
    seen: set[tuple[str, str]] = set()
    unique = []
    for item in diagnoses:
        key = (str(item.get('source') or ''), str(item.get('code') or ''))
        if key in seen:
            continue
        seen.add(key)
        enriched = dict(item)
        if enriched.get('source') == 'client_diagnosis' and enriched.get('is_active') and enriched.get('code') not in plan_codes:
            enriched['present_in_current_plan'] = False
        elif enriched.get('code'):
            enriched['present_in_current_plan'] = enriched.get('code') in plan_codes
        unique.append(enriched)
    return unique


def _add_diagnosis_issues(issues: list[JsonObject], diagnoses: list[JsonObject]) -> None:
    if any(item.get('source') == 'client_diagnosis' and item.get('is_active') and item.get('present_in_current_plan') is False for item in diagnoses):
        _add_issue(
            issues,
            'active_client_diagnosis_missing_from_current_plan',
            'high',
            'An active client diagnosis was not represented in the current treatment plan diagnosis set.',
            source='/clients/{id}/diagnosis',
        )


def _diagnosis_is_active(raw: JsonObject) -> bool:
    status = first_text(raw, 'status', 'diagnosisStatus').lower()
    if any(word in status for word in ('inactive', 'resolved', 'deleted', 'discharge', 'closed')):
        return False
    return bool_value(raw.get('isActive'), default=True)


def _interval_days(loc: str, options: AggregateBuildOptions) -> int:
    normalized = loc.lower().strip()
    for key, days in options.loc_update_interval_days.items():
        if key.lower() in normalized:
            return int(days)
    return options.default_ongoing_update_days


def _add_days(value: str, days: int) -> str:
    anchor = parse_date(value)
    if not anchor:
        return ''
    return (anchor + timedelta(days=days)).isoformat()


def _due_status(value: str, *, today: date, due_soon_threshold_days: int) -> str:
    due = parse_date(value)
    if not due:
        return 'Missing Data'
    delta = (due - today).days
    if delta < 0:
        return 'Overdue'
    if delta <= 1:
        return 'Urgent'
    if delta <= due_soon_threshold_days:
        return 'Due Soon'
    return 'Compliant'


def _missing_items(state: _PatientState, current: JsonObject | None) -> list[str]:
    missing = []
    if not first_text(state.raw, 'admissionDateTime', 'admissionDate', 'firstContactDate'):
        missing.append('admission_date')
    if not first_text(state.raw, 'levelOfCare', 'level_of_care'):
        missing.append('level_of_care')
    if current is None:
        missing.append('current_treatment_plan')
    elif not current.get('staff_signature_date'):
        missing.append('current_plan_staff_signature_date')
    return missing


def _completion_computed(current: JsonObject | None) -> bool | None:
    if current is None:
        return None
    counts = current.get('content_summary') if isinstance(current.get('content_summary'), dict) else {}
    return bool(current.get('staff_signature_date') and (counts.get('problem_count') or counts.get('diagnosis_count')))


def _source_confidence(values: list[str]) -> str:
    rank = {'none': 0, 'unknown': 0, 'name_fallback': 1, 'medium': 2, 'high': 3}
    if not values:
        return 'unknown'
    return max(values, key=lambda value: rank.get(value, 0))


def _safe_mapping(raw: JsonObject) -> JsonObject:
    safe = sanitize_patient_payload(raw)
    return safe if isinstance(safe, dict) else {}


def _raw_source(endpoint: str, raw: JsonObject) -> JsonObject:
    return {
        'endpoint': endpoint,
        'method': 'GET',
        'source_record_id': first_text(raw, 'id', 'href', 'treatmentPlanId', 'treatmentPlanReviewId'),
        'payload_hash': _payload_hash(raw),
        'source_record_count': 1,
        'source_version': first_text(raw, 'apiVersion', 'version') or 'unknown',
    }


def _payload_hash(value: Any) -> str:
    safe = sanitize_patient_payload(value)
    encoded = json.dumps(safe, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _dedupe_raw_sources(sources: list[JsonObject]) -> list[JsonObject]:
    seen: set[tuple[str, str]] = set()
    deduped = []
    for source in sources:
        key = (str(source.get('endpoint') or ''), str(source.get('payload_hash') or ''))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped


def _unmatched_record(raw: JsonObject, *, endpoint: str, reason: str) -> JsonObject:
    return {
        'endpoint': endpoint,
        'source_record_id': first_text(raw, 'id', 'href', 'treatmentPlanId', 'treatmentPlanReviewId'),
        'payload_hash': _payload_hash(raw),
        'reason': reason,
    }


def _issue(code: str, severity: str, message: str, *, source: str) -> JsonObject:
    return {'code': code, 'severity': severity, 'message': message, 'source': source}


def _add_issue(issues: list[JsonObject], code: str, severity: str, message: str, *, source: str) -> None:
    issues.append(_issue(code, severity, message, source=source))


def _count_by(items: list[JsonObject], key: str) -> JsonObject:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or 'unknown')
        counts[value] = counts.get(value, 0) + 1
    return counts


def _endpoint_summary(aggregates: list[JsonObject]) -> JsonObject:
    counts: dict[str, int] = {}
    for aggregate in aggregates:
        for source in aggregate.get('raw_sources', []):
            if isinstance(source, dict):
                endpoint = str(source.get('endpoint') or 'unknown')
                counts[endpoint] = counts.get(endpoint, 0) + 1
    return counts


def _identifier_diagnostics(aggregates: list[JsonObject]) -> JsonObject:
    return {
        'source_confidence': _count_by(aggregates, 'source_confidence'),
        'name_fallback_aggregate_count': sum(1 for aggregate in aggregates if aggregate.get('source_confidence') == 'name_fallback'),
    }


def _diagnosis_summary(aggregates: list[JsonObject]) -> JsonObject:
    missing = 0
    total = 0
    for aggregate in aggregates:
        for diagnosis in aggregate.get('diagnoses', []):
            if not isinstance(diagnosis, dict):
                continue
            total += 1
            if diagnosis.get('source') == 'client_diagnosis' and diagnosis.get('is_active') and diagnosis.get('present_in_current_plan') is False:
                missing += 1
    return {'diagnosis_count': total, 'active_client_diagnosis_missing_from_current_plan_count': missing}


def _computed_summary(aggregates: list[JsonObject], key: str) -> JsonObject:
    values = []
    for aggregate in aggregates:
        status = aggregate.get('computed_status')
        if isinstance(status, dict):
            values.append({key: status.get(key)})
    return _count_by(values, key)
