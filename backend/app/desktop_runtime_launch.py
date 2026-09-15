from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from app.desktop_identity import IdentityError, authorized_paths_equal, current_user_sid, validated_path
from app.desktop_process import OwnerProcessLease, ProcessIdentityError, open_owner_process
from app.desktop_runtime_authority import RuntimeAuthority, RuntimeAuthorityError, RuntimePaths, authorize_runtime

GUID_N = re.compile(r"^[0-9a-f]{32}$")
MAINTENANCE_NAMES = (
    "IZ_CNA_MAINTENANCE_MODE",
    "IZ_CNA_MAINTENANCE_JOURNAL",
    "IZ_CNA_MAINTENANCE_TRANSACTION_ID",
    "IZ_CNA_MAINTENANCE_OWNER_PID",
    "IZ_CNA_MAINTENANCE_OWNER_STARTED_UTC",
)


@dataclass(frozen=True, slots=True)
class ManagedRuntimeLaunch:
    authority: RuntimeAuthority
    owner_lease: OwnerProcessLease | None


def _required_environment(name: str, reason: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeAuthorityError(reason)
    return value


def _paths(executable_value: Path) -> RuntimePaths:
    try:
        executable = validated_path(executable_value, must_exist=True)
        data_root = validated_path(
            _required_environment("IZ_CNA_LOCAL_APP_DATA_DIR", "data_root_missing"),
            must_exist=True,
        )
        install_root = validated_path(executable.parent.parent, must_exist=True)
        maintenance_root = validated_path(
            data_root.parent / "IZ Clinical Notes Analyzer Maintenance",
            must_exist=True,
        )
        state_root = validated_path(maintenance_root / "state", must_exist=True)
    except IdentityError as exc:
        raise RuntimeAuthorityError("runtime_path_invalid") from exc
    try:
        environment_file = validated_path(
            _required_environment("IZ_CNA_ENV_FILE", "environment_file_missing"),
            must_exist=True,
        )
    except IdentityError as exc:
        raise RuntimeAuthorityError("environment_file_missing") from exc
    if not authorized_paths_equal(environment_file, data_root / ".env"):
        raise RuntimeAuthorityError("environment_path_mismatch")
    return RuntimePaths(
        install_root=install_root,
        data_root=data_root,
        maintenance_root=maintenance_root,
        state_root=state_root,
        journal_path=state_root / "maintenance-journal.json",
        receipt_path=state_root / "install-receipt.json",
        identity_path=state_root / "runtime-identity.json",
        executable_path=executable,
    )


def _candidate_lease(paths: RuntimePaths) -> tuple[str, OwnerProcessLease]:
    try:
        configured_journal = validated_path(
            _required_environment("IZ_CNA_MAINTENANCE_JOURNAL", "journal_path_missing"),
            must_exist=False,
        )
    except IdentityError as exc:
        raise RuntimeAuthorityError("journal_path_invalid") from exc
    if not authorized_paths_equal(configured_journal, paths.journal_path):
        raise RuntimeAuthorityError("journal_path_mismatch")
    transaction_id = _required_environment("IZ_CNA_MAINTENANCE_TRANSACTION_ID", "transaction_missing")
    if not GUID_N.fullmatch(transaction_id):
        raise RuntimeAuthorityError("transaction_invalid")
    raw_pid = _required_environment("IZ_CNA_MAINTENANCE_OWNER_PID", "maintenance_owner_missing")
    if not raw_pid.isascii() or not raw_pid.isdecimal() or int(raw_pid) < 1:
        raise RuntimeAuthorityError("maintenance_owner_invalid")
    started = _required_environment("IZ_CNA_MAINTENANCE_OWNER_STARTED_UTC", "maintenance_owner_missing")
    try:
        lease = open_owner_process(int(raw_pid), current_user_sid(), started)
    except ProcessIdentityError as exc:
        raise RuntimeAuthorityError(str(exc)) from exc
    return transaction_id, lease


def prepare_managed_launch(executable_path: Path) -> ManagedRuntimeLaunch:
    paths = _paths(executable_path)
    mode = os.environ.get("IZ_CNA_MAINTENANCE_MODE", "").strip()
    if mode == "candidate":
        transaction_id, lease = _candidate_lease(paths)
        try:
            authority = authorize_runtime(paths, mode="candidate", transaction_id=transaction_id)
        except RuntimeAuthorityError:
            lease.close()
            raise
        return ManagedRuntimeLaunch(authority, lease)
    if mode or any(os.environ.get(name, "").strip() for name in MAINTENANCE_NAMES[1:]):
        raise RuntimeAuthorityError("maintenance_environment_invalid")
    authority = authorize_runtime(paths, mode="installed", transaction_id=None)
    return ManagedRuntimeLaunch(authority, None)
