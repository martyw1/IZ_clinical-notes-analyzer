from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.models import (
    AllevaBucket,
    ComplianceStatus,
    DocumentCompletionStatus,
    NoteSetStatus,
    NoteSetUploadMode,
    Role,
    WorkflowDefinitionVersionStatus,
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


class UserSelfUpdate(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)


class UserPasswordChangeInput(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12)


class AppSettingsUpdate(BaseModel):
    organization_name: str | None = Field(default=None, max_length=120)
    access_intel_enabled: bool | None = None
    access_geo_lookup_url: str | None = Field(default=None, max_length=255)
    access_reputation_url: str | None = Field(default=None, max_length=255)
    access_reputation_api_key: str | None = None
    clear_access_reputation_api_key: bool = False
    access_lookup_timeout_seconds: int | None = Field(default=None, ge=1, le=30)
    llm_enabled: bool | None = None
    llm_provider_name: str | None = Field(default=None, max_length=80)
    llm_base_url: str | None = Field(default=None, max_length=255)
    llm_model: str | None = Field(default=None, max_length=120)
    llm_api_key: str | None = None
    clear_llm_api_key: bool = False
    llm_use_for_access_review: bool | None = None
    llm_use_for_evaluation_gap_analysis: bool | None = None
    llm_analysis_instructions: str | None = None
    emr_api_enabled: bool | None = None
    emr_vendor_name: str | None = Field(default=None, max_length=120)
    emr_fhir_base_url: str | None = Field(default=None, max_length=255)
    emr_smart_client_id: str | None = Field(default=None, max_length=255)
    emr_smart_client_secret: str | None = None
    clear_emr_smart_client_secret: bool = False
    emr_smart_token_url: str | None = Field(default=None, max_length=500)
    emr_smart_token_auth_style: str | None = Field(default=None, pattern=r'^(body|basic|basic_urlencoded|both|all)$')
    emr_smart_scopes: str | None = Field(default=None, max_length=500)
    emr_api_timeout_seconds: int | None = Field(default=None, ge=1, le=60)
    emr_periodic_check_enabled: bool | None = None
    emr_periodic_check_interval_minutes: int | None = Field(default=None, ge=5, le=10080)
    facility_timezone: str | None = Field(default=None, max_length=80)
    treatment_plan_loc_change_window_days: int | None = Field(default=None, ge=0, le=365)
    treatment_plan_loc_change_window_validated: bool | None = None


class AppSettingsOut(BaseModel):
    organization_name: str
    access_intel_enabled: bool
    access_geo_lookup_url: str
    access_reputation_url: str
    access_reputation_api_key_configured: bool
    access_lookup_timeout_seconds: int
    llm_enabled: bool
    llm_provider_name: str
    llm_base_url: str
    llm_model: str
    llm_api_key_configured: bool
    llm_use_for_access_review: bool
    llm_use_for_evaluation_gap_analysis: bool
    llm_analysis_instructions: str
    emr_api_enabled: bool
    emr_vendor_name: str
    emr_fhir_base_url: str
    emr_smart_client_id: str
    emr_smart_client_secret_configured: bool
    emr_smart_token_url: str
    emr_smart_token_auth_style: str
    emr_smart_scopes: str
    emr_api_timeout_seconds: int
    emr_periodic_check_enabled: bool
    emr_periodic_check_interval_minutes: int
    emr_last_check_at: datetime | None = None
    emr_last_check_status: str
    emr_last_check_message: str
    emr_last_successful_check_at: datetime | None = None
    emr_last_failure_at: datetime | None = None
    facility_timezone: str
    effective_timezone: str
    effective_timezone_label: str
    treatment_plan_loc_change_window_days: int | None = None
    treatment_plan_loc_change_window_validated: bool
    updated_by_id: int | None = None
    updated_at: datetime | None = None


class RuntimeCheckOut(BaseModel):
    name: str
    status: str
    message: str
    detail: str = ''


class ReadinessOut(BaseModel):
    status: str
    failed: int
    warnings: int
    checks: list[RuntimeCheckOut]


class EmrDiscoveryInput(BaseModel):
    fhir_base_url: str | None = Field(default=None, max_length=255)


class EmrDiscoveryOut(BaseModel):
    status: str
    fhir_base_url: str
    smart_configuration_url: str
    authorization_endpoint_configured: bool
    token_endpoint_configured: bool
    capabilities: list[str]
    message: str


class EmrConnectionProfileOut(BaseModel):
    adapter_key: str
    enabled: bool
    vendor_name: str
    live_import_status: str
    fhir_base_url: str
    smart_discovery_url: str | None
    client_id_configured: bool
    client_secret_configured: bool
    scopes: list[str]
    supported_resources: list[str]
    standards: list[str]
    supported_export_formats: list[str]
    document_manager_sections: list[dict[str, str]]
    required_vendor_inputs: list[str]


class EmrImportPlanOut(BaseModel):
    patient_id: str
    fhir_base_url: str
    source_identifier_note: str
    planned_requests: list[dict[str, str]]
    alleva_notes: list[str]
    supported_export_formats: list[str]
    document_manager_sections: list[dict[str, str]]
    attachment_handling: str
    document_mapping: dict[str, str]


class EmrEndpointProfileBase(BaseModel):
    profile_key: str = Field(min_length=3, max_length=80, pattern=r'^[a-z0-9][a-z0-9_-]*$')
    display_name: str = Field(min_length=1, max_length=120)
    vendor_name: str = Field(default='Alleva', max_length=120)
    adapter_key: str = Field(default='alleva-fhir-document-manager', max_length=120)
    fhir_base_url: str = Field(default='', max_length=500)
    openapi_url: str = Field(default='', max_length=500)
    token_url: str = Field(default='', max_length=500)
    token_auth_style: str = Field(default='body', pattern=r'^(body|basic|basic_urlencoded|both|all)$')
    client_id: str = Field(default='', max_length=255)
    scopes: str = Field(default='', max_length=500)
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    is_active: bool = True
    is_default: bool = False
    notes: str = Field(default='', max_length=2000)


class EmrEndpointProfileCreate(EmrEndpointProfileBase):
    client_secret: str | None = None


class EmrEndpointProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    vendor_name: str | None = Field(default=None, max_length=120)
    adapter_key: str | None = Field(default=None, max_length=120)
    fhir_base_url: str | None = Field(default=None, max_length=500)
    openapi_url: str | None = Field(default=None, max_length=500)
    token_url: str | None = Field(default=None, max_length=500)
    token_auth_style: str | None = Field(default=None, pattern=r'^(body|basic|basic_urlencoded|both|all)$')
    client_id: str | None = Field(default=None, max_length=255)
    client_secret: str | None = None
    clear_client_secret: bool = False
    scopes: str | None = Field(default=None, max_length=500)
    timeout_seconds: int | None = Field(default=None, ge=1, le=60)
    is_active: bool | None = None
    is_default: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class EmrEndpointProfileOut(BaseModel):
    id: int
    profile_key: str
    display_name: str
    vendor_name: str
    adapter_key: str
    fhir_base_url: str
    openapi_url: str
    token_url: str
    token_auth_style: str
    client_id: str
    client_id_configured: bool
    client_secret_configured: bool
    scopes: str
    timeout_seconds: int
    is_active: bool
    is_default: bool
    notes: str
    created_by_id: int | None = None
    updated_by_id: int | None = None
    created_at: datetime
    updated_at: datetime


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


class TreatmentPlanChecklistAcronymOut(BaseModel):
    term: str
    definition: str
    validation_status: str


class TreatmentPlanChecklistStatusOut(BaseModel):
    key: str
    label: str
    description: str


class TreatmentPlanChecklistStepOut(BaseModel):
    step: int
    key: str
    title: str
    source_modes: list[str]
    objective: str
    required_metadata: list[str]
    required_documents: list[str]
    checks: list[str]
    finding_examples: list[str]
    remediation_suggestions: list[str]
    evidence_fields: list[str]
    automation_level: str
    severity_default: str
    status_options: list[str]
    reviewer_actions: list[str]
    manual_override: bool
    override_reason_required: bool
    audit_event: str
    export_fields: list[str]


class TreatmentPlanChecklistOut(BaseModel):
    checklist_id: str
    version: str
    display_name: str
    organization: str
    status: str
    last_updated: str
    source_of_truth: str
    review_owner_roles: list[str]
    viewer_roles: list[str]
    acronyms: list[TreatmentPlanChecklistAcronymOut]
    review_statuses: list[TreatmentPlanChecklistStatusOut]
    loc_change_blocker: dict[str, str]
    steps: list[TreatmentPlanChecklistStepOut]


class ReviewSourceItemOut(BaseModel):
    source_type: str
    source_item_id: str
    patient_id: str
    display_name: str
    document_type: str
    source_system_or_file: str
    review_status: str
    status_reason: str
    service_date: str
    plan_date: str
    provider_staff: str
    program_location: str
    last_changed_at: str
    review_chart_id: int | None = None
    timeliness_client_id: int | None = None


class ReviewSourceDiscoveryOut(BaseModel):
    checklist_id: str
    checklist_version: str
    last_refreshed_at: str
    last_refresh_at: str
    last_successful_check_at: str
    last_failure_at: str
    next_refresh_at: str
    live_import_enabled: bool
    live_import_status: str
    api_configured: bool
    api_mode: str
    api_mode_label: str
    daily_monitoring_enabled: bool
    refresh_mode: str
    last_check_mode: str
    changed_item_count: int
    error_count: int
    notification_badge_count: int
    manual_review_cadence: str
    manual_mode_message: str
    plain_english_status: str
    status_counts: dict[str, int]
    items: list[ReviewSourceItemOut]


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
    created_at: datetime | None = None
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


class WorkflowDefinitionVersionInput(BaseModel):
    definition_snapshot: dict[str, Any] = Field(default_factory=dict)
    transition_rules: list[dict[str, Any]] = Field(default_factory=list)
    version_notes: str = Field(default='', max_length=2000)


class WorkflowDefinitionCreate(BaseModel):
    workflow_key: str = Field(min_length=3, max_length=80, pattern=r'^[a-z0-9][a-z0-9_-]*$')
    display_name: str = Field(min_length=1, max_length=120)
    description: str = Field(default='', max_length=2000)
    category: str = Field(default='clinical_review', max_length=80)
    is_active: bool = True
    initial_version: WorkflowDefinitionVersionInput | None = None


class WorkflowDefinitionUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=80)
    is_active: bool | None = None


class WorkflowDefinitionVersionOut(BaseModel):
    id: int
    workflow_definition_id: int
    version: int
    status: WorkflowDefinitionVersionStatus
    definition_snapshot: dict[str, Any]
    transition_rules: list[dict[str, Any]]
    version_notes: str
    created_by_id: int
    published_by_id: int | None = None
    archived_by_id: int | None = None
    created_at: datetime
    published_at: datetime | None = None
    archived_at: datetime | None = None


class WorkflowDefinitionOut(BaseModel):
    id: int
    workflow_key: str
    display_name: str
    description: str
    category: str
    is_active: bool
    current_version_id: int | None = None
    created_by_id: int
    updated_by_id: int | None = None
    created_at: datetime
    updated_at: datetime
    current_version: WorkflowDefinitionVersionOut | None = None
    versions: list[WorkflowDefinitionVersionOut] = Field(default_factory=list)


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
    source_document_id: str = ''
    source_document_reference_id: str = ''
    source_attachment_url: str = ''
    source_author: str = ''
    source_custodian: str = ''
    source_security_label: str = ''
    source_provenance_id: str = ''


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
    source_document_id: str
    source_document_reference_id: str
    source_attachment_url: str
    source_author: str
    source_custodian: str
    source_security_label: str
    source_provenance_id: str
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
    source_export_id: str
    source_patient_resource_id: str
    created_at: datetime
    file_count: int


class PatientNoteSetDetailOut(PatientNoteSetSummaryOut):
    documents: list[PatientNoteDocumentOut]


class PatientIdDetectionOut(BaseModel):
    patient_id: str | None = None
    confidence: str
    source_filename: str | None = None
    source_kind: str | None = None
    match_text: str | None = None
    reason: str


class UiEventInput(BaseModel):
    screen: str = Field(default='', max_length=80)
    action_name: str = Field(min_length=1, max_length=160)
    result: str = Field(default='clicked', max_length=40)
    context: dict[str, Any] = Field(default_factory=dict)


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    timestamp_utc: datetime
    timestamp_local: str = ''
    effective_timezone: str = ''
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


class TimelinessLevelOfCareInput(BaseModel):
    level_of_care: str
    facility: str = ''
    effective_date: str = ''
    discharge_date: str = ''
    source_evidence: str = ''


class TimelinessTreatmentPlanInput(BaseModel):
    plan_kind: str
    document_date: str = ''
    staff_signature_date: str = ''
    client_signature_date: str = ''
    reviewer_signature_date: str = ''
    displayed_next_due_date: str = ''
    source_evidence: str = ''
    source_section: str = ''
    source_document_id: str = ''
    is_valid: bool = True
    conflict_note: str = ''


class TimelinessClientUpsert(BaseModel):
    patient_id: str
    permitted_name: str = ''
    is_active: bool = True
    current_level_of_care: str = ''
    counselor_name: str = ''
    admission_date: str = ''
    source_evidence: str = ''
    level_of_care_history: list[TimelinessLevelOfCareInput] = Field(default_factory=list)
    treatment_plans: list[TimelinessTreatmentPlanInput] = Field(default_factory=list)


class TimelinessOverrideInput(BaseModel):
    field_name: str = Field(min_length=1, max_length=120)
    original_value: str = ''
    new_value: str = ''
    reason: str = Field(min_length=1, max_length=1000)
    affected_rule: str = Field(default='', max_length=120)


class TimelinessLevelOfCareOut(BaseModel):
    id: int
    level_of_care: str
    facility: str
    effective_date: str
    discharge_date: str
    interval_days: int | None = None
    is_current: bool
    source_evidence: str


class TimelinessTreatmentPlanOut(BaseModel):
    id: int
    plan_kind: str
    document_date: str
    staff_signature_date: str
    client_signature_date: str
    reviewer_signature_date: str
    displayed_next_due_date: str
    source_evidence: str
    source_section: str
    source_document_id: str
    is_valid: bool
    conflict_note: str


class TimelinessOverrideOut(BaseModel):
    id: int
    field_name: str
    original_value: str
    new_value: str
    reason: str
    affected_rule: str
    created_by_id: int
    created_at: datetime


class TimelinessRuleResultOut(BaseModel):
    rule_id: str
    label: str
    due_date: str | None = None
    status: str
    evidence_summary: str


class TimelinessEvidenceComparisonOut(BaseModel):
    document_next_due_date: str | None = None
    signature_anchor_due_date: str | None = None
    loc_anchor_due_date: str | None = None
    final_status: str
    conflict_explanation: str
    source_evidence: str
    staff_signature_date: str | None = None
    loc_effective_date: str | None = None
    interval_days: int | None = None
    loc_change_window_days: int | None = None
    loc_change_rule_validated: bool


class TimelinessClientSummaryOut(BaseModel):
    id: int
    patient_id: str
    permitted_name: str
    current_level_of_care: str
    counselor_name: str
    admission_date: str
    last_valid_review_date: str | None = None
    next_due_date: str | None = None
    days_until_due: int | None = None
    status: str
    rule_used: str
    evidence_summary: str
    evidence_completeness_percent: int
    missing_evidence_fields: list[str]
    last_checked_at: datetime
    last_imported_at: datetime | None = None


class TimelinessDashboardOut(BaseModel):
    total_active_clients: int
    compliant: int
    due_soon: int
    urgent: int
    overdue: int
    returned: int = 0
    needs_review: int
    missing_data: int
    conflicting_evidence: int = 0
    unable_to_evaluate: int = 0
    approved: int = 0
    compliance_percentage: float
    loc_change_window_days: int | None = None
    loc_change_window_validated: bool
    items: list[TimelinessClientSummaryOut]


class TimelinessClientDetailOut(TimelinessClientSummaryOut):
    is_active: bool
    source_evidence: str
    evidence_comparison: TimelinessEvidenceComparisonOut
    rule_results: list[TimelinessRuleResultOut]
    level_of_care_history: list[TimelinessLevelOfCareOut]
    treatment_plans: list[TimelinessTreatmentPlanOut]
    overrides: list[TimelinessOverrideOut]
    audit_history: list[AuditLogOut]
