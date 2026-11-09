from datetime import date

import pytest

from app.v2.services.deadline_calendar import deadline_status
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


def test_calendar_warning_window_includes_today_weekends_and_day_ten():
    today = date(2026, 10, 16)  # Friday
    assert deadline_status(date(2026, 10, 15), today) == "Overdue"
    for due in (today, date(2026, 10, 18), date(2026, 10, 26)):
        assert deadline_status(due, today) == "Due Soon"
    assert deadline_status(date(2026, 10, 27), today) == "Current/Compliant"
    assert deadline_status(None, today) == "Unable to Evaluate"


@pytest.mark.parametrize("loc,expected", [("PHP-5", "2026-10-08"), ("PHP 5", "2026-10-08"), ("IOP-19", "2026-11-07"), ("OP", "2026-11-07")])
def test_loc_aliases_compute_configured_interval(loc, expected):
    result = evaluate_plan_version(_aggregate(loc=loc, due="Unknown").model_copy(update={
        "source_last_updated": "2026-09-08T13:00:00Z",
    }), load_rule_package(), date(2026, 10, 16), "America/New_York")
    assert result.calculated_due_date == expected


@pytest.mark.parametrize("loc", ["PHP \u2013 5", "  php-5  ", "PHP\u00a05"])
def test_loc_presentation_variants_keep_exact_configured_mapping(loc):
    result = evaluate_plan_version(_aggregate(loc=loc).model_copy(update={"source_last_updated": "2026-09-08"}),
                                  load_rule_package(), date(2026, 10, 16), "America/New_York")
    assert result.calculated_due_date == "2026-10-08"


@pytest.mark.parametrize("loc,updated,reason", [("Unknown LOC", "2026-09-08", "LOC"),
    ("PHP", "", "first created"), ("PHP", "invalid", "first created"),
    ("PHP", "2027-01-01", "future")])
def test_unavailable_deadlines_explain_actual_missing_input(loc, updated, reason):
    from app.v2.services.deadline_calendar import computed_deadline_details
    status, explanation = computed_deadline_details(_aggregate(loc=loc).model_copy(update={"source_last_updated": updated}),
                                                    load_rule_package(), date(2026, 10, 16), "America/New_York")
    assert status == "Unable to Evaluate"
    assert reason in explanation


def test_settings_and_calculator_use_the_same_configured_intervals(monkeypatch):
    from dataclasses import replace
    from app.v2.api import foundation_routes
    from app.v2.models import AppSetting
    from app.v2.services.deadline_calendar import computed_deadline_details
    package = load_rule_package()
    levels = dict(package.rules.levels_of_care)
    levels["PHP"] = levels["PHP"].model_copy(update={"treatment_plan_update_interval_days": 17})
    package = replace(package, rules=package.rules.model_copy(update={"levels_of_care": levels}))
    monkeypatch.setattr(foundation_routes, "load_rule_package", lambda: package)
    settings = foundation_routes._settings_out(AppSetting(organization_name="Synthetic", facility_timezone="America/New_York"))
    assert settings.treatment_plan_php_review_interval_days == 17
    aggregate = _aggregate(loc="PHP-5").model_copy(update={"source_last_updated": "2026-09-08"})
    result = evaluate_plan_version(aggregate, package, date(2026, 10, 16), "America/New_York")
    assert result.calculated_due_date == "2026-09-25"
    status, explanation = computed_deadline_details(aggregate, package, date(2026, 10, 16), "America/New_York")
    assert status == "Overdue"
    assert "+ 17 calendar days" in explanation


@pytest.mark.parametrize("loc,days", [("IOP 4", 60), ("Evening IOP 4 group", 60), ("IOP-ANY", 60), ("PHP 4 day", 30), ("Program PHP extended", 30)])
def test_user_loc_family_substrings_apply_canonical_rule(loc, days):
    from datetime import timedelta
    aggregate = _aggregate(loc=loc).model_copy(update={"source_last_updated": "2026-09-01"})
    result = evaluate_plan_version(aggregate, load_rule_package(), date(2026, 11, 6), "America/New_York")
    assert result.calculated_due_date == (date(2026, 9, 1) + timedelta(days=days)).isoformat()


@pytest.mark.parametrize("updated", ["", "Unknown", "invalid"])
def test_created_fallback_is_exact_plan_evidence_and_is_explained(updated):
    from app.v2.services.deadline_calendar import computed_deadline_details
    aggregate = _aggregate(loc="IOP 4").model_copy(update={"source_last_updated": updated})
    aggregate = aggregate.model_copy(update={"treatment_plans": ({"plan_id": aggregate.content_snapshot.plan_id, "created_date": "2026-09-01T12:00:00Z"},)})
    result = evaluate_plan_version(aggregate, load_rule_package(), date(2026, 11, 6), "America/New_York")
    assert result.calculated_due_date == "2026-10-31"
    assert "first created" in computed_deadline_details(aggregate, load_rule_package(), date(2026, 11, 6), "America/New_York")[1]
    aggregate = aggregate.model_copy(update={"source_last_updated": "2026-09-10"})
    assert evaluate_plan_version(aggregate, load_rule_package(), date(2026, 11, 6), "America/New_York").calculated_due_date == "2026-11-09"


def test_conflicting_family_and_other_plan_creation_never_guess():
    aggregate = _aggregate(loc="PHP / IOP transition").model_copy(update={"source_last_updated": "2026-09-01"})
    result = evaluate_plan_version(aggregate, load_rule_package(), date(2026, 11, 6), "America/New_York")
    assert result.calculated_due_date == ""
    assert result.overall_status == "Conflicting Evidence"
    aggregate = _aggregate(loc="IOP 4").model_copy(update={"source_last_updated": "", "treatment_plans": ({"plan_id": "OTHER", "created_date": "2026-09-01"},)})
    assert evaluate_plan_version(aggregate, load_rule_package(), date(2026, 11, 6), "America/New_York").calculated_due_date == ""



def test_conflicting_created_dates_require_review_without_a_computed_date():
    aggregate = _aggregate(loc="IOP 4").model_copy(update={"source_last_updated": ""})
    plan_id = aggregate.content_snapshot.plan_id
    aggregate = aggregate.model_copy(update={"treatment_plans": ({"plan_id": plan_id, "created_date": "2026-09-01"}, {"plan_id": plan_id, "created_date": "2026-09-03"})})
    result = evaluate_plan_version(aggregate, load_rule_package(), date(2026, 11, 6), "America/New_York")
    assert result.calculated_due_date == ""
    assert result.overall_status == "Conflicting Evidence"


@pytest.mark.parametrize("loc",["GOP","gop","GOP 4","Evening GOP program"])
def test_gop_uses_thirty_days_and_creation_fallback(loc):
    from app.v2.services.deadline_calendar import computed_deadline_details
    aggregate=_aggregate(loc=loc).model_copy(update={'source_last_updated':'2026-09-01T12:00:00Z'})
    result=evaluate_plan_version(aggregate,load_rule_package(),date(2026,11,6),'America/New_York')
    assert result.mapped_level_of_care=='GOP' and result.calculated_due_date=='2026-10-01'
    assert 'GOP' in computed_deadline_details(aggregate,load_rule_package(),date(2026,11,6),'America/New_York')[1]
    aggregate=aggregate.model_copy(update={'source_last_updated':'','treatment_plans':({'plan_id':aggregate.content_snapshot.plan_id,'created_date':'2026-09-01T12:00:00Z'},)})
    assert evaluate_plan_version(aggregate,load_rule_package(),date(2026,11,6),'America/New_York').calculated_due_date=='2026-10-01'


def test_settings_reports_gop_interval_from_package():
    from app.v2.api.foundation_routes import _settings_out
    from app.v2.models import AppSetting
    settings=_settings_out(AppSetting(organization_name='Synthetic',facility_timezone='America/New_York'))
    assert settings.treatment_plan_gop_review_interval_days==30
