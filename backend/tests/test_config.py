from app.core.config import Settings


def test_frontend_origins_list_parses_csv():
    settings = Settings(frontend_origins='http://localhost:5173, https://example.com')
    assert settings.frontend_origins_list == ['http://localhost:5173', 'https://example.com']
