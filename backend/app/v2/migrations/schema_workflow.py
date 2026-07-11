from __future__ import annotations

WORKFLOW_STATEMENTS = (
    """CREATE TABLE manager_dispositions(
        id INTEGER PRIMARY KEY,
        plan_version_id INTEGER REFERENCES treatment_plan_versions(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        criterion_id TEXT,
        status TEXT,
        comment TEXT,
        actor_user_id INTEGER REFERENCES users(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        created_at TEXT,
        supersedes_disposition_id INTEGER NULL REFERENCES manager_dispositions(id) ON UPDATE RESTRICT ON DELETE RESTRICT
    )""",
    "CREATE UNIQUE INDEX uq_manager_disposition_event ON manager_dispositions(plan_version_id,criterion_id,actor_user_id,created_at)",
    """CREATE TABLE correction_work_items(
        id INTEGER PRIMARY KEY,
        plan_version_id INTEGER NOT NULL REFERENCES treatment_plan_versions(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        criterion_id TEXT NOT NULL,
        disposition_id INTEGER NOT NULL REFERENCES manager_dispositions(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        assigned_counselor_user_id INTEGER NOT NULL REFERENCES users(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        status TEXT NOT NULL,
        opened_at TEXT NOT NULL,
        closed_at TEXT NULL,
        idempotency_key TEXT NOT NULL UNIQUE
    )""",
    """CREATE TABLE correction_submissions(
        id INTEGER PRIMARY KEY,
        work_item_id INTEGER NOT NULL REFERENCES correction_work_items(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        counselor_user_id INTEGER NOT NULL REFERENCES users(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        submission_encrypted BLOB NOT NULL,
        evidence_sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL,
        idempotency_key TEXT NOT NULL UNIQUE
    )""",
    """CREATE TRIGGER manager_dispositions_no_update BEFORE UPDATE ON manager_dispositions
        BEGIN SELECT RAISE(ABORT,'manager_dispositions are immutable'); END""",
    """CREATE TRIGGER manager_dispositions_no_delete BEFORE DELETE ON manager_dispositions
        BEGIN SELECT RAISE(ABORT,'manager_dispositions are immutable'); END""",
)
