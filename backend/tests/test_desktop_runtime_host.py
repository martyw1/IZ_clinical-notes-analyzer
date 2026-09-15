from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest
from fastapi import FastAPI

from app.desktop_process import open_owner_process, process_started_utc
from app.desktop_runtime_authority import authorize_runtime
from app.desktop_runtime_host import ManagedRuntimeHost
from app.desktop_runtime_launch import ManagedRuntimeLaunch
from test_desktop_runtime_authority import TX, clear_profile_environment, make_runtime_fixture

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows managed runtime contract")


@pytest.fixture
def component_root() -> Path:
    path = Path(gettempdir()).resolve() / f"iz-cna-component-{uuid.uuid4().hex[:12]}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def unused_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def control(component_root: Path, operation: str) -> dict[str, object]:
    powershell = shutil.which("powershell")
    assert powershell is not None
    repository = Path(__file__).resolve().parents[2]
    script = "\n".join(
        (
            "$ErrorActionPreference = 'Stop'",
            f"Import-Module '{repository / 'scripts/installer/maintenance-common.psm1'}' -Force -WarningAction SilentlyContinue",
            f"Import-Module '{repository / 'scripts/installer/maintenance-runtime.psm1'}' -Force -WarningAction SilentlyContinue",
            f"$context = Get-IzMaintenanceContext -TransactionId ([Guid]'{TX}') -ComponentTestRoot '{component_root}'",
            "$identity = Get-Content -LiteralPath $context.runtime_identity_path -Raw | ConvertFrom-Json",
            f"$response = Invoke-IzRuntimeControl -Context $context -Operation {operation} -RuntimeIdentity $identity -TimeoutSeconds 5",
            "[Console]::Out.Write(($response | ConvertTo-Json -Compress))",
        )
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    with TemporaryDirectory(prefix="iz-cna-host-ps-cache-") as cache:
        environment = os.environ.copy()
        environment["PSModuleAnalysisCachePath"] = str(Path(cache) / "ModuleAnalysisCache")
        environment["PSModulePath"] = os.pathsep.join(
            (
                str(Path.home() / "Documents" / "WindowsPowerShell" / "Modules"),
                str(Path(os.environ["ProgramFiles"]) / "WindowsPowerShell" / "Modules"),
                str(Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "Modules"),
            )
        )
        result = subprocess.run(
            [powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
            env=environment,
        )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert isinstance(value, dict)
    return value


def wait_for_identity(path: Path) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if path.is_file():
            return
        time.sleep(0.05)
    pytest.fail("runtime identity did not appear")


def get_status(url: str) -> int:
    try:
        with urlopen(url, timeout=5) as response:
            response.read()
            return response.status
    except HTTPError as exc:
        exc.read()
        return exc.code


def test_live_candidate_gate_commit_drain_and_graceful_shutdown(component_root: Path) -> None:
    fixture = make_runtime_fixture(component_root)
    authority = authorize_runtime(fixture.paths, mode="candidate", transaction_id=TX)
    owner = open_owner_process(os.getpid(), authority.owner_sid, process_started_utc(os.getpid()))
    launch = ManagedRuntimeLaunch(authority, owner)
    app = FastAPI()

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/business")
    def business() -> dict[str, str]:
        return {"status": "business"}

    port = unused_port()
    host = ManagedRuntimeHost(launch, app, port)
    outcomes: list[int] = []
    thread = threading.Thread(target=lambda: outcomes.append(host.run()), name="managed-runtime-test")
    thread.start()
    try:
        wait_for_identity(fixture.paths.identity_path)
        assert control(component_root, "status")["gate"] == "maintenance"
        assert get_status(f"http://127.0.0.1:{port}/api/health") == 200
        assert get_status(f"http://127.0.0.1:{port}/api/business") == 503
        fixture.write_receipt()
        fixture.journal["state"] = "COMMITTED"
        fixture.journal["completed_steps"] = ["NEW_PROGRAM_MOVED", "INSTALL_RECEIPT_WRITTEN", "COMMIT_RECORDED"]
        fixture.write_journal()
        committed = control(component_root, "commit")
        assert committed["status"] == "ok"
        assert committed["gate"] == "open"
        assert get_status(f"http://127.0.0.1:{port}/api/business") == 200
        drained = control(component_root, "drain")
        assert drained["reason"] == "drained"
        assert drained["active_business_requests"] == 0
        stopped = control(component_root, "shutdown")
        assert stopped["reason"] == "shutdown_requested"
    finally:
        thread.join(15)
        if thread.is_alive():
            host.request_shutdown()
            thread.join(5)
    assert not thread.is_alive()
    assert outcomes == [0]
    assert not fixture.paths.identity_path.exists()


def test_candidate_shuts_down_when_maintenance_owner_dies(component_root: Path) -> None:
    fixture = make_runtime_fixture(component_root)
    authority = authorize_runtime(fixture.paths, mode="candidate", transaction_id=TX)
    owner_process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    owner = open_owner_process(
        owner_process.pid,
        authority.owner_sid,
        process_started_utc(owner_process.pid),
    )
    app = FastAPI()
    port = unused_port()
    host = ManagedRuntimeHost(ManagedRuntimeLaunch(authority, owner), app, port)
    outcomes: list[int] = []
    thread = threading.Thread(target=lambda: outcomes.append(host.run()), name="owner-death-runtime-test")
    thread.start()
    try:
        wait_for_identity(fixture.paths.identity_path)
        assert control(component_root, "status")["gate"] == "maintenance"
        owner_process.terminate()
        owner_process.wait(5)
        thread.join(10)
    finally:
        if owner_process.poll() is None:
            owner_process.kill()
            owner_process.wait(5)
        if thread.is_alive():
            host.request_shutdown()
            thread.join(5)

    assert not thread.is_alive()
    assert outcomes == [0]
    assert not fixture.paths.identity_path.exists()
