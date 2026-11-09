"""Recurring deadline dates and the calendar-day warning window."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def plan_update_date(raw: str, facility_timezone: str = "") -> date | None:
    try:
        value = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        if value.tzinfo is not None and facility_timezone:
            value = value.astimezone() if facility_timezone == "local_machine" else value.astimezone(ZoneInfo(facility_timezone))
        return value.date()
    except (ValueError, ZoneInfoNotFoundError):
        return None


def deadline_status(due: date | None, today: date) -> str:
    if due is None:
        return "Unable to Evaluate"
    if due < today:
        return "Overdue"
    if due <= today + timedelta(days=10):
        return "Due Soon"
    return "Current/Compliant"


def computed_deadline_details(aggregate, package, today: date, facility_timezone: str) -> tuple[str, str]:
    """Explain the recurring schedule independently of checklist and worklist eligibility."""
    from app.v2.services.evaluation_evidence import collect_evidence
    evidence = collect_evidence(aggregate, package, today, facility_timezone)
    if sum(family in aggregate.current_level_of_care.casefold() for family in ("iop","php","gop")) > 1:
        return "Conflicting Evidence", "The LOC contains multiple timing categories (PHP, IOP or GOP). Confirm the current category before calculating a deadline."
    if evidence.anchor_source == "conflicting first created dates":
        return "Conflicting Evidence", "Conflicting first created dates exist for this selected plan; confirm its clock anchor."
    reasons = []
    if evidence.interval_days is None:
        reasons.append("The LOC is missing or does not match a configured LOC alias.")
    if evidence.anchor is None:
        reasons.append("Neither a usable last updated date nor an unambiguous first created date is available for this plan. Admission and review dates are not substituted.")
    elif evidence.anchor > today:
        reasons.append("The selected plan clock anchor is in the future.")
    if reasons:
        return "Unable to Evaluate", " ".join(reasons)
    return deadline_status(evidence.calculated_due, today), (
        f"{evidence.mapped_loc} using {evidence.anchor_source}: {evidence.anchor.isoformat()} + {evidence.interval_days} calendar days "
        f"= {evidence.calculated_due.isoformat()}. Due Soon includes today through 10 calendar days ahead. "
        "This schedule status does not resolve missing or conflicting checklist evidence."
    )


def recurring_plan_anchor(aggregate, facility_timezone: str = "") -> tuple[date | None, str]:
    updated = plan_update_date(aggregate.source_last_updated, facility_timezone)
    if updated is not None:
        return updated, "last updated"
    # Use creation evidence for this exact plan, never admission, import time or another plan.
    selected = aggregate.content_snapshot.plan_id
    candidates = []
    for row in aggregate.treatment_plans:
        identity = str(row.get("plan_id", row.get("id", "")))
        if identity and identity != selected:
            continue
        raw = row.get("created_date", row.get("createdDate", ""))
        if isinstance(raw, str) and (created := plan_update_date(raw, facility_timezone)) is not None:
            candidates.append(created)
    dates = set(candidates)
    if len(dates) > 1:
        return None, "conflicting first created dates"
    return (next(iter(dates)), "first created (last updated unavailable)") if dates else (None, "creation unavailable")


def plan_tracking_timestamp(aggregate) -> str:
    """Keep source last_updated untouched while ranking valid creation-fallback plans."""
    try:
        datetime.fromisoformat(aggregate.source_last_updated.strip().replace("Z", "+00:00"))
        return aggregate.source_last_updated
    except ValueError:
        pass
    # Only use creation evidence already accepted by the evaluator for this plan.
    if not aggregate.date_clock_anchor or aggregate.date_clock_anchor == "Unknown":
        return ""
    created = []
    for row in aggregate.treatment_plans:
        identity = str(row.get("plan_id", row.get("id", "")))
        if identity and identity != aggregate.content_snapshot.plan_id:
            continue
        raw = row.get("created_date", row.get("createdDate", ""))
        if not isinstance(raw, str):
            continue
        try:
            instant = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        except ValueError:
            continue
        created.append(instant.replace(tzinfo=timezone.utc) if instant.tzinfo is None else instant.astimezone(timezone.utc))
    return min(created).isoformat() if created else ""
