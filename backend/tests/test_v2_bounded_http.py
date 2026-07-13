from __future__ import annotations

import gzip
import json

import httpx

from app.v2.services.bounded_http import get_bounded


def test_get_bounded_returns_decoded_json_when_vendor_uses_compression() -> None:
    # Given: the vendor streams a gzip-compressed JSON response.
    encoded = gzip.compress(json.dumps([{"id": "synthetic-plan"}]).encode("utf-8"))
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "application/json", "content-encoding": "gzip"},
            content=encoded,
            request=request,
        )
    )

    # When: the bounded HTTP helper buffers the decoded response.
    with httpx.Client(transport=transport) as client:
        response = get_bounded(client, "https://synthetic.invalid/treatment-plans", maximum_bytes=1_000)

    # Then: callers can parse the response without a second decompression attempt.
    assert response.json() == [{"id": "synthetic-plan"}]
    assert "content-encoding" not in response.headers
