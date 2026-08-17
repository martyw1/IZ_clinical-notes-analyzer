from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from app.core.platform_paths import PlatformPathContext, resolve_local_app_data_dir, resolve_resource_root

APP_NAME: Final = "IZ Clinical Notes Analyzer"
APP_VERSION: Final = "2.0.0-beta.2"
BUILD_CHANNEL: Final = "beta-local-desktop-v2"


def resolve_repository_root(module_path: Path, bundled_data_root: Path | None) -> Path:
    return resolve_resource_root(module_path, bundled_data_root)


_bundled_data_root = getattr(sys, "_MEIPASS", None) if getattr(sys, "frozen", False) else None
RESOURCE_ROOT: Final = resolve_resource_root(Path(__file__), Path(_bundled_data_root) if _bundled_data_root else None)
REPO_ROOT: Final = RESOURCE_ROOT
RESTRICTED_ENVIRONMENTS: Final = frozenset({"production", "local-client"})
UNSAFE_SECURITY_VALUES: Final = frozenset(
    {
        "",
        "admin",
        "change-me",
        "local-admin-pass1",
        "password",
        "password123",
        "v2-local-development-secret",
    }
)


@dataclass(frozen=True, slots=True)
class ConfigurationError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return self.reason


def _load_env_file() -> None:
    configured = os.environ.get("IZ_CNA_ENV_FILE", "").strip()
    if not configured:
        return
    env_path = Path(configured).expanduser()
    if not env_path.is_file():
        raise ConfigurationError("Configured environment file is unavailable")
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        normalized_name = name.strip()
        if normalized_name:
            os.environ.setdefault(normalized_name, value.strip().strip("\"'"))


_load_env_file()


def _env(canonical_name: str, generated_name: str, default: str = "") -> str:
    canonical = os.environ.get(canonical_name)
    if canonical is not None:
        return canonical
    return os.environ.get(generated_name, default)


def _validate_restricted_configuration(candidate: Settings) -> None:
    if candidate.environment.strip().lower() not in RESTRICTED_ENVIRONMENTS:
        return
    invalid_fields: list[str] = []
    secret = candidate.secret_key.strip()
    encryption_key = candidate.data_encryption_key.strip()
    username = candidate.bootstrap_admin_username.strip()
    password = candidate.bootstrap_admin_password.strip()
    if len(secret) < 32 or secret.lower() in UNSAFE_SECURITY_VALUES:
        invalid_fields.append("application secret")
    if len(encryption_key) < 32 or encryption_key.lower() in UNSAFE_SECURITY_VALUES:
        invalid_fields.append("data encryption secret")
    if not username or username.lower() in UNSAFE_SECURITY_VALUES - {"admin"}:
        invalid_fields.append("administrator username")
    password_is_structured = any(character.isalpha() for character in password) and any(
        character.isdigit() for character in password
    )
    if len(password) < 12 or password.lower() in UNSAFE_SECURITY_VALUES or not password_is_structured:
        invalid_fields.append("administrator credential")
    if invalid_fields:
        raise ConfigurationError(
            f"Unsafe production configuration: {', '.join(invalid_fields)} must be replaced"
        )


def _local_app_data_root() -> Path:
    return resolve_local_app_data_dir(
        RESOURCE_ROOT,
        PlatformPathContext(
            platform_name=sys.platform,
            environment=os.environ,
            home=Path.home(),
            cwd=Path.cwd(),
            frozen=bool(getattr(sys, "frozen", False)),
        ),
    )


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    app_version: str
    build_channel: str
    environment: str
    secret_key: str
    data_encryption_key: str
    access_token_expire_minutes: int
    local_sqlite_db_path: str
    bootstrap_admin_username: str
    bootstrap_admin_password: str
    local_app_data_dir: Path
    allowed_hosts: tuple[str, ...]
    frontend_origins: tuple[str, ...]

    @property
    def sqlite_db_path(self) -> Path:
        configured = Path(self.local_sqlite_db_path).expanduser()
        if configured.is_absolute():
            return configured
        return self.local_app_data_dir / configured

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.sqlite_db_path.as_posix()}"

    @property
    def legacy_sqlite_db_path(self) -> Path:
        return self.local_app_data_dir / "clinical-notes-analyzer.sqlite3"

    @property
    def effective_data_encryption_secret(self) -> str:
        return self.data_encryption_key.strip() or self.secret_key

    @property
    def api_harness_runs_dir(self) -> Path:
        return self.local_app_data_dir / "api-harness-runs"

    @property
    def audit_log_path(self) -> Path:
        return self.local_app_data_dir / "logs" / "v2-audit-log.jsonl"


def build_settings() -> Settings:
    allowed_hosts = tuple(
        host.strip()
        for host in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,::1,testserver").split(",")
        if host.strip()
    )
    frontend_origins = tuple(
        origin.strip()
        for origin in os.environ.get(
            "FRONTEND_ORIGINS",
            "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    )
    candidate = Settings(
        app_name=APP_NAME,
        app_version=APP_VERSION,
        build_channel=BUILD_CHANNEL,
        environment=os.environ.get("ENVIRONMENT", "development"),
        secret_key=_env("IZ_CNA_SECRET_KEY", "SECRET_KEY", "v2-local-development-secret"),
        data_encryption_key=_env("IZ_CNA_DATA_ENCRYPTION_KEY", "DATA_ENCRYPTION_KEY"),
        access_token_expire_minutes=int(os.environ.get("IZ_CNA_ACCESS_TOKEN_EXPIRE_MINUTES", "60")),
        local_sqlite_db_path=_env(
            "IZ_CNA_LOCAL_SQLITE_DB_PATH", "LOCAL_SQLITE_DB_PATH", "clinical-notes-analyzer-v2.sqlite3"
        ),
        bootstrap_admin_username=_env("IZ_CNA_BOOTSTRAP_ADMIN_USERNAME", "BOOTSTRAP_ADMIN_USERNAME", "admin"),
        bootstrap_admin_password=_env(
            "IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD", "BOOTSTRAP_ADMIN_PASSWORD", "local-admin-pass1"
        ),
        local_app_data_dir=_local_app_data_root(),
        allowed_hosts=allowed_hosts,
        frontend_origins=frontend_origins,
    )
    _validate_restricted_configuration(candidate)
    return candidate


settings: Final = build_settings()
