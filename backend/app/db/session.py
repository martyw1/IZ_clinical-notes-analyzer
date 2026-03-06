import os

from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


LOCALHOST_ALIASES = {'localhost', '127.0.0.1', '::1'}


def resolve_database_url(
    database_url: str,
    *,
    in_docker: bool | None = None,
    database_host_mode: str | None = None,
) -> str:
    if not database_url.startswith('postgresql'):
        return database_url

    if in_docker is None:
        in_docker = os.path.exists('/.dockerenv')

    if not in_docker:
        return database_url

    parsed_url = make_url(database_url)
    if parsed_url.host not in LOCALHOST_ALIASES:
        return database_url

    mode = (database_host_mode or settings.database_host_mode or 'internal').strip().lower()
    if mode == 'external':
        return database_url

    if mode == 'host':
        rewritten = parsed_url.set(host='host.docker.internal')
        return rewritten.render_as_string(hide_password=False)

    rewritten = parsed_url.set(host='db')
    return rewritten.render_as_string(hide_password=False)


resolved_database_url = resolve_database_url(settings.database_url)
connect_args = {'check_same_thread': False} if resolved_database_url.startswith('sqlite') else {}
engine = create_engine(resolved_database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
