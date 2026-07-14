from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Final, assert_never
from urllib.parse import urlsplit, urlunsplit

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.v2.models import AppSetting, AuditLog
from app.v2.services.audit_store import record_audit_event
from app.v2.services.legacy_settings_reader import LegacyProfile, LegacySourceRejected, read_legacy_profile
from app.v2.services.secure_storage import (
    LEGACY_SECRET_TEXT_PREFIX,
    SECRET_TEXT_PREFIX,
    decrypt_api_client_id,
    decrypt_text_secret,
    encrypt_text_secret,
)

DEFAULT_API_BASE: Final = "https://api.allevasoft.com"
DEFAULT_OPENAPI_URL: Final = "https://api.allevasoft.com/swagger/v1/swagger.json"
DEFAULT_TOKEN_URL: Final = "https://authorization.allevasoft.com/connect/token"
DEFAULT_API_VERSION: Final = "1.0"
DEFAULT_START_DATE: Final = "2000-01-01T16:03"
PENDING_STATE: Final = "credentials_migrated_approval_pending"
USER_CONFIGURED_STATE: Final = "v2_user_configured"
def migrate_legacy_api_settings(db: Session, legacy_database_path: Path, encryption_secret: str) -> str:
    row = db.execute(select(AppSetting)).scalar_one()
    state = row.legacy_api_settings_migration_state.strip()
    if state == PENDING_STATE:
        return _reconcile_pending_approval(db, row, legacy_database_path, encryption_secret)
    if state:
        return state
    if not _is_pristine(db, row):
        _protect_existing_client_id(row)
        return _finish(db, row, USER_CONFIGURED_STATE, source_found=legacy_database_path.is_file())

    result = read_legacy_profile(legacy_database_path, encryption_secret)
    match result:
        case LegacySourceRejected(reason="source_missing"):
            return _finish(db, row, "no_legacy_source", source_found=False)
        case LegacySourceRejected():
            _disable_sync_gates(row)
            return _finish(db, row, "legacy_source_rejected", source_found=True, outcome="warning")
        case LegacyProfile() as profile:
            _apply_profile(row, profile)
            return _set_approval_state(db, row, profile)
        case unreachable:
            assert_never(unreachable)


def _reconcile_pending_approval(
    db: Session,
    row: AppSetting,
    legacy_database_path: Path,
    encryption_secret: str,
) -> str:
    result = read_legacy_profile(legacy_database_path, encryption_secret)
    match result:
        case LegacyProfile() as profile if _matches_migrated_profile(row, profile):
            return _set_approval_state(db, row, profile)
        case LegacyProfile():
            _disable_sync_gates(row)
            return _finish(db, row, USER_CONFIGURED_STATE, source_found=True, outcome="warning")
        case LegacySourceRejected():
            return PENDING_STATE
        case unreachable:
            assert_never(unreachable)


def _set_approval_state(db: Session, row: AppSetting, profile: LegacyProfile) -> str:
    candidate = _approval_candidate(row, profile)
    compatible = candidate and _builtin_contract_is_compatible(row)
    row.alleva_treatment_plan_sync_enabled = compatible
    row.alleva_treatment_plan_sync_approved = compatible
    row.alleva_treatment_plan_endpoint_mapping_validated = compatible
    if compatible or not candidate:
        return _finish(db, row, "completed", source_found=True)
    return _finish(db, row, PENDING_STATE, source_found=True, outcome="warning")


def _is_pristine(db: Session, row: AppSetting) -> bool:
    saved = db.execute(
        select(AuditLog.id).where(AuditLog.action == "settings.api_profile.saved").limit(1)
    ).scalar_one_or_none()
    return (
        saved is None
        and not row.api_client_id
        and not row.api_client_secret
        and row.api_base_url.strip() == DEFAULT_API_BASE
        and row.openapi_url.strip() == DEFAULT_OPENAPI_URL
        and row.api_oauth_token_url.strip() == DEFAULT_TOKEN_URL
        and row.api_token_auth_style.strip() == "body"
        and not row.api_scopes.strip()
        and row.alleva_api_version.strip() == DEFAULT_API_VERSION
        and row.alleva_treatment_plan_start_date.strip() == DEFAULT_START_DATE
    )


def _apply_profile(row: AppSetting, profile: LegacyProfile) -> None:
    row.emr_vendor_name = profile.vendor_name
    row.emr_api_enabled = profile.api_enabled
    row.api_client_id = encrypt_text_secret(profile.client_id)
    row.api_client_secret = encrypt_text_secret(profile.client_secret)
    row.api_oauth_token_url = profile.token_url
    row.api_token_auth_style = profile.token_auth_style
    row.emr_api_timeout_seconds = profile.timeout_seconds
    row.api_base_url = profile.api_base_url
    row.openapi_url = profile.openapi_url
    row.alleva_api_version = profile.api_version
    row.alleva_treatment_plan_start_date = DEFAULT_START_DATE
    row.alleva_treatment_plan_sync_limit = profile.sync_limit


def _approval_candidate(row: AppSetting, profile: LegacyProfile) -> bool:
    return (
        profile.api_enabled and profile.sync_enabled and profile.sync_approved and profile.mapping_validated
        and _normalized_url(profile.api_base_url) == DEFAULT_API_BASE
        and _normalized_url(profile.token_url) == DEFAULT_TOKEN_URL
        and profile.api_version == DEFAULT_API_VERSION
        and profile.token_auth_style in {"body", "basic"}
        and not row.api_scopes.strip()
        and row.alleva_treatment_plan_start_date == DEFAULT_START_DATE
    )


def _builtin_contract_is_compatible(profile: AppSetting) -> bool:
    from app.v2.services.alleva_contracts import _builtin_contract_payload

    payload = _builtin_contract_payload(
        profile,
        contract_version="legacy-settings-compatibility-check",
        effective_at=datetime.now(timezone.utc),
    )
    endpoints = payload.endpoints
    expected = {
        "clients": ("/clients", {"limit": "Limit", "offset": "Cursor"}),
        "treatment_plans": ("/treatment-plans", {"limit": "Limit", "offset": "Cursor", "client_id": "ClientId", "start_date": "StartDate"}),
        "treatment_plan_detail": ("/treatment-plans/{plan_id}", {}),
        "diagnoses": ("/treatment-plans/{plan_id}/diagnosis", {}),
        "reviews": ("/treatment-reviews", {"limit": "Limit", "offset": "Cursor"}),
        "review_detail": ("/treatment-reviews/{review_id}", {}),
    }
    return all(
        key in endpoints and endpoints[key].path == path and endpoints[key].parameters == parameters
        for key, (path, parameters) in expected.items()
    )


def _matches_migrated_profile(row: AppSetting, profile: LegacyProfile) -> bool:
    try:
        client_id = decrypt_api_client_id(row.api_client_id)
        client_secret = decrypt_text_secret(row.api_client_secret)
    except HTTPException:
        return False
    return (
        client_id == profile.client_id and client_secret == profile.client_secret
        and row.api_base_url == profile.api_base_url and row.openapi_url == profile.openapi_url
        and row.api_oauth_token_url == profile.token_url and row.api_token_auth_style == profile.token_auth_style
        and row.alleva_api_version == profile.api_version and row.emr_api_enabled == profile.api_enabled
    )


def _normalized_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme.casefold() != "https" or not parts.netloc or parts.username or parts.password or parts.query or parts.fragment:
        return ""
    path = parts.path.rstrip("/")
    return urlunsplit(("https", parts.netloc.casefold(), path, "", ""))


def _protect_existing_client_id(row: AppSetting) -> None:
    value = row.api_client_id.strip()
    if value and not value.startswith((SECRET_TEXT_PREFIX, LEGACY_SECRET_TEXT_PREFIX)):
        row.api_client_id = encrypt_text_secret(value)


def _disable_sync_gates(row: AppSetting) -> None:
    row.alleva_treatment_plan_sync_enabled = False
    row.alleva_treatment_plan_sync_approved = False
    row.alleva_treatment_plan_endpoint_mapping_validated = False


def _finish(
    db: Session,
    row: AppSetting,
    state: str,
    *,
    source_found: bool,
    outcome: str = "success",
) -> str:
    row.legacy_api_settings_migration_state = state
    record_audit_event(
        db,
        action="settings.legacy_api.migration",
        target_entity_type="api_connection_profile",
        target_entity_id="alleva",
        outcome_status=outcome,
        details={
            "migration_state": state,
            "source_found": source_found,
            "client_id_configured": bool(row.api_client_id),
            "client_secret_configured": bool(row.api_client_secret),
            "api_enabled": row.emr_api_enabled,
            "sync_enabled": row.alleva_treatment_plan_sync_enabled,
            "sync_approved": row.alleva_treatment_plan_sync_approved,
            "mapping_validated": row.alleva_treatment_plan_endpoint_mapping_validated,
        },
        commit=False,
    )
    return state
