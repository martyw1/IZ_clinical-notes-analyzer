from __future__ import annotations

from collections.abc import Iterator

import httpx


class ResponseTooLarge(ValueError):
    pass


def get_bounded(
    client: httpx.Client,
    url: str,
    *,
    maximum_bytes: int,
    params: dict[str, str | int] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    request = client.build_request("GET", url, params=params, headers=headers)
    return _send_bounded(client, request, maximum_bytes)


def post_bounded(
    client: httpx.Client,
    url: str,
    *,
    maximum_bytes: int,
    data: dict[str, str],
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    request = client.build_request("POST", url, data=data, headers=headers)
    return _send_bounded(client, request, maximum_bytes)


def _send_bounded(client: httpx.Client, request: httpx.Request, maximum_bytes: int) -> httpx.Response:
    response = client.send(request, stream=True)
    try:
        content = bytearray()
        for chunk in _chunks(response):
            content.extend(chunk)
            if len(content) > maximum_bytes:
                raise ResponseTooLarge("HTTP response exceeded the configured byte limit")
        decoded_headers = httpx.Headers(response.headers)
        for header_name in ("content-encoding", "content-length", "transfer-encoding"):
            if header_name in decoded_headers:
                del decoded_headers[header_name]
        return httpx.Response(
            response.status_code,
            headers=decoded_headers,
            content=bytes(content),
            request=request,
        )
    finally:
        response.close()


def _chunks(response: httpx.Response) -> Iterator[bytes]:
    yield from response.iter_bytes()
