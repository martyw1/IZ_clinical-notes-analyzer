from contextlib import asynccontextmanager
import logging
import os
import time
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

from app.api.routes import router
from app.api.api_config_routes import router as api_config_router
from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.bootstrap import ensure_schema_compatibility
from app.db.session import SessionLocal, engine
from app.models.models import Role, User
from app.services.audit import bind_request_context, log_event, log_request_completed, log_unhandled_exception, reset_audit_context, system_audit_context
from app.services.runtime_checks import assert_startup_ready, readiness_payload
from app.services.version import build_version_payload
from app.services.workflow_definitions import ensure_default_workflow_definitions

logger = logging.getLogger(__name__)


def wait_for_database(max_attempts: int = 8, initial_delay: float = 0.5) -> None:
    delay = initial_delay
    for attempt in range(1, max_attempts + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text('SELECT 1'))
            return
        except SQLAlchemyError as exc:
            logger.warning('Database not ready (attempt %s/%s): %s', attempt, max_attempts, exc)
            if attempt == max_attempts:
                raise
            time.sleep(delay)
            delay *= 2


def initialize_database() -> None:
    with system_audit_context():
        startup_checks = assert_startup_ready()
        wait_for_database()
        added_columns = ensure_schema_compatibility(engine)
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            admin = db.execute(select(User).where(User.username == settings.bootstrap_admin_username)).scalar_one_or_none()
            if not admin:
                admin = User(
                    username=settings.bootstrap_admin_username,
                    full_name='System Administrator',
                    password_hash=hash_password(settings.bootstrap_admin_password),
                    role=Role.admin,
                    is_active=True,
                    must_reset_password=False,
                )
                db.add(admin)
                db.commit()
                log_event(
                    action='system.bootstrap.admin.created',
                    event_category='system',
                    target_entity='user',
                    target_entity_type='user',
                    target_entity_id=settings.bootstrap_admin_username,
                    details={'username': settings.bootstrap_admin_username},
                    message='Bootstrap admin account created during startup.',
                )
                db.refresh(admin)
            elif settings.reset_bootstrap_admin_on_startup:
                admin.password_hash = hash_password(settings.bootstrap_admin_password)
                admin.full_name = admin.full_name or 'System Administrator'
                admin.is_active = True
                admin.failed_login_attempts = 0
                admin.is_locked = False
                admin.must_reset_password = False
                db.commit()
                log_event(
                    action='system.bootstrap.admin.reset',
                    event_category='system',
                    target_entity='user',
                    target_entity_type='user',
                    target_entity_id=settings.bootstrap_admin_username,
                    details={'username': settings.bootstrap_admin_username},
                    message='Bootstrap admin account reset during startup.',
                )
            seeded_workflow = ensure_default_workflow_definitions(db, actor_id=admin.id)
            if seeded_workflow is not None:
                db.commit()
                log_event(
                    action='system.workflow_definition.seeded',
                    event_category='system',
                    target_entity='workflow_definition',
                    target_entity_type='workflow_definition',
                    target_entity_id=seeded_workflow.workflow_key,
                    details={'workflow_key': seeded_workflow.workflow_key, 'version': 1},
                    message='Default Treatment Plan Timeliness workflow profile seeded during startup.',
                )
        finally:
            db.close()

        log_event(
            action='system.startup.completed',
            event_category='system',
            target_entity='application',
            target_entity_type='application',
            target_entity_id=settings.app_name,
            details={
                'schema_updates': added_columns,
                'runtime_checks': [check.as_dict() for check in startup_checks],
            },
            message='Application startup and schema compatibility checks completed.',
        )


def create_app() -> FastAPI:
    os.makedirs(settings.upload_dir_path, exist_ok=True)
    os.makedirs(settings.log_dir_path, exist_ok=True)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        initialize_database()
        yield

    api = FastAPI(title=settings.app_name, lifespan=lifespan)

    api.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)

    api.add_middleware(
        CORSMiddleware,
        allow_origins=settings.frontend_origins_list,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    @api.middleware('http')
    async def forensic_request_middleware(request: Request, call_next):
        token = bind_request_context(request)
        started_at = perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (perf_counter() - started_at) * 1000
            log_unhandled_exception(request, exc, duration_ms=duration_ms)
            reset_audit_context(token)
            return JSONResponse(status_code=500, content={'detail': 'Internal server error'})

        duration_ms = (perf_counter() - started_at) * 1000
        response.headers['x-request-id'] = getattr(request.state, 'request_id', '')
        response.headers.setdefault('cache-control', 'no-store')
        response.headers.setdefault('x-content-type-options', 'nosniff')
        response.headers.setdefault('x-frame-options', 'DENY')
        response.headers.setdefault('referrer-policy', 'no-referrer')
        response.headers.setdefault('permissions-policy', 'camera=(), microphone=(), geolocation=()')
        log_request_completed(request, status_code=response.status_code, duration_ms=duration_ms)
        reset_audit_context(token)
        return response

    @api.get('/health')
    def health():
        return {'status': 'ok'}

    @api.get('/api/health')
    def api_health():
        return {'status': 'ok'}

    @api.get('/api/readiness')
    def api_readiness():
        return readiness_payload()

    @api.get('/api/version')
    def api_version():
        return build_version_payload()

    api.include_router(router)
    api.include_router(api_config_router)
    return api


app = create_app()
