from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.core.security import create_access_token, hash_password, password_policy_error, verify_password
from app.db.session import get_db
from app.models.models import (
    AppSetting,
    AuditLog,
    Chart,
    PatientNoteSet,
    Role,
    User,
    WorkflowDefinition,
    WorkflowDefinitionVersion,
    WorkflowTransition,
)
from app.schemas.schemas import (
    LoginInput,
    PasswordResetInput,
    Token,
    UserCreate,
    UserOut,
    UserPasswordChangeInput,
    UserPasswordResetAdmin,
    UserSelfUpdate,
    UserUpdate,
)
from app.services.access_intel import lookup_access_intel
from app.services.app_settings import get_or_create_app_settings
from app.services.audit import log_event


router = APIRouter()
USER_MANAGER_ROLES = (Role.admin, Role.manager)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_bootstrap_admin(user: User) -> bool:
    return user.username == settings.bootstrap_admin_username


def _enforce_password_policy(password: str, *, username: str | None = None) -> None:
    error = password_policy_error(password, username=username)
    if error:
        raise HTTPException(status_code=400, detail=error)


def _active_admin_count(db: Session) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(User).where(User.role == Role.admin, User.is_active.is_(True), User.is_locked.is_(False))
        ).scalar_one()
    )


def _assert_admin_safety(target: User, db: Session, *, new_role: Role | None = None, new_is_active: bool | None = None, new_is_locked: bool | None = None) -> None:
    if target.role != Role.admin:
        return

    admin_would_be_removed = new_role == Role.counselor or new_role == Role.manager or new_is_active is False or new_is_locked is True
    if admin_would_be_removed and _active_admin_count(db) <= 1:
        raise HTTPException(status_code=400, detail='At least one active, unlocked admin account must remain')


def _assert_user_management_scope(actor: User, target: User | None = None, *, requested_role: Role | None = None) -> None:
    if actor.role == Role.admin:
        return
    if actor.role != Role.manager:
        raise HTTPException(status_code=403, detail='Insufficient permissions')
    if target is not None:
        if target.id == actor.id:
            raise HTTPException(status_code=403, detail='Use My account to manage your own profile')
        if target.role != Role.counselor:
            raise HTTPException(status_code=403, detail='Office managers can manage counselor accounts only')
    if requested_role is not None and requested_role != Role.counselor:
        raise HTTPException(status_code=403, detail='Office managers can create or assign counselor accounts only')


def _user_snapshot(user: User) -> dict[str, object]:
    return {
        'id': user.id,
        'username': user.username,
        'full_name': user.full_name,
        'role': user.role.value,
        'is_active': user.is_active,
        'is_locked': user.is_locked,
        'must_reset_password': user.must_reset_password,
        'last_login_at': user.last_login_at,
        'created_at': user.created_at,
    }


def _user_delete_blockers(user_id: int, db: Session) -> list[str]:
    blockers: list[str] = []

    relationship_checks = [
        ('assigned charts', select(Chart.id).where(Chart.counselor_id == user_id).limit(1)),
        ('reviewed charts', select(Chart.id).where(Chart.reviewed_by_id == user_id).limit(1)),
        ('uploaded patient note sets', select(PatientNoteSet.id).where(PatientNoteSet.uploaded_by_id == user_id).limit(1)),
        ('workflow transitions', select(WorkflowTransition.id).where(WorkflowTransition.actor_id == user_id).limit(1)),
        ('workflow definitions', select(WorkflowDefinition.id).where(WorkflowDefinition.created_by_id == user_id).limit(1)),
        ('workflow definition updates', select(WorkflowDefinition.id).where(WorkflowDefinition.updated_by_id == user_id).limit(1)),
        ('workflow definition versions', select(WorkflowDefinitionVersion.id).where(WorkflowDefinitionVersion.created_by_id == user_id).limit(1)),
        ('workflow definition publications', select(WorkflowDefinitionVersion.id).where(WorkflowDefinitionVersion.published_by_id == user_id).limit(1)),
        ('workflow definition archives', select(WorkflowDefinitionVersion.id).where(WorkflowDefinitionVersion.archived_by_id == user_id).limit(1)),
        ('application settings updates', select(AppSetting.id).where(AppSetting.updated_by_id == user_id).limit(1)),
        ('forensic audit history', select(AuditLog.id).where(AuditLog.actor_id == user_id).limit(1)),
    ]

    for label, stmt in relationship_checks:
        if db.execute(stmt).scalar_one_or_none() is not None:
            blockers.append(label)

    return blockers


@router.post('/auth/login', response_model=Token)
def login(payload: LoginInput, request: Request, db: Session = Depends(get_db)):
    username = payload.username.strip()
    app_settings = get_or_create_app_settings(db)
    forwarded_for = request.headers.get('x-forwarded-for', '')
    source_ip = (forwarded_for.split(',')[0].strip() if forwarded_for else '') or request.headers.get('x-real-ip') or (request.client.host if request.client else None)
    access_intel = lookup_access_intel(app_settings, source_ip)
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()

    if not user or not verify_password(payload.password, user.password_hash):
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.is_locked = True
            db.commit()
        log_event(
            db,
            request,
            'auth.login.failed',
            event_category='access_attempt',
            target_entity='user',
            target_entity_type='user',
            target_entity_id=username,
            details={'username': username, **access_intel.as_details()},
            outcome_status='failure',
            severity='warning',
            http_status_code=401,
            message=f'Login failed for username {username}. {access_intel.danger_summary}',
        )
        raise HTTPException(status_code=401, detail='Invalid credentials')

    if not user.is_active:
        log_event(
            db,
            request,
            'auth.login.blocked',
            actor=user,
            event_category='access_attempt',
            target_entity='user',
            target_entity_type='user',
            target_entity_id=str(user.id),
            details={'username': user.username, 'reason': 'inactive', **access_intel.as_details()},
            outcome_status='failure',
            severity='warning',
            http_status_code=403,
            message=f'Login blocked for inactive account {user.username}. {access_intel.danger_summary}',
        )
        raise HTTPException(status_code=403, detail='Account inactive')

    if user.is_locked:
        log_event(
            db,
            request,
            'auth.login.blocked',
            actor=user,
            event_category='access_attempt',
            target_entity='user',
            target_entity_type='user',
            target_entity_id=str(user.id),
            details={'username': user.username, 'reason': 'locked', **access_intel.as_details()},
            outcome_status='failure',
            severity='warning',
            http_status_code=403,
            message=f'Login blocked for locked account {user.username}. {access_intel.danger_summary}',
        )
        raise HTTPException(status_code=403, detail='Account locked')

    user.failed_login_attempts = 0
    user.last_login_at = _utc_now()
    if _is_bootstrap_admin(user):
        user.must_reset_password = False
    db.commit()

    token = create_access_token(user.username)
    log_event(
        db,
        request,
        'auth.login.success',
        actor=user,
        event_category='access_attempt',
        target_entity='user',
        target_entity_type='user',
        target_entity_id=str(user.id),
        details={'username': user.username, **access_intel.as_details()},
        http_status_code=200,
        message=f'Login succeeded for {user.username}. {access_intel.danger_summary}',
    )
    return Token(access_token=token, must_reset_password=user.must_reset_password)


@router.post('/auth/reset-password')
def reset_password(payload: PasswordResetInput, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if _is_bootstrap_admin(user):
        log_event(
            db,
            request,
            'auth.password.reset.blocked',
            actor=user,
            event_category='authentication',
            target_entity='user',
            target_entity_type='user',
            target_entity_id=str(user.id),
            details={'username': user.username, 'reason': 'bootstrap_admin_static_password'},
            outcome_status='failure',
            severity='warning',
            http_status_code=400,
            message='Static bootstrap admin password change was blocked.',
        )
        raise HTTPException(status_code=400, detail='The bootstrap admin password is fixed and cannot be changed in-app')

    _enforce_password_policy(payload.new_password, username=user.username)
    user.password_hash = hash_password(payload.new_password)
    user.must_reset_password = False
    user.is_locked = False
    user.failed_login_attempts = 0
    db.commit()
    log_event(
        db,
        request,
        'auth.password.reset',
        actor=user,
        event_category='authentication',
        target_entity='user',
        target_entity_type='user',
        target_entity_id=str(user.id),
        details={'username': user.username},
        message=f'Password reset completed for {user.username}.',
    )
    return {'status': 'ok'}


@router.get('/users/me', response_model=UserOut)
def me(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    log_event(
        db,
        request,
        'user.profile.read',
        actor=user,
        event_category='data_access',
        target_entity='user',
        target_entity_type='user',
        target_entity_id=str(user.id),
        details={'username': user.username},
        message=f'Profile viewed for {user.username}.',
    )
    return user


@router.patch('/users/me', response_model=UserOut)
def update_my_profile(payload: UserSelfUpdate, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.full_name = payload.full_name.strip() or user.username
    db.commit()
    db.refresh(user)
    log_event(
        db,
        request,
        'user.profile.update',
        actor=user,
        event_category='user_management',
        target_entity='user',
        target_entity_type='user',
        target_entity_id=str(user.id),
        details={'username': user.username, 'full_name': user.full_name},
        message=f'Profile updated for {user.username}.',
    )
    return user


@router.post('/users/me/change-password')
def change_my_password(
    payload: UserPasswordChangeInput,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if _is_bootstrap_admin(user):
        raise HTTPException(status_code=400, detail='The bootstrap admin password is fixed and cannot be changed in-app')
    if not verify_password(payload.current_password, user.password_hash):
        log_event(
            db,
            request,
            'auth.password.change.failed',
            actor=user,
            event_category='authentication',
            target_entity='user',
            target_entity_type='user',
            target_entity_id=str(user.id),
            details={'username': user.username, 'reason': 'current_password_mismatch'},
            outcome_status='failure',
            severity='warning',
            http_status_code=400,
            message=f'Password change failed for {user.username}: current password mismatch.',
        )
        raise HTTPException(status_code=400, detail='Current password is incorrect')

    _enforce_password_policy(payload.new_password, username=user.username)
    user.password_hash = hash_password(payload.new_password)
    user.must_reset_password = False
    user.is_locked = False
    user.failed_login_attempts = 0
    db.commit()
    log_event(
        db,
        request,
        'auth.password.change',
        actor=user,
        event_category='authentication',
        target_entity='user',
        target_entity_type='user',
        target_entity_id=str(user.id),
        details={'username': user.username},
        message=f'Password changed for {user.username}.',
    )
    return {'status': 'ok'}


@router.get('/users', response_model=list[UserOut])
def list_users(request: Request, user: User = Depends(require_roles(*USER_MANAGER_ROLES)), db: Session = Depends(get_db)):
    users = list(db.execute(select(User).order_by(User.role.asc(), User.username.asc())).scalars().all())
    log_event(
        db,
        request,
        'user.list.read',
        actor=user,
        event_category='user_management',
        target_entity='user_directory',
        target_entity_type='user',
        details={'count': len(users)},
        message=f'User directory viewed by {user.username}.',
    )
    return users


@router.post('/users', response_model=UserOut)
def create_user(payload: UserCreate, request: Request, user: User = Depends(require_roles(*USER_MANAGER_ROLES)), db: Session = Depends(get_db)):
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail='Username is required')
    _assert_user_management_scope(user, requested_role=payload.role)
    exists = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail='Username exists')

    _enforce_password_policy(payload.password, username=username)
    created = User(
        username=username,
        full_name=payload.full_name.strip() or username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
        must_reset_password=True,
    )
    db.add(created)
    db.commit()
    db.refresh(created)
    log_event(
        db,
        request,
        'user.create',
        actor=user,
        event_category='user_management',
        target_entity='user',
        target_entity_type='user',
        target_entity_id=str(created.id),
        details={'username': created.username, 'role': created.role.value},
        message=f'User {created.username} created with role {created.role.value}.',
    )
    return created


@router.patch('/users/{user_id}', response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, request: Request, actor: User = Depends(require_roles(*USER_MANAGER_ROLES)), db: Session = Depends(get_db)):
    target = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail='User not found')
    _assert_user_management_scope(actor, target, requested_role=payload.role)

    if _is_bootstrap_admin(target):
        disallowed = any(
            value is not None
            for value in [payload.role, payload.is_active, payload.is_locked, payload.must_reset_password]
        )
        if disallowed:
            raise HTTPException(status_code=400, detail='The bootstrap admin account cannot be deactivated, locked, or re-scoped')

    _assert_admin_safety(target, db, new_role=payload.role, new_is_active=payload.is_active, new_is_locked=payload.is_locked)

    if payload.full_name is not None:
        target.full_name = payload.full_name.strip() or target.username
    if payload.role is not None and not _is_bootstrap_admin(target):
        target.role = payload.role
    if payload.is_active is not None and not _is_bootstrap_admin(target):
        target.is_active = payload.is_active
    if payload.is_locked is not None and not _is_bootstrap_admin(target):
        target.is_locked = payload.is_locked
        if not target.is_locked:
            target.failed_login_attempts = 0
    if payload.must_reset_password is not None and not _is_bootstrap_admin(target):
        target.must_reset_password = payload.must_reset_password

    db.commit()
    db.refresh(target)
    log_event(
        db,
        request,
        'user.update',
        actor=actor,
        event_category='user_management',
        target_entity='user',
        target_entity_type='user',
        target_entity_id=str(target.id),
        details={
            'username': target.username,
            'role': target.role.value,
            'is_active': target.is_active,
            'is_locked': target.is_locked,
            'must_reset_password': target.must_reset_password,
        },
        message=f'User {target.username} updated by {actor.username}.',
    )
    return target


@router.post('/users/{user_id}/reset-password', response_model=UserOut)
def admin_reset_password(
    user_id: int,
    payload: UserPasswordResetAdmin,
    request: Request,
    actor: User = Depends(require_roles(*USER_MANAGER_ROLES)),
    db: Session = Depends(get_db),
):
    target = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail='User not found')
    _assert_user_management_scope(actor, target)
    if _is_bootstrap_admin(target):
        raise HTTPException(status_code=400, detail='The bootstrap admin password is fixed and cannot be changed in-app')

    _enforce_password_policy(payload.new_password, username=target.username)
    target.password_hash = hash_password(payload.new_password)
    target.must_reset_password = payload.require_reset_on_login
    target.is_locked = False
    target.failed_login_attempts = 0
    db.commit()
    db.refresh(target)
    log_event(
        db,
        request,
        'user.password.reset.admin',
        actor=actor,
        event_category='user_management',
        target_entity='user',
        target_entity_type='user',
        target_entity_id=str(target.id),
        details={'username': target.username, 'require_reset_on_login': payload.require_reset_on_login},
        message=f'Password reset by admin for {target.username}.',
    )
    return target


@router.delete('/users/{user_id}')
def delete_user(user_id: int, request: Request, actor: User = Depends(require_roles(*USER_MANAGER_ROLES)), db: Session = Depends(get_db)):
    target = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail='User not found')
    _assert_user_management_scope(actor, target)
    if actor.id == target.id:
        raise HTTPException(status_code=400, detail='You cannot delete your own account')
    if _is_bootstrap_admin(target):
        raise HTTPException(status_code=400, detail='The bootstrap admin account cannot be deleted')

    _assert_admin_safety(target, db, new_is_active=False)
    blockers = _user_delete_blockers(target.id, db)
    if blockers:
        blocker_summary = ', '.join(blockers)
        raise HTTPException(
            status_code=400,
            detail=f'User cannot be deleted because related records exist: {blocker_summary}. Deactivate the account instead.',
        )

    before_state = _user_snapshot(target)
    username = target.username
    target_id = target.id
    db.delete(target)
    db.commit()
    log_event(
        db,
        request,
        'user.delete',
        actor=actor,
        event_category='user_management',
        target_entity='user',
        target_entity_type='user',
        target_entity_id=str(target_id),
        details={'username': username},
        before_state=before_state,
        diff_state=before_state,
        message=f'User {username} deleted by {actor.username}.',
    )
    return {'status': 'deleted'}
