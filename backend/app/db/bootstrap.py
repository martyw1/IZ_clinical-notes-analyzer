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
        'full_name': "VARCHAR(120) NOT NULL DEFAULT ''",
        'is_active': 'BOOLEAN NOT NULL DEFAULT TRUE',
        'must_reset_password': 'BOOLEAN NOT NULL DEFAULT TRUE',
        'failed_login_attempts': 'INTEGER NOT NULL DEFAULT 0',
        'is_locked': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'last_login_at': 'TIMESTAMP WITH TIME ZONE',
        'created_at': 'TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()',
    },
    'app_settings': {
        'organization_name': "VARCHAR(120) NOT NULL DEFAULT 'R3 Recovery Services'",
        'access_intel_enabled': 'BOOLEAN NOT NULL DEFAULT TRUE',
        'access_geo_lookup_url': "VARCHAR(255) NOT NULL DEFAULT 'https://ipwho.is/{ip}'",
        'access_reputation_url': "VARCHAR(255) NOT NULL DEFAULT 'https://api.abuseipdb.com/api/v2/check'",
        'access_reputation_api_key': "VARCHAR(255) NOT NULL DEFAULT ''",
        'access_lookup_timeout_seconds': 'INTEGER NOT NULL DEFAULT 4',
        'llm_enabled': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'llm_provider_name': "VARCHAR(80) NOT NULL DEFAULT 'OpenAI-compatible'",
        'llm_base_url': "VARCHAR(255) NOT NULL DEFAULT 'https://api.openai.com/v1'",
        'llm_model': "VARCHAR(120) NOT NULL DEFAULT 'gpt-4.1-mini'",
        'llm_api_key': "VARCHAR(255) NOT NULL DEFAULT ''",
        'llm_use_for_access_review': 'BOOLEAN NOT NULL DEFAULT TRUE',
        'llm_use_for_evaluation_gap_analysis': 'BOOLEAN NOT NULL DEFAULT TRUE',
        'llm_analysis_instructions': "TEXT NOT NULL DEFAULT ''",
        'emr_api_enabled': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'emr_vendor_name': "VARCHAR(120) NOT NULL DEFAULT 'Alleva / FHIR'",
        'emr_fhir_base_url': "VARCHAR(255) NOT NULL DEFAULT ''",
        'emr_smart_client_id': "VARCHAR(255) NOT NULL DEFAULT ''",
        'emr_smart_client_secret': "VARCHAR(1024) NOT NULL DEFAULT ''",
        'emr_smart_token_url': "VARCHAR(500) NOT NULL DEFAULT 'https://authorization.allevasoft.com/connect/token'",
        'emr_smart_token_auth_style': "VARCHAR(40) NOT NULL DEFAULT 'body'",
        'emr_smart_scopes': "VARCHAR(500) NOT NULL DEFAULT 'openid fhirUser launch/patient patient/Patient.rs patient/DocumentReference.rs patient/Binary.rs patient/Provenance.rs'",
        'emr_api_timeout_seconds': 'INTEGER NOT NULL DEFAULT 10',
        'emr_periodic_check_enabled': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'emr_periodic_check_interval_minutes': 'INTEGER NOT NULL DEFAULT 1440',
        'emr_last_check_at': 'TIMESTAMP WITH TIME ZONE',
        'emr_last_check_status': "VARCHAR(40) NOT NULL DEFAULT ''",
        'emr_last_check_message': "TEXT NOT NULL DEFAULT ''",
        'emr_last_successful_check_at': 'TIMESTAMP WITH TIME ZONE',
        'emr_last_failure_at': 'TIMESTAMP WITH TIME ZONE',
        'facility_timezone': "VARCHAR(80) NOT NULL DEFAULT 'local_machine'",
        'treatment_plan_loc_change_window_days': 'INTEGER',
        'treatment_plan_loc_change_window_validated': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'updated_by_id': 'INTEGER',
        'updated_at': 'TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()',
    },
    'charts': {
        'source_note_set_id': 'INTEGER',
        'patient_id': "VARCHAR(120) NOT NULL DEFAULT ''",
        'admission_date': "VARCHAR(40) NOT NULL DEFAULT ''",
        'discharge_date': "VARCHAR(40) NOT NULL DEFAULT ''",
        'auditor_name': "VARCHAR(120) NOT NULL DEFAULT ''",
        'other_details': "TEXT NOT NULL DEFAULT ''",
        'system_score': 'INTEGER NOT NULL DEFAULT 0',
        'system_summary': "TEXT NOT NULL DEFAULT ''",
        'manager_comment': "TEXT NOT NULL DEFAULT ''",
        'reviewed_by_id': 'INTEGER',
        'system_generated_at': 'TIMESTAMP WITH TIME ZONE',
        'reviewed_at': 'TIMESTAMP WITH TIME ZONE',
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
    'workflow_definitions': {
        'workflow_key': "VARCHAR(80) NOT NULL DEFAULT ''",
        'display_name': "VARCHAR(120) NOT NULL DEFAULT ''",
        'description': "TEXT NOT NULL DEFAULT ''",
        'category': "VARCHAR(80) NOT NULL DEFAULT 'clinical_review'",
        'is_active': 'BOOLEAN NOT NULL DEFAULT TRUE',
        'current_version_id': 'INTEGER',
        'created_by_id': 'INTEGER',
        'updated_by_id': 'INTEGER',
        'created_at': 'TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()',
        'updated_at': 'TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()',
    },
    'workflow_definition_versions': {
        'workflow_definition_id': 'INTEGER',
        'version': 'INTEGER NOT NULL DEFAULT 1',
        'status': "VARCHAR(20) NOT NULL DEFAULT 'draft'",
        'definition_snapshot': "TEXT NOT NULL DEFAULT '{}'",
        'transition_rules': "TEXT NOT NULL DEFAULT '[]'",
        'version_notes': "TEXT NOT NULL DEFAULT ''",
        'created_by_id': 'INTEGER',
        'published_by_id': 'INTEGER',
        'archived_by_id': 'INTEGER',
        'created_at': 'TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()',
        'published_at': 'TIMESTAMP WITH TIME ZONE',
        'archived_at': 'TIMESTAMP WITH TIME ZONE',
    },
    'patient_note_sets': {
        'source_export_id': "VARCHAR(120) NOT NULL DEFAULT ''",
        'source_patient_resource_id': "VARCHAR(120) NOT NULL DEFAULT ''",
    },
    'patient_note_documents': {
        'source_document_id': "VARCHAR(120) NOT NULL DEFAULT ''",
        'source_document_reference_id': "VARCHAR(120) NOT NULL DEFAULT ''",
        'source_attachment_url': "VARCHAR(500) NOT NULL DEFAULT ''",
        'source_author': "VARCHAR(255) NOT NULL DEFAULT ''",
        'source_custodian': "VARCHAR(255) NOT NULL DEFAULT ''",
        'source_security_label': "VARCHAR(255) NOT NULL DEFAULT ''",
        'source_provenance_id': "VARCHAR(120) NOT NULL DEFAULT ''",
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
    'level_of_care_history': {
        'facility': "VARCHAR(120) NOT NULL DEFAULT ''",
        'discharge_date': "VARCHAR(40) NOT NULL DEFAULT ''",
    },
    'treatment_plan_records': {
        'reviewer_signature_date': "VARCHAR(40) NOT NULL DEFAULT ''",
        'displayed_next_due_date': "VARCHAR(40) NOT NULL DEFAULT ''",
        'source_section': "VARCHAR(120) NOT NULL DEFAULT ''",
    },
}

SQLITE_COLUMN_DEFS: Mapping[str, str] = {
    'must_reset_password': 'BOOLEAN NOT NULL DEFAULT 1',
    'full_name': "TEXT NOT NULL DEFAULT ''",
    'is_active': 'BOOLEAN NOT NULL DEFAULT 1',
    'failed_login_attempts': 'INTEGER NOT NULL DEFAULT 0',
    'is_locked': 'BOOLEAN NOT NULL DEFAULT 0',
    'last_login_at': 'TEXT',
    'created_at': 'TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP',
    'organization_name': "TEXT NOT NULL DEFAULT 'R3 Recovery Services'",
    'access_intel_enabled': 'BOOLEAN NOT NULL DEFAULT 1',
    'access_geo_lookup_url': "TEXT NOT NULL DEFAULT 'https://ipwho.is/{ip}'",
    'access_reputation_url': "TEXT NOT NULL DEFAULT 'https://api.abuseipdb.com/api/v2/check'",
    'access_reputation_api_key': "TEXT NOT NULL DEFAULT ''",
    'access_lookup_timeout_seconds': 'INTEGER NOT NULL DEFAULT 4',
    'llm_enabled': 'BOOLEAN NOT NULL DEFAULT 0',
    'llm_provider_name': "TEXT NOT NULL DEFAULT 'OpenAI-compatible'",
    'llm_base_url': "TEXT NOT NULL DEFAULT 'https://api.openai.com/v1'",
    'llm_model': "TEXT NOT NULL DEFAULT 'gpt-4.1-mini'",
    'llm_api_key': "TEXT NOT NULL DEFAULT ''",
    'llm_use_for_access_review': 'BOOLEAN NOT NULL DEFAULT 1',
    'llm_use_for_evaluation_gap_analysis': 'BOOLEAN NOT NULL DEFAULT 1',
    'llm_analysis_instructions': "TEXT NOT NULL DEFAULT ''",
    'emr_api_enabled': 'BOOLEAN NOT NULL DEFAULT 0',
    'emr_vendor_name': "TEXT NOT NULL DEFAULT 'Alleva / FHIR'",
    'emr_fhir_base_url': "TEXT NOT NULL DEFAULT ''",
    'emr_smart_client_id': "TEXT NOT NULL DEFAULT ''",
    'emr_smart_client_secret': "TEXT NOT NULL DEFAULT ''",
    'emr_smart_token_url': "TEXT NOT NULL DEFAULT 'https://authorization.allevasoft.com/connect/token'",
    'emr_smart_token_auth_style': "TEXT NOT NULL DEFAULT 'body'",
    'emr_smart_scopes': "TEXT NOT NULL DEFAULT 'openid fhirUser launch/patient patient/Patient.rs patient/DocumentReference.rs patient/Binary.rs patient/Provenance.rs'",
    'emr_api_timeout_seconds': 'INTEGER NOT NULL DEFAULT 10',
    'emr_periodic_check_enabled': 'BOOLEAN NOT NULL DEFAULT 0',
    'emr_periodic_check_interval_minutes': 'INTEGER NOT NULL DEFAULT 1440',
    'emr_last_check_at': 'TEXT',
    'emr_last_check_status': "TEXT NOT NULL DEFAULT ''",
    'emr_last_check_message': "TEXT NOT NULL DEFAULT ''",
    'emr_last_successful_check_at': 'TEXT',
    'emr_last_failure_at': 'TEXT',
    'facility_timezone': "TEXT NOT NULL DEFAULT 'local_machine'",
    'treatment_plan_loc_change_window_days': 'INTEGER',
    'treatment_plan_loc_change_window_validated': 'BOOLEAN NOT NULL DEFAULT 0',
    'updated_by_id': 'INTEGER',
    'updated_at': 'TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP',
    'source_note_set_id': 'INTEGER',
    'admission_date': "TEXT NOT NULL DEFAULT ''",
    'discharge_date': "TEXT NOT NULL DEFAULT ''",
    'patient_id': "TEXT NOT NULL DEFAULT ''",
    'auditor_name': "TEXT NOT NULL DEFAULT ''",
    'other_details': "TEXT NOT NULL DEFAULT ''",
    'system_score': 'INTEGER NOT NULL DEFAULT 0',
    'system_summary': "TEXT NOT NULL DEFAULT ''",
    'manager_comment': "TEXT NOT NULL DEFAULT ''",
    'reviewed_by_id': 'INTEGER',
    'system_generated_at': 'TEXT',
    'reviewed_at': 'TEXT',
    'notes': "TEXT NOT NULL DEFAULT ''",
    'evidence_location': "TEXT NOT NULL DEFAULT ''",
    'evidence_date': "TEXT NOT NULL DEFAULT ''",
    'expiration_date': "TEXT NOT NULL DEFAULT ''",
    'updated_at': 'TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP',
    'comment': "TEXT NOT NULL DEFAULT ''",
    'workflow_key': "TEXT NOT NULL DEFAULT ''",
    'display_name': "TEXT NOT NULL DEFAULT ''",
    'description': "TEXT NOT NULL DEFAULT ''",
    'category': "TEXT NOT NULL DEFAULT 'clinical_review'",
    'current_version_id': 'INTEGER',
    'workflow_definition_id': 'INTEGER',
    'version': 'INTEGER NOT NULL DEFAULT 1',
    'status': "TEXT NOT NULL DEFAULT 'draft'",
    'definition_snapshot': "TEXT NOT NULL DEFAULT '{}'",
    'transition_rules': "TEXT NOT NULL DEFAULT '[]'",
    'version_notes': "TEXT NOT NULL DEFAULT ''",
    'created_by_id': 'INTEGER',
    'published_by_id': 'INTEGER',
    'archived_by_id': 'INTEGER',
    'published_at': 'TEXT',
    'archived_at': 'TEXT',
    'source_export_id': "TEXT NOT NULL DEFAULT ''",
    'source_patient_resource_id': "TEXT NOT NULL DEFAULT ''",
    'source_document_id': "TEXT NOT NULL DEFAULT ''",
    'source_document_reference_id': "TEXT NOT NULL DEFAULT ''",
    'source_attachment_url': "TEXT NOT NULL DEFAULT ''",
    'source_author': "TEXT NOT NULL DEFAULT ''",
    'source_custodian': "TEXT NOT NULL DEFAULT ''",
    'source_security_label': "TEXT NOT NULL DEFAULT ''",
    'source_provenance_id': "TEXT NOT NULL DEFAULT ''",
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
    'facility': "TEXT NOT NULL DEFAULT ''",
    'displayed_next_due_date': "TEXT NOT NULL DEFAULT ''",
    'reviewer_signature_date': "TEXT NOT NULL DEFAULT ''",
    'source_section': "TEXT NOT NULL DEFAULT ''",
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

        if inspector.has_table('app_settings') and dialect_name == 'postgresql':
            connection.execute(text('ALTER TABLE app_settings ALTER COLUMN emr_smart_client_secret TYPE VARCHAR(1024)'))

        if inspector.has_table('charts'):
            if dialect_name == 'postgresql':
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_charts_patient_id ON charts(patient_id)'))
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_charts_source_note_set_id ON charts(source_note_set_id)'))
            elif dialect_name == 'sqlite':
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_charts_patient_id ON charts(patient_id)'))
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_charts_source_note_set_id ON charts(source_note_set_id)'))

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
