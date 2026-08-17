from __future__ import annotations

import os
import secrets
import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Final, Protocol
from urllib.parse import urlsplit

from app.core.platform_paths import PlatformPathError, assert_mutable_path_outside_resources
from app.desktop.ownership import DataDirLease


class DesktopBootstrapError(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)

    def __str__(self) -> str:
        return self.reason_code


@dataclass(frozen=True, slots=True)
class BootstrapCredential:
    username: str
    password: str = field(repr=False)


class PrivateStorageProvider(Protocol):
    @property
    def resource_root(self) -> Path: ...

    def canonical_data_dir_id(self, path: Path) -> str: ...

    def create_private_directory(self, path: Path) -> None: ...

    def verify_private_directory(self, path: Path) -> None: ...

    def open_private_file(self, path: Path) -> int: ...

    def verify_private_file(self, path: Path) -> None: ...

    def sync_directory(self, path: Path) -> None: ...


_SAFE_AMBIENT: Final = frozenset({"IZ_CNA_LOCAL_APP_DATA_DIR", "IZ_CNA_PORT"})
_APPLICATION_ENV: Final = frozenset(
    {
        "APP_NAME", "APP_VERSION", "BUILD_CHANNEL", "ENVIRONMENT", "BACKEND_PORT", "FRONTEND_PORT",
        "DATABASE_BACKEND", "DATABASE_URL", "SECRET_KEY", "DATA_ENCRYPTION_KEY", "LOCAL_SQLITE_DB_PATH",
        "BOOTSTRAP_ADMIN_USERNAME", "BOOTSTRAP_ADMIN_PASSWORD", "RESET_BOOTSTRAP_ADMIN_ON_STARTUP",
        "FRONTEND_ORIGIN", "FRONTEND_ORIGINS", "ALLOWED_HOSTS", "UPLOAD_DIR", "LOG_DIR", "RULES_CONFIG_PATH",
        "LLM_ENABLED", "EMR_API_ENABLED", "ALLEVA_TREATMENT_PLAN_SYNC_ENABLED",
    }
)
_REQUIRED_ENV: Final = frozenset(
    {
        "ENVIRONMENT", "BACKEND_PORT", "IZ_CNA_LOCAL_SQLITE_DB_PATH", "IZ_CNA_SECRET_KEY",
        "IZ_CNA_DATA_ENCRYPTION_KEY", "IZ_CNA_BOOTSTRAP_ADMIN_USERNAME", "IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD",
        "FRONTEND_ORIGINS", "ALLOWED_HOSTS", "LLM_ENABLED", "EMR_API_ENABLED",
        "ALLEVA_TREATMENT_PLAN_SYNC_ENABLED",
    }
)
_SECRET_ALPHABET: Final = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"


def bootstrap_desktop(
    data_root: Path,
    held_lease: DataDirLease | None,
    private_storage: PrivateStorageProvider,
) -> BootstrapCredential:
    try:
        assert_mutable_path_outside_resources(data_root, private_storage.resource_root)
    except PlatformPathError as exc:
        raise DesktopBootstrapError(exc.reason_code) from exc
    expected_id = private_storage.canonical_data_dir_id(data_root)
    if held_lease is None or not held_lease.is_held_by_current_process() or held_lease.canonical_data_dir_id != expected_id:
        raise DesktopBootstrapError("desktop_data_dir_lease_invalid")
    ambient_port = os.environ.get("IZ_CNA_PORT", "").strip()
    _sanitize_ambient_configuration()
    private_storage.create_private_directory(data_root)
    private_storage.verify_private_directory(data_root)
    if private_storage.canonical_data_dir_id(data_root) != expected_id:
        raise DesktopBootstrapError("desktop_data_dir_identity_changed")
    env_file = data_root / ".env"
    if env_file.exists():
        selected = _read_environment(env_file, private_storage)
    else:
        port = _port(ambient_port or "8000")
        content, selected = _new_environment(port)
        selected = _publish_environment(env_file, content, selected, private_storage)
    os.environ["IZ_CNA_ENV_FILE"] = str(env_file.resolve())
    os.environ["IZ_CNA_LOCAL_APP_DATA_DIR"] = str(data_root.resolve())
    os.environ["IZ_CNA_PORT"] = str(selected.port)
    return selected.credential


@dataclass(frozen=True, slots=True)
class _SelectedEnvironment:
    credential: BootstrapCredential
    port: int


def _sanitize_ambient_configuration() -> None:
    ignored = False
    for name in tuple(os.environ):
        if name in _SAFE_AMBIENT:
            continue
        if name.startswith("IZ_CNA_") or name in _APPLICATION_ENV:
            os.environ.pop(name)
            ignored = True
    if ignored:
        warnings.warn("desktop_ambient_configuration_ignored", RuntimeWarning, stacklevel=2)


def _new_environment(port: int) -> tuple[bytes, _SelectedEnvironment]:
    secret_key = _random_secret(64)
    encryption_key = _random_secret(64)
    password = _random_secret(24)
    values = {
        "ENVIRONMENT": "local-client",
        "BACKEND_PORT": str(port),
        "IZ_CNA_LOCAL_SQLITE_DB_PATH": "clinical-notes-analyzer-v2.sqlite3",
        "IZ_CNA_SECRET_KEY": secret_key,
        "IZ_CNA_DATA_ENCRYPTION_KEY": encryption_key,
        "IZ_CNA_BOOTSTRAP_ADMIN_USERNAME": "admin",
        "IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD": password,
        "FRONTEND_ORIGINS": f"http://localhost:{port},http://127.0.0.1:{port}",
        "ALLOWED_HOSTS": "localhost,127.0.0.1,::1",
        "LLM_ENABLED": "false",
        "EMR_API_ENABLED": "false",
        "ALLEVA_TREATMENT_PLAN_SYNC_ENABLED": "false",
    }
    content = ("\n".join(f"{name}={value}" for name, value in values.items()) + "\n").encode()
    return content, _validate_environment(values)


def _publish_environment(
    env_file: Path,
    content: bytes,
    selected: _SelectedEnvironment,
    private_storage: PrivateStorageProvider,
) -> _SelectedEnvironment:
    temporary = env_file.with_name(f".{env_file.name}.{secrets.token_hex(16)}.tmp")
    descriptor = private_storage.open_private_file(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        private_storage.verify_private_file(temporary)
        try:
            os.link(temporary, env_file)
        except FileExistsError:
            return _read_environment(env_file, private_storage)
        private_storage.verify_private_file(env_file)
        private_storage.sync_directory(env_file.parent)
        return selected
    finally:
        temporary.unlink(missing_ok=True)


def _read_environment(env_file: Path, private_storage: PrivateStorageProvider) -> _SelectedEnvironment:
    if env_file.is_symlink():
        raise DesktopBootstrapError("desktop_environment_unsafe")
    private_storage.verify_private_file(env_file)
    try:
        text = env_file.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise DesktopBootstrapError("desktop_environment_unsafe") from exc
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if not separator or not name.strip() or name.strip() in values:
            raise DesktopBootstrapError("desktop_environment_unsafe")
        values[name.strip()] = value.strip()
    return _validate_environment(values)


def _validate_environment(values: Mapping[str, str]) -> _SelectedEnvironment:
    if not _REQUIRED_ENV <= values.keys() or values["ENVIRONMENT"].casefold() != "local-client":
        raise DesktopBootstrapError("desktop_environment_unsafe")
    port = _port(values["BACKEND_PORT"])
    password = values["IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD"]
    safe_password = len(password) >= 12 and any(char.isalpha() for char in password) and any(char.isdigit() for char in password)
    sqlite_path = PureWindowsPath(values["IZ_CNA_LOCAL_SQLITE_DB_PATH"])
    origins = tuple(item.strip() for item in values["FRONTEND_ORIGINS"].split(",") if item.strip())
    hosts = frozenset(item.strip() for item in values["ALLOWED_HOSTS"].split(",") if item.strip())
    safe = (
        len(values["IZ_CNA_SECRET_KEY"]) >= 32
        and len(values["IZ_CNA_DATA_ENCRYPTION_KEY"]) >= 32
        and bool(values["IZ_CNA_BOOTSTRAP_ADMIN_USERNAME"].strip())
        and safe_password
        and not sqlite_path.is_absolute()
        and ".." not in sqlite_path.parts
        and origins
        and all(_localhost_origin(origin, port) for origin in origins)
        and {"localhost", "127.0.0.1"} <= hosts <= {"localhost", "127.0.0.1", "::1", "testserver"}
        and all(values[name].casefold() == "false" for name in ("LLM_ENABLED", "EMR_API_ENABLED", "ALLEVA_TREATMENT_PLAN_SYNC_ENABLED"))
    )
    if not safe:
        raise DesktopBootstrapError("desktop_environment_unsafe")
    credential = BootstrapCredential(values["IZ_CNA_BOOTSTRAP_ADMIN_USERNAME"], password)
    return _SelectedEnvironment(credential, port)


def _localhost_origin(value: str, port: int) -> bool:
    try:
        parsed = urlsplit(value)
        return parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"} and parsed.port == port and not parsed.username and not parsed.password
    except ValueError:
        return False


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise DesktopBootstrapError("desktop_environment_unsafe") from exc
    if not 1 <= port <= 65535:
        raise DesktopBootstrapError("desktop_environment_unsafe")
    return port


def _random_secret(length: int) -> str:
    while True:
        value = "".join(secrets.choice(_SECRET_ALPHABET) for _ in range(length))
        if any(char.isalpha() for char in value) and any(char.isdigit() for char in value):
            return value
