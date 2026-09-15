from __future__ import annotations

import hashlib
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from starlette.types import ASGIApp

from app.desktop_identity import PRODUCT_ID
from app.desktop_lifecycle import GateSnapshot, MaintenanceGateMiddleware, RuntimeGate
from app.desktop_process import process_started_utc
from app.desktop_runtime_contracts import RuntimeIdentity
from app.desktop_runtime_control import RuntimeController
from app.desktop_runtime_files import acquire_runtime_lock, remove_runtime_identity, write_runtime_identity
from app.desktop_runtime_launch import ManagedRuntimeLaunch
from app.desktop_windows_pipe import WindowsNamedPipeServer


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


class ManagedRuntimeHost:
    def __init__(self, launch: ManagedRuntimeLaunch, app: ASGIApp, port: int) -> None:
        self._launch = launch
        self._gate = RuntimeGate(launch.authority.gate)
        gated_app = MaintenanceGateMiddleware(app, self._gate)
        config = uvicorn.Config(
            gated_app,
            host="127.0.0.1",
            port=port,
            access_log=False,
            log_config=None,
        )
        self._server = uvicorn.Server(config)
        self._port = port
        self._identity_lock = threading.Lock()
        self._identity = self._new_identity()
        self._published = False
        self._controller = RuntimeController(
            authority=launch.authority,
            identity=self._identity,
            gate=self._gate,
            request_shutdown=self.request_shutdown,
            state_changed=self._state_changed,
        )

    def _new_identity(self) -> RuntimeIdentity:
        authority = self._launch.authority
        executable = Path(sys.executable).resolve(strict=True)
        return RuntimeIdentity(
            schema="iz-cna-runtime-identity-v1",
            product_id=PRODUCT_ID,
            owner_sid=authority.owner_sid,
            scope_id=authority.scope_id,
            data_identity=authority.data_identity,
            instance_id=uuid.uuid4().hex,
            transaction_id=authority.transaction_id,
            process_id=os.getpid(),
            process_started_utc=process_started_utc(os.getpid()),
            executable_path=str(executable),
            executable_sha256=_sha256(executable),
            version=authority.release.version,
            build=authority.release.build,
            installer_revision=authority.release.installer_revision,
            port=self._port,
            pipe_name="iz-cna-runtime-v1-" + authority.scope_id[:32],
            gate=authority.gate,
            draining=False,
            created_utc=_utc_now(),
        )

    def _state_changed(self, snapshot: GateSnapshot) -> None:
        with self._identity_lock:
            self._identity = self._identity.model_copy(
                update={"gate": snapshot.gate, "draining": snapshot.draining}
            )
            if self._published:
                write_runtime_identity(self._launch.authority.paths.identity_path, self._identity)

    def _owner_died(self) -> None:
        if self._controller.committed:
            return
        self._gate.drain(0)
        self._state_changed(self._gate.snapshot())
        self.request_shutdown()

    def request_shutdown(self) -> None:
        self._server.should_exit = True

    def run(self) -> int:
        authority = self._launch.authority
        lock = acquire_runtime_lock(authority.paths.state_root, authority.scope_id, authority.data_identity)
        pipe = WindowsNamedPipeServer(self._identity.pipe_name, self._controller.handle_message)
        pipe_started = False
        try:
            owner = self._launch.owner_lease
            if owner is not None:
                if owner.exited:
                    return 31
                owner.watch(self._owner_died)
            pipe.start()
            pipe_started = True
            with self._identity_lock:
                write_runtime_identity(authority.paths.identity_path, self._identity)
                self._published = True
            self._server.run()
            return 0 if self._server.started else 31
        finally:
            if pipe_started:
                pipe.stop()
            if self._launch.owner_lease is not None:
                self._launch.owner_lease.close()
            with self._identity_lock:
                self._published = False
                remove_runtime_identity(authority.paths.identity_path, self._identity.instance_id)
            lock.close()
