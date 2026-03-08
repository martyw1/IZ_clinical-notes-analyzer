from contextlib import asynccontextmanager
import logging
import os
import time
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse

from app.api.routes import router
from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.bootstrap import ensure_schema_compatibility
from app.db.session import SessionLocal, engine
from app.models.models import Role, User
from app.services.audit import bind_request_context, log_event, log_request_completed, log_unhandled_exception, reset_audit_context, system_audit_context

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
        wait_for_database()
        added_columns = ensure_schema_compatibility(engine)
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            admin = db.execute(select(User).where(User.username == settings.bootstrap_admin_username)).scalar_one_or_none()
            if not admin:
                db.add(
                    User(
                        username=settings.bootstrap_admin_username,
                        password_hash=hash_password(settings.bootstrap_admin_password),
                        role=Role.admin,
                        must_reset_password=True,
                    )
                )
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
            elif settings.reset_bootstrap_admin_on_startup and settings.environment != 'production':
                admin.password_hash = hash_password(settings.bootstrap_admin_password)
                admin.failed_login_attempts = 0
                admin.is_locked = False
                admin.must_reset_password = True
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
        finally:
            db.close()

        log_event(
            action='system.startup.completed',
            event_category='system',
            target_entity='application',
            target_entity_type='application',
            target_entity_id=settings.app_name,
            details={'schema_updates': added_columns},
            message='Application startup and schema compatibility checks completed.',
        )


def create_app() -> FastAPI:
    os.makedirs(settings.upload_dir_path, exist_ok=True)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        initialize_database()
        yield

    api = FastAPI(title=settings.app_name, lifespan=lifespan)

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
        log_request_completed(request, status_code=response.status_code, duration_ms=duration_ms)
        reset_audit_context(token)
        return response

    @api.get('/health')
    def health():
        return {'status': 'ok'}

    @api.get('/api/health')
    def api_health():
        return {'status': 'ok'}

    api.include_router(router)
    return api


app = create_app()
