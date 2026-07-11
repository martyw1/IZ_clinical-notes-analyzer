from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from app.v2.migrations.lifecycle_types import TableCount

REPORT_TABLES = (
    "facilities", "patients", "patient_assignments", "loc_history",
    "treatment_plan_versions", "treatment_review_versions", "diagnosis_snapshots",
    "source_documents", "evaluation_runs", "criterion_results", "manager_dispositions",
    "correction_work_items", "correction_submissions", "sync_jobs", "sync_checkpoints",
    "sync_failures", "reconciliation_outcomes", "migration_reconciliation",
)


def table_counts_database(database_path: Path) -> tuple[TableCount, ...]:
    with closing(sqlite3.connect(database_path)) as connection:
        return table_counts(connection)


def table_counts(connection: sqlite3.Connection) -> tuple[TableCount, ...]:
    existing = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return tuple(
        TableCount(table=table, count=int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]))
        for table in REPORT_TABLES
        if table in existing
    )
