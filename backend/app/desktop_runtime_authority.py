from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.desktop_identity import (
    IdentityError,
    authorized_paths_equal,
    contained_path,
    current_user_sid,
    install_identity,
    scope_id,
    validated_path,
)
from app.desktop_profile import resolve_profile
from app.desktop_runtime_contracts import (
    InstallReceipt,
    MaintenanceJournal,
    ReleaseIdentity,
)
from app.desktop_runtime_errors import RuntimeAuthorityError
from app.desktop_runtime_inventory import (
    read_inventory,
    read_journal,
    read_receipt,
    validate_files,
)

LaunchMode = Literal["candidate", "installed"]


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    install_root: Path
    data_root: Path
    maintenance_root: Path
    state_root: Path
    journal_path: Path
    receipt_path: Path
    identity_path: Path
    executable_path: Path


@dataclass(frozen=True, slots=True)
class RuntimeAuthority:
    paths: RuntimePaths
    owner_sid: str
    scope_id: str
    data_identity: str
    release: ReleaseIdentity
    gate: Literal["open", "maintenance"]
    transaction_id: str | None


def _validate_paths(paths: RuntimePaths) -> None:
    expected_state = paths.maintenance_root / "state"
    expected_executable = paths.install_root / "runtime" / "IZClinicalNotesAnalyzer.exe"
    expected_journal = expected_state / "maintenance-journal.json"
    expected_receipt = expected_state / "install-receipt.json"
    expected_identity = expected_state / "runtime-identity.json"
    pairs = (
        (paths.state_root, expected_state),
        (paths.executable_path, expected_executable),
        (paths.journal_path, expected_journal),
        (paths.receipt_path, expected_receipt),
        (paths.identity_path, expected_identity),
    )
    if any(not authorized_paths_equal(left, right) for left, right in pairs):
        raise RuntimeAuthorityError("runtime_path_mismatch")
    try:
        for root in (paths.install_root, paths.data_root, paths.maintenance_root, paths.state_root):
            validated_path(root, must_exist=True)
        validated_path(paths.executable_path, must_exist=True)
    except IdentityError as exc:
        raise RuntimeAuthorityError("runtime_path_invalid") from exc


def _validate_common(
    journal: MaintenanceJournal,
    owner_sid: str,
    expected_scope: str,
    expected_data: str,
) -> None:
    if (
        journal.owner_sid != owner_sid
        or journal.scope_id != expected_scope
        or journal.data_identity != expected_data
    ):
        raise RuntimeAuthorityError("journal_identity_mismatch")


def _validate_receipt(
    paths: RuntimePaths,
    receipt: InstallReceipt,
    owner_sid: str,
    expected_scope: str,
    expected_data: str,
) -> None:
    if (
        receipt.owner_sid != owner_sid
        or receipt.scope_id != expected_scope
        or receipt.install_identity != install_identity(owner_sid, paths.install_root)
        or receipt.data_identity != expected_data
    ):
        raise RuntimeAuthorityError("install_receipt_mismatch")
    validate_files(paths.install_root, receipt.owned_files, exact=False)


def _release_matches(left: ReleaseIdentity | None, right: ReleaseIdentity) -> bool:
    return left is not None and left == right


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise RuntimeAuthorityError("rollback_state_mismatch") from exc
    return digest.hexdigest()


def _validate_rollback_snapshot(
    paths: RuntimePaths,
    journal: MaintenanceJournal,
    expected_data: str,
) -> None:
    snapshot = journal.snapshot
    if (
        "DATA_RESTORED" not in journal.completed_steps
        or snapshot is None
        or not snapshot.verified
        or snapshot.data_identity != expected_data
        or snapshot.relative_path != "snapshot/pre-change.izcnabackup"
        or snapshot.length < 0
    ):
        raise RuntimeAuthorityError("rollback_state_mismatch")
    transaction_root = paths.maintenance_root / "transactions" / journal.transaction_id
    try:
        root = validated_path(transaction_root, must_exist=True)
        snapshot_path = contained_path(
            root,
            root / "snapshot" / "pre-change.izcnabackup",
            must_exist=True,
        )
    except IdentityError as exc:
        raise RuntimeAuthorityError("rollback_state_mismatch") from exc
    if (
        not snapshot_path.is_file()
        or snapshot_path.stat().st_size != snapshot.length
        or _file_sha256(snapshot_path) != snapshot.sha256
    ):
        raise RuntimeAuthorityError("rollback_state_mismatch")


def _validate_rollback_program(
    paths: RuntimePaths,
    journal: MaintenanceJournal,
    receipt: InstallReceipt,
) -> None:
    if "OLD_PROGRAM_MOVED" in journal.completed_steps:
        inventory = read_inventory(paths.maintenance_root, journal, "previous")
        validate_files(paths.install_root, inventory.files, exact=True)
        return
    try:
        validate_files(paths.install_root, receipt.owned_files, exact=True)
    except RuntimeAuthorityError:
        inventory = read_inventory(paths.maintenance_root, journal, "previous")
        validate_files(paths.install_root, inventory.files, exact=True)


def _authorize_installed(
    paths: RuntimePaths,
    journal: MaintenanceJournal,
    receipt: InstallReceipt,
    owner_sid: str,
    expected_scope: str,
    expected_data: str,
) -> ReleaseIdentity:
    _validate_receipt(paths, receipt, owner_sid, expected_scope, expected_data)
    release = receipt.release()
    if journal.state == "COMMITTED":
        if (
            journal.transaction_id != receipt.last_committed_transaction
            or not _release_matches(journal.target_release, release)
            or journal.payload_identity != release.payload_identity
            or journal.program.active_payload_identity != release.payload_identity
            or not {"INSTALL_RECEIPT_WRITTEN", "COMMIT_RECORDED"}.issubset(journal.completed_steps)
        ):
            raise RuntimeAuthorityError("commit_state_mismatch")
        return release
    if journal.state == "ROLLED_BACK":
        required_steps = {"OLD_PROGRAM_RESTORED", "OLD_RECEIPT_RESTORED", "ROLLBACK_VALIDATED"}
        if (
            receipt.last_committed_transaction == journal.transaction_id
            or not _release_matches(journal.source_release, release)
            or journal.program.active_payload_identity != release.payload_identity
            or not required_steps.issubset(journal.completed_steps)
            or journal.prior_receipt_sha256 is None
            or _file_sha256(paths.receipt_path) != journal.prior_receipt_sha256
        ):
            raise RuntimeAuthorityError("rollback_state_mismatch")
        _validate_rollback_program(paths, journal, receipt)
        if "CANDIDATE_STARTED" in journal.completed_steps:
            _validate_rollback_snapshot(paths, journal, expected_data)
        return release
    raise RuntimeAuthorityError("maintenance_pending")


def authorize_runtime(paths: RuntimePaths, *, mode: LaunchMode, transaction_id: str | None) -> RuntimeAuthority:
    _validate_paths(paths)
    owner = current_user_sid()
    expected_scope = scope_id(owner, paths.install_root, paths.data_root)
    journal = read_journal(paths.journal_path)
    fresh_candidate = (
        mode == "candidate"
        and journal.action == "AutoInstall"
        and journal.source_release is None
        and journal.snapshot is None
        and not paths.receipt_path.exists()
    )
    try:
        profile = resolve_profile(
            str(paths.data_root),
            str(paths.data_root / ".env"),
            "",
            allow_missing_database=fresh_candidate,
        )
    except IdentityError as exc:
        raise RuntimeAuthorityError(exc.reason) from exc
    if not profile.database_path.exists():
        unexpected = [path for path in paths.data_root.iterdir() if path.name != ".env"]
        if not fresh_candidate or unexpected:
            raise RuntimeAuthorityError("database_missing")
    _validate_common(journal, owner, expected_scope, profile.data_identity)
    if mode == "candidate":
        if transaction_id is None or journal.transaction_id != transaction_id:
            raise RuntimeAuthorityError("transaction_mismatch")
        if journal.state not in ("NEW_MOVED", "VALIDATING") or "NEW_PROGRAM_MOVED" not in journal.completed_steps:
            raise RuntimeAuthorityError("candidate_state_invalid")
        release = journal.target_release
        if release is None or journal.payload_identity != release.payload_identity:
            raise RuntimeAuthorityError("candidate_release_invalid")
        if journal.program.active_payload_identity != release.payload_identity:
            raise RuntimeAuthorityError("candidate_release_invalid")
        inventory = read_inventory(paths.maintenance_root, journal, "stage")
        validate_files(paths.install_root, inventory.files, exact=True)
        return RuntimeAuthority(paths, owner, expected_scope, profile.data_identity, release, "maintenance", transaction_id)
    if transaction_id is not None:
        raise RuntimeAuthorityError("transaction_mismatch")
    receipt = read_receipt(paths.receipt_path)
    release = _authorize_installed(paths, journal, receipt, owner, expected_scope, profile.data_identity)
    return RuntimeAuthority(paths, owner, expected_scope, profile.data_identity, release, "open", None)


def validate_candidate_commit(authority: RuntimeAuthority) -> ReleaseIdentity:
    if authority.transaction_id is None:
        raise RuntimeAuthorityError("commit_not_candidate")
    journal = read_journal(authority.paths.journal_path)
    _validate_common(journal, authority.owner_sid, authority.scope_id, authority.data_identity)
    if journal.state != "COMMITTED" or journal.transaction_id != authority.transaction_id:
        raise RuntimeAuthorityError("commit_not_durable")
    receipt = read_receipt(authority.paths.receipt_path)
    release = _authorize_installed(
        authority.paths,
        journal,
        receipt,
        authority.owner_sid,
        authority.scope_id,
        authority.data_identity,
    )
    if release != authority.release:
        raise RuntimeAuthorityError("commit_release_mismatch")
    return release
