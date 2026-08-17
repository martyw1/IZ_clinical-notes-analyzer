from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from app.core.config import APP_VERSION, BUILD_CHANNEL, RESOURCE_ROOT, settings

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list[JsonPrimitive] | dict[str, JsonPrimitive]

UNKNOWN = "unknown"


def _metadata_path() -> Path:
    return RESOURCE_ROOT / "VERSION.json"


def _read_metadata() -> dict[str, JsonValue]:
    path = _metadata_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, dict):
        return {str(key): value for key, value in payload.items()}
    return {}


def _git_value(*args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=RESOURCE_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN
    return completed.stdout.strip() or UNKNOWN


def build_version_payload() -> dict[str, JsonValue]:
    metadata = _read_metadata()
    branch = os.environ.get("IZ_CNA_GIT_BRANCH", "").strip() or _git_value("branch", "--show-current")
    dirty = _git_value("status", "--porcelain")
    return {
        "app_name": str(metadata.get("app_name") or settings.app_name),
        "version": str(metadata.get("version") or APP_VERSION),
        "build": str(metadata.get("build") or ""),
        "release_channel": str(metadata.get("release_channel") or BUILD_CHANNEL),
        "release_date": str(metadata.get("release_date") or ""),
        "stability": str(metadata.get("stability") or "beta"),
        "is_prerelease": bool(metadata.get("is_prerelease", True)),
        "version_name": str(metadata.get("version_name") or "Version 2.0 Beta"),
        "environment": settings.environment,
        "git_commit": os.environ.get("IZ_CNA_GIT_COMMIT", "").strip()[:12]
        or _git_value("rev-parse", "--short=12", "HEAD"),
        "git_branch": branch,
        "git_dirty": dirty not in {"", UNKNOWN},
        "active_runtime": "v2",
    }
