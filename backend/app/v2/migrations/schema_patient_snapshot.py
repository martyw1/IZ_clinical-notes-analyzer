from __future__ import annotations


PATIENT_SNAPSHOT_STATEMENTS = (
    """CREATE TABLE patient_source_snapshots(
        id INTEGER PRIMARY KEY,
        patient_id INTEGER NOT NULL REFERENCES patients(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        source_system TEXT NOT NULL,
        source_record_id TEXT NOT NULL,
        version_ordinal INTEGER NOT NULL CHECK(version_ordinal >= 1),
        normalized_snapshot_encrypted BLOB NOT NULL,
        content_sha256 TEXT NOT NULL,
        source_last_updated TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        supersedes_snapshot_id INTEGER NULL REFERENCES patient_source_snapshots(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        sync_job_id INTEGER NULL REFERENCES sync_jobs(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        approval_record_id INTEGER NULL REFERENCES alleva_contract_approvals(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        contract_version TEXT NULL,
        contract_sha256 TEXT NULL,
        UNIQUE(patient_id,source_system,source_record_id,content_sha256),
        UNIQUE(patient_id,version_ordinal)
    )""",
    "CREATE INDEX ix_patient_source_snapshots_latest ON patient_source_snapshots(patient_id,version_ordinal DESC,id DESC)",
    """CREATE TRIGGER patient_source_snapshots_no_update BEFORE UPDATE ON patient_source_snapshots
        BEGIN SELECT RAISE(ABORT,'patient_source_snapshots are immutable'); END""",
    """CREATE TRIGGER patient_source_snapshots_no_delete BEFORE DELETE ON patient_source_snapshots
        BEGIN SELECT RAISE(ABORT,'patient_source_snapshots are immutable'); END""",
)
