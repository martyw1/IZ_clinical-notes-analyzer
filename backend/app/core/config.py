from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

APP_NAME: Final = "IZ Clinical Notes Analyzer"
APP_VERSION: Final = "2.0.0-beta.1"
BUILD_CHANNEL: Final = "beta-local-desktop-v2"
REPO_ROOT: Final = Path(__file__).resolve().parents[3]


def _local_app_data_root() -> Path:
    configured = os.environ.get("IZ_CNA_LOCAL_APP_DATA_DIR", "").strip()
    if configured:
        return Path(configured)
    base = os.environ.get("LOCALAPPDATA", "").strip()
    if base:
        return Path(base) / APP_NAME
    return REPO_ROOT / ".local-app-data"


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    app_version: str
    build_channel: str
    environment: str
<<<<<<< HEAD
    secret_key: str
    data_encryption_key: str
    access_token_expire_minutes: int
    local_sqlite_db_path: str
    bootstrap_admin_username: str
    bootstrap_admin_password: str
=======
>>>>>>> 7ff7108 (Rebuild V2 beta local desktop app)
    local_app_data_dir: Path
    allowed_hosts: tuple[str, ...]
    frontend_origins: tuple[str, ...]

    @property
<<<<<<< HEAD
    def sqlite_db_path(self) -> Path:
        configured = Path(self.local_sqlite_db_path).expanduser()
        if configured.is_absolute():
            return configured
        return self.local_app_data_dir / configured

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.sqlite_db_path.as_posix()}"

    @property
    def effective_data_encryption_secret(self) -> str:
        return self.data_encryption_key.strip() or self.secret_key

    @property
=======
>>>>>>> 7ff7108 (Rebuild V2 beta local desktop app)
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
    return Settings(
        app_name=APP_NAME,
        app_version=APP_VERSION,
        build_channel=BUILD_CHANNEL,
        environment=os.environ.get("ENVIRONMENT", "development"),
<<<<<<< HEAD
        secret_key=os.environ.get("IZ_CNA_SECRET_KEY") or os.environ.get("SECRET_KEY", "v2-local-development-secret"),
        data_encryption_key=os.environ.get("IZ_CNA_DATA_ENCRYPTION_KEY") or os.environ.get("DATA_ENCRYPTION_KEY", ""),
        access_token_expire_minutes=int(os.environ.get("IZ_CNA_ACCESS_TOKEN_EXPIRE_MINUTES", "60")),
        local_sqlite_db_path=os.environ.get("IZ_CNA_LOCAL_SQLITE_DB_PATH", "clinical-notes-analyzer-v2.sqlite3"),
        bootstrap_admin_username=os.environ.get("IZ_CNA_BOOTSTRAP_ADMIN_USERNAME", "admin"),
        bootstrap_admin_password=os.environ.get("IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD", "local-admin-pass1"),
=======
>>>>>>> 7ff7108 (Rebuild V2 beta local desktop app)
        local_app_data_dir=_local_app_data_root(),
        allowed_hosts=allowed_hosts,
        frontend_origins=frontend_origins,
    )


settings: Final = build_settings()
