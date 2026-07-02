from __future__ import annotations

from datetime import date
from typing import Any, Final, Literal
from urllib.parse import quote

from app.services.alleva_patient_plan_contract import aggregate_patient_treatment_plans, is_active_patient, patient_record, warning
from app.services.alleva_retrieval import (
    ALLEVA_CLIENTS_PATH,
    ALLEVA_TREATMENT_PLANS_PATH,
    DEFAULT_API_VERSION,
    AllevaCollectionResult,
    fetch_alleva_collection,
    fetch_alleva_detail,
    text_value,
)
from app.services.alleva_treatment_plan_harness_models import TreatmentPlanHarnessRequest

PATIENT_CENTERED_TREATMENT_PLAN_REPORTS: Final = {
    'patient_centered_treatment_plans',
    'active_patient_centered_treatment_plans',
    'single_patient_treatment_plans',
}
PATIENT_CENTERED_SOURCE_OPERATION: Final = 'GET /clients + GET /treatment-plans?ClientId={patient_id}'
PatientSelection = Literal['all', 'active', 'single']


def _patient_selection(report: str) -> PatientSelection:
    if report == 'active_patient_centered_treatment_plans':
        return 'active'
    if report == 'single_patient_treatment_plans':
        return 'single'
    return 'all'


def _missing_patient_id_result() -> dict[str, Any]:
    return {
        'status': 'fail',
        'message': 'patient_id is required before pulling single-patient production treatment plans.',
        'category': 'missing_patient_id',
        'source_operation': PATIENT_CENTERED_SOURCE_OPERATION,
        'rows': [],
        'aggregates': [],
        'returned_count': 0,
        'total_records_seen': 0,
        'patient_selection': 'single',
        'fetch_errors': [],
        'fetch_error': None,
        'excluded_patients': [],
        'review_data_status': 'unavailable_via_rest_without_known_review_id',
        'next_review_due_source': 'unavailable',
        'client_query_parameter': 'ClientId',
        'lowercase_clientId_used': False,
    }


def _base_parameters(operation_parameters: dict[str, Any]) -> dict[str, Any]:
    parameters = dict(operation_parameters)
    parameters.setdefault('Limit', 500)
    parameters.setdefault('Cursor', 0)
    parameters.setdefault('api-version', DEFAULT_API_VERSION)
    parameters.setdefault('X-Version', DEFAULT_API_VERSION)
    return parameters


def _client_parameters(operation_parameters: dict[str, Any]) -> dict[str, Any]:
    parameters = _base_parameters(operation_parameters)
    parameters.pop('ClientId', None)
    parameters.pop('clientId', None)
    return parameters


def _plan_parameters(operation_parameters: dict[str, Any], patient_id: str) -> dict[str, Any]:
    parameters = _base_parameters(operation_parameters)
    parameters.pop('fields', None)
    parameters.pop('clientId', None)
    parameters['ClientId'] = patient_id
    return parameters


def _fetch_clients(request: TreatmentPlanHarnessRequest, selection: PatientSelection) -> tuple[list[dict[str, Any]], AllevaCollectionResult]:
    if selection == 'single':
        detail = fetch_alleva_detail(
            base_url=request.base_url,
            path=f'{ALLEVA_CLIENTS_PATH}/{quote(request.patient_id.strip())}',
            operation_parameters=_client_parameters(request.operation_parameters),
            api_key=request.api_key,
            bearer_token=request.bearer_token,
            api_key_header_name=request.api_key_header_name,
            timeout_seconds=request.timeout_seconds,
        )
        if detail.records:
            return detail.records, detail
        fallback = {'id': request.patient_id.strip()}
        return [fallback], detail
    clients = fetch_alleva_collection(
        base_url=request.base_url,
        path=ALLEVA_CLIENTS_PATH,
        operation_parameters=_client_parameters(request.operation_parameters),
        api_key=request.api_key,
        bearer_token=request.bearer_token,
        api_key_header_name=request.api_key_header_name,
        timeout_seconds=request.timeout_seconds,
        max_pages=request.max_pages,
    )
    return clients.records, clients


def _selected_patients(selection: PatientSelection, clients: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if selection == 'active':
        return [client for client in clients if is_active_patient(client)]
    return clients


def _endpoint_urls(result: AllevaCollectionResult, count: int) -> list[str]:
    if not result.pages:
        return [''] * count
    return [result.pages[0].url] * count


def _patient_plan_fetch(
    request: TreatmentPlanHarnessRequest,
    *,
    patient_id: str,
) -> AllevaCollectionResult:
    return fetch_alleva_collection(
        base_url=request.base_url,
        path=ALLEVA_TREATMENT_PLANS_PATH,
        operation_parameters=_plan_parameters(request.operation_parameters, patient_id),
        api_key=request.api_key,
        bearer_token=request.bearer_token,
        api_key_header_name=request.api_key_header_name,
        timeout_seconds=request.timeout_seconds,
        max_pages=request.max_pages,
    )


def _fetch_error(endpoint: str, result: AllevaCollectionResult) -> dict[str, Any] | None:
    if not result.error and not result.warning:
        return None
    issue = result.error or result.warning or {}
    return {'endpoint': endpoint, **issue}


def run_patient_centered_treatment_plan_harness_pull(request: TreatmentPlanHarnessRequest, *, today: date) -> dict[str, Any]:
    selection = _patient_selection(request.report)
    if selection == 'single' and not request.patient_id.strip():
        return _missing_patient_id_result()

    clients, client_result = _fetch_clients(request, selection)
    selected_clients = _selected_patients(selection, clients)
    aggregates: list[dict[str, Any]] = []
    fetch_errors = [error for error in [_fetch_error(ALLEVA_CLIENTS_PATH, client_result)] if error]
    excluded_patients: list[dict[str, str]] = []

    for client in selected_clients:
        summary = patient_record(client)
        patient_id = text_value(summary.get('patient_id'))
        if not patient_id:
            excluded_patients.append({'reason': 'GET /clients record did not include canonical id', 'status_label': summary.get('status_label', '')})
            continue
        plan_result = _patient_plan_fetch(request, patient_id=patient_id)
        plan_error = _fetch_error(f'{ALLEVA_TREATMENT_PLANS_PATH}?ClientId={patient_id}', plan_result)
        if plan_error:
            fetch_errors.append(plan_error)
        aggregate = aggregate_patient_treatment_plans(
            patient=client,
            treatment_plans=plan_result.records,
            endpoint_urls=_endpoint_urls(plan_result, len(plan_result.records)),
            today=today,
        )
        if plan_error:
            aggregate['warnings'].append(warning('treatment_plan_fetch_incomplete', plan_error.get('message', 'Treatment-plan fetch did not complete.'), source='/treatment-plans'))
        aggregates.append(aggregate)

    total_records_seen = len(clients) + sum(row['total_plan_count'] for row in aggregates)
    status = 'ok'
    if fetch_errors and not aggregates:
        status = 'fail'
    elif fetch_errors or not aggregates:
        status = 'warn'
    message = _message(status=status, selection=selection, aggregate_count=len(aggregates), total_records_seen=total_records_seen)
    return {
        'status': status,
        'message': message,
        'category': 'completed' if status == 'ok' else ('partial_source_failure' if aggregates else 'no_patient_plan_aggregates'),
        'source_operation': PATIENT_CENTERED_SOURCE_OPERATION,
        'method': 'GET',
        'rows': aggregates,
        'aggregates': aggregates,
        'returned_count': len(aggregates),
        'total_records_seen': total_records_seen,
        'patient_selection': selection,
        'fetch_errors': fetch_errors,
        'fetch_error': fetch_errors[0] if fetch_errors else None,
        'excluded_patients': excluded_patients,
        'review_data_status': 'unavailable_via_rest_without_known_review_id',
        'next_review_due_source': 'unavailable',
        'client_query_parameter': 'ClientId',
        'lowercase_clientId_used': False,
        'ignored_lowercase_clientId_parameter': 'clientId' in request.operation_parameters,
        'direct_patient_filter_supported': True,
        'filtering_mode': 'server_side_ClientId_query',
        'columns': [],
        'tsv': '',
        'copy_format': 'json',
    }


def _message(*, status: str, selection: PatientSelection, aggregate_count: int, total_records_seen: int) -> str:
    selection_label = {'all': 'patient-centered', 'active': 'active-patient-centered', 'single': 'single-patient'}[selection]
    if status == 'ok':
        return f'Alleva {selection_label} treatment-plan pull built {aggregate_count} aggregate(s) from {total_records_seen} fetched record(s) using ClientId.'
    if aggregate_count:
        return f'Alleva {selection_label} treatment-plan pull built {aggregate_count} aggregate(s), but one or more patient plan calls could not finish.'
    return f'Alleva {selection_label} treatment-plan pull did not produce aggregates. Confirm /clients, ClientId treatment-plan access, and source data.'
