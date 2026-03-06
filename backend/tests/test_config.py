from app.core.config import Settings
from app.db.session import resolve_database_url


def test_frontend_origins_list_parses_csv():
    settings = Settings(frontend_origins='http://localhost:5173, https://example.com')
    assert settings.frontend_origins_list == ['http://localhost:5173', 'https://example.com']


def test_resolve_database_url_rewrites_localhost_inside_docker_internal_mode():
    original = 'postgresql+psycopg2://iz_clinical_notes:p%40ss%2Fword@localhost:5432/iz_clinical_notes_analyzer'
    resolved = resolve_database_url(original, in_docker=True, database_host_mode='internal')
    assert resolved == 'postgresql+psycopg2://iz_clinical_notes:p%40ss%2Fword@db:5432/iz_clinical_notes_analyzer'


def test_resolve_database_url_rewrites_localhost_inside_docker_host_mode():
    original = 'postgresql+psycopg2://iz_clinical_notes:pass@127.0.0.1:5432/iz_clinical_notes_analyzer'
    resolved = resolve_database_url(original, in_docker=True, database_host_mode='host')
    assert resolved == 'postgresql+psycopg2://iz_clinical_notes:pass@host.docker.internal:5432/iz_clinical_notes_analyzer'


def test_resolve_database_url_keeps_external_host_inside_docker():
    original = 'postgresql+psycopg2://iz_clinical_notes:pass@db.example.org:5432/iz_clinical_notes_analyzer'
    assert resolve_database_url(original, in_docker=True, database_host_mode='external') == original


def test_resolve_database_url_keeps_localhost_outside_docker():
    original = 'postgresql+psycopg2://iz_clinical_notes:pass@localhost:5432/iz_clinical_notes_analyzer'
    assert resolve_database_url(original, in_docker=False, database_host_mode='internal') == original
