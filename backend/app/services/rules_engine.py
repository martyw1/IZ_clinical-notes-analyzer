from __future__ import annotations

"""YAML-driven completeness rules engine.

The engine is deliberately deterministic: it checks field presence, date math,
level-of-care mappings, and numeric attendance/completeness facts without using
an LLM. Future clinical-text analysis can be plugged in later as an explicit
separate analyzer rather than silently changing v1 compliance outcomes.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from app.core.config import settings

VALID_SEVERITIES = {'info', 'warning', 'high', 'critical', 'unable_to_evaluate'}
VALID_STATUSES = {'compliant', 'due_soon', 'noncompliant', 'unable_to_evaluate'}


@dataclass(frozen=True)
class RuleFinding:
    rule_id: str
    rule_name: str
    workflow_id: str
    category: str
    severity: str
    status: str
    passed: bool
    message: str
    expected: str = ''
    actual: str = ''
    emitted: bool = True
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuleEvaluationResult:
    workflow_id: str
    evaluation_date: str
    overall_status: str
    highest_severity: str
    findings: list[RuleFinding]
    derived_fields: dict[str, Any]
    source_fields: dict[str, Any]


def load_rules_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load the configured YAML rules file."""
    config_path = Path(path) if path else settings.rules_config_file
    with config_path.open('r', encoding='utf-8') as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f'Rules config {config_path} must contain a YAML object at the top level.')
    return payload


def validate_rules_config(config: dict[str, Any]) -> list[str]:
    """Return validation errors for a rules YAML document."""
    errors: list[str] = []
    if not config.get('config_version'):
        errors.append('config_version is required')
    workflow = config.get('workflow')
    if not isinstance(workflow, dict) or not workflow.get('id'):
        errors.append('workflow.id is required')
    if not isinstance(config.get('levels_of_care'), dict):
        errors.append('levels_of_care must be a mapping')
    rules = config.get('rules')
    if not isinstance(rules, list) or not rules:
        errors.append('rules must be a non-empty list')
        return errors

    seen_ids: set[str] = set()
    for index, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            errors.append(f'rules[{index}] must be a mapping')
            continue
        rule_id = str(rule.get('id') or '').strip()
        if not rule_id:
            errors.append(f'rules[{index}].id is required')
        elif rule_id in seen_ids:
            errors.append(f'duplicate rule id: {rule_id}')
        seen_ids.add(rule_id)
        severity = str(rule.get('severity') or '').strip()
        if severity not in VALID_SEVERITIES:
            errors.append(f'{rule_id or f"rules[{index}]"}: unknown severity {severity!r}')
        logic = rule.get('logic')
        if not isinstance(logic, dict) or not logic.get('type'):
            errors.append(f'{rule_id or f"rules[{index}]"}: logic.type is required')
    return errors


def get_field(data: dict[str, Any], dotted_path: str, default: Any = None) -> Any:
    """Read dotted fields like treatment_plan.exists from nested dictionaries."""
    current: Any = data
    for part in dotted_path.split('.'):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default
    return current


def set_field(data: dict[str, Any], dotted_path: str, value: Any) -> None:
    """Write dotted fields into a nested dictionary."""
    parts = dotted_path.split('.')
    current = data
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _format_value(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if value is None:
        return ''
    return str(value)


def _compare(left: Any, operator: str, right: Any) -> bool:
    if operator == '==':
        return left == right
    if operator == '!=':
        return left != right
    if operator == '<=':
        return left <= right
    if operator == '<':
        return left < right
    if operator == '>=':
        return left >= right
    if operator == '>':
        return left > right
    raise ValueError(f'Unsupported operator: {operator}')


def _message(template: str, context: dict[str, Any]) -> str:
    flattened = dict(context)

    def flatten(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                flatten(f'{prefix}.{key}' if prefix else str(key), nested)
        else:
            flattened[prefix] = _format_value(value)

    flatten('', context)
    try:
        return template.format(**flattened)
    except Exception:
        return template


def _map_level_of_care(config: dict[str, Any], raw_value: str) -> str | None:
    normalized = (raw_value or '').strip().lower()
    if not normalized:
        return None
    for key, level in (config.get('levels_of_care') or {}).items():
        aliases = [str(key), *(level.get('aliases') or [])]
        if normalized in {alias.strip().lower() for alias in aliases}:
            return str(key)
    return None


def _resolve_config_path(config: dict[str, Any], dotted_path: str, context: dict[str, Any]) -> Any:
    path = dotted_path
    for key, value in context.items():
        if not isinstance(value, dict):
            path = path.replace('{' + key + '}', str(value))
    return get_field(config, path)


def _first_present(data: dict[str, Any], field_names: list[str]) -> tuple[str, Any] | None:
    for field_name in field_names:
        value = get_field(data, field_name)
        if value not in (None, ''):
            return field_name, value
    return None


def _finding(rule: dict[str, Any], *, passed: bool, status: str, message: str, expected: str = '', actual: str = '', emitted: bool = True, details: dict[str, Any] | None = None) -> RuleFinding:
    return RuleFinding(
        rule_id=str(rule.get('id')),
        rule_name=str(rule.get('name') or rule.get('id')),
        workflow_id=str(rule.get('workflow_id') or ''),
        category=str(rule.get('category') or ''),
        severity=str(rule.get('severity') or 'info'),
        status=status,
        passed=passed,
        message=message,
        expected=expected,
        actual=actual,
        emitted=emitted,
        details=details or {},
    )


def evaluate_rules(chart: dict[str, Any], config: dict[str, Any] | None = None, *, evaluation_date: str | date | None = None) -> RuleEvaluationResult:
    """Evaluate one normalized chart payload against the YAML rule config."""
    config = config or load_rules_config()
    validation_errors = validate_rules_config(config)
    if validation_errors:
        raise ValueError('; '.join(validation_errors))

    context = dict(chart)
    if not isinstance(context.get('treatment_plan'), dict):
        context['treatment_plan'] = dict(context.get('treatment_plan') or {})
    if not isinstance(context.get('attendance'), dict):
        context['attendance'] = dict(context.get('attendance') or {})
    if not isinstance(context.get('requirements'), dict):
        context['requirements'] = dict(context.get('requirements') or {})

    eval_date = _as_date(evaluation_date) or _as_date(context.get('evaluation_date')) or date.today()
    context['evaluation_date'] = eval_date.isoformat()
    raw_level = str(context.get('current_level_of_care') or '')
    mapped_level = _map_level_of_care(config, raw_level)
    if mapped_level:
        context['mapped_level_of_care'] = mapped_level

    effective = _first_present(context, ['treatment_plan.last_updated_date', 'treatment_plan.last_completed_date'])
    if effective:
        _, effective_value = effective
        set_field(context, 'treatment_plan_effective_date', _format_value(_as_date(effective_value) or effective_value))

    findings: list[RuleFinding] = []
    for rule in config.get('rules') or []:
        if not rule.get('enabled', True):
            continue
        applies_to = rule.get('applies_to') or {}
        if isinstance(applies_to, dict):
            skip = False
            for field_name, allowed_values in applies_to.items():
                if get_field(context, field_name) not in allowed_values:
                    skip = True
                    break
            if skip:
                continue

        logic = rule.get('logic') or {}
        logic_type = logic.get('type')
        passed = False
        status_on_fail = str(rule.get('output_status_on_fail') or 'noncompliant')
        status_on_pass = str(rule.get('output_status_on_pass') or 'compliant')
        expected = ''
        actual = ''
        details: dict[str, Any] = {'logic_type': logic_type}

        try:
            if logic_type == 'scope_filter':
                include = logic.get('include_when') or {}
                value = get_field(context, str(include.get('field')))
                expected = ', '.join(map(str, include.get('value') or []))
                actual = _format_value(value)
                passed = value in (include.get('value') or [])
                if not passed and rule.get('output_status_on_fail') == 'compliant':
                    status_on_fail = 'compliant'

            elif logic_type == 'field_required':
                value = get_field(context, str(logic.get('field')))
                actual = _format_value(value)
                expected = 'non-empty value'
                passed = value not in (None, '')

            elif logic_type == 'lookup_required':
                value = str(get_field(context, str(logic.get('field'))) or '')
                mapped = _map_level_of_care(config, value)
                expected = str(logic.get('lookup_table') or '')
                actual = value
                passed = bool(mapped)
                if mapped:
                    context['mapped_level_of_care'] = mapped
                    details['mapped_level_of_care'] = mapped

            elif logic_type == 'boolean_required_true':
                value = get_field(context, str(logic.get('field')))
                expected = 'true'
                actual = _format_value(value)
                passed = value is True or str(value).lower() == 'true'

            elif logic_type == 'at_least_one_field_required':
                present = _first_present(context, [str(item) for item in logic.get('fields') or []])
                expected = 'at least one configured field'
                actual = present[0] if present else ''
                passed = bool(present)
                if present and 'treatment_plan' in present[0]:
                    parsed = _as_date(present[1])
                    context['treatment_plan_effective_date'] = _format_value(parsed or present[1])

            elif logic_type == 'date_add':
                source_date = _as_date(get_field(context, str(logic.get('source_date_field'))))
                interval = _resolve_config_path(config, str(logic.get('interval_days_from') or ''), context)
                if source_date is None or interval is None:
                    status_on_fail = 'unable_to_evaluate'
                    passed = False
                    details['missing_prerequisite'] = {
                        'source_date_field': str(logic.get('source_date_field')),
                        'source_date_value': _format_value(source_date),
                        'interval_days_from': str(logic.get('interval_days_from') or ''),
                        'interval_value': _format_value(interval),
                    }
                else:
                    due_date = source_date + timedelta(days=int(interval))
                    set_field(context, str(logic.get('output_field')), due_date.isoformat())
                    expected = f'{source_date.isoformat()} + {interval} calendar days'
                    actual = due_date.isoformat()
                    passed = True

            elif logic_type == 'date_compare':
                left = _as_date(get_field(context, str(logic.get('left_field'))))
                right = _as_date(get_field(context, str(logic.get('right_field'))))
                expected = f'{logic.get("left_field")} {logic.get("operator")} {logic.get("right_field")}'
                actual = f'{_format_value(left)} {logic.get("operator")} {_format_value(right)}'
                if left is None or right is None:
                    status_on_fail = 'unable_to_evaluate'
                    passed = False
                    details['missing_prerequisite'] = {
                        'left_field': str(logic.get('left_field')),
                        'left_value': _format_value(left),
                        'right_field': str(logic.get('right_field')),
                        'right_value': _format_value(right),
                    }
                else:
                    passed = _compare(left, str(logic.get('operator')), right)

            elif logic_type == 'days_until':
                left = _as_date(get_field(context, str(logic.get('from_date_field'))))
                right = _as_date(get_field(context, str(logic.get('to_date_field'))))
                if left and right:
                    delta = (right - left).days
                    operator = str(logic.get('operator'))
                    target = logic.get('value')
                    if operator == 'between_inclusive' and isinstance(target, dict):
                        minimum = int(target.get('min', 0))
                        maximum = target.get('max')
                        if maximum is None and target.get('max_from_engine_default'):
                            maximum = get_field(config, 'engine.evaluation_defaults.' + str(target['max_from_engine_default']))
                        maximum = int(maximum)
                        passed = minimum <= delta <= maximum
                        expected = f'{minimum} <= days_until <= {maximum}'
                    else:
                        passed = _compare(delta, operator, int(target))
                        expected = f'days_until {operator} {target}'
                    actual = str(delta)
                else:
                    status_on_fail = 'unable_to_evaluate'
                    passed = False
                    details['missing_prerequisite'] = {
                        'from_date_field': str(logic.get('from_date_field')),
                        'from_date_value': _format_value(left),
                        'to_date_field': str(logic.get('to_date_field')),
                        'to_date_value': _format_value(right),
                    }

            elif logic_type == 'numeric_compare':
                left = get_field(context, str(logic.get('left_field')))
                if logic.get('right_field'):
                    right = get_field(context, str(logic.get('right_field')))
                elif logic.get('right_value_from'):
                    right = _resolve_config_path(config, str(logic.get('right_value_from')), context)
                else:
                    right = logic.get('right_value')
                expected = _format_value(right)
                actual = _format_value(left)
                if left is None or right is None:
                    status_on_fail = 'unable_to_evaluate'
                    passed = False
                    details['missing_prerequisite'] = {
                        'left_field': str(logic.get('left_field')),
                        'left_value': _format_value(left),
                        'right_value': _format_value(right),
                    }
                else:
                    passed = _compare(float(left), str(logic.get('operator')), float(right))

            elif logic_type == 'per_day_numeric_compare':
                values = get_field(context, str(logic.get('collection_field')))
                right = _resolve_config_path(config, str(logic.get('right_value_from')), context)
                expected = f'each day >= {right}'
                actual = _format_value(values)
                if right is None:
                    status_on_fail = 'unable_to_evaluate'
                    passed = False
                elif isinstance(values, dict):
                    passed = all(float(value) >= float(right) for value in values.values())
                elif isinstance(values, list):
                    passed = all(float(value) >= float(right) for value in values)
                else:
                    status_on_fail = 'unable_to_evaluate'
                    passed = False

            elif logic_type == 'detect_level_of_care_change_within_period':
                history = get_field(context, str(logic.get('history_field')))
                start = _as_date(get_field(context, str(logic.get('period_start_field'))))
                end = _as_date(get_field(context, str(logic.get('period_end_field'))))
                changes = []
                if isinstance(history, list) and start and end:
                    for entry in history:
                        if isinstance(entry, dict):
                            changed_at = _as_date(entry.get('date') or entry.get('start_date'))
                            if changed_at and start <= changed_at <= end:
                                changes.append(entry)
                passed = bool(changes)
                expected = 'level-of-care transition detected only when present'
                actual = str(len(changes))
                details['changes'] = changes

            else:
                status_on_fail = 'unable_to_evaluate'
                expected = 'supported rule type'
                actual = str(logic_type)
                passed = False

        except Exception as exc:
            status_on_fail = 'unable_to_evaluate'
            passed = False
            details['error'] = str(exc)

        status = status_on_pass if passed else status_on_fail
        if status not in VALID_STATUSES:
            status = 'unable_to_evaluate'
        template = str(rule.get('pass_message') if passed else rule.get('unavailable_data_message') or rule.get('fail_message') or '')
        message = _message(template, context)
        emitted = not bool(rule.get('emit_only_when_true')) or passed
        findings.append(_finding(rule, passed=passed, status=status, message=message, expected=expected, actual=actual, emitted=emitted, details=details))

    visible_findings = [finding for finding in findings if finding.emitted]
    blocking = [finding for finding in visible_findings if finding.status in {'noncompliant', 'unable_to_evaluate'}]
    due_soon = [finding for finding in visible_findings if finding.status == 'due_soon']
    overall_status = 'noncompliant' if any(f.status == 'noncompliant' for f in blocking) else 'unable_to_evaluate' if blocking else 'due_soon' if due_soon else 'compliant'
    severity_rank = {'info': 1, 'warning': 2, 'high': 3, 'critical': 4, 'unable_to_evaluate': 5}
    highest_severity = max((finding.severity for finding in visible_findings), key=lambda item: severity_rank.get(item, 0), default='info')
    return RuleEvaluationResult(
        workflow_id=str((config.get('workflow') or {}).get('id') or ''),
        evaluation_date=eval_date.isoformat(),
        overall_status=overall_status,
        highest_severity=highest_severity,
        findings=visible_findings,
        derived_fields={
            'mapped_level_of_care': context.get('mapped_level_of_care'),
            'treatment_plan_effective_date': context.get('treatment_plan_effective_date'),
            'treatment_plan_calculated_due_date': get_field(context, 'treatment_plan.calculated_due_date'),
        },
        source_fields=context,
    )


def result_as_dict(result: RuleEvaluationResult) -> dict[str, Any]:
    """Serialize a rule result for API and tests without leaking Python objects."""
    return {
        'workflow_id': result.workflow_id,
        'evaluation_date': result.evaluation_date,
        'overall_status': result.overall_status,
        'highest_severity': result.highest_severity,
        'derived_fields': result.derived_fields,
        'source_fields': result.source_fields,
        'findings': [finding.__dict__ for finding in result.findings],
    }
