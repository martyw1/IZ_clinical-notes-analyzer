from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.v2.api.deps import AdminUser, CurrentUser, DbSession
from app.v2.api.models import (
    ApiConfigurationOut,
    ApiConfigurationUpdate,
    AppSettingsOut,
    AppSettingsUpdate,
    AuditLogItemOut,
    AuditLogListOut,
    LoginInput,
    TokenOut,
    UserCreate,
    UserOut,
    UserPasswordResetAdmin,
    UserUpdate,
)
from app.v2.models import AppSetting, AuditLog, User
from app.v2.security import create_access_token, hash_password, password_policy_error, verify_password
from app.v2.services.audit_store import JsonValue, record_audit_event
from app.v2.services.secure_storage import encrypt_text_secret

router = APIRouter()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        is_locked=user.is_locked,
        must_reset_password=user.must_reset_password,
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


def _settings_row(db: DbSession) -> AppSetting:
    row = db.execute(select(AppSetting)).scalar_one_or_none()
    if not row:
        row = AppSetting()
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _settings_out(row: AppSetting) -> AppSettingsOut:
    return AppSettingsOut(
        organization_name=row.organization_name,
        facility_timezone=row.facility_timezone,
        treatment_plan_master_due_days=row.treatment_plan_master_due_days,
        treatment_plan_php_review_interval_days=row.treatment_plan_php_review_interval_days,
        treatment_plan_iop_op_review_interval_days=row.treatment_plan_iop_op_review_interval_days,
        treatment_plan_loc_change_window_days=row.treatment_plan_loc_change_window_days,
        treatment_plan_loc_change_window_validated=row.treatment_plan_loc_change_window_validated,
    )


def _api_config_out(row: AppSetting) -> ApiConfigurationOut:
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
    )


@router.post("/api/auth/login", response_model=TokenOut)
def login(payload: LoginInput, db: DbSession) -> TokenOut:
    username = payload.username.strip()
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.is_locked = True
            db.commit()
        record_audit_event(db, action="auth.login.failed", target_entity_type="user", target_entity_id=username, outcome_status="failure")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        record_audit_event(db, action="auth.login.blocked", actor=user, target_entity_type="user", target_entity_id=str(user.id), outcome_status="failure")
        raise HTTPException(status_code=403, detail="Account inactive")
    if user.is_locked:
        record_audit_event(db, action="auth.login.blocked", actor=user, target_entity_type="user", target_entity_id=str(user.id), outcome_status="failure")
        raise HTTPException(status_code=403, detail="Account locked")
    user.failed_login_attempts = 0
    user.last_login_at = _utc_now()
    db.commit()
    token = create_access_token(user.username)
    record_audit_event(db, action="auth.login.success", actor=user, target_entity_type="user", target_entity_id=str(user.id))
    return TokenOut(access_token=token, must_reset_password=user.must_reset_password)


@router.get("/api/users/me", response_model=UserOut)
def current_profile(user: CurrentUser) -> UserOut:
    return _user_out(user)


@router.get("/api/users", response_model=list[UserOut])
def list_users(_: AdminUser, db: DbSession) -> list[UserOut]:
    users = db.execute(select(User).order_by(User.role.asc(), User.username.asc())).scalars().all()
    return [_user_out(user) for user in users]


@router.post("/api/users", response_model=UserOut)
def create_user(payload: UserCreate, actor: AdminUser, db: DbSession) -> UserOut:
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    if db.execute(select(User).where(User.username == username)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username exists")
    policy_error = password_policy_error(payload.password, username=username)
    if policy_error:
        raise HTTPException(status_code=400, detail=policy_error)
    created = User(
        username=username,
        full_name=payload.full_name.strip() or username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
        must_reset_password=True,
        failed_login_attempts=0,
        is_locked=False,
    )
    db.add(created)
    db.commit()
    db.refresh(created)
    record_audit_event(db, action="user.create", actor=actor, target_entity_type="user", target_entity_id=str(created.id), details={"username": created.username, "role": created.role})
    return _user_out(created)


@router.patch("/api/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, actor: AdminUser, db: DbSession) -> UserOut:
    target = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.username == "admin" and any(value is not None for value in (payload.role, payload.is_active, payload.is_locked)):
        raise HTTPException(status_code=400, detail="The bootstrap admin account cannot be deactivated, locked, or re-scoped")
    if payload.full_name is not None:
        target.full_name = payload.full_name.strip() or target.username
    if payload.role is not None:
        target.role = payload.role
    if payload.is_active is not None:
        target.is_active = payload.is_active
    if payload.is_locked is not None:
        target.is_locked = payload.is_locked
        if not target.is_locked:
            target.failed_login_attempts = 0
    if payload.must_reset_password is not None:
        target.must_reset_password = payload.must_reset_password
    db.commit()
    db.refresh(target)
    record_audit_event(db, action="user.update", actor=actor, target_entity_type="user", target_entity_id=str(target.id))
    return _user_out(target)


@router.post("/api/users/{user_id}/reset-password", response_model=UserOut)
def admin_reset_password(user_id: int, payload: UserPasswordResetAdmin, actor: AdminUser, db: DbSession) -> UserOut:
    target = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.username == "admin":
        raise HTTPException(status_code=400, detail="The bootstrap admin password is managed by local setup")
    policy_error = password_policy_error(payload.new_password, username=target.username)
    if policy_error:
        raise HTTPException(status_code=400, detail=policy_error)
    target.password_hash = hash_password(payload.new_password)
    target.must_reset_password = payload.require_reset_on_login
    target.failed_login_attempts = 0
    target.is_locked = False
    db.commit()
    db.refresh(target)
    record_audit_event(db, action="user.password.reset.admin", actor=actor, target_entity_type="user", target_entity_id=str(target.id))
    return _user_out(target)


@router.get("/api/settings", response_model=AppSettingsOut)
def get_settings(_: CurrentUser, db: DbSession) -> AppSettingsOut:
    return _settings_out(_settings_row(db))


@router.patch("/api/settings", response_model=AppSettingsOut)
def save_settings(payload: AppSettingsUpdate, actor: AdminUser, db: DbSession) -> AppSettingsOut:
    row = _settings_row(db)
    for field in payload.model_fields_set:
        setattr(row, field, getattr(payload, field))
    row.updated_at = _utc_now()
    db.commit()
    db.refresh(row)
    record_audit_event(db, action="settings.saved", actor=actor, target_entity_type="app_settings", target_entity_id=str(row.id), details={"fields": sorted(payload.model_fields_set)})
    return _settings_out(row)


@router.get("/api/api-configuration", response_model=ApiConfigurationOut)
def get_api_configuration(_: AdminUser, db: DbSession) -> ApiConfigurationOut:
    return _api_config_out(_settings_row(db))


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
    }
    for source, target in field_map.items():
        if source in payload.model_fields_set:
            value = getattr(payload, source)
            if value is not None:
                setattr(row, target, value)
    secret = payload.client_secret if "client_secret" in payload.model_fields_set else payload.api_key
    if secret:
        row.api_client_secret = encrypt_text_secret(secret)
    row.updated_at = _utc_now()
    db.commit()
    db.refresh(row)
    record_audit_event(
        db,
        action="settings.api_profile.saved",
        actor=actor,
        target_entity_type="api_connection_profile",
        target_entity_id=row.emr_vendor_name,
        details={"vendor_name": row.emr_vendor_name, "api_base_url": row.api_base_url, "client_secret_configured": bool(row.api_client_secret)},
    )
    return _api_config_out(row)


@router.get("/api/audit/logs", response_model=AuditLogListOut)
def audit_logs(_: AdminUser, db: DbSession, limit: int = 100) -> AuditLogListOut:
    rows = db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(max(1, min(limit, 500)))).scalars().all()
    return AuditLogListOut(items=tuple(_audit_item(row) for row in rows))


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
