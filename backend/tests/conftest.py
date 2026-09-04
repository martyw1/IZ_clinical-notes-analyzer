from collections.abc import Iterator
from contextlib import ExitStack
import os
from tempfile import TemporaryDirectory
from typing import Final

import pytest

from v2_test_runtime import preserved_environment, runtime_scope


collect_ignore_glob: Final = ("*.local-*.py", "*.local.*.py")
_session_resources: Final = pytest.StashKey[ExitStack]()
_configuration_names: Final = frozenset({
    "ENVIRONMENT", "SECRET_KEY", "DATA_ENCRYPTION_KEY", "LOCAL_SQLITE_DB_PATH",
    "BOOTSTRAP_ADMIN_USERNAME", "BOOTSTRAP_ADMIN_PASSWORD", "ALLOWED_HOSTS", "FRONTEND_ORIGINS",
})


def pytest_configure(config: pytest.Config) -> None:
    resources = ExitStack()
    config.stash[_session_resources] = resources
    resources.enter_context(preserved_environment())
    app_data = resources.enter_context(TemporaryDirectory(prefix="iz-cna-pytest-collection-"))
    for name in tuple(os.environ):
        if name.startswith("IZ_CNA_") or name in _configuration_names:
            os.environ.pop(name)
    os.environ["IZ_CNA_LOCAL_APP_DATA_DIR"] = app_data
    os.environ["ENVIRONMENT"] = "test"


def pytest_unconfigure(config: pytest.Config) -> None:
    config.stash[_session_resources].close()


@pytest.fixture(autouse=True)
def isolated_test_runtime(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    with runtime_scope():
        yield
