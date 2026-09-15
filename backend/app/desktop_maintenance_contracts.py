from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Operation = Literal["inspect-data", "snapshot-database", "verify-data"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True, strict=True)


class InspectionRequest(StrictModel):
    schema_tag: Literal["iz-cna-data-inspection-request-v1"] = Field(alias="schema")
    data_root: str
    environment_file: str
    expected_database_path: str


class SnapshotRequest(StrictModel):
    schema_tag: Literal["iz-cna-database-snapshot-request-v1"] = Field(alias="schema")
    data_root: str
    environment_file: str
    source_database_path: str
    owned_output_root: str
    snapshot_database_path: str


class VerificationRequest(StrictModel):
    schema_tag: Literal["iz-cna-data-verification-request-v1"] = Field(alias="schema")
    data_root: str
    environment_file: str
    expected_database_path: str


class OwnedRootMarker(StrictModel):
    schema_tag: Literal["iz-cna-owned-root-v1"] = Field(alias="schema")
    product_id: Literal["r3.iz-clinical-notes-analyzer.desktop"]
    owner_sid: str
    scope_id: str
    role: Literal["transaction"]
    transaction_id: str
    root_path_hash: str
    created_utc: str


class MaintenanceResult(StrictModel):
    schema_tag: str = Field(alias="schema")
    operation: Operation
    status: Literal["success"]
    reason: Literal["ok"]
    data_identity: str
    source_identity_hash: str
    profile_snapshot_identity: str
    environment_sha256: str
    database_relative_path: str
    database_sha256: str
    sqlite_integrity: Literal["ok"]
    foreign_key_violations: int
    schema_version: int
    safe_counts: dict[str, int]
    encrypted_payloads_checked: int
    encrypted_payloads_valid: int


class SnapshotResult(MaintenanceResult):
    snapshot_sha256: str


class FailureResult(StrictModel):
    schema_tag: str = Field(alias="schema")
    operation: Operation
    status: Literal["failed"]
    reason: str
