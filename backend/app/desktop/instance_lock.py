from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from app.desktop.ownership import DataDirLease


@dataclass(frozen=True, slots=True)
class InstanceLockError(RuntimeError):
    reason_code: str

    def __str__(self) -> str:
        return self.reason_code


@dataclass(frozen=True, slots=True)
class LockAcquisitionRequest:
    data_root: Path
    canonical_data_dir_id: str
    lock_file: Path


@dataclass(frozen=True, slots=True)
class LeaseHandoffOffer:
    canonical_data_dir_id: str
    lock_file_identity: str
    handle_identity: str
    inherited_descriptor: int
    nonce: str


@dataclass(frozen=True, slots=True)
class LeaseHandoffAcknowledgement:
    canonical_data_dir_id: str
    lock_file_identity: str
    handle_identity: str
    nonce: str


class NativeDataDirLease(DataDirLease, Protocol):
    @property
    def lock_file(self) -> Path: ...

    @property
    def lock_file_identity(self) -> str: ...

    @property
    def handle_identity(self) -> str: ...

    def validate_native_identity(self) -> bool: ...

    def begin_handoff(self, nonce: str) -> LeaseHandoffOffer: ...

    def adoption_is_valid(
        self,
        offer: LeaseHandoffOffer,
        acknowledgement: LeaseHandoffAcknowledgement,
    ) -> bool: ...


class InstanceLockProvider(Protocol):
    def canonical_data_dir_id(self, data_root: Path) -> str: ...

    def lock_root(self) -> Path: ...

    def try_acquire(self, request: LockAcquisitionRequest) -> NativeDataDirLease | None: ...


class LeaseHandoffTarget(Protocol):
    def adopt(self, offer: LeaseHandoffOffer) -> LeaseHandoffAcknowledgement: ...


class MaintenanceOperation(StrEnum):
    BACKUP = "backup"
    RESTORE = "restore"
    DIAGNOSTICS = "diagnostics"
    UNINSTALL = "uninstall"
    COMPLETE_UNINSTALL = "complete-uninstall"
    ADMIN_RECOVERY = "admin-recovery"
    REPORT_WRITE = "report-write"


@dataclass(frozen=True, slots=True)
class MaintenanceStopRequest:
    data_root: Path
    canonical_data_dir_id: str
    operation: MaintenanceOperation
    timeout_seconds: float = 30.0


class MaintenanceOwnerStopper(Protocol):
    def ensure_owner_stopped(self, request: MaintenanceStopRequest) -> bool: ...

    def revalidate_stale_state(self, request: MaintenanceStopRequest, lease: InstanceLease) -> bool: ...


class InstanceLease:
    def __init__(self, native_lease: NativeDataDirLease) -> None:
        self._native_lease = native_lease
        self._released = False

    @property
    def canonical_data_dir_id(self) -> str:
        return self._native_lease.canonical_data_dir_id

    @property
    def lock_file(self) -> Path:
        return self._native_lease.lock_file

    @property
    def lock_file_identity(self) -> str:
        return self._native_lease.lock_file_identity

    @property
    def handle_identity(self) -> str:
        return self._native_lease.handle_identity

    def is_held_by_current_process(self) -> bool:
        return not self._released and self._native_lease.is_held_by_current_process()

    def validate_native_identity(self) -> bool:
        return not self._released and self._native_lease.validate_native_identity()

    def release(self) -> None:
        if self._released:
            return
        self._native_lease.release()
        self._released = True

    def _begin_handoff(self, nonce: str) -> LeaseHandoffOffer:
        if not self.is_held_by_current_process() or not self.validate_native_identity():
            raise InstanceLockError("desktop_data_dir_lease_invalid")
        return self._native_lease.begin_handoff(nonce)

    def _adoption_is_valid(
        self,
        offer: LeaseHandoffOffer,
        acknowledgement: LeaseHandoffAcknowledgement,
    ) -> bool:
        return self._native_lease.adoption_is_valid(offer, acknowledgement)


class InstanceCoordinator:
    def __init__(
        self,
        provider: InstanceLockProvider,
        maintenance_stopper: MaintenanceOwnerStopper | None = None,
    ) -> None:
        self._provider = provider
        self._maintenance_stopper = maintenance_stopper

    def acquire(self, data_root: Path) -> InstanceLease | None:
        canonical_id = self._provider.canonical_data_dir_id(data_root)
        return self._acquire_for(data_root, canonical_id)

    def handoff(
        self,
        lease: InstanceLease,
        target: LeaseHandoffTarget,
    ) -> LeaseHandoffAcknowledgement:
        nonce = secrets.token_urlsafe(32)
        offer = lease._begin_handoff(nonce)
        acknowledgement = target.adopt(offer)
        offer_matches_parent = (
            offer.canonical_data_dir_id == lease.canonical_data_dir_id
            and offer.lock_file_identity == lease.lock_file_identity
            and offer.handle_identity == lease.handle_identity
            and hmac.compare_digest(offer.nonce, nonce)
        )
        acknowledgement_matches_offer = (
            acknowledgement.canonical_data_dir_id == offer.canonical_data_dir_id
            and acknowledgement.lock_file_identity == offer.lock_file_identity
            and acknowledgement.handle_identity == offer.handle_identity
            and hmac.compare_digest(acknowledgement.nonce, offer.nonce)
        )
        if (
            not offer_matches_parent
            or not acknowledgement_matches_offer
            or not lease._adoption_is_valid(offer, acknowledgement)
        ):
            raise InstanceLockError("desktop_lease_handoff_invalid")
        lease.release()
        return acknowledgement

    def request_maintenance_lease(
        self,
        data_root: Path,
        operation: MaintenanceOperation,
    ) -> InstanceLease:
        if self._maintenance_stopper is None:
            raise InstanceLockError("desktop_maintenance_control_unavailable")
        canonical_id = self._provider.canonical_data_dir_id(data_root)
        request = MaintenanceStopRequest(data_root.absolute(), canonical_id, operation)
        if not self._maintenance_stopper.ensure_owner_stopped(request):
            raise InstanceLockError("desktop_maintenance_owner_timeout")
        if self._provider.canonical_data_dir_id(data_root) != canonical_id:
            raise InstanceLockError("desktop_data_dir_identity_changed")
        lease = self._acquire_for(data_root, canonical_id)
        if lease is None:
            raise InstanceLockError("desktop_maintenance_owner_timeout")
        if self._maintenance_stopper.revalidate_stale_state(request, lease):
            return lease
        lease.release()
        raise InstanceLockError("desktop_runtime_state_conflict")

    @contextmanager
    def maintenance_lease(
        self,
        data_root: Path,
        operation: MaintenanceOperation,
    ) -> Iterator[InstanceLease]:
        lease = self.request_maintenance_lease(data_root, operation)
        try:
            yield lease
        finally:
            lease.release()

    def _acquire_for(self, data_root: Path, canonical_id: str) -> InstanceLease | None:
        absolute_data_root = data_root.absolute()
        lock_root = self._provider.lock_root().absolute()
        digest = hashlib.sha256(canonical_id.encode("utf-8")).hexdigest()
        lock_file = lock_root / f"{digest}.lock"
        _assert_outside_data_root(lock_file, absolute_data_root)
        native_lease = self._provider.try_acquire(
            LockAcquisitionRequest(absolute_data_root, canonical_id, lock_file)
        )
        if native_lease is None:
            return None
        lease = InstanceLease(native_lease)
        if (
            lease.canonical_data_dir_id != canonical_id
            or lease.lock_file.absolute() != lock_file
            or self._provider.canonical_data_dir_id(data_root) != canonical_id
            or not lease.is_held_by_current_process()
            or not lease.validate_native_identity()
        ):
            lease.release()
            raise InstanceLockError("desktop_data_dir_lease_invalid")
        return lease


def _assert_outside_data_root(lock_file: Path, data_root: Path) -> None:
    try:
        lock_file.relative_to(data_root)
    except ValueError:
        return
    raise InstanceLockError("desktop_lock_must_be_outside_data_root")
