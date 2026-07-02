from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from app.services.alleva_retrieval import (
    ALLEVA_TREATMENT_PLANS_PATH,
    DEFAULT_API_VERSION,
    endpoint_failure_message,
    list_records,
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


def run_treatment_plan_harness_pull(request: TreatmentPlanHarnessRequest) -> dict[str, Any]:
    if request.report == 'single_treatment_plan' and not request.patient_id.strip():
        return _missing_patient_id_result()
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
        'rows': rows,
        'direct_patient_filter_supported': False,
        'filtering_mode': 'client_side_by_client_reference' if request.report == 'single_treatment_plan' else '',
        'filtering_explanation': filtering_explanation,
        'matched_client_references': matched_references,
    }
