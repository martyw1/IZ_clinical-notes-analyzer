from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import select, text

from app.v2.api.deps import AdminUser, DbSession
from app.v2.api.models import (
    ApiConfigurationOut,
    ApiConfigurationUpdate,
    AuditLogItemOut,
    AuditLogListOut,
    AuditVerificationOut,
)
from app.v2.models import AppSetting, AuditLog
from app.v2.services.audit_store import JsonValue, audit_policy_metadata, record_audit_event, verify_audit_chain_details
from app.v2.services.alleva_contracts import active_contract
from app.v2.services.secure_storage import encrypt_text_secret

router = APIRouter()


def _settings_row(db: DbSession) -> AppSetting:
    row = db.execute(select(AppSetting)).scalar_one()
    return row


def _api_config_out(row: AppSetting, contract_version: str | None = None, effective_at: datetime | None = None) -> ApiConfigurationOut:
    configured = bool(row.api_client_secret)
    return ApiConfigurationOut(
        vendor_name=row.emr_vendor_name,
        api_base_url=row.api_base_url,
        openapi_url=row.openapi_url,
        token_url=row.api_oauth_token_url,
        client_id=row.api_client_id,
        api_key_configured=configured,
        client_secret_configured=configured,
        token_auth_style=row.api_token_auth_style,
        scopes=row.api_scopes,
        pagination_limit=row.api_pagination_limit,
        sync_limit=row.alleva_treatment_plan_sync_limit,
        timeout_seconds=row.emr_api_timeout_seconds,
        api_enabled=row.emr_api_enabled,
        treatment_plan_sync_enabled=row.alleva_treatment_plan_sync_enabled,
        treatment_plan_sync_approved=row.alleva_treatment_plan_sync_approved,
        treatment_plan_endpoint_mapping_validated=row.alleva_treatment_plan_endpoint_mapping_validated,
        active_contract_version=contract_version,
        active_contract_effective_at=effective_at,
    )


@router.get("/api/api-configuration", response_model=ApiConfigurationOut)
def get_api_configuration(_: AdminUser, db: DbSession) -> ApiConfigurationOut:
    contract = active_contract(db)
    return _api_config_out(_settings_row(db), contract.contract_version if contract else None, contract.effective_at if contract else None)


@router.patch("/api/api-configuration", response_model=ApiConfigurationOut)
def save_api_configuration(payload: ApiConfigurationUpdate, actor: AdminUser, db: DbSession) -> ApiConfigurationOut:
    row = _settings_row(db)
    field_map = {
        "vendor_name": "emr_vendor_name",
        "api_base_url": "api_base_url",
        "openapi_url": "openapi_url",
        "token_url": "api_oauth_token_url",
        "client_id": "api_client_id",
        "token_auth_style": "api_token_auth_style",
        "scopes": "api_scopes",
        "pagination_limit": "api_pagination_limit",
        "sync_limit": "alleva_treatment_plan_sync_limit",
        "timeout_seconds": "emr_api_timeout_seconds",
        "api_enabled": "emr_api_enabled",
        "treatment_plan_sync_enabled": "alleva_treatment_plan_sync_enabled",
        "treatment_plan_sync_approved": "alleva_treatment_plan_sync_approved",
        "treatment_plan_endpoint_mapping_validated": "alleva_treatment_plan_endpoint_mapping_validated",
    }
    for source, target in field_map.items():
        if source in payload.model_fields_set:
            value = getattr(payload, source)
            if value is not None:
                setattr(row, target, value)
    secret = payload.client_secret if "client_secret" in payload.model_fields_set else payload.api_key
    if secret:
        row.api_client_secret = encrypt_text_secret(secret)
    row.updated_at = datetime.now(timezone.utc)
    record_audit_event(
        db,
        action="settings.api_profile.saved",
        actor=actor,
        target_entity_type="api_connection_profile",
        target_entity_id=row.emr_vendor_name,
        details={
            "client_secret_configured": bool(row.api_client_secret),
            "api_testing_enabled": row.emr_api_enabled,
        },
        commit=False,
    )
    db.commit()
    db.refresh(row)
    contract = active_contract(db)
    return _api_config_out(row, contract.contract_version if contract else None, contract.effective_at if contract else None)


@router.get("/api/audit/logs", response_model=AuditLogListOut)
def audit_logs(_: AdminUser, db: DbSession, limit: int = 100) -> AuditLogListOut:
    columns = {str(row[1]) for row in db.execute(text("PRAGMA table_info('audit_logs')")).all()}
    details_column = "details" if "details" in columns else "details_json"
    if details_column not in columns:
        return AuditLogListOut(items=())
    rows = db.execute(
        text(
            "SELECT event_id,timestamp_utc,actor_id,actor_username,actor_role,action,"
            "target_entity_type,target_entity_id,outcome_status,"
            f"{details_column} AS details_json FROM audit_logs ORDER BY id DESC LIMIT :limit"
        ),
        {"limit": max(1, min(limit, 500))},
    ).mappings().all()
    return AuditLogListOut(items=tuple(_audit_mapping_item(row) for row in rows))


@router.get("/api/audit/verify", response_model=AuditVerificationOut)
def verify_audit_logs(_: AdminUser, db: DbSession) -> AuditVerificationOut:
    verification = verify_audit_chain_details(db)
    privacy_mode, retention_hook = audit_policy_metadata()
    return AuditVerificationOut(
        valid=verification.valid,
        event_count=verification.event_count,
        verified_event_count=verification.verified_event_count,
        legacy_event_count=verification.legacy_event_count,
        first_invalid_id=verification.first_invalid_id,
        verification_scope=verification.verification_scope,
        privacy_mode=privacy_mode,
        retention_hook=retention_hook,
    )


def _audit_item(row: AuditLog) -> AuditLogItemOut:
    return _audit_values(
        event_id=row.event_id,
        timestamp_utc=row.timestamp_utc,
        actor_id=row.actor_id,
        actor_username=row.actor_username,
        actor_role=row.actor_role,
        action=row.action,
        target_entity_type=row.target_entity_type,
        target_entity_id=row.target_entity_id,
        outcome_status=row.outcome_status,
        details_json=row.details_json,
    )


def _audit_mapping_item(row: Mapping[str, object]) -> AuditLogItemOut:
    return _audit_values(
        event_id=row.get("event_id"),
        timestamp_utc=row.get("timestamp_utc"),
        actor_id=row.get("actor_id"),
        actor_username=row.get("actor_username"),
        actor_role=row.get("actor_role"),
        action=row.get("action"),
        target_entity_type=row.get("target_entity_type"),
        target_entity_id=row.get("target_entity_id"),
        outcome_status=row.get("outcome_status"),
        details_json=row.get("details_json"),
    )


def _audit_values(
    *, event_id: object, timestamp_utc: object, actor_id: object, actor_username: object,
    actor_role: object, action: object, target_entity_type: object, target_entity_id: object,
    outcome_status: object, details_json: object,
) -> AuditLogItemOut:
    try:
        details = json.loads(details_json) if isinstance(details_json, str) else details_json
    except (json.JSONDecodeError, TypeError):
        details = {}
    safe_details: dict[str, JsonValue] = details if isinstance(details, dict) else {}
    return AuditLogItemOut(
        event_id=str(event_id),
        timestamp_utc=_audit_timestamp(timestamp_utc),
        actor_id=str(actor_id),
        actor_username=str(actor_username or ""),
        actor_role=str(actor_role or ""),
        action=str(action or "unknown"),
        target_entity_type=str(target_entity_type or "system"),
        target_entity_id=str(target_entity_id or ""),
        outcome_status=str(outcome_status or "unknown"),
        details=safe_details,
    )


def _audit_timestamp(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")
