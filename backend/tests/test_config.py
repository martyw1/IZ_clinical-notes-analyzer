from app.core.config import Settings
from app.db.session import resolve_database_url


def test_frontend_origins_list_parses_csv():
    settings = Settings(frontend_origins='http://localhost:5173, https://example.com')
    assert settings.frontend_origins_list == ['http://localhost:5173', 'https://example.com']


def test_database_url_value_builds_from_dedicated_postgres_settings():
    settings = Settings(
        database_url=None,
        database_host='127.0.0.1',
        database_port=55432,
        database_name='clinical_notes_app',
        database_user='clinical_user',
        database_password='s3cret!',
    )
    assert settings.database_url_value == 'postgresql+psycopg://clinical_user:s3cret%21@127.0.0.1:55432/clinical_notes_app'


def test_resolve_database_url_rewrites_localhost_inside_docker_to_postgres_service():
    original = 'postgresql+psycopg2://iz_clinical_notes:p%40ss%2Fword@localhost:5432/iz_clinical_notes_analyzer'
    resolved = resolve_database_url(original, in_docker=True, postgres_service_host='postgres')
    assert resolved == 'postgresql+psycopg://iz_clinical_notes:p%40ss%2Fword@postgres:5432/iz_clinical_notes_analyzer'


def test_resolve_database_url_keeps_localhost_outside_docker():
    original = 'postgresql+psycopg2://iz_clinical_notes:pass@localhost:55432/iz_clinical_notes_analyzer'
    assert resolve_database_url(original, in_docker=False) == 'postgresql+psycopg://iz_clinical_notes:pass@localhost:55432/iz_clinical_notes_analyzer'


def test_resolve_database_url_keeps_dedicated_external_host_inside_docker():
    original = 'postgresql+psycopg2://iz_clinical_notes:pass@db.example.org:5432/iz_clinical_notes_analyzer'
    assert resolve_database_url(original, in_docker=True) == 'postgresql+psycopg://iz_clinical_notes:pass@db.example.org:5432/iz_clinical_notes_analyzer'
