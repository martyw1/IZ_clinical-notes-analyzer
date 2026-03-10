from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.models.models import AppSetting
from app.services.llm_assist import call_llm_text, llm_is_configured

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AccessIntelResult:
    source_ip: str | None
    ip_scope: str
    geolocation: dict[str, Any]
    reputation: dict[str, Any]
    lookup_status: str
    danger_score: int
    dangerous: bool | None
    danger_summary: str

    def as_details(self) -> dict[str, Any]:
        return {
            'source_ip': self.source_ip,
            'ip_scope': self.ip_scope,
            'geolocation': self.geolocation,
            'reputation': self.reputation,
            'lookup_status': self.lookup_status,
            'danger_score': self.danger_score,
            'dangerous': self.dangerous,
            'danger_summary': self.danger_summary,
        }


def _ip_scope(source_ip: str | None) -> str:
    if not source_ip:
        return 'unknown'
    try:
        address = ipaddress.ip_address(source_ip)
    except ValueError:
        return 'invalid'
    if address.is_loopback:
        return 'loopback'
    if address.is_private:
        return 'private'
    if address.is_reserved:
        return 'reserved'
    if address.is_multicast:
        return 'multicast'
    if address.is_global:
        return 'public'
    return 'unknown'


def _request_timeout(app_settings: AppSetting) -> int:
    return max(1, app_settings.access_lookup_timeout_seconds)


def _fetch_geolocation(app_settings: AppSetting, source_ip: str) -> dict[str, Any]:
    template = app_settings.access_geo_lookup_url.strip()
    if not template:
        return {}
    url = template.format(ip=source_ip) if '{ip}' in template else f"{template.rstrip('/')}/{source_ip}"

    with httpx.Client(timeout=_request_timeout(app_settings)) as client:
        response = client.get(url, headers={'Accept': 'application/json'})
        response.raise_for_status()
        payload = response.json()

    if isinstance(payload, dict) and payload.get('success') is False:
        return {'provider_error': payload.get('message') or 'lookup_failed'}

    connection = payload.get('connection') if isinstance(payload, dict) else {}
    if not isinstance(connection, dict):
        connection = {}
    return {
        'provider': 'ipwho.is',
        'country': payload.get('country'),
        'country_code': payload.get('country_code') or payload.get('countryCode'),
        'region': payload.get('region'),
        'city': payload.get('city'),
        'latitude': payload.get('latitude'),
        'longitude': payload.get('longitude'),
        'continent': payload.get('continent'),
        'isp': connection.get('isp'),
        'organization': connection.get('org'),
        'asn': connection.get('asn'),
        'type': payload.get('type'),
    }


def _fetch_reputation(app_settings: AppSetting, source_ip: str) -> dict[str, Any]:
    if not app_settings.access_reputation_api_key.strip() or not app_settings.access_reputation_url.strip():
        return {}

    with httpx.Client(timeout=_request_timeout(app_settings)) as client:
        response = client.get(
            app_settings.access_reputation_url.strip(),
            params={'ipAddress': source_ip, 'maxAgeInDays': 90},
            headers={
                'Accept': 'application/json',
                'Key': app_settings.access_reputation_api_key,
            },
        )
        response.raise_for_status()
        payload = response.json()

    data = payload.get('data') if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        return {}
    return {
        'provider': 'AbuseIPDB',
        'abuse_confidence_score': data.get('abuseConfidenceScore'),
        'total_reports': data.get('totalReports'),
        'last_reported_at': data.get('lastReportedAt'),
        'country_code': data.get('countryCode'),
        'usage_type': data.get('usageType'),
        'isp': data.get('isp'),
        'domain': data.get('domain'),
        'is_tor': data.get('isTor'),
    }


def _fallback_summary(source_ip: str | None, ip_scope: str, geolocation: dict[str, Any], reputation: dict[str, Any], danger_score: int) -> tuple[bool | None, str]:
    if ip_scope in {'loopback', 'private'}:
        return (False, f'This IP is not dangerous based on current evidence because {source_ip or "it"} is a local/private address and not internet-routable.')
    if ip_scope == 'invalid':
        return (None, 'This IP could not be validated, so its danger level is unknown.')

    abuse_score = reputation.get('abuse_confidence_score')
    location_bits = [value for value in [geolocation.get('city'), geolocation.get('region'), geolocation.get('country')] if value]
    location = ', '.join(location_bits) if location_bits else 'an unknown location'
    if isinstance(abuse_score, int) and abuse_score >= 75:
        return (True, f'This IP appears dangerous because AbuseIPDB reports an abuse confidence score of {abuse_score} for a public address in {location}.')
    if isinstance(abuse_score, int) and abuse_score >= 25:
        return (True, f'This IP may be dangerous because AbuseIPDB reports an abuse confidence score of {abuse_score} for a public address in {location}.')
    if danger_score <= 20:
        return (False, f'This IP does not currently appear dangerous because no strong abuse indicators were returned for the public address in {location}.')
    return (None, f'This IP has some risk indicators, but the current evidence is not strong enough to classify it as dangerous.')


def _llm_summary(app_settings: AppSetting, source_ip: str | None, ip_scope: str, geolocation: dict[str, Any], reputation: dict[str, Any], danger_score: int) -> str | None:
    if not app_settings.llm_use_for_access_review or not llm_is_configured(app_settings):
        return None

    response = call_llm_text(
        app_settings,
        system_prompt=(
            'You assess login-access IPs for a clinical records application. '
            'Return exactly one sentence that explicitly says whether the IP is dangerous or not dangerous based on the supplied evidence. '
            'Do not hedge with multiple sentences.'
        ),
        user_prompt=(
            f'Source IP: {source_ip}\n'
            f'IP scope: {ip_scope}\n'
            f'Geolocation data: {geolocation}\n'
            f'Reputation data: {reputation}\n'
            f'Heuristic danger score: {danger_score}\n'
            'Use only this evidence. Mention danger clearly in one sentence.'
        ),
        max_tokens=120,
        temperature=0,
    )
    return response.strip() if response else None


def lookup_access_intel(app_settings: AppSetting, source_ip: str | None) -> AccessIntelResult:
    ip_scope = _ip_scope(source_ip)
    geolocation: dict[str, Any] = {}
    reputation: dict[str, Any] = {}
    lookup_status = 'not_run'

    if not app_settings.access_intel_enabled:
        danger_summary = 'This IP could not be assessed because access intelligence lookups are disabled.'
        return AccessIntelResult(source_ip, ip_scope, geolocation, reputation, 'disabled', 0, None, danger_summary)

    if source_ip and ip_scope == 'public':
        lookup_status = 'partial'
        try:
            geolocation = _fetch_geolocation(app_settings, source_ip)
        except Exception as exc:  # pragma: no cover - exercised via runtime/network failures
            logger.warning('Geolocation lookup failed for %s: %s', source_ip, exc)
            geolocation = {'provider_error': str(exc)}
        try:
            reputation = _fetch_reputation(app_settings, source_ip)
        except Exception as exc:  # pragma: no cover - exercised via runtime/network failures
            logger.warning('Reputation lookup failed for %s: %s', source_ip, exc)
            reputation = {'provider_error': str(exc)}
        if geolocation or reputation:
            lookup_status = 'complete'
    elif source_ip:
        lookup_status = f'skipped_{ip_scope}'
    else:
        lookup_status = 'missing_ip'

    danger_score = 0
    abuse_score = reputation.get('abuse_confidence_score')
    if isinstance(abuse_score, int):
        danger_score = abuse_score
    elif ip_scope in {'loopback', 'private'}:
        danger_score = 0
    elif geolocation.get('provider_error') or reputation.get('provider_error'):
        danger_score = 25

    dangerous, danger_summary = _fallback_summary(source_ip, ip_scope, geolocation, reputation, danger_score)
    llm_summary = _llm_summary(app_settings, source_ip, ip_scope, geolocation, reputation, danger_score)
    if llm_summary:
        danger_summary = llm_summary
        normalized = llm_summary.lower()
        if 'not dangerous' in normalized:
            dangerous = False
        elif 'dangerous' in normalized:
            dangerous = True
        else:
            dangerous = dangerous

    return AccessIntelResult(
        source_ip=source_ip,
        ip_scope=ip_scope,
        geolocation=geolocation,
        reputation=reputation,
        lookup_status=lookup_status,
        danger_score=danger_score,
        dangerous=dangerous,
        danger_summary=danger_summary,
    )
