from app.core.config import Settings
from app.db.session import resolve_database_url


def test_frontend_origins_list_parses_csv():
    settings = Settings(frontend_origins='http://localhost:5173, https://example.com')
    assert settings.frontend_origins_list == ['http://localhost:5173', 'https://example.com']


def test_resolve_database_url_rewrites_localhost_inside_docker():
    resolved = resolve_database_url('postgresql+psycopg2://postgres:postgres@localhost:5432/optiflow', in_docker=True)
    assert resolved == 'postgresql+psycopg2://postgres:***@db:5432/optiflow'


def test_resolve_database_url_keeps_non_localhost_host_inside_docker():
    original = 'postgresql+psycopg2://postgres:postgres@postgres:5432/optiflow'
    assert resolve_database_url(original, in_docker=True) == original


def test_resolve_database_url_keeps_localhost_outside_docker():
    original = 'postgresql+psycopg2://postgres:postgres@localhost:5432/optiflow'
    assert resolve_database_url(original, in_docker=False) == original
