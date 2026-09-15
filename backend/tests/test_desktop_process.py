from __future__ import annotations

import subprocess
import sys
import threading

import pytest

from app.desktop_identity import current_user_sid
from app.desktop_process import ProcessIdentityError, open_owner_process, process_started_utc

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows process ownership contract")


def test_current_process_identity_matches_sid_and_start_time() -> None:
    started = process_started_utc(__import__("os").getpid())

    lease = open_owner_process(__import__("os").getpid(), current_user_sid(), started)
    try:
        assert not lease.exited
    finally:
        lease.close()


def test_owner_lease_observes_real_process_death() -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    lease = open_owner_process(process.pid, current_user_sid(), process_started_utc(process.pid))
    observed = threading.Event()
    lease.watch(observed.set)
    process.terminate()
    try:
        assert observed.wait(5)
        assert lease.exited
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(5)
        lease.close()


def test_owner_lease_rejects_wrong_start_time() -> None:
    with pytest.raises(ProcessIdentityError, match="maintenance_owner_mismatch"):
        open_owner_process(__import__("os").getpid(), current_user_sid(), "2000-01-01T00:00:00Z")
