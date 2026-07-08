from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from app.services.alleva_retrieval import (
    ALLEVA_TREATMENT_PLANS_PATH,
    DEFAULT_API_VERSION,
    bool_value,
    endpoint_failure_message,
    fetch_alleva_collection,
    list_records,
    rows_to_tsv,
    text_value,
)
from app.services.alleva_treatment_plan_harness_models import (
    NON_SUCCESS_BODY_PREVIEW_OMITTED,
    TREATMENT_PLAN_HARNESS_REPORTS,
    TreatmentPlanHarnessRequest,
    treatment_plan_default_parameters,
)
from app.services.alleva_treatment_plan_harness_streaming import decode_preview, load_json_body, stream_body
from app.services.alleva_treatment_plan_harness_summary import (
    filtered_records,
    safe_response_json_preview,
    safe_treatment_plan_row,
)
from app.services.api_connectivity import (
    MAX_RESPONSE_CAPTURE_BYTES,
    MAX_RESPONSE_PREVIEW_CHARS,
    redact_sensitive_text,
)

TREATMENT_PLAN_HARNESS_TSV_COLUMNS = [
    'treatment_plan_id',
    'patient_id',
    'raw_client_ref',
    'start_date',
    'end_date',
    'is_active',
    'is_complete',
    'is_initial_tp',
    'problem_count',
    'diagnosis_count',
    'goal_count',
    'objective_count',
    'intervention_count',
    'last_modified',
    'content_value_status',
]

TREATMENT_PLAN_COUNT_COLUMNS = ['metric', 'count', 'meaning']


def _missing_patient_id_result() -> dict[str, Any]:
    return {
        'status': 'fail',
        'message': 'Patient / Client ID is required before pulling a single treatment plan.',
        'category': 'missing_patient_id',
        'method': 'GET',
        'source_operation': f'GET {ALLEVA_TREATMENT_PLANS_PATH}',
        'rows': [],
        'total_records_seen': 0,
        'returned_count': 0,
        'direct_patient_filter_supported': False,
        'filtering_mode': 'client_side_by_client_reference',
    }


def _network_failure_result(exc: httpx.RequestError) -> dict[str, Any]:
    return {
        'status': 'fail',
        'message': redact_sensitive_text(f'{exc.__class__.__name__}: {exc}'),
        'category': 'network_failure',
        'method': 'GET',
        'source_operation': f'GET {ALLEVA_TREATMENT_PLANS_PATH}',
        'rows': [],
        'total_records_seen': 0,
        'returned_count': 0,
    }


def _status_message(*, request: TreatmentPlanHarnessRequest, status_code: int, api_version: str, parse_status: str, row_count: int, record_count: int) -> tuple[str, str, str]:
    if not 200 <= status_code < 300:
        category, message = endpoint_failure_message(path=ALLEVA_TREATMENT_PLANS_PATH, status_code=status_code, api_version=api_version)
        return 'fail', category, message
    if parse_status != 'ok':
        return 'warn', 'endpoint_non_json_response', f'Alleva GET {ALLEVA_TREATMENT_PLANS_PATH} responded, but the saved full response body could not be parsed as JSON.'
    if request.report == 'single_treatment_plan' and row_count == 0:
        return 'warn', 'no_treatment_plans_for_patient', f'GET {ALLEVA_TREATMENT_PLANS_PATH} returned {record_count} treatment plan record(s), but none matched the entered Patient / Client ID.'
    if request.report == 'single_treatment_plan':
        return 'ok', 'completed', f'GET {ALLEVA_TREATMENT_PLANS_PATH} returned {record_count} treatment plan record(s); client-side filtering returned {row_count} matching record(s).'
    return 'ok', 'completed', f'GET {ALLEVA_TREATMENT_PLANS_PATH} returned {row_count} treatment plan record(s).'


def _selected_records(request: TreatmentPlanHarnessRequest, records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str], str]:
    if request.report != 'single_treatment_plan':
        return records, [], ''
    selected_records, matched_references = filtered_records(records, request.patient_id)
    return selected_records, matched_references, (
        'The checked local Swagger/OpenAPI mapping does not expose a direct single-patient treatment-plan endpoint; '
        'the harness used client-side filtering against client references such as /clients/{patientId}.'
    )


def _treatment_plan_count_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active_count = sum(1 for record in records if bool_value(record.get('isActive'), default=False))
    inactive_count = len(records) - active_count
    return [
        {
            'metric': 'total_treatment_plans',
            'count': len(records),
            'meaning': 'All treatment-plan records returned by paginated GET /treatment-plans.',
        },
        {
            'metric': 'active_treatment_plans_isActive_true',
            'count': active_count,
            'meaning': 'Treatment-plan records where Alleva isActive is true.',
        },
        {
            'metric': 'inactive_treatment_plans_isActive_false',
            'count': inactive_count,
            'meaning': 'Treatment-plan records where Alleva isActive is false or missing.',
        },
    ]


def _collection_status(collection_error: dict[str, Any] | None, collection_warning: dict[str, Any] | None, row_count: int) -> tuple[str, str]:
    if collection_error and row_count == 0:
        return 'fail', str(collection_error.get('category') or 'endpoint_request_failed')
    if collection_error or collection_warning:
        return 'warn', str((collection_error or collection_warning or {}).get('category') or 'pagination_incomplete')
    return 'ok', 'completed'


def _run_paginated_summary(request: TreatmentPlanHarnessRequest) -> dict[str, Any]:
    collection = fetch_alleva_collection(
        base_url=request.base_url,
        path=ALLEVA_TREATMENT_PLANS_PATH,
        operation_parameters=request.operation_parameters,
        api_key=request.api_key,
        bearer_token=request.bearer_token,
        api_key_header_name=request.api_key_header_name,
        timeout_seconds=request.timeout_seconds,
        max_pages=request.max_pages,
    )
    plan_rows = [safe_treatment_plan_row(record, today=date.today()) for record in collection.records]
    status, category = _collection_status(collection.error, collection.warning, len(plan_rows))
    if request.report == 'treatment_plan_counts':
        count_rows = _treatment_plan_count_rows(collection.records)
        active_count = int(count_rows[1]['count'])
        inactive_count = int(count_rows[2]['count'])
        message = (
            f'GET {ALLEVA_TREATMENT_PLANS_PATH} counted {len(collection.records)} treatment-plan record(s): '
            f'{active_count} active and {inactive_count} inactive.'
        )
        return {
            'status': status,
            'message': message,
            'category': category,
            'method': 'GET',
            'source_operation': f'GET {ALLEVA_TREATMENT_PLANS_PATH}',
            'total_records_seen': len(collection.records),
            'returned_count': len(collection.records),
            'page_count': collection.page_count,
            'pagination_complete': collection.complete,
            'fetch_error': collection.error,
            'fetch_warning': collection.warning,
            'diagnostics': collection.diagnostics(),
            'treatment_plan_counts': {
                'total_treatment_plans': len(collection.records),
                'active_treatment_plans': active_count,
                'inactive_treatment_plans': inactive_count,
            },
            'columns': TREATMENT_PLAN_COUNT_COLUMNS,
            'tsv': rows_to_tsv(count_rows, TREATMENT_PLAN_COUNT_COLUMNS),
            'copy_format': 'tsv',
            'rows': count_rows,
            'treatment_plan_rows_preview': plan_rows[:25],
            'direct_patient_filter_supported': False,
            'filtering_mode': 'paginated_all_treatment_plans',
            'filtering_explanation': 'Counts use paginated GET /treatment-plans and classify active records only by Alleva isActive.',
            'matched_client_references': [],
        }
    message = f'GET {ALLEVA_TREATMENT_PLANS_PATH} returned {len(plan_rows)} treatment-plan record(s) across {collection.page_count} page(s).'
    return {
        'status': status,
        'message': message,
        'category': category,
        'method': 'GET',
        'source_operation': f'GET {ALLEVA_TREATMENT_PLANS_PATH}',
        'total_records_seen': len(collection.records),
        'returned_count': len(plan_rows),
        'page_count': collection.page_count,
        'pagination_complete': collection.complete,
        'fetch_error': collection.error,
        'fetch_warning': collection.warning,
        'diagnostics': collection.diagnostics(),
        'columns': TREATMENT_PLAN_HARNESS_TSV_COLUMNS,
        'tsv': rows_to_tsv(plan_rows, TREATMENT_PLAN_HARNESS_TSV_COLUMNS),
        'copy_format': 'tsv',
        'rows': plan_rows,
        'direct_patient_filter_supported': False,
        'filtering_mode': 'paginated_all_treatment_plans',
        'filtering_explanation': 'All-pages diagnostic uses paginated GET /treatment-plans; production patient matching should use /clients then ClientId per patient.',
        'matched_client_references': [],
    }


def run_treatment_plan_harness_pull(request: TreatmentPlanHarnessRequest) -> dict[str, Any]:
    if request.report == 'single_treatment_plan' and not request.patient_id.strip():
        return _missing_patient_id_result()
    if request.report in {'all_treatment_plans_all_pages', 'treatment_plan_counts'}:
        return _run_paginated_summary(request)
    try:
        streamed = stream_body(request)
    except httpx.RequestError as exc:
        return _network_failure_result(exc)

    api_version = text_value(request.operation_parameters.get('api-version')) or text_value(request.operation_parameters.get('X-Version')) or DEFAULT_API_VERSION
    response_preview = redact_sensitive_text(decode_preview(streamed.preview)[:MAX_RESPONSE_PREVIEW_CHARS])
    parsed_json, parse_status, parse_error = load_json_body(streamed.body_file)
    records = list_records(parsed_json)
    selected_records, matched_references, filtering_explanation = _selected_records(request, records)
    rows = [safe_treatment_plan_row(record, today=date.today()) for record in selected_records]
    status, category, message = _status_message(
        request=request,
        status_code=streamed.status_code,
        api_version=api_version,
        parse_status=parse_status,
        row_count=len(rows),
        record_count=len(records),
    )
    response_json_preview = safe_response_json_preview(
        parsed_json=parsed_json,
        total_records_seen=len(records),
        selected_rows=rows,
        single_patient_filter=request.report == 'single_treatment_plan',
    ) if parse_status == 'ok' else None
    return {
        'status': status,
        'message': message,
        'category': category,
        'method': 'GET',
        'source_operation': f'GET {ALLEVA_TREATMENT_PLANS_PATH}',
        'url': streamed.url,
        'status_code': streamed.status_code,
        'elapsed_ms': streamed.elapsed_ms,
        'content_type': streamed.content_type,
        'response_truncated': streamed.truncated,
        'response_capture_limit_bytes': MAX_RESPONSE_CAPTURE_BYTES,
        'response_size_bytes_observed': streamed.observed_bytes,
        'response_body_file': streamed.body_file,
        'response_body_preview': NON_SUCCESS_BODY_PREVIEW_OMITTED if not 200 <= streamed.status_code < 300 else ('' if parse_status == 'ok' else response_preview),
        'response_json_parse_status': parse_status,
        'response_json_parse_error': parse_error,
        'response_json_preview': response_json_preview,
        'total_records_seen': len(records),
        'returned_count': len(rows),
        'columns': TREATMENT_PLAN_HARNESS_TSV_COLUMNS,
        'tsv': rows_to_tsv(rows, TREATMENT_PLAN_HARNESS_TSV_COLUMNS),
        'copy_format': 'tsv',
        'rows': rows,
        'direct_patient_filter_supported': False,
        'filtering_mode': 'client_side_by_client_reference' if request.report == 'single_treatment_plan' else '',
        'filtering_explanation': filtering_explanation,
        'matched_client_references': matched_references,
    }
