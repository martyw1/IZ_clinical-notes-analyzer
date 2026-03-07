import importlib
from pathlib import Path

import pytest


@pytest.fixture
def app_with_sqlite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / 'test.db'
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{db_path}')
    monkeypatch.setenv('SECRET_KEY', 'test-secret')

    import app.core.config as config_module
    import app.db.session as session_module
    import app.main as main_module

    importlib.reload(config_module)
    importlib.reload(session_module)
    importlib.reload(main_module)

    return main_module.app, session_module.SessionLocal
