import os

from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker
from fastapi import Request

from app.core.config import settings
from app.services.audit import attach_audit_context, refresh_request_context, register_session_audit_events


LOCALHOST_ALIASES = {'localhost', '127.0.0.1', '::1'}
LEGACY_POSTGRES_DRIVER = 'postgresql+psycopg2'
CURRENT_POSTGRES_DRIVER = 'postgresql+psycopg'


def normalize_database_driver(database_url: str) -> str:
    if not database_url.startswith('postgresql'):
        return database_url

    parsed_url = make_url(database_url)
    if parsed_url.drivername != LEGACY_POSTGRES_DRIVER:
        return database_url

    rewritten = parsed_url.set(drivername=CURRENT_POSTGRES_DRIVER)
    return rewritten.render_as_string(hide_password=False)


def resolve_database_url(
    database_url: str,
    *,
    in_docker: bool | None = None,
    postgres_service_host: str = 'postgres',
) -> str:
    normalized_url = normalize_database_driver(database_url)
    if not normalized_url.startswith('postgresql'):
        return database_url

    if in_docker is None:
        in_docker = os.path.exists('/.dockerenv')

    if not in_docker:
        return normalized_url

    parsed_url = make_url(normalized_url)
    if parsed_url.host not in LOCALHOST_ALIASES:
        return normalized_url

    rewritten = parsed_url.set(host=postgres_service_host)
    return rewritten.render_as_string(hide_password=False)


resolved_database_url = resolve_database_url(settings.database_url_value, postgres_service_host=settings.postgres_service_host)
connect_args = {'check_same_thread': False} if resolved_database_url.startswith('sqlite') else {}
engine = create_engine(resolved_database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
register_session_audit_events(SessionLocal)


def get_db(request: Request):
    db = SessionLocal()
    refresh_request_context(request)
    attach_audit_context(db)
    try:
        yield db
    finally:
        db.close()
