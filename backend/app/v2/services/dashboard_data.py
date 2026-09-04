from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Protocol


class DashboardTreatmentPlan(Protocol):
    patient_record_id: int
    overall_status: str
    missing_criteria_count: int

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
    returned_count: int,
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
            "active_patient_ids": len({row.patient_record_id for row in treatment_plans}),
            "overdue_plans": _count_status(treatment_plans, "Overdue"),
            "urgent_plans": _count_status(treatment_plans, "Urgent"),
            "due_soon_plans": _count_status(treatment_plans, "Due Soon"),
            "needs_review": _count_status(treatment_plans, "Needs Review"),
            "missing_data": sum(row.missing_criteria_count for row in treatment_plans),
            "returned": returned_count,
            "conflicting": _count_status(treatment_plans, "Conflicting Evidence"),
            "unable": _count_status(treatment_plans, "Unable to Evaluate"),
        },
        "blockers": blockers,
    }


def _count_status(treatment_plans: Sequence[DashboardTreatmentPlan], status: str) -> int:
    return sum(1 for row in treatment_plans if row.overall_status == status)


def _api_readiness(api_configured: bool, api_enabled: bool) -> tuple[str, str]:
    if not api_configured:
        return "not configured", "No encrypted API credential is saved for connectivity testing."
    if not api_enabled:
        return "configured; disabled", "An encrypted API credential is saved, but API use remains disabled."
    return "configured for testing", "Encrypted API credentials are saved and bounded connectivity testing is enabled."
