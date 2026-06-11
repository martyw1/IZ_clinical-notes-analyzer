from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_ALLEVA_SWAGGER_UI_URL = 'https://api.allevasoft.com/swagger/index.html'
DEFAULT_TIMEOUT_SECONDS = 10
MAX_BODY_SNIPPET_CHARS = 600
MAX_PATHS_RETURNED = 40
HTTP_METHODS = {'get', 'post', 'put', 'patch', 'delete', 'head', 'options'}
REDACTED = '[redacted]'
SENSITIVE_NAME_PARTS = ('authorization', 'api_key', 'apikey', 'access_token', 'refresh_token', 'bearer', 'client_secret', 'secret', 'password', 'token')


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
            'url': redact_url(self.url),
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


def _is_sensitive_name(value: str) -> bool:
    normalized = re.sub(r'[^a-z0-9]+', '_', value.lower()).strip('_')
    return any(part in normalized for part in SENSITIVE_NAME_PARTS)


def redact_sensitive_text(value: str) -> str:
    redacted = re.sub(r'(?i)(bearer\s+)[A-Za-z0-9._~+/\-=]+', rf'\1{REDACTED}', value)
    return re.sub(
        r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|authorization|secret|token|bearer)([\"']?\s*[:=]\s*[\"']?)[^\"',\s}]+",
        rf'\1\2{REDACTED}',
        redacted,
    )


def redact_sensitive_value(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            redacted[key_text] = REDACTED if _is_sensitive_name(key_text) else redact_sensitive_value(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_value(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def redact_url(value: str) -> str:
    parsed = urlparse(value)
    if not parsed.query:
        return value
    redacted_query = urlencode([(key, REDACTED if _is_sensitive_name(key) else val) for key, val in parse_qsl(parsed.query, keep_blank_values=True)])
    return urlunparse(parsed._replace(query=redacted_query))


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


def _resolve_schema_ref(definition: dict[str, Any], value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    ref = value.get('$ref')
    if not isinstance(ref, str) or not ref.startswith('#/'):
        return value
    current: Any = definition
    for part in ref[2:].split('/'):
        if not isinstance(current, dict):
            return value
        current = current.get(part.replace('~1', '/').replace('~0', '~'))
    return current if isinstance(current, dict) else value


def _schema_type(schema: Any) -> str:
    if not isinstance(schema, dict):
        return 'string'
    if isinstance(schema.get('type'), str):
        return schema['type']
    if isinstance(schema.get('enum'), list):
        return 'string'
    if isinstance(schema.get('properties'), dict):
        return 'object'
    if isinstance(schema.get('items'), dict):
        return 'array'
    return 'string'


def _field_from_schema(name: str, schema: Any, *, required: bool = False, location: str = 'body') -> dict[str, Any]:
    schema = schema if isinstance(schema, dict) else {}
    return {
        'name': name,
        'in': location,
        'required': required,
        'type': _schema_type(schema),
        'description': str(schema.get('description') or ''),
        'enum': schema.get('enum') if isinstance(schema.get('enum'), list) else [],
        'default': schema.get('default', ''),
        'format': str(schema.get('format') or ''),
    }


def _body_fields(definition: dict[str, Any], schema: Any) -> list[dict[str, Any]]:
    schema = _resolve_schema_ref(definition, schema)
    if not isinstance(schema, dict):
        return []
    if isinstance(schema.get('allOf'), list):
        merged: list[dict[str, Any]] = []
        for part in schema['allOf']:
            merged.extend(_body_fields(definition, part))
        return merged
    properties = schema.get('properties') if isinstance(schema.get('properties'), dict) else {}
    required_names = set(schema.get('required') if isinstance(schema.get('required'), list) else [])
    return [
        _field_from_schema(name, _resolve_schema_ref(definition, prop_schema), required=name in required_names, location='body')
        for name, prop_schema in properties.items()
    ]


def extract_openapi_operations(definition: dict[str, Any], *, selected_definition_url: str = '') -> list[dict[str, Any]]:
    """Return a UI-friendly list of API operations with their required inputs."""
    if not isinstance(definition, dict):
        return []
    paths = definition.get('paths') if isinstance(definition.get('paths'), dict) else {}
    operations: list[dict[str, Any]] = []
    for path, path_item in sorted(paths.items()):
        if not isinstance(path_item, dict):
            continue
        inherited_parameters = path_item.get('parameters') if isinstance(path_item.get('parameters'), list) else []
        for method, operation in sorted(path_item.items()):
            method_lower = method.lower()
            if method_lower not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            parameters: list[dict[str, Any]] = []
            for raw_parameter in [*inherited_parameters, *(operation.get('parameters') if isinstance(operation.get('parameters'), list) else [])]:
                parameter = _resolve_schema_ref(definition, raw_parameter)
                if not isinstance(parameter, dict):
                    continue
                schema = _resolve_schema_ref(definition, parameter.get('schema') or {})
                parameters.append(
                    {
                        **_field_from_schema(
                            str(parameter.get('name') or ''),
                            schema,
                            required=bool(parameter.get('required')),
                            location=str(parameter.get('in') or 'query'),
                        ),
                        'description': str(parameter.get('description') or schema.get('description') or ''),
                    }
                )

            request_body = operation.get('requestBody') if isinstance(operation.get('requestBody'), dict) else {}
            request_body = _resolve_schema_ref(definition, request_body)
            content = request_body.get('content') if isinstance(request_body, dict) and isinstance(request_body.get('content'), dict) else {}
            preferred_content_type = ''
            body_schema: Any = {}
            for candidate in ['application/json', 'application/x-www-form-urlencoded', 'multipart/form-data']:
                if isinstance(content.get(candidate), dict):
                    preferred_content_type = candidate
                    body_schema = content[candidate].get('schema') or {}
                    break
            if not preferred_content_type and content:
                preferred_content_type = str(next(iter(content.keys())))
                first = content.get(preferred_content_type)
                body_schema = first.get('schema') if isinstance(first, dict) else {}

            operations.append(
                {
                    'operation_key': f'{method_lower.upper()} {path}',
                    'method': method_lower.upper(),
                    'path': path,
                    'operation_id': str(operation.get('operationId') or ''),
                    'summary': str(operation.get('summary') or ''),
                    'description': str(operation.get('description') or ''),
                    'tags': operation.get('tags') if isinstance(operation.get('tags'), list) else [],
                    'parameters': parameters,
                    'request_body_required': bool(request_body.get('required')) if isinstance(request_body, dict) else False,
                    'request_body_content_type': preferred_content_type,
                    'request_body_fields': _body_fields(definition, body_schema),
                    'selected_definition_url': selected_definition_url,
                }
            )
    return operations


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
        response.read()
        result.status_code = response.status_code
        try:
            result.elapsed_ms = int(response.elapsed.total_seconds() * 1000)
        except RuntimeError:
            result.elapsed_ms = None
        result.content_type = response.headers.get('content-type', '')
        body_text = response.text[:MAX_BODY_SNIPPET_CHARS]
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        result.message = redact_sensitive_text(f'HTTP {exc.response.status_code}: {exc.response.text[:MAX_BODY_SNIPPET_CHARS]}')
        logger.warning('API probe received HTTP error for %s: %s', url, result.message)
        return result, None, ''
    except httpx.RequestError as exc:
        result.message = redact_sensitive_text(f'{exc.__class__.__name__}: {exc}')
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
    operations = extract_openapi_operations(selected_definition or {}, selected_definition_url=selected_definition_url)
    return {
        'status': status,
        'message': message,
        'selected_definition_url': selected_definition_url,
        'definition_summary': selected_summary or {},
        'definition': selected_definition or {},
        'operations': operations,
        'probes': [probe.as_dict() for probe in probes],
        'api_key_used': bool((api_key or '').strip()),
    }


def build_api_connectivity_report(*, report_type: str, request: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return {
        'report_type': report_type,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'request': redact_sensitive_value(request),
        'result': redact_sensitive_value(result),
    }


def persist_api_connectivity_report(report: dict[str, Any], *, report_dir: Path | None = None) -> str:
    """Write a redacted API-connectivity report to local app data."""
    target_dir = report_dir or (settings.local_app_data_dir / 'api-reports')
    target_dir.mkdir(parents=True, exist_ok=True)
    report_type = re.sub(r'[^a-zA-Z0-9_.-]+', '-', str(report.get('report_type') or 'api-connectivity')).strip('-') or 'api-connectivity'
    generated = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    path = target_dir / f'{generated}-{report_type}.json'
    path.write_text(json.dumps(redact_sensitive_value(report), indent=2, sort_keys=True), encoding='utf-8')
    return str(path)


def _base_url_for_operation(*, api_base_url: str | None, definition: dict[str, Any], selected_definition_url: str | None) -> str:
    configured = _clean_url(api_base_url).rstrip('/')
    if configured and _is_http_url(configured):
        return configured
    servers = definition.get('servers') if isinstance(definition.get('servers'), list) else []
    for server in servers:
        if isinstance(server, dict) and _is_http_url(str(server.get('url') or '')):
            return str(server['url']).rstrip('/')
    origin = _origin(_clean_url(selected_definition_url))
    if origin:
        return origin.rstrip('/')
    return ''


def execute_openapi_operation(
    *,
    definition: dict[str, Any],
    selected_definition_url: str | None = None,
    api_base_url: str | None = None,
    method: str,
    path: str,
    parameters: dict[str, Any] | None = None,
    request_body: Any | None = None,
    api_key: str | None = None,
    api_key_header_name: str = 'x-api-key',
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    operations = extract_openapi_operations(definition, selected_definition_url=selected_definition_url or '')
    operation = next((item for item in operations if item['method'] == method.upper() and item['path'] == path), None)
    if not operation:
        return {'status': 'fail', 'message': 'Selected API operation was not found in the loaded definition.'}

    values = parameters or {}
    missing = [item['name'] for item in operation['parameters'] if item.get('required') and not str(values.get(item['name'], '')).strip()]
    missing.extend([item['name'] for item in operation['request_body_fields'] if item.get('required') and (not isinstance(request_body, dict) or request_body.get(item['name']) in (None, ''))])
    if missing:
        return {'status': 'fail', 'message': f'Missing required value(s): {", ".join(sorted(set(missing)))}', 'missing': sorted(set(missing))}

    base_url = _base_url_for_operation(api_base_url=api_base_url, definition=definition, selected_definition_url=selected_definition_url)
    if not base_url:
        return {'status': 'fail', 'message': 'No HTTP API base URL is available for this operation.'}

    resolved_path = path
    query: dict[str, Any] = {}
    headers = _headers(api_key=api_key, api_key_header_name=api_key_header_name)
    for parameter in operation['parameters']:
        name = parameter['name']
        value = values.get(name)
        if value in (None, ''):
            continue
        location = parameter.get('in')
        if location == 'path':
            resolved_path = resolved_path.replace('{' + name + '}', str(value)).replace('{' + name + '+}', str(value))
        elif location == 'query':
            query[name] = value
        elif location == 'header':
            headers[name] = str(value)

    url = urljoin(base_url.rstrip('/') + '/', resolved_path.lstrip('/'))
    if query:
        url = f'{url}?{urlencode(query, doseq=True)}'

    timeout = max(1, min(int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS), 60))
    started_result: dict[str, Any] = {
        'status': 'fail',
        'method': method.upper(),
        'url': redact_url(url),
        'request_body_sent': request_body is not None and method.upper() not in {'GET', 'HEAD'},
    }
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.request(
                method.upper(),
                url,
                headers=headers,
                json=request_body if method.upper() not in {'GET', 'HEAD'} and request_body not in (None, '') else None,
            )
            response.read()
    except httpx.RequestError as exc:
        return {**started_result, 'message': redact_sensitive_text(f'{exc.__class__.__name__}: {exc}')}

    try:
        elapsed_ms = int(response.elapsed.total_seconds() * 1000)
    except RuntimeError:
        elapsed_ms = None
    content_type = response.headers.get('content-type', '')
    body_text = redact_sensitive_text(response.text[:MAX_BODY_SNIPPET_CHARS])
    parsed_json: Any | None = None
    if 'json' in content_type.lower():
        try:
            parsed_json = redact_sensitive_value(response.json())
        except json.JSONDecodeError:
            parsed_json = None
    return {
        **started_result,
        'status': 'ok' if 200 <= response.status_code < 300 else 'warn',
        'message': f'HTTP {response.status_code}',
        'status_code': response.status_code,
        'elapsed_ms': elapsed_ms,
        'content_type': content_type,
        'response_json': parsed_json,
        'response_body_preview': '' if parsed_json is not None else body_text,
    }
