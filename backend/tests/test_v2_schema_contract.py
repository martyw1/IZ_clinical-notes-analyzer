from __future__ import annotations

import sqlite3

import pytest

from app.v2.migrations.runner import MigrationRequest, run_migrations
from v2_migration_fixtures import SYNTHETIC_SECRET, create_legacy_database

EXPECTED_COLUMNS = {
    "schema_migrations": ("version", "name", "checksum_sha256", "applied_at", "app_build"),
    "facilities": ("id", "facility_key", "display_name", "timezone", "is_active", "created_at", "updated_at"),
    "user_facilities": ("user_id", "facility_id", "assigned_by_user_id", "assigned_at"),
    "patients": ("id", "facility_id", "canonical_client_id", "source_system", "lifecycle_state", "first_seen_at", "last_seen_at", "reconciled_at", "source_patient_id"),
    "patient_assignments": ("patient_id", "counselor_user_id", "assigned_by_user_id", "assigned_at", "ended_at", "is_active"),
    "loc_history": ("id", "patient_id", "loc_code", "source_system", "source_record_id", "effective_date", "recorded_at", "reconciliation_state", "evidence_sha256"),
    "treatment_plan_versions": ("id", "patient_id", "source_system", "source_record_id", "version_ordinal", "plan_date", "signature_date", "admission_date", "source_next_review_due", "normalized_snapshot_encrypted", "content_sha256", "evidence_sha256", "imported_at", "supersedes_version_id", "sync_job_id", "approval_record_id", "contract_version", "contract_sha256"),
    "treatment_review_versions": ("id", "patient_id", "source_system", "source_record_id", "version_ordinal", "review_date", "signature_date", "normalized_snapshot_encrypted", "content_sha256", "evidence_sha256", "imported_at", "supersedes_version_id", "sync_job_id", "approval_record_id", "contract_version", "contract_sha256"),
    "diagnosis_snapshots": ("id", "plan_version_id", "review_version_id", "source_record_id", "normalized_snapshot_encrypted", "content_sha256", "captured_at", "sync_job_id", "approval_record_id", "contract_version", "contract_sha256"),
    "source_documents": ("id", "patient_id", "plan_version_id", "review_version_id", "document_id", "source_kind", "source_format", "content_type", "size_bytes", "sha256", "encrypted_relative_path", "created_by_user_id", "created_at"),
    "evaluation_runs": ("id", "plan_version_id", "checklist_version", "rules_version", "evaluation_date", "facility_timezone", "evidence_sha256", "trigger_kind", "run_sequence", "created_at", "sync_job_id", "approval_record_id", "contract_version", "contract_sha256"),
    "criterion_results": ("id", "evaluation_run_id", "criterion_id", "result_status", "normalized_path", "source_record_type", "source_record_version_id", "evaluated_value_safe", "explanation", "evidence_sha256"),
    "manager_dispositions": ("id", "plan_version_id", "criterion_id", "status", "comment", "actor_user_id", "created_at", "supersedes_disposition_id"),
    "correction_work_items": ("id", "plan_version_id", "criterion_id", "disposition_id", "assigned_counselor_user_id", "status", "opened_at", "closed_at", "idempotency_key"),
    "correction_submissions": ("id", "work_item_id", "counselor_user_id", "submission_encrypted", "evidence_sha256", "created_at", "idempotency_key"),
    "alleva_contract_approvals": ("id", "contract_version", "encrypted_contract_json", "contract_sha256", "approver_user_id", "approved_at", "effective_at", "expires_at", "revoked_at"),
    "sync_jobs": ("id", "external_job_id", "requested_by_user_id", "approval_record_id", "status", "idempotency_key", "cancel_requested", "started_at", "completed_at", "counters_json"),
    "sync_checkpoints": ("id", "job_id", "endpoint_key", "page_number", "cursor_hash", "response_shape_sha256", "committed_at", "encrypted_records_json"),
    "sync_failures": ("id", "job_id", "checkpoint_id", "error_class", "safe_message", "retryable", "attempt", "occurred_at"),
    "reconciliation_outcomes": ("id", "job_id", "patient_id", "source_kind", "source_record_id", "outcome", "evidence_sha256", "created_at"),
}

EXPECTED_FOREIGN_KEYS = {
    "user_facilities": {("user_id", "users"), ("facility_id", "facilities"), ("assigned_by_user_id", "users")},
    "patients": {("facility_id", "facilities")},
    "patient_assignments": {("patient_id", "patients"), ("counselor_user_id", "users"), ("assigned_by_user_id", "users")},
    "loc_history": {("patient_id", "patients")},
    "treatment_plan_versions": {("patient_id", "patients"), ("supersedes_version_id", "treatment_plan_versions"), ("sync_job_id", "sync_jobs"), ("approval_record_id", "alleva_contract_approvals")},
    "treatment_review_versions": {("patient_id", "patients"), ("supersedes_version_id", "treatment_review_versions"), ("sync_job_id", "sync_jobs"), ("approval_record_id", "alleva_contract_approvals")},
    "diagnosis_snapshots": {("plan_version_id", "treatment_plan_versions"), ("review_version_id", "treatment_review_versions"), ("sync_job_id", "sync_jobs"), ("approval_record_id", "alleva_contract_approvals")},
    "source_documents": {("patient_id", "patients"), ("plan_version_id", "treatment_plan_versions"), ("review_version_id", "treatment_review_versions"), ("created_by_user_id", "users")},
    "evaluation_runs": {("plan_version_id", "treatment_plan_versions"), ("sync_job_id", "sync_jobs"), ("approval_record_id", "alleva_contract_approvals")},
    "criterion_results": {("evaluation_run_id", "evaluation_runs")},
    "manager_dispositions": {("plan_version_id", "treatment_plan_versions"), ("actor_user_id", "users"), ("supersedes_disposition_id", "manager_dispositions")},
    "correction_work_items": {("plan_version_id", "treatment_plan_versions"), ("disposition_id", "manager_dispositions"), ("assigned_counselor_user_id", "users")},
    "correction_submissions": {("work_item_id", "correction_work_items"), ("counselor_user_id", "users")},
    "alleva_contract_approvals": {("approver_user_id", "users")},
    "sync_jobs": {("requested_by_user_id", "users"), ("approval_record_id", "alleva_contract_approvals")},
    "sync_checkpoints": {("job_id", "sync_jobs")},
    "sync_failures": {("job_id", "sync_jobs"), ("checkpoint_id", "sync_checkpoints")},
    "reconciliation_outcomes": {("job_id", "sync_jobs"), ("patient_id", "patients")},
}

EXPECTED_UNIQUE_KEYS = {
    "schema_migrations": {("name",)},
    "facilities": {("facility_key",)},
    "user_facilities": {("user_id", "facility_id")},
    "patients": {("facility_id", "source_system", "canonical_client_id"), ("facility_id", "source_system", "source_patient_id")},
    "patient_assignments": {("patient_id", "counselor_user_id", "assigned_at"), ("patient_id", "counselor_user_id")},
    "loc_history": {("patient_id", "source_system", "source_record_id", "effective_date", "evidence_sha256")},
    "treatment_plan_versions": {("patient_id", "source_system", "source_record_id", "content_sha256"), ("patient_id", "version_ordinal")},
    "treatment_review_versions": {("patient_id", "source_system", "source_record_id", "content_sha256"), ("patient_id", "version_ordinal")},
    "diagnosis_snapshots": {("plan_version_id", "content_sha256"), ("review_version_id", "content_sha256")},
    "source_documents": {("document_id",), ("patient_id", "sha256", "source_kind")},
    "evaluation_runs": {("plan_version_id", "checklist_version", "rules_version", "evaluation_date", "evidence_sha256", "run_sequence")},
    "criterion_results": {("evaluation_run_id", "criterion_id")},
    "manager_dispositions": {("plan_version_id", "criterion_id", "actor_user_id", "created_at")},
    "correction_work_items": {("idempotency_key",)},
    "correction_submissions": {("idempotency_key",)},
    "alleva_contract_approvals": {("contract_version",)},
    "sync_jobs": {("external_job_id",), ("idempotency_key",)},
    "sync_checkpoints": {("job_id", "endpoint_key", "page_number", "cursor_hash")},
    "reconciliation_outcomes": {("job_id", "patient_id", "source_kind", "source_record_id")},
}


def test_schema_ledger_has_exact_columns_and_foreign_keys(tmp_path) -> None:
    # Given: a synthetic database using the current mutable persistence schema.
    database_path = create_legacy_database(tmp_path)

    # When: the ordered application-owned migration registry is applied.
    run_migrations(MigrationRequest(database_path, tmp_path, SYNTHETIC_SECRET, "test-build"))

    # Then: every clinical ledger table has its exact declared columns and valid foreign keys.
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for table, expected in EXPECTED_COLUMNS.items():
            table_info = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
            actual = tuple(row[1] for row in table_info)
            assert actual == expected
            expected_pk = ("version",) if table == "schema_migrations" else (
                ("user_id", "facility_id") if table == "user_facilities" else (
                    ("patient_id", "counselor_user_id", "assigned_at") if table == "patient_assignments" else ("id",)
                )
            )
            actual_pk = tuple(row[1] for row in sorted(table_info, key=lambda item: item[5]) if row[5])
            assert actual_pk == expected_pk
        for table, expected in EXPECTED_FOREIGN_KEYS.items():
            actual = {(row[3], row[2]) for row in connection.execute(f'PRAGMA foreign_key_list("{table}")')}
            assert actual == expected
        for table, expected in EXPECTED_UNIQUE_KEYS.items():
            actual = {
                tuple(column[2] for column in connection.execute(f'PRAGMA index_info("{index[1]}")'))
                for index in connection.execute(f'PRAGMA index_list("{table}")')
                if index[2]
            }
            assert expected <= actual
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_version_rows_are_immutable_and_uniqueness_is_enforced(tmp_path) -> None:
    # Given: a migrated database containing two immutable treatment-plan versions.
    database_path = create_legacy_database(tmp_path)
    run_migrations(MigrationRequest(database_path, tmp_path, SYNTHETIC_SECRET, "test-build"))

    # When: an existing plan is updated and a duplicate content version is inserted.
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        plan = connection.execute("SELECT * FROM treatment_plan_versions ORDER BY id LIMIT 1").fetchone()
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute("UPDATE treatment_plan_versions SET plan_date='2030-01-01' WHERE id=?", (plan[0],))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO treatment_plan_versions(patient_id,source_system,source_record_id,version_ordinal,normalized_snapshot_encrypted,content_sha256,evidence_sha256,imported_at) VALUES(?,?,?,?,?,?,?,?)",
                (plan[1], plan[2], plan[3], 99, plan[9], plan[10], plan[11], plan[12]),
            )

    # Then: the original immutable row remains unchanged.
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT plan_date FROM treatment_plan_versions WHERE id=?", (plan[0],)).fetchone()[0] != "2030-01-01"


def test_evaluation_and_criterion_ledgers_reject_update_and_delete(tmp_path) -> None:
    # Given
    database_path = create_legacy_database(tmp_path)
    run_migrations(MigrationRequest(database_path, tmp_path, SYNTHETIC_SECRET, "test-build"))
    with sqlite3.connect(database_path) as connection:
        plan_id = connection.execute("SELECT id FROM treatment_plan_versions ORDER BY id LIMIT 1").fetchone()[0]
        connection.execute(
            "INSERT INTO evaluation_runs(plan_version_id,checklist_version,rules_version,evaluation_date,facility_timezone,evidence_sha256,trigger_kind,run_sequence,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (plan_id, "1.2.0", "1.2.0", "2026-07-10", "America/New_York", "e" * 64, "migration", 1, "2026-07-10T00:00:00+00:00"),
        )
        run_id = connection.execute("SELECT id FROM evaluation_runs").fetchone()[0]
        connection.execute(
            "INSERT INTO criterion_results(evaluation_run_id,criterion_id,result_status,normalized_path,source_record_type,source_record_version_id,evaluated_value_safe,explanation,evidence_sha256) VALUES(?,?,?,?,?,?,?,?,?)",
            (run_id, "criterion-1", "Present", "path", "treatment_plan_version", plan_id, "safe", "safe explanation", "c" * 64),
        )
        connection.commit()

        # When/Then
        for statement in (
            "UPDATE evaluation_runs SET trigger_kind='changed'",
            "DELETE FROM evaluation_runs",
            "UPDATE criterion_results SET result_status='changed'",
            "DELETE FROM criterion_results",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(statement)


def test_boolean_role_and_diagnosis_checks_reject_invalid_states(tmp_path) -> None:
    # Given: a migrated database with the canonical user and clinical schema.
    database_path = create_legacy_database(tmp_path)
    run_migrations(MigrationRequest(database_path, tmp_path, SYNTHETIC_SECRET, "test-build"))

    # When/Then: invalid booleans, roles, and dual-version diagnosis linkage are rejected.
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE facilities SET is_active=2")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE users SET role='manager'")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE users SET recovery_required=2")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE app_settings SET emr_api_enabled=2")
        plan_id = connection.execute("SELECT id FROM treatment_plan_versions LIMIT 1").fetchone()[0]
        review_id = connection.execute("SELECT id FROM treatment_review_versions LIMIT 1").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO diagnosis_snapshots(plan_version_id,review_version_id,source_record_id,normalized_snapshot_encrypted,content_sha256,captured_at) VALUES(?,?,?,?,?,?)",
                (plan_id, review_id, "diagnosis-1", b"encrypted", "e" * 64, "2026-07-10T00:00:00+00:00"),
            )
        actor_id = connection.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()[0]
        connection.execute(
            "INSERT INTO manager_dispositions(plan_version_id,criterion_id,status,actor_user_id,created_at) VALUES(?,?,?,?,?)",
            (plan_id, "criterion-immutable", "review", actor_id, "2026-07-10T00:00:00+00:00"),
        )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute("UPDATE manager_dispositions SET status='changed'")
