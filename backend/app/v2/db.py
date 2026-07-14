from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import event, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine

from app.core.config import settings
from app.v2.models import ApiHarnessJobRecord, AppSetting, Base, User, utc_now
from app.v2.migrations.runner import MigrationRequest, run_migrations
from app.v2.security import hash_password
from app.v2.services.evaluation_store import reevaluate_all_plan_versions
from app.v2.services.legacy_settings_migration import migrate_legacy_api_settings

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
    if not settings.sqlite_db_path.is_file():
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            _ensure_bootstrap_admin(db)
            _ensure_app_settings(db)
            db.commit()
    engine.dispose()
    migration_report = run_migrations(
        MigrationRequest(
            database_path=settings.sqlite_db_path,
            local_app_data_dir=settings.local_app_data_dir,
            encryption_secret=settings.effective_data_encryption_secret,
            app_build=f"{settings.app_version}:{settings.build_channel}",
        )
    )
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        _ensure_bootstrap_admin(db)
        _ensure_app_settings(db)
        migrate_legacy_api_settings(
            db,
            settings.legacy_sqlite_db_path,
            settings.effective_data_encryption_secret,
        )
        _mark_interrupted_jobs_stale(db)
        _ensure_admin_facilities(db)
        reevaluate_all_plan_versions(db, "migration" if migration_report.applied_versions else "startup")
        db.commit()


def _ensure_bootstrap_admin(db: Session) -> None:
    username = settings.bootstrap_admin_username.strip() or "admin"
    existing_id = db.execute(select(User.id).where(User.username == username)).scalar_one_or_none()
    if existing_id is not None:
        return
    db.add(
        User(
            username=username,
            full_name="System Administrator",
            password_hash=hash_password(settings.bootstrap_admin_password),
            role="admin",
            is_active=True,
            must_reset_password=True,
            failed_login_attempts=0,
            is_locked=False,
            auth_state="bootstrap_required",
        )
    )


def _ensure_app_settings(db: Session) -> None:
    existing_id = db.execute(select(AppSetting.id)).scalar_one_or_none()
    if existing_id is not None:
        return
    db.add(AppSetting())


def _mark_interrupted_jobs_stale(db: Session) -> None:
    rows = db.execute(select(ApiHarnessJobRecord).where(ApiHarnessJobRecord.status.in_(("queued", "running", "writing")))).scalars()
    for row in rows:
        row.status = "stale_or_interrupted"
        row.failed_at = utc_now()
        row.updated_at = utc_now()


def _ensure_admin_facilities(db: Session) -> None:
    db.execute(
        text(
            "INSERT OR IGNORE INTO user_facilities"
            "(user_id,facility_id,assigned_by_user_id,assigned_at) "
            "SELECT target.id,facility.id,administrator.id,:assigned_at "
            "FROM users target CROSS JOIN facilities facility "
            "CROSS JOIN (SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1) administrator "
            "WHERE target.role='admin' AND facility.is_active=1"
        ),
        {"assigned_at": utc_now().isoformat()},
    )


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
