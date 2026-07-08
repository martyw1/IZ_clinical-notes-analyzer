from __future__ import annotations

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list[JsonPrimitive] | dict[str, JsonPrimitive]


def dashboard_payload() -> dict[str, JsonValue]:
    return {
        "source_cards": [
            {"label": "Manual upload readiness", "status": "ready", "detail": "PDF, CSV, TSV, XLSX and text paths supported."},
            {"label": "API readiness", "status": "configured for testing", "detail": "Alleva harness uses bounded responses."},
            {"label": "Alleva treatment-plan sync readiness", "status": "blocked", "detail": "Live sync remains gated pending R3/Alleva approval."},
        ],
        "metrics": {
            "active_patient_ids": 1,
            "overdue_plans": 0,
            "urgent_plans": 0,
            "due_soon_plans": 0,
            "needs_review": 1,
            "missing_data": 3,
            "returned": 0,
            "conflicting": 0,
            "unable": 0,
        },
        "blockers": ["LOC-change update window is unvalidated and configurable."],
    }
