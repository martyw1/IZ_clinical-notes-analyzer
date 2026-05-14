import importlib
from pathlib import Path

import pytest


@pytest.fixture
def app_with_sqlite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / 'test.db'
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{db_path}')
    monkeypatch.setenv('SECRET_KEY', 'test-secret-not-placeholder-1234')
    monkeypatch.setenv('DATA_ENCRYPTION_KEY', 'test-data-encryption-key-not-placeholder-1234')
    monkeypatch.setenv('UPLOAD_DIR', str(tmp_path / 'uploads'))
    monkeypatch.setenv('BOOTSTRAP_ADMIN_PASSWORD', 'r3!@analyzer#123')

    import app.core.config as config_module
    import app.db.session as session_module
    import app.services.secure_storage as secure_storage_module
    import app.services.runtime_checks as runtime_checks_module
    import app.services.version as version_module
    import app.main as main_module

    importlib.reload(config_module)
    importlib.reload(session_module)
    importlib.reload(secure_storage_module)
    importlib.reload(runtime_checks_module)
    importlib.reload(version_module)
    importlib.reload(main_module)

    return main_module.app, session_module.SessionLocal
