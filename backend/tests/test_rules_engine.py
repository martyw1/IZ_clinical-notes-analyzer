from app.services.rules_engine import evaluate_rules, load_rules_config, validate_rules_config


def test_rules_config_loads_and_validates():
    config = load_rules_config()
    assert validate_rules_config(config) == []
    assert config['workflow']['id'] == 'treatment_plan_tracking'


def test_php_current_treatment_plan_passes():
    result = evaluate_rules(
        {
            'chart_id': 'demo-php-current',
            'client_status': 'active',
            'current_level_of_care': 'PHP',
            'treatment_plan': {'exists': True, 'last_updated_date': '2026-05-01'},
            'attendance': {'week_start_date': '2026-05-11', 'individual_sessions_completed_count': 2},
        },
        evaluation_date='2026-05-12',
    )
    assert result.overall_status in {'compliant', 'due_soon'}
    assert result.derived_fields['mapped_level_of_care'] == 'PHP'
    assert result.derived_fields['treatment_plan_calculated_due_date'] == '2026-05-31'


def test_late_iop_treatment_plan_fails():
    result = evaluate_rules(
        {
            'chart_id': 'demo-iop-late',
            'client_status': 'active',
            'current_level_of_care': 'Intensive Outpatient',
            'treatment_plan': {'exists': True, 'last_completed_date': '2026-01-01'},
            'attendance': {'week_start_date': '2026-05-11', 'individual_sessions_completed_count': 1},
        },
        evaluation_date='2026-05-12',
    )
    assert result.overall_status == 'noncompliant'
    assert result.derived_fields['mapped_level_of_care'] == 'IOP'
    assert result.derived_fields['treatment_plan_calculated_due_date'] == '2026-03-02'
    assert any(finding.rule_id == 'TP-031' and finding.status == 'noncompliant' for finding in result.findings)


def test_unknown_level_of_care_is_unable_to_evaluate():
    result = evaluate_rules(
        {
            'chart_id': 'demo-unknown-loc',
            'client_status': 'active',
            'current_level_of_care': 'Residential',
            'treatment_plan': {'exists': True, 'last_updated_date': '2026-05-01'},
        },
        evaluation_date='2026-05-12',
    )
    assert result.overall_status == 'unable_to_evaluate'
    assert any(finding.rule_id == 'TP-011' and finding.status == 'unable_to_evaluate' for finding in result.findings)
