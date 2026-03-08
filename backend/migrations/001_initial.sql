-- Initial schema migration for Chart Review Workflow.
-- Use with psql against PostgreSQL for deterministic setup in VPS environments.

CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  username VARCHAR(80) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(20) NOT NULL,
  must_reset_password BOOLEAN NOT NULL DEFAULT TRUE,
  failed_login_attempts INTEGER NOT NULL DEFAULT 0,
  is_locked BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS charts (
  id SERIAL PRIMARY KEY,
  client_name VARCHAR(120) NOT NULL,
  level_of_care VARCHAR(120) NOT NULL,
  admission_date VARCHAR(40) NOT NULL DEFAULT '',
  discharge_date VARCHAR(40) NOT NULL DEFAULT '',
  primary_clinician VARCHAR(120) NOT NULL,
  auditor_name VARCHAR(120) NOT NULL DEFAULT '',
  other_details TEXT NOT NULL DEFAULT '',
  counselor_id INTEGER NOT NULL REFERENCES users(id),
  state VARCHAR(40) NOT NULL DEFAULT 'Draft',
  notes TEXT NOT NULL DEFAULT '',
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
  timestamp_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  actor_id INTEGER REFERENCES users(id),
  actor_username VARCHAR(80),
  actor_role VARCHAR(40),
  source_ip VARCHAR(64),
  user_agent VARCHAR(255),
  request_id VARCHAR(64) NOT NULL,
  action VARCHAR(120) NOT NULL,
  target_entity VARCHAR(120),
  details TEXT NOT NULL DEFAULT '',
  outcome_status VARCHAR(20) NOT NULL DEFAULT 'success',
  severity VARCHAR(20) NOT NULL DEFAULT 'info',
  prev_hash VARCHAR(128),
  hash VARCHAR(128) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_charts_state ON charts(state);
CREATE INDEX IF NOT EXISTS idx_audit_item_responses_chart_id ON audit_item_responses(chart_id);
CREATE INDEX IF NOT EXISTS idx_audit_item_responses_item_key ON audit_item_responses(item_key);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_request_id ON audit_logs(request_id);
