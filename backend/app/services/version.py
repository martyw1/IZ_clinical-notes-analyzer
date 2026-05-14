from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from app.core.config import REPO_ROOT, settings

UNKNOWN = 'unknown'


def _read_version_text() -> str:
    version_file = REPO_ROOT / 'VERSION'
    if version_file.exists():
        value = version_file.read_text(encoding='utf-8').strip()
        if value:
            return value
    metadata = _read_version_metadata()
    return str(metadata.get('version') or '0.0.0-local.unknown')


def _read_version_metadata() -> dict[str, Any]:
    metadata_file = REPO_ROOT / 'VERSION.json'
    if not metadata_file.exists():
        return {}
    try:
        payload = json.loads(metadata_file.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _git_value(*args: str) -> str:
    try:
        completed = subprocess.run(
            ['git', *args],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return UNKNOWN
    return completed.stdout.strip() or UNKNOWN


def build_version_payload() -> dict[str, Any]:
    metadata = _read_version_metadata()
    version = str(metadata.get('version') or _read_version_text())
    short_commit = os.environ.get('IZ_CNA_GIT_COMMIT', '').strip()[:12] or _git_value('rev-parse', '--short=12', 'HEAD')
    branch = os.environ.get('IZ_CNA_GIT_BRANCH', '').strip() or _git_value('branch', '--show-current')
    dirty = _git_value('status', '--porcelain')
    return {
        'app_name': metadata.get('app_name') or settings.app_name,
        'version': version,
        'build': metadata.get('build') or '',
        'release_channel': metadata.get('release_channel') or 'local-desktop',
        'release_date': metadata.get('release_date') or '',
        'version_name': metadata.get('version_name') or '',
        'environment': settings.environment,
        'git_commit': short_commit,
        'git_branch': branch if branch != UNKNOWN else metadata.get('git_branch', UNKNOWN),
        'git_dirty': dirty not in {'', UNKNOWN},
    }
