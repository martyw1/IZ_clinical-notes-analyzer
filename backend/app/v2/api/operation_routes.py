from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.v2.api.deps import AdminUser, DbSession
from app.v2.api.models import OperationTestInput, OperationTestOut
from app.v2.models import AppSetting
from app.v2.services.audit_store import record_audit_event
from app.v2.services.operation_test import test_read_only_operation
from app.v2.services.secure_storage import decrypt_api_client_id, decrypt_text_secret

router = APIRouter()


@router.post("/api/api-configuration/test-operation", response_model=OperationTestOut)
def test_operation(payload: OperationTestInput, actor: AdminUser, db: DbSession) -> OperationTestOut:
    profile = db.execute(select(AppSetting)).scalar_one()
    if not profile.emr_api_enabled:
        raise HTTPException(status_code=409, detail="Enable API testing before running a saved-profile operation.")
    result = test_read_only_operation(
        api_base_url=profile.api_base_url, path=payload.path, token_url=profile.api_oauth_token_url,
        client_id=decrypt_api_client_id(profile.api_client_id),
        client_secret=decrypt_text_secret(profile.api_client_secret),
        scope=profile.api_scopes, token_auth_style=profile.api_token_auth_style,
        timeout_seconds=profile.emr_api_timeout_seconds,
    )
    record_audit_event(
        db, action="api.operation.read_only.tested", actor=actor, target_entity_type="api_operation",
        target_entity_id=f"GET {payload.path}", outcome_status=result.status,
        details={"path": payload.path, "status_code": result.status_code, "response_bytes": result.response_bytes, "response_truncated": result.response_truncated},
    )
    return OperationTestOut(
        status=result.status, message=result.message, status_code=result.status_code,
        content_type=result.content_type, response_bytes=result.response_bytes, response_truncated=result.response_truncated,
    )
