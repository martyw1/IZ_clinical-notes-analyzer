from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.sqlite import insert

from app.v2.api.deps import CurrentUser, DbSession
from app.v2.models import PasswordRecovery, PasswordRecoveryThrottle, User
from app.v2.security import hash_password, password_policy_error, verify_password
from app.v2.services.audit_store import record_audit_event

router = APIRouter()


class RecoveryCodeInput(BaseModel):
    model_config = ConfigDict(frozen=True)
    current_password: str = Field(min_length=1, max_length=1024)


class RecoveryInput(BaseModel):
    model_config = ConfigDict(frozen=True)
    username: str = Field(min_length=1, max_length=80)
    recovery_code: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=1024)


class RecoveryStatus(BaseModel):
    model_config = ConfigDict(frozen=True)
    configured: bool


class RecoveryCodeOut(BaseModel):
    model_config = ConfigDict(frozen=True)
    recovery_code: str


class RecoveryOut(BaseModel):
    model_config = ConfigDict(frozen=True)
    message: str


def _throttle(db: DbSession, scope: str) -> None:
    """Persist a bounded global request budget, including unknown accounts."""
    now = datetime.now(timezone.utc)
    db.execute(insert(PasswordRecoveryThrottle).values(scope=scope, window_start=now, attempts=0).on_conflict_do_nothing())
    db.execute(update(PasswordRecoveryThrottle).where(
        PasswordRecoveryThrottle.scope == scope,
        PasswordRecoveryThrottle.window_start <= now - timedelta(minutes=15),
    ).values(window_start=now, attempts=0))
    attempts = db.execute(update(PasswordRecoveryThrottle).where(
        PasswordRecoveryThrottle.scope == scope,
    ).values(attempts=PasswordRecoveryThrottle.attempts + 1).returning(PasswordRecoveryThrottle.attempts)).scalar_one()
    db.commit()
    if attempts > 20:
        raise HTTPException(status_code=429, detail="Too many recovery attempts. Try again in 15 minutes.", headers={"Retry-After": "900"})


@router.get("/api/users/me/recovery-code", response_model=RecoveryStatus)
def recovery_status(user: CurrentUser, db: DbSession, response: Response) -> RecoveryStatus:
    response.headers["Cache-Control"] = "no-store"
    return RecoveryStatus(configured=db.get(PasswordRecovery, user.id) is not None)


@router.post("/api/users/me/recovery-code", response_model=RecoveryCodeOut)
def generate_recovery_code(payload: RecoveryCodeInput, user: CurrentUser, db: DbSession, response: Response) -> RecoveryCodeOut:
    _throttle(db, "generation")
    if not verify_password(payload.current_password, user.password_hash):
        record_audit_event(db, action="user.recovery.generation.failed", actor=user, outcome_status="failure")
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    code = token_urlsafe(32)
    digest = sha256(code.encode()).hexdigest()
    db.execute(insert(PasswordRecovery).values(user_id=user.id, code_hash=digest).on_conflict_do_update(
        index_elements=[PasswordRecovery.user_id], set_={"code_hash": digest},
    ))
    record_audit_event(db, action="user.recovery.generated", actor=user, target_entity_type="user", target_entity_id=str(user.id), commit=False)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return RecoveryCodeOut(recovery_code=code)


@router.post("/api/auth/recover-password", response_model=RecoveryOut)
def recover_password(payload: RecoveryInput, db: DbSession, response: Response) -> RecoveryOut:
    _throttle(db, "recovery")
    policy_error = password_policy_error(payload.new_password, username=payload.username)
    if policy_error:
        raise HTTPException(status_code=400, detail=policy_error)
    digest = sha256(payload.recovery_code.strip().encode()).hexdigest()
    eligible_users = select(User.id).where(
        User.username == payload.username.strip(), User.is_active.is_(True),
        or_(User.is_locked.is_(False), User.auth_state == "locked_until"),
    )
    user_id = db.execute(delete(PasswordRecovery).where(
        PasswordRecovery.user_id.in_(eligible_users), PasswordRecovery.code_hash == digest,
    ).returning(PasswordRecovery.user_id)).scalar_one_or_none()
    if user_id is None:
        db.rollback()
        record_audit_event(db, action="user.recovery.failed", outcome_status="failure")
        raise HTTPException(status_code=400, detail="Unable to reset password. Check your username and recovery code.")
    user = db.execute(select(User).where(User.id == user_id)).scalar_one()
    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    user.must_reset_password = False
    user.recovery_required = False
    user.failed_login_attempts = 0
    user.is_locked = False
    user.locked_until = None
    user.auth_state = "active"
    record_audit_event(db, action="user.password.recovered", actor=user, target_entity_type="user", target_entity_id=str(user.id), commit=False)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return RecoveryOut(message="Password reset. Sign in with your new password and save a new recovery code.")
