from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.v2.migrations.schema_clinical import CLINICAL_STATEMENTS
from app.v2.migrations.schema_core import CORE_STATEMENTS, USER_EXTENSIONS
from app.v2.migrations.schema_evaluation_ledger import EVALUATION_LEDGER_STATEMENTS
from app.v2.migrations.schema_hardening import HARDENING_STATEMENTS
from app.v2.migrations.schema_sync import SYNC_STATEMENTS
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
)

LATEST_SCHEMA_VERSION = MIGRATIONS[-1].version
