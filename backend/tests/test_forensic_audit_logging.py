import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.models import AuditLog


def _auth_headers(client: TestClient) -> dict[str, str]:
    login = client.post('/api/auth/login', json={'username': 'admin', 'password': 'r3'})
    assert login.status_code == 200
    return {'Authorization': f"Bearer {login.json()['access_token']}"}


def test_chart_changes_emit_forensic_audit_records(app_with_sqlite):
    app, session_local = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        created = client.post(
            '/api/charts',
            headers=headers,
            json={
                'patient_id': 'PAT-001',
                'client_name': 'Patient-001',
                'level_of_care': 'Residential',
                'admission_date': '04/01/2025',
                'discharge_date': '09/10/2025',
                'primary_clinician': 'Clinician A',
                'auditor_name': 'admin',
                'other_details': '',
                'notes': 'Initial draft.',
            },
        )
        assert created.status_code == 200
        chart_id = created.json()['id']

        checklist_items = created.json()['checklist_items']
        checklist_items[0]['status'] = 'yes'
        checklist_items[0]['evidence_location'] = 'Client Overview'

        updated = client.put(
            f'/api/charts/{chart_id}',
            headers=headers,
            json={
                'patient_id': 'PAT-001',
                'client_name': 'Patient-001',
                'level_of_care': 'Residential',
                'admission_date': '04/01/2025',
                'discharge_date': '09/10/2025',
                'primary_clinician': 'Clinician B',
                'auditor_name': 'admin',
                'other_details': 'Follow-up review.',
                'notes': 'Updated after verification.',
                'checklist_items': checklist_items,
            },
        )
        assert updated.status_code == 200

    db = session_local()
    try:
        logs = list(db.execute(select(AuditLog).order_by(AuditLog.id.asc())).scalars().all())
        assert logs

        http_log = next(log for log in logs if log.action == 'http.request.completed' and log.request_path == '/api/charts')
        assert http_log.source_ip is not None
        assert http_log.request_id
        assert http_log.correlation_id
        assert http_log.http_status_code == 200
        assert http_log.cef_payload.startswith('CEF:0|')
        assert '"resourceType":"AuditEvent"' in http_log.fhir_audit_event

        insert_log = next(
            log for log in logs if log.action == 'data.insert.commit' and log.target_entity_type == 'chart' and log.target_entity_id == str(chart_id)
        )
        assert insert_log.before_state is None
        assert insert_log.after_state is not None
        assert '"patient_id":"PAT-001"' in insert_log.after_state
        assert '"client_name":"Patient-001"' in insert_log.after_state

        update_log = next(
            log for log in logs if log.action == 'data.update.commit' and log.target_entity_type == 'chart' and log.target_entity_id == str(chart_id)
        )
        diff_state = json.loads(update_log.diff_state or '{}')
        assert 'primary_clinician' in diff_state
        assert diff_state['primary_clinician']['before'] == 'Clinician A'
        assert diff_state['primary_clinician']['after'] == 'Clinician B'
        assert update_log.patient_id == 'PAT-001'
        assert update_log.route_template == '/api/charts/{chart_id}'
        assert update_log.actor_username == 'admin'
    finally:
        db.close()


def test_audit_log_endpoint_returns_enriched_records(app_with_sqlite):
    app, session_local = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        response = client.get('/api/audit/logs', headers=headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload
        first_record = payload[0]
        assert 'cef_payload' in first_record
        assert 'fhir_audit_event' in first_record
        assert 'event_category' in first_record

    db = session_local()
    try:
        read_log = db.execute(select(AuditLog).where(AuditLog.action == 'audit.logs.read')).scalar_one_or_none()
        assert read_log is not None
        assert read_log.event_category == 'forensic_access'
    finally:
        db.close()
