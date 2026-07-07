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
        'emr_vendor_name': "VARCHAR(120) NOT NULL DEFAULT 'Alleva REST API'",
        'api_client_id': "VARCHAR(255) NOT NULL DEFAULT ''",
        'api_client_secret': "VARCHAR(1024) NOT NULL DEFAULT ''",
        'api_oauth_token_url': "VARCHAR(500) NOT NULL DEFAULT 'https://authorization.allevasoft.com/connect/token'",
        'api_token_auth_style': "VARCHAR(40) NOT NULL DEFAULT 'body'",
        'emr_api_timeout_seconds': 'INTEGER NOT NULL DEFAULT 10',
        'emr_periodic_check_enabled': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'emr_periodic_check_interval_minutes': 'INTEGER NOT NULL DEFAULT 1440',
        'emr_last_check_at': 'TIMESTAMP WITH TIME ZONE',
        'emr_last_check_status': "VARCHAR(40) NOT NULL DEFAULT ''",
        'emr_last_check_message': "TEXT NOT NULL DEFAULT ''",
        'emr_last_successful_check_at': 'TIMESTAMP WITH TIME ZONE',
        'emr_last_failure_at': 'TIMESTAMP WITH TIME ZONE',
        'alleva_api_base_url': "VARCHAR(255) NOT NULL DEFAULT 'https://api.allevasoft.com'",
        'alleva_openapi_url': "VARCHAR(500) NOT NULL DEFAULT 'https://api.allevasoft.com/swagger/v1/swagger.json'",
        'alleva_api_version': "VARCHAR(20) NOT NULL DEFAULT '1.0'",
        'alleva_treatment_plan_sync_enabled': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'alleva_treatment_plan_sync_on_startup': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'alleva_treatment_plan_sync_approved': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'alleva_treatment_plan_endpoint_mapping_validated': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'alleva_treatment_plan_sync_limit': 'INTEGER NOT NULL DEFAULT 250',
        'alleva_treatment_plan_detail_fetch_enabled': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'alleva_treatment_plan_patient_name_import_enabled': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'alleva_treatment_plan_name_join_fallback_enabled': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'alleva_treatment_plan_detail_fetch_limit': 'INTEGER NOT NULL DEFAULT 50',
        'alleva_treatment_plan_sync_last_at': 'TIMESTAMP WITH TIME ZONE',
        'alleva_treatment_plan_sync_last_status': "VARCHAR(40) NOT NULL DEFAULT ''",
        'alleva_treatment_plan_sync_last_message': "TEXT NOT NULL DEFAULT ''",
        'alleva_treatment_plan_sync_last_success_at': 'TIMESTAMP WITH TIME ZONE',
        'alleva_treatment_plan_sync_last_failure_at': 'TIMESTAMP WITH TIME ZONE',
        'facility_timezone': "VARCHAR(80) NOT NULL DEFAULT 'local_machine'",
        'treatment_plan_master_due_days': 'INTEGER NOT NULL DEFAULT 30',
        'treatment_plan_php_review_interval_days': 'INTEGER NOT NULL DEFAULT 30',
        'treatment_plan_iop_op_review_interval_days': 'INTEGER NOT NULL DEFAULT 60',
        'treatment_plan_loc_change_window_days': 'INTEGER DEFAULT 7',
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
    'emr_endpoint_profiles': {
        'profile_key': "VARCHAR(80) NOT NULL DEFAULT ''",
        'display_name': "VARCHAR(120) NOT NULL DEFAULT ''",
        'vendor_name': "VARCHAR(120) NOT NULL DEFAULT 'Alleva'",
        'adapter_key': "VARCHAR(120) NOT NULL DEFAULT 'alleva-rest-api'",
        'api_base_url': "VARCHAR(500) NOT NULL DEFAULT 'https://api.allevasoft.com'",
        'openapi_url': "VARCHAR(500) NOT NULL DEFAULT ''",
        'token_url': "VARCHAR(500) NOT NULL DEFAULT ''",
        'token_auth_style': "VARCHAR(40) NOT NULL DEFAULT 'body'",
        'client_id': "VARCHAR(255) NOT NULL DEFAULT ''",
        'client_secret': "VARCHAR(1024) NOT NULL DEFAULT ''",
        'timeout_seconds': 'INTEGER NOT NULL DEFAULT 10',
        'is_active': 'BOOLEAN NOT NULL DEFAULT TRUE',
        'is_default': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'notes': "TEXT NOT NULL DEFAULT ''",
        'created_by_id': 'INTEGER',
        'updated_by_id': 'INTEGER',
        'created_at': 'TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()',
        'updated_at': 'TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()',
    },
    'patient_note_sets': {
        'source_export_id': "VARCHAR(120) NOT NULL DEFAULT ''",
        'source_patient_resource_id': "VARCHAR(120) NOT NULL DEFAULT ''",
    },
    'patient_note_documents': {
        'source_document_id': "VARCHAR(120) NOT NULL DEFAULT ''",
        'source_attachment_url': "VARCHAR(500) NOT NULL DEFAULT ''",
        'source_author': "VARCHAR(255) NOT NULL DEFAULT ''",
        'source_custodian': "VARCHAR(255) NOT NULL DEFAULT ''",
        'source_security_label': "VARCHAR(255) NOT NULL DEFAULT ''",
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
        'problem_count': 'INTEGER NOT NULL DEFAULT 0',
        'diagnosis_count': 'INTEGER NOT NULL DEFAULT 0',
        'behavioral_definition_count': 'INTEGER NOT NULL DEFAULT 0',
        'goal_count': 'INTEGER NOT NULL DEFAULT 0',
        'objective_count': 'INTEGER NOT NULL DEFAULT 0',
        'intervention_count': 'INTEGER NOT NULL DEFAULT 0',
        'has_guardian_signature': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'guardian_signature_date': "VARCHAR(40) NOT NULL DEFAULT ''",
        'alleva_is_active': 'BOOLEAN NOT NULL DEFAULT TRUE',
        'alleva_is_complete': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'alleva_is_initial_tp': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'alleva_start_date': "VARCHAR(40) NOT NULL DEFAULT ''",
        'alleva_end_date': "VARCHAR(40) NOT NULL DEFAULT ''",
        'alleva_last_modified': "VARCHAR(40) NOT NULL DEFAULT ''",
        'detail_fetched': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'detail_fetched_at': 'TIMESTAMP WITH TIME ZONE',
        'content_source': "VARCHAR(40) NOT NULL DEFAULT 'collection'",
        'content_items_json': "TEXT NOT NULL DEFAULT '[]'",
        'content_capture_status': "VARCHAR(40) NOT NULL DEFAULT 'counts_only'",
        'content_capture_warnings': "TEXT NOT NULL DEFAULT ''",
    },
    'treatment_plan_clients': {
        'alleva_lead_id': "VARCHAR(120) NOT NULL DEFAULT ''",
        'alleva_client_id': "VARCHAR(120) NOT NULL DEFAULT ''",
        'alleva_unique_id': "VARCHAR(120) NOT NULL DEFAULT ''",
        'alleva_mrn': "VARCHAR(120) NOT NULL DEFAULT ''",
        'alleva_source_id': "VARCHAR(120) NOT NULL DEFAULT ''",
        'id_join_confidence': "VARCHAR(40) NOT NULL DEFAULT 'unknown'",
        'id_join_warnings': "TEXT NOT NULL DEFAULT ''",
        'data_quality_warnings': "TEXT NOT NULL DEFAULT ''",
        'discharge_conflict': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'current_plan_record_id': 'INTEGER',
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
    'emr_vendor_name': "TEXT NOT NULL DEFAULT 'Alleva REST API'",
    'api_client_id': "TEXT NOT NULL DEFAULT ''",
    'api_client_secret': "TEXT NOT NULL DEFAULT ''",
    'api_oauth_token_url': "TEXT NOT NULL DEFAULT 'https://authorization.allevasoft.com/connect/token'",
    'api_token_auth_style': "TEXT NOT NULL DEFAULT 'body'",
    'emr_api_timeout_seconds': 'INTEGER NOT NULL DEFAULT 10',
    'emr_periodic_check_enabled': 'BOOLEAN NOT NULL DEFAULT 0',
    'emr_periodic_check_interval_minutes': 'INTEGER NOT NULL DEFAULT 1440',
    'emr_last_check_at': 'TEXT',
    'emr_last_check_status': "TEXT NOT NULL DEFAULT ''",
    'emr_last_check_message': "TEXT NOT NULL DEFAULT ''",
    'emr_last_successful_check_at': 'TEXT',
    'emr_last_failure_at': 'TEXT',
    'alleva_api_base_url': "TEXT NOT NULL DEFAULT 'https://api.allevasoft.com'",
    'alleva_openapi_url': "TEXT NOT NULL DEFAULT 'https://api.allevasoft.com/swagger/v1/swagger.json'",
    'alleva_api_version': "TEXT NOT NULL DEFAULT '1.0'",
    'alleva_treatment_plan_sync_enabled': 'BOOLEAN NOT NULL DEFAULT 0',
    'alleva_treatment_plan_sync_on_startup': 'BOOLEAN NOT NULL DEFAULT 0',
    'alleva_treatment_plan_sync_approved': 'BOOLEAN NOT NULL DEFAULT 0',
    'alleva_treatment_plan_endpoint_mapping_validated': 'BOOLEAN NOT NULL DEFAULT 0',
    'alleva_treatment_plan_sync_limit': 'INTEGER NOT NULL DEFAULT 250',
    'alleva_treatment_plan_detail_fetch_enabled': 'BOOLEAN NOT NULL DEFAULT 0',
    'alleva_treatment_plan_patient_name_import_enabled': 'BOOLEAN NOT NULL DEFAULT 0',
    'alleva_treatment_plan_name_join_fallback_enabled': 'BOOLEAN NOT NULL DEFAULT 0',
    'alleva_treatment_plan_detail_fetch_limit': 'INTEGER NOT NULL DEFAULT 50',
    'alleva_treatment_plan_sync_last_at': 'TEXT',
    'alleva_treatment_plan_sync_last_status': "TEXT NOT NULL DEFAULT ''",
    'alleva_treatment_plan_sync_last_message': "TEXT NOT NULL DEFAULT ''",
    'alleva_treatment_plan_sync_last_success_at': 'TEXT',
    'alleva_treatment_plan_sync_last_failure_at': 'TEXT',
    'facility_timezone': "TEXT NOT NULL DEFAULT 'local_machine'",
    'treatment_plan_master_due_days': 'INTEGER NOT NULL DEFAULT 30',
    'treatment_plan_php_review_interval_days': 'INTEGER NOT NULL DEFAULT 30',
    'treatment_plan_iop_op_review_interval_days': 'INTEGER NOT NULL DEFAULT 60',
    'treatment_plan_loc_change_window_days': 'INTEGER DEFAULT 7',
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
    'api_base_url': "TEXT NOT NULL DEFAULT 'https://api.allevasoft.com'",
    'openapi_url': "TEXT NOT NULL DEFAULT ''",
    'token_url': "TEXT NOT NULL DEFAULT ''",
    'token_auth_style': "TEXT NOT NULL DEFAULT 'body'",
    'client_id': "TEXT NOT NULL DEFAULT ''",
    'client_secret': "TEXT NOT NULL DEFAULT ''",
    'timeout_seconds': 'INTEGER NOT NULL DEFAULT 10',
    'is_default': 'BOOLEAN NOT NULL DEFAULT 0',
    'source_export_id': "TEXT NOT NULL DEFAULT ''",
    'source_patient_resource_id': "TEXT NOT NULL DEFAULT ''",
    'source_document_id': "TEXT NOT NULL DEFAULT ''",
    'source_attachment_url': "TEXT NOT NULL DEFAULT ''",
    'source_author': "TEXT NOT NULL DEFAULT ''",
    'source_custodian': "TEXT NOT NULL DEFAULT ''",
    'source_security_label': "TEXT NOT NULL DEFAULT ''",
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
    'outcome_status': "TEXT NOT NULL DEFAULT 'success'",
    'severity': "TEXT NOT NULL DEFAULT 'info'",
    'prev_hash': 'TEXT',
    'facility': "TEXT NOT NULL DEFAULT ''",
    'displayed_next_due_date': "TEXT NOT NULL DEFAULT ''",
    'reviewer_signature_date': "TEXT NOT NULL DEFAULT ''",
    'source_section': "TEXT NOT NULL DEFAULT ''",
    'problem_count': 'INTEGER NOT NULL DEFAULT 0',
    'diagnosis_count': 'INTEGER NOT NULL DEFAULT 0',
    'behavioral_definition_count': 'INTEGER NOT NULL DEFAULT 0',
    'goal_count': 'INTEGER NOT NULL DEFAULT 0',
    'objective_count': 'INTEGER NOT NULL DEFAULT 0',
    'intervention_count': 'INTEGER NOT NULL DEFAULT 0',
    'has_guardian_signature': 'BOOLEAN NOT NULL DEFAULT 0',
    'guardian_signature_date': "TEXT NOT NULL DEFAULT ''",
    'alleva_is_active': 'BOOLEAN NOT NULL DEFAULT 1',
    'alleva_is_complete': 'BOOLEAN NOT NULL DEFAULT 0',
    'alleva_is_initial_tp': 'BOOLEAN NOT NULL DEFAULT 0',
    'alleva_start_date': "TEXT NOT NULL DEFAULT ''",
    'alleva_end_date': "TEXT NOT NULL DEFAULT ''",
    'alleva_last_modified': "TEXT NOT NULL DEFAULT ''",
    'detail_fetched': 'BOOLEAN NOT NULL DEFAULT 0',
    'detail_fetched_at': 'TEXT',
    'content_source': "TEXT NOT NULL DEFAULT 'collection'",
    'content_items_json': "TEXT NOT NULL DEFAULT '[]'",
    'content_capture_status': "TEXT NOT NULL DEFAULT 'counts_only'",
    'content_capture_warnings': "TEXT NOT NULL DEFAULT ''",
    'alleva_lead_id': "TEXT NOT NULL DEFAULT ''",
    'alleva_client_id': "TEXT NOT NULL DEFAULT ''",
    'alleva_unique_id': "TEXT NOT NULL DEFAULT ''",
    'alleva_mrn': "TEXT NOT NULL DEFAULT ''",
    'alleva_source_id': "TEXT NOT NULL DEFAULT ''",
    'id_join_confidence': "TEXT NOT NULL DEFAULT 'unknown'",
    'id_join_warnings': "TEXT NOT NULL DEFAULT ''",
    'data_quality_warnings': "TEXT NOT NULL DEFAULT ''",
    'discharge_conflict': 'BOOLEAN NOT NULL DEFAULT 0',
    'current_plan_record_id': 'INTEGER',
}

SQLITE_RETIRED_AUDIT_LOG_COLUMNS = {'fhir_audit_event'}

SQLITE_AUDIT_LOG_CANONICAL_COLUMNS: tuple[tuple[str, str, str | None], ...] = (
    ('id', 'INTEGER PRIMARY KEY', None),
    ('event_id', "TEXT UNIQUE NOT NULL DEFAULT ''", "''"),
    ('timestamp_utc', 'TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP', 'CURRENT_TIMESTAMP'),
    ('actor_id', 'INTEGER', None),
    ('actor_username', 'TEXT', None),
    ('actor_role', 'TEXT', None),
    ('actor_type', "TEXT NOT NULL DEFAULT 'human'", "'human'"),
    ('source_ip', 'TEXT', None),
    ('forwarded_for', 'TEXT', None),
    ('source_host', 'TEXT', None),
    ('source_port', 'INTEGER', None),
    ('user_agent', 'TEXT', None),
    ('request_id', "TEXT NOT NULL DEFAULT 'no-request-id'", "'no-request-id'"),
    ('correlation_id', "TEXT NOT NULL DEFAULT 'no-correlation-id'", "'no-correlation-id'"),
    ('session_id', 'TEXT', None),
    ('http_method', 'TEXT', None),
    ('request_path', 'TEXT', None),
    ('route_template', 'TEXT', None),
    ('query_string', 'TEXT', None),
    ('http_status_code', 'INTEGER', None),
    ('event_category', "TEXT NOT NULL DEFAULT 'application'", "'application'"),
    ('action', "TEXT NOT NULL DEFAULT 'application.event'", "'application.event'"),
    ('target_entity', 'TEXT', None),
    ('target_entity_type', 'TEXT', None),
    ('target_entity_id', 'TEXT', None),
    ('patient_id', 'TEXT', None),
    ('message', "TEXT NOT NULL DEFAULT ''", "''"),
    ('details', "TEXT NOT NULL DEFAULT ''", "''"),
    ('before_state', 'TEXT', None),
    ('after_state', 'TEXT', None),
    ('diff_state', 'TEXT', None),
    ('cef_version', 'INTEGER NOT NULL DEFAULT 0', '0'),
    ('cef_device_vendor', "TEXT NOT NULL DEFAULT 'OpenAI'", "'OpenAI'"),
    ('cef_device_product', "TEXT NOT NULL DEFAULT 'IZ Clinical Notes Analyzer'", "'IZ Clinical Notes Analyzer'"),
    ('cef_device_version', "TEXT NOT NULL DEFAULT '1'", "'1'"),
    ('cef_signature_id', "TEXT NOT NULL DEFAULT ''", "''"),
    ('cef_name', "TEXT NOT NULL DEFAULT ''", "''"),
    ('cef_severity', 'INTEGER NOT NULL DEFAULT 5', '5'),
    ('cef_extension', "TEXT NOT NULL DEFAULT ''", "''"),
    ('cef_payload', "TEXT NOT NULL DEFAULT ''", "''"),
    ('outcome_status', "TEXT NOT NULL DEFAULT 'success'", "'success'"),
    ('severity', "TEXT NOT NULL DEFAULT 'info'", "'info'"),
    ('prev_hash', 'TEXT', None),
    ('hash', "TEXT NOT NULL DEFAULT ''", "''"),
)


def _column_ddl(column_name: str, postgres_ddl: str, dialect_name: str) -> str:
    if dialect_name == 'sqlite':
        return SQLITE_COLUMN_DEFS.get(column_name, postgres_ddl)
    return postgres_ddl


def _quote_sqlite_identifier(identifier: str) -> str:
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'


def _sqlite_table_info(connection, table_name: str) -> list[dict[str, object]]:
    rows = connection.execute(text(f'PRAGMA table_info({_quote_sqlite_identifier(table_name)})')).mappings().all()
    return [dict(row) for row in rows]


def _repair_sqlite_audit_log_retired_required_columns(connection) -> list[str]:
    table_info = _sqlite_table_info(connection, 'audit_logs')
    blocking_columns = [
        str(column['name'])
        for column in table_info
        if str(column['name']) in SQLITE_RETIRED_AUDIT_LOG_COLUMNS and int(column.get('notnull') or 0) and column.get('dflt_value') is None
    ]
    if not blocking_columns:
        return []

    existing_columns = {str(column['name']) for column in table_info}
    temp_table = 'audit_logs_schema_compat'
    column_defs = ', '.join(f'{_quote_sqlite_identifier(name)} {ddl}' for name, ddl, _default_sql in SQLITE_AUDIT_LOG_CANONICAL_COLUMNS)
    insert_columns: list[str] = []
    select_expressions: list[str] = []
    for name, _ddl, default_sql in SQLITE_AUDIT_LOG_CANONICAL_COLUMNS:
        quoted_name = _quote_sqlite_identifier(name)
        insert_columns.append(quoted_name)
        if name not in existing_columns:
            select_expressions.append(default_sql or 'NULL')
        elif default_sql is None:
            select_expressions.append(quoted_name)
        else:
            select_expressions.append(f'COALESCE({quoted_name}, {default_sql})')

    logger.warning(
        'Detected legacy audit_logs retired required column(s): %s. Rebuilding audit_logs without retired FHIR columns.',
        ', '.join(blocking_columns),
    )
    connection.execute(text(f'DROP TABLE IF EXISTS {_quote_sqlite_identifier(temp_table)}'))
    connection.execute(text(f'CREATE TABLE {_quote_sqlite_identifier(temp_table)} ({column_defs})'))
    connection.execute(
        text(
            f'INSERT INTO {_quote_sqlite_identifier(temp_table)} ({", ".join(insert_columns)}) '
            f'SELECT {", ".join(select_expressions)} FROM audit_logs ORDER BY id'
        )
    )
    connection.execute(text('DROP TABLE audit_logs'))
    connection.execute(text(f'ALTER TABLE {_quote_sqlite_identifier(temp_table)} RENAME TO audit_logs'))
    return blocking_columns


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

        if inspector.has_table('audit_logs') and dialect_name == 'sqlite':
            removed_columns = _repair_sqlite_audit_log_retired_required_columns(connection)
            if removed_columns:
                added_columns.append({'table': 'audit_logs', 'column': f'retired columns removed: {", ".join(removed_columns)}'})

        if inspector.has_table('app_settings') and dialect_name == 'postgresql':
            connection.execute(text('ALTER TABLE app_settings ALTER COLUMN api_client_secret TYPE VARCHAR(1024)'))

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
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action)'))
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_request_id ON audit_logs(request_id)'))
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_correlation_id ON audit_logs(correlation_id)'))
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_event_category ON audit_logs(event_category)'))
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_patient_id ON audit_logs(patient_id)'))
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_hash ON audit_logs(hash)'))
            elif dialect_name == 'sqlite':
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_event_id ON audit_logs(event_id)'))
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action)'))
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_request_id ON audit_logs(request_id)'))
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_correlation_id ON audit_logs(correlation_id)'))
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_event_category ON audit_logs(event_category)'))
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_patient_id ON audit_logs(patient_id)'))
                connection.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_hash ON audit_logs(hash)'))

        if inspector.has_table('treatment_plan_clients'):
            connection.execute(text('CREATE INDEX IF NOT EXISTS idx_treatment_plan_clients_current_plan ON treatment_plan_clients(current_plan_record_id)'))

    return added_columns
