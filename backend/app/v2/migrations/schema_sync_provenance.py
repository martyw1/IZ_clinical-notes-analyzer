from __future__ import annotations

SYNC_PROVENANCE_STATEMENTS = (
    "ALTER TABLE sync_checkpoints ADD COLUMN encrypted_records_json BLOB NULL",
    "ALTER TABLE treatment_plan_versions ADD COLUMN sync_job_id INTEGER NULL REFERENCES sync_jobs(id) ON UPDATE RESTRICT ON DELETE RESTRICT",
    "ALTER TABLE treatment_plan_versions ADD COLUMN approval_record_id INTEGER NULL REFERENCES alleva_contract_approvals(id) ON UPDATE RESTRICT ON DELETE RESTRICT",
    "ALTER TABLE treatment_plan_versions ADD COLUMN contract_version TEXT NULL",
    "ALTER TABLE treatment_plan_versions ADD COLUMN contract_sha256 TEXT NULL",
    "ALTER TABLE treatment_review_versions ADD COLUMN sync_job_id INTEGER NULL REFERENCES sync_jobs(id) ON UPDATE RESTRICT ON DELETE RESTRICT",
    "ALTER TABLE treatment_review_versions ADD COLUMN approval_record_id INTEGER NULL REFERENCES alleva_contract_approvals(id) ON UPDATE RESTRICT ON DELETE RESTRICT",
    "ALTER TABLE treatment_review_versions ADD COLUMN contract_version TEXT NULL",
    "ALTER TABLE treatment_review_versions ADD COLUMN contract_sha256 TEXT NULL",
    "ALTER TABLE diagnosis_snapshots ADD COLUMN sync_job_id INTEGER NULL REFERENCES sync_jobs(id) ON UPDATE RESTRICT ON DELETE RESTRICT",
    "ALTER TABLE diagnosis_snapshots ADD COLUMN approval_record_id INTEGER NULL REFERENCES alleva_contract_approvals(id) ON UPDATE RESTRICT ON DELETE RESTRICT",
    "ALTER TABLE diagnosis_snapshots ADD COLUMN contract_version TEXT NULL",
    "ALTER TABLE diagnosis_snapshots ADD COLUMN contract_sha256 TEXT NULL",
    "ALTER TABLE evaluation_runs ADD COLUMN sync_job_id INTEGER NULL REFERENCES sync_jobs(id) ON UPDATE RESTRICT ON DELETE RESTRICT",
    "ALTER TABLE evaluation_runs ADD COLUMN approval_record_id INTEGER NULL REFERENCES alleva_contract_approvals(id) ON UPDATE RESTRICT ON DELETE RESTRICT",
    "ALTER TABLE evaluation_runs ADD COLUMN contract_version TEXT NULL",
    "ALTER TABLE evaluation_runs ADD COLUMN contract_sha256 TEXT NULL",
)
