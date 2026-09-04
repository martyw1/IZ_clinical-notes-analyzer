from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Final

from app.v2.migrations.errors import MigrationStateError


ORIGINAL_PAIR_CATEGORY: Final = "source_document_original_pairs"
ELIGIBLE_ORIGINALS: Final = (
    "SELECT d.id,d.plan_version_id FROM source_documents d "
    "JOIN treatment_plan_versions v ON v.id=d.plan_version_id JOIN patients p ON p.id=d.patient_id "
    "WHERE d.patient_id=v.patient_id AND d.source_kind='manual_treatment_plan_file' "
    "AND v.source_system='manual_upload' AND p.source_system='manual_upload'"
)


def record_source_membership_reconciliation(connection: sqlite3.Connection) -> None:
    count = int(connection.execute(f"SELECT COUNT(*) FROM ({ELIGIBLE_ORIGINALS})").fetchone()[0])
    count_hash = hashlib.sha256(f"{ORIGINAL_PAIR_CATEGORY}:{count}".encode()).hexdigest()
    connection.execute(
        "INSERT INTO migration_reconciliation(migration_version,category,source_count,target_count,"
        "source_sha256,target_sha256,verified_at) VALUES(12,?,?,?,?,?,?)",
        (ORIGINAL_PAIR_CATEGORY, count, count, count_hash, count_hash, datetime.now(timezone.utc).isoformat()),
    )


def verify_source_memberships(connection: sqlite3.Connection) -> None:
    reconciliation = connection.execute(
        "SELECT source_count,target_count FROM migration_reconciliation WHERE migration_version=12 AND category=?",
        (ORIGINAL_PAIR_CATEGORY,),
    ).fetchone()
    if reconciliation is None or reconciliation[0] != reconciliation[1]:
        raise MigrationStateError("original source-pair reconciliation is missing or unequal")
    missing = connection.execute(
        f"SELECT 1 FROM ({ELIGIBLE_ORIGINALS}) original LEFT JOIN source_document_plan_memberships m "
        "ON m.source_document_id=original.id AND m.plan_version_id=original.plan_version_id "
        "WHERE m.source_document_id IS NULL LIMIT 1"
    ).fetchone()
    if missing is not None:
        raise MigrationStateError("original source membership is missing")
    invalid = connection.execute(
        "SELECT 1 FROM source_document_plan_memberships m JOIN source_documents d ON d.id=m.source_document_id "
        "JOIN treatment_plan_versions v ON v.id=m.plan_version_id JOIN patients p ON p.id=d.patient_id "
        "WHERE d.patient_id<>v.patient_id OR d.source_kind<>'manual_treatment_plan_file' "
        "OR v.source_system<>'manual_upload' OR p.source_system<>'manual_upload' "
        "OR (m.detached_at IS NULL)<>(m.detached_by_user_id IS NULL) LIMIT 1"
    ).fetchone()
    if invalid is not None:
        raise MigrationStateError("source membership row or source identity is inconsistent")
