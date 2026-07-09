from __future__ import annotations

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


class ManagerActionInput(V2Model):
    criterion_id: str
    action: Literal["approve", "return_for_correction", "override", "comment"]
    comment: str = ""
    override_reason: str = ""


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
    request_keys: tuple[str, ...]


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
