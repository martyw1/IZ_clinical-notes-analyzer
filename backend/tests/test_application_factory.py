from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "desktop_contract"


def _reset_application_imports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IZ_CNA_LOCAL_APP_DATA_DIR", str(tmp_path / "application-profile"))
    monkeypatch.setenv("IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD", "SyntheticFactoryPass123")
    monkeypatch.setenv("IZ_CNA_SECRET_KEY", "synthetic-factory-secret-key-1234567890")
    monkeypatch.setenv("IZ_CNA_DATA_ENCRYPTION_KEY", "synthetic-factory-data-key-1234567890")
    for module_name in tuple(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            sys.modules.pop(module_name)


def test_factory_import_and_construction_have_no_persistence_side_effects(tmp_path: Path) -> None:
    # Given: a fresh interpreter and a nonexistent synthetic application-data root.
    data_root = tmp_path / "factory-only-profile"
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.startswith("IZ_CNA_"):
            environment.pop(name)
    environment.update(
        {
            "IZ_CNA_LOCAL_APP_DATA_DIR": str(data_root),
            "IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD": "SyntheticFactoryPass123",
            "IZ_CNA_SECRET_KEY": "synthetic-factory-secret-key-1234567890",
            "IZ_CNA_DATA_ENCRYPTION_KEY": "synthetic-factory-data-key-1234567890",
        }
    )
    probe = textwrap.dedent(
        """
        from pathlib import Path
        from unittest.mock import patch

        import app.application as application
        import app.v2.db as database

        with (
            patch.object(application, "init_database") as initialize,
            patch.object(database, "run_migrations") as migrate,
            patch.object(database, "reevaluate_all_plan_versions") as reevaluate,
            patch.object(application, "log_event") as audit,
        ):
            application.create_application()
            application.create_application()
            assert initialize.call_count == 0
            assert migrate.call_count == 0
            assert reevaluate.call_count == 0
            assert audit.call_count == 0

        data_root = Path(__import__("os").environ["IZ_CNA_LOCAL_APP_DATA_DIR"])
        assert not data_root.exists(), "factory construction created persistent storage"
        """
    )

    # When: compatibility import plus two factory calls run without a lifespan.
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: construction succeeds without creating the profile, database, or audit ledger.
    assert result.returncode == 0, result.stderr
    assert not data_root.exists()


def test_desktop_lifespan_initializes_database_and_start_audit_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: one desktop application using a fresh synthetic profile.
    _reset_application_imports(tmp_path, monkeypatch)
    application = importlib.import_module("app.application")
    desktop_application = importlib.import_module("app.desktop_application")
    database = importlib.import_module("app.v2.db")
    with (
        patch.object(application, "init_database", wraps=database.init_database) as initialize,
        patch.object(database, "run_migrations", wraps=database.run_migrations) as migrate,
        patch.object(
            database,
            "reevaluate_all_plan_versions",
            wraps=database.reevaluate_all_plan_versions,
        ) as reevaluate,
        patch.object(application, "log_event", wraps=application.log_event) as audit,
    ):
        api = desktop_application.create_desktop_application()
        assert (initialize.call_count, migrate.call_count, reevaluate.call_count, audit.call_count) == (
            0,
            0,
            0,
            0,
        )

        # When: its ASGI lifespan is entered once.
        with TestClient(api):
            pass

    # Then: initialization, migration, reevaluation, and startup audit each run exactly once.
    assert initialize.call_count == 1
    assert migrate.call_count == 1
    assert reevaluate.call_count == 1
    assert audit.call_count == 1
    assert audit.call_args.kwargs["action"] == "app.start"
    database.engine.dispose()


def test_desktop_factory_preserves_task_one_routes_and_middleware(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the Task 1 route fixture and a freshly constructed desktop application.
    _reset_application_imports(tmp_path, monkeypatch)
    desktop_application = importlib.import_module("app.desktop_application")
    api = desktop_application.create_desktop_application()
    expected = json.loads((FIXTURE_ROOT / "routes.json").read_text(encoding="utf-8"))

    # When: API routes, all desktop routes, and middleware are normalized.
    all_routes = [
        (route.path, method)
        for route in api.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    ]
    observed = {
        "schema": "iz-desktop-routes-v1",
        "middleware": [item.cls.__name__ for item in api.user_middleware],
        "routes": sorted(
            (
                {"method": method, "path": route.path}
                for route in api.routes
                if isinstance(route, APIRoute)
                and (route.path.startswith("/api/") or route.path == "/health")
                for method in route.methods
            ),
            key=lambda item: (item["path"], item["method"]),
        ),
    }

    # Then: the Task 1 contract is exact and no desktop dispatch identity is duplicated.
    assert observed == expected
    assert len(all_routes) == len(set(all_routes))


def test_desktop_compatibility_import_constructs_one_base_application(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the base factory is loaded but neither compatibility module has been imported.
    _reset_application_imports(tmp_path, monkeypatch)
    application = importlib.import_module("app.application")

    # When: the legacy desktop ASGI module is imported.
    with patch.object(
        application,
        "create_application",
        wraps=application.create_application,
    ) as create_base:
        desktop_main = importlib.import_module("app.desktop_main")

    # Then: one base app backs the desktop export without realizing app.main:app.
    assert create_base.call_count == 1
    assert "app.main" not in sys.modules
    assert isinstance(desktop_main.app, FastAPI)
    assert desktop_main.create_desktop_app is not None


def test_main_compatibility_exports_are_importable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a clean module graph and a nonexistent synthetic profile.
    _reset_application_imports(tmp_path, monkeypatch)
    application = importlib.import_module("app.application")

    # When: the legacy API ASGI module is imported.
    main = importlib.import_module("app.main")

    # Then: both compatibility exports retain their public shapes without persistence.
    assert main.create_app is application.create_application
    assert isinstance(main.app, FastAPI)
    assert not (tmp_path / "application-profile").exists()


def test_fresh_client_retains_and_closes_application_lifespan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the shared backend test helper creates a client for a synthetic profile.
    from test_v2_manual_patient_correction import _fresh_client

    client = _fresh_client(tmp_path, monkeypatch)

    # When: the pytest monkeypatch fixture runs its registered cleanup.
    assert client.portal is not None
    monkeypatch.undo()

    # Then: the retained lifespan portal is closed instead of leaking across tests.
    assert client.portal is None
