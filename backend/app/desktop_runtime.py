from __future__ import annotations

import os
from typing import Final

import uvicorn

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


def main() -> None:
    uvicorn.run(
        "app.desktop_main:app",
        host=HOST,
        port=_port_from_environment(),
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    main()
