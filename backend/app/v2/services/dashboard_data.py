from __future__ import annotations

from collections.abc import Sequence

from app.v2.models import TreatmentPlanImport

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list[JsonPrimitive] | dict[str, JsonPrimitive]


def dashboard_payload(treatment_plans: Sequence[TreatmentPlanImport]) -> dict[str, JsonValue]:
    return {
        "source_cards": [
            {
                "label": "Manual upload readiness",
                "status": "ready",
                "detail": f"{len(treatment_plans)} normalized treatment-plan aggregate(s) imported.",
            },
            {"label": "API readiness", "status": "configured for testing", "detail": "Alleva harness uses bounded responses."},
            {"label": "Alleva treatment-plan sync readiness", "status": "blocked", "detail": "Live sync remains gated pending R3/Alleva approval."},
        ],
        "metrics": {
            "active_patient_ids": len(treatment_plans),
            "overdue_plans": 0,
            "urgent_plans": 0,
            "due_soon_plans": 0,
            "needs_review": _count_status(treatment_plans, "Needs Review"),
            "missing_data": sum(row.missing_criteria_count for row in treatment_plans),
            "returned": 0,
            "conflicting": _count_status(treatment_plans, "Conflicting Evidence"),
            "unable": _count_status(treatment_plans, "Unable to Evaluate"),
        },
        "blockers": ["LOC-change update window is unvalidated and configurable."],
    }


def _count_status(treatment_plans: Sequence[TreatmentPlanImport], status: str) -> int:
    return sum(1 for row in treatment_plans if row.overall_status == status)
