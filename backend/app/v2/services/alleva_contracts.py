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


@dataclass(frozen=True, slots=True)
class SyncCheckpointPage:
    endpoint_key: str
    page_number: int
    cursor_hash: str
    response_shape_sha256: str
    records: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class SyncImportProvenance:
    sync_job_id: int
    approval_record_id: int
    contract_version: str
    contract_sha256: str


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


def contract_bound_to_sync_job(db: Session, external_job_id: str) -> ApprovedAllevaContract | None:
    row = db.execute(
        text(
            "SELECT approval.id,approval.contract_version,approval.encrypted_contract_json,approval.contract_sha256,"
            "approval.approved_at,approval.effective_at FROM sync_jobs "
            "JOIN alleva_contract_approvals AS approval ON approval.id=sync_jobs.approval_record_id "
            "WHERE sync_jobs.external_job_id=:job_id"
        ),
        {"job_id": external_job_id},
    ).mappings().one_or_none()
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
    return ApprovedAllevaContract(
        int(row["id"]),
        str(row["contract_version"]),
        str(row["contract_sha256"]),
        datetime.fromisoformat(str(row["effective_at"])),
        datetime.fromisoformat(str(row["approved_at"])),
        payload,
    )


def create_sync_ledger(
    db: Session,
    external_job_id: str,
    actor_id: int,
    contract: ApprovedAllevaContract,
    started_at: str,
    resumed_from_job_id: str | None = None,
) -> None:
    counter_values: dict[str, object] = {
        "contract_version": contract.contract_version,
        "contract_sha256": contract.contract_sha256,
    }
    if resumed_from_job_id:
        counter_values["resumed_from_job_id"] = resumed_from_job_id
    counters = json.dumps(counter_values, sort_keys=True)
    db.execute(
        text("INSERT INTO sync_jobs(external_job_id,requested_by_user_id,approval_record_id,status,idempotency_key,cancel_requested,started_at,counters_json) VALUES(:job_id,:actor_id,:approval_id,'queued',:job_id,0,:started_at,:counters)"),
        {"job_id": external_job_id, "actor_id": actor_id, "approval_id": contract.approval_id, "started_at": started_at, "counters": counters},
    )
    db.commit()


def sync_import_provenance(db: Session, external_job_id: str) -> SyncImportProvenance:
    row = db.execute(
        text(
            "SELECT sync_jobs.id,sync_jobs.approval_record_id,approval.contract_version,approval.contract_sha256 "
            "FROM sync_jobs JOIN alleva_contract_approvals AS approval ON approval.id=sync_jobs.approval_record_id "
            "WHERE sync_jobs.external_job_id=:job_id"
        ),
        {"job_id": external_job_id},
    ).mappings().one()
    return SyncImportProvenance(
        int(row["id"]),
        int(row["approval_record_id"]),
        str(row["contract_version"]),
        str(row["contract_sha256"]),
    )


def update_sync_ledger(db: Session, external_job_id: str, status: str, completed_at: str | None, counters: str) -> None:
    row = db.execute(
        text("SELECT counters_json FROM sync_jobs WHERE external_job_id=:job_id"),
        {"job_id": external_job_id},
    ).scalar_one_or_none()
    persisted = _counter_values(row)
    persisted.update(_counter_values(counters))
    db.execute(
        text("UPDATE sync_jobs SET status=:status,completed_at=:completed_at,counters_json=:counters WHERE external_job_id=:job_id"),
        {
            "job_id": external_job_id,
            "status": status,
            "completed_at": completed_at,
            "counters": json.dumps(persisted, sort_keys=True),
        },
    )
    db.commit()


def record_sync_checkpoint(
    db: Session,
    external_job_id: str,
    endpoint_key: str,
    page_number: int,
    cursor_hash: str,
    response_shape_sha256: str,
    records: tuple[dict[str, object], ...],
    committed_at: str,
) -> None:
    encrypted_records = encrypt_bytes(json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    db.execute(
        text(
            "INSERT INTO sync_checkpoints(job_id,endpoint_key,page_number,cursor_hash,response_shape_sha256,"
            "encrypted_records_json,committed_at) SELECT id,:endpoint_key,:page_number,:cursor_hash,"
            ":response_shape_sha256,:encrypted_records,:committed_at FROM sync_jobs WHERE external_job_id=:job_id "
            "ON CONFLICT(job_id,endpoint_key,page_number,cursor_hash) DO UPDATE SET "
            "response_shape_sha256=excluded.response_shape_sha256,encrypted_records_json=excluded.encrypted_records_json,"
            "committed_at=excluded.committed_at"
        ),
        {"job_id": external_job_id, "endpoint_key": endpoint_key, "page_number": page_number, "cursor_hash": cursor_hash, "response_shape_sha256": response_shape_sha256, "encrypted_records": encrypted_records, "committed_at": committed_at},
    )
    db.commit()


def load_sync_checkpoint_pages(db: Session, external_job_id: str, endpoint_key: str) -> tuple[SyncCheckpointPage, ...]:
    rows = db.execute(
        text(
            "SELECT endpoint_key,page_number,cursor_hash,response_shape_sha256,encrypted_records_json "
            "FROM sync_checkpoints JOIN sync_jobs ON sync_checkpoints.job_id=sync_jobs.id "
            "WHERE sync_jobs.external_job_id=:job_id AND sync_checkpoints.endpoint_key=:endpoint_key "
            "ORDER BY sync_checkpoints.page_number,sync_checkpoints.id"
        ),
        {"job_id": external_job_id, "endpoint_key": endpoint_key},
    ).mappings()
    pages: list[SyncCheckpointPage] = []
    for row in rows:
        encrypted_records = row["encrypted_records_json"]
        if not isinstance(encrypted_records, bytes):
            raise ValueError("Sync checkpoint is missing encrypted records required for resume.")
        decoded = json.loads(decrypt_bytes(encrypted_records))
        if not isinstance(decoded, list) or not all(isinstance(record, dict) for record in decoded):
            raise ValueError("Sync checkpoint records are invalid.")
        pages.append(
            SyncCheckpointPage(
                str(row["endpoint_key"]),
                int(row["page_number"]),
                str(row["cursor_hash"]),
                str(row["response_shape_sha256"]),
                tuple(record for record in decoded if isinstance(record, dict)),
            )
        )
    return tuple(pages)


def copy_sync_checkpoints(db: Session, source_job_id: str, destination_job_id: str) -> None:
    db.execute(
        text(
            "INSERT OR IGNORE INTO sync_checkpoints(job_id,endpoint_key,page_number,cursor_hash,response_shape_sha256,"
            "encrypted_records_json,committed_at) SELECT destination.id,checkpoint.endpoint_key,checkpoint.page_number,"
            "checkpoint.cursor_hash,checkpoint.response_shape_sha256,checkpoint.encrypted_records_json,checkpoint.committed_at "
            "FROM sync_checkpoints AS checkpoint JOIN sync_jobs AS source ON source.id=checkpoint.job_id "
            "JOIN sync_jobs AS destination ON destination.external_job_id=:destination_job_id "
            "WHERE source.external_job_id=:source_job_id"
        ),
        {"source_job_id": source_job_id, "destination_job_id": destination_job_id},
    )
    db.commit()


def record_sync_failure(
    db: Session,
    external_job_id: str,
    error_class: str,
    safe_message: str,
    retryable: bool,
    attempt: int,
    occurred_at: str,
) -> None:
    db.execute(
        text(
            "INSERT INTO sync_failures(job_id,checkpoint_id,error_class,safe_message,retryable,attempt,occurred_at) "
            "SELECT id,NULL,:error_class,:safe_message,:retryable,:attempt,:occurred_at "
            "FROM sync_jobs WHERE external_job_id=:job_id"
        ),
        {
            "job_id": external_job_id,
            "error_class": error_class,
            "safe_message": safe_message,
            "retryable": int(retryable),
            "attempt": attempt,
            "occurred_at": occurred_at,
        },
    )
    db.commit()


def set_sync_cancellation_requested(db: Session, external_job_id: str) -> None:
    db.execute(
        text("UPDATE sync_jobs SET cancel_requested=1 WHERE external_job_id=:job_id"),
        {"job_id": external_job_id},
    )
    db.commit()


def reconcile_sync_patients(
    db: Session,
    external_job_id: str,
    observed_lifecycles: dict[str, str],
    completed_snapshot: bool,
    reconciled_at: str,
) -> None:
    facility_id = int(db.execute(text("SELECT id FROM facilities WHERE facility_key='r3-default'")).scalar_one())
    existing = {
        str(row["canonical_client_id"]): int(row["id"])
        for row in db.execute(
            text(
                "SELECT id,canonical_client_id FROM patients "
                "WHERE facility_id=:facility_id AND source_system='alleva_rest_api'"
            ),
            {"facility_id": facility_id},
        ).mappings()
    }
    for client_id, lifecycle_state in observed_lifecycles.items():
        db.execute(
            text(
                "INSERT OR IGNORE INTO patients("
                "facility_id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at,reconciled_at"
                ") VALUES(:facility_id,:client_id,'alleva_rest_api',:lifecycle_state,:reconciled_at,:reconciled_at,:reconciled_at)"
            ),
            {
                "facility_id": facility_id,
                "client_id": client_id,
                "lifecycle_state": lifecycle_state,
                "reconciled_at": reconciled_at,
            },
        )
        patient_id = int(
            db.execute(
                text(
                    "SELECT id FROM patients WHERE facility_id=:facility_id "
                    "AND source_system='alleva_rest_api' AND canonical_client_id=:client_id"
                ),
                {"facility_id": facility_id, "client_id": client_id},
            ).scalar_one()
        )
        db.execute(
            text(
                "UPDATE patients SET lifecycle_state=:lifecycle_state,last_seen_at=:reconciled_at,reconciled_at=:reconciled_at "
                "WHERE id=:patient_id"
            ),
            {"patient_id": patient_id, "lifecycle_state": lifecycle_state, "reconciled_at": reconciled_at},
        )
        _insert_reconciliation_outcome(db, external_job_id, patient_id, client_id, lifecycle_state, reconciled_at)
        existing.pop(client_id, None)
    if completed_snapshot:
        for client_id, patient_id in existing.items():
            db.execute(
                text("UPDATE patients SET lifecycle_state='missing',reconciled_at=:reconciled_at WHERE id=:patient_id"),
                {"patient_id": patient_id, "reconciled_at": reconciled_at},
            )
            _insert_reconciliation_outcome(db, external_job_id, patient_id, client_id, "missing", reconciled_at)
    db.commit()


def _insert_reconciliation_outcome(
    db: Session,
    external_job_id: str,
    patient_id: int,
    client_id: str,
    outcome: str,
    created_at: str,
) -> None:
    evidence_sha256 = hashlib.sha256(f"{external_job_id}:{client_id}:{outcome}".encode("utf-8")).hexdigest()
    db.execute(
        text(
            "INSERT OR IGNORE INTO reconciliation_outcomes("
            "job_id,patient_id,source_kind,source_record_id,outcome,evidence_sha256,created_at"
            ") SELECT id,:patient_id,'alleva_client',:client_id,:outcome,:evidence_sha256,:created_at "
            "FROM sync_jobs WHERE external_job_id=:job_id"
        ),
        {
            "job_id": external_job_id,
            "patient_id": patient_id,
            "client_id": client_id,
            "outcome": outcome,
            "evidence_sha256": evidence_sha256,
            "created_at": created_at,
        },
    )


def _counter_values(raw: str | None) -> dict[str, object]:
    if not raw:
        return {}
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return values if isinstance(values, dict) else {}


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
