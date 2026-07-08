from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import AppSetting
from app.services.api_connectivity import DEFAULT_ALLEVA_SWAGGER_UI_URL, pull_api_definitions, request_client_credentials_token
from app.services.secure_storage import decrypt_text_secret

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def periodic_check_due(settings_row: AppSetting, *, now: datetime | None = None) -> bool:
    if not settings_row.emr_periodic_check_enabled:
        return False
    current = now or _utc_now()
    if settings_row.emr_last_check_at is None:
        return True
    interval = timedelta(minutes=max(5, settings_row.emr_periodic_check_interval_minutes or 1440))
    return settings_row.emr_last_check_at + interval <= current


def next_periodic_check_at(settings_row: AppSetting, *, now: datetime | None = None) -> datetime | None:
    if not settings_row.emr_periodic_check_enabled:
        return None
    current = now or _utc_now()
    if settings_row.emr_last_check_at is None:
        return current
    interval = timedelta(minutes=max(5, settings_row.emr_periodic_check_interval_minutes or 1440))
    return settings_row.emr_last_check_at + interval


def _missing_configuration(settings_row: AppSetting) -> list[str]:
    missing = []
    if not settings_row.alleva_api_base_url.strip():
        missing.append('REST API base URL')
    if not settings_row.alleva_openapi_url.strip():
        missing.append('OpenAPI URL')
    if not settings_row.api_oauth_token_url.strip():
        missing.append('token URL')
    if not settings_row.api_client_id.strip():
        missing.append('client ID')
    if not settings_row.api_client_secret:
        missing.append('client secret')
    return missing


def run_periodic_api_check(db: Session, settings_row: AppSetting) -> dict[str, Any]:
    """Run a bounded authenticated API readiness check without importing live charts."""
    now = _utc_now()
    missing = _missing_configuration(settings_row)
    if missing:
        message = f'Periodic API check skipped; missing {", ".join(missing)}.'
        settings_row.emr_last_check_at = now
        settings_row.emr_last_check_status = 'skipped'
        settings_row.emr_last_check_message = message
        settings_row.emr_last_failure_at = now
        db.commit()
        return {'status': 'skipped', 'message': message, 'token_result': {}, 'definition_summary': {}, 'operation_count': 0}

    client_secret = decrypt_text_secret(settings_row.api_client_secret)
    token_result, bearer_token = request_client_credentials_token(
        token_url=settings_row.api_oauth_token_url,
        client_id=settings_row.api_client_id,
        client_secret=client_secret,
        scope='',
        timeout_seconds=settings_row.emr_api_timeout_seconds,
        token_auth_style=settings_row.api_token_auth_style,
    )
    if not bearer_token:
        message = token_result.get('message') or 'Client-credentials token request failed.'
        settings_row.emr_last_check_at = now
        settings_row.emr_last_check_status = 'fail'
        settings_row.emr_last_check_message = message[:1000]
        settings_row.emr_last_failure_at = now
        db.commit()
        return {'status': 'fail', 'message': message, 'token_result': token_result, 'definition_summary': {}, 'operation_count': 0}

    definition_result = pull_api_definitions(
        swagger_ui_url=DEFAULT_ALLEVA_SWAGGER_UI_URL,
        api_base_url=settings_row.alleva_api_base_url,
        openapi_url=settings_row.alleva_openapi_url,
        bearer_token=bearer_token,
        timeout_seconds=settings_row.emr_api_timeout_seconds,
    )
    status = 'ok' if definition_result.get('status') == 'ok' else 'warn'
    operation_count = len(definition_result.get('operations') or [])
    summary = definition_result.get('definition_summary') or {}
    title = summary.get('title') or 'API definition'
    message = (
        f'{title} checked successfully; {operation_count} operation(s) discovered. '
        'Live patient import remains gated until vendor mapping and compliance approval are complete.'
        if status == 'ok'
        else definition_result.get('message') or 'Authenticated API check completed without loading an OpenAPI definition.'
    )
    settings_row.emr_last_check_at = now
    settings_row.emr_last_check_status = status
    settings_row.emr_last_check_message = str(message)[:1000]
    if status == 'ok':
        settings_row.emr_last_successful_check_at = now
    else:
        settings_row.emr_last_failure_at = now
    db.commit()
    logger.info('Periodic API check completed with status=%s operations=%s', status, operation_count)
    return {
        'status': status,
        'message': message,
        'token_result': token_result,
        'definition_summary': summary,
        'operation_count': operation_count,
    }
