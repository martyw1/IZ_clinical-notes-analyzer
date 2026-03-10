from sqlalchemy import create_engine, inspect, text

from app.db.bootstrap import ensure_schema_compatibility


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
