from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


_BROWSER_HEADERS: Final = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def _response_headers(path: str) -> Mapping[str, str]:
    headers = dict(_BROWSER_HEADERS)
    if path == "/api" or path.startswith("/api/"):
        headers["Cache-Control"] = "no-store"
    return headers


class ResponsePrivacyMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_privacy(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.update(_response_headers(scope["path"]))
            await send(message)

        await self.app(scope, receive, send_with_privacy)


def private_server_error(request: Request, _exc: Exception) -> PlainTextResponse:
    # Starlette's outer error middleware bypasses user middleware, then re-raises for server logging.
    return PlainTextResponse(
        "Internal Server Error",
        status_code=500,
        headers=_response_headers(request.url.path),
    )
