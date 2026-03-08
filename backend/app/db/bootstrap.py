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
        'event_id': "VARCHAR(64) NOT NULL DEFAULT ''",
        'actor_type': "VARCHAR(20) NOT NULL DEFAULT 'human'",
        'forwarded_for': 'VARCHAR(255)',
        'source_host': 'VARCHAR(255)',
        'source_port': 'INTEGER',
        'correlation_id': "VARCHAR(64) NOT NULL DEFAULT 'no-correlation-id'",
        'session_id': 'VARCHAR(128)',
        'http_method': 'VARCHAR(16)',
        'request_path': 'VARCHAR(255)',
        'route_template': 'VARCHAR(255)',
        'query_string': 'TEXT',
        'http_status_code': 'INTEGER',
        'event_category': "VARCHAR(40) NOT NULL DEFAULT 'application'",
        'target_entity_type': 'VARCHAR(80)',
        'target_entity_id': 'VARCHAR(80)',
        'patient_id': 'VARCHAR(120)',
        'message': "TEXT NOT NULL DEFAULT ''",
        'before_state': 'TEXT',
        'after_state': 'TEXT',
        'diff_state': 'TEXT',
        'cef_version': 'INTEGER NOT NULL DEFAULT 0',
        'cef_device_vendor': "VARCHAR(80) NOT NULL DEFAULT 'OpenAI'",
        'cef_device_product': "VARCHAR(120) NOT NULL DEFAULT 'IZ Clinical Notes Analyzer'",
        'cef_device_version': "VARCHAR(40) NOT NULL DEFAULT '1'",
        'cef_signature_id': "VARCHAR(120) NOT NULL DEFAULT ''",
        'cef_name': "VARCHAR(255) NOT NULL DEFAULT ''",
        'cef_severity': 'INTEGER NOT NULL DEFAULT 5',
        'cef_extension': "TEXT NOT NULL DEFAULT ''",
        'cef_payload': "TEXT NOT NULL DEFAULT ''",
        'fhir_audit_event': "TEXT NOT NULL DEFAULT ''",
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
    'event_id': "TEXT NOT NULL DEFAULT ''",
    'actor_type': "TEXT NOT NULL DEFAULT 'human'",
    'forwarded_for': 'TEXT',
    'source_host': 'TEXT',
    'source_port': 'INTEGER',
    'correlation_id': "TEXT NOT NULL DEFAULT 'no-correlation-id'",
    'session_id': 'TEXT',
    'http_method': 'TEXT',
    'request_path': 'TEXT',
    'route_template': 'TEXT',
    'query_string': 'TEXT',
    'http_status_code': 'INTEGER',
    'event_category': "TEXT NOT NULL DEFAULT 'application'",
    'target_entity_type': 'TEXT',
    'target_entity_id': 'TEXT',
    'patient_id': 'TEXT',
    'message': "TEXT NOT NULL DEFAULT ''",
    'before_state': 'TEXT',
    'after_state': 'TEXT',
    'diff_state': 'TEXT',
    'cef_version': 'INTEGER NOT NULL DEFAULT 0',
    'cef_device_vendor': "TEXT NOT NULL DEFAULT 'OpenAI'",
    'cef_device_product': "TEXT NOT NULL DEFAULT 'IZ Clinical Notes Analyzer'",
    'cef_device_version': "TEXT NOT NULL DEFAULT '1'",
    'cef_signature_id': "TEXT NOT NULL DEFAULT ''",
    'cef_name': "TEXT NOT NULL DEFAULT ''",
    'cef_severity': 'INTEGER NOT NULL DEFAULT 5',
    'cef_extension': "TEXT NOT NULL DEFAULT ''",
    'cef_payload': "TEXT NOT NULL DEFAULT ''",
    'fhir_audit_event': "TEXT NOT NULL DEFAULT ''",
    'outcome_status': "TEXT NOT NULL DEFAULT 'success'",
    'severity': "TEXT NOT NULL DEFAULT 'info'",
    'prev_hash': 'TEXT',
}


def _column_ddl(column_name: str, postgres_ddl: str, dialect_name: str) -> str:
    if dialect_name == 'sqlite':
        return SQLITE_COLUMN_DEFS.get(column_name, postgres_ddl)
    return postgres_ddl


def ensure_schema_compatibility(engine: Engine) -> list[dict[str, str]]:
    inspector = inspect(engine)
    dialect_name = engine.dialect.name
    added_columns: list[dict[str, str]] = []

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
                added_columns.append({'table': table_name, 'column': column_name})

        if inspector.has_table('audit_logs'):
            if dialect_name == 'postgresql':
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_event_id ON audit_logs(event_id)'))
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_correlation_id ON audit_logs(correlation_id)'))
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_event_category ON audit_logs(event_category)'))
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_patient_id ON audit_logs(patient_id)'))
            elif dialect_name == 'sqlite':
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_event_id ON audit_logs(event_id)'))
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_correlation_id ON audit_logs(correlation_id)'))
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_event_category ON audit_logs(event_category)'))
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_patient_id ON audit_logs(patient_id)'))

    return added_columns
