from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.v2.migrations.backfill_types import BackfillError, encrypt_bytes, iso_text, user_id
from app.v2.migrations.backfill_versions import VersionBackfill, backfill_import


@dataclass(frozen=True, slots=True)
class RelationBackfill:
    connection: sqlite3.Connection
    encryption_secret: str
    local_app_data_dir: Path
    admin_id: int
    facility_id: int
    plan_versions_by_patient: dict[int, list[tuple[int, str]]]
    now: str


def backfill_legacy_tables(connection: sqlite3.Connection, encryption_secret: str, local_app_data_dir: Path) -> None:
    now = "2026-07-10T00:00:00+00:00"
    settings = connection.execute(
        "SELECT organization_name,facility_timezone FROM app_settings ORDER BY id LIMIT 1"
    ).fetchone()
    display_name = str(settings[0]) if settings else "R3 Recovery Services"
    timezone = str(settings[1]) if settings else "local_machine"
    connection.execute(
        "INSERT OR IGNORE INTO facilities(facility_key,display_name,timezone,is_active,created_at,updated_at) VALUES(?,?,?,?,?,?)",
        ("r3-default", display_name, timezone, 1, now, now),
    )
    facility_id = int(connection.execute("SELECT id FROM facilities WHERE facility_key='r3-default'").fetchone()[0])
    connection.execute("UPDATE users SET role='office_manager' WHERE role='manager'")
    admin = connection.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
    if admin is None:
        raise BackfillError("canonical administrator is missing")
    admin_id = int(admin[0])
    connection.execute(
        """INSERT OR IGNORE INTO user_facilities(user_id,facility_id,assigned_by_user_id,assigned_at)
        SELECT id,?,?,? FROM users WHERE role IN ('admin','office_manager')""",
        (facility_id, admin_id, now),
    )
    plan_versions_by_patient: dict[int, list[tuple[int, str]]] = {}
    legacy_imports = connection.execute(
        "SELECT id,patient_id,plan_id,source_mode,admission_date,next_due_date,encrypted_payload,created_at FROM treatment_plan_imports ORDER BY patient_id,created_at,id"
    ).fetchall()
    version_context = VersionBackfill(connection, facility_id, encryption_secret, plan_versions_by_patient)
    for legacy in legacy_imports:
        backfill_import(version_context, legacy)
    relations = RelationBackfill(connection, encryption_secret, local_app_data_dir, admin_id, facility_id, plan_versions_by_patient, now)
    _backfill_documents(relations)
    _backfill_manager_actions(relations)
    connection.execute(
        "UPDATE treatment_plan_imports SET patient_display_label='Patient ID ' || patient_id"
    )


def _backfill_documents(context: RelationBackfill) -> None:
    rows = context.connection.execute(
        "SELECT patient_id,plan_id,document_id,source_kind,source_format,content_type,size_bytes,sha256,storage_path,created_by_user_id,created_at FROM uploaded_documents ORDER BY id"
    ).fetchall()
    root = context.local_app_data_dir.resolve()
    for row in rows:
        patient = context.connection.execute("SELECT id FROM patients WHERE canonical_client_id=?", (str(row[0]),)).fetchone()
        if patient is None:
            continue
        patient_id = int(patient[0])
        relative_path = Path(str(row[8]))
        resolved = (root / relative_path).resolve()
        if relative_path.is_absolute() or not resolved.is_relative_to(root):
            continue
        matches = [version_id for version_id, record_id in context.plan_versions_by_patient.get(patient_id, ()) if record_id == str(row[1])]
        plan_version_id = matches[0] if len(matches) == 1 else None
        actor_id = user_id(context.connection, row[9], context.admin_id)
        context.connection.execute(
            """INSERT OR IGNORE INTO source_documents(
                patient_id,plan_version_id,review_version_id,document_id,source_kind,source_format,content_type,
                size_bytes,sha256,encrypted_relative_path,created_by_user_id,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (patient_id, plan_version_id, None, *row[2:9], actor_id, iso_text(row[10])),
        )


def _backfill_manager_actions(context: RelationBackfill) -> None:
    rows = context.connection.execute(
        "SELECT id,patient_id,criterion_id,action,comment,actor_user_id,created_at FROM treatment_plan_manager_actions ORDER BY id"
    ).fetchall()
    for row in rows:
        patient = context.connection.execute("SELECT id FROM patients WHERE canonical_client_id=?", (str(row[1]),)).fetchone()
        if patient is None:
            context.connection.execute(
                """INSERT OR IGNORE INTO patients(
                    facility_id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at,reconciled_at
                ) VALUES(?,?,'legacy_unmatched_action','needs_review',?,?,?)""",
                (context.facility_id, str(row[1]), context.now, context.now, context.now),
            )
            patient = context.connection.execute(
                "SELECT id FROM patients WHERE facility_id=? AND source_system='legacy_unmatched_action' AND canonical_client_id=?",
                (context.facility_id, str(row[1])),
            ).fetchone()
        patient_id = int(patient[0])
        versions = context.plan_versions_by_patient.get(patient_id, ())
        actor_id = user_id(context.connection, row[5], context.admin_id)
        if len(versions) == 1:
            context.connection.execute(
                "INSERT OR IGNORE INTO manager_dispositions(plan_version_id,criterion_id,status,comment,actor_user_id,created_at) VALUES(?,?,?,?,?,?)",
                (versions[0][0], str(row[2]), str(row[3]), str(row[4] or ""), actor_id, iso_text(row[6])),
            )
            continue
        job_id = _migration_job(context)
        evidence = hashlib.sha256(f"manager-action:{row[0]}".encode("utf-8")).hexdigest()
        context.connection.execute(
            "INSERT OR IGNORE INTO reconciliation_outcomes(job_id,patient_id,source_kind,source_record_id,outcome,evidence_sha256,created_at) VALUES(?,?,?,?,?,?,?)",
            (job_id, patient_id, "legacy_manager_action", f"legacy-action-{row[0]}", "needs_review", evidence, context.now),
        )


def _migration_job(context: RelationBackfill) -> int:
    approval = context.connection.execute("SELECT id FROM alleva_contract_approvals WHERE contract_version='legacy-migration-v1'").fetchone()
    if approval is None:
        safe_contract = b'{"kind":"internal-legacy-migration"}'
        context.connection.execute(
            "INSERT INTO alleva_contract_approvals(contract_version,encrypted_contract_json,contract_sha256,approver_user_id,approved_at,effective_at) VALUES(?,?,?,?,?,?)",
            ("legacy-migration-v1", encrypt_bytes(safe_contract, context.encryption_secret), hashlib.sha256(safe_contract).hexdigest(), context.admin_id, context.now, context.now),
        )
        approval = context.connection.execute("SELECT id FROM alleva_contract_approvals WHERE contract_version='legacy-migration-v1'").fetchone()
    context.connection.execute(
        "INSERT OR IGNORE INTO sync_jobs(external_job_id,requested_by_user_id,approval_record_id,status,idempotency_key,cancel_requested,started_at,completed_at,counters_json) VALUES(?,?,?,?,?,?,?,?,?)",
        ("legacy-migration", context.admin_id, int(approval[0]), "historical_migration", "legacy-migration-v1", 0, context.now, context.now, "{}"),
    )
    return int(context.connection.execute("SELECT id FROM sync_jobs WHERE idempotency_key='legacy-migration-v1'").fetchone()[0])
