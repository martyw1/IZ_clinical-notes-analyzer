from pathlib import Path
from urllib.parse import parse_qs, urlparse

from api_treatment_plan_harness_support import (
    PatientCenteredTreatmentPlanHarnessHttpxClient,
    TreatmentPlanHarnessHttpxClient,
    base_body,
    patch_outbound_httpx,
    saved_client_credentials_headers,
)


def test_api_configuration_treatment_plan_harness_saves_all_response_metadata(app_with_sqlite, monkeypatch):
    # Given: saved OAuth settings and a synthetic Alleva /treatment-plans response.
    app, session_local = app_with_sqlite
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.models.models import AuditLog

    with TestClient(app) as client:
        patch_outbound_httpx(monkeypatch, TreatmentPlanHarnessHttpxClient)
        headers = saved_client_credentials_headers(client)

        # When: the admin runs the all-treatment-plans harness pull.
        pulled = client.post('/api/api-configuration/alleva-quick-pull', headers=headers, json={**base_body(), 'report': 'all_treatment_plans'})

        # Then: metadata and saved paths appear without leaking treatment narrative or credentials.
        assert pulled.status_code == 200
        payload = pulled.json()
        parsed_url = urlparse(payload['url'])
        query = parse_qs(parsed_url.query)
        assert payload['status'] == 'ok'
        assert payload['source_operation'] == 'GET /treatment-plans'
        assert parsed_url.path.endswith('/treatment-plans')
        assert query['Limit'] == ['100']
        assert query['StartDate'] == ['2000-01-01T16:03']
        assert payload['response_truncated'] is False
        assert payload['response_capture_limit_bytes'] > 0
        assert payload['response_json_parse_status'] == 'ok'
        assert Path(payload['response_body_file']).exists()
        assert Path(payload['report_path']).exists()
        assert payload['report']['report_type'] == 'alleva_all_treatment_plans'
        assert payload['report']['result']['report'] == 'all_treatment_plans'
        assert payload['returned_count'] == 2
        assert payload['rows'][0]['description_present'] is True
        assert 'description' not in payload['rows'][0]
        assert payload['rows'][0]['content_items'][0]['kind'] == 'plan_field'
        assert any(item['kind'] == 'problem' and item.get('text') == 'synthetic substance use problem' for item in payload['rows'][0]['content_items'])
        assert payload['rows'][0]['behavioral_definition_count'] == 1
        assert payload['rows'][0]['content_tree']['problems'][0]['behavioral_definitions'][0]['text'] == 'synthetic cravings and isolation pattern'
        assert (
            payload['rows'][0]['content_tree']['problems'][0]['goals'][0]['objectives'][0]['interventions'][0]['text']
            == 'Synthetic intervention'
        )
        assert payload['rows'][0]['content_items'][-1]['text'] == 'Synthetic intervention'
        assert payload['rows'][0]['content_value_status'] == 'incomplete'
        assert payload['rows'][0]['missing_content_values'] == ['diagnosis']
        assert payload['response_json_preview']['total_records_seen'] == 2
        assert payload['response_json_preview']['preview_omitted_reason'].startswith('raw upstream treatment-plan payload is omitted')
        body_text = Path(payload['response_body_file']).read_text(encoding='utf-8')
        report_text = Path(payload['report_path']).read_text(encoding='utf-8')
        assert 'Synthetic treatment plan content' in body_text
        assert 'Synthetic intervention' in pulled.text
        assert 'Synthetic intervention' in report_text
        for secret in ('saved-secret', 'mock-access-token'):
            assert secret not in pulled.text
            assert secret not in report_text

    db = session_local()
    try:
        logs = db.execute(select(AuditLog).where(AuditLog.action == 'api_configuration.alleva_quick_pull')).scalars().all()
        serialized = ' '.join(f'{log.message} {log.details}' for log in logs)
        for secret in ('Synthetic treatment plan content', 'Synthetic reason', 'Synthetic need', 'Synthetic intervention', 'saved-secret', 'mock-access-token'):
            assert secret not in serialized
    finally:
        db.close()


def test_api_configuration_treatment_plan_harness_filters_single_patient_by_client_href(app_with_sqlite, monkeypatch):
    # Given: /treatment-plans has no direct patient filter, but records include client hrefs.
    app, _ = app_with_sqlite
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        patch_outbound_httpx(monkeypatch, TreatmentPlanHarnessHttpxClient)
        headers = saved_client_credentials_headers(client)

        # When: the admin requests one patient/client ID.
        pulled = client.post(
            '/api/api-configuration/alleva-quick-pull',
            headers=headers,
            json={**base_body(), 'report': 'single_treatment_plan', 'patient_id': 'PAT-HREF-001'},
        )

        # Then: the harness documents client-side fallback filtering and returns only the href match.
        payload = pulled.json()
        assert pulled.status_code == 200
        assert payload['status'] == 'ok'
        assert payload['direct_patient_filter_supported'] is False
        assert payload['filtering_mode'] == 'client_side_by_client_reference'
        assert 'client-side filtering' in payload['filtering_explanation']
        assert payload['total_records_seen'] == 2
        assert payload['returned_count'] == 1
        assert payload['rows'][0]['treatment_plan_id'] == 'tp-101'
        assert 'description' not in payload['rows'][0]
        assert payload['rows'][0]['plan_field_count'] >= 6
        assert payload['rows'][0]['content_items'][0]['kind'] == 'plan_field'
        assert payload['rows'][0]['content_tree']['plan_fields'][0]['text'] == 'Synthetic treatment plan content'
        assert payload['rows'][0]['content_items'][-1]['text'] == 'Synthetic intervention'
        assert payload['rows'][0]['content_tree']['problems'][0]['goals'][0]['text'] == 'sustain recovery goals'
        assert payload['matched_client_references'] == ['/clients/PAT-HREF-001']
        report_text = Path(payload['report_path']).read_text(encoding='utf-8')
        assert 'Other synthetic treatment plan content' not in pulled.text
        assert 'Other synthetic treatment plan content' not in report_text


def test_api_configuration_treatment_plan_harness_requires_patient_id_for_single_pull(app_with_sqlite, monkeypatch):
    # Given: the single-patient report is requested without an identifier.
    app, _ = app_with_sqlite
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        patch_outbound_httpx(monkeypatch, TreatmentPlanHarnessHttpxClient)
        headers = saved_client_credentials_headers(client)

        # When: no patient/client ID is provided.
        pulled = client.post('/api/api-configuration/alleva-quick-pull', headers=headers, json={**base_body(), 'report': 'single_treatment_plan', 'patient_id': '   '})

        # Then: the backend guard fails clearly before calling /treatment-plans.
        payload = pulled.json()
        assert pulled.status_code == 200
        assert payload['status'] == 'fail'
        assert payload['category'] == 'missing_patient_id'
        assert 'Patient / Client ID' in payload['message']


def test_patient_plan_contract_extracts_clients_ref_and_flags_bad_joins():
    # Given: one canonical Alleva /clients.id and treatment plans with missing, malformed, and mismatched client refs.
    from datetime import date

    from app.services.alleva_patient_plan_contract import aggregate_patient_treatment_plans, extract_patient_id_from_client_ref

    assert extract_patient_id_from_client_ref('/clients/307') == '307'
    assert extract_patient_id_from_client_ref('https://api.example.test/clients/307') == '307'

    # When: the aggregate is built from patient context rather than fabricated plan IDs.
    aggregate = aggregate_patient_treatment_plans(
        patient={'id': 307, 'status': {'id': 1049, 'name': 'Active'}},
        treatment_plans=[
            {'id': 1, 'client': '', 'isActive': True, 'isComplete': True},
            {'id': 2, 'client': '/not-clients/307', 'isActive': True, 'isComplete': True},
            {'id': 3, 'client': '/clients/999', 'isActive': True, 'isComplete': True},
        ],
        endpoint_urls=['https://api.example.test/treatment-plans?ClientId=307'],
        today=date(2026, 7, 2),
    )

    # Then: every plan is preserved, but none is treated as a successful joined plan.
    assert aggregate['patient_id'] == '307'
    assert aggregate['total_plan_count'] == 3
    assert all(not plan['join_validated'] for plan in aggregate['treatment_plans'])
    assert {warning['code'] for warning in aggregate['warnings']} >= {'join_not_validated', 'review_data_unavailable'}
    assert all(plan['patient_id'] == '307' for plan in aggregate['treatment_plans'])


def test_patient_status_uses_status_id_not_discharge_fields():
    # Given: Alleva client records with status IDs and misleading planned discharge fields.
    from datetime import date

    from app.services.alleva_patient_plan_contract import aggregate_patient_treatment_plans, is_active_patient, patient_record

    active_with_planned_discharge = {'id': 307, 'status': {'id': 1049, 'name': 'Active'}, 'dischargeDate': '2026-08-01'}
    discharged_without_discharge_date = {'id': 308, 'status': {'id': 1356, 'name': 'Discharged'}}
    inactive_text = {'id': 309, 'status': 'InActive'}
    active_label_without_id = {'id': 310, 'status': 'Active'}

    # When/Then: status.id drives active/discharged classification, not dischargeDate/isDischarge.
    assert is_active_patient(active_with_planned_discharge) is True
    assert is_active_patient(discharged_without_discharge_date) is False
    assert patient_record(active_with_planned_discharge)['planned_discharge_date'] == '2026-08-01'
    assert patient_record(discharged_without_discharge_date)['status_scope'] == 'discharged'
    assert patient_record(inactive_text)['status_scope'] == 'other'

    aggregate = aggregate_patient_treatment_plans(patient=active_label_without_id, treatment_plans=[], endpoint_urls=[], today=date(2026, 7, 2))
    assert aggregate['status_scope'] == 'active'
    assert aggregate['status_id'] == ''
    assert any(warning['code'] == 'missing_patient_status_id' for warning in aggregate['warnings'])


def test_api_configuration_patient_centered_treatment_plan_harness_uses_ClientId(app_with_sqlite, monkeypatch):
    # Given: saved OAuth settings and vendor-shaped client/treatment-plan payloads.
    app, _ = app_with_sqlite
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        patch_outbound_httpx(monkeypatch, PatientCenteredTreatmentPlanHarnessHttpxClient)
        headers = saved_client_credentials_headers(client)

        # When: the admin runs the active patient-centered production harness pull.
        body = base_body()
        body['operation_parameters'] = {**body['operation_parameters'], 'clientId': 'SHOULD-NOT-BE-USED'}
        pulled = client.post('/api/api-configuration/alleva-quick-pull', headers=headers, json={**body, 'report': 'active_patient_centered_treatment_plans'})

        # Then: the backend calls /clients first, uses ClientId per patient, and exposes joined evidence.
        assert pulled.status_code == 200
        payload = pulled.json()
        assert payload['status'] == 'ok'
        assert payload['source_operation'] == 'GET /clients + GET /treatment-plans?ClientId={patient_id}'
        assert payload['client_query_parameter'] == 'ClientId'
        assert payload['lowercase_clientId_used'] is False
        assert payload['ignored_lowercase_clientId_parameter'] is True
        assert payload['returned_count'] == 1
        aggregate = payload['rows'][0]
        assert aggregate['patient_id'] == '307'
        assert aggregate['status_id'] == '1049'
        assert aggregate['status_label'] == 'Active'
        assert aggregate['patient']['source_id'] == 'CHART-307'
        assert aggregate['patient']['planned_discharge_date'] == '2026-08-01'
        assert aggregate['total_plan_count'] == 3
        assert aggregate['active_plan_count'] == 2
        assert aggregate['has_multiple_active_plans'] is True
        assert aggregate['latest_created_active_plan_id'] == '12'
        assert aggregate['review_data_status'] == 'unavailable_via_rest_without_known_review_id'
        assert aggregate['next_review_due_source'] == 'unavailable'
        first_plan = aggregate['treatment_plans'][0]
        parsed_endpoint = urlparse(first_plan['endpoint_url'])
        query = parse_qs(parsed_endpoint.query)
        assert parsed_endpoint.path.endswith('/treatment-plans')
        assert query['ClientId'] == ['307']
        assert 'clientId' not in query
        assert first_plan['raw_client_ref'] == '/clients/307'
        assert first_plan['extracted_patient_id'] == '307'
        assert first_plan['join_validated'] is True
        assert first_plan['is_active'] is True
        assert first_plan['is_complete'] is True
        assert first_plan['is_initial_tp'] is True
        assert first_plan['problem_count'] == 1
        assert first_plan['diagnosis_count'] == 1
        assert first_plan['goal_count'] == 1
        assert first_plan['objective_count'] == 1
        assert first_plan['intervention_count'] == 1
        warning_codes = {warning['code'] for warning in aggregate['warnings']}
        assert {'active_plan_with_past_end_date', 'incomplete_active_plan', 'review_data_unavailable'} <= warning_codes


def test_api_configuration_single_patient_production_pull_requires_and_uses_patient_id(app_with_sqlite, monkeypatch):
    # Given: the single-patient production report is requested through the API harness.
    app, _ = app_with_sqlite
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        patch_outbound_httpx(monkeypatch, PatientCenteredTreatmentPlanHarnessHttpxClient)
        headers = saved_client_credentials_headers(client)

        # When: no patient ID is supplied.
        missing = client.post('/api/api-configuration/alleva-quick-pull', headers=headers, json={**base_body(), 'report': 'single_patient_treatment_plans', 'patient_id': ' '})

        # Then: the guard fails before any patient-plan query.
        assert missing.status_code == 200
        assert missing.json()['status'] == 'fail'
        assert missing.json()['category'] == 'missing_patient_id'

        # When: patient_id 307 is supplied.
        pulled = client.post('/api/api-configuration/alleva-quick-pull', headers=headers, json={**base_body(), 'report': 'single_patient_treatment_plans', 'patient_id': '307'})

        # Then: the result is a single aggregate joined by /clients/307.
        assert pulled.status_code == 200
        payload = pulled.json()
        assert payload['status'] == 'ok'
        assert payload['patient_selection'] == 'single'
        assert payload['returned_count'] == 1
        assert payload['rows'][0]['patient_id'] == '307'
        assert payload['rows'][0]['treatment_plans'][0]['raw_client_ref'] == '/clients/307'
        assert payload['rows'][0]['treatment_plans'][0]['join_validated'] is True


def test_alleva_patient_treatment_plan_data_contract_artifacts_exist():
    # Given: Goal 1 requires explicit reviewed data-contract artifacts.
    repo_root = Path(__file__).resolve().parents[2]
    type_contract = repo_root / 'frontend' / 'src' / 'types' / 'allevaTreatmentPlan.ts'
    markdown_contract = repo_root / 'docs' / 'alleva-patient-treatment-plan-data-contract.md'

    # When: the artifacts are read by backend test coverage.
    type_text = type_contract.read_text(encoding='utf-8')
    markdown_text = markdown_contract.read_text(encoding='utf-8')

    # Then: the required interfaces and clarified contract rules are present.
    for interface_name in (
        'AllevaPatientRecord',
        'AllevaPatientStatus',
        'AllevaTreatmentPlanAggregate',
        'AllevaTreatmentPlan',
        'AllevaTreatmentPlanProblem',
        'AllevaTreatmentPlanDiagnosis',
        'AllevaTreatmentPlanBehavioralDefinition',
        'AllevaTreatmentPlanGoal',
        'AllevaTreatmentPlanObjective',
        'AllevaTreatmentPlanIntervention',
        'AllevaTreatmentReviewAvailability',
        'AllevaPatientPlanSyncWarning',
    ):
        assert f'interface {interface_name}' in type_text
    assert 'GET /treatment-plans?ClientId={patient_id}' in markdown_text
    assert 'unavailable_via_rest_without_known_review_id' in markdown_text
