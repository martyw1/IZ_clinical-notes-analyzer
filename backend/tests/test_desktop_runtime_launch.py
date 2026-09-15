from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from app.desktop_process import process_started_utc
from app.desktop_runtime_authority import RuntimeAuthorityError
from app.desktop_runtime_launch import prepare_managed_launch
from test_desktop_runtime_authority import TX, clear_profile_environment, make_runtime_fixture


def set_candidate_environment(monkeypatch: pytest.MonkeyPatch, data_root: Path, journal_path: Path) -> None:
    monkeypatch.setenv("IZ_CNA_LOCAL_APP_DATA_DIR", str(data_root))
    monkeypatch.setenv("IZ_CNA_ENV_FILE", str(data_root / ".env"))
    monkeypatch.setenv("IZ_CNA_MAINTENANCE_MODE", "candidate")
    monkeypatch.setenv("IZ_CNA_MAINTENANCE_JOURNAL", str(journal_path))
    monkeypatch.setenv("IZ_CNA_MAINTENANCE_TRANSACTION_ID", TX)
    monkeypatch.setenv("IZ_CNA_MAINTENANCE_OWNER_PID", str(os.getpid()))
    monkeypatch.setenv("IZ_CNA_MAINTENANCE_OWNER_STARTED_UTC", process_started_utc(os.getpid()))


def test_candidate_launch_is_fully_authorized_before_application_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = make_runtime_fixture(tmp_path)
    set_candidate_environment(monkeypatch, fixture.paths.data_root, fixture.paths.journal_path)
    sys.modules.pop("app.main", None)

    launch = prepare_managed_launch(fixture.paths.executable_path)
    try:
        assert launch.authority.gate == "maintenance"
        assert launch.owner_lease is not None
        assert "app.main" not in sys.modules
    finally:
        assert launch.owner_lease is not None
        launch.owner_lease.close()


def test_candidate_launch_rejects_noncanonical_journal_argument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = make_runtime_fixture(tmp_path)
    set_candidate_environment(monkeypatch, fixture.paths.data_root, fixture.paths.journal_path)
    monkeypatch.setenv("IZ_CNA_MAINTENANCE_JOURNAL", str(fixture.paths.journal_path.with_name("other.json")))

    with pytest.raises(RuntimeAuthorityError, match="journal_path_mismatch"):
        prepare_managed_launch(fixture.paths.executable_path)


def test_installed_launch_rejects_leftover_candidate_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = make_runtime_fixture(tmp_path)
    monkeypatch.setenv("IZ_CNA_LOCAL_APP_DATA_DIR", str(fixture.paths.data_root))
    monkeypatch.setenv("IZ_CNA_ENV_FILE", str(fixture.paths.data_root / ".env"))
    monkeypatch.setenv("IZ_CNA_MAINTENANCE_OWNER_PID", str(os.getpid()))

    with pytest.raises(RuntimeAuthorityError, match="maintenance_environment_invalid"):
        prepare_managed_launch(fixture.paths.executable_path)


def test_installed_launch_accepts_only_matching_committed_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = make_runtime_fixture(tmp_path)
    fixture.write_receipt()
    fixture.journal["state"] = "COMMITTED"
    fixture.journal["completed_steps"] = ["NEW_PROGRAM_MOVED", "INSTALL_RECEIPT_WRITTEN", "COMMIT_RECORDED"]
    fixture.write_journal()
    monkeypatch.setenv("IZ_CNA_LOCAL_APP_DATA_DIR", str(fixture.paths.data_root))
    monkeypatch.setenv("IZ_CNA_ENV_FILE", str(fixture.paths.data_root / ".env"))

    launch = prepare_managed_launch(fixture.paths.executable_path)

    assert launch.authority.gate == "open"
    assert launch.owner_lease is None
