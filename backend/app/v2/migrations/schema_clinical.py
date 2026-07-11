from __future__ import annotations

CLINICAL_STATEMENTS = (
    """CREATE TABLE treatment_plan_versions(
        id INTEGER PRIMARY KEY,
        patient_id INTEGER NOT NULL REFERENCES patients(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        source_system TEXT NOT NULL,
        source_record_id TEXT NOT NULL,
        version_ordinal INTEGER NOT NULL CHECK(version_ordinal > 0),
        plan_date TEXT NULL,
        signature_date TEXT NULL,
        admission_date TEXT NULL,
        source_next_review_due TEXT NULL,
        normalized_snapshot_encrypted BLOB NOT NULL,
        content_sha256 TEXT NOT NULL,
        evidence_sha256 TEXT NOT NULL,
        imported_at TEXT NOT NULL,
        supersedes_version_id INTEGER NULL REFERENCES treatment_plan_versions(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        UNIQUE(patient_id,source_system,source_record_id,content_sha256),
        UNIQUE(patient_id,version_ordinal)
    )""",
    """CREATE TABLE treatment_review_versions(
        id INTEGER PRIMARY KEY,
        patient_id INTEGER NOT NULL REFERENCES patients(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        source_system TEXT NOT NULL,
        source_record_id TEXT NOT NULL,
        version_ordinal INTEGER NOT NULL CHECK(version_ordinal > 0),
        review_date TEXT NULL,
        signature_date TEXT NULL,
        normalized_snapshot_encrypted BLOB NOT NULL,
        content_sha256 TEXT NOT NULL,
        evidence_sha256 TEXT NOT NULL,
        imported_at TEXT NOT NULL,
        supersedes_version_id INTEGER NULL REFERENCES treatment_review_versions(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        UNIQUE(patient_id,source_system,source_record_id,content_sha256),
        UNIQUE(patient_id,version_ordinal)
    )""",
    """CREATE TABLE diagnosis_snapshots(
        id INTEGER PRIMARY KEY,
        plan_version_id INTEGER NULL REFERENCES treatment_plan_versions(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        review_version_id INTEGER NULL REFERENCES treatment_review_versions(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        source_record_id TEXT NOT NULL,
        normalized_snapshot_encrypted BLOB NOT NULL,
        content_sha256 TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        CHECK((plan_version_id IS NOT NULL) != (review_version_id IS NOT NULL))
    )""",
    "CREATE UNIQUE INDEX uq_diagnosis_plan_hash ON diagnosis_snapshots(plan_version_id,content_sha256) WHERE plan_version_id IS NOT NULL",
    "CREATE UNIQUE INDEX uq_diagnosis_review_hash ON diagnosis_snapshots(review_version_id,content_sha256) WHERE review_version_id IS NOT NULL",
    """CREATE TABLE source_documents(
        id INTEGER PRIMARY KEY,
        patient_id INTEGER NOT NULL REFERENCES patients(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        plan_version_id INTEGER NULL REFERENCES treatment_plan_versions(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        review_version_id INTEGER NULL REFERENCES treatment_review_versions(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        document_id TEXT NOT NULL UNIQUE,
        source_kind TEXT NOT NULL,
        source_format TEXT NOT NULL,
        content_type TEXT NOT NULL,
        size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
        sha256 TEXT NOT NULL,
        encrypted_relative_path TEXT NOT NULL,
        created_by_user_id INTEGER NOT NULL REFERENCES users(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        created_at TEXT NOT NULL,
        UNIQUE(patient_id,sha256,source_kind)
    )""",
    """CREATE TABLE evaluation_runs(
        id INTEGER PRIMARY KEY,
        plan_version_id INTEGER NOT NULL REFERENCES treatment_plan_versions(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        checklist_version TEXT NOT NULL,
        rules_version TEXT NOT NULL,
        evaluation_date TEXT NOT NULL,
        facility_timezone TEXT NOT NULL,
        evidence_sha256 TEXT NOT NULL,
        trigger_kind TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(plan_version_id,checklist_version,rules_version,evaluation_date,evidence_sha256)
    )""",
    """CREATE TABLE criterion_results(
        id INTEGER PRIMARY KEY,
        evaluation_run_id INTEGER NOT NULL REFERENCES evaluation_runs(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        criterion_id TEXT NOT NULL,
        result_status TEXT NOT NULL,
        normalized_path TEXT NOT NULL,
        source_record_type TEXT NOT NULL,
        source_record_version_id INTEGER NOT NULL,
        evaluated_value_safe TEXT NOT NULL,
        explanation TEXT NOT NULL,
        evidence_sha256 TEXT NOT NULL,
        UNIQUE(evaluation_run_id,criterion_id)
    )""",
    """CREATE TRIGGER treatment_plan_versions_no_update BEFORE UPDATE ON treatment_plan_versions
        BEGIN SELECT RAISE(ABORT,'treatment_plan_versions are immutable'); END""",
    """CREATE TRIGGER treatment_plan_versions_no_delete BEFORE DELETE ON treatment_plan_versions
        BEGIN SELECT RAISE(ABORT,'treatment_plan_versions are immutable'); END""",
    """CREATE TRIGGER treatment_review_versions_no_update BEFORE UPDATE ON treatment_review_versions
        BEGIN SELECT RAISE(ABORT,'treatment_review_versions are immutable'); END""",
    """CREATE TRIGGER treatment_review_versions_no_delete BEFORE DELETE ON treatment_review_versions
        BEGIN SELECT RAISE(ABORT,'treatment_review_versions are immutable'); END""",
)
