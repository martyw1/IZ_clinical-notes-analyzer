from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

DEFAULT_ALLEVA_API_VERSION: Final = "1.0"
DEFAULT_TREATMENT_PLAN_START_DATE: Final = "2000-01-01T16:03"
COLLECTION_WRAPPERS: Final = ("items", "data", "results", "value", "records")
SEMANTIC_PARAMETER_NAMES: Final = frozenset(("limit", "offset", "client_id", "start_date"))


@dataclass(frozen=True, slots=True)
class AllevaReadProtocol:
    api_version: str = DEFAULT_ALLEVA_API_VERSION
    treatment_plan_start_date: str = DEFAULT_TREATMENT_PLAN_START_DATE


def read_headers(*, bearer_token: str, protocol: AllevaReadProtocol) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {bearer_token}",
        "X-Version": protocol.api_version,
    }


def collection_parameters(
    *,
    endpoint_parameters: Mapping[str, str],
    limit_parameter: str,
    offset_parameter: str,
    limit: int,
    cursor: int,
    protocol: AllevaReadProtocol,
    include_start_date: bool = False,
    client_id: str | None = None,
) -> dict[str, str | int]:
    parameters: dict[str, str | int] = {
        endpoint_parameters.get("limit", limit_parameter): limit,
        endpoint_parameters.get("offset", offset_parameter): cursor,
        "api-version": protocol.api_version,
    }
    for name, value in endpoint_parameters.items():
        if name not in SEMANTIC_PARAMETER_NAMES:
            parameters[name] = value
    if include_start_date:
        parameters[endpoint_parameters.get("start_date", "StartDate")] = protocol.treatment_plan_start_date
    if client_id is not None:
        parameters[endpoint_parameters.get("client_id", "ClientId")] = client_id
    return parameters


def detail_parameters(protocol: AllevaReadProtocol) -> dict[str, str]:
    return {"api-version": protocol.api_version}


def collection_records(payload: object) -> list[dict[str, object]]:
    values = payload
    if isinstance(payload, dict):
        for wrapper in COLLECTION_WRAPPERS:
            if wrapper in payload:
                values = payload[wrapper]
                break
        else:
            return [payload]
    if not isinstance(values, list):
        raise ValueError("Vendor response did not contain a supported collection payload.")
    return [value for value in values if isinstance(value, dict)]
