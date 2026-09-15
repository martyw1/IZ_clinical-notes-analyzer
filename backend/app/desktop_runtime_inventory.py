from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import ValidationError

from app.desktop_identity import (
    PRODUCT_ID,
    IdentityError,
    authorized_paths_equal,
    contained_path,
    root_path_hash_from_key,
    validated_path,
    windows_path_key,
)
from app.desktop_runtime_contracts import (
    FileRecord,
    InstallReceipt,
    MaintenanceJournal,
    ProgramInventory,
)
from app.desktop_runtime_errors import RuntimeAuthorityError


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise RuntimeAuthorityError("json_duplicate_key")
        result[name] = value
    return result


def _read_object(path: Path, reason: str) -> dict[str, object]:
    try:
        raw = path.read_bytes()
        if not raw or len(raw) > 1_048_576:
            raise RuntimeAuthorityError(reason)
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_object)
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeAuthorityError(reason) from exc
    except RuntimeAuthorityError as exc:
        raise RuntimeAuthorityError(reason) from exc
    if not isinstance(value, dict):
        raise RuntimeAuthorityError(reason)
    return value


def read_journal(path: Path) -> MaintenanceJournal:
    try:
        return MaintenanceJournal.model_validate(_read_object(path, "journal_invalid"))
    except ValidationError as exc:
        raise RuntimeAuthorityError("journal_invalid") from exc


def read_receipt(path: Path) -> InstallReceipt:
    try:
        return InstallReceipt.model_validate(_read_object(path, "install_receipt_invalid"))
    except ValidationError as exc:
        raise RuntimeAuthorityError("install_receipt_invalid") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_path(root: Path, value: str) -> Path:
    pure = PurePosixPath(value)
    if (
        not value
        or pure.is_absolute()
        or pure.as_posix() != value
        or any(part in ("", ".", "..") for part in pure.parts)
        or any(":" in part or "\\" in part for part in pure.parts)
    ):
        raise RuntimeAuthorityError("program_inventory_invalid")
    try:
        return contained_path(root, root.joinpath(*pure.parts), must_exist=True)
    except IdentityError as exc:
        raise RuntimeAuthorityError("program_inventory_mismatch") from exc


def _records_unique(records: Sequence[FileRecord]) -> None:
    paths: list[Path] = []
    for record in records:
        candidate = Path(*PurePosixPath(record.path).parts)
        if any(authorized_paths_equal(candidate, existing) for existing in paths):
            raise RuntimeAuthorityError("program_inventory_invalid")
        paths.append(candidate)


def validate_files(root: Path, records: Sequence[FileRecord], *, exact: bool) -> None:
    _records_unique(records)
    expected_paths: list[Path] = []
    runtime_recorded = False
    for record in records:
        path = _relative_path(root, record.path)
        if record.length < 0 or path.stat().st_size != record.length or _sha256(path) != record.sha256:
            raise RuntimeAuthorityError("program_inventory_mismatch")
        relative = Path(*PurePosixPath(record.path).parts)
        expected_paths.append(relative)
        runtime_recorded = runtime_recorded or authorized_paths_equal(
            relative, Path("runtime") / "IZClinicalNotesAnalyzer.exe"
        )
    if not runtime_recorded:
        raise RuntimeAuthorityError("program_inventory_invalid")
    if exact:
        actual = [
            path.relative_to(root)
            for path in root.rglob("*")
            if path.is_file() and path.name != ".iz-cna-owned-root.json"
        ]
        if len(actual) != len(expected_paths) or any(
            not any(authorized_paths_equal(path, expected) for expected in expected_paths) for path in actual
        ):
            raise RuntimeAuthorityError("program_inventory_mismatch")


def read_inventory(
    maintenance_root: Path,
    journal: MaintenanceJournal,
    role: Literal["stage", "previous"],
) -> ProgramInventory:
    transaction_root = maintenance_root / "transactions" / journal.transaction_id
    inventory_root = (
        maintenance_root.parent
        / "Programs"
        / f"IZ Clinical Notes Analyzer.{role}-{journal.transaction_id}"
    )
    expected_root_hash = root_path_hash_from_key(windows_path_key(inventory_root.resolve(strict=False)))
    program = journal.program
    relative = program.stage_inventory_relative_path if role == "stage" else program.previous_inventory_relative_path
    expected_hash = program.stage_inventory_sha256 if role == "stage" else program.previous_inventory_sha256
    expected_payload = program.stage_payload_identity if role == "stage" else program.previous_payload_identity
    if relative is None or expected_hash is None or expected_payload is None:
        raise RuntimeAuthorityError("program_inventory_invalid")
    path = _relative_path(validated_path(transaction_root, must_exist=True), relative)
    if _sha256(path) != expected_hash:
        raise RuntimeAuthorityError("program_inventory_mismatch")
    try:
        inventory = ProgramInventory.model_validate(_read_object(path, "program_inventory_invalid"))
    except ValidationError as exc:
        raise RuntimeAuthorityError("program_inventory_invalid") from exc
    if (
        inventory.product_id != PRODUCT_ID
        or inventory.owner_sid != journal.owner_sid
        or inventory.scope_id != journal.scope_id
        or inventory.transaction_id != journal.transaction_id
        or inventory.role != role
        or inventory.root_path_hash != expected_root_hash
        or inventory.payload_identity != expected_payload
    ):
        raise RuntimeAuthorityError("program_inventory_mismatch")
    return inventory
