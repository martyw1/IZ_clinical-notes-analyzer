from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONFIGURATION_NAMES = frozenset({"ENVIRONMENT", "BACKEND_PORT", "SECRET_KEY", "DATA_ENCRYPTION_KEY", "LOCAL_SQLITE_DB_PATH", "BOOTSTRAP_ADMIN_USERNAME", "BOOTSTRAP_ADMIN_PASSWORD", "FRONTEND_ORIGINS", "ALLOWED_HOSTS", "LLM_ENABLED", "EMR_API_ENABLED", "ALLEVA_TREATMENT_PLAN_SYNC_ENABLED"})
CANONICAL_ENV_NAMES = frozenset({"ENVIRONMENT", "BACKEND_PORT", "IZ_CNA_LOCAL_SQLITE_DB_PATH", "IZ_CNA_SECRET_KEY", "IZ_CNA_DATA_ENCRYPTION_KEY", "IZ_CNA_BOOTSTRAP_ADMIN_USERNAME", "IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD", "FRONTEND_ORIGINS", "ALLOWED_HOSTS", "LLM_ENABLED", "EMR_API_ENABLED", "ALLEVA_TREATMENT_PLAN_SYNC_ENABLED"})


class _Lease:
    def __init__(self, canonical_id: str, held: bool = True) -> None:
        self.canonical_data_dir_id = canonical_id
        self.held = held

    def is_held_by_current_process(self) -> bool:
        return self.held

    def release(self) -> None:
        self.held = False


class _LocalPrivateStorage:
    def __init__(self, resource_root: Path, *, fail_directory_privacy: bool = False) -> None:
        self.resource_root = resource_root
        self.fail_directory_privacy = fail_directory_privacy
        self.events: list[str] = []

    def canonical_data_dir_id(self, path: Path) -> str:
        self.events.append("canonical")
        normalized = str(path.resolve())
        return normalized.casefold() if os.name == "nt" else normalized

    def create_private_directory(self, path: Path) -> None:
        self.events.append("create_directory")
        if self.fail_directory_privacy:
            raise PermissionError("synthetic privacy failure")
        path.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            path.chmod(0o700)

    def verify_private_directory(self, path: Path) -> None:
        self.events.append("verify_directory")
        assert path.is_dir() and not path.is_symlink()
        if os.name != "nt":
            assert stat.S_IMODE(path.stat().st_mode) == 0o700

    def open_private_file(self, path: Path) -> int:
        self.events.append("open_file")
        return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)

    def verify_private_file(self, path: Path) -> None:
        self.events.append("verify_file")
        assert path.is_file() and not path.is_symlink()
        if os.name != "nt":
            assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def sync_directory(self, path: Path) -> None:
        self.events.append("sync_directory")
        if os.name == "nt":
            return
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


class _VolumeProvider:
    def __init__(self, *, case_sensitive: bool, volume_id: str = "synthetic-volume") -> None:
        self.case_sensitive = case_sensitive
        self.volume_id = volume_id

    def identity_for_path(self, path: Path):
        from app.core.platform_paths import VolumeIdentity

        assert path.exists()
        return VolumeIdentity(identifier=self.volume_id, case_sensitive=self.case_sensitive)


def _safe_env(port: int = 8123) -> bytes:
    lines = ("ENVIRONMENT=local-client", f"BACKEND_PORT={port}", "IZ_CNA_LOCAL_SQLITE_DB_PATH=clinical-notes-analyzer-v2.sqlite3", f"IZ_CNA_SECRET_KEY={'a1' * 32}", f"IZ_CNA_DATA_ENCRYPTION_KEY={'b2' * 32}", "IZ_CNA_BOOTSTRAP_ADMIN_USERNAME=admin", "IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD=SyntheticBootstrapPass123", f"FRONTEND_ORIGINS=http://localhost:{port},http://127.0.0.1:{port}", "ALLOWED_HOSTS=localhost,127.0.0.1,::1", "LLM_ENABLED=false", "EMR_API_ENABLED=false", "ALLEVA_TREATMENT_PLAN_SYNC_ENABLED=false")
    return ("\n".join(lines) + "\n").encode()


def _process_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.startswith("IZ_CNA_") or name in CONFIGURATION_NAMES:
            environment.pop(name)
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(REPOSITORY_ROOT / "backend"), str(REPOSITORY_ROOT / "backend" / "tests"))
    )
    return environment


def _subprocess_bootstrap(data_root: Path, resource_root: Path) -> None:
    assert "app.core.config" not in sys.modules
    assert "app.v2.db" not in sys.modules
    assert "sqlalchemy" not in sys.modules
    from app.desktop.bootstrap import bootstrap_desktop

    storage = _LocalPrivateStorage(resource_root)
    lease = _Lease(storage.canonical_data_dir_id(data_root))
    credential = bootstrap_desktop(data_root, lease, storage)
    assert "app.core.config" not in sys.modules
    assert "app.v2.db" not in sys.modules
    assert "sqlalchemy" not in sys.modules
    from app.core.config import settings

    assert settings.local_app_data_dir == data_root.resolve()
    assert "app.v2.db" not in sys.modules
    from app.v2.db import engine

    assert Path(engine.url.database).resolve() == settings.sqlite_db_path.resolve()
    digest = hashlib.sha256(f"{credential.username}:{credential.password}".encode()).hexdigest()
    print(json.dumps({"credential_sha256": digest, "events": storage.events}))


def _bootstrap_command(data_root: Path, resource_root: Path) -> list[str]:
    code = (
        "from pathlib import Path; "
        "from test_desktop_bootstrap import _subprocess_bootstrap; "
        f"_subprocess_bootstrap(Path({str(data_root)!r}), Path({str(resource_root)!r}))"
    )
    return [sys.executable, "-c", code]


def test_platform_roots_and_frozen_resource_separation(tmp_path: Path) -> None:
    # Given: exact synthetic Windows/macOS environments and a frozen resource bundle.
    from app.core.platform_paths import PlatformPathContext, resolve_local_app_data_dir, resolve_resource_root

    bundle = tmp_path / "bundle"
    module = tmp_path / "source" / "backend" / "app" / "core" / "config.py"
    windows_base, mac_home, override = tmp_path / "win", tmp_path / "home", tmp_path / "override"

    # When: each target platform and the explicit override are resolved without writes.
    resource = resolve_resource_root(module, bundle)
    working = tmp_path / "working"
    windows = resolve_local_app_data_dir(resource, PlatformPathContext("win32", {"LOCALAPPDATA": str(windows_base)}, tmp_path, working, True))
    macos = resolve_local_app_data_dir(resource, PlatformPathContext("darwin", {}, mac_home, working, True))
    selected = resolve_local_app_data_dir(resource, PlatformPathContext("darwin", {"IZ_CNA_LOCAL_APP_DATA_DIR": str(override)}, mac_home, working, True))

    # Then: immutable resources and exact OS-local mutable roots are distinct.
    assert resource == bundle.resolve()
    assert windows == (windows_base / "IZ Clinical Notes Analyzer").resolve()
    assert macos == (mac_home / "Library" / "Application Support" / "IZ Clinical Notes Analyzer").resolve()
    assert selected == override.resolve()
    assert len({resource, windows, macos, selected}) == 4
    assert not any(path.exists() for path in (bundle, windows, macos, selected))


def test_canonical_data_dir_id_obeys_platform_volume_case_rules(tmp_path: Path) -> None:
    # Given: two case aliases on one synthetic volume.
    from app.core.platform_paths import canonical_data_dir_id

    first, second = tmp_path / "ProfileCase", tmp_path / "profilecase"

    # When: Windows, insensitive macOS, and sensitive macOS identities are computed.
    windows = (canonical_data_dir_id(first, "win32", _VolumeProvider(case_sensitive=True)), canonical_data_dir_id(second, "win32", _VolumeProvider(case_sensitive=True)))
    mac_insensitive = (canonical_data_dir_id(first, "darwin", _VolumeProvider(case_sensitive=False)), canonical_data_dir_id(second, "darwin", _VolumeProvider(case_sensitive=False)))
    mac_sensitive = (canonical_data_dir_id(first, "darwin", _VolumeProvider(case_sensitive=True)), canonical_data_dir_id(second, "darwin", _VolumeProvider(case_sensitive=True)))

    # Then: only a case-sensitive macOS volume preserves the distinction.
    assert windows[0] == windows[1]
    assert mac_insensitive[0] == mac_insensitive[1]
    assert mac_sensitive[0] != mac_sensitive[1]


def test_fresh_subprocess_bootstraps_before_config_and_database(tmp_path: Path) -> None:
    # Given: a fresh interpreter, held lease, and private filesystem adapter.
    data_root, resource_root = tmp_path / "data", tmp_path / "resources"

    # When: bootstrap runs before configuration and database imports.
    completed = subprocess.run(_bootstrap_command(data_root, resource_root), env=_process_environment(), capture_output=True, text=True, check=False)

    # Then: the subprocess records private checks before publication and constructs the engine afterward.
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["events"].index("verify_directory") < payload["events"].index("open_file")
    assert (data_root / ".env").is_file()
    assert not (data_root / "clinical-notes-analyzer-v2.sqlite3").exists()


def test_bootstrap_rejects_unsafe_existing_env_without_replacement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a private existing file with one unsafe required secret.
    from app.desktop.bootstrap import DesktopBootstrapError, bootstrap_desktop

    storage, data_root = _LocalPrivateStorage(tmp_path / "resources"), tmp_path / "data"
    storage.create_private_directory(data_root)
    env_file = data_root / ".env"
    env_file.write_bytes(_safe_env().replace(b"a1" * 32, b"change-me"))
    if os.name != "nt":
        env_file.chmod(0o600)
    before = hashlib.sha256(env_file.read_bytes()).digest()

    # When/Then: validation fails closed without changing any byte.
    with pytest.raises(DesktopBootstrapError, match="desktop_environment_unsafe"):
        bootstrap_desktop(data_root, _Lease(storage.canonical_data_dir_id(data_root)), storage)
    assert hashlib.sha256(env_file.read_bytes()).digest() == before


def test_bootstrap_rejects_resource_descendant_data_root(tmp_path: Path) -> None:
    # Given: a mutable candidate beneath the frozen resource tree.
    from app.desktop.bootstrap import DesktopBootstrapError, bootstrap_desktop

    resource_root, data_root = tmp_path / "bundle", tmp_path / "bundle" / "data"
    storage = _LocalPrivateStorage(resource_root)

    # When/Then: bootstrap rejects it before creating directories or files.
    with pytest.raises(DesktopBootstrapError, match="desktop_data_dir_is_immutable"):
        bootstrap_desktop(data_root, _Lease(storage.canonical_data_dir_id(data_root)), storage)
    assert not resource_root.exists()


def test_concurrent_bootstrap_is_atomic(tmp_path: Path) -> None:
    # Given: two fresh processes targeting the same private data directory.
    data_root, resource_root = tmp_path / "data", tmp_path / "resources"
    command, environment = _bootstrap_command(data_root, resource_root), _process_environment()

    # When: both writers race without coordinating through a real launch lease.
    processes = [subprocess.Popen(command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    results = [process.communicate() + (process.returncode,) for process in processes]

    # Then: both observe one complete credential set and no publication temporary remains.
    assert all(returncode == 0 for _stdout, _stderr, returncode in results), results
    assert len({json.loads(stdout)["credential_sha256"] for stdout, _stderr, _returncode in results}) == 1
    assert _safe_required_names(data_root / ".env")
    assert tuple(data_root.glob(".*.tmp")) == ()


@pytest.mark.parametrize("lease_state", ("missing", "unheld", "mismatched"))
def test_bootstrap_requires_matching_held_lease(tmp_path: Path, lease_state: str) -> None:
    # Given: a missing, unheld, or mismatched lease.
    from app.desktop.bootstrap import DesktopBootstrapError, bootstrap_desktop

    storage, data_root = _LocalPrivateStorage(tmp_path / "resources"), tmp_path / "data"
    expected = storage.canonical_data_dir_id(data_root)
    lease = None if lease_state == "missing" else _Lease(expected, held=False) if lease_state == "unheld" else _Lease("other-volume:data")

    # When/Then: bootstrap refuses storage mutation.
    with pytest.raises(DesktopBootstrapError, match="desktop_data_dir_lease_invalid"):
        bootstrap_desktop(data_root, lease, storage)
    assert not data_root.exists()


def test_no_secret_bytes_written_before_private_storage(tmp_path: Path) -> None:
    # Given: a storage provider that cannot establish directory privacy.
    from app.desktop.bootstrap import bootstrap_desktop

    storage, data_root = _LocalPrivateStorage(tmp_path / "resources", fail_directory_privacy=True), tmp_path / "data"

    # When: bootstrap reaches the privacy boundary.
    with pytest.raises(PermissionError, match="synthetic privacy failure"):
        bootstrap_desktop(data_root, _Lease(storage.canonical_data_dir_id(data_root)), storage)

    # Then: no file open or credential bytes precede that successful boundary.
    assert "open_file" not in storage.events
    assert not data_root.exists()


def test_pending_password_handoff_survives_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a first bootstrap whose in-memory handoff is lost before database startup.
    from app.desktop.bootstrap import bootstrap_desktop

    storage, data_root = _LocalPrivateStorage(tmp_path / "resources"), tmp_path / "data"
    lease = _Lease(storage.canonical_data_dir_id(data_root))
    first = bootstrap_desktop(data_root, lease, storage)
    before = hashlib.sha256((data_root / ".env").read_bytes()).digest()

    # When: a restarted process bootstraps from the existing private environment.
    restarted = _LocalPrivateStorage(tmp_path / "resources")
    second = bootstrap_desktop(data_root, _Lease(restarted.canonical_data_dir_id(data_root)), restarted)

    # Then: the candidate handoff is recoverable and the secret file is unchanged.
    assert (second.username, second.password) == (first.username, first.password)
    assert hashlib.sha256((data_root / ".env").read_bytes()).digest() == before


def test_existing_env_is_authoritative_and_ambient_credentials_are_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a safe private file plus conflicting ambient desktop configuration.
    from app.desktop.bootstrap import bootstrap_desktop

    storage, data_root = _LocalPrivateStorage(tmp_path / "resources"), tmp_path / "data"
    storage.create_private_directory(data_root)
    env_file = data_root / ".env"
    env_file.write_bytes(_safe_env(8123))
    if os.name != "nt":
        env_file.chmod(0o600)
    monkeypatch.setenv("IZ_CNA_SECRET_KEY", "ambient-value-must-not-win")
    monkeypatch.setenv("IZ_CNA_PORT", "9001")

    # When: packaged bootstrap selects the private file.
    with pytest.warns(RuntimeWarning) as recorded:
        bootstrap_desktop(data_root, _Lease(storage.canonical_data_dir_id(data_root)), storage)

    # Then: only a safe reason code is emitted and file-backed port/configuration wins.
    assert [str(item.message) for item in recorded] == ["desktop_ambient_configuration_ignored"]
    assert "IZ_CNA_SECRET_KEY" not in os.environ
    assert os.environ["IZ_CNA_PORT"] == "8123"


def test_bootstrap_revalidates_native_identity_after_directory_creation(tmp_path: Path) -> None:
    # Given: a provider whose native volume identity changes when the directory appears.
    from app.desktop.bootstrap import DesktopBootstrapError, bootstrap_desktop

    class ReboundStorage(_LocalPrivateStorage):
        def canonical_data_dir_id(self, path: Path) -> str:
            return f"volume-{'after' if path.exists() else 'before'}:{path.name}"

    storage, data_root = ReboundStorage(tmp_path / "resources"), tmp_path / "data"

    # When/Then: post-creation identity drift fails before any secret file opens.
    with pytest.raises(DesktopBootstrapError, match="desktop_data_dir_identity_changed"):
        bootstrap_desktop(data_root, _Lease(storage.canonical_data_dir_id(data_root)), storage)
    assert not (data_root / ".env").exists()
    assert "open_file" not in storage.events


def test_immutable_bundle_boundaries_reject_app_contents_dmg_cwd_and_symlink(tmp_path: Path) -> None:
    # Given: resource roots representing PyInstaller, an app bundle, a mounted DMG, and a symlink alias.
    from app.core.platform_paths import PlatformPathError, assert_mutable_path_outside_resources

    app_resources = tmp_path / "Synthetic.app" / "Contents" / "Resources"
    cases = (
        (tmp_path / "_MEIPASS" / "data", tmp_path / "_MEIPASS"),
        (tmp_path / "Synthetic.app" / "Contents" / "data", app_resources),
        (Path("/Volumes/Synthetic/Mutable"), Path("/Volumes/Synthetic/Synthetic.app/Contents/Resources")),
        (Path.cwd() / "synthetic-data", Path.cwd()),
    )

    # When/Then: every lexical immutable boundary fails closed without writes.
    for data_root, resource_root in cases:
        with pytest.raises(PlatformPathError, match="desktop_data_dir_is_immutable"):
            assert_mutable_path_outside_resources(data_root, resource_root)
    assert not any(data_root.exists() for data_root, _resource_root in cases[:2])

    resource = tmp_path / "real-resource"
    resource.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(resource, target_is_directory=True)
    except OSError:
        return
    with pytest.raises(PlatformPathError, match="desktop_data_dir_is_immutable"):
        assert_mutable_path_outside_resources(alias / "data", resource)


def test_generated_env_is_private_on_posix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the real POSIX exclusive-open adapter behavior used by the macOS test runner.
    if os.name == "nt":
        pytest.skip("Task 8 owns Windows ACL enforcement")
    from app.desktop.bootstrap import bootstrap_desktop

    storage, data_root = _LocalPrivateStorage(tmp_path / "resources"), tmp_path / "data"

    # When: a new desktop environment is published.
    bootstrap_desktop(data_root, _Lease(storage.canonical_data_dir_id(data_root)), storage)

    # Then: its first descriptor and final link retain mode 0600.
    assert stat.S_IMODE((data_root / ".env").stat().st_mode) == 0o600


def _safe_required_names(env_file: Path) -> bool:
    names = {line.partition("=")[0] for line in env_file.read_text(encoding="utf-8").splitlines()}
    return CANONICAL_ENV_NAMES <= names
