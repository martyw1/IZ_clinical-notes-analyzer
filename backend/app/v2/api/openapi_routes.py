from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.v2.api.deps import AdminUser, DbSession
from app.v2.api.models import (
    DefinitionSummaryOut,
    PullDefinitionsOut,
    OAuthConnectivityOut,
    SampleOpenApiInfo,
    SampleOpenApiOperation,
    SampleOpenApiOut,
    SampleOpenApiPathItem,
)
from app.v2.models import AppSetting
from app.v2.services.audit_store import record_audit_event
from app.v2.services.openapi_definition_loader import OpenApiDefinitionError, load_openapi_definition
from app.v2.services.oauth_connectivity import test_client_credentials
from app.v2.services.secure_storage import decrypt_text_secret

router = APIRouter()


@router.get("/api/api-configuration/sample-openapi.json")
def sample_openapi() -> SampleOpenApiOut:
    return SampleOpenApiOut(
        openapi="3.1.0", info=SampleOpenApiInfo(title="Connectivity Test Definition", version="2.0.0-beta.2"),
        paths={"/clients": SampleOpenApiPathItem(get=SampleOpenApiOperation(operation_id="listClients"))},
    )


@router.post("/api/api-configuration/pull-definitions")
def pull_definitions(actor: AdminUser, db: DbSession) -> PullDefinitionsOut:
    profile = db.execute(select(AppSetting)).scalar_one()
    try:
        summary = load_openapi_definition(profile.openapi_url, profile.emr_api_timeout_seconds)
    except OpenApiDefinitionError as exc:
        record_audit_event(
            db, action="api.openapi.definition.pull.failed", actor=actor, target_entity_type="api_connection_profile",
            target_entity_id=profile.emr_vendor_name, outcome_status="failure", details={"reason": str(exc)},
        )
        raise HTTPException(status_code=502, detail="Unable to retrieve a valid OpenAPI definition from the saved profile") from exc
    record_audit_event(
        db, action="api.openapi.definition.pulled", actor=actor, target_entity_type="api_connection_profile",
        target_entity_id=profile.emr_vendor_name, details={"operation_count": summary.operation_count},
    )
    return PullDefinitionsOut(
        status="ok", definition_summary=DefinitionSummaryOut(title=summary.title, operation_count=summary.operation_count),
        redaction_status="safe_summary_only",
    )


@router.post("/api/api-configuration/test-connectivity", response_model=OAuthConnectivityOut)
def test_connectivity(actor: AdminUser, db: DbSession) -> OAuthConnectivityOut:
    profile = db.execute(select(AppSetting)).scalar_one()
    result = test_client_credentials(
        token_url=profile.api_oauth_token_url, client_id=profile.api_client_id,
        client_secret=decrypt_text_secret(profile.api_client_secret), scope=profile.api_scopes,
        token_auth_style=profile.api_token_auth_style, timeout_seconds=profile.emr_api_timeout_seconds,
    )
    record_audit_event(
        db, action="api.oauth.connectivity.tested", actor=actor, target_entity_type="api_connection_profile",
        target_entity_id=profile.emr_vendor_name, outcome_status=result.status,
        details={"token_auth_style": result.token_auth_style, "credentials_verified": result.status == "ok"},
    )
    return OAuthConnectivityOut(
        status=result.status, token_auth_style=result.token_auth_style, message=result.message,
        token_type=result.token_type, expires_in=result.expires_in,
    )
