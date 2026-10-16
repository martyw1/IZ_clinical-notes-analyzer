from datetime import date

import pytest

from app.v2.services.deadline_calendar import business_day_horizon, deadline_status
from app.v2.services.deterministic_evaluator import evaluate_plan_version
from app.v2.services.rule_package import load_rule_package
from test_v2_deterministic_evaluator import _aggregate


def test_outpatient_update_uses_sixty_calendar_days_not_creation_or_review():
    aggregate = _aggregate(loc="Outpatient", due="Unknown").model_copy(update={
        "source_last_updated": "2026-09-08T13:00:00Z",
        "treatment_reviews": ({"review_date": "2026-09-01", "signed": True},),
    })
    result = evaluate_plan_version(aggregate, load_rule_package(), date(2026, 10, 16), "America/New_York")
    assert result.recurring_anchor == "2026-09-08"
    assert result.calculated_due_date == "2026-11-07"
    # Missing source due date/signatures still do not imply compliance.
    assert result.overall_status == "Missing Data"


@pytest.mark.parametrize("updated,status", [("", "Missing Data"), ("invalid", "Unable to Evaluate"), ("2027-01-01", "Needs Review")])
def test_missing_invalid_or_future_update_never_uses_admission(updated, status):
    result = evaluate_plan_version(_aggregate().model_copy(update={"source_last_updated": updated}),
                                   load_rule_package(), date(2026, 10, 16), "America/New_York")
    assert result.calculated_due_date == ""
    assert result.overall_status == status


def test_business_warning_window_includes_today_weekends_and_tenth_weekday():
    today = date(2026, 10, 16)  # Friday
    assert business_day_horizon(today) == date(2026, 10, 30)
    assert deadline_status(date(2026, 10, 15), today) == "Overdue"
    for due in (today, date(2026, 10, 18), date(2026, 10, 30)):
        assert deadline_status(due, today) == "Due Soon"
    assert deadline_status(date(2026, 10, 31), today) == "Current/Compliant"
    assert deadline_status(None, today) == "Unable to Evaluate"
