from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine

from app.core.config import settings
from app.v2.models import AppSetting, Base, User
from app.v2.security import hash_password

is_sqlite_database = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False, "timeout": 30} if is_sqlite_database else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


if is_sqlite_database:

    @event.listens_for(engine, "connect")
    def configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            if settings.database_url != "sqlite:///:memory:":
                cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()


def init_database() -> None:
    settings.sqlite_db_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        _ensure_bootstrap_admin(db)
        _ensure_app_settings(db)
        db.commit()


def _ensure_bootstrap_admin(db: Session) -> None:
    username = settings.bootstrap_admin_username.strip() or "admin"
    existing = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if existing:
        return
    db.add(
        User(
            username=username,
            full_name="System Administrator",
            password_hash=hash_password(settings.bootstrap_admin_password),
            role="admin",
            is_active=True,
            must_reset_password=False,
            failed_login_attempts=0,
            is_locked=False,
        )
    )


def _ensure_app_settings(db: Session) -> None:
    existing = db.execute(select(AppSetting)).scalar_one_or_none()
    if existing:
        return
    db.add(AppSetting())


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
