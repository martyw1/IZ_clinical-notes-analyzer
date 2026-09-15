from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

GUID_N = re.compile(r"^[0-9a-f]{32}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")

JournalState = Literal[
    "PREPARING",
    "PAYLOAD_VERIFIED",
    "QUIESCED",
    "SNAPSHOT_VERIFIED",
    "SWAP_INTENT",
    "OLD_MOVED",
    "NEW_MOVED",
    "VALIDATING",
    "COMMITTED",
    "ROLLBACK_INTENT",
    "ROLLED_BACK",
    "RECOVERY_REQUIRED",
]
JournalStep = Literal[
    "PAYLOAD_STAGED",
    "PAYLOAD_VERIFIED",
    "RUNTIME_QUIESCED",
    "SNAPSHOT_CREATED",
    "SNAPSHOT_VERIFIED",
    "OLD_MOVE_INTENT_RECORDED",
    "OLD_PROGRAM_MOVED",
    "NEW_MOVE_INTENT_RECORDED",
    "NEW_PROGRAM_MOVED",
    "CANDIDATE_STARTED",
    "CANDIDATE_VALIDATED",
    "INSTALL_RECEIPT_WRITTEN",
    "COMMIT_RECORDED",
    "ROLLBACK_INTENT_RECORDED",
    "CANDIDATE_STOPPED",
    "DATA_RESTORE_INTENT_RECORDED",
    "DATA_RESTORED",
    "PROGRAM_RESTORE_INTENT_RECORDED",
    "OLD_PROGRAM_RESTORED",
    "OLD_RECEIPT_RESTORED",
    "ROLLBACK_VALIDATED",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True, strict=True)


class ReleaseIdentity(StrictModel):
    version: str
    build: str
    installer_revision: int
    payload_identity: str

    @field_validator("payload_identity")
    @classmethod
    def validate_payload_identity(cls, value: str) -> str:
        if not HEX_64.fullmatch(value):
            raise ValueError("payload_identity")
        return value


class SnapshotBinding(StrictModel):
    format: Literal["IZCNABK2"]
    relative_path: str
    length: int
    sha256: str
    data_identity: str
    source_identity_hash: str
    profile_snapshot_identity: str
    verified: bool

    @field_validator("sha256", "data_identity", "source_identity_hash", "profile_snapshot_identity")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if not HEX_64.fullmatch(value):
            raise ValueError("hash")
        return value


class ProgramBinding(StrictModel):
    stage_payload_identity: str | None
    stage_inventory_relative_path: str | None
    stage_inventory_sha256: str | None
    stage_marker_sha256: str | None
    previous_payload_identity: str | None
    previous_inventory_relative_path: str | None
    previous_inventory_sha256: str | None
    previous_marker_sha256: str | None
    active_payload_identity: str | None

    @field_validator(
        "stage_payload_identity",
        "stage_inventory_sha256",
        "stage_marker_sha256",
        "previous_payload_identity",
        "previous_inventory_sha256",
        "previous_marker_sha256",
        "active_payload_identity",
    )
    @classmethod
    def validate_optional_hash(cls, value: str | None) -> str | None:
        if value is not None and not HEX_64.fullmatch(value):
            raise ValueError("hash")
        return value


class MaintenanceJournal(StrictModel):
    schema_tag: Literal["iz-cna-maintenance-journal-v1"] = Field(alias="schema")
    product_id: Literal["r3.iz-clinical-notes-analyzer.desktop"]
    owner_sid: str
    scope_id: str
    transaction_id: str
    action: Literal["AutoInstall", "Repair", "Uninstall", "RemoveData", "Recover", "Backup", "Restore"]
    state: JournalState
    sequence: int
    created_utc: str
    updated_utc: str
    source_release: ReleaseIdentity | None
    target_release: ReleaseIdentity | None
    data_identity: str | None
    payload_identity: str | None
    prior_receipt_sha256: str | None
    snapshot: SnapshotBinding | None
    program: ProgramBinding
    completed_steps: list[JournalStep]

    @field_validator("scope_id")
    @classmethod
    def validate_scope(cls, value: str) -> str:
        if not HEX_64.fullmatch(value):
            raise ValueError("scope_id")
        return value

    @field_validator("transaction_id")
    @classmethod
    def validate_transaction(cls, value: str) -> str:
        if not GUID_N.fullmatch(value):
            raise ValueError("transaction_id")
        return value

    @field_validator("data_identity", "payload_identity", "prior_receipt_sha256")
    @classmethod
    def validate_optional_identity(cls, value: str | None) -> str | None:
        if value is not None and not HEX_64.fullmatch(value):
            raise ValueError("identity")
        return value

    @field_validator("completed_steps")
    @classmethod
    def validate_unique_steps(cls, value: list[JournalStep]) -> list[JournalStep]:
        if len(value) != len(set(value)):
            raise ValueError("completed_steps")
        return value


class FileRecord(StrictModel):
    path: str
    length: int
    sha256: str

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not HEX_64.fullmatch(value):
            raise ValueError("sha256")
        return value


class InventoryFile(FileRecord):
    owned: bool


class ProgramInventory(StrictModel):
    schema_tag: Literal["iz-cna-program-inventory-v1"] = Field(alias="schema")
    product_id: Literal["r3.iz-clinical-notes-analyzer.desktop"]
    owner_sid: str
    scope_id: str
    transaction_id: str
    role: Literal["stage", "previous"]
    root_path_hash: str
    payload_identity: str
    files: list[InventoryFile]

    @field_validator("scope_id", "root_path_hash", "payload_identity")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if not HEX_64.fullmatch(value):
            raise ValueError("hash")
        return value

    @field_validator("transaction_id")
    @classmethod
    def validate_transaction(cls, value: str) -> str:
        if not GUID_N.fullmatch(value):
            raise ValueError("transaction_id")
        return value


class ShortcutRecord(StrictModel):
    location: Literal["start_menu", "desktop"]
    name: str
    target_kind: Literal["installed_relative", "system_powershell"]
    target_relative_path: str
    arguments_sha256: str


class InstallReceipt(StrictModel):
    schema_tag: Literal["iz-cna-install-receipt-v1"] = Field(alias="schema")
    product_id: Literal["r3.iz-clinical-notes-analyzer.desktop"]
    owner_sid: str
    scope_id: str
    install_identity: str
    data_identity: str
    version: str
    build: str
    installer_revision: int
    payload_identity: str
    owned_files: list[FileRecord]
    owned_shortcuts: list[ShortcutRecord]
    last_committed_transaction: str
    recovery_format: Literal["IZCNABK2"]
    written_utc: str

    @field_validator("scope_id", "install_identity", "data_identity", "payload_identity")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if not HEX_64.fullmatch(value):
            raise ValueError("hash")
        return value

    @field_validator("last_committed_transaction")
    @classmethod
    def validate_transaction(cls, value: str) -> str:
        if not GUID_N.fullmatch(value):
            raise ValueError("last_committed_transaction")
        return value

    def release(self) -> ReleaseIdentity:
        return ReleaseIdentity(
            version=self.version,
            build=self.build,
            installer_revision=self.installer_revision,
            payload_identity=self.payload_identity,
        )


class RuntimeIdentity(StrictModel):
    schema_tag: Literal["iz-cna-runtime-identity-v1"] = Field(alias="schema")
    product_id: Literal["r3.iz-clinical-notes-analyzer.desktop"]
    owner_sid: str
    scope_id: str
    data_identity: str
    instance_id: str
    transaction_id: str | None
    process_id: int
    process_started_utc: str
    executable_path: str
    executable_sha256: str
    version: str
    build: str
    installer_revision: int
    port: int
    pipe_name: str
    gate: Literal["open", "maintenance"]
    draining: bool
    created_utc: str
