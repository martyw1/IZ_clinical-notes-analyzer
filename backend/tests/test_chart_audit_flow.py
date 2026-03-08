from fastapi.testclient import TestClient

from app.core.audit_template import AUDIT_TEMPLATE


def _auth_headers(client: TestClient) -> dict[str, str]:
    login = client.post('/api/auth/login', json={'username': 'admin', 'password': 'r3'})
    assert login.status_code == 200
    return {'Authorization': f"Bearer {login.json()['access_token']}"}


def test_audit_template_and_chart_creation(app_with_sqlite):
    app, _ = app_with_sqlite
    with TestClient(app) as client:
        headers = _auth_headers(client)

        template = client.get('/api/audit-template', headers=headers)
        assert template.status_code == 200
        assert len(template.json()) == 4

        created = client.post(
            '/api/charts',
            headers=headers,
            json={
                'client_name': 'Aegis Test',
                'level_of_care': 'IOP, PHP',
                'admission_date': '04/01/2025',
                'discharge_date': '09/10/2025',
                'primary_clinician': 'Marleigh Johnson',
                'auditor_name': 'admin',
                'other_details': 'Episode spans multiple LOCs.',
                'notes': 'Initial audit created from Alleva walkthrough.',
            },
        )

        assert created.status_code == 200
        payload = created.json()
        assert payload['client_name'] == 'Aegis Test'
        assert payload['auditor_name'] == 'admin'
        assert len(payload['checklist_items']) == len(AUDIT_TEMPLATE)
        assert payload['pending_items'] == len(AUDIT_TEMPLATE)
        assert all(item['status'] == 'pending' for item in payload['checklist_items'])

        listing = client.get('/api/charts', headers=headers)
        assert listing.status_code == 200
        assert listing.json()[0]['pending_items'] == len(AUDIT_TEMPLATE)


def test_chart_update_persists_audit_results(app_with_sqlite):
    app, _ = app_with_sqlite
    with TestClient(app) as client:
        headers = _auth_headers(client)

        created = client.post(
            '/api/charts',
            headers=headers,
            json={
                'client_name': 'Aegis Test',
                'level_of_care': 'Residential',
                'admission_date': '04/01/2025',
                'discharge_date': '09/10/2025',
                'primary_clinician': 'Marleigh Johnson',
                'auditor_name': 'admin',
                'other_details': '',
                'notes': '',
            },
        )
        chart = created.json()

        checklist_items = chart['checklist_items']
        checklist_items[0]['status'] = 'yes'
        checklist_items[0]['evidence_location'] = 'Client Overview'
        checklist_items[0]['evidence_date'] = '04/01/2025'
        checklist_items[1]['status'] = 'no'
        checklist_items[1]['notes'] = 'Primary clinician still missing.'
        checklist_items[2]['status'] = 'na'

        updated = client.put(
            f"/api/charts/{chart['id']}",
            headers=headers,
            json={
                'client_name': chart['client_name'],
                'level_of_care': chart['level_of_care'],
                'admission_date': chart['admission_date'],
                'discharge_date': chart['discharge_date'],
                'primary_clinician': chart['primary_clinician'],
                'auditor_name': chart['auditor_name'],
                'other_details': 'Reviewed after walkthrough import.',
                'notes': 'Two items resolved and one missing clinician assignment.',
                'checklist_items': checklist_items,
            },
        )

        assert updated.status_code == 200
        payload = updated.json()
        assert payload['passed_items'] == 1
        assert payload['failed_items'] == 1
        assert payload['not_applicable_items'] == 1
        assert payload['pending_items'] == len(AUDIT_TEMPLATE) - 3
        assert payload['other_details'] == 'Reviewed after walkthrough import.'

        refreshed = client.get(f"/api/charts/{chart['id']}", headers=headers)
        assert refreshed.status_code == 200
        refreshed_payload = refreshed.json()
        first_item = refreshed_payload['checklist_items'][0]
        second_item = refreshed_payload['checklist_items'][1]
        assert first_item['status'] == 'yes'
        assert first_item['evidence_location'] == 'Client Overview'
        assert second_item['status'] == 'no'
        assert second_item['notes'] == 'Primary clinician still missing.'
