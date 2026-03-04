import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Role(str, enum.Enum):
    admin = 'admin'
    counselor = 'counselor'
    manager = 'manager'


class WorkflowState(str, enum.Enum):
    draft = 'Draft'
    submitted = 'Submitted to Admin'
    returned = 'Returned for Update'
    in_progress = 'In Progress Review'
    completed = 'Completed'
    verified = 'Verified'


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), index=True)
    must_reset_password: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Chart(Base):
    __tablename__ = 'charts'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_name: Mapped[str] = mapped_column(String(120), index=True)
    level_of_care: Mapped[str] = mapped_column(String(120))
    primary_clinician: Mapped[str] = mapped_column(String(120))
    counselor_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    state: Mapped[WorkflowState] = mapped_column(Enum(WorkflowState), default=WorkflowState.draft, index=True)
    notes: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    counselor: Mapped[User] = relationship()


class WorkflowTransition(Base):
    __tablename__ = 'workflow_transitions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chart_id: Mapped[int] = mapped_column(ForeignKey('charts.id'), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    from_state: Mapped[str] = mapped_column(String(64))
    to_state: Mapped[str] = mapped_column(String(64))
    comment: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AuditLog(Base):
    __tablename__ = 'audit_logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    actor_username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    target_entity: Mapped[str | None] = mapped_column(String(120), nullable=True)
    details: Mapped[str] = mapped_column(Text, default='')
    outcome_status: Mapped[str] = mapped_column(String(20), default='success')
    severity: Mapped[str] = mapped_column(String(20), default='info')
    prev_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    hash: Mapped[str] = mapped_column(String(128), index=True)
