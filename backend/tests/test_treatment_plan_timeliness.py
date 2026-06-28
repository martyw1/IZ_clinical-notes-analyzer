import json
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password
from app.models.models import AppSetting, AuditLog, Role, TreatmentPlanClient, TreatmentPlanCriterionReview, User
from app.services.alleva_treatment_plan_sync import sync_alleva_rest_payloads
from app.services.timeliness import evaluate_client
from app.services.secure_storage import text_secret_is_encrypted

BOOTSTRAP_ADMIN_PASSWORD = 'r3!@analyzer#123'


def _login_headers(client: TestClient, username: str = 'admin', password: str = BOOTSTRAP_ADMIN_PASSWORD) -> dict[str, str]:
    login = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert login.status_code == 200
    return {'Authorization': f"Bearer {login.json()['access_token']}"}


def _auth_headers(client: TestClient) -> dict[str, str]:
    return _login_headers(client)


def _client_payload(
    patient_id: str = 'PAT-TP-100',
    *,
    loc: str = 'IOP 5',
    review_date: str = '2026-04-02',
    displayed_next_due_date: str = '',
):
    return {
        'patient_id': patient_id,
        'permitted_name': 'Synthetic Client',
        'is_active': True,
        'current_level_of_care': loc,
        'counselor_name': 'Counselor A',
        'admission_date': '2026-02-26',
        'source_evidence': 'Synthetic spreadsheet row',
        'level_of_care_history': [
            {
                'level_of_care': 'PHP',
                'facility': 'Synthetic Facility',
                'effective_date': '2026-02-26',
                'discharge_date': '2026-03-30',
                'source_evidence': 'Synthetic admission LOC',
            },
            {
                'level_of_care': loc,
                'facility': 'Synthetic Facility',
                'effective_date': '2026-03-30',
                'source_evidence': 'Synthetic LOC update',
            },
        ],
        'treatment_plans': [
            {
                'plan_kind': 'initial',
                'document_date': '2026-02-26',
                'staff_signature_date': '2026-02-26',
                'client_signature_date': '2026-02-26',
                'source_evidence': 'Initial Treatment Plan synthetic record',
            },
            {
                'plan_kind': 'master',
                'document_date': '2026-03-03',
                'staff_signature_date': '2026-03-03',
                'client_signature_date': '2026-03-03',
                'source_evidence': 'Master Treatment Plan synthetic record',
            },
            {
                'plan_kind': 'review',
                'document_date': review_date,
                'staff_signature_date': review_date,
                'client_signature_date': '',
                'displayed_next_due_date': displayed_next_due_date,
                'source_evidence': 'Treatment Plan Review synthetic record',
                'source_section': 'Treatment Plan Reviews',
            },
        ],
    }


def _single_loc_client_payload(
    patient_id: str,
    *,
    loc: str = 'PHP',
    review_date: str = '2026-05-01',
    is_active: bool = True,
):
    return {
        'patient_id': patient_id,
        'permitted_name': 'Synthetic Client',
        'is_active': is_active,
        'current_level_of_care': loc,
        'counselor_name': 'Counselor A',
        'admission_date': '2026-04-01',
        'source_evidence': 'Synthetic spreadsheet row',
        'level_of_care_history': [
            {
                'level_of_care': loc,
                'facility': 'Synthetic Facility',
                'effective_date': '2026-04-01',
                'discharge_date': '' if is_active else '2026-05-15',
                'source_evidence': 'Synthetic current LOC row',
            }
        ],
        'treatment_plans': [
            {
                'plan_kind': 'initial',
                'document_date': '2026-04-01',
                'staff_signature_date': '2026-04-01',
                'client_signature_date': '2026-04-01',
                'source_evidence': 'Initial Treatment Plan synthetic record',
            },
            {
                'plan_kind': 'master',
                'document_date': '2026-04-15',
                'staff_signature_date': '2026-04-15',
                'client_signature_date': '2026-04-15',
                'source_evidence': 'Master Treatment Plan synthetic record',
            },
            {
                'plan_kind': 'review',
                'document_date': review_date,
                'staff_signature_date': review_date,
                'client_signature_date': '',
                'source_evidence': 'Treatment Plan Review synthetic record',
                'source_section': 'Treatment Plan Reviews',
            },
        ],
    }


def test_timeliness_dashboard_surfaces_iop_5_loc_anchor_ambiguity(app_with_sqlite):
    app, _ = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        created = client.post('/api/timeliness/clients', headers=headers, json=_client_payload())
        assert created.status_code == 200
        assert created.json()['last_valid_review_date'] == '2026-04-02'

        dashboard = client.get('/api/timeliness/dashboard?evaluation_date=2026-05-27', headers=headers)
        assert dashboard.status_code == 200
        payload = dashboard.json()
        assert payload['total_active_clients'] == 1
        assert payload['urgent'] == 0
        assert payload['needs_review'] == 1
        assert payload['loc_change_window_validated'] is False
        item = payload['items'][0]
        assert item['patient_id'] == 'PAT-TP-100'
        assert item['next_due_date'] == '2026-04-06'
        assert item['days_until_due'] == -51
        assert item['status'] == 'Needs Review'
        assert item['rule_used'] == 'TP-DUE-DATE-CONFLICT'

        detail = client.get(f"/api/timeliness/clients/{item['id']}?evaluation_date=2026-05-27", headers=headers)
        assert detail.status_code == 200
        detail_payload = detail.json()
        assert any(result['rule_id'] == 'TP-LOC-CHANGE-UNVALIDATED' for result in detail_payload['rule_results'])
        assert any(result['rule_id'] == 'TP-DUE-DATE-CONFLICT' for result in detail_payload['rule_results'])
        assert len(detail_payload['level_of_care_history']) == 2
        assert detail_payload['evidence_comparison']['document_next_due_date'] is None
        assert detail_payload['evidence_comparison']['signature_anchor_due_date'] == '2026-06-01'
        assert detail_payload['evidence_comparison']['current_date'] == '2026-05-27'
        assert detail_payload['evidence_comparison']['date_clock_anchor_date'] == '2026-04-02'
        assert detail_payload['evidence_comparison']['date_clock_due_date'] == '2026-06-01'
        assert detail_payload['evidence_comparison']['loc_anchor_due_date'] == '2026-04-06'
        assert detail_payload['evidence_comparison']['loc_change_due_date'] == '2026-04-06'
        assert detail_payload['evidence_comparison']['loc_change_window_days'] == 7
        assert detail_payload['checklist_id'] == 'treatment-plan-v1'
        assert detail_payload['checklist_version'] == '1.2.0'
        assert len(detail_payload['checklist_results']) == 42
        checklist_by_key = {item['key']: item for item in detail_payload['checklist_results']}
        assert checklist_by_key['confirm_correct_client_chart']['status'] == 'Confirmed'
        assert checklist_by_key['confirm_admission_date']['status'] == 'Confirmed'
        assert checklist_by_key['confirm_loc_rule_mapping']['status'] == 'Confirmed'
        assert checklist_by_key['calculate_next_review_due_date']['status'] == 'Due Soon'
        assert checklist_by_key['loc_change_deadline_unresolved']['status'] == 'Needs Review'
        assert checklist_by_key['flag_missing_data_not_compliance']['status'] == 'Missing Data'
        assert checklist_by_key['loc_change_deadline_unresolved']['finding_examples']
        assert checklist_by_key['loc_change_deadline_unresolved']['remediation_suggestions']
        assert checklist_by_key['loc_change_deadline_unresolved']['manual_override_allowed'] is True


def test_timeliness_due_date_conflict_stays_needs_review(app_with_sqlite):
    app, _ = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        created = client.post(
            '/api/timeliness/clients',
            headers=headers,
            json=_client_payload(patient_id='PAT-TP-CONFLICT', displayed_next_due_date='2026-05-29'),
        )
        assert created.status_code == 200

        detail = client.get(f"/api/timeliness/clients/{created.json()['id']}?evaluation_date=2026-05-27", headers=headers)
        assert detail.status_code == 200
        payload = detail.json()
        assert payload['status'] == 'Needs Review'
        assert payload['next_due_date'] == '2026-04-06'
        assert payload['rule_used'] == 'TP-DUE-DATE-CONFLICT'
        assert payload['evidence_comparison']['document_next_due_date'] == '2026-05-29'
        assert payload['evidence_comparison']['signature_anchor_due_date'] == '2026-06-01'
        assert payload['evidence_comparison']['loc_anchor_due_date'] == '2026-04-06'
        assert payload['evidence_comparison']['loc_change_due_date'] == '2026-04-06'
        assert payload['evidence_comparison']['loc_change_window_days'] == 7
        assert 'LOC-change due date is 2026-04-06' in payload['evidence_comparison']['conflict_explanation']
        assert any(result['rule_id'] == 'TP-DUE-DATE-CONFLICT' for result in payload['rule_results'])


@pytest.mark.parametrize(
    ('evaluation_date', 'expected_status', 'expected_days_until_due'),
    [
        ('2026-05-31', 'Urgent', 0),
        ('2026-05-30', 'Urgent', 1),
        ('2026-05-24', 'Due Soon', 7),
        ('2026-05-23', 'Compliant', 8),
        ('2026-06-01', 'Overdue', -1),
    ],
)
def test_timeliness_due_date_boundary_windows(app_with_sqlite, evaluation_date, expected_status, expected_days_until_due):
    app, _ = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        created = client.post('/api/timeliness/clients', headers=headers, json=_single_loc_client_payload(patient_id=f'PAT-BOUNDARY-{evaluation_date}'))
        assert created.status_code == 200

        detail = client.get(f"/api/timeliness/clients/{created.json()['id']}?evaluation_date={evaluation_date}", headers=headers)
        assert detail.status_code == 200
        payload = detail.json()
        assert payload['next_due_date'] == '2026-05-31'
        assert payload['days_until_due'] == expected_days_until_due
        assert payload['status'] == expected_status


@pytest.mark.parametrize(
    ('loc', 'evaluation_date', 'expected_due_date'),
    [
        ('PHP', '2026-05-31', '2026-05-31'),
        ('IOP 5', '2026-06-30', '2026-06-30'),
    ],
)
def test_timeliness_exact_30_and_60_day_boundaries_are_not_overdue(app_with_sqlite, loc, evaluation_date, expected_due_date):
    app, _ = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        created = client.post(
            '/api/timeliness/clients',
            headers=headers,
            json=_single_loc_client_payload(patient_id=f'PAT-{loc.replace(" ", "-")}-BOUNDARY', loc=loc),
        )
        assert created.status_code == 200

        detail = client.get(f"/api/timeliness/clients/{created.json()['id']}?evaluation_date={evaluation_date}", headers=headers)
        assert detail.status_code == 200
        payload = detail.json()
        assert payload['next_due_date'] == expected_due_date
        assert payload['days_until_due'] == 0
        assert payload['status'] == 'Urgent'


def test_inactive_clients_are_excluded_from_active_timeliness_dashboard(app_with_sqlite):
    app, _ = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        created = client.post('/api/timeliness/clients', headers=headers, json=_single_loc_client_payload(patient_id='PAT-INACTIVE-TP', is_active=False))
        assert created.status_code == 200

        dashboard = client.get('/api/timeliness/dashboard?evaluation_date=2026-05-31', headers=headers)
        assert dashboard.status_code == 200
        payload = dashboard.json()
        assert payload['total_active_clients'] == 0
        assert payload['items'] == []


def test_timeliness_criterion_reviews_persist_and_are_audited_without_comments(app_with_sqlite):
    app, session_local = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        created = client.post('/api/timeliness/clients', headers=headers, json=_single_loc_client_payload(patient_id='PAT-CRITERIA-100'))
        assert created.status_code == 200
        client_id = created.json()['id']

        updated = client.put(
            f'/api/timeliness/clients/{client_id}/criterion-reviews?evaluation_date=2026-05-31',
            headers=headers,
            json=[
                {
                    'criterion_key': 'calculate_next_review_due_date',
                    'status': 'Needs Update',
                    'comment': 'Synthetic counselor should update the next review due date.',
                },
                {
                    'criterion_key': 'confirm_client_signature_status',
                    'status': 'Needs Review',
                    'comment': 'Synthetic manager should confirm whether client signature is applicable.',
                },
            ],
        )
        assert updated.status_code == 200
        checklist_by_key = {item['key']: item for item in updated.json()['checklist_results']}
        assert checklist_by_key['calculate_next_review_due_date']['manager_status'] == 'Needs Update'
        assert checklist_by_key['calculate_next_review_due_date']['manager_comment'] == 'Synthetic counselor should update the next review due date.'
        assert checklist_by_key['confirm_client_signature_status']['manager_status'] == 'Needs Review'

        reloaded = client.get(f'/api/timeliness/clients/{client_id}?evaluation_date=2026-05-31', headers=headers)
        assert reloaded.status_code == 200
        reloaded_by_key = {item['key']: item for item in reloaded.json()['checklist_results']}
        assert reloaded_by_key['calculate_next_review_due_date']['manager_status'] == 'Needs Update'
        assert reloaded_by_key['calculate_next_review_due_date']['manager_comment']

    db = session_local()
    try:
        assert db.execute(select(TreatmentPlanCriterionReview).where(TreatmentPlanCriterionReview.criterion_key == 'calculate_next_review_due_date')).scalar_one()
        audit = db.execute(select(AuditLog).where(AuditLog.action == 'timeliness.criterion_reviews.updated')).scalar_one()
        assert audit.patient_id == 'PAT-CRITERIA-100'
        assert 'Synthetic counselor should update' not in audit.details
        assert 'criterion_count' in audit.details
    finally:
        db.close()


def test_api_style_treatment_plan_repull_updates_record_and_reevaluates(app_with_sqlite):
    app, _ = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        initial = _client_payload(patient_id='PAT-TP-REPULL', review_date='2026-04-02')
        initial['permitted_name'] = ''
        created = client.post('/api/timeliness/clients', headers=headers, json=initial)
        assert created.status_code == 200
        assert re.fullmatch(r'no-name-found_\d{4}-\d{2}-\d{2}_\d{6}', created.json()['permitted_name'])

        first_dashboard = client.get('/api/timeliness/dashboard?evaluation_date=2026-05-27', headers=headers)
        assert first_dashboard.status_code == 200
        first_item = first_dashboard.json()['items'][0]
        assert first_item['patient_id'] == 'PAT-TP-REPULL'
        assert first_item['next_due_date'] == '2026-04-06'
        assert first_item['status'] == 'Needs Review'

        updated_payload = _client_payload(patient_id='PAT-TP-REPULL', loc='PHP', review_date='2026-05-20')
        updated_payload['permitted_name'] = ''
        updated_payload['level_of_care_history'] = [
            {
                'level_of_care': 'PHP',
                'facility': 'Synthetic Facility',
                'effective_date': '2026-02-26',
                'source_evidence': 'Synthetic API re-pull LOC',
            }
        ]
        updated = client.post('/api/timeliness/clients', headers=headers, json=updated_payload)
        assert updated.status_code == 200
        assert updated.json()['last_valid_review_date'] == '2026-05-20'

        second_dashboard = client.get('/api/timeliness/dashboard?evaluation_date=2026-05-27', headers=headers)
        assert second_dashboard.status_code == 200
        second_item = second_dashboard.json()['items'][0]
        assert second_item['patient_id'] == 'PAT-TP-REPULL'
        assert second_item['next_due_date'] == '2026-06-19'
        assert second_item['status'] == 'Compliant'
        assert second_item['rule_used'] == 'TP-REVIEW-30'


def test_alleva_rest_payloads_sync_into_r3_timeliness_engine(app_with_sqlite):
    app, session_local = app_with_sqlite
    with TestClient(app):
        pass

    db = session_local()
    try:
        settings_row = db.execute(select(AppSetting).order_by(AppSetting.id.asc())).scalars().first()

        def detail_fetcher(raw_plan):
            if raw_plan.get('id') != 502:
                return None
            return {
                'id': 502,
                'problems': [
                    {
                        'diagnoses': [{'code': 'F10.20'}],
                        'goals': [
                            {
                                'objectives': [
                                    {
                                        'interventions': [{'description': 'Synthetic intervention'}],
                                    }
                                ],
                            }
                        ],
                    }
                ],
                'guardianSignature': {'signatureDateTime': '2026-03-03T12:00:00Z'},
            }

        summary = sync_alleva_rest_payloads(
            db,
            clients_payload=[
                {
                    'id': 101,
                    'clientId': 1001,
                    'name': {'clientFullName': 'Synthetic Client'},
                    'levelOfCare': 'PHP',
                    'admissionDateTime': '2026-02-26T09:00:00Z',
                    'facilityName': 'Synthetic Facility',
                    'primaryClinicians': 'Synthetic Clinician',
                }
            ],
            treatment_plans_payload=[
                {
                    'id': 501,
                    'client': {'id': 101},
                    'isInitialTP': True,
                    'isComplete': True,
                    'startDate': '2026-02-26T10:00:00Z',
                    'staffSignatureDate': '2026-02-26',
                    'clientSignature': {'signatureDateTime': '2026-02-26T11:00:00Z'},
                },
                {
                    'id': 502,
                    'client': {'id': 101},
                    'isInitialTP': False,
                    'isComplete': True,
                    'isActive': True,
                    'startDate': '2026-03-03T10:00:00Z',
                    'staffSignatureDate': '2026-03-03',
                    'clientSignature': {'signatureDateTime': '2026-03-03T11:00:00Z'},
                }
            ],
            treatment_reviews_payload=[
                {
                    'id': 701,
                    'client': {'id': 101, 'clientId': 1001},
                    'createdDate': '2026-03-20T12:00:00Z',
                    'staffSignatureDate': '2026-03-20',
                    'clientSignatureDate': '2026-03-20',
                    'nextReviewDueDate': '2026-04-19',
                }
            ],
            plan_detail_fetcher=detail_fetcher,
            detail_fetch_limit=10,
        )
        db.commit()

        assert summary['upserted_client_count'] == 1
        assert summary['unmapped_treatment_review_count'] == 0
        assert summary['current_plan_selected_count'] == 1
        assert summary['detail_fetch_attempt_count'] == 1
        assert summary['detail_fetch_success_count'] == 1
        stored_client = db.execute(select(TreatmentPlanClient).where(TreatmentPlanClient.patient_id == '1001')).scalar_one()
        current_plan = next(plan for plan in stored_client.treatment_plans if plan.id == stored_client.current_plan_record_id)
        assert current_plan.source_document_id == '502'
        assert current_plan.detail_fetched is True
        assert current_plan.problem_count == 1
        assert current_plan.diagnosis_count == 1
        assert current_plan.goal_count == 1
        assert current_plan.objective_count == 1
        assert current_plan.intervention_count == 1
        assert current_plan.has_guardian_signature is True
        evaluation = evaluate_client(stored_client, settings_row, evaluation_date=date(2026, 4, 1))
        assert evaluation.status == 'Compliant'
        assert evaluation.next_due_date == '2026-04-19'
        assert evaluation.rule_used == 'TP-REVIEW-30'
        assert any(plan.source_section == 'Alleva REST treatment-reviews' for plan in stored_client.treatment_plans)
    finally:
        db.close()


def test_alleva_rest_sync_redacts_patient_names_by_default_and_requires_opt_in(app_with_sqlite):
    app, session_local = app_with_sqlite
    with TestClient(app):
        pass

    db = session_local()
    try:
        base_clients = [
            {
                'id': 1101,
                'clientId': 'PAT-NAME-REDAC',
                'name': {'clientFullName': 'Synthetic Import Name'},
                'status': 'Active',
                'isClient': True,
                'admissionDateTime': '2026-02-26T09:00:00Z',
                'levelOfCare': 'PHP',
            }
        ]
        base_plans = [
            {
                'id': 1501,
                'client': {'id': 1101, 'clientId': 'PAT-NAME-REDAC'},
                'isInitialTP': False,
                'isActive': True,
                'isComplete': True,
                'startDate': '2026-03-03T10:00:00Z',
                'staffSignatureDate': '2026-03-03',
                'clientSignature': {'signatureDateTime': '2026-03-03T11:00:00Z'},
            }
        ]

        sync_alleva_rest_payloads(
            db,
            clients_payload=base_clients,
            treatment_plans_payload=base_plans,
            treatment_reviews_payload=[],
        )
        db.commit()
        stored_client = db.execute(select(TreatmentPlanClient).where(TreatmentPlanClient.patient_id == 'PAT-NAME-REDAC')).scalar_one()
        assert re.fullmatch(r'no-name-found_\d{4}-\d{2}-\d{2}_\d{6}', stored_client.permitted_name)
        assert stored_client.permitted_name != 'Synthetic Import Name'

        sync_alleva_rest_payloads(
            db,
            clients_payload=base_clients,
            treatment_plans_payload=base_plans,
            treatment_reviews_payload=[],
            patient_name_import_enabled=True,
        )
        db.commit()
        stored_client = db.execute(select(TreatmentPlanClient).where(TreatmentPlanClient.patient_id == 'PAT-NAME-REDAC')).scalar_one()
        assert stored_client.permitted_name == 'Synthetic Import Name'
    finally:
        db.close()


def test_alleva_rest_sync_keeps_active_client_with_discharge_conflict_and_aggregate_detail(app_with_sqlite):
    app, session_local = app_with_sqlite
    with TestClient(app):
        pass

    db = session_local()
    try:
        summary = sync_alleva_rest_payloads(
            db,
            clients_payload=[
                {
                    'id': 201,
                    'clientId': 'PAT-ACTIVE-DISCH',
                    'name': {'clientFullName': 'Synthetic Active Conflict'},
                    'status': 'Active',
                    'isClient': True,
                    'admissionDateTime': '2026-04-01T09:00:00Z',
                    'dischargeDateTime': '2026-06-01T09:00:00Z',
                    'levelOfCare': 'PHP',
                }
            ],
            treatment_plans_payload=[
                {
                    'id': 801,
                    'client': {'id': 201, 'clientId': 'PAT-ACTIVE-DISCH'},
                    'isInitialTP': False,
                    'isActive': True,
                    'isComplete': True,
                    'startDate': '2026-05-01T10:00:00Z',
                    'staffSignatureDate': '2026-05-01',
                    'clientSignature': {'signatureDateTime': '2026-05-01T11:00:00Z'},
                }
            ],
            treatment_reviews_payload=[],
            plan_detail_fetcher=lambda _raw: {
                'problems': [
                    {
                        'diagnoses': [{'code': 'F33.1'}],
                        'goals': [{'objectives': [{'interventions': [{'description': 'Synthetic intervention'}]}]}],
                    }
                ],
            },
            detail_fetch_limit=5,
        )
        db.commit()

        assert summary['active_client_count'] == 1
        assert summary['upserted_client_count'] == 1
        assert summary['current_plan_selected_count'] == 1
        assert summary['detail_fetch_success_count'] == 1
        stored_client = db.execute(select(TreatmentPlanClient).where(TreatmentPlanClient.patient_id == 'PAT-ACTIVE-DISCH')).scalar_one()
        assert stored_client.is_active is True
        assert stored_client.discharge_conflict is True
        assert 'active_status_discharge_field_conflict' in json.loads(stored_client.data_quality_warnings)
        assert stored_client.current_plan_record_id is not None
        current_plan = next(plan for plan in stored_client.treatment_plans if plan.id == stored_client.current_plan_record_id)
        assert current_plan.detail_fetched is True
        assert current_plan.problem_count == 1
        assert current_plan.diagnosis_count == 1
        assert current_plan.goal_count == 1
        assert current_plan.objective_count == 1
        assert current_plan.intervention_count == 1
        client_id = stored_client.id
    finally:
        db.close()

    with TestClient(app) as client:
        headers = _auth_headers(client)
        aggregate = client.get(f'/api/timeliness/clients/{client_id}/treatment-plan', headers=headers)
        assert aggregate.status_code == 200
        payload = aggregate.json()
        assert payload['patient_id'] == 'PAT-ACTIVE-DISCH'
        assert payload['current_plan']['source_document_id'] == '801'
        assert payload['current_plan']['problem_count'] == 1
        assert payload['current_plan']['detail_fetched'] is True
        assert 'active_status_discharge_field_conflict' in payload['data_quality_warnings']


def test_alleva_detail_sample_fetches_current_plan_content_counts(app_with_sqlite, monkeypatch):
    app, session_local = app_with_sqlite
    detail_calls = []

    def fake_token_request(**kwargs):
        assert kwargs['client_secret'] == 'alleva-rest-secret'
        return {'status': 'ok', 'token_type': 'Bearer'}, 'mock-access-token'

    class FakeDetailResult:
        def __init__(self, path, records):
            self.path = path
            self.records = records
            self.error = None

        def diagnostics(self):
            return {
                'endpoint': self.path,
                'record_count': len(self.records),
                'complete': True,
                'pages': [],
            }

    def fake_fetch_detail(**kwargs):
        detail_calls.append(kwargs)
        assert kwargs['bearer_token'] == 'mock-access-token'
        return FakeDetailResult(
            kwargs['path'],
            [
                {
                    'id': 'TP 901',
                    'problems': [
                        {
                            'diagnoses': [{'code': 'F10.20'}],
                            'goals': [{'objectives': [{'interventions': [{'description': 'Synthetic intervention'}]}]}],
                        }
                    ],
                }
            ],
        )

    monkeypatch.setattr('app.api.routes.request_client_credentials_token', fake_token_request)
    monkeypatch.setattr('app.api.routes.fetch_alleva_detail', fake_fetch_detail)

    with TestClient(app) as client:
        headers = _auth_headers(client)
        saved_settings = client.patch(
            '/api/settings',
            headers=headers,
            json={
                'alleva_api_base_url': 'https://api.example.test',
                'api_oauth_token_url': 'https://authorization.example.test/connect/token',
                'api_client_id': 'alleva-rest-client',
                'api_client_secret': 'alleva-rest-secret',
                'api_token_auth_style': 'body',
            },
        )
        assert saved_settings.status_code == 200

        db = session_local()
        try:
            sync_alleva_rest_payloads(
                db,
                clients_payload=[
                    {
                        'id': 301,
                        'clientId': 'PAT-SAMPLE',
                        'status': 'Active',
                        'isClient': True,
                        'admissionDateTime': '2026-04-01T09:00:00Z',
                        'levelOfCare': 'PHP',
                    }
                ],
                treatment_plans_payload=[
                    {
                        'id': 'TP 901',
                        'client': {'id': 301, 'clientId': 'PAT-SAMPLE'},
                        'isInitialTP': False,
                        'isActive': True,
                        'isComplete': True,
                        'startDate': '2026-05-01T10:00:00Z',
                        'staffSignatureDate': '2026-05-01',
                        'clientSignature': {'signatureDateTime': '2026-05-01T11:00:00Z'},
                    }
                ],
                treatment_reviews_payload=[],
            )
            db.commit()
        finally:
            db.close()

        sample = client.post('/api/emr/alleva/sync/detail-sample', headers=headers, json={'patient_ids': ['PAT-SAMPLE']})
        assert sample.status_code == 200
        payload = sample.json()
        assert payload['status'] == 'ok'
        assert payload['requested_count'] == 1
        result = payload['results'][0]
        assert result['status'] == 'ok'
        assert result['treatment_plan_id'] == 'TP 901'
        assert result['endpoint'] == '/treatment-plans/TP%20901'
        assert result['content_counts'] == {
            'problem_count': 1,
            'diagnosis_count': 1,
            'goal_count': 1,
            'objective_count': 1,
            'intervention_count': 1,
        }
        assert detail_calls[0]['path'] == '/treatment-plans/TP%20901'


def test_timeliness_missing_data_and_manual_override_are_audited(app_with_sqlite):
    app, _ = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        created = client.post(
            '/api/timeliness/clients',
            headers=headers,
            json={
                'patient_id': 'PAT-TP-MISSING',
                'is_active': True,
                'current_level_of_care': '',
                'admission_date': '',
                'treatment_plans': [],
            },
        )
        assert created.status_code == 200
        assert created.json()['status'] == 'Missing Data'

        override = client.post(
            f"/api/timeliness/clients/{created.json()['id']}/overrides",
            headers=headers,
            json={
                'field_name': 'status',
                'original_value': 'Missing Data',
                'new_value': 'Needs Review',
                'reason': 'Synthetic manager review note.',
                'affected_rule': 'TP-MISSING-LOC',
            },
        )
        assert override.status_code == 200
        assert override.json()['affected_rule'] == 'TP-MISSING-LOC'

        detail = client.get(f"/api/timeliness/clients/{created.json()['id']}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()['overrides'][0]['reason'] == 'Synthetic manager review note.'
        assert any(log['action'] == 'timeliness.override.created' for log in detail.json()['audit_history'])


def test_counselor_override_attempt_is_blocked_and_logged(app_with_sqlite):
    app, session_local = app_with_sqlite

    with TestClient(app) as client:
        admin_headers = _auth_headers(client)
        created = client.post('/api/timeliness/clients', headers=admin_headers, json=_client_payload(patient_id='PAT-TP-DENIED'))
        assert created.status_code == 200

        db = session_local()
        try:
            db.add(
                User(
                    username='counselor-denied',
                    full_name='Synthetic Counselor',
                    password_hash=hash_password('counselor-pass-1234'),
                    role=Role.counselor,
                    is_active=True,
                    must_reset_password=False,
                )
            )
            db.commit()
        finally:
            db.close()

        counselor_headers = _login_headers(client, 'counselor-denied', 'counselor-pass-1234')
        detail = client.get(f"/api/timeliness/clients/{created.json()['id']}", headers=counselor_headers)
        assert detail.status_code == 200
        assert len(detail.json()['checklist_results']) == 42
        denied = client.post(
            f"/api/timeliness/clients/{created.json()['id']}/overrides",
            headers=counselor_headers,
            json={
                'field_name': 'status',
                'original_value': 'Urgent',
                'new_value': 'Needs Review',
                'reason': 'Synthetic counselor attempt.',
                'affected_rule': 'TP-REVIEW-60',
            },
        )
        assert denied.status_code == 403

    db = session_local()
    try:
        audit = db.execute(select(AuditLog).where(AuditLog.action == 'timeliness.override.denied')).scalar_one()
        assert audit.patient_id == 'PAT-TP-DENIED'
        assert audit.outcome_status == 'failure'
        assert 'Synthetic counselor attempt' not in audit.details
    finally:
        db.close()


def test_patient_note_upload_syncs_treatment_plan_metadata(app_with_sqlite):
    app, session_local = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        data = {
            'patient_id': 'PAT-UPLOAD-TP',
            'upload_mode': 'initial',
            'level_of_care': 'PHP',
            'admission_date': '2026-02-26',
            'primary_clinician': 'Counselor B',
            'file_manifest': json.dumps(
                [
                    {
                        'client_file_name': 'initial.txt',
                        'document_label': 'Initial Treatment Plan',
                        'alleva_bucket': 'custom_forms',
                        'document_type': 'initial_treatment_plan',
                        'completion_status': 'completed',
                        'client_signed': True,
                        'staff_signed': True,
                        'document_date': '2026-02-26',
                        'description': 'Synthetic initial treatment plan.',
                    },
                    {
                        'client_file_name': 'master.txt',
                        'document_label': 'Master Treatment Plan',
                        'alleva_bucket': 'custom_forms',
                        'document_type': 'master_treatment_plan',
                        'completion_status': 'completed',
                        'client_signed': True,
                        'staff_signed': True,
                        'document_date': '2026-03-03',
                        'description': 'Synthetic master treatment plan.',
                    },
                    {
                        'client_file_name': 'review.txt',
                        'document_label': 'Treatment Plan Review',
                        'alleva_bucket': 'custom_forms',
                        'document_type': 'treatment_plan_review',
                        'completion_status': 'completed',
                        'client_signed': False,
                        'staff_signed': True,
                        'document_date': '2026-04-02',
                        'description': 'Synthetic treatment plan review.',
                    },
                ]
            ),
        }
        uploaded = client.post(
            '/api/patient-note-sets',
            headers=headers,
            data=data,
            files=[
                ('files', ('initial.txt', b'Synthetic initial treatment plan.', 'text/plain')),
                ('files', ('master.txt', b'Synthetic master treatment plan.', 'text/plain')),
                ('files', ('review.txt', b'Synthetic treatment plan review.', 'text/plain')),
            ],
        )
        assert uploaded.status_code == 200

        dashboard = client.get('/api/timeliness/dashboard?evaluation_date=2026-04-25', headers=headers)
        assert dashboard.status_code == 200
        item = dashboard.json()['items'][0]
        assert item['patient_id'] == 'PAT-UPLOAD-TP'
        assert item['last_valid_review_date'] == '2026-04-02'
        assert item['next_due_date'] == '2026-05-02'
        assert item['status'] == 'Due Soon'

    db = session_local()
    try:
        stored_client = db.execute(select(TreatmentPlanClient).where(TreatmentPlanClient.patient_id == 'PAT-UPLOAD-TP')).scalar_one()
        assert stored_client.current_level_of_care == 'PHP'
    finally:
        db.close()


def test_settings_api_encrypts_saved_api_keys_and_exposes_loc_blocker(app_with_sqlite):
    app, session_local = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        updated = client.patch(
            '/api/settings',
            headers=headers,
            json={
                'llm_api_key': 'sk-synthetic-test',
                'access_reputation_api_key': 'rep-synthetic-test',
                'alleva_treatment_plan_patient_name_import_enabled': True,
                'alleva_treatment_plan_name_join_fallback_enabled': True,
                'treatment_plan_loc_change_window_days': 3,
                'treatment_plan_loc_change_window_validated': False,
            },
        )
        assert updated.status_code == 200
        payload = updated.json()
        assert payload['llm_api_key_configured'] is True
        assert payload['access_reputation_api_key_configured'] is True
        assert payload['alleva_treatment_plan_patient_name_import_enabled'] is True
        assert payload['alleva_treatment_plan_name_join_fallback_enabled'] is True
        assert payload['treatment_plan_loc_change_window_days'] == 3
        assert payload['treatment_plan_loc_change_window_validated'] is False
        assert payload['alleva_treatment_plan_sync_on_startup'] is False

    db = session_local()
    try:
        app_settings = db.execute(select(AppSetting)).scalar_one()
        assert text_secret_is_encrypted(app_settings.llm_api_key)
        assert text_secret_is_encrypted(app_settings.access_reputation_api_key)
        assert app_settings.alleva_treatment_plan_patient_name_import_enabled is True
        assert app_settings.alleva_treatment_plan_name_join_fallback_enabled is True
    finally:
        db.close()


def test_settings_save_with_patient_name_import_off_redacts_existing_alleva_names(app_with_sqlite):
    app, session_local = app_with_sqlite
    with TestClient(app):
        pass

    db = session_local()
    try:
        sync_alleva_rest_payloads(
            db,
            clients_payload=[
                {
                    'id': 9101,
                    'clientId': 'PAT-REDACT-SAVE',
                    'name': {'clientFullName': 'Synthetic Existing Name'},
                    'status': 'Active',
                    'isClient': True,
                    'admissionDateTime': '2026-02-26T09:00:00Z',
                    'levelOfCare': 'PHP',
                }
            ],
            treatment_plans_payload=[],
            treatment_reviews_payload=[],
            patient_name_import_enabled=True,
        )
        db.commit()
        stored_client = db.execute(select(TreatmentPlanClient).where(TreatmentPlanClient.patient_id == 'PAT-REDACT-SAVE')).scalar_one()
        assert stored_client.permitted_name == 'Synthetic Existing Name'
    finally:
        db.close()

    with TestClient(app) as client:
        headers = _auth_headers(client)
        response = client.patch(
            '/api/settings',
            headers=headers,
            json={'alleva_treatment_plan_patient_name_import_enabled': False},
        )
        assert response.status_code == 200
        assert response.json()['alleva_treatment_plan_patient_name_import_enabled'] is False

    db = session_local()
    try:
        stored_client = db.execute(select(TreatmentPlanClient).where(TreatmentPlanClient.patient_id == 'PAT-REDACT-SAVE')).scalar_one()
        assert re.fullmatch(r'no-name-found_\d{4}-\d{2}-\d{2}_\d{6}', stored_client.permitted_name)
    finally:
        db.close()
