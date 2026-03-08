import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
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


class ComplianceStatus(str, enum.Enum):
    pending = 'pending'
    yes = 'yes'
    no = 'no'
    na = 'na'


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
    admission_date: Mapped[str] = mapped_column(String(40), default='')
    discharge_date: Mapped[str] = mapped_column(String(40), default='')
    primary_clinician: Mapped[str] = mapped_column(String(120))
    auditor_name: Mapped[str] = mapped_column(String(120), default='')
    other_details: Mapped[str] = mapped_column(Text, default='')
    counselor_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    state: Mapped[WorkflowState] = mapped_column(Enum(WorkflowState), default=WorkflowState.draft, index=True)
    notes: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    counselor: Mapped[User] = relationship()
    audit_responses: Mapped[list['AuditItemResponse']] = relationship(cascade='all, delete-orphan', back_populates='chart')


class WorkflowTransition(Base):
    __tablename__ = 'workflow_transitions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chart_id: Mapped[int] = mapped_column(ForeignKey('charts.id'), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    from_state: Mapped[str] = mapped_column(String(64))
    to_state: Mapped[str] = mapped_column(String(64))
    comment: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AuditItemResponse(Base):
    __tablename__ = 'audit_item_responses'
    __table_args__ = (UniqueConstraint('chart_id', 'item_key', name='uq_chart_audit_item_key'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chart_id: Mapped[int] = mapped_column(ForeignKey('charts.id'), index=True)
    item_key: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[ComplianceStatus] = mapped_column(Enum(ComplianceStatus), default=ComplianceStatus.pending, index=True)
    notes: Mapped[str] = mapped_column(Text, default='')
    evidence_location: Mapped[str] = mapped_column(String(255), default='')
    evidence_date: Mapped[str] = mapped_column(String(80), default='')
    expiration_date: Mapped[str] = mapped_column(String(80), default='')
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    chart: Mapped[Chart] = relationship(back_populates='audit_responses')


class AuditLog(Base):
    __tablename__ = 'audit_logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True)
    actor_username: Mapped[str] = mapped_column(String(80), nullable=True)
    actor_role: Mapped[str] = mapped_column(String(40), nullable=True)
    source_ip: Mapped[str] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    target_entity: Mapped[str] = mapped_column(String(120), nullable=True)
    details: Mapped[str] = mapped_column(Text, default='')
    outcome_status: Mapped[str] = mapped_column(String(20), default='success')
    severity: Mapped[str] = mapped_column(String(20), default='info')
    prev_hash: Mapped[str] = mapped_column(String(128), nullable=True)
    hash: Mapped[str] = mapped_column(String(128), index=True)
