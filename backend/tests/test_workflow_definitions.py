from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.models import AuditLog

BOOTSTRAP_ADMIN_PASSWORD = 'r3!@analyzer#123'


def _auth_headers(client: TestClient) -> dict[str, str]:
    login = client.post('/api/auth/login', json={'username': 'admin', 'password': BOOTSTRAP_ADMIN_PASSWORD})
    assert login.status_code == 200
    return {'Authorization': f"Bearer {login.json()['access_token']}"}


def _login_headers(client: TestClient, username: str, password: str) -> dict[str, str]:
    login = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert login.status_code == 200
    if login.json().get('must_reset_password'):
        reset = client.post(
            '/api/auth/reset-password',
            json={'new_password': password},
            headers={'Authorization': f"Bearer {login.json()['access_token']}"},
        )
        assert reset.status_code == 200
        login = client.post('/api/auth/login', json={'username': username, 'password': password})
        assert login.status_code == 200
    return {'Authorization': f"Bearer {login.json()['access_token']}"}


def _workflow_payload(key: str = 'treatment_plan_followup') -> dict[str, object]:
    return {
        'workflow_key': key,
        'display_name': 'Treatment Plan Follow-up',
        'description': 'Synthetic workflow profile for due-date follow-up.',
        'category': 'treatment_plan',
        'initial_version': {
            'definition_snapshot': {
                'steps': [
                    {'key': 'review_due_date', 'label': 'Review due date'},
                    {'key': 'office_manager_approval', 'label': 'Office manager approval'},
                ],
                'owner_roles': ['admin', 'manager'],
            },
            'transition_rules': [
                {'from': 'draft', 'to': 'ready_for_review', 'roles': ['admin']},
                {'from': 'ready_for_review', 'to': 'published', 'roles': ['admin', 'manager']},
            ],
            'version_notes': 'Initial synthetic workflow definition.',
        },
    }


def test_admin_can_create_version_publish_and_archive_workflow_definition(app_with_sqlite):
    app, session_local = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        created = client.post('/api/workflow-definitions', headers=headers, json=_workflow_payload())
        assert created.status_code == 200
        definition = created.json()
        assert definition['workflow_key'] == 'treatment_plan_followup'
        assert definition['current_version_id'] is None
        assert definition['versions'][0]['version'] == 1
        assert definition['versions'][0]['status'] == 'draft'

        listed = client.get('/api/workflow-definitions', headers=headers)
        assert listed.status_code == 200
        listed_keys = {item['workflow_key'] for item in listed.json()}
        assert 'treatment_plan_timeliness' in listed_keys
        assert 'treatment_plan_followup' in listed_keys

        first_version_id = definition['versions'][0]['id']
        published_first = client.post(f"/api/workflow-definitions/{definition['id']}/versions/{first_version_id}/publish", headers=headers)
        assert published_first.status_code == 200
        assert published_first.json()['current_version_id'] == first_version_id
        assert published_first.json()['current_version']['status'] == 'published'

        new_version = client.post(
            f"/api/workflow-definitions/{definition['id']}/versions",
            headers=headers,
            json={
                'definition_snapshot': {
                    'steps': [
                        {'key': 'review_due_date', 'label': 'Review due date'},
                        {'key': 'escalation', 'label': 'Escalation'},
                    ]
                },
                'transition_rules': [{'from': 'ready_for_review', 'to': 'escalated', 'roles': ['manager']}],
                'version_notes': 'Adds manager escalation.',
            },
        )
        assert new_version.status_code == 200
        second_version_id = new_version.json()['id']
        assert new_version.json()['version'] == 2

        updated_version = client.patch(
            f"/api/workflow-definitions/{definition['id']}/versions/{second_version_id}",
            headers=headers,
            json={
                'definition_snapshot': {
                    'steps': [
                        {'key': 'review_due_date', 'label': 'Review due date'},
                        {'key': 'escalation', 'label': 'Escalation'},
                        {'key': 'close', 'label': 'Close'},
                    ]
                },
                'transition_rules': [{'from': 'escalated', 'to': 'closed', 'roles': ['admin']}],
                'version_notes': 'Adds close step.',
            },
        )
        assert updated_version.status_code == 200
        assert updated_version.json()['definition_snapshot']['steps'][-1]['key'] == 'close'

        published_second = client.post(f"/api/workflow-definitions/{definition['id']}/versions/{second_version_id}/publish", headers=headers)
        assert published_second.status_code == 200
        payload = published_second.json()
        assert payload['current_version_id'] == second_version_id
        version_statuses = {version['version']: version['status'] for version in payload['versions']}
        assert version_statuses == {1: 'archived', 2: 'published'}

        edit_published = client.patch(
            f"/api/workflow-definitions/{definition['id']}/versions/{second_version_id}",
            headers=headers,
            json={'definition_snapshot': {}, 'transition_rules': [], 'version_notes': 'Blocked edit.'},
        )
        assert edit_published.status_code == 400

        archived = client.post(f"/api/workflow-definitions/{definition['id']}/archive", headers=headers)
        assert archived.status_code == 200
        assert archived.json()['is_active'] is False
        assert archived.json()['current_version']['status'] == 'archived'

        active_only = client.get('/api/workflow-definitions', headers=headers)
        assert active_only.status_code == 200
        assert [item['workflow_key'] for item in active_only.json()] == ['treatment_plan_timeliness']

        include_archived = client.get('/api/workflow-definitions?include_archived=true', headers=headers)
        assert include_archived.status_code == 200
        include_archived_keys = {item['workflow_key'] for item in include_archived.json()}
        assert {'treatment_plan_timeliness', 'treatment_plan_followup'} <= include_archived_keys

    db = session_local()
    try:
        actions = {
            log.action
            for log in db.execute(
                select(AuditLog).where(AuditLog.target_entity_type.in_(['workflow_definition', 'workflow_definition_version']))
            ).scalars()
        }
        assert 'workflow_definition.create' in actions
        assert 'workflow_definition.version.publish' in actions
        assert 'workflow_definition.archive' in actions
    finally:
        db.close()


def test_workflow_definition_role_gate_and_duplicate_key(app_with_sqlite):
    app, _ = app_with_sqlite

    with TestClient(app) as client:
        admin_headers = _auth_headers(client)
        manager = client.post(
            '/api/users',
            headers=admin_headers,
            json={
                'username': 'workflow-manager',
                'full_name': 'Workflow Manager',
                'password': 'temporary-pass-1234',
                'role': 'manager',
            },
        )
        assert manager.status_code == 200
        manager_headers = _login_headers(client, 'workflow-manager', 'temporary-pass-1234')

        created = client.post('/api/workflow-definitions', headers=admin_headers, json=_workflow_payload('workflow_role_gate'))
        assert created.status_code == 200

        duplicate = client.post('/api/workflow-definitions', headers=admin_headers, json=_workflow_payload('workflow_role_gate'))
        assert duplicate.status_code == 400

        manager_list = client.get('/api/workflow-definitions', headers=manager_headers)
        assert manager_list.status_code == 200
        assert {item['workflow_key'] for item in manager_list.json()} == {'treatment_plan_timeliness', 'workflow_role_gate'}

        manager_create = client.post('/api/workflow-definitions', headers=manager_headers, json=_workflow_payload('manager_created'))
        assert manager_create.status_code == 403


def test_default_workflow_is_seeded_and_unused_drafts_can_be_deleted(app_with_sqlite):
    app, session_local = app_with_sqlite

    with TestClient(app) as client:
        headers = _auth_headers(client)
        listed = client.get('/api/workflow-definitions', headers=headers)
        assert listed.status_code == 200
        default = next(item for item in listed.json() if item['workflow_key'] == 'treatment_plan_timeliness')
        assert default['current_version']['status'] == 'published'
        assert default['current_version']['definition_snapshot']['checklist_id'] == 'treatment-plan-v1'
        assert default['current_version']['definition_snapshot']['version'] == '1.1.0'
        assert default['current_version']['definition_snapshot']['steps'][0]['label'] == 'Confirm this is the correct client chart'
        assert len(default['current_version']['definition_snapshot']['steps']) == 42
        assert default['current_version']['definition_snapshot']['steps'][33]['key'] == 'require_manual_override_reason'
        transition_targets = {item['to'] for item in default['current_version']['transition_rules']}
        assert {'current_compliant', 'returned_for_correction', 'approved_finalized'} <= transition_targets

        delete_default = client.delete(f"/api/workflow-definitions/{default['id']}", headers=headers)
        assert delete_default.status_code == 400

        draft = client.post('/api/workflow-definitions', headers=headers, json=_workflow_payload('delete_me_draft'))
        assert draft.status_code == 200
        deleted = client.delete(f"/api/workflow-definitions/{draft.json()['id']}", headers=headers)
        assert deleted.status_code == 200
        assert deleted.json() == {'status': 'deleted', 'workflow_key': 'delete_me_draft'}

        invalid = client.post(
            '/api/workflow-definitions',
            headers=headers,
            json={
                **_workflow_payload('invalid_steps'),
                'initial_version': {
                    'definition_snapshot': {'steps': [{'key': 'missing_label'}]},
                    'transition_rules': [{'from': 'draft', 'to': 'active', 'roles': ['admin']}],
                    'version_notes': '',
                },
            },
        )
        assert invalid.status_code == 400
        assert 'label is required' in invalid.json()['detail']

    db = session_local()
    try:
        delete_log = db.execute(select(AuditLog).where(AuditLog.action == 'workflow_definition.delete')).scalar_one()
        assert 'delete_me_draft' in delete_log.details
        seed_log = db.execute(select(AuditLog).where(AuditLog.action == 'system.workflow_definition.seeded')).scalar_one_or_none()
        assert seed_log is not None
    finally:
        db.close()
