from app.core.config import Settings
from app.db.session import resolve_database_url


def test_frontend_origins_list_parses_csv():
    settings = Settings(frontend_origins='http://localhost:5173, https://example.com')
    assert settings.frontend_origins_list == ['http://localhost:5173', 'https://example.com']


def test_resolve_database_url_rewrites_localhost_inside_docker():
    resolved = resolve_database_url('postgresql+psycopg2://chart:chart@localhost:5432/chartreview', in_docker=True)
    assert resolved == 'postgresql+psycopg2://chart:***@db:5432/chartreview'


def test_resolve_database_url_keeps_non_localhost_host_inside_docker():
    original = 'postgresql+psycopg2://chart:chart@postgres:5432/chartreview'
    assert resolve_database_url(original, in_docker=True) == original


def test_resolve_database_url_keeps_localhost_outside_docker():
    original = 'postgresql+psycopg2://chart:chart@localhost:5432/chartreview'
    assert resolve_database_url(original, in_docker=False) == original
