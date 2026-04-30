from __future__ import annotations

"""Startup and readiness checks for a non-technical local deployment.

These checks catch missing parser dependencies, weak local secrets, unwritable
storage, and risky synced-folder placement before a clinic tries to use the app
with real exports.
"""

import importlib
import os
import platform
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from app.core.config import settings
from app.services.secure_storage import ensure_private_directory, stored_payload_is_encrypted


@dataclass(frozen=True)
class RuntimeCheck:
    name: str
    status: str
    message: str
    detail: str = ''

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _check_import(module_name: str, purpose: str) -> RuntimeCheck:
    """Verify that a required runtime dependency can actually be imported."""
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        return RuntimeCheck(module_name, 'fail', f'{purpose} is not available.', str(exc))
    version = getattr(module, '__version__', 'installed')
    return RuntimeCheck(module_name, 'ok', f'{purpose} is available.', str(version))


def _check_upload_directory() -> RuntimeCheck:
    """Confirm clinical document storage exists, is writable, and is private."""
    upload_dir = settings.upload_dir_path
    try:
        ensure_private_directory(upload_dir)
        probe = upload_dir / '.startup-write-test'
        probe.write_text('ok', encoding='utf-8')
        probe.unlink()
    except Exception as exc:
        return RuntimeCheck('upload_dir', 'fail', 'Clinical upload storage is not writable.', str(exc))

    if os.name != 'nt':
        mode = upload_dir.stat().st_mode & 0o777
        if mode & 0o077:
            return RuntimeCheck('upload_dir_permissions', 'warn', 'Clinical upload storage is writable but not private to the current user.', oct(mode))
    sync_markers = {'onedrive', 'icloud', 'dropbox', 'google drive'}
    lowered_path = str(upload_dir).lower()
    if any(marker in lowered_path for marker in sync_markers):
        return RuntimeCheck('upload_dir_sync_root', 'warn', 'Clinical upload storage appears to be inside a synced folder.', str(upload_dir))
    return RuntimeCheck('upload_dir', 'ok', 'Clinical upload storage is writable and private.', str(upload_dir))


def _check_disk_space() -> RuntimeCheck:
    """Warn early when local storage is too small for binder-style imports."""
    target = settings.upload_dir_path
    try:
        usage = shutil.disk_usage(target if target.exists() else target.parent)
    except Exception as exc:
        return RuntimeCheck('disk_space', 'warn', 'Could not inspect free disk space for clinical uploads.', str(exc))

    free_gb = usage.free / (1024**3)
    if free_gb < 2:
        return RuntimeCheck('disk_space', 'warn', 'Free disk space is low for PDF and Word binder imports.', f'{free_gb:.1f} GB free')
    return RuntimeCheck('disk_space', 'ok', 'Free disk space is sufficient for local binder imports.', f'{free_gb:.1f} GB free')


def _check_existing_upload_encryption() -> RuntimeCheck:
    """Spot-check existing stored documents so plaintext PHI is surfaced early."""
    upload_dir = settings.upload_dir_path
    if not upload_dir.exists():
        return RuntimeCheck('stored_upload_encryption', 'ok', 'No existing uploads were found.')

    checked = 0
    unencrypted: list[str] = []
    for path in upload_dir.rglob('*'):
        if not path.is_file() or path.name.startswith('.startup-write-test'):
            continue
        checked += 1
        if not stored_payload_is_encrypted(path):
            unencrypted.append(str(path))
        if checked >= 100 or unencrypted:
            break

    if unencrypted:
        status = 'fail' if settings.is_production_like else 'warn'
        return RuntimeCheck('stored_upload_encryption', status, 'Existing clinical upload files are not encrypted.', unencrypted[0])
    return RuntimeCheck('stored_upload_encryption', 'ok', 'Existing stored upload files are encrypted.', f'checked={checked}')


def collect_runtime_checks() -> list[RuntimeCheck]:
    """Collect dependency, storage, and secret checks without raising."""
    checks = [
        RuntimeCheck('operating_system', 'ok', 'Runtime operating system detected.', f'{platform.system()} {platform.release()}'),
        RuntimeCheck('python', 'ok' if sys.version_info >= (3, 11) else 'fail', 'Python 3.11 or newer is required.', platform.python_version()),
        _check_import('fastapi', 'FastAPI backend'),
        _check_import('sqlalchemy', 'SQLAlchemy database layer'),
        _check_import('pypdf', 'PDF text extraction'),
        _check_import('cryptography', 'Encrypted local clinical-file storage'),
        _check_import('httpx', 'FHIR/SMART API discovery client'),
        _check_upload_directory(),
        _check_disk_space(),
        _check_existing_upload_encryption(),
    ]

    if settings.looks_placeholder_secret(settings.secret_key):
        status = 'fail' if settings.is_production_like else 'warn'
        checks.append(RuntimeCheck('secret_key', status, 'JWT signing key is still a placeholder.', 'Set SECRET_KEY in .env.'))
    else:
        checks.append(RuntimeCheck('secret_key', 'ok', 'JWT signing key is configured.'))

    if not settings.data_encryption_key.strip():
        status = 'fail' if settings.is_production_like else 'warn'
        checks.append(
            RuntimeCheck(
                'data_encryption_key',
                status,
                'Clinical file encryption key is not set separately from the JWT key.',
                'Set DATA_ENCRYPTION_KEY so JWT rotation does not break file decryption.',
            )
        )
    elif settings.looks_placeholder_secret(settings.data_encryption_key):
        status = 'fail' if settings.is_production_like else 'warn'
        checks.append(RuntimeCheck('data_encryption_key', status, 'Clinical file encryption key is still a placeholder.', 'Set DATA_ENCRYPTION_KEY in .env.'))
    else:
        checks.append(RuntimeCheck('data_encryption_key', 'ok', 'Clinical file encryption key is configured.'))

    return checks


def readiness_payload() -> dict[str, object]:
    """Return the API shape consumed by the frontend readiness panel."""
    checks = collect_runtime_checks()
    failed = sum(1 for check in checks if check.status == 'fail')
    warnings = sum(1 for check in checks if check.status == 'warn')
    return {
        'status': 'fail' if failed else 'warn' if warnings else 'ok',
        'failed': failed,
        'warnings': warnings,
        'checks': [check.as_dict() for check in checks],
    }


def assert_startup_ready() -> list[RuntimeCheck]:
    """Fail fast on hard startup blockers while allowing warning states."""
    checks = collect_runtime_checks()
    failures = [check for check in checks if check.status == 'fail']
    if failures:
        names = ', '.join(check.name for check in failures)
        raise RuntimeError(f'Startup dependency check failed: {names}')
    return checks
