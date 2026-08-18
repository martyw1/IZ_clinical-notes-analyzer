from __future__ import annotations

# noqa: SIZE_OK -- Task 4's provider-neutral state, lease, and handoff matrix is one security contract.

import base64
import hashlib
import json
import os
import shutil
import sys
import unicodedata
from pathlib import Path

import pytest


def _canonical(path: Path) -> str:
    return unicodedata.normalize("NFC", str(path.absolute())).casefold()


class _RuntimeLease:
    def __init__(self, canonical_id: str) -> None:
        self.canonical_data_dir_id = canonical_id
        self.held = True
        self.native_identity_valid = True
        self.release_count = 0

    def is_held_by_current_process(self) -> bool:
        return self.held

    def validate_native_identity(self) -> bool:
        return self.held and self.native_identity_valid

    def release(self) -> None:
        if self.held:
            self.held = False
            self.release_count += 1


class _StateStorage:
    def __init__(self) -> None:
        self.permissions_valid = True
        self.symlinked = False
        self.atomic_writes = 0
        self.removals = 0

    def prepare_private_runtime_directory(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def read_private_file(self, path: Path, max_bytes: int) -> bytes | None:
        self._validate(path)
        if not path.exists():
            return None
        payload = path.read_bytes()
        if len(payload) > max_bytes:
            from app.desktop.runtime_state import RuntimeStateError

            raise RuntimeStateError("desktop_runtime_state_too_large")
        return payload

    def atomic_write_private_file(self, path: Path, payload: bytes) -> None:
        self._validate(path)
        temporary = path.with_name(f".{path.name}.synthetic.tmp")
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
        self.atomic_writes += 1

    def remove_private_file(self, path: Path) -> None:
        self._validate(path)
        try:
            path.unlink()
        except FileNotFoundError:
            return
        self.removals += 1

    def _validate(self, path: Path) -> None:
        from app.desktop.runtime_state import RuntimeStateError

        if not self.permissions_valid:
            raise RuntimeStateError("desktop_runtime_state_permissions_invalid")
        if self.symlinked or path.is_symlink() or path.parent.is_symlink():
            raise RuntimeStateError("desktop_runtime_state_symlink_rejected")


class _NativeLease(_RuntimeLease):
    def __init__(self, provider: _LockProvider, request) -> None:
        super().__init__(request.canonical_data_dir_id)
        self.provider = provider
        self.lock_file = request.lock_file
        self.lock_file_identity = f"inode:{request.lock_file.name}"
        self.handle_identity = f"handle:{provider.acquire_count}"

    def begin_handoff(self, nonce: str):
        from app.desktop.instance_lock import LeaseHandoffOffer

        self.provider.events.append("parent_duplicated")
        return LeaseHandoffOffer(
            canonical_data_dir_id=self.provider.handoff_data_dir_id or self.canonical_data_dir_id,
            lock_file_identity=self.provider.handoff_lock_file_identity or self.lock_file_identity,
            handle_identity=self.handle_identity,
            inherited_descriptor=41,
            nonce=self.provider.handoff_nonce or nonce,
        )

    def adoption_is_valid(self, offer, acknowledgement) -> bool:
        return (
            self.provider.child_holds
            and offer.inherited_descriptor == 41
            and acknowledgement.handle_identity == self.handle_identity
        )

    def release(self) -> None:
        if self.held:
            super().release()
            self.provider.release_count += 1
            self.provider.events.append("parent_released")
            if not self.provider.child_holds:
                self.provider.held = False


class _LockProvider:
    def __init__(self, lock_root: Path) -> None:
        self._lock_root = lock_root
        self.acquire_count = 0
        self.release_count = 0
        self.held = False
        self.child_holds = False
        self.events: list[str] = []
        self.handoff_data_dir_id: str | None = None
        self.handoff_lock_file_identity: str | None = None
        self.handoff_nonce: str | None = None

    def canonical_data_dir_id(self, data_root: Path) -> str:
        return _canonical(data_root)

    def lock_root(self) -> Path:
        return self._lock_root

    def try_acquire(self, request):
        self.acquire_count += 1
        request.lock_file.parent.mkdir(parents=True, exist_ok=True)
        request.lock_file.touch(exist_ok=True)
        if self.held:
            return None
        self.held = True
        return _NativeLease(self, request)


class _MaintenanceStopper:
    def __init__(self, *, stopped: bool = True, revalidated: bool = True) -> None:
        self.stopped = stopped
        self.revalidated = revalidated
        self.stop_calls = 0
        self.revalidate_calls = 0
        self.lease_was_held = False

    def ensure_owner_stopped(self, request) -> bool:
        self.stop_calls += 1
        assert request.timeout_seconds == 30.0
        return self.stopped

    def revalidate_stale_state(self, request, lease) -> bool:
        self.revalidate_calls += 1
        self.lease_was_held = lease.is_held_by_current_process()
        return self.revalidated


class _BootstrapStorage:
    def __init__(self, resource_root: Path) -> None:
        self.resource_root = resource_root

    def canonical_data_dir_id(self, path: Path) -> str:
        return _canonical(path)

    def create_private_directory(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def verify_private_directory(self, path: Path) -> None:
        assert path.is_dir() and not path.is_symlink()

    def open_private_file(self, path: Path) -> int:
        return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)

    def verify_private_file(self, path: Path) -> None:
        assert path.is_file() and not path.is_symlink()

    def sync_directory(self, path: Path) -> None:
        assert path.is_dir()


class _HandoffTarget:
    def __init__(self, provider: _LockProvider, *, valid_nonce: bool = True) -> None:
        self.provider = provider
        self.valid_nonce = valid_nonce

    def adopt(self, offer):
        from app.desktop.instance_lock import LeaseHandoffAcknowledgement

        assert self.provider.held
        self.provider.events.append("child_adopted")
        self.provider.child_holds = True
        return LeaseHandoffAcknowledgement(
            canonical_data_dir_id=offer.canonical_data_dir_id,
            lock_file_identity=offer.lock_file_identity,
            handle_identity=offer.handle_identity,
            nonce=offer.nonce if self.valid_nonce else "wrong-nonce",
        )


def _process_identity():
    from app.desktop.process_identity import (
        DesktopPlatform,
        ExecutablePathPolicy,
        ProcessIdentity,
        normalize_executable_path,
    )

    platform = DesktopPlatform.WINDOWS if os.name == "nt" else DesktopPlatform.MACOS
    return ProcessIdentity(
        pid=os.getpid(),
        creation_time_epoch_ns=1_786_999_000_000_000_000,
        executable_path=normalize_executable_path(
            sys.executable,
            ExecutablePathPolicy(platform=platform, case_sensitive=False),
        ),
    )


def _state(data_dir_id: str, *, token_byte: bytes = b"a"):
    from app.desktop.runtime_state import DesktopRuntimeState

    identity = _process_identity()
    token = base64.urlsafe_b64encode(token_byte * 32).rstrip(b"=").decode("ascii")
    return DesktopRuntimeState(
        schema_version=1,
        data_dir_id=data_dir_id,
        run_id="12345678-1234-4234-9234-123456789abc",
        control_token=token,
        pid=identity.pid,
        process_creation_time_epoch_ns=identity.creation_time_epoch_ns,
        executable_path=identity.executable_path,
        port=8123,
        started_at_epoch_ns=1_786_999_100_000_000_000,
        ready=True,
    )


def test_runtime_state_round_trips_atomically_and_removes_only_with_matching_lease(tmp_path: Path) -> None:
    # Given: one canonical data root, private state provider, and exact held lease.
    from app.desktop.runtime_state import RuntimeStateStore

    data_root = tmp_path / "profile"
    data_root.mkdir()
    data_dir_id, storage = _canonical(data_root), _StateStorage()
    store, lease = RuntimeStateStore(data_root, data_dir_id, storage), _RuntimeLease(data_dir_id)
    state = _state(data_dir_id)

    # When: state is atomically published, read, and removed through the lease boundary.
    store.write(state, lease)
    observed = store.read()
    store.remove(lease)

    # Then: the full state round-trips, the secret stays out of repr, and cleanup is exact.
    assert observed == state
    assert state.control_token not in repr(state)
    assert storage.atomic_writes == 1
    assert storage.removals == 1
    assert store.state_file == data_root / "runtime" / "desktop-state.json"
    assert store.read() is None


def test_created_runtime_states_use_unique_256_bit_urlsafe_tokens() -> None:
    # Given: the same identity seed for two independent desktop runs.
    from app.desktop.runtime_state import RuntimeStateSeed, create_runtime_state

    seed = RuntimeStateSeed(
        data_dir_id="volume|synthetic-profile",
        process_identity=_process_identity(),
        port=8123,
        started_at_epoch_ns=1_786_999_100_000_000_000,
    )

    # When: two runtime states are created.
    first, second = create_runtime_state(seed), create_runtime_state(seed)

    # Then: run IDs and full 256-bit URL-safe control tokens are unique.
    assert first.run_id != second.run_id
    assert first.control_token != second.control_token
    assert len(base64.urlsafe_b64decode(first.control_token + "=")) == 32
    assert len(base64.urlsafe_b64decode(second.control_token + "=")) == 32


@pytest.mark.parametrize("lease_failure", ("wrong-root", "unheld", "native-identity"))
def test_runtime_state_mutation_rejects_invalid_lease(lease_failure: str, tmp_path: Path) -> None:
    # Given: a runtime store and a lease that fails one ownership invariant.
    from app.desktop.runtime_state import RuntimeStateError, RuntimeStateStore

    data_root = tmp_path / "profile"
    data_root.mkdir()
    data_dir_id, storage = _canonical(data_root), _StateStorage()
    store, lease = RuntimeStateStore(data_root, data_dir_id, storage), _RuntimeLease(data_dir_id)
    if lease_failure == "wrong-root":
        lease.canonical_data_dir_id = "volume|other-profile"
    elif lease_failure == "unheld":
        lease.held = False
    else:
        lease.native_identity_valid = False

    # When/Then: publication fails before any runtime directory or state file is created.
    with pytest.raises(RuntimeStateError, match="desktop_data_dir_lease_invalid"):
        store.write(_state(data_dir_id), lease)
    assert not store.runtime_directory.exists()


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        (lambda payload: b"not-json", "desktop_runtime_state_corrupt"),
        (
            lambda payload: json.dumps({**json.loads(payload), "schema_version": 99}).encode(),
            "desktop_runtime_state_schema_unsupported",
        ),
        (
            lambda payload: json.dumps(
                {key: value for key, value in json.loads(payload).items() if key != "pid"}
            ).encode(),
            "desktop_runtime_state_corrupt",
        ),
        (lambda payload: payload[:-1] + b',"pid":999999}', "desktop_runtime_state_corrupt"),
    ),
)
def test_corrupt_or_unknown_runtime_state_fails_closed(tmp_path: Path, mutation, reason: str) -> None:
    # Given: a valid state file that is then synthetically corrupted at rest.
    from app.desktop.runtime_state import RuntimeStateError, RuntimeStateStore

    data_root = tmp_path / "profile"
    data_root.mkdir()
    data_dir_id, storage = _canonical(data_root), _StateStorage()
    store, lease = RuntimeStateStore(data_root, data_dir_id, storage), _RuntimeLease(data_dir_id)
    store.write(_state(data_dir_id), lease)
    store.state_file.write_bytes(mutation(store.state_file.read_bytes()))

    # When/Then: parsing rejects the state without rewriting it.
    before = store.state_file.read_bytes()
    with pytest.raises(RuntimeStateError, match=reason):
        store.read()
    assert store.state_file.read_bytes() == before


def test_cross_data_dir_and_invalid_permissions_are_rejected_without_mutation(tmp_path: Path) -> None:
    # Given: state created for one profile and copied into another profile's runtime path.
    from app.desktop.runtime_state import RuntimeStateError, RuntimeStateStore

    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    storage = _StateStorage()
    first_store = RuntimeStateStore(first, _canonical(first), storage)
    first_store.write(_state(_canonical(first)), _RuntimeLease(_canonical(first)))
    second_store = RuntimeStateStore(second, _canonical(second), storage)
    storage.prepare_private_runtime_directory(second_store.runtime_directory)
    shutil.copyfile(first_store.state_file, second_store.state_file)
    copied = second_store.state_file.read_bytes()

    # When/Then: cross-profile identity and private-permission failures both fail closed.
    with pytest.raises(RuntimeStateError, match="desktop_runtime_state_wrong_data_dir"):
        second_store.read()
    storage.permissions_valid = False
    with pytest.raises(RuntimeStateError, match="desktop_runtime_state_permissions_invalid"):
        first_store.read()
    assert second_store.state_file.read_bytes() == copied


def test_symlinked_runtime_state_is_rejected_before_storage_access(tmp_path: Path) -> None:
    # Given: a storage provider reporting a runtime path-link substitution.
    from app.desktop.runtime_state import RuntimeStateError, RuntimeStateStore

    data_root = tmp_path / "profile"
    data_root.mkdir()
    storage = _StateStorage()
    storage.symlinked = True
    store = RuntimeStateStore(data_root, _canonical(data_root), storage)

    # When/Then: no state is accepted or created through the linked path.
    with pytest.raises(RuntimeStateError, match="desktop_runtime_state_symlink_rejected"):
        store.write(_state(_canonical(data_root)), _RuntimeLease(_canonical(data_root)))
    assert not store.state_file.exists()


def test_process_identity_exact_match_rejects_pid_reuse_and_path_change() -> None:
    # Given: an expected process and observations differing by one identity component.
    from app.desktop.process_identity import ProcessIdentity, process_identity_matches

    expected = _process_identity()

    class Provider:
        def __init__(self, observed: ProcessIdentity | None) -> None:
            self.observed = observed

        def identity_for_pid(self, pid: int) -> ProcessIdentity | None:
            assert pid == expected.pid
            return self.observed

    reused = ProcessIdentity(expected.pid, expected.creation_time_epoch_ns + 1, expected.executable_path)
    moved = ProcessIdentity(
        expected.pid,
        expected.creation_time_epoch_ns,
        type(expected.executable_path)(f"{expected.executable_path}.other"),
    )

    # When/Then: only PID + exact creation time + exact normalized path matches.
    assert process_identity_matches(Provider(expected), expected)
    assert not process_identity_matches(Provider(reused), expected)
    assert not process_identity_matches(Provider(moved), expected)
    assert not process_identity_matches(Provider(None), expected)


def test_executable_path_normalization_respects_injected_case_policy() -> None:
    # Given: case and Unicode aliases evaluated under injected volume policies.
    from app.desktop.process_identity import DesktopPlatform, ExecutablePathPolicy, normalize_executable_path

    insensitive = ExecutablePathPolicy(DesktopPlatform.WINDOWS, case_sensitive=False)
    sensitive = ExecutablePathPolicy(DesktopPlatform.WINDOWS, case_sensitive=True)
    composed = "C:/Apps/Pr\u00f3gram.exe"
    decomposed_lower = unicodedata.normalize("NFD", "c:/apps/pr\u00f3gram.exe")

    # When: both aliases are normalized for insensitive and sensitive volumes.
    insensitive_paths = {normalize_executable_path(path, insensitive) for path in (composed, decomposed_lower)}
    sensitive_paths = {normalize_executable_path(path, sensitive) for path in (composed, decomposed_lower)}

    # Then: Unicode is canonicalized while case equivalence follows the injected policy.
    assert len(insensitive_paths) == 1
    assert len(sensitive_paths) == 2


def test_coordinator_acquires_once_releases_once_and_bootstrap_never_reacquires(tmp_path: Path) -> None:
    # Given: one provider-neutral coordinator and Task 2's bootstrap boundary.
    from app.desktop.bootstrap import bootstrap_desktop
    from app.desktop.instance_lock import InstanceCoordinator

    data_root = tmp_path / "profile"
    provider = _LockProvider(tmp_path / "locks")
    coordinator = InstanceCoordinator(provider)

    # When: one lease is acquired and passed unchanged through bootstrap.
    lease = coordinator.acquire(data_root)
    assert lease is not None
    bootstrap_desktop(data_root, lease, _BootstrapStorage(tmp_path / "resources"))
    lease.release()
    lease.release()

    # Then: acquisition and native release each occur exactly once.
    assert provider.acquire_count == 1
    assert provider.release_count == 1


def test_lease_outside_data_root_and_persistent_lock_file_remains_unheld(tmp_path: Path) -> None:
    # Given: a coordinator whose provider keeps locks in an outside-root directory.
    from app.desktop.instance_lock import InstanceCoordinator

    data_root = tmp_path / "profile"
    provider = _LockProvider(tmp_path / "outside-locks")
    coordinator = InstanceCoordinator(provider)

    # When: ownership is acquired, released, and reopened.
    first = coordinator.acquire(data_root)
    assert first is not None
    lock_file = first.lock_file
    first.release()
    second = coordinator.acquire(data_root)

    # Then: the persistent file is outside the deletable root and was unheld between owners.
    assert data_root.absolute() not in lock_file.parents
    assert lock_file.name == f"{hashlib.sha256(_canonical(data_root).encode()).hexdigest()}.lock"
    assert lock_file.is_file()
    assert second is not None
    second.release()


def test_inherited_handoff_has_no_release_gap_and_requires_nonce_bound_adoption(tmp_path: Path) -> None:
    # Given: a held parent lease and a child adopting its duplicated descriptor.
    from app.desktop.instance_lock import InstanceCoordinator, InstanceLockError

    provider = _LockProvider(tmp_path / "locks")
    coordinator = InstanceCoordinator(provider)
    lease = coordinator.acquire(tmp_path / "profile")
    assert lease is not None

    # When: the child proves descriptor identity and the handoff nonce.
    coordinator.handoff(lease, _HandoffTarget(provider))

    # Then: adoption precedes parent release and exclusion remains held by the child.
    assert provider.events == ["parent_duplicated", "child_adopted", "parent_released"]
    assert provider.held
    provider.child_holds = False
    provider.held = False

    # Given/When: a second handoff returns the wrong nonce.
    second = coordinator.acquire(tmp_path / "profile")
    assert second is not None
    with pytest.raises(InstanceLockError, match="desktop_lease_handoff_invalid"):
        coordinator.handoff(second, _HandoffTarget(provider, valid_nonce=False))

    # Then: the parent lease is retained rather than opening a gap.
    assert second.is_held_by_current_process()
    second.release()


@pytest.mark.parametrize("offer_field", ("data-dir", "lock-file", "nonce"))
def test_inherited_handoff_offer_must_bind_to_parent_lease(offer_field: str, tmp_path: Path) -> None:
    # Given: a held parent lease whose provider emits an offer for different native ownership.
    from app.desktop.instance_lock import InstanceCoordinator, InstanceLockError

    provider = _LockProvider(tmp_path / "locks")
    coordinator = InstanceCoordinator(provider)
    lease = coordinator.acquire(tmp_path / "profile")
    assert lease is not None
    if offer_field == "data-dir":
        provider.handoff_data_dir_id = "volume|other-profile"
    elif offer_field == "lock-file":
        provider.handoff_lock_file_identity = "inode:other-lock"
    else:
        provider.handoff_nonce = "replaced-provider-nonce"

    # When/Then: even an echoing child cannot release the original parent lease.
    with pytest.raises(InstanceLockError, match="desktop_lease_handoff_invalid"):
        coordinator.handoff(lease, _HandoffTarget(provider))
    assert lease.is_held_by_current_process()
    lease.release()


def test_unicode_case_aliases_share_one_provider_neutral_lease(tmp_path: Path) -> None:
    # Given: NFC/NFD and case aliases mapped by the injected insensitive-volume policy.
    from app.desktop.instance_lock import InstanceCoordinator

    provider = _LockProvider(tmp_path / "locks")
    coordinator = InstanceCoordinator(provider)
    first = tmp_path / "Pr\u00f3file"
    alias = tmp_path / unicodedata.normalize("NFD", "pr\u00f3file")

    # When/Then: both spellings target the same persistent lease.
    owner = coordinator.acquire(first)
    assert owner is not None
    assert coordinator.acquire(alias) is None
    owner.release()


def test_live_not_ready_owner_is_never_evicted_or_released_by_contender(tmp_path: Path) -> None:
    # Given: a held provider lease representing a live owner that has not reached readiness.
    from app.desktop.instance_lock import InstanceCoordinator

    provider = _LockProvider(tmp_path / "locks")
    coordinator = InstanceCoordinator(provider)
    owner = coordinator.acquire(tmp_path / "profile")
    assert owner is not None

    # When: a second launch attempts the same canonical data directory.
    contender = coordinator.acquire(tmp_path / "profile")

    # Then: acquisition fails without evicting or releasing the live owner.
    assert contender is None
    assert owner.is_held_by_current_process()
    assert provider.release_count == 0
    owner.release()


def test_maintenance_owner_timeout_never_runs_unlocked_operation(tmp_path: Path) -> None:
    # Given: a live owner that cannot be stopped within the fixed maintenance budget.
    from app.desktop.instance_lock import InstanceCoordinator, InstanceLockError, MaintenanceOperation

    provider = _LockProvider(tmp_path / "locks")
    stopper = _MaintenanceStopper(stopped=False)
    coordinator = InstanceCoordinator(provider, stopper)

    # When/Then: maintenance fails before acquisition or any operation can run.
    with pytest.raises(InstanceLockError, match="desktop_maintenance_owner_timeout"):
        coordinator.request_maintenance_lease(tmp_path / "profile", MaintenanceOperation.BACKUP)
    assert stopper.stop_calls == 1
    assert provider.acquire_count == 0


@pytest.mark.parametrize("operation", ("backup", "restore", "uninstall", "complete-uninstall"))
def test_maintenance_lease_is_retained_through_data_root_deletion_and_callback(operation: str, tmp_path: Path) -> None:
    # Given: a verified stopped owner and an outside-root persistent lock.
    from app.desktop.instance_lock import InstanceCoordinator, MaintenanceOperation

    data_root = tmp_path / "profile"
    data_root.mkdir()
    provider, stopper = _LockProvider(tmp_path / "locks"), _MaintenanceStopper()
    coordinator = InstanceCoordinator(provider, stopper)

    # When: backup/restore/uninstall work runs inside the maintenance context.
    with coordinator.maintenance_lease(data_root, MaintenanceOperation(operation)) as lease:
        assert lease.is_held_by_current_process()
        shutil.rmtree(data_root)
        assert coordinator.acquire(data_root) is None

    # Then: the lease was revalidated while held and remains persistent but unheld afterward.
    assert stopper.lease_was_held
    reacquired = coordinator.acquire(data_root)
    assert reacquired is not None
    assert reacquired.lock_file.is_file()
    reacquired.release()
