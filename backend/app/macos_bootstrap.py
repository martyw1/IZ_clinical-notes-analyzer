from __future__ import annotations

import logging
import os
import secrets
import stat
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

MACOS_APP_NAME: Final = "IZ Clinical Notes Analyzer"
ENV_FILE_NAME: Final = ".env"
PRIVATE_DIRECTORY_MODE: Final = 0o700
PRIVATE_FILE_MODE: Final = 0o600
POSIX_PERMISSIONS: Final = os.name == "posix"
LOGGER = logging.getLogger(__name__)


class BootstrapCode(StrEnum):
    READY = "ready"
    INVALID_DATA_DIR = "invalid_data_dir"
    UNSAFE_DATA_DIR = "unsafe_data_dir"
    UNSAFE_ENV_FILE = "unsafe_env_file"
    FILESYSTEM_ERROR = "filesystem_error"


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    code: BootstrapCode
    local_app_data_dir: Path | None = None
    env_file: Path | None = None
    created_env: bool = False

    @property
    def ok(self) -> bool:
        return self.code is BootstrapCode.READY


class _BootstrapError(Exception):
    def __init__(self, code: BootstrapCode) -> None:
        self.code = code
        super().__init__(code.value)


def _resolve_data_dir(home: Path | None, override: str | Path | None) -> Path:
    configured = override
    if configured is None:
        configured_value = os.environ.get("IZ_CNA_LOCAL_APP_DATA_DIR", "").strip()
        configured = configured_value or None
    root = (
        Path(configured).expanduser()
        if configured is not None
        else (home if home is not None else Path.home())
        / "Library"
        / "Application Support"
        / MACOS_APP_NAME
    )
    if not root.is_absolute():
        raise _BootstrapError(BootstrapCode.INVALID_DATA_DIR)
    return root


def _assert_private_directory(root: Path) -> None:
    if root.is_symlink():
        raise _BootstrapError(BootstrapCode.UNSAFE_DATA_DIR)
    created = False
    if not root.exists():
        try:
            root.mkdir(mode=PRIVATE_DIRECTORY_MODE, parents=True)
            created = True
        except FileExistsError:
            if root.is_symlink() or not root.is_dir():
                raise _BootstrapError(BootstrapCode.UNSAFE_DATA_DIR)
            created = False
        except OSError as exc:
            raise _BootstrapError(BootstrapCode.FILESYSTEM_ERROR) from exc
        if created:
            try:
                os.chmod(root, PRIVATE_DIRECTORY_MODE)
            except OSError as exc:
                raise _BootstrapError(BootstrapCode.FILESYSTEM_ERROR) from exc
    if not root.is_dir():
        raise _BootstrapError(BootstrapCode.UNSAFE_DATA_DIR)
    try:
        mode = stat.S_IMODE(root.stat().st_mode)
    except OSError as exc:
        raise _BootstrapError(BootstrapCode.FILESYSTEM_ERROR) from exc
    if POSIX_PERMISSIONS and mode != PRIVATE_DIRECTORY_MODE:
        raise _BootstrapError(BootstrapCode.UNSAFE_DATA_DIR)


def _read_existing_env(env_file: Path) -> bytes | None:
    if env_file.is_symlink():
        raise _BootstrapError(BootstrapCode.UNSAFE_ENV_FILE)
    if not env_file.exists():
        return None
    if not env_file.is_file():
        raise _BootstrapError(BootstrapCode.UNSAFE_ENV_FILE)
    try:
        mode = stat.S_IMODE(env_file.stat().st_mode)
    except OSError as exc:
        raise _BootstrapError(BootstrapCode.FILESYSTEM_ERROR) from exc
    if POSIX_PERMISSIONS and mode != PRIVATE_FILE_MODE:
        raise _BootstrapError(BootstrapCode.UNSAFE_ENV_FILE)
    try:
        content = env_file.read_bytes()
    except OSError as exc:
        raise _BootstrapError(BootstrapCode.FILESYSTEM_ERROR) from exc
    return content


def _new_env_contents() -> bytes:
    secret_key = secrets.token_hex(32)
    encryption_key = secrets.token_hex(32)
    admin_password = secrets.token_urlsafe(32)
    lines = (
        f"APP_NAME={MACOS_APP_NAME}",
        "ENVIRONMENT=local-client",
        "BACKEND_PORT=8000",
        "FRONTEND_PORT=5173",
        "DATABASE_BACKEND=sqlite",
        "LOCAL_SQLITE_DB_PATH=clinical-notes-analyzer.sqlite3",
        "DATABASE_URL=",
        f"SECRET_KEY={secret_key}",
        f"DATA_ENCRYPTION_KEY={encryption_key}",
        "FRONTEND_ORIGIN=http://localhost:8000",
        "FRONTEND_ORIGINS=http://localhost:8000,http://localhost:5173",
        "ALLOWED_HOSTS=localhost,127.0.0.1,::1,testserver",
        "UPLOAD_DIR=uploads",
        "LOG_DIR=logs",
        "RULES_CONFIG_PATH=config/rules/alleva_treatment_plan_completeness_rules.yaml",
        "BOOTSTRAP_ADMIN_USERNAME=admin",
        f"BOOTSTRAP_ADMIN_PASSWORD={admin_password}",
        "RESET_BOOTSTRAP_ADMIN_ON_STARTUP=true",
        "LLM_ENABLED=false",
        "EMR_API_ENABLED=false",
        "ALLEVA_TREATMENT_PLAN_SYNC_ENABLED=false",
        "ALLEVA_TREATMENT_PLAN_SYNC_APPROVED=false",
        "ALLEVA_TREATMENT_PLAN_ENDPOINT_MAPPING_VALIDATED=false",
        "ALLEVA_LIVE_SYNC_ENABLED=false",
        "",
    )
    return "\n".join(lines).encode("utf-8")


def _sync_directory(root: Path) -> None:
    directory_flag = getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(root, os.O_RDONLY | directory_flag)
    except OSError:
        LOGGER.debug("directory synchronization is unavailable")
        return
    try:
        os.fsync(descriptor)
    except OSError:
        LOGGER.debug("directory synchronization failed")
        return
    finally:
        os.close(descriptor)


def _create_env_atomically(root: Path, env_file: Path, content: bytes) -> bool:
    descriptor = -1
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=".env.", dir=root)
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_path, PRIVATE_FILE_MODE)
        try:
            os.link(temporary_path, env_file)
        except FileExistsError:
            return False
        _sync_directory(root)
        return True
    except OSError as exc:
        raise _BootstrapError(BootstrapCode.FILESYSTEM_ERROR) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _ensure_env_file(root: Path) -> tuple[Path, bool]:
    env_file = root / ENV_FILE_NAME
    if _read_existing_env(env_file) is not None:
        return env_file, False
    content = _new_env_contents()
    if _create_env_atomically(root, env_file, content):
        return env_file, True
    if _read_existing_env(env_file) is None:
        raise _BootstrapError(BootstrapCode.FILESYSTEM_ERROR)
    return env_file, False


def bootstrap(
    *,
    home: Path | None = None,
    data_dir_override: str | Path | None = None,
) -> BootstrapResult:
    try:
        root = _resolve_data_dir(home, data_dir_override)
        _assert_private_directory(root)
        env_file, created_env = _ensure_env_file(root)
    except _BootstrapError as exc:
        return BootstrapResult(code=exc.code)
    except (OSError, RuntimeError, ValueError):
        return BootstrapResult(code=BootstrapCode.FILESYSTEM_ERROR)
    os.environ["IZ_CNA_LOCAL_APP_DATA_DIR"] = str(root)
    os.environ["IZ_CNA_ENV_FILE"] = str(env_file)
    return BootstrapResult(
        code=BootstrapCode.READY,
        local_app_data_dir=root,
        env_file=env_file,
        created_env=created_env,
    )
