import json
import re
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password
from app.models.models import AppSetting, AuditLog, Role, TreatmentPlanClient, User
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
                    'startDate': '2026-03-03T10:00:00Z',
                    'staffSignatureDate': '2026-03-03',
                    'clientSignature': {'signatureDateTime': '2026-03-03T11:00:00Z'},
                }
            ],
            treatment_reviews_payload=[
                {
                    'id': 701,
                    'clientName': 'Synthetic Client',
                    'createdDated': '2026-03-20T12:00:00Z',
                    'creatorSignatureDate': '2026-03-20',
                    'clientSignatureDate': '2026-03-20',
                    'nextReviewDue': '2026-04-19',
                }
            ],
        )
        db.commit()

        assert summary['upserted_client_count'] == 1
        assert summary['unmapped_treatment_review_count'] == 0
        stored_client = db.execute(select(TreatmentPlanClient).where(TreatmentPlanClient.patient_id == '1001')).scalar_one()
        evaluation = evaluate_client(stored_client, settings_row, evaluation_date=date(2026, 4, 1))
        assert evaluation.status == 'Compliant'
        assert evaluation.next_due_date == '2026-04-19'
        assert evaluation.rule_used == 'TP-REVIEW-30'
        assert any(plan.source_section == 'Alleva REST treatment-reviews' for plan in stored_client.treatment_plans)
    finally:
        db.close()


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

        dashboard = client.get('/api/timeliness/dashboard?evaluation_date=2026-04-22', headers=headers)
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
                'treatment_plan_loc_change_window_days': 3,
                'treatment_plan_loc_change_window_validated': False,
            },
        )
        assert updated.status_code == 200
        payload = updated.json()
        assert payload['llm_api_key_configured'] is True
        assert payload['access_reputation_api_key_configured'] is True
        assert payload['treatment_plan_loc_change_window_days'] == 3
        assert payload['treatment_plan_loc_change_window_validated'] is False

    db = session_local()
    try:
        app_settings = db.execute(select(AppSetting)).scalar_one()
        assert text_secret_is_encrypted(app_settings.llm_api_key)
        assert text_secret_is_encrypted(app_settings.access_reputation_api_key)
    finally:
        db.close()
