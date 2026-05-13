from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

DEFAULT_ALLEVA_SWAGGER_UI_URL = 'https://api.allevasoft.com/swagger/index.html'
DEFAULT_TIMEOUT_SECONDS = 10
MAX_BODY_SNIPPET_CHARS = 600
MAX_PATHS_RETURNED = 40


@dataclass
class ProbeResult:
    url: str
    kind: str
    status_code: int | None = None
    ok: bool = False
    elapsed_ms: int | None = None
    content_type: str = ''
    message: str = ''
    openapi_version: str | None = None
    title: str | None = None
    version: str | None = None
    path_count: int = 0
    schema_count: int = 0
    security_scheme_names: list[str] = field(default_factory=list)
    sample_paths: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            'url': self.url,
            'kind': self.kind,
            'status_code': self.status_code,
            'ok': self.ok,
            'elapsed_ms': self.elapsed_ms,
            'content_type': self.content_type,
            'message': self.message,
            'openapi_version': self.openapi_version,
            'title': self.title,
            'version': self.version,
            'path_count': self.path_count,
            'schema_count': self.schema_count,
            'security_scheme_names': self.security_scheme_names,
            'sample_paths': self.sample_paths,
        }


def _clean_url(value: str | None) -> str:
    return (value or '').strip()


def _origin(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ''
    return f'{parsed.scheme}://{parsed.netloc}'


def _is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)


def _safe_candidates(*urls: str | None) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in urls:
        url = _clean_url(raw)
        if not url or not _is_http_url(url) or url in seen:
            continue
        ordered.append(url)
        seen.add(url)
    return ordered


def candidate_definition_urls(
    *,
    swagger_ui_url: str | None = None,
    api_base_url: str | None = None,
    openapi_url: str | None = None,
    discovered_from_swagger_ui: list[str] | None = None,
) -> list[str]:
    bases: list[str] = []
    for url in [api_base_url, swagger_ui_url]:
        cleaned = _clean_url(url)
        if not cleaned:
            continue
        if cleaned.endswith('/swagger/index.html'):
            bases.append(cleaned[: -len('/swagger/index.html')])
        elif cleaned.endswith('/swagger/') or cleaned.endswith('/swagger'):
            bases.append(cleaned.rstrip('/swagger/'))
        else:
            origin = _origin(cleaned)
            if origin:
                bases.append(origin)
            elif _is_http_url(cleaned):
                bases.append(cleaned.rstrip('/'))

    generated: list[str] = []
    for base in bases:
        root = base.rstrip('/') + '/'
        generated.extend(
            [
                urljoin(root, 'swagger/v1/swagger.json'),
                urljoin(root, 'swagger.json'),
                urljoin(root, 'openapi.json'),
                urljoin(root, 'api/swagger.json'),
                urljoin(root, 'api/openapi.json'),
            ]
        )

    return _safe_candidates(openapi_url, *(discovered_from_swagger_ui or []), *generated)


def extract_swagger_ui_definition_urls(swagger_html: str, swagger_ui_url: str) -> list[str]:
    found: list[str] = []
    patterns = [
        r"\burl\s*:\s*['\"]([^'\"]+)['\"]",
        r"\burls\s*:\s*\[([^\]]+)\]",
    ]
    for match in re.finditer(patterns[0], swagger_html):
        found.append(match.group(1))

    for match in re.finditer(patterns[1], swagger_html, re.DOTALL):
        for url_match in re.finditer(r"url\s*:\s*['\"]([^'\"]+)['\"]", match.group(1)):
            found.append(url_match.group(1))

    base = swagger_ui_url
    return _safe_candidates(*(urljoin(base, candidate) for candidate in found))


def _headers(api_key: str | None = None, api_key_header_name: str = 'x-api-key') -> dict[str, str]:
    headers = {'Accept': 'application/json, text/html;q=0.9, */*;q=0.8'}
    key = (api_key or '').strip()
    if not key:
        return headers
    header_name = (api_key_header_name or 'x-api-key').strip()
    if header_name:
        headers[header_name] = key
    headers['Authorization'] = f'Bearer {key}'
    return headers


def _json_summary(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    paths = payload.get('paths') if isinstance(payload.get('paths'), dict) else {}
    components = payload.get('components') if isinstance(payload.get('components'), dict) else {}
    definitions = payload.get('definitions') if isinstance(payload.get('definitions'), dict) else {}
    schemas = components.get('schemas') if isinstance(components.get('schemas'), dict) else definitions
    security_schemes = components.get('securitySchemes') if isinstance(components.get('securitySchemes'), dict) else payload.get('securityDefinitions')
    info = payload.get('info') if isinstance(payload.get('info'), dict) else {}
    openapi_version = str(payload.get('openapi') or payload.get('swagger') or '')
    if not openapi_version and not paths:
        return None
    return {
        'openapi_version': openapi_version,
        'title': str(info.get('title') or ''),
        'version': str(info.get('version') or ''),
        'path_count': len(paths),
        'schema_count': len(schemas) if isinstance(schemas, dict) else 0,
        'security_scheme_names': sorted(security_schemes.keys()) if isinstance(security_schemes, dict) else [],
        'sample_paths': sorted(paths.keys())[:MAX_PATHS_RETURNED],
    }


def _probe_get(client: httpx.Client, url: str, *, kind: str, headers: dict[str, str]) -> tuple[ProbeResult, Any | None, str]:
    result = ProbeResult(url=url, kind=kind)
    try:
        response = client.get(url, headers=headers)
        result.status_code = response.status_code
        result.elapsed_ms = int(response.elapsed.total_seconds() * 1000)
        result.content_type = response.headers.get('content-type', '')
        body_text = response.text[:MAX_BODY_SNIPPET_CHARS]
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        result.message = f'HTTP {exc.response.status_code}: {exc.response.text[:MAX_BODY_SNIPPET_CHARS]}'
        logger.warning('API probe received HTTP error for %s: %s', url, result.message)
        return result, None, ''
    except httpx.RequestError as exc:
        result.message = f'{exc.__class__.__name__}: {exc}'
        logger.warning('API probe request failed for %s: %s', url, exc)
        return result, None, ''

    parsed_json: Any | None = None
    try:
        parsed_json = response.json()
    except json.JSONDecodeError:
        parsed_json = None

    summary = _json_summary(parsed_json)
    if summary:
        result.ok = True
        result.message = 'OpenAPI/Swagger definition loaded.'
        result.openapi_version = summary['openapi_version']
        result.title = summary['title']
        result.version = summary['version']
        result.path_count = summary['path_count']
        result.schema_count = summary['schema_count']
        result.security_scheme_names = summary['security_scheme_names']
        result.sample_paths = summary['sample_paths']
    else:
        result.ok = 200 <= (result.status_code or 0) < 300
        result.message = 'Endpoint reachable, but the response was not an OpenAPI/Swagger JSON definition.'
    return result, parsed_json, body_text


def pull_api_definitions(
    *,
    swagger_ui_url: str | None = DEFAULT_ALLEVA_SWAGGER_UI_URL,
    api_base_url: str | None = None,
    openapi_url: str | None = None,
    api_key: str | None = None,
    api_key_header_name: str = 'x-api-key',
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    timeout = max(1, min(int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS), 60))
    headers = _headers(api_key=api_key, api_key_header_name=api_key_header_name)
    swagger_ui_url = _clean_url(swagger_ui_url) or DEFAULT_ALLEVA_SWAGGER_UI_URL
    probes: list[ProbeResult] = []
    discovered_definition_urls: list[str] = []
    selected_definition: dict[str, Any] | None = None
    selected_definition_url = ''

    logger.info('Starting API definition pull for swagger_ui_url=%s api_base_url=%s openapi_url=%s', swagger_ui_url, api_base_url, openapi_url)

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        if swagger_ui_url and _is_http_url(swagger_ui_url):
            swagger_probe, _, html = _probe_get(client, swagger_ui_url, kind='swagger_ui', headers=headers)
            probes.append(swagger_probe)
            if html:
                discovered_definition_urls = extract_swagger_ui_definition_urls(html, swagger_ui_url)
                if discovered_definition_urls:
                    swagger_probe.message = f'Swagger UI reachable; discovered {len(discovered_definition_urls)} API definition URL(s).'

        for definition_url in candidate_definition_urls(
            swagger_ui_url=swagger_ui_url,
            api_base_url=api_base_url,
            openapi_url=openapi_url,
            discovered_from_swagger_ui=discovered_definition_urls,
        ):
            probe, parsed_definition, _ = _probe_get(client, definition_url, kind='openapi_definition', headers=headers)
            probes.append(probe)
            if probe.ok and parsed_definition and _json_summary(parsed_definition):
                selected_definition = parsed_definition
                selected_definition_url = definition_url
                break

    status = 'ok' if selected_definition else ('warn' if any(probe.ok for probe in probes) else 'fail')
    message = 'API definition loaded successfully.' if selected_definition else 'No OpenAPI/Swagger definition was found at the probed URLs.'
    if status == 'warn':
        message = 'At least one endpoint was reachable, but no OpenAPI/Swagger definition was loaded.'

    selected_summary = _json_summary(selected_definition) if selected_definition else None
    return {
        'status': status,
        'message': message,
        'selected_definition_url': selected_definition_url,
        'definition_summary': selected_summary or {},
        'definition': selected_definition or {},
        'probes': [probe.as_dict() for probe in probes],
        'api_key_used': bool((api_key or '').strip()),
    }
