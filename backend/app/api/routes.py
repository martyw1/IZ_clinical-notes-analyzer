from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.models import Chart, Role, User, WorkflowState, WorkflowTransition, AuditLog
from app.schemas.schemas import (
    AuditLogOut,
    ChartCreate,
    ChartOut,
    LoginInput,
    PasswordResetInput,
    Token,
    TransitionInput,
    UserCreate,
    UserOut,
)
from app.services.audit import log_event

router = APIRouter(prefix='/api')


def _allowed_transition(role: Role, current: WorkflowState, target: WorkflowState) -> bool:
    allowed = {
        Role.counselor: {
            WorkflowState.draft: [WorkflowState.submitted],
            WorkflowState.returned: [WorkflowState.submitted],
        },
        Role.admin: {
            WorkflowState.submitted: [WorkflowState.in_progress, WorkflowState.returned],
            WorkflowState.in_progress: [WorkflowState.completed, WorkflowState.returned],
            WorkflowState.completed: [WorkflowState.verified],
        },
        Role.manager: {
            WorkflowState.completed: [WorkflowState.verified],
            WorkflowState.submitted: [WorkflowState.in_progress],
        },
    }
    return target in allowed.get(role, {}).get(current, [])


@router.post('/auth/login', response_model=Token)
def login(payload: LoginInput, request: Request, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.username == payload.username)).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.is_locked = True
            db.commit()
        log_event(db, request, 'auth.login.failed', target_entity='user', details={'username': payload.username}, outcome_status='failure', severity='warning')
        raise HTTPException(status_code=401, detail='Invalid credentials')
    if user.is_locked:
        raise HTTPException(status_code=403, detail='Account locked')
    user.failed_login_attempts = 0
    db.commit()
    token = create_access_token(user.username)
    log_event(db, request, 'auth.login.success', actor=user, target_entity='user', details={'username': user.username})
    return Token(access_token=token, must_reset_password=user.must_reset_password)


@router.post('/auth/reset-password')
def reset_password(payload: PasswordResetInput, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.password_hash = hash_password(payload.new_password)
    user.must_reset_password = False
    db.commit()
    log_event(db, request, 'auth.password.reset', actor=user, target_entity='user', details={'username': user.username})
    return {'status': 'ok'}


@router.get('/users/me', response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post('/users', response_model=UserOut)
def create_user(payload: UserCreate, request: Request, db: Session = Depends(get_db), _: User = Depends(require_roles(Role.admin))):
    exists = db.execute(select(User).where(User.username == payload.username)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail='Username exists')
    user = User(username=payload.username, password_hash=hash_password(payload.password), role=payload.role, must_reset_password=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    log_event(db, request, 'user.create', target_entity='user', details={'username': user.username, 'role': user.role.value})
    return user


@router.get('/charts', response_model=list[ChartOut])
def list_charts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(Chart)
    if user.role == Role.counselor:
        stmt = stmt.where(Chart.counselor_id == user.id)
    return list(db.execute(stmt.order_by(Chart.id.desc())).scalars().all())


@router.post('/charts', response_model=ChartOut)
def create_chart(payload: ChartCreate, request: Request, user: User = Depends(require_roles(Role.counselor, Role.admin)), db: Session = Depends(get_db)):
    chart = Chart(
        client_name=payload.client_name,
        level_of_care=payload.level_of_care,
        primary_clinician=payload.primary_clinician,
        counselor_id=user.id,
        notes=payload.notes,
    )
    db.add(chart)
    db.commit()
    db.refresh(chart)
    log_event(db, request, 'chart.create', actor=user, target_entity=f'chart:{chart.id}', details={'state': chart.state.value})
    return chart


@router.post('/charts/{chart_id}/transition', response_model=ChartOut)
def transition_chart(chart_id: int, payload: TransitionInput, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chart = db.get(Chart, chart_id)
    if not chart:
        raise HTTPException(status_code=404, detail='Chart not found')
    if user.role == Role.counselor and chart.counselor_id != user.id:
        raise HTTPException(status_code=403, detail='Cannot transition this chart')
    if not _allowed_transition(user.role, chart.state, payload.to_state):
        raise HTTPException(status_code=400, detail='Invalid transition for role/state')
    if payload.to_state == WorkflowState.returned and not payload.comment.strip():
        raise HTTPException(status_code=400, detail='Comment required for returns')
    old = chart.state
    chart.state = payload.to_state
    db.add(WorkflowTransition(chart_id=chart.id, actor_id=user.id, from_state=old.value, to_state=payload.to_state.value, comment=payload.comment))
    db.commit()
    db.refresh(chart)
    log_event(db, request, 'chart.transition', actor=user, target_entity=f'chart:{chart.id}', details={'from': old.value, 'to': payload.to_state.value, 'comment': payload.comment})
    return chart


@router.post('/uploads')
def upload_files(request: Request, files: list[UploadFile] = File(...), user: User = Depends(require_roles(Role.counselor, Role.admin)), db: Session = Depends(get_db)):
    accepted = []
    for f in files:
        accepted.append({'filename': f.filename, 'content_type': f.content_type})
    log_event(db, request, 'file.upload', actor=user, target_entity='batch-upload', details={'count': len(accepted), 'files': accepted})
    return {'uploaded': accepted}


@router.get('/audit/logs', response_model=list[AuditLogOut])
def audit_logs(_: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    return list(db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(500)).scalars().all())
