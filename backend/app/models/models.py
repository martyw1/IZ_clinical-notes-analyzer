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
    awaiting_manager_review = 'Awaiting Office Manager Review'
    manager_rejected = 'Returned to Counselor'
    manager_approved = 'Approved by Office Manager'


class ComplianceStatus(str, enum.Enum):
    pending = 'pending'
    yes = 'yes'
    no = 'no'
    na = 'na'


class NoteSetStatus(str, enum.Enum):
    active = 'active'
    superseded = 'superseded'


class NoteSetUploadMode(str, enum.Enum):
    initial = 'initial'
    update = 'update'


class AllevaBucket(str, enum.Enum):
    custom_forms = 'custom_forms'
    uploaded_documents = 'uploaded_documents'
    portal_documents = 'portal_documents'
    labs = 'labs'
    medications = 'medications'
    notes = 'notes'
    other = 'other'


class DocumentCompletionStatus(str, enum.Enum):
    completed = 'completed'
    incomplete = 'incomplete'
    draft = 'draft'


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), default='')
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_reset_password: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AppSetting(Base):
    __tablename__ = 'app_settings'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_name: Mapped[str] = mapped_column(String(120), default='R3 Recovery Services')
    access_intel_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    access_geo_lookup_url: Mapped[str] = mapped_column(String(255), default='https://ipwho.is/{ip}')
    access_reputation_url: Mapped[str] = mapped_column(String(255), default='https://api.abuseipdb.com/api/v2/check')
    access_reputation_api_key: Mapped[str] = mapped_column(String(255), default='')
    access_lookup_timeout_seconds: Mapped[int] = mapped_column(Integer, default=4)
    llm_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    llm_provider_name: Mapped[str] = mapped_column(String(80), default='OpenAI-compatible')
    llm_base_url: Mapped[str] = mapped_column(String(255), default='https://api.openai.com/v1')
    llm_model: Mapped[str] = mapped_column(String(120), default='gpt-4.1-mini')
    llm_api_key: Mapped[str] = mapped_column(String(255), default='')
    llm_use_for_access_review: Mapped[bool] = mapped_column(Boolean, default=True)
    llm_use_for_evaluation_gap_analysis: Mapped[bool] = mapped_column(Boolean, default=True)
    llm_analysis_instructions: Mapped[str] = mapped_column(Text, default='')
    updated_by_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    updated_by: Mapped[User] = relationship(foreign_keys=[updated_by_id])


class Chart(Base):
    __tablename__ = 'charts'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_note_set_id: Mapped[int] = mapped_column(ForeignKey('patient_note_sets.id'), nullable=True, index=True)
    patient_id: Mapped[str] = mapped_column(String(120), default='', index=True)
    client_name: Mapped[str] = mapped_column(String(120), index=True)
    level_of_care: Mapped[str] = mapped_column(String(120))
    admission_date: Mapped[str] = mapped_column(String(40), default='')
    discharge_date: Mapped[str] = mapped_column(String(40), default='')
    primary_clinician: Mapped[str] = mapped_column(String(120))
    auditor_name: Mapped[str] = mapped_column(String(120), default='')
    other_details: Mapped[str] = mapped_column(Text, default='')
    counselor_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    state: Mapped[WorkflowState] = mapped_column(Enum(WorkflowState), default=WorkflowState.draft, index=True)
    system_score: Mapped[int] = mapped_column(Integer, default=0)
    system_summary: Mapped[str] = mapped_column(Text, default='')
    manager_comment: Mapped[str] = mapped_column(Text, default='')
    reviewed_by_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True)
    system_generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    counselor: Mapped[User] = relationship(foreign_keys=[counselor_id])
    source_note_set: Mapped['PatientNoteSet'] = relationship(back_populates='review_charts')
    reviewed_by: Mapped[User] = relationship(foreign_keys=[reviewed_by_id])
    audit_responses: Mapped[list['AuditItemResponse']] = relationship(cascade='all, delete-orphan', back_populates='chart')


class PatientNoteSet(Base):
    __tablename__ = 'patient_note_sets'
    __table_args__ = (UniqueConstraint('patient_id', 'version', name='uq_patient_note_sets_patient_version'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[NoteSetStatus] = mapped_column(Enum(NoteSetStatus), default=NoteSetStatus.active, index=True)
    upload_mode: Mapped[NoteSetUploadMode] = mapped_column(Enum(NoteSetUploadMode), default=NoteSetUploadMode.initial)
    source_system: Mapped[str] = mapped_column(String(80), default='Alleva EMR')
    primary_clinician: Mapped[str] = mapped_column(String(120), default='')
    level_of_care: Mapped[str] = mapped_column(String(120), default='')
    admission_date: Mapped[str] = mapped_column(String(40), default='')
    discharge_date: Mapped[str] = mapped_column(String(40), default='')
    upload_notes: Mapped[str] = mapped_column(Text, default='')
    replaced_note_set_id: Mapped[int] = mapped_column(ForeignKey('patient_note_sets.id'), nullable=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    uploaded_by: Mapped[User] = relationship()
    documents: Mapped[list['PatientNoteDocument']] = relationship(cascade='all, delete-orphan', back_populates='note_set')
    review_charts: Mapped[list[Chart]] = relationship(back_populates='source_note_set')


class PatientNoteDocument(Base):
    __tablename__ = 'patient_note_documents'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    note_set_id: Mapped[int] = mapped_column(ForeignKey('patient_note_sets.id'), index=True)
    document_label: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120), default='application/octet-stream')
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    alleva_bucket: Mapped[AllevaBucket] = mapped_column(Enum(AllevaBucket), default=AllevaBucket.custom_forms, index=True)
    document_type: Mapped[str] = mapped_column(String(80), default='clinical_note')
    completion_status: Mapped[DocumentCompletionStatus] = mapped_column(
        Enum(DocumentCompletionStatus),
        default=DocumentCompletionStatus.completed,
        index=True,
    )
    client_signed: Mapped[bool] = mapped_column(Boolean, default=False)
    staff_signed: Mapped[bool] = mapped_column(Boolean, default=False)
    document_date: Mapped[str] = mapped_column(String(40), default='')
    description: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    note_set: Mapped[PatientNoteSet] = relationship(back_populates='documents')


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
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True)
    actor_username: Mapped[str] = mapped_column(String(80), nullable=True)
    actor_role: Mapped[str] = mapped_column(String(40), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), default='human')
    source_ip: Mapped[str] = mapped_column(String(64), nullable=True)
    forwarded_for: Mapped[str] = mapped_column(String(255), nullable=True)
    source_host: Mapped[str] = mapped_column(String(255), nullable=True)
    source_port: Mapped[int] = mapped_column(Integer, nullable=True)
    user_agent: Mapped[str] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str] = mapped_column(String(128), nullable=True)
    http_method: Mapped[str] = mapped_column(String(16), nullable=True)
    request_path: Mapped[str] = mapped_column(String(255), nullable=True)
    route_template: Mapped[str] = mapped_column(String(255), nullable=True)
    query_string: Mapped[str] = mapped_column(Text, nullable=True)
    http_status_code: Mapped[int] = mapped_column(Integer, nullable=True)
    event_category: Mapped[str] = mapped_column(String(40), index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    target_entity: Mapped[str] = mapped_column(String(120), nullable=True)
    target_entity_type: Mapped[str] = mapped_column(String(80), nullable=True)
    target_entity_id: Mapped[str] = mapped_column(String(80), nullable=True)
    patient_id: Mapped[str] = mapped_column(String(120), nullable=True, index=True)
    message: Mapped[str] = mapped_column(Text, default='')
    details: Mapped[str] = mapped_column(Text, default='')
    before_state: Mapped[str] = mapped_column(Text, nullable=True)
    after_state: Mapped[str] = mapped_column(Text, nullable=True)
    diff_state: Mapped[str] = mapped_column(Text, nullable=True)
    cef_version: Mapped[int] = mapped_column(Integer, default=0)
    cef_device_vendor: Mapped[str] = mapped_column(String(80), default='OpenAI')
    cef_device_product: Mapped[str] = mapped_column(String(120), default='IZ Clinical Notes Analyzer')
    cef_device_version: Mapped[str] = mapped_column(String(40), default='1')
    cef_signature_id: Mapped[str] = mapped_column(String(120), default='')
    cef_name: Mapped[str] = mapped_column(String(255), default='')
    cef_severity: Mapped[int] = mapped_column(Integer, default=5)
    cef_extension: Mapped[str] = mapped_column(Text, default='')
    cef_payload: Mapped[str] = mapped_column(Text, default='')
    fhir_audit_event: Mapped[str] = mapped_column(Text, default='')
    outcome_status: Mapped[str] = mapped_column(String(20), default='success')
    severity: Mapped[str] = mapped_column(String(20), default='info')
    prev_hash: Mapped[str] = mapped_column(String(128), nullable=True)
    hash: Mapped[str] = mapped_column(String(128), index=True)
