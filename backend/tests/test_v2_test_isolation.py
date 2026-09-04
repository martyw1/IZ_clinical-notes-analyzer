from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from inspect import unwrap
from pathlib import Path
from types import TracebackType

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import event

from test_v2_manual_patient_correction import _auth_headers, _fresh_client
from test_v2_manual_name_privacy import metadata_database
from test_v2_plan_version_actions import runtime
from test_v2_plan_version_corrections import scenario
from v2_test_runtime import runtime_scope


@pytest.mark.parametrize("fixture_body", [
    pytest.param(unwrap(runtime), id="plan_actions"),
    pytest.param(unwrap(metadata_database), id="manual_metadata"),
    pytest.param(unwrap(scenario), id="plan_corrections"),
])
def test_real_fixture_enters_and_exits_client_lifespan_once(
    tmp_path: Path, monkeypatch: MonkeyPatch,
    fixture_body: Callable[[Path, MonkeyPatch], Iterator[object]],
    record_testsuite_property: Callable[[str, str], None],
) -> None:
    events: list[str] = []
    original_enter, original_exit = TestClient.__enter__, TestClient.__exit__

    def enter(client: TestClient) -> TestClient:
        events.append("enter")
        return original_enter(client)

    def exit_client(
        client: TestClient, exception_type: type[BaseException] | None,
        exception: BaseException | None, traceback: TracebackType | None,
    ) -> None:
        events.append("exit")
        original_exit(client, exception_type, exception, traceback)

    monkeypatch.setattr(TestClient, "__enter__", enter)
    monkeypatch.setattr(TestClient, "__exit__", exit_client)
    with runtime_scope(), contextmanager(fixture_body)(tmp_path, monkeypatch):
        pass

    record_testsuite_property(f"lifecycle.{fixture_body.__name__}", ",".join(events))
    assert events == ["enter", "exit"]


def test_bootstrap_changes_only_its_owned_process_environment(tmp_path: Path) -> None:
    # Given: a synthetic profile whose bootstrap intentionally updates process state.
    from app.macos_bootstrap import BootstrapCode, bootstrap

    profile = tmp_path / "bootstrap-profile"

    # When: the actual bootstrap runs without pytest's monkeypatch wrapper.
    result = bootstrap(data_dir_override=profile)

    # Then: its documented process-state side effect is present during this test.
    assert result.code is BootstrapCode.READY
    assert os.environ["IZ_CNA_LOCAL_APP_DATA_DIR"] == str(profile)
    assert os.environ["IZ_CNA_ENV_FILE"] == str(profile / ".env")


def test_next_app_has_its_own_database_after_bootstrap(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # Given: the earlier test may have bootstrapped another local profile.
    expected_database = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"

    # When: this test creates its independent application.
    client = _fresh_client(tmp_path, monkeypatch)
    from app.core.config import settings

    # Then: settings and real migrated storage belong to this test, not that profile.
    assert settings.sqlite_db_path == expected_database
    assert client.get("/api/readiness").status_code == 200
    with sqlite3.connect(expected_database) as database:
        assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert database.execute("SELECT COUNT(*) FROM users").fetchone() == (1,)


def test_restarting_a_test_app_disposes_the_previous_engine(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # Given: an initialized app with a real pooled SQLite engine.
    _fresh_client(tmp_path, monkeypatch)
    from app.v2.db import engine

    disposed: list[bool] = []
    event.listen(engine, "engine_disposed", lambda _engine: disposed.append(True))

    # When: the same synthetic profile is restarted through the shared factory.
    restarted = _fresh_client(tmp_path, monkeypatch)

    # Then: the old engine has released its handles and persisted schema remains usable.
    assert disposed == [True]
    assert restarted.get("/api/readiness").status_code == 200


@pytest.mark.parametrize("environment", ("local-client", "production"))
def test_restricted_origins_are_rejected_before_job_creation(
    tmp_path: Path, monkeypatch: MonkeyPatch, environment: str,
) -> None:
    # Given: restricted runtime settings and a complete synthetic untrusted profile.
    monkeypatch.setenv("ENVIRONMENT", environment)
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    configured = client.patch(
        "/api/api-configuration", headers=headers,
        json={
            "client_id": "synthetic-client", "client_secret": "synthetic-secret",
            "api_base_url": "https://vendor.invalid", "token_url": "https://vendor.invalid/token",
            "api_enabled": True, "treatment_plan_sync_enabled": True, "treatment_plan_sync_approved": True,
        },
    )
    assert configured.status_code == 200
    import app.v2.api.alleva_sync_routes as routes

    calls: list[bool] = []
    monkeypatch.setattr(routes.job_service, "create_treatment_plan_sync_job", lambda *_args: calls.append(True))

    # When: a real authenticated sync request reaches the unchanged trust guard.
    response = client.post("/api/v2/alleva-sync/run", headers=headers)

    # Then: no mapping or worker is created for the untrusted origin.
    assert response.status_code == 409
    assert "not trusted production origins" in response.json()["detail"]
    assert calls == []
    with sqlite3.connect(tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3") as database:
        assert database.execute("SELECT COUNT(*) FROM alleva_contract_approvals").fetchone() == (0,)
        assert database.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (0,)
