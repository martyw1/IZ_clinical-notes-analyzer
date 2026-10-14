from __future__ import annotations

from threading import Event

from test_v2_distinct_alleva_jobs import _configure, _partial_roster_server, _wait
from test_v2_alleva_sync import _mock_alleva_server
from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def test_two_stage_update_orders_calls_and_survives_restart(tmp_path, monkeypatch):
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    with _mock_alleva_server(published_shape=True) as (base, state):
        _configure(client, headers, base)
        started = client.post('/api/v2/roster-update/run', headers=headers)
        assert started.status_code == 202
        job_id = started.json()['job_id']
        result = _wait(client, headers, f'/api/v2/api-harness/jobs/{job_id}')
        assert result['status'] == 'completed'
        assert result['stage_number'] == 2
        assert result['phase_total'] == result['phase_completed'] == 1
        token_indices = [i for i, path in enumerate(state.paths) if path == '/token']
        assert len(token_indices) == 2
        assert all('treatment-plans' not in path for path in state.paths[:token_indices[1]])
        # An unchanged replay must close its transaction before publishing progress.
        again = client.post('/api/v2/roster-update/run', headers=headers)
        replay = _wait(client, headers, f"/api/v2/api-harness/jobs/{again.json()['job_id']}")
        assert replay['status'] == 'completed'
        assert replay['records_written'] == 0
    restarted = _fresh_client(tmp_path, monkeypatch)
    saved = restarted.get('/api/v2/roster-update/latest', headers=_auth_headers(restarted)).json()
    assert saved['job_id'] == replay['job_id']
    assert saved['phase_completed'] == saved['phase_total'] == 1
    assert saved['child_job_id']


def test_partial_patient_pull_does_not_start_plan_stage(tmp_path, monkeypatch):
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    with _partial_roster_server() as base:
        _configure(client, headers, base, pagination_limit=2, sync_limit=2)
        started = client.post('/api/v2/roster-update/run', headers=headers).json()
        result = _wait(client, headers, f"/api/v2/api-harness/jobs/{started['job_id']}")
    assert result['status'] == 'completed_with_warnings'
    assert result['stage_number'] == 1
    jobs = client.get('/api/v2/api-harness/jobs', headers=headers).json()
    assert not any(job['job_type'] == 'approved_treatment_plan_sync' for job in jobs)


def test_update_keeps_reads_available_rejects_overlap_and_cancels(tmp_path, monkeypatch):
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    entered, release = Event(), Event()
    from app.v2.services import jobs
    original = jobs.run_roster_pull

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(8)
        return original(*args, **kwargs)

    monkeypatch.setattr(jobs, 'run_roster_pull', delayed)
    with _mock_alleva_server() as (base, _):
        _configure(client, headers, base)
        started = client.post('/api/v2/roster-update/run', headers=headers).json()
        try:
            assert entered.wait(3)
            assert client.get('/api/v2/patient-roster', headers=headers).status_code == 200
            for route in ('roster-update/run', 'patient-roster/pull', 'alleva-sync/run'):
                assert client.post(f'/api/v2/{route}', headers=headers).status_code == 409
            client.post(f"/api/v2/api-harness/jobs/{started['job_id']}/cancel", headers=headers)
        finally:
            release.set()
        result = _wait(client, headers, f"/api/v2/api-harness/jobs/{started['job_id']}")
    assert result['status'] == 'cancelled'
    assert result['stage_number'] == 1


def test_combined_update_requires_saved_approval(tmp_path, monkeypatch):
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    assert client.post('/api/v2/roster-update/run', headers=headers).status_code == 409
    assert client.get('/api/v2/roster-update/latest', headers=headers).status_code == 404
    assert client.post('/api/v2/roster-update/run').status_code == 401
    from test_v2_auth_rbac import _create_user
    _, viewer_headers = _create_user(client, headers, 'synthetic-update-viewer', 'viewer')
    assert client.post('/api/v2/roster-update/run', headers=viewer_headers).status_code == 403
    assert client.get('/api/v2/roster-update/latest', headers=viewer_headers).status_code == 403


def test_unexpected_roster_worker_error_stops_parent_safely(tmp_path, monkeypatch):
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    from app.v2.services import jobs
    def fail(*args, **kwargs):
        raise RuntimeError('Synthetic sensitive worker detail')
    monkeypatch.setattr(jobs, 'run_roster_pull', fail)
    with _mock_alleva_server() as (base, _):
        _configure(client, headers, base)
        started = client.post('/api/v2/roster-update/run', headers=headers).json()
        result = _wait(client, headers, f"/api/v2/api-harness/jobs/{started['job_id']}")
    assert result['status'] == 'failed'
    assert result['stage_number'] == 1
    assert 'sensitive' not in result['message']


def test_schema_twelve_upgrade_adds_progress_without_changing_clinical_rows(tmp_path, monkeypatch):
    import sqlite3
    from contextlib import closing
    from app.v2.migrations import runner
    from app.v2.migrations.registry import MIGRATIONS
    from app.v2.migrations.schema_verifier import verify_database
    from v2_migration_fixtures import SYNTHETIC_SECRET, create_legacy_database
    database = create_legacy_database(tmp_path)
    request = runner.MigrationRequest(database, tmp_path, SYNTHETIC_SECRET, 'synthetic-progress-upgrade')
    with monkeypatch.context() as context:
        context.setattr(runner, 'MIGRATIONS', MIGRATIONS[:12])
        context.setattr(runner, 'LATEST_SCHEMA_VERSION', 12)
        runner.run_migrations(request)
    with closing(sqlite3.connect(database)) as db:
        clinical = db.execute('SELECT * FROM treatment_plan_versions').fetchall()
    report = runner.run_migrations(request)
    assert report.applied_versions == (13,)
    assert report.backup_path is not None
    verify_database(database, 13)
    with closing(sqlite3.connect(database)) as db:
        assert db.execute('SELECT * FROM treatment_plan_versions').fetchall() == clinical
        assert db.execute('SELECT COUNT(*) FROM api_job_progress').fetchone() == (0,)


def test_interrupted_parent_is_retained_and_retry_uses_saved_credentials(tmp_path, monkeypatch):
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    with _mock_alleva_server(published_shape=True) as (base, _):
        _configure(client, headers, base)
        from app.v2.services.jobs import job_service
        # Simulate process exit after queuing, before any vendor work starts.
        with monkeypatch.context() as context:
            context.setattr(job_service, '_run_roster_update', lambda *args: None)
            original = client.post('/api/v2/roster-update/run', headers=headers).json()
        restarted = _fresh_client(tmp_path, monkeypatch)
        restarted_headers = _auth_headers(restarted)
        saved = restarted.get('/api/v2/roster-update/latest', headers=restarted_headers).json()
        assert saved['job_id'] == original['job_id']
        assert saved['status'] == 'stale_or_interrupted'
        assert saved['stage_number'] == 1
        retry = restarted.post('/api/v2/roster-update/run', headers=restarted_headers)
        assert retry.status_code == 202
        completed = _wait(restarted, restarted_headers, f"/api/v2/api-harness/jobs/{retry.json()['job_id']}")
        assert completed['status'] == 'completed'
        assert completed['job_id'] != original['job_id']
