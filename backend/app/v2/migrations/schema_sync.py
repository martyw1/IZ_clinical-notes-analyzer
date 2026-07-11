from __future__ import annotations

SYNC_STATEMENTS = (
    """CREATE TABLE alleva_contract_approvals(
        id INTEGER PRIMARY KEY,
        contract_version TEXT NOT NULL UNIQUE,
        encrypted_contract_json BLOB NOT NULL,
        contract_sha256 TEXT NOT NULL,
        approver_user_id INTEGER NOT NULL REFERENCES users(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        approved_at TEXT NOT NULL,
        effective_at TEXT NOT NULL,
        expires_at TEXT NULL,
        revoked_at TEXT NULL
    )""",
    """CREATE TABLE sync_jobs(
        id INTEGER PRIMARY KEY,
        external_job_id TEXT NOT NULL UNIQUE,
        requested_by_user_id INTEGER NOT NULL REFERENCES users(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        approval_record_id INTEGER NOT NULL REFERENCES alleva_contract_approvals(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        status TEXT NOT NULL,
        idempotency_key TEXT NOT NULL UNIQUE,
        cancel_requested INTEGER NOT NULL CHECK(cancel_requested IN (0,1)),
        started_at TEXT NOT NULL,
        completed_at TEXT NULL,
        counters_json TEXT NOT NULL
    )""",
    """CREATE TABLE sync_checkpoints(
        id INTEGER PRIMARY KEY,
        job_id INTEGER NOT NULL REFERENCES sync_jobs(id) ON UPDATE RESTRICT ON DELETE CASCADE,
        endpoint_key TEXT NOT NULL,
        page_number INTEGER NOT NULL CHECK(page_number >= 0),
        cursor_hash TEXT NOT NULL,
        response_shape_sha256 TEXT NOT NULL,
        committed_at TEXT NOT NULL,
        UNIQUE(job_id,endpoint_key,page_number,cursor_hash)
    )""",
    """CREATE TABLE sync_failures(
        id INTEGER PRIMARY KEY,
        job_id INTEGER NOT NULL REFERENCES sync_jobs(id) ON UPDATE RESTRICT ON DELETE CASCADE,
        checkpoint_id INTEGER NULL REFERENCES sync_checkpoints(id) ON UPDATE RESTRICT ON DELETE CASCADE,
        error_class TEXT NOT NULL,
        safe_message TEXT NOT NULL,
        retryable INTEGER NOT NULL CHECK(retryable IN (0,1)),
        attempt INTEGER NOT NULL CHECK(attempt > 0),
        occurred_at TEXT NOT NULL
    )""",
    """CREATE TABLE reconciliation_outcomes(
        id INTEGER PRIMARY KEY,
        job_id INTEGER NOT NULL REFERENCES sync_jobs(id) ON UPDATE RESTRICT ON DELETE CASCADE,
        patient_id INTEGER NOT NULL REFERENCES patients(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        source_kind TEXT NOT NULL,
        source_record_id TEXT NOT NULL,
        outcome TEXT NOT NULL,
        evidence_sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(job_id,patient_id,source_kind,source_record_id)
    )""",
    """CREATE TRIGGER users_role_insert_check BEFORE INSERT ON users
        WHEN NEW.role NOT IN ('admin','office_manager','counselor','viewer')
        BEGIN SELECT RAISE(ABORT,'invalid canonical role'); END""",
    """CREATE TRIGGER users_role_update_check BEFORE UPDATE OF role ON users
        WHEN NEW.role NOT IN ('admin','office_manager','counselor','viewer')
        BEGIN SELECT RAISE(ABORT,'invalid canonical role'); END""",
    """CREATE TRIGGER users_boolean_insert_check BEFORE INSERT ON users
        WHEN NEW.is_active NOT IN (0,1) OR NEW.must_reset_password NOT IN (0,1)
            OR NEW.is_locked NOT IN (0,1) OR NEW.recovery_required NOT IN (0,1)
        BEGIN SELECT RAISE(ABORT,'invalid user boolean'); END""",
    """CREATE TRIGGER users_boolean_update_check BEFORE UPDATE OF is_active,must_reset_password,is_locked,recovery_required ON users
        WHEN NEW.is_active NOT IN (0,1) OR NEW.must_reset_password NOT IN (0,1)
            OR NEW.is_locked NOT IN (0,1) OR NEW.recovery_required NOT IN (0,1)
        BEGIN SELECT RAISE(ABORT,'invalid user boolean'); END""",
    """CREATE TRIGGER app_settings_boolean_update_check BEFORE UPDATE ON app_settings
        WHEN NEW.treatment_plan_loc_change_window_validated NOT IN (0,1)
            OR NEW.emr_api_enabled NOT IN (0,1) OR NEW.alleva_treatment_plan_sync_enabled NOT IN (0,1)
            OR NEW.alleva_treatment_plan_sync_approved NOT IN (0,1)
            OR NEW.alleva_treatment_plan_endpoint_mapping_validated NOT IN (0,1)
        BEGIN SELECT RAISE(ABORT,'invalid application-setting boolean'); END""",
)
