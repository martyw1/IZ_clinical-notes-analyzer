from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.v2.services.bounded_http import ResponseTooLarge, get_bounded

MAX_OPENAPI_BYTES = 2 * 1024 * 1024
HTTP_METHODS = frozenset({"get", "put", "post", "delete", "patch", "head", "options", "trace"})


class OpenApiDefinitionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OpenApiDefinitionSummary:
    title: str
    operation_count: int


def load_openapi_definition(url: str, timeout_seconds: int) -> OpenApiDefinitionSummary:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise OpenApiDefinitionError("Saved OpenAPI URL must be an absolute HTTP or HTTPS URL")
    try:
        with httpx.Client(timeout=max(1, min(timeout_seconds, 60)), follow_redirects=True) as client:
            response = get_bounded(client, url, maximum_bytes=MAX_OPENAPI_BYTES, headers={"accept": "application/json"})
            response.raise_for_status()
    except (httpx.HTTPError, ResponseTooLarge) as exc:
        raise OpenApiDefinitionError("Unable to retrieve the saved OpenAPI definition") from exc
    try:
        payload = json.loads(response.content)
    except (TypeError, json.JSONDecodeError) as exc:
        raise OpenApiDefinitionError("Saved OpenAPI URL did not return JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("paths"), dict):
        raise OpenApiDefinitionError("Response is not a valid OpenAPI document with paths")
    info = payload.get("info")
    title = info.get("title") if isinstance(info, dict) else None
    return OpenApiDefinitionSummary(title=title if isinstance(title, str) and title.strip() else "Untitled OpenAPI definition", operation_count=_operation_count(payload["paths"]))


def _operation_count(paths: dict[object, object]) -> int:
    return sum(
        1
        for path_item in paths.values()
        if isinstance(path_item, dict)
        for method, operation in path_item.items()
        if isinstance(method, str) and method.lower() in HTTP_METHODS and isinstance(operation, dict)
    )
