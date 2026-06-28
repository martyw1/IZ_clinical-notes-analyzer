-- Add Alleva treatment-plan aggregate fields.
-- Runtime desktop installs are also protected by backend/app/db/bootstrap.py.

ALTER TABLE treatment_plan_records ADD COLUMN problem_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE treatment_plan_records ADD COLUMN diagnosis_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE treatment_plan_records ADD COLUMN goal_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE treatment_plan_records ADD COLUMN objective_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE treatment_plan_records ADD COLUMN intervention_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE treatment_plan_records ADD COLUMN has_guardian_signature BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE treatment_plan_records ADD COLUMN guardian_signature_date VARCHAR(40) NOT NULL DEFAULT '';
ALTER TABLE treatment_plan_records ADD COLUMN alleva_is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE treatment_plan_records ADD COLUMN alleva_is_complete BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE treatment_plan_records ADD COLUMN alleva_is_initial_tp BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE treatment_plan_records ADD COLUMN alleva_start_date VARCHAR(40) NOT NULL DEFAULT '';
ALTER TABLE treatment_plan_records ADD COLUMN alleva_end_date VARCHAR(40) NOT NULL DEFAULT '';
ALTER TABLE treatment_plan_records ADD COLUMN alleva_last_modified VARCHAR(40) NOT NULL DEFAULT '';
ALTER TABLE treatment_plan_records ADD COLUMN detail_fetched BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE treatment_plan_records ADD COLUMN detail_fetched_at DATETIME;
ALTER TABLE treatment_plan_records ADD COLUMN content_source VARCHAR(40) NOT NULL DEFAULT 'collection';

ALTER TABLE treatment_plan_clients ADD COLUMN alleva_lead_id VARCHAR(120) NOT NULL DEFAULT '';
ALTER TABLE treatment_plan_clients ADD COLUMN alleva_client_id VARCHAR(120) NOT NULL DEFAULT '';
ALTER TABLE treatment_plan_clients ADD COLUMN alleva_unique_id VARCHAR(120) NOT NULL DEFAULT '';
ALTER TABLE treatment_plan_clients ADD COLUMN alleva_mrn VARCHAR(120) NOT NULL DEFAULT '';
ALTER TABLE treatment_plan_clients ADD COLUMN alleva_source_id VARCHAR(120) NOT NULL DEFAULT '';
ALTER TABLE treatment_plan_clients ADD COLUMN id_join_confidence VARCHAR(40) NOT NULL DEFAULT 'unknown';
ALTER TABLE treatment_plan_clients ADD COLUMN id_join_warnings TEXT NOT NULL DEFAULT '';
ALTER TABLE treatment_plan_clients ADD COLUMN data_quality_warnings TEXT NOT NULL DEFAULT '';
ALTER TABLE treatment_plan_clients ADD COLUMN discharge_conflict BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE treatment_plan_clients ADD COLUMN current_plan_record_id INTEGER REFERENCES treatment_plan_records(id);

ALTER TABLE app_settings ADD COLUMN alleva_treatment_plan_detail_fetch_enabled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE app_settings ADD COLUMN alleva_treatment_plan_name_join_fallback_enabled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE app_settings ADD COLUMN alleva_treatment_plan_detail_fetch_limit INTEGER NOT NULL DEFAULT 50;

CREATE INDEX IF NOT EXISTS idx_treatment_plan_clients_current_plan ON treatment_plan_clients(current_plan_record_id);
