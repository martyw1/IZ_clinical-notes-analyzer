from fastapi.testclient import TestClient

from app.services.treatment_plan_checklist import load_treatment_plan_checklist, validate_treatment_plan_checklist

BOOTSTRAP_ADMIN_PASSWORD = 'r3!@analyzer#123'


def _auth_headers(client: TestClient) -> dict[str, str]:
    login = client.post('/api/auth/login', json={'username': 'admin', 'password': BOOTSTRAP_ADMIN_PASSWORD})
    assert login.status_code == 200
    return {'Authorization': f"Bearer {login.json()['access_token']}"}


def test_treatment_plan_v1_checklist_is_canonical_and_complete():
    checklist = load_treatment_plan_checklist()

    assert validate_treatment_plan_checklist(checklist) == []
    assert checklist['checklist_id'] == 'treatment-plan-v1'
    assert checklist['version'] == '1.2.0'
    assert [step['step'] for step in checklist['steps']] == list(range(1, 43))
    assert checklist['steps'][0]['key'] == 'confirm_correct_client_chart'
    assert checklist['steps'][-1]['key'] == 'use_synthetic_or_approved_non_phi_data'
    assert checklist['loc_change_blocker']['status'] == 'unvalidated'
    assert all(step['manual_override'] is True for step in checklist['steps'])
    assert all(step['override_reason_required'] is True for step in checklist['steps'])
    assert all(step['audit_event'].startswith('treatment_plan.checklist.') for step in checklist['steps'])
    assert all({'status', 'source_evidence', 'finding_message', 'severity', 'reviewer_action', 'override_reason'} <= set(step['export_fields']) for step in checklist['steps'])

    acronym_terms = {item['term'] for item in checklist['acronyms']}
    assert {'API', 'EMR', 'PHI', 'PII', 'OCR', 'LLM', 'TP', 'SUD', 'LOC', 'ASAM', 'SMART'} <= acronym_terms

    status_labels = {item['label'] for item in checklist['review_statuses']}
    assert {
        'Not Reviewed',
        'Ready for Review',
        'In Review',
        'Needs Human Review',
        'Passed',
        'Failed',
        'Missing Required Data',
        'Error',
        'Finalized',
        'Returned for Correction',
        'Approved / Finalized',
        'Conflicting Evidence',
        'Unable to Evaluate',
    } <= status_labels


def test_treatment_plan_checklist_api_is_visible_to_authenticated_users(app_with_sqlite):
    app, _ = app_with_sqlite

    with TestClient(app) as client:
        response = client.get('/api/treatment-plan-checklist', headers=_auth_headers(client))

    assert response.status_code == 200
    payload = response.json()
    assert payload['display_name'] == 'Treatment Plan Checklist Version 1 - 42 Step PRD'
    assert len(payload['steps']) == 42
    assert payload['steps'][33]['key'] == 'require_manual_override_reason'
    assert payload['steps'][33]['override_reason_required'] is True
    assert {item['term'] for item in payload['acronyms']} >= {'API', 'EMR', 'MRN', 'LOC'}


def test_readiness_reports_treatment_plan_checklist(app_with_sqlite):
    app, _ = app_with_sqlite

    with TestClient(app) as client:
        response = client.get('/api/system/readiness', headers=_auth_headers(client))

    assert response.status_code == 200
    checklist_check = next(check for check in response.json()['checks'] if check['name'] == 'treatment_plan_checklist')
    assert checklist_check['status'] == 'ok'
    assert 'steps=42' in checklist_check['detail']
