from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

LOCAL_MACHINE_TIMEZONE = 'local_machine'


def normalize_timezone_name(value: str | None) -> str:
    raw = (value or '').strip()
    if not raw or raw.lower() in {'local', 'local_machine', 'machine', 'system'}:
        return LOCAL_MACHINE_TIMEZONE
    try:
        ZoneInfo(raw)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f'Unknown timezone: {raw}') from exc
    return raw


def effective_zoneinfo(timezone_name: str | None):
    normalized = normalize_timezone_name(timezone_name)
    if normalized == LOCAL_MACHINE_TIMEZONE:
        return datetime.now().astimezone().tzinfo
    return ZoneInfo(normalized)


def effective_timezone_label(timezone_name: str | None) -> str:
    normalized = normalize_timezone_name(timezone_name)
    zone = effective_zoneinfo(normalized)
    if normalized == LOCAL_MACHINE_TIMEZONE:
        suffix = datetime.now(zone).tzname() if zone else 'local time'
        return f'Local machine timezone ({suffix})'
    return normalized


def localize_datetime(value: datetime | None, timezone_name: str | None) -> datetime | None:
    if value is None:
        return None
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(effective_zoneinfo(timezone_name))


def format_local_timestamp(value: datetime, timezone_name: str | None, *, for_filename: bool = False) -> str:
    local_value = localize_datetime(value, timezone_name)
    if local_value is None:
        return ''
    return local_value.strftime('%Y-%m-%d_%H-%M-%S' if for_filename else '%Y-%m-%d %H:%M:%S %Z')
