from __future__ import annotations

import logging
import os
import stat
import subprocess
import sys
from pathlib import Path
from threading import Barrier, Thread

from app.core.config import resolve_macos_local_app_data_dir
from app.macos_bootstrap import BootstrapCode, BootstrapResult, bootstrap


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _environment_delta(before: dict[str, str], after: dict[str, str]) -> set[str]:
    return {key for key in set(before) | set(after) if before.get(key) != after.get(key)}


def test_windows_override_baseline_shape_is_preserved(monkeypatch, tmp_path: Path) -> None:
    # Given: the existing cross-platform settings override is a private synthetic path.
    override = tmp_path / "windows-data"
    monkeypatch.setenv("IZ_CNA_LOCAL_APP_DATA_DIR", str(override))

    # When: the shared resolver receives the same override.
    actual = resolve_macos_local_app_data_dir(home=tmp_path / "home")

    # Then: explicit local data configuration remains authoritative.
    assert actual == override


def test_bootstrap_uses_private_application_support_root(tmp_path: Path, monkeypatch) -> None:
    # Given: a synthetic user home with no existing application data.
    home = tmp_path / "home"
    monkeypatch.delenv("IZ_CNA_LOCAL_APP_DATA_DIR", raising=False)
    monkeypatch.delenv("IZ_CNA_ENV_FILE", raising=False)

    # When: Darwin bootstrap initializes the local profile.
    result = bootstrap(home=home)

    # Then: the default root and env file are private and ready.
    root = home / "Library" / "Application Support" / "IZ Clinical Notes Analyzer"
    assert result.code is BootstrapCode.READY
    assert result.local_app_data_dir == root
    assert result.env_file == root / ".env"
    assert result.created_env is True
    if os.name == "posix":
        assert _mode(root) == 0o700
        assert _mode(root / ".env") == 0o600


def test_bootstrap_override_wins_and_only_sets_bootstrap_environment(
    monkeypatch, tmp_path: Path, caplog,
) -> None:
    # Given: a caller-supplied synthetic override and an unrelated environment canary.
    override = tmp_path / "override"
    monkeypatch.setenv("BOOTSTRAP_CANARY", "unchanged")
    monkeypatch.delenv("IZ_CNA_ENV_FILE", raising=False)
    monkeypatch.delenv("IZ_CNA_LOCAL_APP_DATA_DIR", raising=False)
    before = dict(os.environ)
    sensitive_path = override
    original_open = os.open

    def deny_directory_open(path, *args, **kwargs):
        if Path(path) == sensitive_path:
            raise PermissionError(f"denied: {sensitive_path}")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", deny_directory_open)

    # When: bootstrap creates the profile at the explicit override.
    with caplog.at_level(logging.DEBUG, logger="app.macos_bootstrap"):
        result = bootstrap(data_dir_override=override)

    # Then: only the two documented bootstrap variables change.
    assert result.code is BootstrapCode.READY
    assert result.local_app_data_dir == override
    assert Path(os.environ["IZ_CNA_ENV_FILE"]) == override / ".env"
    assert Path(os.environ["IZ_CNA_LOCAL_APP_DATA_DIR"]) == override
    assert _environment_delta(before, dict(os.environ)) <= {
        "IZ_CNA_ENV_FILE",
        "IZ_CNA_LOCAL_APP_DATA_DIR",
    }
    assert os.environ["BOOTSTRAP_CANARY"] == "unchanged"
    assert "directory synchronization is unavailable" in caplog.text
    assert str(sensitive_path) not in caplog.text


def test_first_env_contains_semantic_fields_with_disabled_gates(tmp_path: Path) -> None:
    # Given: a fresh synthetic application-data root.
    root = tmp_path / "profile"

    # When: bootstrap generates the first local configuration.
    result = bootstrap(data_dir_override=root)
    assert result.env_file is not None
    values = dict(
        line.split("=", 1)
        for line in result.env_file.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )

    # Then: Windows-compatible fields exist and optional integrations stay disabled.
    assert result.code is BootstrapCode.READY
    assert values["ENVIRONMENT"] == "local-client"
    assert values["DATABASE_BACKEND"] == "sqlite"
    assert values["LOCAL_SQLITE_DB_PATH"] == "clinical-notes-analyzer.sqlite3"
    assert values["LLM_ENABLED"] == "false"
    assert values["EMR_API_ENABLED"] == "false"
    assert values["ALLEVA_TREATMENT_PLAN_SYNC_ENABLED"] == "false"
    assert values["ALLEVA_TREATMENT_PLAN_SYNC_APPROVED"] == "false"
    assert values["ALLEVA_TREATMENT_PLAN_ENDPOINT_MAPPING_VALIDATED"] == "false"


def test_existing_env_is_byte_identical_and_not_overwritten(tmp_path: Path) -> None:
    # Given: a private existing file containing a synthetic preservation canary.
    root = tmp_path / "profile"
    root.mkdir(mode=0o700)
    env_file = root / ".env"
    expected = b"SYNTHETIC_CANARY=keep-exact-bytes\n"
    env_file.write_bytes(expected)
    os.chmod(env_file, 0o600)

    # When: bootstrap opens an already initialized profile.
    result = bootstrap(data_dir_override=root)

    # Then: the existing bytes and permissions remain unchanged.
    assert result.code is BootstrapCode.READY
    assert result.created_env is False
    assert env_file.read_bytes() == expected
    if os.name == "posix":
        assert _mode(env_file) == 0o600


def test_concurrent_initialization_has_one_stable_env(tmp_path: Path) -> None:
    # Given: independent callers racing to initialize one synthetic profile.
    root = tmp_path / "profile"
    barrier = Barrier(8)
    results: list[BootstrapResult] = []

    def initialize() -> None:
        barrier.wait()
        results.append(bootstrap(data_dir_override=root))

    threads = [Thread(target=initialize) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # Then: every caller observes ready state and one byte-identical file exists.
    assert len(results) == 8
    assert all(result.code is BootstrapCode.READY for result in results)
    assert sum(result.created_env for result in results) == 1
    assert {
        (result.code, result.local_app_data_dir, result.env_file)
        for result in results
    } == {(BootstrapCode.READY, root, root / ".env")}
    assert len(list(root.glob(".env.*"))) == 0


def test_invalid_relative_override_does_not_mutate_environment(monkeypatch, tmp_path: Path) -> None:
    # Given: a relative override and a preexisting environment canary.
    monkeypatch.setenv("IZ_CNA_ENV_FILE", "synthetic-existing-env")
    monkeypatch.setenv("IZ_CNA_LOCAL_APP_DATA_DIR", "synthetic-existing-root")
    before = dict(os.environ)

    # When: bootstrap rejects the unsafe path.
    result = bootstrap(data_dir_override=Path("relative-profile"))

    # Then: the failure is typed and no environment or filesystem state changes.
    assert result.code is BootstrapCode.INVALID_DATA_DIR
    assert _environment_delta(before, dict(os.environ)) == set()
    assert not (tmp_path / "relative-profile").exists()


def test_unsafe_existing_root_permissions_fail_without_mutation(tmp_path: Path) -> None:
    if os.name != "posix":
        return
    # Given: an existing synthetic root with group/other access.
    root = tmp_path / "profile"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o755)

    # When: bootstrap validates the existing root.
    result = bootstrap(data_dir_override=root)

    # Then: it refuses to create mutable state and does not repair permissions silently.
    assert result.code is BootstrapCode.UNSAFE_DATA_DIR
    assert _mode(root) == 0o755
    assert not (root / ".env").exists()


def test_unsafe_existing_env_permissions_fail_without_mutation(tmp_path: Path) -> None:
    if os.name != "posix":
        return
    # Given: a private root with an environment file that is too permissive.
    root = tmp_path / "profile"
    root.mkdir(mode=0o700)
    env_file = root / ".env"
    expected = b"SYNTHETIC_SECRET=do-not-print\n"
    env_file.write_bytes(expected)
    os.chmod(env_file, 0o644)

    # When: bootstrap validates the existing environment file.
    result = bootstrap(data_dir_override=root)

    # Then: it refuses the unsafe file without changing its bytes or permissions.
    assert result.code is BootstrapCode.UNSAFE_ENV_FILE
    assert env_file.read_bytes() == expected
    assert _mode(env_file) == 0o644


def test_bootstrap_imports_no_application_modules(tmp_path: Path) -> None:
    # Given: a fresh interpreter with only the bootstrap module requested.
    root = tmp_path / "profile"
    code = (
        "import sys; "
        "from app.macos_bootstrap import bootstrap; "
        f"result = bootstrap(data_dir_override={str(root)!r}); "
        "assert result.code.value == 'ready'; "
        "assert 'app.core.config' not in sys.modules; "
        "assert 'app.v2.db' not in sys.modules; "
        "print('bootstrap_import_boundary=PASS')"
    )

    # When: the bootstrap module runs in isolation.
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: application/database modules remain unimported and output is a safe code only.
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "bootstrap_import_boundary=PASS"
