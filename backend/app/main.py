from contextlib import asynccontextmanager
import logging
import os
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import router
from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.bootstrap import ensure_schema_compatibility
from app.db.session import SessionLocal, engine
from app.models.models import Role, User

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
    wait_for_database()
    ensure_schema_compatibility(engine)
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
        elif settings.reset_bootstrap_admin_on_startup and settings.environment != 'production':
            admin.password_hash = hash_password(settings.bootstrap_admin_password)
            admin.failed_login_attempts = 0
            admin.is_locked = False
            admin.must_reset_password = True
            db.commit()
    finally:
        db.close()


def create_app() -> FastAPI:
    os.makedirs(settings.upload_dir, exist_ok=True)

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

    @api.get('/health')
    def health():
        return {'status': 'ok'}

    @api.get('/api/health')
    def api_health():
        return {'status': 'ok'}

    api.include_router(router)
    return api


app = create_app()
