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
    local_app_data_dir: Path
    allowed_hosts: tuple[str, ...]
    frontend_origins: tuple[str, ...]

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
    return Settings(
        app_name=APP_NAME,
        app_version=APP_VERSION,
        build_channel=BUILD_CHANNEL,
        environment=os.environ.get("ENVIRONMENT", "development"),
        local_app_data_dir=_local_app_data_root(),
        allowed_hosts=allowed_hosts,
        frontend_origins=frontend_origins,
    )


settings: Final = build_settings()
