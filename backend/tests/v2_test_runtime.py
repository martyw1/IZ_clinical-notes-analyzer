from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Final

from fastapi.testclient import TestClient
from pytest import MonkeyPatch


_resources: Final = ContextVar[ExitStack]("test_app_resources")


@contextmanager
def preserved_environment() -> Iterator[None]:
    previous = os.environ.copy()
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(previous)


@contextmanager
def runtime_scope() -> Iterator[None]:
    with preserved_environment(), ExitStack() as resources:
        token = _resources.set(resources)
        try:
            yield
        finally:
            reset_app_modules()
            _resources.reset(token)


def reset_app_modules() -> None:
    _resources.get().close()
    database_module = sys.modules.get("app.v2.db")
    if database_module is not None:
        database_module.engine.dispose()
    for module_name in tuple(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            sys.modules.pop(module_name)


def configured_client(*, raise_server_exceptions: bool = True) -> TestClient:
    from app.main import create_app

    client = TestClient(create_app(), raise_server_exceptions=raise_server_exceptions)
    return _resources.get().enter_context(client)


def prepare_app(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("IZ_CNA_LOCAL_APP_DATA_DIR", str(tmp_path / "app-data"))
    monkeypatch.setenv("IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD", "StrongLocalPass1")
    monkeypatch.setenv("IZ_CNA_SECRET_KEY", "test-secret-key-for-v2-manual-correction")
    monkeypatch.setenv("IZ_CNA_DATA_ENCRYPTION_KEY", "test-data-encryption-key-for-v2-manual-correction")
    reset_app_modules()


def fresh_client(tmp_path: Path, monkeypatch: MonkeyPatch) -> TestClient:
    prepare_app(tmp_path, monkeypatch)
    return configured_client()
