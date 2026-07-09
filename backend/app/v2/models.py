from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(40), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_reset_password: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_name: Mapped[str] = mapped_column(String(120), default="R3 Recovery Services")
    facility_timezone: Mapped[str] = mapped_column(String(80), default="local_machine")
    treatment_plan_master_due_days: Mapped[int] = mapped_column(Integer, default=30)
    treatment_plan_php_review_interval_days: Mapped[int] = mapped_column(Integer, default=30)
    treatment_plan_iop_op_review_interval_days: Mapped[int] = mapped_column(Integer, default=60)
    treatment_plan_loc_change_window_days: Mapped[int | None] = mapped_column(Integer, nullable=True, default=7)
    treatment_plan_loc_change_window_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    emr_vendor_name: Mapped[str] = mapped_column(String(120), default="Alleva REST API")
    api_base_url: Mapped[str] = mapped_column(String(500), default="https://api.allevasoft.com")
    openapi_url: Mapped[str] = mapped_column(String(500), default="https://api.allevasoft.com/swagger/v1/swagger.json")
    api_oauth_token_url: Mapped[str] = mapped_column(String(500), default="https://authorization.allevasoft.com/connect/token")
    api_token_auth_style: Mapped[str] = mapped_column(String(40), default="body")
    api_client_id: Mapped[str] = mapped_column(String(255), default="")
    api_client_secret: Mapped[str] = mapped_column(Text, default="")
    api_scopes: Mapped[str] = mapped_column(String(500), default="")
    emr_api_timeout_seconds: Mapped[int] = mapped_column(Integer, default=10)
    api_pagination_limit: Mapped[int] = mapped_column(Integer, default=100)
    alleva_treatment_plan_sync_limit: Mapped[int] = mapped_column(Integer, default=250)
    emr_api_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    actor_id: Mapped[str] = mapped_column(String(80), default="system")
    actor_username: Mapped[str] = mapped_column(String(80), default="")
    actor_role: Mapped[str] = mapped_column(String(40), default="system")
    action: Mapped[str] = mapped_column(String(120), index=True)
    target_entity_type: Mapped[str] = mapped_column(String(80), default="system")
    target_entity_id: Mapped[str] = mapped_column(String(120), default="")
    outcome_status: Mapped[str] = mapped_column(String(20), default="success")
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    prev_hash: Mapped[str] = mapped_column(String(128), default="")
    hash: Mapped[str] = mapped_column(String(128), index=True)


class TreatmentPlanImport(Base):
    __tablename__ = "treatment_plan_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    patient_display_label: Mapped[str] = mapped_column(String(120), default="")
    plan_id: Mapped[str] = mapped_column(String(120), default="")
    source_mode: Mapped[str] = mapped_column(String(40), default="manual_upload", index=True)
    current_level_of_care: Mapped[str] = mapped_column(String(80), default="")
    admission_date: Mapped[str] = mapped_column(String(40), default="")
    next_due_date: Mapped[str] = mapped_column(String(40), default="")
    overall_status: Mapped[str] = mapped_column(String(80), default="Needs Review", index=True)
    missing_criteria_count: Mapped[int] = mapped_column(Integer, default=0)
    returned_criteria_count: Mapped[int] = mapped_column(Integer, default=0)
    content_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    content_hash: Mapped[str] = mapped_column(String(128), default="", index=True)
    encrypted_payload: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UploadedDocument(Base):
    __tablename__ = "uploaded_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    patient_id: Mapped[str] = mapped_column(String(80), index=True)
    plan_id: Mapped[str] = mapped_column(String(120), index=True)
    source_kind: Mapped[str] = mapped_column(String(80), index=True)
    source_format: Mapped[str] = mapped_column(String(40), default="")
    content_type: Mapped[str] = mapped_column(String(120), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(128), index=True)
    storage_path: Mapped[str] = mapped_column(String(500))
    redaction_status: Mapped[str] = mapped_column(String(80), default="encrypted_original_file")
    created_by_user_id: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class TreatmentPlanManagerAction(Base):
    __tablename__ = "treatment_plan_manager_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(80), index=True)
    criterion_id: Mapped[str] = mapped_column(String(160), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    override_reason: Mapped[str] = mapped_column(Text, default="")
    actor_user_id: Mapped[str] = mapped_column(String(80), default="")
    actor_username: Mapped[str] = mapped_column(String(80), default="")
    actor_role: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
