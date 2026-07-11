from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import select

from app.v2.api.deps import AdminUser, DbSession
from app.v2.api.models import (
    ApiConfigurationOut,
    ApiConfigurationUpdate,
    AuditLogItemOut,
    AuditLogListOut,
    AuditVerificationOut,
)
from app.v2.models import AppSetting, AuditLog
from app.v2.services.audit_store import JsonValue, audit_policy_metadata, record_audit_event, verify_audit_chain
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
    db.commit()
    db.refresh(row)
    record_audit_event(
        db,
        action="settings.api_profile.saved",
        actor=actor,
        target_entity_type="api_connection_profile",
        target_entity_id=row.emr_vendor_name,
        details={
            "vendor_name": row.emr_vendor_name,
            "api_base_url": row.api_base_url,
            "client_secret_configured": bool(row.api_client_secret),
        },
    )
    contract = active_contract(db)
    return _api_config_out(row, contract.contract_version if contract else None, contract.effective_at if contract else None)


@router.get("/api/audit/logs", response_model=AuditLogListOut)
def audit_logs(_: AdminUser, db: DbSession, limit: int = 100) -> AuditLogListOut:
    rows = db.execute(
        select(AuditLog).order_by(AuditLog.id.desc()).limit(max(1, min(limit, 500)))
    ).scalars().all()
    return AuditLogListOut(items=tuple(_audit_item(row) for row in rows))


@router.get("/api/audit/verify", response_model=AuditVerificationOut)
def verify_audit_logs(_: AdminUser, db: DbSession) -> AuditVerificationOut:
    valid, event_count, first_invalid_id = verify_audit_chain(db)
    privacy_mode, retention_hook = audit_policy_metadata()
    return AuditVerificationOut(
        valid=valid,
        event_count=event_count,
        first_invalid_id=first_invalid_id,
        privacy_mode=privacy_mode,
        retention_hook=retention_hook,
    )


def _audit_item(row: AuditLog) -> AuditLogItemOut:
    details = json.loads(row.details_json)
    safe_details: dict[str, JsonValue] = details if isinstance(details, dict) else {}
    return AuditLogItemOut(
        event_id=row.event_id,
        timestamp_utc=row.timestamp_utc.isoformat(),
        actor_id=row.actor_id,
        actor_username=row.actor_username,
        actor_role=row.actor_role,
        action=row.action,
        target_entity_type=row.target_entity_type,
        target_entity_id=row.target_entity_id,
        outcome_status=row.outcome_status,
        details=safe_details,
        prev_hash=row.prev_hash,
        hash=row.hash,
    )
