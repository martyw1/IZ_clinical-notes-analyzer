from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import Protocol
from app.v2.services.deadline_calendar import business_day_horizon
from app.v2.services.evaluation_evidence import parse_date


class DashboardTreatmentPlan(Protocol):
    patient_record_id: int
    last_updated: str
    next_due_date: str
    plan_version_id: int

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list[JsonPrimitive] | dict[str, JsonPrimitive]


def dashboard_payload(
    treatment_plans: Sequence[DashboardTreatmentPlan],
    *,
    api_configured: bool,
    api_client_id_configured: bool,
    api_enabled: bool,
    sync_enabled: bool,
    sync_authorized: bool,
    loc_change_window_validated: bool,
    evaluation_date: date,
) -> dict[str, JsonValue]:
    has_imports = bool(treatment_plans)
    api_status, api_detail = _api_readiness(api_configured, api_enabled)
    blockers = []
    if not has_imports:
        blockers.append("No normalized treatment-plan records are available. Import a supported manual file or run an approved sync.")
    if not api_configured:
        blockers.append("API credentials are not configured; live connectivity testing is unavailable.")
    elif not api_enabled:
        blockers.append("API credentials are saved but API use is disabled.")
    elif not api_client_id_configured:
        blockers.append("OAuth client ID is not configured.")
    elif not sync_enabled:
        blockers.append("Treatment-plan sync is disabled in Settings.")
    elif not sync_authorized:
        blockers.append("Live read-only treatment-plan import is not authorized for this tenant.")
    if not loc_change_window_validated:
        blockers.append("LOC-change update window is unvalidated and configurable.")
    latest, uncertain = latest_patient_plans(treatment_plans)
    if uncertain:
        blockers.append(f"{uncertain} patient record(s) excluded from deadline counts because the latest plan cannot be determined from valid last updated dates.")
    due_dates = tuple(parse_date(row.next_due_date) for row in latest)
    unavailable = sum(due is None for due in due_dates)
    if unavailable:
        blockers.append(f"{unavailable} latest plan(s) have no computable update deadline; review the plan dates and LOC.")
    horizon = business_day_horizon(evaluation_date)
    return {
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "source_cards": [
            {
                "label": "Manual upload readiness",
                "status": "ready" if has_imports else "awaiting data",
                "detail": f"{len(treatment_plans)} normalized treatment-plan aggregate(s) imported." if has_imports else "No normalized treatment-plan aggregates have been imported.",
            },
            {"label": "API readiness", "status": api_status, "detail": api_detail},
            {
                "label": "Alleva treatment-plan sync readiness",
                "status": "ready" if api_configured and api_client_id_configured and api_enabled and sync_enabled and sync_authorized else "not ready",
                "detail": "Built-in Alleva v1 mapping will be applied automatically." if api_configured and api_client_id_configured and api_enabled and sync_enabled and sync_authorized else "Save the client ID and encrypted secret, then enable and authorize live read-only sync in Settings.",
            },
        ],
        "metrics": {
            "overdue_plans": sum(due is not None and due < evaluation_date for due in due_dates),
            "due_soon_plans": sum(due is not None and evaluation_date <= due <= horizon for due in due_dates),
        },
        "blockers": blockers,
    }


def latest_patient_plans(rows: Sequence[DashboardTreatmentPlan]) -> tuple[tuple[DashboardTreatmentPlan, ...], int]:
    """One latest clinical update per authorized patient record, never import order."""
    grouped: dict[int, list[DashboardTreatmentPlan]] = {}
    for row in rows:
        grouped.setdefault(row.patient_record_id, []).append(row)
    selected = []
    uncertain = 0
    for plans in grouped.values():
        try:
            dates = [datetime.fromisoformat(row.last_updated.strip().replace("Z", "+00:00")) for row in plans]
            dates = [value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc) for value in dates]
        except ValueError:
            uncertain += 1
            continue
        newest = max(dates)
        candidates = [row for row, updated in zip(plans, dates, strict=True) if updated == newest]
        if len({row.next_due_date for row in candidates}) > 1:
            uncertain += 1
            continue
        selected.append(max(candidates, key=lambda row: row.plan_version_id))
    return tuple(selected), uncertain


def _api_readiness(api_configured: bool, api_enabled: bool) -> tuple[str, str]:
    if not api_configured:
        return "not configured", "No encrypted API credential is saved for connectivity testing."
    if not api_enabled:
        return "configured; disabled", "An encrypted API credential is saved, but API use remains disabled."
    return "configured for testing", "Encrypted API credentials are saved and bounded connectivity testing is enabled."
