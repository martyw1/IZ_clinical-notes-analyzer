from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import event, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine

from app.core.config import settings
from app.v2.models import ApiHarnessJobRecord, AppSetting, Base, User, utc_now
from app.v2.migrations.runner import MigrationRequest, run_migrations
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
    _ensure_app_settings_columns()
    with SessionLocal() as db:
        _ensure_bootstrap_admin(db)
        _ensure_app_settings(db)
        db.commit()
    engine.dispose()
    run_migrations(
        MigrationRequest(
            database_path=settings.sqlite_db_path,
            local_app_data_dir=settings.local_app_data_dir,
            encryption_secret=settings.effective_data_encryption_secret,
            app_build=f"{settings.app_version}:{settings.build_channel}",
        )
    )
    with SessionLocal() as db:
        _mark_interrupted_jobs_stale(db)
        db.commit()


def _ensure_app_settings_columns() -> None:
    if not is_sqlite_database:
        return
    existing = {column["name"] for column in inspect(engine).get_columns("app_settings")}
    definitions = {
        "alleva_treatment_plan_sync_enabled": "BOOLEAN NOT NULL DEFAULT 0",
        "alleva_treatment_plan_sync_approved": "BOOLEAN NOT NULL DEFAULT 0",
        "alleva_treatment_plan_endpoint_mapping_validated": "BOOLEAN NOT NULL DEFAULT 0",
    }
    with engine.begin() as connection:
        for name, definition in definitions.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE app_settings ADD COLUMN {name} {definition}"))


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


def _mark_interrupted_jobs_stale(db: Session) -> None:
    rows = db.execute(select(ApiHarnessJobRecord).where(ApiHarnessJobRecord.status.in_(("queued", "running", "writing")))).scalars()
    for row in rows:
        row.status = "stale_or_interrupted"
        row.failed_at = utc_now()
        row.updated_at = utc_now()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
