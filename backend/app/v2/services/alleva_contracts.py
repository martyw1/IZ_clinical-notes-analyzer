from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final

from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.v2.api.models import AllevaContractApprovalIn
from app.v2.services.secure_storage import decrypt_bytes, encrypt_bytes

REQUIRED_ENDPOINTS: Final = frozenset(("clients", "treatment_plans", "treatment_plan_detail", "diagnoses", "reviews", "review_detail"))


@dataclass(frozen=True, slots=True)
class ApprovedAllevaContract:
    approval_id: int
    contract_version: str
    contract_sha256: str
    effective_at: datetime
    approved_at: datetime
    payload: AllevaContractApprovalIn


def approve_contract(db: Session, payload: AllevaContractApprovalIn, approver_user_id: int) -> ApprovedAllevaContract:
    _validate_contract(payload)
    canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    now = datetime.now(timezone.utc)
    statement = (
        "INSERT INTO alleva_contract_approvals("
        "contract_version,encrypted_contract_json,contract_sha256,approver_user_id,approved_at,effective_at"
        ") VALUES(:version,:encrypted,:sha256,:approver,:approved_at,:effective_at)"
    )
    result = db.execute(text(statement), {"version": payload.contract_version, "encrypted": encrypt_bytes(canonical), "sha256": digest, "approver": approver_user_id, "approved_at": now.isoformat(), "effective_at": payload.effective_at.astimezone(timezone.utc).isoformat()})
    db.commit()
    return ApprovedAllevaContract(int(result.lastrowid), payload.contract_version, digest, payload.effective_at, now, payload)


def active_contract(db: Session) -> ApprovedAllevaContract | None:
    statement = (
        "SELECT id,contract_version,encrypted_contract_json,contract_sha256,approved_at,effective_at "
        "FROM alleva_contract_approvals WHERE revoked_at IS NULL "
        "AND (expires_at IS NULL OR expires_at > :now) AND effective_at <= :now "
        "ORDER BY effective_at DESC, id DESC LIMIT 1"
    )
    row = db.execute(text(statement), {"now": datetime.now(timezone.utc).isoformat()}).mappings().one_or_none()
    if row is None or not isinstance(row["encrypted_contract_json"], bytes):
        return None
    try:
        canonical = decrypt_bytes(row["encrypted_contract_json"])
        if hashlib.sha256(canonical).hexdigest() != row["contract_sha256"]:
            return None
        payload = AllevaContractApprovalIn.model_validate_json(canonical)
        _validate_contract(payload)
    except (HTTPException, ValueError, json.JSONDecodeError):
        return None
    return ApprovedAllevaContract(int(row["id"]), str(row["contract_version"]), str(row["contract_sha256"]), datetime.fromisoformat(str(row["effective_at"])), datetime.fromisoformat(str(row["approved_at"])), payload)


def create_sync_ledger(db: Session, external_job_id: str, actor_id: int, contract: ApprovedAllevaContract, started_at: str) -> None:
    counters = json.dumps({"contract_version": contract.contract_version, "contract_sha256": contract.contract_sha256}, sort_keys=True)
    db.execute(
        text("INSERT INTO sync_jobs(external_job_id,requested_by_user_id,approval_record_id,status,idempotency_key,cancel_requested,started_at,counters_json) VALUES(:job_id,:actor_id,:approval_id,'queued',:job_id,0,:started_at,:counters)"),
        {"job_id": external_job_id, "actor_id": actor_id, "approval_id": contract.approval_id, "started_at": started_at, "counters": counters},
    )
    db.commit()


def update_sync_ledger(db: Session, external_job_id: str, status: str, completed_at: str | None, counters: str) -> None:
    db.execute(text("UPDATE sync_jobs SET status=:status,completed_at=:completed_at,counters_json=:counters WHERE external_job_id=:job_id"), {"job_id": external_job_id, "status": status, "completed_at": completed_at, "counters": counters})
    db.commit()


def _validate_contract(payload: AllevaContractApprovalIn) -> None:
    if set(payload.endpoints) != REQUIRED_ENDPOINTS:
        raise ValueError("The approval record must map exactly the six required Alleva endpoints.")
    for endpoint in payload.endpoints.values():
        if not endpoint.path.startswith("/") or not endpoint.field_mappings:
            raise ValueError("Every approved endpoint requires an absolute path and field mapping.")
    if "{plan_id}" not in payload.endpoints["treatment_plan_detail"].path:
        raise ValueError("Treatment-plan detail path must contain {plan_id}.")
    if "{plan_id}" not in payload.endpoints["diagnoses"].path or "{plan_id}" not in payload.endpoints["reviews"].path:
        raise ValueError("Diagnosis and review paths must contain {plan_id}.")
    if "{plan_id}" not in payload.endpoints["review_detail"].path or "{review_id}" not in payload.endpoints["review_detail"].path:
        raise ValueError("Review detail path must contain {plan_id} and {review_id}.")
