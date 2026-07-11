from __future__ import annotations

EVALUATION_LEDGER_STATEMENTS = (
    "ALTER TABLE criterion_results RENAME TO criterion_results_v2",
    "ALTER TABLE evaluation_runs RENAME TO evaluation_runs_v2",
    """CREATE TABLE evaluation_runs(
        id INTEGER PRIMARY KEY,
        plan_version_id INTEGER NOT NULL REFERENCES treatment_plan_versions(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        checklist_version TEXT NOT NULL,
        rules_version TEXT NOT NULL,
        evaluation_date TEXT NOT NULL,
        facility_timezone TEXT NOT NULL,
        evidence_sha256 TEXT NOT NULL,
        trigger_kind TEXT NOT NULL,
        run_sequence INTEGER NOT NULL CHECK(run_sequence > 0),
        created_at TEXT NOT NULL,
        UNIQUE(plan_version_id,checklist_version,rules_version,evaluation_date,evidence_sha256,run_sequence)
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
    """INSERT INTO evaluation_runs(
        id,plan_version_id,checklist_version,rules_version,evaluation_date,facility_timezone,
        evidence_sha256,trigger_kind,run_sequence,created_at
    ) SELECT id,plan_version_id,checklist_version,rules_version,evaluation_date,facility_timezone,
        evidence_sha256,trigger_kind,1,created_at FROM evaluation_runs_v2""",
    """INSERT INTO criterion_results(
        id,evaluation_run_id,criterion_id,result_status,normalized_path,source_record_type,
        source_record_version_id,evaluated_value_safe,explanation,evidence_sha256
    ) SELECT id,evaluation_run_id,criterion_id,result_status,normalized_path,source_record_type,
        source_record_version_id,evaluated_value_safe,explanation,evidence_sha256 FROM criterion_results_v2""",
    "DROP TABLE criterion_results_v2",
    "DROP TABLE evaluation_runs_v2",
    """CREATE TRIGGER evaluation_runs_no_update BEFORE UPDATE ON evaluation_runs
        BEGIN SELECT RAISE(ABORT,'evaluation_runs are immutable'); END""",
    """CREATE TRIGGER evaluation_runs_no_delete BEFORE DELETE ON evaluation_runs
        BEGIN SELECT RAISE(ABORT,'evaluation_runs are immutable'); END""",
    """CREATE TRIGGER criterion_results_no_update BEFORE UPDATE ON criterion_results
        BEGIN SELECT RAISE(ABORT,'criterion_results are immutable'); END""",
    """CREATE TRIGGER criterion_results_no_delete BEFORE DELETE ON criterion_results
        BEGIN SELECT RAISE(ABORT,'criterion_results are immutable'); END""",
)
