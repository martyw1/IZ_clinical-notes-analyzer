#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic"]
# ///
# How to run: the approved marker-owned office-manager harness invokes
# backend/.venv/Scripts/python.exe backend/tests/office_manager_source_snapshot.py
# CONTRACT_PATH RUN_ID SOURCE_FILE_ID [SOURCE_FILE_ID ...].
# Uses the already installed backend environment; do not install or upgrade.
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class Contract(FrozenModel):
    run_id: str = Field(min_length=1)
    physical_data_dir: Path


class Marker(FrozenModel):
    runId: str = Field(min_length=1)
    dataDir: Path


class ProbeRequest(FrozenModel):
    contract_path: Path
    run_id: str = Field(min_length=1)
    source_ids: tuple[str, ...] = Field(min_length=1, max_length=8)


@dataclass(frozen=True, slots=True)
class SnapshotFailure(Exception):
    code: str

    def __str__(self) -> str:
        return self.code


class SourceSnapshot(FrozenModel):
    source_document_id: int = Field(gt=0)
    source_file_id: str
    patient_record_id: int = Field(gt=0)
    first_plan_version_id: int | None
    first_review_version_id: int | None
    source_kind: str
    sha256: str
    created_at: str
    created_by_user_id: int
    encrypted_relative_path: Path = Field(exclude=True)
    relative_path_sha256: str
    ciphertext_sha256: str
    ciphertext_size: int


class MembershipSnapshot(FrozenModel):
    source_document_id: int = Field(gt=0)
    plan_version_id: int = Field(gt=0)
    attached_at: str
    attached_by_user_id: int | None
    detached_at: str | None
    detached_by_user_id: int | None


class SchemaFingerprint(FrozenModel):
    version: int = Field(gt=0)
    checksum_sha256: str


class ArchiveSnapshot(FrozenModel):
    read_only: bool
    ownership_verified: bool
    sources: tuple[SourceSnapshot, ...]
    memberships: tuple[MembershipSnapshot, ...]
    schema_history: tuple[SchemaFingerprint, ...]
    integrity_ok: bool
    foreign_key_violation_count: int


SOURCE_COLUMNS: Final = (
    "id AS source_document_id,document_id AS source_file_id,patient_id AS patient_record_id,"
    "plan_version_id AS first_plan_version_id,review_version_id AS first_review_version_id,"
    "source_kind,sha256,created_at,created_by_user_id,encrypted_relative_path"
)
MEMBERSHIP_COLUMNS: Final = (
    "source_document_id,plan_version_id,attached_at,attached_by_user_id,detached_at,detached_by_user_id"
)


def owned_runtime(request: ProbeRequest) -> Path:
    """Resolve the live contract and run marker before opening a database."""
    contract_path = request.contract_path.resolve(strict=True)
    contract = Contract.model_validate_json(contract_path.read_text(encoding="utf-8"))
    root = contract.physical_data_dir.resolve(strict=True)
    permitted_root = (Path(os.environ["LOCALAPPDATA"]) / "IZ-CNA-OfficeManager-Smoke").resolve(strict=True)
    if root.parent != permitted_root or contract_path.parent != root or contract_path.name != "fixture-contract.json":
        raise SnapshotFailure("UNOWNED_RUNTIME")
    marker_path = (root / "owner.json").resolve(strict=True)
    if marker_path.parent != root:
        raise SnapshotFailure("UNOWNED_MARKER")
    marker = Marker.model_validate_json(marker_path.read_text(encoding="utf-8"))
    if contract.run_id != request.run_id or marker.runId != request.run_id or marker.dataDir.resolve(strict=True) != root:
        raise SnapshotFailure("RUN_MARKER_MISMATCH")
    if len(set(request.source_ids)) != len(request.source_ids):
        raise SnapshotFailure("DUPLICATE_SOURCE_SELECTOR")
    if any(re.fullmatch(r"[A-Za-z0-9-]{1,128}", source_id) is None for source_id in request.source_ids):
        raise SnapshotFailure("INVALID_SOURCE_SELECTOR")
    return root


def source_snapshot(connection: sqlite3.Connection, source_id: str, root: Path) -> SourceSnapshot:
    """Hash one exact archived source without decrypting or emitting its path."""
    row = connection.execute(
        f"SELECT {SOURCE_COLUMNS} FROM source_documents WHERE document_id=?", (source_id,),
    ).fetchone()
    if row is None:
        raise SnapshotFailure("SOURCE_NOT_FOUND")
    relative = Path(str(row["encrypted_relative_path"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise SnapshotFailure("UNSAFE_SOURCE_PATH")
    physical = (root / relative).resolve(strict=True)
    if not physical.is_relative_to(root):
        raise SnapshotFailure("UNOWNED_SOURCE_PATH")
    with physical.open("rb") as archived:
        ciphertext_sha256 = hashlib.file_digest(archived, "sha256").hexdigest()
    return SourceSnapshot.model_validate({
        **dict(row),
        "relative_path_sha256": hashlib.sha256(str(row["encrypted_relative_path"]).encode()).hexdigest(),
        "ciphertext_sha256": ciphertext_sha256,
        "ciphertext_size": physical.stat().st_size,
    })


def take_snapshot(request: ProbeRequest) -> ArchiveSnapshot:
    """Read only allowed source, membership, and schema fields from the owned DB."""
    root = owned_runtime(request)
    database = (root / "clinical-notes-analyzer-v2.sqlite3").resolve(strict=True)
    if database.parent != root:
        raise SnapshotFailure("UNOWNED_DATABASE")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=5)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        sources = tuple(source_snapshot(connection, source_id, root) for source_id in request.source_ids)
        source_rows = tuple(source.source_document_id for source in sources)
        placeholders = ",".join("?" for _source in source_rows)
        memberships = tuple(MembershipSnapshot.model_validate(dict(row)) for row in connection.execute(
            f"SELECT {MEMBERSHIP_COLUMNS} FROM source_document_plan_memberships "
            f"WHERE source_document_id IN ({placeholders}) ORDER BY source_document_id,plan_version_id",
            source_rows,
        ))
        schema = tuple(SchemaFingerprint.model_validate(dict(row)) for row in connection.execute(
            "SELECT version,checksum_sha256 FROM schema_migrations ORDER BY version",
        ))
        return ArchiveSnapshot(
            read_only=connection.execute("PRAGMA query_only").fetchone()[0] == 1,
            ownership_verified=True, sources=sources, memberships=memberships, schema_history=schema,
            integrity_ok=connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok",
            foreign_key_violation_count=len(connection.execute("PRAGMA foreign_key_check").fetchall()),
        )


def main() -> int:
    """Emit a safe snapshot or a value-free CLI error; never print raw exceptions."""
    try:
        if len(sys.argv) < 4:
            raise SnapshotFailure("EXPECTED_CONTRACT_RUN_AND_SOURCE_IDS")
        request = ProbeRequest(contract_path=Path(sys.argv[1]), run_id=sys.argv[2], source_ids=tuple(sys.argv[3:]))
        print(take_snapshot(request).model_dump_json())
        return 0
    except Exception as error:  # noqa: BROAD_EXCEPT_OK - CLI boundary emits type only, not values or traceback.
        print(json.dumps({"status": "failed", "error_type": type(error).__name__, "values_omitted": True}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
