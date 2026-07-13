from __future__ import annotations

CORE_STATEMENTS = (
    """CREATE TABLE schema_migrations(
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        checksum_sha256 TEXT NOT NULL,
        applied_at TEXT NOT NULL,
        app_build TEXT NOT NULL
    )""",
    """CREATE TABLE facilities(
        id INTEGER PRIMARY KEY,
        facility_key TEXT UNIQUE NOT NULL,
        display_name TEXT NOT NULL,
        timezone TEXT NOT NULL,
        is_active INTEGER NOT NULL CHECK(is_active IN (0,1)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE user_facilities(
        user_id INTEGER NOT NULL REFERENCES users(id) ON UPDATE RESTRICT ON DELETE CASCADE,
        facility_id INTEGER NOT NULL REFERENCES facilities(id) ON UPDATE RESTRICT ON DELETE CASCADE,
        assigned_by_user_id INTEGER NOT NULL REFERENCES users(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        assigned_at TEXT NOT NULL,
        PRIMARY KEY(user_id, facility_id)
    )""",
    """CREATE TABLE patients(
        id INTEGER PRIMARY KEY,
        facility_id INTEGER NOT NULL REFERENCES facilities(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        canonical_client_id TEXT NOT NULL,
        source_system TEXT NOT NULL,
        lifecycle_state TEXT NOT NULL,
        first_seen_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        reconciled_at TEXT NULL,
        UNIQUE(facility_id, source_system, canonical_client_id)
    )""",
    """CREATE TABLE patient_assignments(
        patient_id INTEGER NOT NULL REFERENCES patients(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        counselor_user_id INTEGER NOT NULL REFERENCES users(id) ON UPDATE RESTRICT ON DELETE CASCADE,
        assigned_by_user_id INTEGER NOT NULL REFERENCES users(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        assigned_at TEXT NOT NULL,
        ended_at TEXT NULL,
        is_active INTEGER NOT NULL CHECK(is_active IN (0,1)),
        PRIMARY KEY(patient_id, counselor_user_id, assigned_at)
    )""",
    "CREATE UNIQUE INDEX uq_patient_assignments_active ON patient_assignments(patient_id,counselor_user_id) WHERE is_active=1",
    """CREATE TABLE loc_history(
        id INTEGER PRIMARY KEY,
        patient_id INTEGER NOT NULL REFERENCES patients(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        loc_code TEXT NOT NULL,
        source_system TEXT NOT NULL,
        source_record_id TEXT NOT NULL,
        effective_date TEXT NOT NULL,
        recorded_at TEXT NOT NULL,
        reconciliation_state TEXT NOT NULL,
        evidence_sha256 TEXT NOT NULL,
        UNIQUE(patient_id,source_system,source_record_id,effective_date,evidence_sha256)
    )""",
)

USER_EXTENSIONS = (
    ("auth_state", "TEXT NOT NULL DEFAULT 'active'"),
    ("locked_until", "TEXT NULL"),
    ("password_changed_at", "TEXT NULL"),
    ("recovery_required", "INTEGER NOT NULL DEFAULT 0 CHECK(recovery_required IN (0,1))"),
)

APP_SETTING_NORMALIZED_EXTENSIONS = (
    ("api_base_url", "VARCHAR(500) NOT NULL DEFAULT 'https://api.allevasoft.com'"),
    ("openapi_url", "VARCHAR(500) NOT NULL DEFAULT 'https://api.allevasoft.com/swagger/v1/swagger.json'"),
    ("api_scopes", "VARCHAR(500) NOT NULL DEFAULT ''"),
    ("api_pagination_limit", "INTEGER NOT NULL DEFAULT 100"),
)

APP_SETTING_EXTENSIONS = (
    *APP_SETTING_NORMALIZED_EXTENSIONS,
    ("alleva_treatment_plan_sync_enabled", "BOOLEAN NOT NULL DEFAULT 0"),
    ("alleva_treatment_plan_sync_approved", "BOOLEAN NOT NULL DEFAULT 0"),
    ("alleva_treatment_plan_endpoint_mapping_validated", "BOOLEAN NOT NULL DEFAULT 0"),
)

APP_SETTING_LEGACY_SOURCES = (
    ("api_base_url", "alleva_api_base_url"),
    ("openapi_url", "alleva_openapi_url"),
)
