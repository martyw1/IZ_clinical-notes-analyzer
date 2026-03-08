from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.models import (
    AllevaBucket,
    ComplianceStatus,
    DocumentCompletionStatus,
    NoteSetStatus,
    NoteSetUploadMode,
    Role,
    WorkflowState,
)


class Token(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    must_reset_password: bool


class LoginInput(BaseModel):
    username: str
    password: str


class PasswordResetInput(BaseModel):
    new_password: str = Field(min_length=12)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    role: Role
    is_active: bool
    is_locked: bool
    must_reset_password: bool
    last_login_at: datetime | None = None
    created_at: datetime | None = None


class UserCreate(BaseModel):
    username: str
    full_name: str = ''
    password: str = Field(min_length=12)
    role: Role


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: Role | None = None
    is_active: bool | None = None
    is_locked: bool | None = None
    must_reset_password: bool | None = None


class UserPasswordResetAdmin(BaseModel):
    new_password: str = Field(min_length=12)
    require_reset_on_login: bool = True


class AuditTemplateItemOut(BaseModel):
    key: str
    step: int
    section: str
    label: str
    timeframe: str
    instructions: str
    evidence_hint: str
    policy_note: str | None = None


class AuditTemplateSectionOut(BaseModel):
    section: str
    items: list[AuditTemplateItemOut]


class AuditItemUpdate(BaseModel):
    item_key: str
    status: ComplianceStatus = ComplianceStatus.pending
    notes: str = ''
    evidence_location: str = ''
    evidence_date: str = ''
    expiration_date: str = ''


class AuditItemOut(AuditItemUpdate):
    step: int
    section: str
    label: str
    timeframe: str
    instructions: str
    evidence_hint: str
    policy_note: str | None = None


class ChartCreate(BaseModel):
    patient_id: str
    client_name: str = ''
    level_of_care: str
    admission_date: str = ''
    discharge_date: str = ''
    primary_clinician: str
    auditor_name: str = ''
    other_details: str = ''
    notes: str = ''


class ChartSummaryOut(BaseModel):
    id: int
    source_note_set_id: int | None = None
    patient_id: str
    client_name: str
    level_of_care: str
    admission_date: str
    discharge_date: str
    primary_clinician: str
    auditor_name: str
    other_details: str
    counselor_id: int
    state: WorkflowState
    system_score: int
    system_summary: str
    manager_comment: str
    reviewed_by_id: int | None = None
    system_generated_at: datetime | None = None
    reviewed_at: datetime | None = None
    notes: str
    pending_items: int
    passed_items: int
    failed_items: int
    not_applicable_items: int


class ChartDetailOut(ChartSummaryOut):
    checklist_items: list[AuditItemOut]


class ChartUpdate(BaseModel):
    patient_id: str
    client_name: str = ''
    level_of_care: str
    admission_date: str = ''
    discharge_date: str = ''
    primary_clinician: str
    auditor_name: str = ''
    other_details: str = ''
    notes: str = ''
    checklist_items: list[AuditItemUpdate]


class TransitionInput(BaseModel):
    to_state: WorkflowState
    comment: str = ''


class PatientNoteDocumentUploadInput(BaseModel):
    client_file_name: str = ''
    document_label: str = ''
    alleva_bucket: AllevaBucket = AllevaBucket.custom_forms
    document_type: str = 'clinical_note'
    completion_status: DocumentCompletionStatus = DocumentCompletionStatus.completed
    client_signed: bool = False
    staff_signed: bool = False
    document_date: str = ''
    description: str = ''


class PatientNoteDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_label: str
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    alleva_bucket: AllevaBucket
    document_type: str
    completion_status: DocumentCompletionStatus
    client_signed: bool
    staff_signed: bool
    document_date: str
    description: str
    created_at: datetime


class PatientNoteSetSummaryOut(BaseModel):
    id: int
    patient_id: str
    review_chart_id: int | None = None
    version: int
    status: NoteSetStatus
    upload_mode: NoteSetUploadMode
    source_system: str
    primary_clinician: str
    level_of_care: str
    admission_date: str
    discharge_date: str
    upload_notes: str
    created_at: datetime
    file_count: int


class PatientNoteSetDetailOut(PatientNoteSetSummaryOut):
    documents: list[PatientNoteDocumentOut]


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    timestamp_utc: datetime
    actor_username: str | None
    actor_role: str | None
    actor_type: str
    source_ip: str | None
    forwarded_for: str | None
    source_host: str | None
    source_port: int | None
    request_id: str
    correlation_id: str
    session_id: str | None
    http_method: str | None
    request_path: str | None
    route_template: str | None
    query_string: str | None
    http_status_code: int | None
    event_category: str
    action: str
    target_entity: str | None
    target_entity_type: str | None
    target_entity_id: str | None
    patient_id: str | None
    message: str
    details: str
    before_state: str | None
    after_state: str | None
    diff_state: str | None
    cef_extension: str
    cef_payload: str
    fhir_audit_event: str
    outcome_status: str
    severity: str
    prev_hash: str | None
    hash: str
