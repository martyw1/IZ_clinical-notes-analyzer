from __future__ import annotations

"""Startup and readiness checks for a non-technical local deployment.

These checks catch missing parser dependencies, weak local secrets, unwritable
storage, invalid YAML rules, local database availability, and risky synced-folder
placement before a clinic tries to use the app with real exports.
"""

import importlib
import os
import platform
import shutil
import sys
from dataclasses import asdict, dataclass

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

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


def _check_database_config() -> RuntimeCheck:
    """Confirm the selected database mode is local and service-free for desktop runs."""
    try:
        database_url = settings.database_url_value
    except Exception as exc:
        return RuntimeCheck('database_config', 'fail', 'Database configuration is invalid.', str(exc))
    if database_url.startswith('sqlite'):
        return RuntimeCheck('database_config', 'ok', 'Local SQLite database is configured.', str(settings.sqlite_db_path))
    if database_url.startswith('postgresql'):
        return RuntimeCheck('database_config', 'warn', 'PostgreSQL is configured; this is for developer/server runs, not the no-Docker Windows desktop target.', database_url.split('@')[-1])
    return RuntimeCheck('database_config', 'fail', 'Unsupported database URL scheme.', database_url.split(':', 1)[0])


def _check_database_connection() -> RuntimeCheck:
    """Probe the SQLAlchemy engine without requiring app startup to complete."""
    try:
        from app.db.session import engine

        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        return RuntimeCheck('database_connection', 'ok', 'Database connection check passed.', engine.dialect.name)
    except SQLAlchemyError as exc:
        return RuntimeCheck('database_connection', 'fail', 'Database connection check failed.', str(exc))
    except Exception as exc:
        return RuntimeCheck('database_connection', 'fail', 'Database connection could not be checked.', str(exc))


def _check_rules_config() -> RuntimeCheck:
    """Validate the YAML rules configuration before checks are run against data."""
    try:
        from app.services.rules_engine import load_rules_config, validate_rules_config

        config = load_rules_config()
        errors = validate_rules_config(config)
    except Exception as exc:
        return RuntimeCheck('rules_config', 'fail', 'Rules configuration could not be loaded.', str(exc))
    if errors:
        return RuntimeCheck('rules_config', 'fail', 'Rules configuration failed validation.', '; '.join(errors[:5]))
    workflow_id = (config.get('workflow') or {}).get('id', '')
    rules_count = len(config.get('rules') or [])
    return RuntimeCheck('rules_config', 'ok', 'Rules configuration loaded and validated.', f'{settings.rules_config_file} workflow={workflow_id} rules={rules_count}')


def _check_treatment_plan_checklist() -> RuntimeCheck:
    """Validate the canonical Version 1 treatment-plan checklist."""
    try:
        from app.services.treatment_plan_checklist import load_treatment_plan_checklist

        checklist = load_treatment_plan_checklist()
    except Exception as exc:
        return RuntimeCheck('treatment_plan_checklist', 'fail', 'Treatment Plan Checklist Version 1 could not be loaded.', str(exc))
    return RuntimeCheck(
        'treatment_plan_checklist',
        'ok',
        'Treatment Plan Checklist Version 1 loaded and validated.',
        f"{checklist['source_of_truth']} version={checklist['version']} steps={len(checklist['steps'])}",
    )


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
    """Collect dependency, storage, database, rules, and secret checks without raising."""
    checks = [
        RuntimeCheck('operating_system', 'ok', 'Runtime operating system detected.', f'{platform.system()} {platform.release()}'),
        RuntimeCheck('python', 'ok' if sys.version_info >= (3, 11) else 'fail', 'Python 3.11 or newer is required for source runs; packaged releases include a runtime.', platform.python_version()),
        _check_import('fastapi', 'FastAPI backend'),
        _check_import('sqlalchemy', 'SQLAlchemy database layer'),
        _check_import('yaml', 'YAML rules parser'),
        _check_import('pypdf', 'PDF text extraction'),
        _check_import('cryptography', 'Encrypted local clinical-file storage'),
        _check_import('httpx', 'Alleva/API connectivity client'),
        _check_database_config(),
        _check_database_connection(),
        _check_rules_config(),
        _check_treatment_plan_checklist(),
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
