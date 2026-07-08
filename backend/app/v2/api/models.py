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


class ApiConfigurationUpdate(V2Model):
    vendor_name: str = "Alleva REST API"
    api_base_url: str = "https://api.allevasoft.com"
    api_key: str | None = None
    timeout_seconds: int = 10
    api_enabled: bool = False


class ApiConfigurationOut(V2Model):
    vendor_name: str
    api_base_url: str
    api_key_configured: bool
    client_secret_configured: bool = False
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
