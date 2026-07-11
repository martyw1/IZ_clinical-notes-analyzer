from __future__ import annotations

HARDENING_STATEMENTS = (
    """CREATE TABLE migration_reconciliation(
        migration_version INTEGER NOT NULL,
        category TEXT NOT NULL,
        source_count INTEGER NOT NULL CHECK(source_count >= 0),
        target_count INTEGER NOT NULL CHECK(target_count >= 0),
        source_sha256 TEXT NOT NULL,
        target_sha256 TEXT NOT NULL,
        verified_at TEXT NOT NULL,
        PRIMARY KEY(migration_version,category)
    )""",
    """CREATE TRIGGER app_settings_boolean_insert_check BEFORE INSERT ON app_settings
        WHEN NEW.treatment_plan_loc_change_window_validated NOT IN (0,1)
            OR NEW.emr_api_enabled NOT IN (0,1) OR NEW.alleva_treatment_plan_sync_enabled NOT IN (0,1)
            OR NEW.alleva_treatment_plan_sync_approved NOT IN (0,1)
            OR NEW.alleva_treatment_plan_endpoint_mapping_validated NOT IN (0,1)
        BEGIN SELECT RAISE(ABORT,'invalid application-setting boolean'); END""",
    """CREATE TRIGGER api_harness_jobs_boolean_insert_check BEFORE INSERT ON api_harness_jobs
        WHEN NEW.raw_sensitive_mode_used NOT IN (0,1) OR NEW.cancel_requested NOT IN (0,1)
        BEGIN SELECT RAISE(ABORT,'invalid API job boolean'); END""",
    """CREATE TRIGGER api_harness_jobs_boolean_update_check BEFORE UPDATE OF raw_sensitive_mode_used,cancel_requested ON api_harness_jobs
        WHEN NEW.raw_sensitive_mode_used NOT IN (0,1) OR NEW.cancel_requested NOT IN (0,1)
        BEGIN SELECT RAISE(ABORT,'invalid API job boolean'); END""",
    """CREATE TRIGGER workflow_profiles_boolean_insert_check BEFORE INSERT ON workflow_profiles
        WHEN NEW.is_active NOT IN (0,1)
        BEGIN SELECT RAISE(ABORT,'invalid workflow-profile boolean'); END""",
    """CREATE TRIGGER workflow_profiles_boolean_update_check BEFORE UPDATE OF is_active ON workflow_profiles
        WHEN NEW.is_active NOT IN (0,1)
        BEGIN SELECT RAISE(ABORT,'invalid workflow-profile boolean'); END""",
)
