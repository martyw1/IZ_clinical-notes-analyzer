from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.v2.migrations.schema_clinical import CLINICAL_STATEMENTS
from app.v2.migrations.schema_core import APP_SETTING_NORMALIZED_EXTENSIONS, CORE_STATEMENTS, USER_EXTENSIONS
from app.v2.migrations.schema_evaluation_ledger import EVALUATION_LEDGER_STATEMENTS
from app.v2.migrations.schema_hardening import HARDENING_STATEMENTS
from app.v2.migrations.schema_patient_identity import PATIENT_IDENTITY_STATEMENTS
from app.v2.migrations.schema_patient_snapshots import PATIENT_SNAPSHOT_STATEMENTS
from app.v2.migrations.schema_sync import SYNC_STATEMENTS
from app.v2.migrations.schema_sync_provenance import SYNC_PROVENANCE_STATEMENTS
from app.v2.migrations.schema_workflow import WORKFLOW_STATEMENTS


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]
    checksum_sha256: str


def _migration(version: int, name: str, statements: tuple[str, ...]) -> Migration:
    extension_sql = tuple(f"ALTER TABLE users ADD COLUMN {name} {definition}" for name, definition in USER_EXTENSIONS)
    canonical = "\n".join((*extension_sql, *statements)).encode("utf-8")
    return Migration(version=version, name=name, statements=statements, checksum_sha256=hashlib.sha256(canonical).hexdigest())


MIGRATIONS = (
    _migration(
        1,
        "immutable_v2_clinical_foundation",
        (*CORE_STATEMENTS, *CLINICAL_STATEMENTS, *WORKFLOW_STATEMENTS, *SYNC_STATEMENTS),
    ),
    _migration(2, "verify_and_harden_v2_clinical_foundation", HARDENING_STATEMENTS),
    _migration(3, "append_only_evaluation_ledger", EVALUATION_LEDGER_STATEMENTS),
    _migration(4, "sync_checkpoint_recovery_and_provenance", SYNC_PROVENANCE_STATEMENTS),
    _migration(
        5,
        "normalize_legacy_api_settings",
        tuple(
            f"ALTER TABLE app_settings ADD COLUMN {name} {definition}"
            for name, definition in APP_SETTING_NORMALIZED_EXTENSIONS
        ),
    ),
    _migration(
        6,
        "add_api_request_rate_ceiling",
        (),
    ),
    _migration(
        7,
        "persist_alleva_protocol_and_legacy_settings_migration_state",
        (),
    ),
    _migration(8, "separate_alleva_mrn_from_source_patient_id", PATIENT_IDENTITY_STATEMENTS),
    _migration(9, "append_only_encrypted_patient_snapshots", PATIENT_SNAPSHOT_STATEMENTS),
)

APP_SETTINGS_MIGRATION_VERSION = 5
LATEST_SCHEMA_VERSION = MIGRATIONS[-1].version
