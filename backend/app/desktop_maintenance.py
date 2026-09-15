from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.desktop_identity import (
    PRODUCT_ID,
    IdentityError,
    authorized_paths_equal,
    contained_path,
    current_user_sid,
    root_path_hash,
    validated_path,
)
from app.desktop_profile import resolve_profile
from app.desktop_maintenance_contracts import (
    FailureResult,
    InspectionRequest,
    MaintenanceResult,
    Operation,
    OwnedRootMarker,
    SnapshotRequest,
    SnapshotResult,
    VerificationRequest,
)
from app.desktop_sqlite_inspection import (
    DatabaseInspection,
    DatabaseInspectionError,
    inspect_database,
    sha256_file,
    snapshot_database,
)

SCHEMAS = {
    "inspect-data": "iz-cna-data-inspection-v1",
    "snapshot-database": "iz-cna-database-snapshot-v1",
    "verify-data": "iz-cna-data-verification-v1",
}
GUID_N = re.compile(r"^[0-9a-f]{32}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class MaintenanceError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise MaintenanceError("request_invalid")
        result[name] = value
    return result


def _read_json(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    if len(raw) > 65_536:
        raise MaintenanceError("request_invalid")
    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MaintenanceError("request_invalid") from exc
    if not isinstance(value, dict):
        raise MaintenanceError("request_invalid")
    return value


def _write_json(path: Path, payload: BaseModel) -> None:
    encoded = payload.model_dump_json(by_alias=True, exclude_none=False).encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise MaintenanceError("result_exists") from exc
    with os.fdopen(descriptor, "wb") as target:
        target.write(encoded)
        target.flush()
        os.fsync(target.fileno())


def _hash_json(value: dict[str, object]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _result(
    operation: Operation,
    profile_data_identity: str,
    environment_sha256: str,
    database_relative_path: str,
    inspection: DatabaseInspection,
) -> MaintenanceResult:
    source_values: dict[str, object] = {
        "product_id": PRODUCT_ID,
        "database_relative_path": database_relative_path,
        "environment_sha256": environment_sha256,
        "database_sha256": inspection.database_sha256,
    }
    source_identity = _hash_json(source_values)
    safe_counts_sha256 = _hash_json(dict(sorted(inspection.safe_counts.items())))
    profile_snapshot_identity = _hash_json(
        {
            **source_values,
            "source_identity_hash": source_identity,
            "safe_counts_sha256": safe_counts_sha256,
        }
    )
    return MaintenanceResult(
        schema=SCHEMAS[operation],
        operation=operation,
        status="success",
        reason="ok",
        data_identity=profile_data_identity,
        source_identity_hash=source_identity,
        profile_snapshot_identity=profile_snapshot_identity,
        environment_sha256=environment_sha256,
        database_relative_path=database_relative_path,
        database_sha256=inspection.database_sha256,
        sqlite_integrity=inspection.sqlite_integrity,
        foreign_key_violations=inspection.foreign_key_violations,
        schema_version=inspection.schema_version,
        safe_counts=inspection.safe_counts,
        encrypted_payloads_checked=inspection.encrypted_payloads_checked,
        encrypted_payloads_valid=inspection.encrypted_payloads_valid,
    )


def _validate_marker(root: Path) -> None:
    marker_path = contained_path(root, root / ".iz-cna-owned-root.json", must_exist=True)
    try:
        marker = OwnedRootMarker.model_validate(_read_json(marker_path))
    except ValidationError as exc:
        raise MaintenanceError("owned_output_invalid") from exc
    if (
        marker.owner_sid != current_user_sid()
        or not HEX_64.fullmatch(marker.scope_id)
        or not GUID_N.fullmatch(marker.transaction_id)
        or root.name != marker.transaction_id
        or marker.root_path_hash != root_path_hash(root)
    ):
        raise MaintenanceError("owned_output_invalid")


def _inspect(request: InspectionRequest | VerificationRequest, operation: Operation) -> MaintenanceResult:
    profile = resolve_profile(
        request.data_root,
        request.environment_file,
        request.expected_database_path,
        allow_relocated_absolute=operation == "verify-data",
    )
    inspection = inspect_database(profile.database_path, profile.data_root, profile.encryption_secret)
    return _result(
        operation,
        profile.data_identity,
        profile.environment_sha256,
        profile.database_relative_path,
        inspection,
    )


def _snapshot(request: SnapshotRequest, request_path: Path, result_path: Path) -> SnapshotResult:
    profile = resolve_profile(request.data_root, request.environment_file, request.source_database_path)
    owned_root = validated_path(request.owned_output_root, must_exist=True)
    _validate_marker(owned_root)
    expected_snapshot = owned_root / "snapshot" / "selected-database.sqlite3"
    snapshot_path = contained_path(owned_root, request.snapshot_database_path, must_exist=False)
    if not authorized_paths_equal(snapshot_path, expected_snapshot.resolve(strict=False)):
        raise MaintenanceError("snapshot_path_invalid")
    if not authorized_paths_equal(request_path.parent, (owned_root / "requests").resolve(strict=True)):
        raise MaintenanceError("request_path_invalid")
    if not authorized_paths_equal(result_path.parent, (owned_root / "results").resolve(strict=True)):
        raise MaintenanceError("result_path_invalid")
    snapshot_database(profile.database_path, snapshot_path)
    try:
        inspection = inspect_database(snapshot_path, profile.data_root, profile.encryption_secret)
        base = _result(
            "snapshot-database",
            profile.data_identity,
            profile.environment_sha256,
            profile.database_relative_path,
            inspection,
        )
        return SnapshotResult(**base.model_dump(by_alias=True), snapshot_sha256=sha256_file(snapshot_path))
    except (DatabaseInspectionError, OSError):
        snapshot_path.unlink(missing_ok=True)
        raise


def _execute(operation: Operation, request_path: Path, result_path: Path) -> BaseModel:
    payload = _read_json(request_path)
    try:
        if operation == "inspect-data":
            return _inspect(InspectionRequest.model_validate(payload), operation)
        if operation == "verify-data":
            return _inspect(VerificationRequest.model_validate(payload), operation)
        return _snapshot(SnapshotRequest.model_validate(payload), request_path, result_path)
    except ValidationError as exc:
        raise MaintenanceError("request_invalid") from exc


def main(argv: Sequence[str] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 5 or arguments[1] != "--request" or arguments[3] != "--result":
        return 20
    operation_value = arguments[0]
    if operation_value not in SCHEMAS:
        return 20
    operation: Operation = operation_value
    result_path: Path | None = None
    try:
        request_path = validated_path(arguments[2], must_exist=True)
        result_path = validated_path(arguments[4], must_exist=False)
        if result_path.exists() or authorized_paths_equal(request_path, result_path):
            return 20
        result = _execute(operation, request_path, result_path)
        _write_json(result_path, result)
        return 0
    except (IdentityError, DatabaseInspectionError, MaintenanceError, OSError) as exc:
        reason = exc.reason if isinstance(exc, (IdentityError, DatabaseInspectionError, MaintenanceError)) else "io_error"
        if result_path is None:
            return 20
        try:
            failure = FailureResult(
                schema=SCHEMAS[operation],
                operation=operation,
                status="failed",
                reason=reason,
            )
            _write_json(result_path, failure)
        except (IdentityError, MaintenanceError, OSError):
            return 20
        return 20
