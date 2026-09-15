from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 8000


def _port_from_environment() -> int:
    raw_port = os.environ.get("IZ_CNA_PORT", str(DEFAULT_PORT)).strip()
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise SystemExit("IZ_CNA_PORT must be a valid TCP port number") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("IZ_CNA_PORT must be between 1 and 65535")
    return port


def _run_unmanaged(port: int) -> int:
    import uvicorn

    uvicorn.run(
        "app.desktop_main:app",
        host=HOST,
        port=port,
        access_log=False,
        log_config=None,
    )
    return 0


def _run_managed(port: int) -> int:
    from app.desktop_runtime_host import ManagedRuntimeHost
    from app.desktop_runtime_launch import prepare_managed_launch

    launch = prepare_managed_launch(Path(sys.executable))
    try:
        from app.desktop_main import app

        host = ManagedRuntimeHost(launch, app, port)
    except (OSError, RuntimeError, ValueError):
        if launch.owner_lease is not None:
            launch.owner_lease.close()
        raise
    return host.run()


def main(argv: Sequence[str] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ("maintenance",):
        from app.desktop_maintenance import main as maintenance_main

        return maintenance_main(arguments[1:])
    if arguments:
        return 20
    port = _port_from_environment()
    if getattr(sys, "frozen", False):
        try:
            return _run_managed(port)
        except (OSError, RuntimeError, ValueError):
            return 31
    return _run_unmanaged(port)


if __name__ == "__main__":
    raise SystemExit(main())
