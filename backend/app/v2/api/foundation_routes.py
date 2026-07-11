from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.v2.api.deps import AdminUser, CurrentUser, DbSession
from app.v2.api.models import (
    AppSettingsOut,
    AppSettingsUpdate,
    LoginInput,
    TokenOut,
    UserCreate,
    UserOut,
    UserPasswordResetAdmin,
    UserPasswordChange,
    UserUpdate,
)
from app.v2.models import AppSetting, User
from app.v2.authorization import facility_ids_for_user
from app.v2.security import create_access_token, hash_password, password_policy_error, verify_password
from app.v2.services.audit_store import record_audit_event
from app.v2.services.evaluation_store import reevaluate_all_plan_versions

router = APIRouter()
RULE_SETTING_FIELDS = frozenset(
    {
        "facility_timezone",
        "treatment_plan_master_due_days",
        "treatment_plan_php_review_interval_days",
        "treatment_plan_iop_op_review_interval_days",
        "treatment_plan_loc_change_window_days",
        "treatment_plan_loc_change_window_validated",
    }
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _user_out(user: User, db: DbSession) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        is_locked=user.is_locked,
        must_reset_password=user.must_reset_password,
        auth_state=user.auth_state,
        locked_until=user.locked_until.isoformat() if user.locked_until else None,
        facility_ids=facility_ids_for_user(db, user.id),
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


@router.post("/api/auth/login", response_model=TokenOut)
def login(payload: LoginInput, db: DbSession) -> TokenOut:
    username = payload.username.strip()
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    now = _utc_now()
    if user and user.auth_state == "locked_until":
        locked_until = user.locked_until
        if locked_until is not None and locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until is not None and now < locked_until:
            record_audit_event(db, action="auth.login.blocked", actor=user, target_entity_type="user", target_entity_id=str(user.id), outcome_status="denied")
            raise HTTPException(status_code=423, detail="Account temporarily locked")
        user.is_locked = False
        user.locked_until = None
        user.auth_state = "password_change_required" if user.must_reset_password else "active"
        user.failed_login_attempts = 0
        db.commit()
    if not user or not verify_password(payload.password, user.password_hash):
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.is_locked = True
                user.auth_state = "locked_until"
                user.locked_until = now + timedelta(minutes=15)
            db.commit()
            if user.auth_state == "locked_until":
                record_audit_event(db, action="auth.lockout.started", actor=user, target_entity_type="user", target_entity_id=str(user.id), outcome_status="denied", details={"duration_minutes": 15})
        record_audit_event(db, action="auth.login.failed", target_entity_type="user", target_entity_id=username, outcome_status="failure")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        record_audit_event(db, action="auth.login.blocked", actor=user, target_entity_type="user", target_entity_id=str(user.id), outcome_status="failure")
        raise HTTPException(status_code=403, detail="Account inactive")
    if user.is_locked or user.auth_state == "locked_until":
        record_audit_event(db, action="auth.login.blocked", actor=user, target_entity_type="user", target_entity_id=str(user.id), outcome_status="failure")
        raise HTTPException(status_code=403, detail="Account locked")
    user.failed_login_attempts = 0
    user.last_login_at = now
    if user.auth_state == "bootstrap_required":
        user.auth_state = "password_change_required"
        user.must_reset_password = True
    db.commit()
    token = create_access_token(user.username, user.password_changed_at)
    if user.auth_state == "password_change_required" and user.password_changed_at is None:
        record_audit_event(db, action="auth.bootstrap.completed", actor=user, target_entity_type="user", target_entity_id=str(user.id))
    record_audit_event(db, action="auth.login.success", actor=user, target_entity_type="user", target_entity_id=str(user.id))
    return TokenOut(access_token=token, must_reset_password=user.must_reset_password, auth_state=user.auth_state)


@router.get("/api/users/me", response_model=UserOut)
def current_profile(user: CurrentUser, db: DbSession) -> UserOut:
    return _user_out(user, db)


@router.post("/api/users/me/change-password", response_model=UserOut)
def change_current_password(payload: UserPasswordChange, user: CurrentUser, db: DbSession) -> UserOut:
    if not verify_password(payload.current_password, user.password_hash):
        record_audit_event(db, action="user.password.change.failed", actor=user, target_entity_type="user", target_entity_id=str(user.id), outcome_status="failure")
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(status_code=400, detail="New password must differ from the current password")
    policy_error = password_policy_error(payload.new_password, username=user.username)
    if policy_error:
        raise HTTPException(status_code=400, detail=policy_error)
    user.password_hash = hash_password(payload.new_password)
    user.must_reset_password = False
    user.failed_login_attempts = 0
    user.is_locked = False
    user.auth_state = "active"
    user.locked_until = None
    user.password_changed_at = _utc_now()
    user.recovery_required = False
    db.commit()
    db.refresh(user)
    record_audit_event(db, action="user.password.changed", actor=user, target_entity_type="user", target_entity_id=str(user.id))
    return _user_out(user, db)


@router.get("/api/users", response_model=list[UserOut])
def list_users(_: AdminUser, db: DbSession) -> list[UserOut]:
    users = db.execute(select(User).order_by(User.role.asc(), User.username.asc())).scalars().all()
    return [_user_out(user, db) for user in users]


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
        auth_state="password_change_required",
    )
    db.add(created)
    db.commit()
    db.refresh(created)
    record_audit_event(db, action="user.create", actor=actor, target_entity_type="user", target_entity_id=str(created.id), details={"username": created.username, "role": created.role})
    return _user_out(created, db)


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
    return _user_out(target, db)


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
    target.password_changed_at = _utc_now()
    target.must_reset_password = payload.require_reset_on_login
    target.failed_login_attempts = 0
    target.is_locked = False
    target.locked_until = None
    target.auth_state = "password_change_required" if payload.require_reset_on_login else "active"
    db.commit()
    db.refresh(target)
    record_audit_event(db, action="user.password.reset.admin", actor=actor, target_entity_type="user", target_entity_id=str(target.id))
    return _user_out(target, db)


@router.get("/api/settings", response_model=AppSettingsOut)
def get_settings(_: AdminUser, db: DbSession) -> AppSettingsOut:
    return _settings_out(_settings_row(db))


@router.patch("/api/settings", response_model=AppSettingsOut)
def save_settings(payload: AppSettingsUpdate, actor: AdminUser, db: DbSession) -> AppSettingsOut:
    row = _settings_row(db)
    for field in payload.model_fields_set:
        setattr(row, field, getattr(payload, field))
    row.updated_at = _utc_now()
    db.commit()
    db.refresh(row)
    if RULE_SETTING_FIELDS.intersection(payload.model_fields_set):
        reevaluate_all_plan_versions(db, "rule_config")
    record_audit_event(db, action="settings.saved", actor=actor, target_entity_type="app_settings", target_entity_id=str(row.id), details={"fields": sorted(payload.model_fields_set)})
    return _settings_out(row)
