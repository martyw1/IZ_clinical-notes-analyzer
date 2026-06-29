from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

from app.db.bootstrap import ensure_schema_compatibility
from app.models.models import AuditLog


def test_ensure_schema_compatibility_adds_missing_legacy_columns(tmp_path):
    db_path = tmp_path / 'legacy.db'
    engine = create_engine(f'sqlite:///{db_path}')

    with engine.begin() as connection:
        connection.execute(
            text(
                'CREATE TABLE users ('
                'id INTEGER PRIMARY KEY, '
                'username VARCHAR(80) UNIQUE NOT NULL, '
                'password_hash VARCHAR(255) NOT NULL, '
                'role VARCHAR(20) NOT NULL'
                ')'
            )
        )

    ensure_schema_compatibility(engine)

    columns = {column['name'] for column in inspect(engine).get_columns('users')}
    assert 'must_reset_password' in columns
    assert 'failed_login_attempts' in columns
    assert 'is_locked' in columns
    assert 'created_at' in columns


def test_ensure_schema_compatibility_adds_new_chart_columns(tmp_path):
    db_path = tmp_path / 'legacy-chart.db'
    engine = create_engine(f'sqlite:///{db_path}')

    with engine.begin() as connection:
        connection.execute(
            text(
                'CREATE TABLE charts ('
                'id INTEGER PRIMARY KEY, '
                'client_name VARCHAR(120) NOT NULL, '
                'level_of_care VARCHAR(120) NOT NULL, '
                'primary_clinician VARCHAR(120) NOT NULL, '
                'counselor_id INTEGER NOT NULL, '
                'state VARCHAR(40) NOT NULL DEFAULT "Draft"'
                ')'
            )
        )

    ensure_schema_compatibility(engine)

    columns = {column['name'] for column in inspect(engine).get_columns('charts')}
    assert 'patient_id' in columns
    assert 'admission_date' in columns
    assert 'discharge_date' in columns
    assert 'auditor_name' in columns
    assert 'other_details' in columns
    assert 'notes' in columns


def test_ensure_schema_compatibility_adds_app_settings_columns(tmp_path):
    db_path = tmp_path / 'legacy-settings.db'
    engine = create_engine(f'sqlite:///{db_path}')

    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE app_settings (id INTEGER PRIMARY KEY)'))

    ensure_schema_compatibility(engine)

    columns = {column['name'] for column in inspect(engine).get_columns('app_settings')}
    assert 'organization_name' in columns
    assert 'access_intel_enabled' in columns
    assert 'llm_enabled' in columns
    assert 'llm_model' in columns
    assert 'alleva_treatment_plan_patient_name_import_enabled' in columns
    assert 'treatment_plan_loc_change_window_days' in columns
    assert 'treatment_plan_loc_change_window_validated' in columns


def test_ensure_schema_compatibility_adds_workflow_definition_columns(tmp_path):
    db_path = tmp_path / 'legacy-workflows.db'
    engine = create_engine(f'sqlite:///{db_path}')

    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE workflow_definitions (id INTEGER PRIMARY KEY)'))
        connection.execute(text('CREATE TABLE workflow_definition_versions (id INTEGER PRIMARY KEY)'))

    ensure_schema_compatibility(engine)

    definition_columns = {column['name'] for column in inspect(engine).get_columns('workflow_definitions')}
    version_columns = {column['name'] for column in inspect(engine).get_columns('workflow_definition_versions')}
    assert 'workflow_key' in definition_columns
    assert 'current_version_id' in definition_columns
    assert 'definition_snapshot' in version_columns
    assert 'transition_rules' in version_columns
    assert 'published_at' in version_columns


def test_ensure_schema_compatibility_adds_treatment_plan_content_columns(tmp_path):
    db_path = tmp_path / 'legacy-treatment-plans.db'
    engine = create_engine(f'sqlite:///{db_path}')

    with engine.begin() as connection:
        connection.execute(
            text(
                'CREATE TABLE treatment_plan_records ('
                'id INTEGER PRIMARY KEY, '
                'client_id INTEGER NOT NULL, '
                'plan_kind VARCHAR(40) NOT NULL, '
                'document_date VARCHAR(40) NOT NULL DEFAULT "", '
                'staff_signature_date VARCHAR(40) NOT NULL DEFAULT "", '
                'client_signature_date VARCHAR(40) NOT NULL DEFAULT ""'
                ')'
            )
        )

    ensure_schema_compatibility(engine)

    columns = {column['name'] for column in inspect(engine).get_columns('treatment_plan_records')}
    assert 'content_items_json' in columns
    assert 'content_capture_status' in columns
    assert 'content_capture_warnings' in columns


def test_ensure_schema_compatibility_repairs_retired_required_audit_columns(tmp_path):
    db_path = tmp_path / 'legacy-audit-fhir.db'
    engine = create_engine(f'sqlite:///{db_path}')

    with engine.begin() as connection:
        connection.execute(
            text(
                'CREATE TABLE audit_logs ('
                'id INTEGER PRIMARY KEY, '
                'event_id TEXT UNIQUE NOT NULL, '
                'timestamp_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, '
                'request_id TEXT NOT NULL, '
                'correlation_id TEXT NOT NULL, '
                'event_category TEXT NOT NULL, '
                'action TEXT NOT NULL, '
                'details TEXT NOT NULL DEFAULT "", '
                'fhir_audit_event TEXT NOT NULL, '
                'hash TEXT NOT NULL'
                ')'
            )
        )
        connection.execute(
            text(
                'INSERT INTO audit_logs (event_id, request_id, correlation_id, event_category, action, fhir_audit_event, hash) '
                'VALUES ("legacy-event", "legacy-request", "legacy-correlation", "system", "system.legacy", "{}", "legacy-hash")'
            )
        )

    updates = ensure_schema_compatibility(engine)

    columns = {column['name'] for column in inspect(engine).get_columns('audit_logs')}
    assert 'fhir_audit_event' not in columns
    assert any(update['table'] == 'audit_logs' and 'fhir_audit_event' in update['column'] for update in updates)
    indexes = {index['name'] for index in inspect(engine).get_indexes('audit_logs')}
    assert {'idx_audit_action', 'idx_audit_request_id', 'idx_audit_patient_id'} <= indexes

    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        db.add(
            AuditLog(
                event_id='new-event',
                request_id='new-request',
                correlation_id='new-correlation',
                event_category='system',
                action='system.startup.completed',
                message='Startup completed without legacy FHIR audit columns.',
                details='{}',
                hash='new-hash',
            )
        )
        db.commit()
        logs = db.execute(select(AuditLog).order_by(AuditLog.id.asc())).scalars().all()
        assert [log.event_id for log in logs] == ['legacy-event', 'new-event']
    finally:
        db.close()
