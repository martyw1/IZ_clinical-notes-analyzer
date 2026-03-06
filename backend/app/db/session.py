import os

from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


def resolve_database_url(database_url: str, *, in_docker: bool | None = None) -> str:
    if not database_url.startswith('postgresql'):
        return database_url

    if in_docker is None:
        in_docker = os.path.exists('/.dockerenv')

    if not in_docker:
        return database_url

    parsed_url = make_url(database_url)
    if parsed_url.host in {'localhost', '127.0.0.1', '::1'}:
        parsed_url = parsed_url.set(host='db')
        return str(parsed_url)

    return database_url


connect_args = {'check_same_thread': False} if settings.database_url.startswith('sqlite') else {}
engine = create_engine(resolve_database_url(settings.database_url), connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
