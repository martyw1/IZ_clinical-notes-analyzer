from __future__ import annotations

from datetime import datetime
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class V2Model(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)


class LoginInput(V2Model):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class TokenOut(V2Model):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    must_reset_password: bool = False
    auth_state: Literal["password_change_required", "active"]


class ReadinessCheck(V2Model):
    name: str
    status: Literal["ok", "warn", "fail"]
    path: str | None = None
    value: str | None = None
    message: str | None = None


class ReadinessOut(V2Model):
    status: Literal["ok", "warn", "fail"]
    runtime: Literal["v2"]
    checks: tuple[ReadinessCheck, ...]


class UserOut(V2Model):
    id: int
    username: str
    full_name: str
    role: Literal["admin", "office_manager", "counselor", "viewer"]
    is_active: bool
    is_locked: bool = False
    must_reset_password: bool = False
    auth_state: Literal["bootstrap_required", "password_change_required", "active", "locked_until"]
    locked_until: str | None = None
    facility_ids: tuple[int, ...] = ()
    last_login_at: str | None = None
    created_at: str | None = None


class UserCreate(V2Model):
    username: str = Field(min_length=1)
    full_name: str = ""
    role: Literal["admin", "office_manager", "counselor", "viewer"]
    password: str = Field(min_length=1)


class UserUpdate(V2Model):
    full_name: str | None = None
    role: Literal["admin", "office_manager", "counselor", "viewer"] | None = None
    is_active: bool | None = None
    is_locked: bool | None = None
    must_reset_password: bool | None = None


class UserPasswordResetAdmin(V2Model):
    new_password: str = Field(min_length=1)
    require_reset_on_login: bool = True


class UserPasswordChange(V2Model):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


class FacilityOut(V2Model):
    id: int
    facility_key: str
    display_name: str
    timezone: str
    is_active: bool


class AssignmentOut(V2Model):
    patient_id: str
    counselor_username: str
    is_active: bool


class DashboardSourceCardOut(V2Model):
    label: str
    status: str
    detail: str


class DashboardOut(V2Model):
    source_cards: tuple[DashboardSourceCardOut, ...]
    metrics: dict[str, int]
    blockers: tuple[str, ...]


class TreatmentPlanListItemOut(V2Model):
    patient_id: str
    patient_display_label: str
    current_level_of_care: str
    admission_date: str
    next_due_date: str
    status: str
    missing_criteria_count: int
    returned_criteria_count: int
    source_mode: str
    content_completeness_summary: dict[str, int]
    warnings: tuple[str, ...]


class TreatmentPlanListOut(V2Model):
    items: tuple[TreatmentPlanListItemOut, ...]
    status_order: tuple[str, ...]


class AppSettingsUpdate(V2Model):
    organization_name: str | None = None
    facility_timezone: str | None = None
    treatment_plan_master_due_days: int | None = Field(default=None, ge=1, le=365)
    treatment_plan_php_review_interval_days: int | None = Field(default=None, ge=1, le=365)
    treatment_plan_iop_op_review_interval_days: int | None = Field(default=None, ge=1, le=365)
    treatment_plan_loc_change_window_days: int | None = Field(default=None, ge=0, le=365)
    treatment_plan_loc_change_window_validated: bool | None = None


class AppSettingsOut(V2Model):
    organization_name: str
    facility_timezone: str
    treatment_plan_master_due_days: int
    treatment_plan_php_review_interval_days: int
    treatment_plan_iop_op_review_interval_days: int
    treatment_plan_loc_change_window_days: int | None
    treatment_plan_loc_change_window_validated: bool


class ApiConfigurationUpdate(V2Model):
    vendor_name: str = "Alleva REST API"
    api_base_url: str = "https://api.allevasoft.com"
    api_key: str | None = None
    openapi_url: str | None = None
    token_url: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    token_auth_style: Literal["body", "basic"] | None = None
    scopes: str | None = None
    pagination_limit: int | None = Field(default=None, ge=1, le=5000)
    sync_limit: int | None = Field(default=None, ge=1, le=5000)
    timeout_seconds: int = 10
    api_enabled: bool = False
    treatment_plan_sync_enabled: bool = False
    treatment_plan_sync_approved: bool = False
    treatment_plan_endpoint_mapping_validated: bool = False


class ApiConfigurationOut(V2Model):
    vendor_name: str
    api_base_url: str
    openapi_url: str
    token_url: str
    client_id: str
    api_key_configured: bool
    client_secret_configured: bool = False
    token_auth_style: str
    scopes: str
    pagination_limit: int
    sync_limit: int
    timeout_seconds: int
    api_enabled: bool
    treatment_plan_sync_enabled: bool
    treatment_plan_sync_approved: bool
    treatment_plan_endpoint_mapping_validated: bool
    active_contract_version: str | None = None
    active_contract_effective_at: datetime | None = None


class AllevaEndpointContract(V2Model):
    path: str = Field(min_length=1, max_length=500)
    parameters: dict[str, str]
    field_mappings: dict[str, str]


class AllevaOAuthContract(V2Model):
    token_auth_style: Literal["body", "basic"]
    scope: str = Field(min_length=1, max_length=500)


class AllevaPaginationContract(V2Model):
    limit_parameter: str = Field(min_length=1, max_length=80)
    offset_parameter: str = Field(min_length=1, max_length=80)
    maximum_page_size: int = Field(ge=1, le=5000)


class AllevaRateLimitContract(V2Model):
    maximum_requests_per_minute: int = Field(ge=1, le=10000)
    retry_after_seconds: int = Field(ge=1, le=300)


class AllevaAttachmentsContract(V2Model):
    mode: Literal["metadata_only", "disabled"]
    download_allowed: Literal[False]


class AllevaContractApprovalIn(V2Model):
    contract_version: str = Field(min_length=1, max_length=120)
    effective_at: datetime
    vendor_documentation_url: str = Field(min_length=1, max_length=500)
    test_population_reference: str = Field(min_length=1, max_length=200)
    oauth: AllevaOAuthContract
    pagination: AllevaPaginationContract
    rate_limit: AllevaRateLimitContract
    attachments: AllevaAttachmentsContract
    endpoints: dict[str, AllevaEndpointContract]


class AllevaContractApprovalOut(V2Model):
    contract_version: str
    contract_sha256: str
    effective_at: datetime
    approved_at: datetime
    active_contract_version: str | None = None
    active_contract_effective_at: datetime | None = None


class AllevaEndpointContract(V2Model):
    path: str = Field(min_length=1, max_length=500)
    parameters: dict[str, str]
    field_mappings: dict[str, str]


class AllevaOAuthContract(V2Model):
    token_auth_style: Literal["body", "basic"]
    scope: str = Field(min_length=1, max_length=500)


class AllevaPaginationContract(V2Model):
    limit_parameter: str = Field(min_length=1, max_length=80)
    offset_parameter: str = Field(min_length=1, max_length=80)
    maximum_page_size: int = Field(ge=1, le=5000)


class AllevaRateLimitContract(V2Model):
    maximum_requests_per_minute: int = Field(ge=1, le=10000)
    retry_after_seconds: int = Field(ge=1, le=300)


class AllevaAttachmentsContract(V2Model):
    mode: Literal["metadata_only", "disabled"]
    download_allowed: Literal[False]


class AllevaContractApprovalIn(V2Model):
    contract_version: str = Field(min_length=1, max_length=120)
    effective_at: datetime
    vendor_documentation_url: str = Field(min_length=1, max_length=500)
    test_population_reference: str = Field(min_length=1, max_length=200)
    oauth: AllevaOAuthContract
    pagination: AllevaPaginationContract
    rate_limit: AllevaRateLimitContract
    attachments: AllevaAttachmentsContract
    endpoints: dict[str, AllevaEndpointContract]


class AllevaContractApprovalOut(V2Model):
    contract_version: str
    contract_sha256: str
    effective_at: datetime
    approved_at: datetime


class AllevaTreatmentPlanSyncOut(V2Model):
    status: Literal["completed"]
    imported_patient_count: int
    skipped_plan_count: int


class ManagerActionInput(V2Model):
    criterion_id: str
    action: Literal["approve", "return_for_correction", "override", "comment"]
    comment: str = ""
    override_reason: str = ""
    assigned_counselor_username: str = ""


class CorrectionSubmissionInput(V2Model):
    work_item_id: int
    criterion_id: str
    comment: str = Field(min_length=1)


class CorrectionQueueItemOut(V2Model):
    work_item_id: int
    plan_version_id: int
    patient_id: str
    patient_display_label: str
    criterion_id: str
    criterion_title: str
    return_comment: str
    returned_by_username: str
    returned_at: str


class CorrectionQueueOut(V2Model):
    items: tuple[CorrectionQueueItemOut, ...]


class ApiHarnessJobStart(V2Model):
    job_type: Literal["pull_all_treatment_plans_all_fields"] = "pull_all_treatment_plans_all_fields"


class SampleOpenApiInfo(V2Model):
    title: str
    version: str


class SampleOpenApiOperation(V2Model):
    operation_id: str = Field(alias="operationId")


class SampleOpenApiPathItem(V2Model):
    get: SampleOpenApiOperation


class SampleOpenApiOut(V2Model):
    openapi: str
    info: SampleOpenApiInfo
    paths: dict[str, SampleOpenApiPathItem]


class PullDefinitionsInput(V2Model):
    swagger_ui_url: str
    openapi_url: str
    api_base_url: str
    use_saved_api_key: bool
    api_key_header_name: str
    client_id: str = "ClientId"
    timeout_seconds: int


class DefinitionSummaryOut(V2Model):
    title: str
    operation_count: int


class PullDefinitionsOut(V2Model):
    status: Literal["ok"]
    definition_summary: DefinitionSummaryOut
    redaction_status: Literal["safe_summary_only"]


class OAuthConnectivityOut(V2Model):
    status: Literal["ok", "failure"]
    token_auth_style: Literal["body", "basic"]
    message: str
    token_type: str = ""
    expires_in: int | None = None


class OperationTestInput(V2Model):
    path: str = Field(min_length=1, max_length=500)


class OperationTestOut(V2Model):
    status: Literal["ok", "failure"]
    message: str
    status_code: int | None = None
    content_type: str = ""
    response_bytes: int = 0
    response_truncated: bool = False


class AuditLogItemOut(V2Model):
    event_id: str
    timestamp_utc: str
    actor_id: str
    actor_username: str
    actor_role: str
    action: str
    target_entity_type: str
    target_entity_id: str
    outcome_status: str
    details: dict[str, str | int | float | bool | None | list[str] | dict[str, str]]
    prev_hash: str
    hash: str


class AuditLogListOut(V2Model):
    items: tuple[AuditLogItemOut, ...]


class AuditVerificationOut(V2Model):
    valid: bool
    event_count: int
    first_invalid_id: int | None = None


class WorkflowProfileCreate(V2Model):
    workflow_key: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    display_name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class WorkflowProfileVersionOut(V2Model):
    id: int
    version: int
    status: Literal["draft", "published", "archived"]
    version_notes: str


class WorkflowProfileOut(V2Model):
    id: int
    workflow_key: str
    display_name: str
    description: str
    is_active: bool
    current_version: WorkflowProfileVersionOut | None
    versions: tuple[WorkflowProfileVersionOut, ...]
