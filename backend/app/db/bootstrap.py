from __future__ import annotations

import logging
from collections.abc import Mapping

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# Defensive, idempotent bootstrap migration used when an existing database volume
# was created by an older app version. This prevents startup crashes where ORM
# models expect newer columns that are not present yet.
REQUIRED_COLUMNS: dict[str, dict[str, str]] = {
    'users': {
        'must_reset_password': 'BOOLEAN NOT NULL DEFAULT TRUE',
        'failed_login_attempts': 'INTEGER NOT NULL DEFAULT 0',
        'is_locked': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'created_at': 'TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()',
    },
    'charts': {
        'admission_date': "VARCHAR(40) NOT NULL DEFAULT ''",
        'discharge_date': "VARCHAR(40) NOT NULL DEFAULT ''",
        'auditor_name': "VARCHAR(120) NOT NULL DEFAULT ''",
        'other_details': "TEXT NOT NULL DEFAULT ''",
        'notes': "TEXT NOT NULL DEFAULT ''",
        'created_at': 'TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()',
    },
    'audit_item_responses': {
        'notes': "TEXT NOT NULL DEFAULT ''",
        'evidence_location': "VARCHAR(255) NOT NULL DEFAULT ''",
        'evidence_date': "VARCHAR(80) NOT NULL DEFAULT ''",
        'expiration_date': "VARCHAR(80) NOT NULL DEFAULT ''",
        'updated_at': 'TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()',
    },
    'workflow_transitions': {
        'comment': "TEXT NOT NULL DEFAULT ''",
        'created_at': 'TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()',
    },
    'audit_logs': {
        'outcome_status': "VARCHAR(20) NOT NULL DEFAULT 'success'",
        'severity': "VARCHAR(20) NOT NULL DEFAULT 'info'",
        'prev_hash': 'VARCHAR(128)',
    },
}

SQLITE_COLUMN_DEFS: Mapping[str, str] = {
    'must_reset_password': 'BOOLEAN NOT NULL DEFAULT 1',
    'failed_login_attempts': 'INTEGER NOT NULL DEFAULT 0',
    'is_locked': 'BOOLEAN NOT NULL DEFAULT 0',
    'created_at': 'TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP',
    'admission_date': "TEXT NOT NULL DEFAULT ''",
    'discharge_date': "TEXT NOT NULL DEFAULT ''",
    'auditor_name': "TEXT NOT NULL DEFAULT ''",
    'other_details': "TEXT NOT NULL DEFAULT ''",
    'notes': "TEXT NOT NULL DEFAULT ''",
    'evidence_location': "TEXT NOT NULL DEFAULT ''",
    'evidence_date': "TEXT NOT NULL DEFAULT ''",
    'expiration_date': "TEXT NOT NULL DEFAULT ''",
    'updated_at': 'TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP',
    'comment': "TEXT NOT NULL DEFAULT ''",
    'outcome_status': "TEXT NOT NULL DEFAULT 'success'",
    'severity': "TEXT NOT NULL DEFAULT 'info'",
    'prev_hash': 'TEXT',
}


def _column_ddl(column_name: str, postgres_ddl: str, dialect_name: str) -> str:
    if dialect_name == 'sqlite':
        return SQLITE_COLUMN_DEFS.get(column_name, postgres_ddl)
    return postgres_ddl


def ensure_schema_compatibility(engine: Engine) -> None:
    inspector = inspect(engine)
    dialect_name = engine.dialect.name

    with engine.begin() as connection:
        for table_name, columns in REQUIRED_COLUMNS.items():
            if not inspector.has_table(table_name):
                continue

            existing_columns = {column['name'] for column in inspector.get_columns(table_name)}
            for column_name, postgres_ddl in columns.items():
                if column_name in existing_columns:
                    continue

                column_ddl = _column_ddl(column_name, postgres_ddl, dialect_name)
                logger.warning('Detected legacy schema: adding missing %s.%s column.', table_name, column_name)
                connection.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_ddl}'))
