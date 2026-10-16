"""Recurring deadline dates and the Monday-Friday warning window."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def plan_update_date(raw: str, facility_timezone: str = "") -> date | None:
    try:
        value = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        if value.tzinfo is not None and facility_timezone:
            value = value.astimezone() if facility_timezone == "local_machine" else value.astimezone(ZoneInfo(facility_timezone))
        return value.date()
    except (ValueError, ZoneInfoNotFoundError):
        return None


def business_day_horizon(today: date, days: int = 10) -> date:
    horizon = today
    for _ in range(days):
        horizon += timedelta(days=1)
        while horizon.weekday() >= 5:
            horizon += timedelta(days=1)
    return horizon


def deadline_status(due: date | None, today: date) -> str:
    if due is None:
        return "Unable to Evaluate"
    if due < today:
        return "Overdue"
    if due <= business_day_horizon(today):
        return "Due Soon"
    return "Current/Compliant"
