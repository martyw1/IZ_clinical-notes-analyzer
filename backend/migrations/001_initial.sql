-- Initial schema migration for Chart Review Workflow.
-- Use with psql against PostgreSQL for deterministic setup in VPS environments.

CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  username VARCHAR(80) UNIQUE NOT NULL,
  full_name VARCHAR(120) NOT NULL DEFAULT '',
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(20) NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  must_reset_password BOOLEAN NOT NULL DEFAULT TRUE,
  failed_login_attempts INTEGER NOT NULL DEFAULT 0,
  is_locked BOOLEAN NOT NULL DEFAULT FALSE,
  last_login_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app_settings (
  id SERIAL PRIMARY KEY,
  organization_name VARCHAR(120) NOT NULL DEFAULT 'R3 Recovery Services',
  access_intel_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  access_geo_lookup_url VARCHAR(255) NOT NULL DEFAULT 'https://ipwho.is/{ip}',
  access_reputation_url VARCHAR(255) NOT NULL DEFAULT 'https://api.abuseipdb.com/api/v2/check',
  access_reputation_api_key VARCHAR(255) NOT NULL DEFAULT '',
  access_lookup_timeout_seconds INTEGER NOT NULL DEFAULT 4,
  llm_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  llm_provider_name VARCHAR(80) NOT NULL DEFAULT 'OpenAI-compatible',
  llm_base_url VARCHAR(255) NOT NULL DEFAULT 'https://api.openai.com/v1',
  llm_model VARCHAR(120) NOT NULL DEFAULT 'gpt-4.1-mini',
  llm_api_key VARCHAR(255) NOT NULL DEFAULT '',
  llm_use_for_access_review BOOLEAN NOT NULL DEFAULT TRUE,
  llm_use_for_evaluation_gap_analysis BOOLEAN NOT NULL DEFAULT TRUE,
  llm_analysis_instructions TEXT NOT NULL DEFAULT '',
  updated_by_id INTEGER REFERENCES users(id),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS charts (
  id SERIAL PRIMARY KEY,
  source_note_set_id INTEGER,
  patient_id VARCHAR(120) NOT NULL DEFAULT '',
  client_name VARCHAR(120) NOT NULL,
  level_of_care VARCHAR(120) NOT NULL,
  admission_date VARCHAR(40) NOT NULL DEFAULT '',
  discharge_date VARCHAR(40) NOT NULL DEFAULT '',
  primary_clinician VARCHAR(120) NOT NULL,
  auditor_name VARCHAR(120) NOT NULL DEFAULT '',
  other_details TEXT NOT NULL DEFAULT '',
  counselor_id INTEGER NOT NULL REFERENCES users(id),
  state VARCHAR(40) NOT NULL DEFAULT 'Draft',
  system_score INTEGER NOT NULL DEFAULT 0,
  system_summary TEXT NOT NULL DEFAULT '',
  manager_comment TEXT NOT NULL DEFAULT '',
  reviewed_by_id INTEGER REFERENCES users(id),
  system_generated_at TIMESTAMPTZ,
  reviewed_at TIMESTAMPTZ,
  notes TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS patient_note_sets (
  id SERIAL PRIMARY KEY,
  patient_id VARCHAR(120) NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  status VARCHAR(20) NOT NULL DEFAULT 'active',
  upload_mode VARCHAR(20) NOT NULL DEFAULT 'initial',
  source_system VARCHAR(80) NOT NULL DEFAULT 'Alleva EMR',
  primary_clinician VARCHAR(120) NOT NULL DEFAULT '',
  level_of_care VARCHAR(120) NOT NULL DEFAULT '',
  admission_date VARCHAR(40) NOT NULL DEFAULT '',
  discharge_date VARCHAR(40) NOT NULL DEFAULT '',
  upload_notes TEXT NOT NULL DEFAULT '',
  replaced_note_set_id INTEGER REFERENCES patient_note_sets(id),
  uploaded_by_id INTEGER NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_patient_note_sets_patient_version UNIQUE (patient_id, version)
);

CREATE TABLE IF NOT EXISTS patient_note_documents (
  id SERIAL PRIMARY KEY,
  note_set_id INTEGER NOT NULL REFERENCES patient_note_sets(id),
  document_label VARCHAR(255) NOT NULL,
  original_filename VARCHAR(255) NOT NULL,
  storage_path VARCHAR(255) NOT NULL,
  content_type VARCHAR(120) NOT NULL DEFAULT 'application/octet-stream',
  size_bytes INTEGER NOT NULL DEFAULT 0,
  sha256 VARCHAR(64) NOT NULL,
  alleva_bucket VARCHAR(40) NOT NULL DEFAULT 'custom_forms',
  document_type VARCHAR(80) NOT NULL DEFAULT 'clinical_note',
  completion_status VARCHAR(20) NOT NULL DEFAULT 'completed',
  client_signed BOOLEAN NOT NULL DEFAULT FALSE,
  staff_signed BOOLEAN NOT NULL DEFAULT FALSE,
  document_date VARCHAR(40) NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_item_responses (
  id SERIAL PRIMARY KEY,
  chart_id INTEGER NOT NULL REFERENCES charts(id),
  item_key VARCHAR(80) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  notes TEXT NOT NULL DEFAULT '',
  evidence_location VARCHAR(255) NOT NULL DEFAULT '',
  evidence_date VARCHAR(80) NOT NULL DEFAULT '',
  expiration_date VARCHAR(80) NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_chart_audit_item_key UNIQUE (chart_id, item_key)
);

CREATE TABLE IF NOT EXISTS workflow_transitions (
  id SERIAL PRIMARY KEY,
  chart_id INTEGER NOT NULL REFERENCES charts(id),
  actor_id INTEGER NOT NULL REFERENCES users(id),
  from_state VARCHAR(64) NOT NULL,
  to_state VARCHAR(64) NOT NULL,
  comment TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id SERIAL PRIMARY KEY,
  event_id VARCHAR(64) UNIQUE NOT NULL,
  timestamp_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  actor_id INTEGER REFERENCES users(id),
  actor_username VARCHAR(80),
  actor_role VARCHAR(40),
  actor_type VARCHAR(20) NOT NULL DEFAULT 'human',
  source_ip VARCHAR(64),
  forwarded_for VARCHAR(255),
  source_host VARCHAR(255),
  source_port INTEGER,
  user_agent VARCHAR(255),
  request_id VARCHAR(64) NOT NULL,
  correlation_id VARCHAR(64) NOT NULL,
  session_id VARCHAR(128),
  http_method VARCHAR(16),
  request_path VARCHAR(255),
  route_template VARCHAR(255),
  query_string TEXT,
  http_status_code INTEGER,
  event_category VARCHAR(40) NOT NULL,
  action VARCHAR(120) NOT NULL,
  target_entity VARCHAR(120),
  target_entity_type VARCHAR(80),
  target_entity_id VARCHAR(80),
  patient_id VARCHAR(120),
  message TEXT NOT NULL DEFAULT '',
  details TEXT NOT NULL DEFAULT '',
  before_state TEXT,
  after_state TEXT,
  diff_state TEXT,
  cef_version INTEGER NOT NULL DEFAULT 0,
  cef_device_vendor VARCHAR(80) NOT NULL DEFAULT 'OpenAI',
  cef_device_product VARCHAR(120) NOT NULL DEFAULT 'IZ Clinical Notes Analyzer',
  cef_device_version VARCHAR(40) NOT NULL DEFAULT '1',
  cef_signature_id VARCHAR(120) NOT NULL DEFAULT '',
  cef_name VARCHAR(255) NOT NULL DEFAULT '',
  cef_severity INTEGER NOT NULL DEFAULT 5,
  cef_extension TEXT NOT NULL DEFAULT '',
  cef_payload TEXT NOT NULL DEFAULT '',
  fhir_audit_event TEXT NOT NULL DEFAULT '',
  outcome_status VARCHAR(20) NOT NULL DEFAULT 'success',
  severity VARCHAR(20) NOT NULL DEFAULT 'info',
  prev_hash VARCHAR(128),
  hash VARCHAR(128) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_charts_patient_id ON charts(patient_id);
CREATE INDEX IF NOT EXISTS idx_charts_source_note_set_id ON charts(source_note_set_id);
CREATE INDEX IF NOT EXISTS idx_charts_state ON charts(state);
CREATE INDEX IF NOT EXISTS idx_audit_item_responses_chart_id ON audit_item_responses(chart_id);
CREATE INDEX IF NOT EXISTS idx_audit_item_responses_item_key ON audit_item_responses(item_key);
CREATE INDEX IF NOT EXISTS idx_patient_note_sets_patient_id ON patient_note_sets(patient_id);
CREATE INDEX IF NOT EXISTS idx_patient_note_sets_status ON patient_note_sets(status);
CREATE INDEX IF NOT EXISTS idx_patient_note_documents_note_set_id ON patient_note_documents(note_set_id);
CREATE INDEX IF NOT EXISTS idx_patient_note_documents_sha256 ON patient_note_documents(sha256);
CREATE INDEX IF NOT EXISTS idx_audit_event_id ON audit_logs(event_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_request_id ON audit_logs(request_id);
CREATE INDEX IF NOT EXISTS idx_audit_correlation_id ON audit_logs(correlation_id);
CREATE INDEX IF NOT EXISTS idx_audit_event_category ON audit_logs(event_category);
CREATE INDEX IF NOT EXISTS idx_audit_patient_id ON audit_logs(patient_id);
